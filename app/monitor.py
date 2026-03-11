"""
Process Monitor

Handles process data collection using psutil.
Supports CPU and Memory monitoring modes.
Uses background thread for non-blocking UI.
"""

import ctypes
from ctypes import wintypes
import time


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
    """Return system commit limit (RAM + all page files) in bytes via GetPerformanceInfo."""
    try:
        pi = _PERFORMANCE_INFORMATION()
        pi.cb = ctypes.sizeof(pi)
        ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(pi), pi.cb)
        return pi.CommitLimit * pi.PageSize
    except Exception:
        return psutil.virtual_memory().total
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from collections import deque
from typing import Optional

import heapq

import psutil
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker

# Optional WMI for CPU temperature on Windows
try:
    import wmi
    WMI_AVAILABLE = True
except ImportError:
    WMI_AVAILABLE = False


@dataclass
class HWiNFOData:
    """HWiNFO sensor data."""
    # CPU mode sensors
    cpu_tctl: Optional[float] = None      # CPU (Tctl/Tdie)
    cpu_power: Optional[float] = None     # CPU Package Power (W)
    cpu_edc: Optional[float] = None       # CPU EDC (Electrical Design Current %)

    # Memory mode sensors
    virt_committed: Optional[float] = None  # Virtual Memory Committed (bytes, converted from HWiNFO unit)
    dram_read: Optional[float] = None       # DRAM Read Bandwidth (MB/s)
    dram_write: Optional[float] = None      # DRAM Write Bandwidth (MB/s)


# Windows API for shared memory access
_kernel32 = ctypes.windll.kernel32

_OpenFileMapping = _kernel32.OpenFileMappingW
_OpenFileMapping.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
_OpenFileMapping.restype = wintypes.HANDLE

_MapViewOfFile = _kernel32.MapViewOfFile
_MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
_MapViewOfFile.restype = ctypes.c_void_p

_UnmapViewOfFile = _kernel32.UnmapViewOfFile
_UnmapViewOfFile.argtypes = [ctypes.c_void_p]
_UnmapViewOfFile.restype = wintypes.BOOL

_CloseHandle = _kernel32.CloseHandle
_CloseHandle.argtypes = [wintypes.HANDLE]
_CloseHandle.restype = wintypes.BOOL

_FILE_MAP_READ = 0x0004

# ---- NtQuerySystemInformation — bulk process data in one kernel call ----

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


class _HWiNFOHeader(ctypes.Structure):
    """HWiNFO shared memory header structure."""
    _pack_ = 1
    _fields_ = [
        ("dwSignature", ctypes.c_uint32),
        ("dwVersion", ctypes.c_uint32),
        ("dwRevision", ctypes.c_uint32),
        ("pollTime", ctypes.c_int64),
        ("dwOffsetOfSensorSection", ctypes.c_uint32),
        ("dwSizeOfSensorElement", ctypes.c_uint32),
        ("dwNumSensorElements", ctypes.c_uint32),
        ("dwOffsetOfReadingSection", ctypes.c_uint32),
        ("dwSizeOfReadingElement", ctypes.c_uint32),
        ("dwNumReadingElements", ctypes.c_uint32),
    ]


class _HWiNFOReading(ctypes.Structure):
    """HWiNFO reading structure (SDK default with 128-byte labels)."""
    _pack_ = 1
    _fields_ = [
        ("dwSensorIndex", ctypes.c_uint32),
        ("dwReadingID", ctypes.c_uint32),
        ("dwReadingType", ctypes.c_uint32),
        ("szLabelOrig", ctypes.c_char * 128),
        ("szLabelUser", ctypes.c_char * 128),
        ("szUnit", ctypes.c_char * 16),
        ("Value", ctypes.c_double),
        ("ValueMin", ctypes.c_double),
        ("ValueMax", ctypes.c_double),
        ("ValueAvg", ctypes.c_double),
    ]


class HWiNFOSharedMemory:
    """Read sensors from HWiNFO shared memory using Windows API."""

    HWINFO_SENSORS_SM = "Global\\HWiNFO_SENS_SM2"

    # Sensor targets to find (key -> dataclass attribute)
    TARGETS = [
        ("cpu (tctl/tdie)", "cpu_tctl"),
        ("cpu edc", "cpu_edc"),
        ("cpu package power", "cpu_power"),
        ("virtual memory committed", "virt_committed"),
        ("dram read bandwidth", "dram_read"),
        ("dram write bandwidth", "dram_write"),
    ]

    def __init__(self):
        self._cache: Optional[HWiNFOData] = None
        self._last_read: float = 0
        self._cache_seconds: float = 0.5
        # Cached sensor indices and units (found on first scan)
        self._sensor_indices: Optional[dict[str, int]] = None
        self._sensor_units: Optional[dict[str, str]] = None
        self._reading_offset: int = 0
        self._reading_size: int = 0

    def _find_sensor_indices(self, base: int, header: _HWiNFOHeader) -> tuple[dict[str, int], dict[str, str]]:
        """Scan once to find indices and units of target sensors."""
        indices: dict[str, int] = {}
        units: dict[str, str] = {}

        for i in range(header.dwNumReadingElements):
            addr = base + header.dwOffsetOfReadingSection + i * header.dwSizeOfReadingElement
            reading = _HWiNFOReading.from_address(addr)

            label_orig = reading.szLabelOrig.decode('utf-8', errors='ignore').rstrip('\x00').lower()
            label_user = reading.szLabelUser.decode('utf-8', errors='ignore').rstrip('\x00').lower()

            # Check pattern targets
            for target_key, target_name in self.TARGETS:
                if target_key in label_orig or target_key in label_user:
                    indices[target_name] = i
                    units[target_name] = reading.szUnit.decode('utf-8', errors='ignore').rstrip('\x00')
                    break

        return indices, units

    def get_sensors(self) -> HWiNFOData:
        """Get sensor values from HWiNFO (fast - only reads cached indices)."""
        now = time.time()
        if now - self._last_read < self._cache_seconds and self._cache is not None:
            return self._cache

        data = HWiNFOData()

        try:
            handle = _OpenFileMapping(_FILE_MAP_READ, False, self.HWINFO_SENSORS_SM)
            if not handle:
                return data

            base = _MapViewOfFile(handle, _FILE_MAP_READ, 0, 0, 0)
            if not base:
                _CloseHandle(handle)
                return data

            header = _HWiNFOHeader.from_address(base)
            self._reading_offset = header.dwOffsetOfReadingSection
            self._reading_size = header.dwSizeOfReadingElement

            # First time: scan all to find indices and units
            if self._sensor_indices is None:
                self._sensor_indices, self._sensor_units = self._find_sensor_indices(base, header)

            # Fast path: only read the sensors we need
            for attr_name, idx in self._sensor_indices.items():
                addr = base + self._reading_offset + idx * self._reading_size
                reading = _HWiNFOReading.from_address(addr)
                value = reading.Value
                # Convert virt_committed to bytes using HWiNFO's reported unit
                if attr_name == 'virt_committed' and self._sensor_units:
                    hw_unit = self._sensor_units.get(attr_name, 'MB')
                    if hw_unit == 'GB':
                        value *= 1024 ** 3
                    elif hw_unit == 'MB':
                        value *= 1024 ** 2
                    elif hw_unit == 'KB':
                        value *= 1024
                setattr(data, attr_name, value)

            _UnmapViewOfFile(base)
            _CloseHandle(handle)

            self._cache = data
            self._last_read = now

        except Exception:
            pass

        return data

    def get_cpu_temp(self) -> Optional[float]:
        """Get primary CPU temperature (Tctl/Tdie preferred)."""
        data = self.get_sensors()
        return data.cpu_tctl


# Global HWiNFO reader instance
_hwinfo_reader: Optional[HWiNFOSharedMemory] = None

from .styles import MEMORY_UNITS, format_pct, format_speed, get_process_display_name
from .color_management import ProcessColorManager


# Indices into the aggregated per-process list [cpu_pct, threads, rss, vms, count, pid]
_CPU_IDX     = 0
_THREADS_IDX = 1
_RSS_IDX     = 2
_VMS_IDX     = 3
_COUNT_IDX   = 4
_PID_IDX     = 5


class MonitorMode(Enum):
    """Monitoring mode selection."""

    CPU = auto()
    MEMORY = auto()
    NETWORK = auto()
    BOTH = auto()  # Opens both CPU and Memory windows


@dataclass
class ProcessInfo:
    """Information about a single process or process group."""

    name: str
    value: float  # CPU % or Memory bytes
    threads: int = 0  # Number of threads (OS threads)
    count: int = 0    # Number of processes in this group (parallel count)
    vms: int = 0      # Virtual Memory Size (commit size)
    timestamp: float = field(default_factory=time.time)
    uptime_seconds: int = 0  # Rolling average only: seconds active within retention window

    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()


@dataclass
class HistoryRecord:
    """Historical high-usage record."""

    name: str
    value: float
    timestamp: float
    threads: int = 0  # Number of threads at peak
    count: int = 0    # Number of processes in group at peak
    vms: int = 0      # Virtual Memory Size (commit size) at peak

    @property
    def time_str(self) -> str:
        """Format timestamp as HH:MM."""
        return datetime.fromtimestamp(self.timestamp).strftime("%H:%M")


@dataclass
class MonitorStats:
    """Current monitoring statistics."""

    total_usage: float = 0.0
    max_usage: float = 0.0
    max_usage_time: Optional[datetime] = None
    process_count: int = 0


def _collect_processes(
    need_cpu: bool,
    need_mem: bool,
    cpu_threads: int,
) -> tuple[dict[str, list], float, int, dict[int, str]]:
    """
    Single psutil pass collecting CPU and/or memory data.

    Args:
        need_cpu: Collect cpu_percent and num_threads
        need_mem: Collect rss, vms, page_faults
        cpu_threads: Total logical CPU count (for idle calculation)

    Returns:
        (aggregated, total_cpu, total_rss)
        aggregated: {display_name: [cpu_pct, threads, rss, vms, pf]}
    """
    attrs = ['name', 'pid']
    if need_cpu:
        attrs += ['cpu_percent', 'num_threads']
    if need_mem:
        attrs += ['memory_info']

    aggregated: dict[str, list] = {}
    pid_to_name: dict[int, str] = {}
    total_cpu = 0.0
    total_rss = 0

    for proc in psutil.process_iter(attrs):
        try:
            info = proc.info
            name = info['name']
            if not name:
                continue

            cpu_pct = 0.0
            threads = 0
            if need_cpu:
                cpu_pct = info.get('cpu_percent') or 0.0
                threads = info.get('num_threads') or 0
                if name == 'System Idle Process':
                    total_cpu = (cpu_threads * 100) - cpu_pct
                    continue

            rss = 0
            vms = 0
            if need_mem:
                mem_info = info.get('memory_info')
                if mem_info:
                    rss = mem_info.rss
                    vms = mem_info.vms
                    total_rss += rss

            pid = info.get('pid') or 0
            display_name = get_process_display_name(name)
            pid_to_name[pid] = display_name
            if display_name in aggregated:
                entry = aggregated[display_name]
                entry[_CPU_IDX]     += cpu_pct
                entry[_THREADS_IDX] += threads
                entry[_RSS_IDX]     += rss
                entry[_VMS_IDX]     += vms
                entry[_COUNT_IDX]   += 1
                # Keep first-seen PID for company lookup
            else:
                aggregated[display_name] = [cpu_pct, threads, rss, vms, 1, pid]

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return aggregated, total_cpu, total_rss, pid_to_name


# ---- CPU delta state for _collect_processes_bulk ----
# Populated on each call; only written by the background collector thread.
_prev_cpu_times: dict[int, tuple[int, int]] = {}   # pid → (user_100ns, kernel_100ns)
_prev_collect_time: float = 0.0


def _collect_processes_bulk(
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
                entry[_CPU_IDX]     += cpu_pct
                entry[_THREADS_IDX] += info.NumberOfThreads
                entry[_RSS_IDX]     += rss
                entry[_VMS_IDX]     += vms
                entry[_COUNT_IDX]   += 1
            else:
                aggregated[display_name] = [cpu_pct, info.NumberOfThreads, rss, vms, 1, pid]

        if info.NextEntryOffset == 0:
            break
        offset += info.NextEntryOffset

    if need_cpu:
        _prev_cpu_times = new_cpu_times
        _prev_collect_time = now

    return aggregated, total_cpu, total_rss, pid_to_name


class ProcessMonitor:
    """
    Monitors system processes for CPU or Memory usage.

    Aggregates processes by name and tracks historical peaks.
    """

    def __init__(
        self,
        mode: MonitorMode = MonitorMode.CPU,
        cpu_threads: Optional[int] = None,
        ram_gb: Optional[int] = None,
    ):
        """
        Initialize the process monitor.

        Args:
            mode: CPU or MEMORY monitoring mode
            cpu_threads: Total CPU threads (auto-detect if None)
            ram_gb: Total RAM in GB (auto-detect if None)
        """
        self.mode = mode

        # Auto-detect system specs
        self.cpu_threads = cpu_threads or psutil.cpu_count()
        self.ram_bytes = (ram_gb or self._detect_ram_gb()) * (1024 ** 3)

        # State
        self.stats = MonitorStats()
        self.history: dict[str, HistoryRecord] = {}
        self.history_max_size = 10
        self.retention_seconds = 120 * 60  # 2 hours default

        # Rolling average buffer: (timestamp, {name: (value, threads, count, vms)}) snapshots
        self._rolling_snapshots: deque = deque()
        # Incremental accumulator: {name: [total_value, total_threads, total_count, total_vms, sample_count]}
        self._rolling_acc: dict[str, list] = {}
        self._refresh_rate_ms: int = 1000  # Used to compute uptime from sample count

        # Peak buffer: (timestamp, total_usage) — rolling window, same retention as snapshots
        self._peak_buffer: deque = deque()
        self._first_cpu_tick: bool = True  # First bulk-collect tick has bogus total_cpu (no prev delta)

        # Initialize CPU percent (first call returns 0)
        if mode == MonitorMode.CPU:
            self._init_cpu_percent()

    def _detect_ram_gb(self) -> int:
        """Detect total RAM in GB."""
        return round(psutil.virtual_memory().total / (1024 ** 3))

    def get_cpu_temperature(self) -> Optional[float]:
        """
        Get CPU temperature in Celsius.

        Supports: HWiNFO, OpenHardwareMonitor, LibreHardwareMonitor.
        Requires one of these running with shared memory/WMI enabled.

        Returns:
            Temperature in Celsius or None if unavailable
        """
        global _hwinfo_reader

        # Try HWiNFO shared memory first (most common on Windows)
        if _hwinfo_reader is None:
            _hwinfo_reader = HWiNFOSharedMemory()
        temp = _hwinfo_reader.get_cpu_temp()
        if temp is not None:
            return temp

        # Try psutil (works on Linux, some Windows)
        if hasattr(psutil, 'sensors_temperatures'):
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for name in ['coretemp', 'cpu_thermal', 'k10temp', 'zenpower']:
                        if name in temps and temps[name]:
                            return temps[name][0].current
            except Exception:
                pass

        # Try WMI on Windows
        if WMI_AVAILABLE:
            # OpenHardwareMonitor WMI
            try:
                w = wmi.WMI(namespace="root\\OpenHardwareMonitor")
                sensors = w.Sensor()
                for sensor in sensors:
                    if sensor.SensorType == 'Temperature' and 'CPU' in sensor.Name:
                        return float(sensor.Value)
            except Exception:
                pass

            # LibreHardwareMonitor WMI
            try:
                w = wmi.WMI(namespace="root\\LibreHardwareMonitor")
                sensors = w.Sensor()
                for sensor in sensors:
                    if sensor.SensorType == 'Temperature' and 'CPU' in sensor.Name:
                        return float(sensor.Value)
            except Exception:
                pass

        return None

    def get_hwinfo_data(self) -> HWiNFOData:
        """
        Get all HWiNFO sensor data.

        Returns:
            HWiNFOData with CPU temps, ambient temp, DRAM bandwidth
        """
        global _hwinfo_reader
        if _hwinfo_reader is None:
            _hwinfo_reader = HWiNFOSharedMemory()
        return _hwinfo_reader.get_sensors()

    def _init_cpu_percent(self):
        """Initialize CPU percent tracking (first call is always 0)."""
        for proc in psutil.process_iter(['cpu_percent']):
            try:
                proc.cpu_percent()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def set_mode(self, mode: MonitorMode):
        """Change monitoring mode."""
        if self.mode != mode:
            self.mode = mode
            self.stats = MonitorStats()
            if mode == MonitorMode.CPU:
                self._init_cpu_percent()

    def set_history_settings(self, max_size: int, retention_minutes: int):
        """Configure history tracking."""
        self.history_max_size = max_size
        self.retention_seconds = retention_minutes * 60

    def set_refresh_rate(self, refresh_rate_ms: int):
        """Set refresh rate used to compute uptime from sample count."""
        self._refresh_rate_ms = refresh_rate_ms

    def get_processes(self, limit: int = 10) -> list[ProcessInfo]:
        """
        Get current process usage data (single-mode convenience method).

        Args:
            limit: Maximum number of processes to return

        Returns:
            List of ProcessInfo sorted by usage (descending)
        """
        need_cpu = self.mode == MonitorMode.CPU
        need_mem = self.mode == MonitorMode.MEMORY
        aggregated, total_cpu, total_rss, _ = _collect_processes(need_cpu, need_mem, self.cpu_threads)
        if need_cpu:
            return self._extract_cpu_top(aggregated, total_cpu, limit)
        return self._extract_mem_top(aggregated, total_rss, limit)

    def _extract_cpu_top(self, aggregated: dict[str, list], total_cpu: float, limit: int) -> list[ProcessInfo]:
        """Extract top CPU processes from aggregated data and update stats."""
        self.stats.total_usage = total_cpu
        self.stats.process_count = len(aggregated)

        if self._first_cpu_tick:
            self._first_cpu_tick = False
        else:
            now_ts = time.time()
            self._peak_buffer.append((now_ts, total_cpu))
            cutoff = now_ts - self.retention_seconds
            while self._peak_buffer and self._peak_buffer[0][0] < cutoff:
                self._peak_buffer.popleft()

        top = heapq.nlargest(limit, aggregated.items(), key=lambda x: x[1][_CPU_IDX])
        return [
            ProcessInfo(name=name, value=entry[_CPU_IDX], threads=entry[_THREADS_IDX], count=entry[_COUNT_IDX])
            for name, entry in top
        ]

    def _extract_mem_top(self, aggregated: dict[str, list], total_rss: int, limit: int) -> list[ProcessInfo]:
        """Extract top memory processes from aggregated data and update stats."""
        vm = psutil.virtual_memory()
        self.stats.total_usage = vm.used
        self.stats.process_count = len(aggregated)

        now_ts = time.time()
        self._peak_buffer.append((now_ts, vm.used))
        cutoff = now_ts - self.retention_seconds
        while self._peak_buffer and self._peak_buffer[0][0] < cutoff:
            self._peak_buffer.popleft()

        top = heapq.nlargest(limit, aggregated.items(), key=lambda x: x[1][_RSS_IDX])
        return [
            ProcessInfo(name=name, value=entry[_RSS_IDX], vms=entry[_VMS_IDX], count=entry[_COUNT_IDX])
            for name, entry in top
        ]

    def update_history(self, processes: list[ProcessInfo]):
        """
        Update historical high-usage records.

        Args:
            processes: Current process list from get_processes()
        """
        now = time.time()

        # Remove expired records
        self.history = {
            name: record for name, record in self.history.items()
            if (now - record.timestamp) < self.retention_seconds
        }

        # Check each process against history
        for proc in processes:
            if proc.value <= 0:
                continue

            if proc.name in self.history:
                # Update if current value is higher
                if proc.value > self.history[proc.name].value:
                    self.history[proc.name] = HistoryRecord(
                        name=proc.name,
                        value=proc.value,
                        timestamp=now,
                        threads=proc.threads,
                        count=proc.count,
                        vms=proc.vms,
                    )
            else:
                # Add new record if we have space or this beats the lowest
                if len(self.history) < self.history_max_size:
                    self.history[proc.name] = HistoryRecord(
                        name=proc.name,
                        value=proc.value,
                        timestamp=now,
                        threads=proc.threads,
                        count=proc.count,
                        vms=proc.vms,
                    )
                elif self.history:
                    min_name = min(self.history, key=lambda k: self.history[k].value)
                    if proc.value > self.history[min_name].value:
                        del self.history[min_name]
                        self.history[proc.name] = HistoryRecord(
                            name=proc.name,
                            value=proc.value,
                            timestamp=now,
                            threads=proc.threads,
                            count=proc.count,
                            vms=proc.vms,
                        )

    def get_history(self) -> list[HistoryRecord]:
        """Get historical high-usage records sorted by value descending."""
        return sorted(self.history.values(), key=lambda r: r.value, reverse=True)[:self.history_max_size]

    def update_rolling_average(self, aggregated: dict) -> None:
        """Add current process snapshot to rolling average buffer and purge old entries.

        Stores a lightweight snapshot of all process values from the aggregated dict.
        CPU mode captures (cpu_pct, threads, count, 0); Memory mode captures (rss, 0, count, vms).
        Old snapshots outside the retention window are purged immediately.

        Maintains an incremental accumulator (_rolling_acc) so get_rolling_average()
        reads O(processes) instead of O(snapshots * processes).
        """
        now = time.time()
        acc = self._rolling_acc

        if self.mode == MonitorMode.CPU:
            snapshot = {
                name: (entry[_CPU_IDX], entry[_THREADS_IDX], entry[_COUNT_IDX], 0)
                for name, entry in aggregated.items()
            }
        else:
            snapshot = {
                name: (entry[_RSS_IDX], 0, entry[_COUNT_IDX], entry[_VMS_IDX])
                for name, entry in aggregated.items()
            }

        # Add new snapshot values to accumulator
        for name, (value, threads, count, vms) in snapshot.items():
            if name not in acc:
                acc[name] = [0.0, 0, 0, 0, 0]
            entry = acc[name]
            entry[0] += value
            entry[1] += threads
            entry[2] += count
            entry[3] += vms
            entry[4] += 1

        self._rolling_snapshots.append((now, snapshot))

        # Purge expired snapshots and subtract their values from accumulator
        cutoff = now - self.retention_seconds
        while self._rolling_snapshots and self._rolling_snapshots[0][0] < cutoff:
            _, expired = self._rolling_snapshots.popleft()
            for name, (value, threads, count, vms) in expired.items():
                entry = acc.get(name)
                if entry is None:
                    continue
                entry[0] -= value
                entry[1] -= threads
                entry[2] -= count
                entry[3] -= vms
                entry[4] -= 1
                if entry[4] <= 0:
                    del acc[name]

    def get_rolling_average(self, limit: int = 0) -> list[ProcessInfo]:
        """Calculate per-process averages across the rolling window, sorted by average value descending.

        Args:
            limit: Maximum number of processes to return (0 = no limit).

        Reads from the incremental accumulator (_rolling_acc) maintained by update_rolling_average().
        Each process that appeared in at least one snapshot is included.
        Threads and count are rounded to the nearest integer.
        Processes with zero average value are excluded.
        """
        total_snapshots = len(self._rolling_snapshots)
        if total_snapshots == 0:
            return []

        if total_snapshots >= 2:
            actual_span = self._rolling_snapshots[-1][0] - self._rolling_snapshots[0][0]
        else:
            actual_span = 0.0

        result = []
        for name, (total_val, total_threads, total_count, total_vms, samples) in self._rolling_acc.items():
            if samples == 0:
                continue
            # Denominator is always total_snapshots — same for all processes.
            # A process active for only part of the window gets a proportionally lower average.
            avg_value = total_val / total_snapshots
            if avg_value <= 0:
                continue
            uptime_seconds = round(samples * actual_span / total_snapshots) if actual_span else 0
            result.append(ProcessInfo(
                name=name,
                value=avg_value,
                threads=round(total_threads / samples),
                count=round(total_count / samples),
                vms=round(total_vms / samples),
                uptime_seconds=uptime_seconds,
            ))

        sorted_result = sorted(result, key=lambda p: p.value, reverse=True)
        return sorted_result[:limit] if limit > 0 else sorted_result

    def format_value(self, value: float, unit: str = "MB") -> str:
        """
        Format a value for display.

        Args:
            value: Raw value (CPU % or Memory bytes)
            unit: Memory unit (KB, MB, GB) - ignored for CPU mode

        Returns:
            Formatted string
        """
        if self.mode == MonitorMode.CPU:
            return format_pct(value)
        else:
            divisor = MEMORY_UNITS.get(unit, MEMORY_UNITS["MB"])
            converted = value / divisor
            # GB with 2 decimals, KB/MB with no decimals
            if unit == "GB":
                return f"{converted:,.2f} {unit}"
            else:
                return f"{converted:,.0f} {unit}"

    def get_total_display(self, unit: str = "MB") -> str:
        """Get formatted total usage string."""
        if self.mode == MonitorMode.CPU:
            total_pct = (self.stats.total_usage / (self.cpu_threads * 100)) * 100
            return f"{format_pct(self.stats.total_usage)} ({format_pct(total_pct)})"
        else:
            divisor = MEMORY_UNITS.get(unit, MEMORY_UNITS["MB"])
            total = self.stats.total_usage / divisor
            pct = (self.stats.total_usage / self.ram_bytes) * 100
            if unit == "GB":
                return f"{total:,.2f} {unit} ({format_pct(pct)})"
            else:
                return f"{total:,.0f} {unit} ({format_pct(pct)})"

    def get_max_display(self, unit: str = "MB") -> str:
        """Get formatted maximum usage string within the rolling retention window."""
        if not self._peak_buffer:
            return "No data yet"

        peak_ts, peak_val = max(self._peak_buffer, key=lambda x: x[1])
        time_str = datetime.fromtimestamp(peak_ts).strftime("%H:%M")

        if self.mode == MonitorMode.CPU:
            return f"Peak: {format_pct(peak_val)} at {time_str}"
        else:
            divisor = MEMORY_UNITS.get(unit, MEMORY_UNITS["MB"])
            value = peak_val / divisor
            if unit == "GB":
                return f"Peak: {value:,.2f} {unit} at {time_str}"
            else:
                return f"Peak: {value:,.0f} {unit} at {time_str}"


@dataclass
class MonitorData:
    """Data emitted by SharedDataCollector."""
    processes: list[ProcessInfo]
    history: list[HistoryRecord]
    total_display: str
    max_display: str
    hwinfo: HWiNFOData
    stats: MonitorStats
    process_totals: ProcessInfo  # Aggregated totals from ALL processes (for Σ row)
    rolling_average: list[ProcessInfo] = field(default_factory=list)  # Per-process rolling averages


# ---------------------------------------------------------------------------
# Network monitoring data structures
# ---------------------------------------------------------------------------

@dataclass
class NetworkProcessInfo:
    """Per-process network traffic for one tick."""
    name: str
    download: float  # bytes/sec received
    upload: float    # bytes/sec sent
    timestamp: float = field(default_factory=time.time)


@dataclass
class NetworkHistoryRecord:
    """Historical peak network record for a process."""
    name: str
    download: float  # peak bytes/sec download
    upload: float    # peak bytes/sec upload
    sort_value: float  # the value used for ranking (depends on sort mode)
    timestamp: float = field(default_factory=time.time)

    @property
    def time_str(self) -> str:
        return datetime.fromtimestamp(self.timestamp).strftime("%H:%M")


@dataclass
class NetworkMonitorData:
    """Data emitted by SharedDataCollector for the network window."""
    processes: list[NetworkProcessInfo]
    history: list[NetworkHistoryRecord]
    rolling_average: list[NetworkProcessInfo]
    current_download: float   # total bytes/sec download (all processes)
    current_upload: float     # total bytes/sec upload (all processes)
    cumulative_download: int  # total bytes downloaded since start
    cumulative_upload: int    # total bytes uploaded since start
    peak_display: str
    sort_mode: str            # "total", "download", or "upload"


class NetworkMonitor:
    """Tracks per-process network traffic, history peaks, and rolling averages.

    Works similarly to ProcessMonitor but for network bytes/sec.
    """

    def __init__(self, sort_mode: str = "total"):
        self.sort_mode = sort_mode
        self.history: dict[str, NetworkHistoryRecord] = {}
        self.history_max_size = 10
        self.retention_seconds = 120 * 60

        # Cumulative totals (bytes since monitoring started)
        self.cumulative_download: int = 0
        self.cumulative_upload: int = 0

        # Peak total speed buffer: (timestamp, speed_bytes_per_sec)
        self._peak_buffer: deque = deque()

        # Rolling average: deque of (timestamp, {name: (dl, ul)})
        self._rolling_snapshots: deque = deque()
        self._rolling_acc: dict[str, list] = {}  # {name: [total_dl, total_ul, samples]}

    def _sort_key(self, dl: float, ul: float) -> float:
        """Compute sort key based on current sort mode."""
        if self.sort_mode == "download":
            return dl
        elif self.sort_mode == "upload":
            return ul
        return dl + ul

    def process_snapshot(
        self,
        pid_bytes: dict[int, tuple[int, int]],
        pid_to_name: dict[int, str],
        elapsed_sec: float,
        limit: int = 10,
    ) -> list[NetworkProcessInfo]:
        """Aggregate ETW per-PID bytes into per-process-name rates.

        Args:
            pid_bytes: {pid: (bytes_recv, bytes_sent)} from NetworkTracer.snapshot_and_reset()
            pid_to_name: {pid: display_name} mapping from bulk process collect
            elapsed_sec: seconds since last snapshot (for rate calculation)
            limit: max processes to return

        Returns:
            Top N processes sorted by sort_mode, as NetworkProcessInfo list.
        """
        if elapsed_sec <= 0:
            elapsed_sec = 1.0

        # Aggregate by process name
        name_bytes: dict[str, list[int]] = {}
        for pid, (recv, sent) in pid_bytes.items():
            name = pid_to_name.get(pid)
            if not name:
                continue
            if name not in name_bytes:
                name_bytes[name] = [0, 0]
            name_bytes[name][0] += recv
            name_bytes[name][1] += sent

        # Update cumulative totals
        total_recv = sum(r for r, _ in pid_bytes.values())
        total_sent = sum(s for _, s in pid_bytes.values())
        self.cumulative_download += total_recv
        self.cumulative_upload += total_sent

        # Compute rates
        now = time.time()
        total_dl_rate = total_recv / elapsed_sec
        total_ul_rate = total_sent / elapsed_sec

        # Update peak buffer
        peak_value = self._sort_key(total_dl_rate, total_ul_rate)
        self._peak_buffer.append((now, peak_value, total_dl_rate, total_ul_rate))
        cutoff = now - self.retention_seconds
        while self._peak_buffer and self._peak_buffer[0][0] < cutoff:
            self._peak_buffer.popleft()

        # Build process list with rates
        process_list: list[tuple[str, float, float]] = []
        for name, (recv, sent) in name_bytes.items():
            dl_rate = recv / elapsed_sec
            ul_rate = sent / elapsed_sec
            process_list.append((name, dl_rate, ul_rate))

        # Sort by sort mode
        process_list.sort(key=lambda x: self._sort_key(x[1], x[2]), reverse=True)
        top = process_list[:limit]

        # Update rolling average accumulator
        snapshot = {name: (dl, ul) for name, dl, ul in process_list}
        self._update_rolling(now, snapshot)

        return [
            NetworkProcessInfo(name=name, download=dl, upload=ul)
            for name, dl, ul in top
        ]

    def _update_rolling(self, now: float, snapshot: dict[str, tuple[float, float]]):
        """Add snapshot to rolling average and purge expired entries."""
        acc = self._rolling_acc

        for name, (dl, ul) in snapshot.items():
            if name not in acc:
                acc[name] = [0.0, 0.0, 0]
            entry = acc[name]
            entry[0] += dl
            entry[1] += ul
            entry[2] += 1

        self._rolling_snapshots.append((now, snapshot))

        cutoff = now - self.retention_seconds
        while self._rolling_snapshots and self._rolling_snapshots[0][0] < cutoff:
            _, expired = self._rolling_snapshots.popleft()
            for name, (dl, ul) in expired.items():
                entry = acc.get(name)
                if entry is None:
                    continue
                entry[0] -= dl
                entry[1] -= ul
                entry[2] -= 1
                if entry[2] <= 0:
                    del acc[name]

    def get_rolling_average(self, limit: int = 0) -> list[NetworkProcessInfo]:
        """Get per-process rolling averages sorted by sort mode."""
        total_snapshots = len(self._rolling_snapshots)
        if total_snapshots == 0:
            return []

        result = []
        for name, (total_dl, total_ul, samples) in self._rolling_acc.items():
            if samples == 0:
                continue
            avg_dl = total_dl / total_snapshots
            avg_ul = total_ul / total_snapshots
            if avg_dl <= 0 and avg_ul <= 0:
                continue
            result.append(NetworkProcessInfo(name=name, download=avg_dl, upload=avg_ul))

        result.sort(key=lambda p: self._sort_key(p.download, p.upload), reverse=True)
        return result[:limit] if limit > 0 else result

    def update_history(self, processes: list[NetworkProcessInfo]):
        """Update peak history records."""
        now = time.time()

        # Remove expired
        self.history = {
            name: rec for name, rec in self.history.items()
            if (now - rec.timestamp) < self.retention_seconds
        }

        for proc in processes:
            sort_val = self._sort_key(proc.download, proc.upload)
            if sort_val <= 0:
                continue

            if proc.name in self.history:
                if sort_val > self.history[proc.name].sort_value:
                    self.history[proc.name] = NetworkHistoryRecord(
                        name=proc.name, download=proc.download, upload=proc.upload,
                        sort_value=sort_val, timestamp=now,
                    )
            else:
                if len(self.history) < self.history_max_size:
                    self.history[proc.name] = NetworkHistoryRecord(
                        name=proc.name, download=proc.download, upload=proc.upload,
                        sort_value=sort_val, timestamp=now,
                    )
                elif self.history:
                    min_name = min(self.history, key=lambda k: self.history[k].sort_value)
                    if sort_val > self.history[min_name].sort_value:
                        del self.history[min_name]
                        self.history[proc.name] = NetworkHistoryRecord(
                            name=proc.name, download=proc.download, upload=proc.upload,
                            sort_value=sort_val, timestamp=now,
                        )

    def get_history(self) -> list[NetworkHistoryRecord]:
        """Get historical records sorted by sort_value descending."""
        return sorted(self.history.values(), key=lambda r: r.sort_value, reverse=True)[:self.history_max_size]

    def get_peak_display(self, unit: str = "MB/s") -> str:
        """Get formatted peak speed string."""
        if not self._peak_buffer:
            return "Peak: --"
        peak_ts, _, peak_dl, peak_ul = max(self._peak_buffer, key=lambda x: x[1])
        time_str = datetime.fromtimestamp(peak_ts).strftime("%H:%M")
        return f"Peak: ↓{format_speed(peak_dl, unit)} ↑{format_speed(peak_ul, unit)} at {time_str}"


class SharedDataCollector(QThread):
    """
    Singleton that collects process data once and distributes to multiple windows.
    """

    cpu_data_ready = Signal(MonitorData)
    memory_data_ready = Signal(MonitorData)
    network_data_ready = Signal(NetworkMonitorData)

    _instance: Optional['SharedDataCollector'] = None
    _lock = QMutex()

    def __new__(cls, parent=None):
        """Singleton pattern."""
        with QMutexLocker(cls._lock):
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, parent=None):
        if self._initialized:
            return
        super().__init__(parent)
        self._initialized = True

        self._cpu_monitor: Optional[ProcessMonitor] = None
        self._memory_monitor: Optional[ProcessMonitor] = None
        self._network_monitor: Optional[NetworkMonitor] = None
        self._network_tracer = None  # NetworkTracer (lazy import)
        self._running = False
        self._interval_ms = 1000
        self._cpu_refresh_ms = 1000
        self._memory_refresh_ms = 1000
        self._network_refresh_ms = 1000
        self._mutex = QMutex()

        # Settings per mode
        self._cpu_settings: Optional[dict] = None
        self._memory_settings: Optional[dict] = None
        self._network_settings: Optional[dict] = None

        # Network timing
        self._last_network_time: float = 0.0

        # Subscribers
        self._cpu_enabled = False
        self._memory_enabled = False
        self._network_enabled = False

    def configure_cpu(
        self,
        cpu_threads: int,
        ram_gb: int,
        current_rows: int,
        history_rows: int,
        retention_minutes: int,
        refresh_rate_ms: int,
    ):
        """Configure CPU monitoring."""
        with QMutexLocker(self._mutex):
            self._cpu_settings = {
                'current_rows': current_rows,
                'history_rows': history_rows,
            }
            if self._cpu_monitor is None:
                self._cpu_monitor = ProcessMonitor(
                    mode=MonitorMode.CPU,
                    cpu_threads=cpu_threads,
                    ram_gb=ram_gb,
                )
            self._cpu_monitor.set_history_settings(history_rows, retention_minutes)
            self._cpu_monitor.set_refresh_rate(refresh_rate_ms)
            self._cpu_refresh_ms = refresh_rate_ms
            self._cpu_enabled = True
            self._interval_ms = self._compute_interval()

    def configure_memory(
        self,
        cpu_threads: int,
        ram_gb: int,
        current_rows: int,
        history_rows: int,
        retention_minutes: int,
        refresh_rate_ms: int,
        memory_unit: str,
    ):
        """Configure Memory monitoring."""
        with QMutexLocker(self._mutex):
            self._memory_settings = {
                'current_rows': current_rows,
                'history_rows': history_rows,
                'memory_unit': memory_unit,
            }
            if self._memory_monitor is None:
                self._memory_monitor = ProcessMonitor(
                    mode=MonitorMode.MEMORY,
                    cpu_threads=cpu_threads,
                    ram_gb=ram_gb,
                )
            self._memory_monitor.set_history_settings(history_rows, retention_minutes)
            self._memory_monitor.set_refresh_rate(refresh_rate_ms)
            self._memory_refresh_ms = refresh_rate_ms
            self._memory_enabled = True
            self._interval_ms = self._compute_interval()

    def configure_network(
        self,
        current_rows: int,
        history_rows: int,
        retention_minutes: int,
        refresh_rate_ms: int,
        network_unit: str,
        sort_mode: str,
        max_download_mbps: int,
        max_upload_mbps: int,
    ):
        """Configure Network monitoring."""
        with QMutexLocker(self._mutex):
            self._network_settings = {
                'current_rows': current_rows,
                'history_rows': history_rows,
                'network_unit': network_unit,
                'sort_mode': sort_mode,
                'max_download_mbps': max_download_mbps,
                'max_upload_mbps': max_upload_mbps,
            }
            if self._network_monitor is None:
                self._network_monitor = NetworkMonitor(sort_mode=sort_mode)
            self._network_monitor.sort_mode = sort_mode
            self._network_monitor.history_max_size = history_rows
            self._network_monitor.retention_seconds = retention_minutes * 60
            self._network_refresh_ms = refresh_rate_ms
            self._network_enabled = True
            self._interval_ms = self._compute_interval()

            # Start ETW tracer if not already running
            if self._network_tracer is None:
                from .network_monitor import NetworkTracer
                self._network_tracer = NetworkTracer()
                self._network_tracer.start()

    def disable_cpu(self):
        """Disable CPU monitoring."""
        with QMutexLocker(self._mutex):
            self._cpu_enabled = False
            if not self._memory_enabled and not self._network_enabled:
                self.stop()

    def disable_memory(self):
        """Disable Memory monitoring."""
        with QMutexLocker(self._mutex):
            self._memory_enabled = False
            if not self._cpu_enabled and not self._network_enabled:
                self.stop()

    def disable_network(self):
        """Disable Network monitoring."""
        with QMutexLocker(self._mutex):
            self._network_enabled = False
            if self._network_tracer is not None:
                self._network_tracer.stop()
                self._network_tracer = None
            if not self._cpu_enabled and not self._memory_enabled:
                self.stop()

    def _compute_interval(self) -> int:
        """Compute interval as min of all enabled modes. Must be called within mutex."""
        rates = []
        if self._cpu_enabled:
            rates.append(self._cpu_refresh_ms)
        if self._memory_enabled:
            rates.append(self._memory_refresh_ms)
        if self._network_enabled:
            rates.append(self._network_refresh_ms)
        return min(rates) if rates else 1000

    def run(self):
        """Main collector loop - single psutil pass, emits to all subscribers."""
        self._running = True

        while self._running:
            # Read settings under lock (fast)
            with QMutexLocker(self._mutex):
                cpu_enabled = self._cpu_enabled
                cpu_monitor = self._cpu_monitor
                cpu_settings = self._cpu_settings.copy() if self._cpu_settings else None
                mem_enabled = self._memory_enabled
                mem_monitor = self._memory_monitor
                mem_settings = self._memory_settings.copy() if self._memory_settings else None
                net_enabled = self._network_enabled
                net_monitor = self._network_monitor
                net_tracer = self._network_tracer
                net_settings = self._network_settings.copy() if self._network_settings else None
                interval = self._interval_ms

            need_cpu = bool(cpu_enabled and cpu_monitor and cpu_settings)
            need_mem = bool(mem_enabled and mem_monitor and mem_settings)
            need_net = bool(net_enabled and net_monitor and net_tracer and net_settings)

            if need_cpu or need_mem or need_net:
                # Single NtQuerySystemInformation call (replaces ~300 per-process psutil calls)
                cpu_threads = cpu_monitor.cpu_threads if cpu_monitor else psutil.cpu_count()
                aggregated, total_cpu, total_rss, pid_to_name = _collect_processes_bulk(need_cpu, need_mem, cpu_threads)

                # Register new process names for company color lookup (fast no-op for cached names)
                color_mgr = ProcessColorManager()
                for proc_name, entry in aggregated.items():
                    color_mgr.lookup_company(proc_name, entry[_PID_IDX])
                color_mgr.refresh_active_counts(aggregated.keys())

                hwinfo = cpu_monitor.get_hwinfo_data() if cpu_monitor else HWiNFOData()

                if need_cpu:
                    history_limit = max(cpu_settings['current_rows'], cpu_settings['history_rows'])
                    all_processes = cpu_monitor._extract_cpu_top(aggregated, total_cpu, history_limit)
                    processes = all_processes[:cpu_settings['current_rows']]
                    cpu_monitor.update_history(all_processes)
                    cpu_monitor.update_rolling_average(aggregated)
                    cpu_totals = ProcessInfo(
                        name="Total",
                        value=cpu_monitor.stats.total_usage,
                        threads=sum(e[_THREADS_IDX] for e in aggregated.values()),
                        count=sum(e[_COUNT_IDX] for e in aggregated.values()),
                    )
                    self.cpu_data_ready.emit(MonitorData(
                        processes=processes,
                        history=cpu_monitor.get_history(),
                        total_display=cpu_monitor.get_total_display("MB"),
                        max_display=cpu_monitor.get_max_display("MB"),
                        hwinfo=hwinfo,
                        stats=cpu_monitor.stats,
                        process_totals=cpu_totals,
                        rolling_average=cpu_monitor.get_rolling_average(cpu_settings['history_rows']),
                    ))

                if need_mem:
                    unit = mem_settings.get('memory_unit', 'MB')
                    history_limit = max(mem_settings['current_rows'], mem_settings['history_rows'])
                    all_processes = mem_monitor._extract_mem_top(aggregated, total_rss, history_limit)
                    processes = all_processes[:mem_settings['current_rows']]
                    mem_monitor.update_history(all_processes)
                    mem_monitor.update_rolling_average(aggregated)
                    mem_totals = ProcessInfo(
                        name="Total",
                        value=total_rss,
                        vms=sum(e[_VMS_IDX] for e in aggregated.values()),
                        count=sum(e[_COUNT_IDX] for e in aggregated.values()),
                    )
                    self.memory_data_ready.emit(MonitorData(
                        processes=processes,
                        history=mem_monitor.get_history(),
                        total_display=mem_monitor.get_total_display(unit),
                        max_display=mem_monitor.get_max_display(unit),
                        hwinfo=hwinfo,
                        stats=mem_monitor.stats,
                        process_totals=mem_totals,
                        rolling_average=mem_monitor.get_rolling_average(mem_settings['history_rows']),
                    ))

                if need_net:
                    now = time.time()
                    elapsed = now - self._last_network_time if self._last_network_time > 0 else 1.0
                    self._last_network_time = now

                    pid_bytes = net_tracer.snapshot_and_reset()
                    net_unit = net_settings.get('network_unit', 'MB/s')
                    net_limit = max(net_settings['current_rows'], net_settings['history_rows'])
                    net_processes = net_monitor.process_snapshot(
                        pid_bytes, pid_to_name, elapsed, net_limit,
                    )
                    net_monitor.update_history(net_processes)

                    # Compute current total rates for header
                    total_recv = sum(r for r, _ in pid_bytes.values())
                    total_sent = sum(s for _, s in pid_bytes.values())
                    current_dl = total_recv / elapsed if elapsed > 0 else 0.0
                    current_ul = total_sent / elapsed if elapsed > 0 else 0.0

                    self.network_data_ready.emit(NetworkMonitorData(
                        processes=net_processes[:net_settings['current_rows']],
                        history=net_monitor.get_history(),
                        rolling_average=net_monitor.get_rolling_average(net_settings['history_rows']),
                        current_download=current_dl,
                        current_upload=current_ul,
                        cumulative_download=net_monitor.cumulative_download,
                        cumulative_upload=net_monitor.cumulative_upload,
                        peak_display=net_monitor.get_peak_display(net_unit),
                        sort_mode=net_monitor.sort_mode,
                    ))

            self.msleep(interval)

    def stop(self):
        """Stop the collector."""
        self._running = False
        # Stop ETW tracer if running
        if self._network_tracer is not None:
            self._network_tracer.stop()
            self._network_tracer = None
        self.wait(2000)

    @property
    def cpu_monitor(self) -> Optional[ProcessMonitor]:
        """Get CPU monitor instance."""
        return self._cpu_monitor

    @property
    def memory_monitor(self) -> Optional[ProcessMonitor]:
        """Get Memory monitor instance."""
        return self._memory_monitor

    @property
    def network_monitor(self) -> Optional[NetworkMonitor]:
        """Get Network monitor instance."""
        return self._network_monitor

    @classmethod
    def reset_instance(cls):
        """Reset singleton (for testing)."""
        with QMutexLocker(cls._lock):
            if cls._instance is not None:
                cls._instance.stop()
                cls._instance = None
