"""CPU / Memory statistics for one monitor mode.

`ProcessMonitor` turns the raw per-tick aggregate from `system_query` into
what a window actually shows: the top-N table, the historical peak records,
the rolling averages, and the formatted header strings. One instance per mode
— the collector owns a CPU one and a Memory one — so their histories, peak
buffers and retention settings never mix.
"""

import heapq
import time
from datetime import datetime
from collections import deque
from typing import Optional

import psutil

from ..styles import MEMORY_UNITS, format_pct
from .hwinfo import HWiNFOData, read_sensors
from .monitor_data import HistoryRecord, MonitorMode, MonitorStats, ProcessInfo
from .rolling_window import RollingWindow
from .system_query import COUNT_IDX, CPU_IDX, RSS_IDX, THREADS_IDX, VMS_IDX


# ══════════════════════════ THE PER-MODE MONITOR ══════════════════════════

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

        # Rolling average window: (value, threads, count, vms) per tick
        self._rolling = RollingWindow(self.retention_seconds, n_fields=4)
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

    def get_hwinfo_data(self) -> HWiNFOData:
        """
        Get all HWiNFO sensor data.

        Returns:
            HWiNFOData with CPU temps, ambient temp, DRAM bandwidth
        """
        return read_sensors()

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

    def _extract_cpu_top(self, aggregated: dict[str, list], total_cpu: float, limit: int) -> list[ProcessInfo]:
        """Extract top CPU processes from aggregated data and update stats."""
        self.stats.process_count = len(aggregated)

        if self._first_cpu_tick:
            # No prev-tick delta yet: total_cpu is a bogus artifact (cpu_threads*100 - 0).
            self.stats.total_usage = 0.0
            self._first_cpu_tick = False
        else:
            self.stats.total_usage = total_cpu
            now_ts = time.time()
            self._peak_buffer.append((now_ts, total_cpu))
            cutoff = now_ts - self.retention_seconds
            while self._peak_buffer and self._peak_buffer[0][0] < cutoff:
                self._peak_buffer.popleft()

        top = heapq.nlargest(limit, aggregated.items(), key=lambda x: x[1][CPU_IDX])
        return [
            ProcessInfo(name=name, value=entry[CPU_IDX], threads=entry[THREADS_IDX], count=entry[COUNT_IDX])
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

        top = heapq.nlargest(limit, aggregated.items(), key=lambda x: x[1][RSS_IDX])
        return [
            ProcessInfo(name=name, value=entry[RSS_IDX], vms=entry[VMS_IDX], count=entry[COUNT_IDX])
            for name, entry in top
        ]

    def update_history(self, processes: list[ProcessInfo]):
        """
        Update historical high-usage records.

        Args:
            processes: Current process list from _extract_cpu_top/_extract_mem_top
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
        """Add the current process snapshot to the rolling window.

        CPU mode captures (cpu_pct, threads, count, 0); Memory mode captures
        (rss, 0, count, vms). See RollingWindow for the accuracy/memory model.
        """
        if self.mode == MonitorMode.CPU:
            snapshot = {
                name: (entry[CPU_IDX], entry[THREADS_IDX], entry[COUNT_IDX], 0)
                for name, entry in aggregated.items()
            }
        else:
            snapshot = {
                name: (entry[RSS_IDX], 0, entry[COUNT_IDX], entry[VMS_IDX])
                for name, entry in aggregated.items()
            }
        self._rolling.retention_seconds = self.retention_seconds
        self._rolling.add(time.time(), snapshot)

    def get_rolling_average(self, limit: int = 0) -> list[ProcessInfo]:
        """Calculate per-process averages across the rolling window, sorted by average value descending.

        Args:
            limit: Maximum number of processes to return (0 = no limit).

        Reads from the RollingWindow accumulator maintained by update_rolling_average().
        Each process that appeared in at least one snapshot is included.
        Threads and count are rounded to the nearest integer.
        Processes with zero average value are excluded.
        """
        total_snapshots = self._rolling.total_samples
        if total_snapshots == 0:
            return []
        actual_span = self._rolling.span_seconds()

        result = []
        for name, (total_val, total_threads, total_count, total_vms), samples in self._rolling.items():
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
