"""
ETW-based per-process network traffic monitor.

Uses Windows Event Tracing (ETW) with the kernel logger to capture
TCP and UDP send/receive events per process in real time.
Requires administrator privileges.

Data flow:
    ETW kernel trace → event callback → per-PID byte counters
    SharedDataCollector polls snapshot_and_reset() each tick → rates per process
"""

import ctypes
import logging
import os
import struct
import sys
import threading
from collections import defaultdict
from dataclasses import dataclass

from .persistence import get_data_dir


# ---------------------------------------------------------------------------
# Why the trace is not running — a structured reason, never a bare string
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TraceFailure:
    """Why per-process network capture is unavailable, in words a user can act on.

    A bare message string forced the UI to either show developer text or
    string-match on it. The `code` lets the window pick the right remedy
    (relaunching elevated cannot fix "another instance", and retrying cannot
    fix "needs admin"), while `reason` and `action` are the two lines it shows.
    """

    code: str      # one of the NEEDS_* / *_FAILED constants below
    reason: str    # what went wrong, in plain language
    action: str    # what the user can do about it
    detail: str = ""   # raw API status, for the log — never the only record


NEEDS_ADMIN = "NEEDS_ADMIN"
OTHER_INSTANCE = "OTHER_INSTANCE"
START_FAILED = "START_FAILED"
CONSUMER_DIED = "CONSUMER_DIED"


# File logger for ETW diagnostics. Opt-in via VITALS_DEBUG=1 because the log
# is DEBUG-level and truncated on every launch — not a production default.
# When enabled it writes to the user-writable data dir (never Program Files).
def _setup_etw_logger():
    logger = logging.getLogger("etw_net")
    if os.environ.get("VITALS_DEBUG") != "1":
        # Not the full DEBUG trace, but never silence either: a capture that
        # refuses to start has to leave SOME record without the user first
        # knowing an env var exists (root Rule #1).
        logger.setLevel(logging.WARNING)
        logger.addHandler(logging.StreamHandler(sys.stderr))
        return logger
    logger.setLevel(logging.DEBUG)
    log_dir = get_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(str(log_dir / "network_debug.log"), mode='w', encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    logger.addHandler(handler)
    return logger

_log = _setup_etw_logger()


# ---------------------------------------------------------------------------
# GUID helper
# ---------------------------------------------------------------------------

class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


# Custom session GUID for our SystemTraceProvider session.
# When using EVENT_TRACE_SYSTEM_LOGGER_MODE with a custom session name,
# Wnode.Guid must NOT be SystemTraceControlGuid — it must be a unique GUID.
# Windows keys the extra system-logger slots off this GUID, so it was
# regenerated for Vitals: a still-running legacy PMUsage instance (old
# GUID) can no longer occupy our slot during the rename transition.
_VitalsNetTraceGuid = _GUID(
    0xA7C4D9E2, 0x31B8, 0x4E5D,
    (ctypes.c_ubyte * 8)(0x96, 0xF0, 0x5A, 0x2C, 0x8B, 0x1D, 0x7E, 0x43),
)

# Provider GUIDs for kernel TCP/IP and UDP/IP events
_TCPIP_DATA1 = 0x9A280AC0
_TCPIP_DATA2 = 0xC8E0
_UDPIP_DATA1 = 0xBF3A50C5
_UDPIP_DATA2 = 0xA9C9


# ---------------------------------------------------------------------------
# ETW constants
# ---------------------------------------------------------------------------

_EVENT_TRACE_REAL_TIME_MODE = 0x00000100
_EVENT_TRACE_SYSTEM_LOGGER_MODE = 0x02000000
_EVENT_TRACE_FLAG_NETWORK_TCPIP = 0x00010000
_WNODE_FLAG_TRACED_GUID = 0x00020000
_PROCESS_TRACE_MODE_REAL_TIME = 0x00000100
_PROCESS_TRACE_MODE_EVENT_RECORD = 0x10000000
_EVENT_TRACE_CONTROL_STOP = 1
_INVALID_PROCESSTRACE_HANDLE = 0xFFFFFFFFFFFFFFFF

# Network event opcodes (same for TCP and UDP, IPv4 and IPv6)
_OPCODE_SEND_V4 = 10
_OPCODE_RECV_V4 = 11
_OPCODE_SEND_V6 = 26
_OPCODE_RECV_V6 = 27
_SEND_OPCODES = {_OPCODE_SEND_V4, _OPCODE_SEND_V6}
_RECV_OPCODES = {_OPCODE_RECV_V4, _OPCODE_RECV_V6}


# ---------------------------------------------------------------------------
# ETW structures (64-bit Windows 10/11)
# ---------------------------------------------------------------------------

class _WNODE_HEADER(ctypes.Structure):
    _fields_ = [
        ("BufferSize", ctypes.c_uint32),
        ("ProviderId", ctypes.c_uint32),
        ("HistoricalContext", ctypes.c_uint64),
        ("TimeStamp", ctypes.c_int64),
        ("Guid", _GUID),
        ("ClientContext", ctypes.c_uint32),
        ("Flags", ctypes.c_uint32),
    ]


class _EVENT_TRACE_PROPERTIES(ctypes.Structure):
    _fields_ = [
        ("Wnode", _WNODE_HEADER),
        ("BufferSize", ctypes.c_uint32),
        ("MinimumBuffers", ctypes.c_uint32),
        ("MaximumBuffers", ctypes.c_uint32),
        ("MaximumFileSize", ctypes.c_uint32),
        ("LogFileMode", ctypes.c_uint32),
        ("FlushTimer", ctypes.c_uint32),
        ("EnableFlags", ctypes.c_uint32),
        ("AgeLimit", ctypes.c_int32),
        ("NumberOfBuffers", ctypes.c_uint32),
        ("FreeBuffers", ctypes.c_uint32),
        ("EventsLost", ctypes.c_uint32),
        ("BuffersWritten", ctypes.c_uint32),
        ("LogBuffersLost", ctypes.c_uint32),
        ("RealTimeBuffersLost", ctypes.c_uint32),
        ("LoggerThreadId", ctypes.c_void_p),
        ("LogFileNameOffset", ctypes.c_uint32),
        ("LoggerNameOffset", ctypes.c_uint32),
    ]


class _EVENT_DESCRIPTOR(ctypes.Structure):
    _fields_ = [
        ("Id", ctypes.c_uint16),
        ("Version", ctypes.c_uint8),
        ("Channel", ctypes.c_uint8),
        ("Level", ctypes.c_uint8),
        ("Opcode", ctypes.c_uint8),
        ("Task", ctypes.c_uint16),
        ("Keyword", ctypes.c_uint64),
    ]


class _EVENT_HEADER(ctypes.Structure):
    _fields_ = [
        ("Size", ctypes.c_uint16),
        ("HeaderType", ctypes.c_uint16),
        ("Flags", ctypes.c_uint16),
        ("EventProperty", ctypes.c_uint16),
        ("ThreadId", ctypes.c_uint32),
        ("ProcessId", ctypes.c_uint32),
        ("TimeStamp", ctypes.c_int64),
        ("ProviderId", _GUID),
        ("EventDescriptor", _EVENT_DESCRIPTOR),
        ("KernelTime", ctypes.c_uint32),
        ("UserTime", ctypes.c_uint32),
        ("ActivityId", _GUID),
    ]


class _ETW_BUFFER_CONTEXT(ctypes.Structure):
    _fields_ = [
        ("ProcessorIndex", ctypes.c_uint16),
        ("LoggerId", ctypes.c_uint16),
    ]


class _EVENT_RECORD(ctypes.Structure):
    _fields_ = [
        ("EventHeader", _EVENT_HEADER),
        ("BufferContext", _ETW_BUFFER_CONTEXT),
        ("ExtendedDataCount", ctypes.c_uint16),
        ("UserDataLength", ctypes.c_uint16),
        ("ExtendedData", ctypes.c_void_p),
        ("UserData", ctypes.c_void_p),
        ("UserContext", ctypes.c_void_p),
    ]


# EVENT_TRACE_LOGFILEW — contains large embedded structs (EVENT_TRACE, TRACE_LOGFILE_HEADER).
# We only need a few fields; the rest are opaque byte arrays sized for 64-bit Windows.
_EVENT_TRACE_SIZE = 88
_TRACE_LOGFILE_HEADER_SIZE = 280


class _EVENT_TRACE_LOGFILEW(ctypes.Structure):
    _fields_ = [
        ("LogFileName", ctypes.c_wchar_p),
        ("LoggerName", ctypes.c_wchar_p),
        ("CurrentTime", ctypes.c_int64),
        ("BuffersRead", ctypes.c_uint32),
        ("ProcessTraceMode", ctypes.c_uint32),
        ("CurrentEvent", ctypes.c_byte * _EVENT_TRACE_SIZE),
        ("LogfileHeader", ctypes.c_byte * _TRACE_LOGFILE_HEADER_SIZE),
        ("BufferCallback", ctypes.c_void_p),
        ("BufferSize", ctypes.c_uint32),
        ("Filled", ctypes.c_uint32),
        ("EventsLost", ctypes.c_uint32),
        ("EventRecordCallback", ctypes.c_void_p),
        ("IsKernelTrace", ctypes.c_uint32),
        ("Context", ctypes.c_void_p),
    ]


# Callback type: void WINAPI callback(PEVENT_RECORD)
_EVENT_RECORD_CALLBACK = ctypes.WINFUNCTYPE(None, ctypes.POINTER(_EVENT_RECORD))


# ---------------------------------------------------------------------------
# API function declarations (advapi32.dll)
# ---------------------------------------------------------------------------

_advapi32 = ctypes.windll.advapi32

# kernel32 with use_last_error so GetLastError is read reliably (named mutex)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
_kernel32.CreateMutexW.restype = ctypes.c_void_p   # HANDLE is 64-bit
_kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
_ERROR_ALREADY_EXISTS = 183

_StartTraceW = _advapi32.StartTraceW
_StartTraceW.argtypes = [
    ctypes.POINTER(ctypes.c_uint64),   # TraceHandle out
    ctypes.c_wchar_p,                  # InstanceName
    ctypes.c_void_p,                   # Properties (buffer pointer)
]
_StartTraceW.restype = ctypes.c_uint32

_ControlTraceW = _advapi32.ControlTraceW
_ControlTraceW.argtypes = [
    ctypes.c_uint64,     # TraceHandle
    ctypes.c_wchar_p,    # InstanceName
    ctypes.c_void_p,     # Properties
    ctypes.c_uint32,     # ControlCode
]
_ControlTraceW.restype = ctypes.c_uint32

_OpenTraceW = _advapi32.OpenTraceW
_OpenTraceW.argtypes = [ctypes.POINTER(_EVENT_TRACE_LOGFILEW)]
_OpenTraceW.restype = ctypes.c_uint64

_ProcessTrace = _advapi32.ProcessTrace
_ProcessTrace.argtypes = [
    ctypes.POINTER(ctypes.c_uint64),  # HandleArray
    ctypes.c_uint32,                  # HandleCount
    ctypes.c_void_p,                  # StartTime
    ctypes.c_void_p,                  # EndTime
]
_ProcessTrace.restype = ctypes.c_uint32

_CloseTrace = _advapi32.CloseTrace
_CloseTrace.argtypes = [ctypes.c_uint64]
_CloseTrace.restype = ctypes.c_uint32


# ---------------------------------------------------------------------------
# Link speed detection
# ---------------------------------------------------------------------------

def get_link_speed_mbps() -> int:
    """Get the link speed of the primary (active) network interface in Mbps.

    Falls back to 1000 Mbps (1 Gbps) if detection fails.
    """
    try:
        import psutil
        stats = psutil.net_if_stats()
        best_speed = 0
        for _name, info in stats.items():
            if info.isup and info.speed > best_speed:
                best_speed = info.speed
        return best_speed if best_speed > 0 else 1000
    except Exception:
        return 1000


# ---------------------------------------------------------------------------
# NetworkTracer — ETW kernel trace for per-process network bytes
# ---------------------------------------------------------------------------

class NetworkTracer:
    """Captures per-process network bytes via ETW kernel trace.

    Runs a real-time ETW session with EVENT_TRACE_FLAG_NETWORK_TCPIP enabled.
    A background thread processes events; each TCP/UDP send/receive event
    increments per-PID byte counters.

    The SharedDataCollector calls snapshot_and_reset() on each tick to read
    accumulated bytes and compute rates.
    """

    _SESSION_NAME = "Vitals_NetTrace"
    # Named mutex marking a live instance that owns the ETW session — without
    # it, a second Vitals instance would silently kill the first one's trace
    # (the session name is fixed system-wide).
    _OWNER_MUTEX_NAME = "Global\\Vitals_NetTrace_Owner"

    def __init__(self):
        self._session_handle = ctypes.c_uint64(0)
        self._trace_handle = ctypes.c_uint64(0)
        self._owner_mutex = None
        self._thread: threading.Thread | None = None
        self._running = False
        # True once StartTraceW succeeded. Tracked separately from _running
        # because ETW kernel sessions outlive the process: the session must be
        # stopped even when the consumer thread has already died.
        self._session_started = False
        self._lock = threading.Lock()
        self._error: TraceFailure | None = None
        # Set by stop() so a consumer thread that ends on request is never
        # mistaken for one that died — liveness alone cannot tell them apart.
        self._stopping = False
        # Guards the one-time _log.exception() call in _event_callback so a
        # parsing bug is discoverable without flooding the log on every event
        self._callback_error_reported = False

        # Per-PID counters: {pid: [bytes_received, bytes_sent]}
        self._counters: dict[int, list[int]] = defaultdict(lambda: [0, 0])

        # Must prevent callback from being garbage collected
        self._callback_ref: _EVENT_RECORD_CALLBACK | None = None

        # Properties buffer (kept alive for stop call)
        self._props_buf: ctypes.Array | None = None

    @property
    def error(self) -> 'TraceFailure | None':
        """Why capture is unavailable, or None if running normally."""
        return self._error

    def is_dead(self) -> bool:
        """True when the consumer thread ended on its own after a good start.

        `start()` returns as soon as the consumer thread is spawned, so every
        real failure inside it — OpenTraceW, ProcessTrace, or the session being
        stopped from outside — happens AFTER success was reported. Without this
        check the tracer then returns empty snapshots forever and the window
        shows a plausible, permanent zero instead of a problem.

        Judged by liveness AND intent: a clean stop() also ends the thread.
        """
        return self._session_started and not self._running and not self._stopping

    @staticmethod
    def _is_admin() -> bool:
        """Check if running with administrator privileges."""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    def start(self) -> bool:
        """Start ETW trace session. Returns True on success."""
        _log.info("start() called, _running=%s", self._running)
        if self._running:
            return True

        self._error = None
        self._stopping = False

        is_admin = self._is_admin()
        _log.info("is_admin=%s", is_admin)
        if not is_admin:
            # The admin check MUST stay first. The owner mutex lives in the
            # Global\ namespace, so when an elevated Vitals already holds it a
            # non-elevated CreateMutexW fails with ACCESS_DENIED rather than
            # ALREADY_EXISTS — testing the mutex first would miss that case
            # entirely. Both causes are named here because from down here they
            # are genuinely indistinguishable.
            self._error = TraceFailure(
                NEEDS_ADMIN,
                "Per-process network capture needs Administrator rights.",
                "Restart Vitals as administrator. If another Vitals is already "
                "running, exit it from its tray icon first — only one instance "
                "can trace the network.",
            )
            _log.error("%s: %s", self._error.code, self._error.reason)
            return False

        # Acquire the single-owner mutex: if another live Vitals holds it,
        # fail visibly instead of stealing that instance's trace session
        handle = _kernel32.CreateMutexW(None, False, self._OWNER_MUTEX_NAME)
        last_error = ctypes.get_last_error()
        if not handle or last_error == _ERROR_ALREADY_EXISTS:
            # A NULL handle is NOT ownership. Storing it regardless (as this
            # did) made any non-183 failure look like a successful acquire,
            # and the code then went on to stop the other instance's session.
            if handle:
                self._owner_mutex = handle
                self._release_owner_mutex()
            self._error = TraceFailure(
                OTHER_INSTANCE,
                "Another Vitals instance is already tracing the network.",
                "Exit the other Vitals from its tray icon, then press Retry.",
                f"CreateMutexW error {last_error}",
            )
            _log.error("%s: %s (%s)", self._error.code, self._error.reason, self._error.detail)
            return False
        self._owner_mutex = handle

        # With the mutex held, any pre-existing session with our name can
        # only be a stale leftover from a crash — safe to stop
        self._stop_existing_session()
        _log.info("stopped existing session")

        # Build properties buffer using struct.pack_into for reliable byte-level writes.
        # ctypes from_buffer + nested struct assignment can silently write to copies.
        name_bytes = (len(self._SESSION_NAME) + 1) * 2
        props_struct_size = 120  # sizeof(EVENT_TRACE_PROPERTIES) on x64
        props_size = props_struct_size + name_bytes
        self._props_buf = ctypes.create_string_buffer(props_size)

        # Custom session GUID as bytes (NOT SystemTraceControlGuid — that causes 0x57)
        g = _VitalsNetTraceGuid
        guid_bytes = struct.pack('<IHH8s', g.Data1, g.Data2, g.Data3, bytes(g.Data4))

        # WNODE_HEADER (offsets 0-47)
        struct.pack_into('<I', self._props_buf, 0, props_size)           # Wnode.BufferSize
        # ProviderId (4), HistoricalContext (8), TimeStamp (8) = 0 (already zeroed)
        self._props_buf[24:40] = guid_bytes                              # Wnode.Guid
        struct.pack_into('<I', self._props_buf, 40, 1)                   # Wnode.ClientContext = QPC
        struct.pack_into('<I', self._props_buf, 44, _WNODE_FLAG_TRACED_GUID)  # Wnode.Flags

        # EVENT_TRACE_PROPERTIES fields (offsets 48-119)
        struct.pack_into('<I', self._props_buf, 48, 64)                  # BufferSize (64 KB)
        struct.pack_into('<I', self._props_buf, 52, 4)                   # MinimumBuffers
        struct.pack_into('<I', self._props_buf, 56, 64)                  # MaximumBuffers
        # MaximumFileSize = 0 (offset 60, already zeroed)
        log_mode = _EVENT_TRACE_REAL_TIME_MODE | _EVENT_TRACE_SYSTEM_LOGGER_MODE
        struct.pack_into('<I', self._props_buf, 64, log_mode)            # LogFileMode
        # FlushTimer = 0 (offset 68)
        struct.pack_into('<I', self._props_buf, 72, _EVENT_TRACE_FLAG_NETWORK_TCPIP)  # EnableFlags
        # AgeLimit through RealTimeBuffersLost = 0 (offsets 76-103)
        # LoggerThreadId = 0 (offset 104, 8 bytes)
        # LogFileNameOffset = 0 (offset 112)
        struct.pack_into('<I', self._props_buf, 116, props_struct_size)  # LoggerNameOffset

        # Start trace session
        self._session_handle = ctypes.c_uint64(0)
        _log.info("calling StartTraceW session=%s", self._SESSION_NAME)
        status = _StartTraceW(
            ctypes.byref(self._session_handle),
            self._SESSION_NAME,
            self._props_buf,
        )
        _log.info("StartTraceW returned 0x%08X, handle=%s", status, self._session_handle.value)
        if status != 0:
            self._error = TraceFailure(
                START_FAILED,
                "Windows refused to start the network trace session.",
                "Press Retry. If it keeps failing, a reboot clears a stuck "
                "kernel trace session.",
                f"StartTraceW 0x{status:08X}",
            )
            _log.error("%s: %s (%s)", self._error.code, self._error.reason, self._error.detail)
            self._release_owner_mutex()
            return False
        self._session_started = True

        # Create callback (prevent GC)
        self._callback_ref = _EVENT_RECORD_CALLBACK(self._event_callback)

        # Start consumer thread
        self._running = True
        self._thread = threading.Thread(target=self._consume, daemon=True, name="ETW-NetTrace")
        self._thread.start()
        _log.info("consumer thread started")
        return True

    def stop(self):
        """Stop the ETW kernel session and wait for the consumer thread.

        Runs the session teardown even when the consumer thread already died
        (e.g. ProcessTrace failed) — the kernel session outlives the process
        and would otherwise keep tracing system-wide until reboot.

        Idempotent, and safe to call from the collector thread as well as from
        app shutdown: each handle is cleared before it is closed.
        """
        self._stopping = True
        self._running = False

        # Stop the trace session — this also causes ProcessTrace() to return
        if self._session_started:
            stop_props_size = ctypes.sizeof(_EVENT_TRACE_PROPERTIES) + (len(self._SESSION_NAME) + 1) * 2
            stop_buf = ctypes.create_string_buffer(stop_props_size)
            stop_props = _EVENT_TRACE_PROPERTIES.from_buffer(stop_buf)
            stop_props.Wnode.BufferSize = stop_props_size
            stop_props.LoggerNameOffset = ctypes.sizeof(_EVENT_TRACE_PROPERTIES)
            _ControlTraceW(
                self._session_handle.value,
                self._SESSION_NAME,
                stop_buf,
                _EVENT_TRACE_CONTROL_STOP,
            )
            self._session_started = False

        # Close the consumer trace handle (cleared first — a second stop()
        # must not hand the same handle to CloseTrace twice)
        handle = self._trace_handle.value
        if handle not in (0, _INVALID_PROCESSTRACE_HANDLE):
            self._trace_handle = ctypes.c_uint64(0)
            _CloseTrace(handle)

        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

        self._callback_ref = None
        self._release_owner_mutex()

    def _release_owner_mutex(self):
        """Release the session-owner mutex so another instance may trace."""
        handle = self._owner_mutex
        if handle:
            self._owner_mutex = None
            _kernel32.CloseHandle(handle)

    def snapshot_and_reset(self) -> dict[int, tuple[int, int]]:
        """Get accumulated bytes per PID since last snapshot and reset counters.

        Returns:
            {pid: (bytes_received, bytes_sent)}
        """
        with self._lock:
            result = {}
            for pid, counts in self._counters.items():
                recv, sent = counts
                if recv > 0 or sent > 0:
                    result[pid] = (recv, sent)
            self._counters.clear()
            return result

    def _stop_existing_session(self):
        """Stop any leftover session from a previous crash.

        Intentional best-effort: failure here only means there was no stale
        session to stop or it is already gone — never a reason to abort startup.
        """
        try:
            buf_size = ctypes.sizeof(_EVENT_TRACE_PROPERTIES) + (len(self._SESSION_NAME) + 1) * 2
            buf = ctypes.create_string_buffer(buf_size)
            props = _EVENT_TRACE_PROPERTIES.from_buffer(buf)
            props.Wnode.BufferSize = buf_size
            props.LoggerNameOffset = ctypes.sizeof(_EVENT_TRACE_PROPERTIES)
            _ControlTraceW(0, self._SESSION_NAME, buf, _EVENT_TRACE_CONTROL_STOP)
        except Exception:
            pass

    def _consume(self):
        """Consumer thread: open trace and call ProcessTrace (blocks until session stops)."""
        _log.info("_consume() started")
        try:
            logfile = _EVENT_TRACE_LOGFILEW()
            logfile.LoggerName = self._SESSION_NAME
            logfile.ProcessTraceMode = _PROCESS_TRACE_MODE_REAL_TIME | _PROCESS_TRACE_MODE_EVENT_RECORD
            logfile.EventRecordCallback = ctypes.cast(self._callback_ref, ctypes.c_void_p).value

            self._trace_handle = ctypes.c_uint64(_OpenTraceW(ctypes.byref(logfile)))
            _log.info("OpenTraceW handle=%s (invalid=%s)", self._trace_handle.value, self._trace_handle.value == _INVALID_PROCESSTRACE_HANDLE)
            if self._trace_handle.value == _INVALID_PROCESSTRACE_HANDLE:
                self._error = self._consumer_failure("OpenTraceW returned an invalid handle")
                _log.error("%s: %s", CONSUMER_DIED, self._error.detail)
                self._running = False
                return

            handle_arr = (ctypes.c_uint64 * 1)(self._trace_handle.value)
            _log.info("calling ProcessTrace (blocking)...")
            status = _ProcessTrace(handle_arr, 1, None, None)
            _log.info("ProcessTrace returned 0x%08X", status)
            if status != 0:
                self._error = self._consumer_failure(f"ProcessTrace 0x{status:08X}")
                _log.error("%s: %s", CONSUMER_DIED, self._error.detail)
            elif not self._stopping:
                # ProcessTrace returning cleanly while we still want to trace
                # means the kernel session was stopped from outside us.
                self._error = self._consumer_failure("the trace session was stopped externally")
                _log.error("%s: %s", CONSUMER_DIED, self._error.detail)

        except Exception as e:
            self._error = self._consumer_failure(f"consumer thread crashed: {e}")
            _log.exception("ETW consumer exception")
        finally:
            self._running = False
            _log.info("_consume() ended")

    @staticmethod
    def _consumer_failure(detail: str) -> TraceFailure:
        """Build the failure for a consumer thread that ended after a good start."""
        return TraceFailure(
            CONSUMER_DIED,
            "Network capture stopped unexpectedly.",
            "Press Retry to start a new trace session.",
            detail,
        )

    def _event_callback(self, event_ptr):
        """ETW event callback — called for each kernel network event.

        Extracts PID and transfer size from TCP/UDP send/receive events.
        The first 8 bytes of UserData are always [PID: uint32, size: uint32]
        for send/receive opcodes.

        Must never raise — an unhandled exception here would propagate into
        native ETW code. The first exception is logged via _log.exception()
        (guarded by self._callback_error_reported) so a parsing bug is
        discoverable; subsequent ones are suppressed to keep this hot path
        fast and avoid flooding the log.
        """
        try:
            event = event_ptr.contents
            opcode = event.EventHeader.EventDescriptor.Opcode

            is_send = opcode in _SEND_OPCODES
            is_recv = opcode in _RECV_OPCODES
            if not (is_send or is_recv):
                return

            # Check provider GUID (fast: compare first two fields only)
            guid = event.EventHeader.ProviderId
            is_network = (
                (guid.Data1 == _TCPIP_DATA1 and guid.Data2 == _TCPIP_DATA2)
                or (guid.Data1 == _UDPIP_DATA1 and guid.Data2 == _UDPIP_DATA2)
            )
            if not is_network:
                return

            # Extract PID and size from UserData
            if event.UserDataLength < 8 or not event.UserData:
                return

            data = ctypes.cast(event.UserData, ctypes.POINTER(ctypes.c_uint32))
            pid = data[0]
            size = data[1]

            if pid == 0 or size == 0:
                return

            with self._lock:
                counters = self._counters[pid]
                if is_recv:
                    counters[0] += size
                else:
                    counters[1] += size

        except Exception:
            if not self._callback_error_reported:
                self._callback_error_reported = True
                _log.exception("_event_callback: unexpected error (suppressing further occurrences)")
