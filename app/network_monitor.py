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
import ctypes.wintypes as wt
import threading
from collections import defaultdict


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


# SystemTraceControlGuid — required for kernel trace sessions
_SystemTraceControlGuid = _GUID(
    0x9E814AAD, 0x3204, 0x11D2,
    (ctypes.c_ubyte * 8)(0x9A, 0x82, 0x00, 0x60, 0x08, 0xA8, 0x69, 0x39),
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

    _SESSION_NAME = "PMUsage_NetTrace"

    def __init__(self):
        self._session_handle = ctypes.c_uint64(0)
        self._trace_handle = ctypes.c_uint64(0)
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()
        self._error: str | None = None

        # Per-PID counters: {pid: [bytes_received, bytes_sent]}
        self._counters: dict[int, list[int]] = defaultdict(lambda: [0, 0])

        # Must prevent callback from being garbage collected
        self._callback_ref: _EVENT_RECORD_CALLBACK | None = None

        # Properties buffer (kept alive for stop call)
        self._props_buf: ctypes.Array | None = None

    @property
    def error(self) -> str | None:
        """Last error message, or None if running normally."""
        return self._error

    def start(self) -> bool:
        """Start ETW trace session. Returns True on success."""
        if self._running:
            return True

        self._error = None

        # Stop any leftover session from a previous crash
        self._stop_existing_session()

        # Allocate properties buffer (struct + space for session name in UTF-16)
        name_bytes = (len(self._SESSION_NAME) + 1) * 2
        props_size = ctypes.sizeof(_EVENT_TRACE_PROPERTIES) + name_bytes
        self._props_buf = ctypes.create_string_buffer(props_size)
        props = _EVENT_TRACE_PROPERTIES.from_buffer(self._props_buf)

        # Fill properties
        props.Wnode.BufferSize = props_size
        props.Wnode.Flags = _WNODE_FLAG_TRACED_GUID
        props.Wnode.ClientContext = 1  # QPC timestamps
        ctypes.memmove(ctypes.byref(props.Wnode.Guid), ctypes.byref(_SystemTraceControlGuid), ctypes.sizeof(_GUID))
        props.BufferSize = 64          # 64 KB per ETW buffer
        props.MinimumBuffers = 4
        props.MaximumBuffers = 64
        props.LogFileMode = _EVENT_TRACE_REAL_TIME_MODE | _EVENT_TRACE_SYSTEM_LOGGER_MODE
        props.EnableFlags = _EVENT_TRACE_FLAG_NETWORK_TCPIP
        props.LoggerNameOffset = ctypes.sizeof(_EVENT_TRACE_PROPERTIES)

        # Start trace session
        self._session_handle = ctypes.c_uint64(0)
        status = _StartTraceW(
            ctypes.byref(self._session_handle),
            self._SESSION_NAME,
            self._props_buf,
        )
        if status != 0:
            self._error = f"StartTraceW failed: 0x{status:08X}"
            return False

        # Create callback (prevent GC)
        self._callback_ref = _EVENT_RECORD_CALLBACK(self._event_callback)

        # Start consumer thread
        self._running = True
        self._thread = threading.Thread(target=self._consume, daemon=True, name="ETW-NetTrace")
        self._thread.start()
        return True

    def stop(self):
        """Stop ETW trace session and wait for consumer thread."""
        if not self._running:
            return

        self._running = False

        # Stop the trace session — this causes ProcessTrace() to return
        if self._props_buf is not None:
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

        # Close the consumer trace handle
        if self._trace_handle.value != 0 and self._trace_handle.value != _INVALID_PROCESSTRACE_HANDLE:
            _CloseTrace(self._trace_handle.value)

        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

        self._callback_ref = None

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
        """Stop any leftover session from a previous crash."""
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
        try:
            logfile = _EVENT_TRACE_LOGFILEW()
            logfile.LoggerName = self._SESSION_NAME
            logfile.ProcessTraceMode = _PROCESS_TRACE_MODE_REAL_TIME | _PROCESS_TRACE_MODE_EVENT_RECORD
            logfile.EventRecordCallback = ctypes.cast(self._callback_ref, ctypes.c_void_p).value

            self._trace_handle = ctypes.c_uint64(_OpenTraceW(ctypes.byref(logfile)))
            if self._trace_handle.value == _INVALID_PROCESSTRACE_HANDLE:
                self._error = "OpenTraceW failed: invalid handle"
                self._running = False
                return

            handle_arr = (ctypes.c_uint64 * 1)(self._trace_handle.value)
            _ProcessTrace(handle_arr, 1, None, None)

        except Exception as e:
            self._error = f"ETW consumer error: {e}"
        finally:
            self._running = False

    def _event_callback(self, event_ptr):
        """ETW event callback — called for each kernel network event.

        Extracts PID and transfer size from TCP/UDP send/receive events.
        The first 8 bytes of UserData are always [PID: uint32, size: uint32]
        for send/receive opcodes.
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
            pass  # Never crash the ETW consumer thread
