"""Raw Windows system queries (ctypes) — the app's process data source.

Two kernel calls live here:

- `collect_processes_bulk()` — ONE
  `NtQuerySystemInformation(SystemProcessInformation)` call returning every
  process at once, aggregated by display name. It replaces ~300 per-process
  `NtQueryInformationProcess` kernel transitions per tick (~10-20x less CPU),
  which is why the collector's hot path goes through here and not psutil.
- `get_commit_limit_bytes()` — the system commit limit via `GetPerformanceInfo`,
  used as the 100% reference for the Memory window's Commit coloring.

No Qt, no app state: this module answers what Windows currently reports.
"""

import ctypes
import sys
import time
from ctypes import wintypes

import psutil

from ..styles import get_process_display_name


# ═════════════════════════ AGGREGATED ENTRY LAYOUT ═════════════════════════

# `collect_processes_bulk()` returns {display_name: entry}, where entry is a
# plain list indexed by these constants. A list (not a dataclass) because this
# is the hot path: one tick builds a few hundred of them.
CPU_IDX = 0
THREADS_IDX = 1
RSS_IDX = 2
VMS_IDX = 3
COUNT_IDX = 4
PID_IDX = 5


# ════════════════════════ GetPerformanceInfo (psapi) ════════════════════════

class _PERFORMANCE_INFORMATION(ctypes.Structure):
    """Windows PERFORMANCE_INFORMATION structure (psapi.h)."""
    _fields_ = [
        ('cb',                wintypes.DWORD),
        ('CommitTotal',       ctypes.c_size_t),
        ('CommitLimit',       ctypes.c_size_t),
        ('CommitPeak',        ctypes.c_size_t),
        ('PhysicalTotal',     ctypes.c_size_t),
        ('PhysicalAvailable', ctypes.c_size_t),
        ('SystemCache',       ctypes.c_size_t),
        ('KernelTotal',       ctypes.c_size_t),
        ('KernelPaged',       ctypes.c_size_t),
        ('KernelNonpaged',    ctypes.c_size_t),
        ('PageSize',          ctypes.c_size_t),
        ('HandleCount',       wintypes.DWORD),
        ('ProcessCount',      wintypes.DWORD),
        ('ThreadCount',       wintypes.DWORD),
    ]


def get_commit_limit_bytes() -> int:
    """Return system commit limit (RAM + all page files) in bytes via GetPerformanceInfo.

    Returns 0 if GetPerformanceInfo reports failure (documented fallback: commit
    coloring disabled). Falls back to physical RAM total if the ctypes call itself
    raises OSError (documented fallback: commit limit approximated by RAM size).
    """
    try:
        pi = _PERFORMANCE_INFORMATION()
        pi.cb = ctypes.sizeof(pi)
        if not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(pi), pi.cb):
            print("[Vitals] get_commit_limit_bytes: GetPerformanceInfo failed", file=sys.stderr)
            return 0
        return pi.CommitLimit * pi.PageSize
    except OSError as e:
        print(f"[Vitals] get_commit_limit_bytes: WinAPI call failed: {e} - using physical RAM total", file=sys.stderr)
        return psutil.virtual_memory().total


# ═══════════════ NtQuerySystemInformation — structures & binding ═══════════════

_ntdll = ctypes.windll.ntdll


class _UNICODE_STRING_PROC(ctypes.Structure):
    """UNICODE_STRING embedded in SYSTEM_PROCESS_INFORMATION."""
    _fields_ = [
        ("Length",        ctypes.c_ushort),
        ("MaximumLength", ctypes.c_ushort),
        ("Buffer",        ctypes.c_void_p),  # PWSTR — points into the same output buffer
    ]


class _SYSTEM_PROCESS_INFO(ctypes.Structure):
    """
    SYSTEM_PROCESS_INFORMATION (64-bit Windows).
    NtQuerySystemInformation(SystemProcessInformation=5) returns a packed linked
    list of these; each entry is followed by NumberOfThreads SYSTEM_THREAD_INFORMATION
    records that we skip via NextEntryOffset.
    sizeof should be 256 bytes on 64-bit (ctypes auto-aligns c_size_t/c_void_p fields).
    """
    _fields_ = [
        ("NextEntryOffset",               wintypes.ULONG),
        ("NumberOfThreads",               wintypes.ULONG),
        ("_Spare",                        ctypes.c_int64 * 3),   # reserved LARGE_INTEGER[3]
        ("CreateTime",                    ctypes.c_int64),
        ("UserTime",                      ctypes.c_int64),        # CPU user time (100 ns units)
        ("KernelTime",                    ctypes.c_int64),        # CPU kernel time (100 ns units)
        ("ImageName",                     _UNICODE_STRING_PROC),  # process name
        ("BasePriority",                  ctypes.c_long),
        ("UniqueProcessId",               ctypes.c_void_p),       # PID
        ("InheritedFromUniqueProcessId",  ctypes.c_void_p),
        ("HandleCount",                   wintypes.ULONG),
        ("SessionId",                     wintypes.ULONG),
        ("UniqueProcessKey",              ctypes.c_size_t),
        ("PeakVirtualSize",               ctypes.c_size_t),
        ("VirtualSize",                   ctypes.c_size_t),       # VMS
        ("PageFaultCount",                wintypes.ULONG),
        # 4 bytes implicit padding (ctypes aligns next c_size_t to 8 bytes)
        ("PeakWorkingSetSize",            ctypes.c_size_t),
        ("WorkingSetSize",                ctypes.c_size_t),       # RSS
        ("QuotaPeakPagedPoolUsage",       ctypes.c_size_t),
        ("QuotaPagedPoolUsage",           ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage",    ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage",        ctypes.c_size_t),
        ("PagefileUsage",                 ctypes.c_size_t),       # private bytes / commit
        ("PeakPagefileUsage",             ctypes.c_size_t),
        ("PrivatePageCount",              ctypes.c_size_t),
        ("ReadOperationCount",            ctypes.c_int64),
        ("WriteOperationCount",           ctypes.c_int64),
        ("OtherOperationCount",           ctypes.c_int64),
        ("ReadTransferCount",             ctypes.c_int64),
        ("WriteTransferCount",            ctypes.c_int64),
        ("OtherTransferCount",            ctypes.c_int64),
    ]


_NtQuerySystemInformation = _ntdll.NtQuerySystemInformation
_NtQuerySystemInformation.argtypes = [
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]
_NtQuerySystemInformation.restype = ctypes.c_long     # NTSTATUS (signed)

_SYSTEM_PROCESS_INFORMATION_CLASS = 5
_STATUS_INFO_LENGTH_MISMATCH       = -1073741820       # 0xC0000004 as signed NTSTATUS


# ═══════════════════════ BULK PROCESS COLLECTION ═══════════════════════

# CPU delta state for collect_processes_bulk().
# Populated on each call; only written by the background collector thread.
_prev_cpu_times: dict[int, tuple[int, int]] = {}   # pid → (user_100ns, kernel_100ns)
_prev_collect_time: float = 0.0


def collect_processes_bulk(
    need_cpu: bool,
    need_mem: bool,
    cpu_threads: int,
) -> tuple[dict[str, list], float, int, dict[int, str]]:
    """
    Single NtQuerySystemInformation(SystemProcessInformation) call collecting
    all process data at once.

    Replaces ~300 per-process NtQueryInformationProcess kernel transitions with
    one system-wide call, reducing CPU usage by ~10–20×.

    Returns:
        (aggregated dict, total_cpu float, total_rss int, pid_to_name dict)
    """
    global _prev_cpu_times, _prev_collect_time

    buf_size = 512 * 1024   # 512 KB — fits most systems comfortably
    for _ in range(5):
        buf = ctypes.create_string_buffer(buf_size)
        needed = wintypes.DWORD(0)
        status = _NtQuerySystemInformation(
            _SYSTEM_PROCESS_INFORMATION_CLASS,
            buf,
            buf_size,
            ctypes.byref(needed),
        )
        if status == 0:
            break
        if status == _STATUS_INFO_LENGTH_MISMATCH:
            buf_size = needed.value + 65536
            continue
        raise OSError(f"NtQuerySystemInformation failed: NTSTATUS={status & 0xFFFFFFFF:#010x}")
    else:
        raise OSError("NtQuerySystemInformation: buffer too small after 5 retries")

    now = time.time()
    elapsed_100ns = (now - _prev_collect_time) * 10_000_000 if _prev_collect_time > 0 else 0.0

    aggregated: dict[str, list] = {}
    pid_to_name: dict[int, str] = {}
    total_cpu = 0.0
    total_rss = 0
    new_cpu_times: dict[int, tuple[int, int]] = {}

    buf_addr = ctypes.addressof(buf)
    offset = 0

    while True:
        info = _SYSTEM_PROCESS_INFO.from_address(buf_addr + offset)

        pid = info.UniqueProcessId if info.UniqueProcessId is not None else 0

        # Decode process name from UTF-16LE embedded in the output buffer
        if info.ImageName.Length > 0 and info.ImageName.Buffer:
            name_bytes = ctypes.string_at(info.ImageName.Buffer, info.ImageName.Length)
            name = name_bytes.decode('utf-16-le')
        elif pid == 4:
            name = 'System'
        else:
            name = ''   # PID 0 = Idle process (no image name in NtQuerySystemInformation)

        # CPU delta
        cpu_pct = 0.0
        if need_cpu:
            user_time   = info.UserTime
            kernel_time = info.KernelTime
            new_cpu_times[pid] = (user_time, kernel_time)

            if pid in _prev_cpu_times and elapsed_100ns > 0:
                prev_user, prev_kernel = _prev_cpu_times[pid]
                delta = (user_time - prev_user) + (kernel_time - prev_kernel)
                cpu_pct = max(0.0, delta / elapsed_100ns * 100.0)

        # Memory
        rss = vms = 0
        if need_mem:
            rss = info.WorkingSetSize
            vms = info.PagefileUsage

        # PID 0 = System Idle Process — drives total_cpu, excluded from table
        if pid == 0:
            if need_cpu:
                total_cpu = (cpu_threads * 100) - cpu_pct
        elif name:
            total_rss += rss
            display_name = get_process_display_name(name)
            pid_to_name[pid] = display_name
            if display_name in aggregated:
                entry = aggregated[display_name]
                entry[CPU_IDX]     += cpu_pct
                entry[THREADS_IDX] += info.NumberOfThreads
                entry[RSS_IDX]     += rss
                entry[VMS_IDX]     += vms
                entry[COUNT_IDX]   += 1
            else:
                aggregated[display_name] = [cpu_pct, info.NumberOfThreads, rss, vms, 1, pid]

        if info.NextEntryOffset == 0:
            break
        offset += info.NextEntryOffset

    if need_cpu:
        _prev_cpu_times = new_cpu_times
        _prev_collect_time = now

    return aggregated, total_cpu, total_rss, pid_to_name
