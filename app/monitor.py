"""
Process Monitor

Handles process data collection using psutil.
Supports CPU and Memory monitoring modes.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional

import psutil

from .styles import MEMORY_UNITS, get_process_display_name


class MonitorMode(Enum):
    """Monitoring mode selection."""

    CPU = auto()
    MEMORY = auto()


@dataclass
class ProcessInfo:
    """Information about a single process or process group."""

    name: str
    value: float  # CPU % or Memory bytes
    cores_used: float = 0.0  # Estimated CPU cores used
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
    cores_used: float = 0.0

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
        Get current process usage data.

        Args:
            limit: Maximum number of processes to return

        Returns:
            List of ProcessInfo sorted by usage (descending)
        """
        if self.mode == MonitorMode.CPU:
            return self._get_cpu_processes(limit)
        else:
            return self._get_memory_processes(limit)

    def _get_cpu_processes(self, limit: int) -> list[ProcessInfo]:
        """Get CPU usage per process."""
        aggregated: dict[str, float] = defaultdict(float)
        total_cpu = 0.0

        for proc in psutil.process_iter(['name', 'cpu_percent']):
            try:
                info = proc.info
                name = info['name']
                cpu_pct = info['cpu_percent']

                if name == 'System Idle Process':
                    # Calculate actual CPU usage from idle
                    total_cpu = (self.cpu_threads * 100) - cpu_pct
                    continue

                if not name:
                    continue

                display_name = get_process_display_name(name)
                aggregated[display_name] += cpu_pct

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Update stats
        self.stats.total_usage = total_cpu
        self.stats.process_count = len(aggregated)

        if total_cpu > self.stats.max_usage:
            self.stats.max_usage = total_cpu
            self.stats.max_usage_time = datetime.now()

        # Convert to ProcessInfo list
        processes = []
        for name, cpu_pct in aggregated.items():
            # Calculate cores used (100% = 1 core)
            cores_used = cpu_pct / 100.0
            processes.append(ProcessInfo(
                name=name,
                value=cpu_pct,
                cores_used=cores_used,
            ))

        # Sort by usage and limit
        processes.sort(key=lambda p: p.value, reverse=True)
        return processes[:limit]

    def _get_memory_processes(self, limit: int) -> list[ProcessInfo]:
        """Get memory usage per process."""
        aggregated: dict[str, int] = defaultdict(int)
        total_memory = 0

        for proc in psutil.process_iter(['name', 'memory_info']):
            try:
                info = proc.info
                name = info['name']
                mem_info = info['memory_info']

                if not name or not mem_info:
                    continue

                display_name = get_process_display_name(name)
                mem_bytes = mem_info.rss
                aggregated[display_name] += mem_bytes
                total_memory += mem_bytes

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Update stats
        self.stats.total_usage = total_memory
        self.stats.process_count = len(aggregated)

        if total_memory > self.stats.max_usage:
            self.stats.max_usage = total_memory
            self.stats.max_usage_time = datetime.now()

        # Convert to ProcessInfo list
        processes = [
            ProcessInfo(name=name, value=mem_bytes)
            for name, mem_bytes in aggregated.items()
        ]

        # Sort by usage and limit
        processes.sort(key=lambda p: p.value, reverse=True)
        return processes[:limit]

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
                        cores_used=proc.cores_used,
                    )
            else:
                # Add new record if we have space or this beats the lowest
                if len(self.history) < self.history_max_size:
                    self.history.append(HistoryRecord(
                        name=proc.name,
                        value=proc.value,
                        timestamp=now,
                        cores_used=proc.cores_used,
                    ))
                elif self.history and proc.value > self.history[-1].value:
                    # Replace lowest record
                    self.history[-1] = HistoryRecord(
                        name=proc.name,
                        value=proc.value,
                        timestamp=now,
                        cores_used=proc.cores_used,
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
            return f"{value:.1f}%"
        else:
            divisor = MEMORY_UNITS.get(unit, MEMORY_UNITS["MB"])
            converted = value / divisor
            decimals = 2 if unit == "GB" else (1 if unit == "MB" else 0)
            return f"{converted:,.{decimals}f} {unit}"

    def format_cores(self, cores: float) -> str:
        """Format cores used for display."""
        if cores < 0.1:
            return ""
        elif cores < 1:
            return f"{cores:.1f}"
        else:
            return f"{cores:.1f}"

    def get_total_display(self, unit: str = "MB") -> str:
        """Get formatted total usage string."""
        if self.mode == MonitorMode.CPU:
            total_pct = (self.stats.total_usage / (self.cpu_threads * 100)) * 100
            return f"{self.stats.total_usage:.1f}% ({total_pct:.0f}% of {self.cpu_threads} threads)"
        else:
            divisor = MEMORY_UNITS.get(unit, MEMORY_UNITS["MB"])
            total = self.stats.total_usage / divisor
            ram_total = self.ram_bytes / divisor
            pct = (self.stats.total_usage / self.ram_bytes) * 100
            decimals = 2 if unit == "GB" else (1 if unit == "MB" else 0)
            return f"{total:,.{decimals}f} / {ram_total:,.{decimals}f} {unit} ({pct:.1f}%)"

    def get_max_display(self, unit: str = "MB") -> str:
        """Get formatted maximum usage string."""
        if self.stats.max_usage_time is None:
            return "No data yet"

        time_str = self.stats.max_usage_time.strftime("%H:%M")

        if self.mode == MonitorMode.CPU:
            return f"Peak: {self.stats.max_usage:.1f}% at {time_str}"
        else:
            divisor = MEMORY_UNITS.get(unit, MEMORY_UNITS["MB"])
            value = self.stats.max_usage / divisor
            decimals = 2 if unit == "GB" else (1 if unit == "MB" else 0)
            return f"Peak: {value:,.{decimals}f} {unit} at {time_str}"
