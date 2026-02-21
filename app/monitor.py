"""
Process Monitor

Handles process data collection using psutil.
Supports CPU and Memory monitoring modes.
Uses background thread for non-blocking UI.
"""

import ctypes
from ctypes import wintypes
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
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
    virt_committed: Optional[float] = None  # Virtual Memory Committed (MB)
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
        # Cached sensor indices (found on first scan)
        self._sensor_indices: Optional[dict[str, int]] = None
        self._reading_offset: int = 0
        self._reading_size: int = 0

    def _find_sensor_indices(self, base: int, header: _HWiNFOHeader) -> dict[str, int]:
        """Scan once to find indices of target sensors."""
        indices: dict[str, int] = {}

        for i in range(header.dwNumReadingElements):
            addr = base + header.dwOffsetOfReadingSection + i * header.dwSizeOfReadingElement
            reading = _HWiNFOReading.from_address(addr)

            label_orig = reading.szLabelOrig.decode('utf-8', errors='ignore').rstrip('\x00').lower()
            label_user = reading.szLabelUser.decode('utf-8', errors='ignore').rstrip('\x00').lower()

            # Check pattern targets
            for target_key, target_name in self.TARGETS:
                if target_key in label_orig or target_key in label_user:
                    indices[target_name] = i
                    break

        return indices

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

            # First time: scan all to find indices
            if self._sensor_indices is None:
                self._sensor_indices = self._find_sensor_indices(base, header)

            # Fast path: only read the 6 sensors we need
            for attr_name, idx in self._sensor_indices.items():
                addr = base + self._reading_offset + idx * self._reading_size
                reading = _HWiNFOReading.from_address(addr)
                setattr(data, attr_name, reading.Value)

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

from .styles import MEMORY_UNITS, get_process_display_name


# Indices into the aggregated per-process list [cpu_pct, threads, rss, vms, count]
_CPU_IDX     = 0
_THREADS_IDX = 1
_RSS_IDX     = 2
_VMS_IDX     = 3
_COUNT_IDX   = 4


class MonitorMode(Enum):
    """Monitoring mode selection."""

    CPU = auto()
    MEMORY = auto()
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
) -> tuple[dict[str, list], float, int]:
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
    attrs = ['name']
    if need_cpu:
        attrs += ['pid', 'cpu_percent', 'num_threads']
    if need_mem:
        attrs += ['memory_info']

    aggregated: dict[str, list] = {}
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

            display_name = get_process_display_name(name)
            if display_name in aggregated:
                entry = aggregated[display_name]
                entry[_CPU_IDX]     += cpu_pct
                entry[_THREADS_IDX] += threads
                entry[_RSS_IDX]     += rss
                entry[_VMS_IDX]     += vms
                entry[_COUNT_IDX]   += 1
            else:
                aggregated[display_name] = [cpu_pct, threads, rss, vms, 1]

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return aggregated, total_cpu, total_rss


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
        self.history: list[HistoryRecord] = []
        self.history_max_size = 10
        self.retention_seconds = 120 * 60  # 2 hours default

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
        aggregated, total_cpu, total_rss = _collect_processes(need_cpu, need_mem, self.cpu_threads)
        if need_cpu:
            return self._extract_cpu_top(aggregated, total_cpu, limit)
        return self._extract_mem_top(aggregated, total_rss, limit)

    def _extract_cpu_top(self, aggregated: dict[str, list], total_cpu: float, limit: int) -> list[ProcessInfo]:
        """Extract top CPU processes from aggregated data and update stats."""
        self.stats.total_usage = total_cpu
        self.stats.process_count = len(aggregated)

        if total_cpu > self.stats.max_usage:
            self.stats.max_usage = total_cpu
            self.stats.max_usage_time = datetime.now()

        top = heapq.nlargest(limit, aggregated.items(), key=lambda x: x[1][_CPU_IDX])
        return [
            ProcessInfo(name=name, value=entry[_CPU_IDX], threads=entry[_THREADS_IDX], count=entry[_COUNT_IDX])
            for name, entry in top
        ]

    def _extract_mem_top(self, aggregated: dict[str, list], total_rss: int, limit: int) -> list[ProcessInfo]:
        """Extract top memory processes from aggregated data and update stats."""
        self.stats.total_usage = total_rss
        self.stats.process_count = len(aggregated)

        if total_rss > self.stats.max_usage:
            self.stats.max_usage = total_rss
            self.stats.max_usage_time = datetime.now()

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
        self.history = [
            record for record in self.history
            if (now - record.timestamp) < self.retention_seconds
        ]

        # Check each process against history
        for proc in processes:
            if proc.value <= 0:
                continue

            # Find existing record for this process
            existing_idx = None
            for i, record in enumerate(self.history):
                if record.name == proc.name:
                    existing_idx = i
                    break

            if existing_idx is not None:
                # Update if current value is higher
                if proc.value > self.history[existing_idx].value:
                    self.history[existing_idx] = HistoryRecord(
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
                    self.history.append(HistoryRecord(
                        name=proc.name,
                        value=proc.value,
                        timestamp=now,
                        threads=proc.threads,
                        count=proc.count,
                        vms=proc.vms,
                    ))
                elif self.history and proc.value > self.history[-1].value:
                    # Replace lowest record
                    self.history[-1] = HistoryRecord(
                        name=proc.name,
                        value=proc.value,
                        timestamp=now,
                        threads=proc.threads,
                        count=proc.count,
                        vms=proc.vms,
                    )

        # Sort history by value (descending)
        self.history.sort(key=lambda r: r.value, reverse=True)

    def get_history(self) -> list[HistoryRecord]:
        """Get historical high-usage records."""
        return self.history[:self.history_max_size]

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
            # No decimals for CPU percentage
            return f"{value:.0f}%"
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
            return f"{self.stats.total_usage:.0f}% ({total_pct:.0f}%)"
        else:
            divisor = MEMORY_UNITS.get(unit, MEMORY_UNITS["MB"])
            total = self.stats.total_usage / divisor
            pct = (self.stats.total_usage / self.ram_bytes) * 100
            if unit == "GB":
                return f"{total:,.2f} {unit} ({pct:.0f}%)"
            else:
                return f"{total:,.0f} {unit} ({pct:.0f}%)"

    def get_max_display(self, unit: str = "MB") -> str:
        """Get formatted maximum usage string."""
        if self.stats.max_usage_time is None:
            return "No data yet"

        time_str = self.stats.max_usage_time.strftime("%H:%M")

        if self.mode == MonitorMode.CPU:
            return f"Peak: {self.stats.max_usage:.0f}% at {time_str}"
        else:
            divisor = MEMORY_UNITS.get(unit, MEMORY_UNITS["MB"])
            value = self.stats.max_usage / divisor
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


class SharedDataCollector(QThread):
    """
    Singleton that collects process data once and distributes to multiple windows.
    """

    cpu_data_ready = Signal(MonitorData)
    memory_data_ready = Signal(MonitorData)

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
        self._running = False
        self._interval_ms = 1000
        self._cpu_refresh_ms = 1000
        self._memory_refresh_ms = 1000
        self._mutex = QMutex()

        # Settings per mode
        self._cpu_settings: Optional[dict] = None
        self._memory_settings: Optional[dict] = None

        # Subscribers
        self._cpu_enabled = False
        self._memory_enabled = False

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
            self._memory_refresh_ms = refresh_rate_ms
            self._memory_enabled = True
            self._interval_ms = self._compute_interval()

    def disable_cpu(self):
        """Disable CPU monitoring."""
        with QMutexLocker(self._mutex):
            self._cpu_enabled = False
            if not self._memory_enabled:
                self.stop()

    def disable_memory(self):
        """Disable Memory monitoring."""
        with QMutexLocker(self._mutex):
            self._memory_enabled = False
            if not self._cpu_enabled:
                self.stop()

    def _compute_interval(self) -> int:
        """Compute interval as min of all enabled modes. Must be called within mutex."""
        rates = []
        if self._cpu_enabled:
            rates.append(self._cpu_refresh_ms)
        if self._memory_enabled:
            rates.append(self._memory_refresh_ms)
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
                interval = self._interval_ms

            need_cpu = bool(cpu_enabled and cpu_monitor and cpu_settings)
            need_mem = bool(mem_enabled and mem_monitor and mem_settings)

            if need_cpu or need_mem:
                # Single psutil iteration for both CPU and RAM
                cpu_threads = cpu_monitor.cpu_threads if cpu_monitor else psutil.cpu_count()
                aggregated, total_cpu, total_rss = _collect_processes(need_cpu, need_mem, cpu_threads)

                hwinfo = cpu_monitor.get_hwinfo_data() if cpu_monitor else HWiNFOData()

                if need_cpu:
                    processes = cpu_monitor._extract_cpu_top(aggregated, total_cpu, cpu_settings['current_rows'])
                    cpu_monitor.update_history(processes)
                    self.cpu_data_ready.emit(MonitorData(
                        processes=processes,
                        history=cpu_monitor.get_history(),
                        total_display=cpu_monitor.get_total_display("MB"),
                        max_display=cpu_monitor.get_max_display("MB"),
                        hwinfo=hwinfo,
                        stats=cpu_monitor.stats,
                    ))

                if need_mem:
                    unit = mem_settings.get('memory_unit', 'MB')
                    processes = mem_monitor._extract_mem_top(aggregated, total_rss, mem_settings['current_rows'])
                    mem_monitor.update_history(processes)
                    self.memory_data_ready.emit(MonitorData(
                        processes=processes,
                        history=mem_monitor.get_history(),
                        total_display=mem_monitor.get_total_display(unit),
                        max_display=mem_monitor.get_max_display(unit),
                        hwinfo=hwinfo,
                        stats=mem_monitor.stats,
                    ))

            self.msleep(interval)

    def stop(self):
        """Stop the collector."""
        self._running = False
        self.wait(2000)

    @property
    def cpu_monitor(self) -> Optional[ProcessMonitor]:
        """Get CPU monitor instance."""
        return self._cpu_monitor

    @property
    def memory_monitor(self) -> Optional[ProcessMonitor]:
        """Get Memory monitor instance."""
        return self._memory_monitor

    @classmethod
    def reset_instance(cls):
        """Reset singleton (for testing)."""
        with QMutexLocker(cls._lock):
            if cls._instance is not None:
                cls._instance.stop()
                cls._instance = None
