"""Per-process network statistics.

`NetworkMonitor` is the network mode's counterpart to `ProcessMonitor`: it
takes the ETW tracer's raw per-PID byte counters, turns them into per-process
rates, and keeps the peak history, the rolling averages and the cumulative
totals the Network window shows. It never touches ETW itself — the tracer
(`network_trace.py`) owns that.
"""

import time
from collections import deque
from datetime import datetime

from ..styles import format_speed
from .monitor_data import NetworkHistoryRecord, NetworkProcessInfo
from .rolling_window import RollingWindow


# ═══════════════════════════ THE NETWORK MONITOR ═══════════════════════════

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

        # Rolling average window: (dl, ul) per tick
        self._rolling = RollingWindow(self.retention_seconds, n_fields=2)

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

        # Update peak buffer (track download only)
        self._peak_buffer.append((now, total_dl_rate))
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
        """Add snapshot to the rolling window (see RollingWindow)."""
        self._rolling.retention_seconds = self.retention_seconds
        self._rolling.add(now, snapshot)

    def get_rolling_average(self, limit: int = 0) -> list[NetworkProcessInfo]:
        """Get per-process rolling averages sorted by sort mode."""
        total_snapshots = self._rolling.total_samples
        if total_snapshots == 0:
            return []
        actual_span = self._rolling.span_seconds()

        result = []
        for name, (total_dl, total_ul), samples in self._rolling.items():
            avg_dl = total_dl / total_snapshots
            avg_ul = total_ul / total_snapshots
            if avg_dl <= 0 and avg_ul <= 0:
                continue
            uptime_seconds = round(samples * actual_span / total_snapshots) if actual_span else 0
            result.append(NetworkProcessInfo(name=name, download=avg_dl, upload=avg_ul, uptime_seconds=uptime_seconds))

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
        """Get formatted peak download speed string."""
        if not self._peak_buffer:
            return "Peak: --"
        peak_ts, peak_dl = max(self._peak_buffer, key=lambda x: x[1])
        time_str = datetime.fromtimestamp(peak_ts).strftime("%H:%M")
        return f"Peak: {format_speed(peak_dl, unit)} at {time_str}"
