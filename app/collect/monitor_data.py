"""The records the collector emits — the contract between data and windows.

Everything a monitor window receives comes through these dataclasses. Keeping
them in one module means a window imports the SHAPE of its tick without
importing the collector that produced it, and the collector can be read
without hunting for what its signals carry.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional

from .hwinfo import HWiNFOData
from .network_trace import TraceFailure


# ══════════════════════════════ MONITOR MODE ══════════════════════════════

class MonitorMode(Enum):
    """Monitoring mode selection."""

    CPU = auto()
    MEMORY = auto()
    NETWORK = auto()
    BOTH = auto()  # Opens both CPU and Memory windows


# ═══════════════════════ CPU / MEMORY PROCESS RECORDS ═══════════════════════

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


# ═══════════════════════════ NETWORK RECORDS ═══════════════════════════

@dataclass
class NetworkProcessInfo:
    """Per-process network traffic for one tick."""
    name: str
    download: float  # bytes/sec received
    upload: float    # bytes/sec sent
    timestamp: float = field(default_factory=time.time)
    uptime_seconds: int = 0  # Rolling average only: seconds active within retention window


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
    # Why capture is unavailable, or None while it is running. A structured
    # TraceFailure, not a message: the window picks the remedy from its code.
    error: Optional[TraceFailure] = None
