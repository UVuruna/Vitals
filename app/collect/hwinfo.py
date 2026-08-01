"""HWiNFO shared-memory sensor reader.

HWiNFO (a third-party monitoring tool) publishes its sensor readings in a
named shared-memory section. When it happens to be running, Vitals reads six
of those readings and shows them in the window header's sensor row: CPU
temperature / power / EDC for the CPU window, committed virtual memory and
DRAM read/write bandwidth for the Memory window.

HWiNFO NOT running is the normal case, not an error: the mapping simply does
not open and an empty `HWiNFOData` comes back, which the windows render as an
absent sensor row. Only unexpected parsing failures are logged, once per
process.

Sensor INDICES are discovered by one full scan on the first successful read
and cached; every later read is a direct offset lookup, and the whole result
is cached for half a second so several windows ticking at once cost one read.
"""

import ctypes
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Optional


# ═════════════════════════════ SENSOR PAYLOAD ═════════════════════════════

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


# ═══════════════════ SHARED-MEMORY API & WIRE STRUCTURES ═══════════════════

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


# ══════════════════════════════ THE READER ══════════════════════════════

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
        # Guards the one-time stderr report in get_sensors() for unexpected
        # parsing failures (HWiNFO not running is a separate, unlogged case)
        self._error_reported: bool = False

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
        """Get sensor values from HWiNFO (fast - only reads cached indices).

        HWiNFO not running (OpenFileMappingW returns NULL) is a normal condition
        and is not logged. Unexpected failures while parsing the shared memory
        are logged to stderr once per process (self._error_reported) rather than
        every tick, and any opened handles are always released via finally so a
        parsing exception can never leak the file-mapping handle.
        """
        now = time.time()
        if now - self._last_read < self._cache_seconds and self._cache is not None:
            return self._cache

        data = HWiNFOData()

        handle = _OpenFileMapping(_FILE_MAP_READ, False, self.HWINFO_SENSORS_SM)
        if not handle:
            # HWiNFO not running - normal condition, nothing to log
            return data

        base = None
        try:
            base = _MapViewOfFile(handle, _FILE_MAP_READ, 0, 0, 0)
            if not base:
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

            self._cache = data
            self._last_read = now

        except Exception as e:
            if not self._error_reported:
                self._error_reported = True
                print(f"[Vitals] HWiNFO shared memory read failed: {e}", file=sys.stderr)
        finally:
            if base:
                _UnmapViewOfFile(base)
            _CloseHandle(handle)

        return data


# ═══════════════════════════ PROCESS-WIDE ACCESS ═══════════════════════════

# One reader per process: the index scan and the half-second cache are only
# worth paying for once, however many windows are ticking.
_hwinfo_reader: Optional[HWiNFOSharedMemory] = None


def read_sensors() -> HWiNFOData:
    """Current HWiNFO readings, or an empty HWiNFOData when it is not running."""
    global _hwinfo_reader
    if _hwinfo_reader is None:
        _hwinfo_reader = HWiNFOSharedMemory()
    return _hwinfo_reader.get_sensors()
