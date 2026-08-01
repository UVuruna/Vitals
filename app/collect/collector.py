"""The single collector thread that feeds every monitor window.

`SharedDataCollector` is a QThread singleton. One tick makes ONE bulk process
query and ONE ETW snapshot, feeds the per-mode statistics objects, and emits a
signal per enabled mode — so three open windows cost exactly what one costs.

It also owns the ETW tracer's lifecycle, including the failure paths: a trace
that never started and a consumer thread that died after a good start both end
up as a structured `TraceFailure` in the Network window's banner rather than
as a plausible, permanent zero.
"""

import time
from typing import Optional

import psutil
from PySide6.QtCore import QMutex, QMutexLocker, QThread, Signal

from ..color_management import ProcessColorManager
from ..styles import Defaults
from .hwinfo import HWiNFOData
from .monitor_data import (
    MonitorData,
    MonitorMode,
    NetworkMonitorData,
    ProcessInfo,
)
from .network_stats import NetworkMonitor
from .network_trace import CONSUMER_DIED, START_FAILED, TraceFailure
from .process_stats import ProcessMonitor
from .system_query import (
    COUNT_IDX,
    PID_IDX,
    THREADS_IDX,
    VMS_IDX,
    collect_processes_bulk,
)


# ═══════════════════════════ THE COLLECTOR THREAD ═══════════════════════════

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
        self._network_tracer_error: Optional[TraceFailure] = None  # Why capture is unavailable
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

            # Start ETW tracer if not already running. On failure the tracer is
            # discarded and the error surfaces in the Network window header.
            if self._network_tracer is None:
                from .network_trace import NetworkTracer, _log as _net_log
                tracer = NetworkTracer()
                if tracer.start():
                    self._network_tracer = tracer
                    self._network_tracer_error = None
                else:
                    self._network_tracer_error = tracer.error or TraceFailure(
                        START_FAILED,
                        "The network trace could not be started.",
                        "Press Retry.",
                    )
                    _net_log.info(
                        "configure_network: tracer.start() failed, code=%s detail=%s",
                        self._network_tracer_error.code,
                        self._network_tracer_error.detail,
                    )

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
                net_tracer_error = self._network_tracer_error
                net_settings = self._network_settings.copy() if self._network_settings else None
                interval = self._interval_ms

            # A tracer whose consumer thread died AFTER start() reported
            # success keeps returning empty snapshots, so every rate reads as a
            # legitimate zero forever. Retire it here so the failure takes the
            # same visible path as one that never started (root Rule #1).
            if net_tracer is not None and net_tracer.is_dead():
                failure = net_tracer.error or TraceFailure(
                    CONSUMER_DIED,
                    "Network capture stopped unexpectedly.",
                    "Press Retry to start a new trace session.",
                )
                # stop() joins the consumer thread — never hold the collector
                # mutex across it, or a configure_*() call would block for it.
                net_tracer.stop()
                with QMutexLocker(self._mutex):
                    self._network_tracer = None
                    self._network_tracer_error = failure
                net_tracer = None
                net_tracer_error = failure

            need_cpu = bool(cpu_enabled and cpu_monitor and cpu_settings)
            need_mem = bool(mem_enabled and mem_monitor and mem_settings)
            need_net = bool(net_enabled and net_monitor and net_tracer and net_settings)

            # Network enabled but no live tracer: surface the reason in the
            # Network window instead of silently showing zeros forever
            if net_enabled and net_settings and net_tracer is None:
                self.network_data_ready.emit(NetworkMonitorData(
                    processes=[], history=[], rolling_average=[],
                    current_download=0.0, current_upload=0.0,
                    cumulative_download=0, cumulative_upload=0,
                    peak_display="--",
                    sort_mode=net_settings.get('sort_mode', 'total'),
                    error=net_tracer_error or TraceFailure(
                        START_FAILED,
                        "The network trace is not running.",
                        "Press Retry.",
                    ),
                ))

            if need_cpu or need_mem or need_net:
                # Single NtQuerySystemInformation call (replaces ~300 per-process psutil calls)
                cpu_threads = cpu_monitor.cpu_threads if cpu_monitor else psutil.cpu_count()
                aggregated, total_cpu, total_rss, pid_to_name = collect_processes_bulk(need_cpu, need_mem, cpu_threads)

                # Register new process names for company color lookup (fast no-op for cached names)
                color_mgr = ProcessColorManager()
                for proc_name, entry in aggregated.items():
                    color_mgr.lookup_company(proc_name, entry[PID_IDX])
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
                        threads=sum(e[THREADS_IDX] for e in aggregated.values()),
                        count=sum(e[COUNT_IDX] for e in aggregated.values()),
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
                        vms=sum(e[VMS_IDX] for e in aggregated.values()),
                        count=sum(e[COUNT_IDX] for e in aggregated.values()),
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

            # Sleep in chunks so stop() interrupts promptly at slow refresh rates
            slept = 0
            while self._running and slept < interval:
                chunk = min(Defaults.COLLECTOR_SLEEP_CHUNK_MS, interval - slept)
                self.msleep(chunk)
                slept += chunk

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
