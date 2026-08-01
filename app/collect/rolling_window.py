"""Rolling-average window with per-tick accuracy and bucketed expiry.

The shared engine behind both "Rolling Average" tables: `ProcessMonitor` feeds
it 4 fields per process (value, threads, count, vms), `NetworkMonitor` 2
(download, upload).
"""

from collections import deque

from ..styles import Defaults


# ═══════════════════════════ THE ROLLING WINDOW ═══════════════════════════

class RollingWindow:
    """Rolling-average buffer with per-tick accuracy and bucketed expiry.

    Shared by ProcessMonitor (4 fields) and NetworkMonitor (2 fields).

    Every tick's values are added to a per-name accumulator immediately, so
    averages stay tick-accurate. For expiry, ticks are merged into coarse
    time buckets (Defaults.ROLLING_BUCKET_SECONDS) instead of storing one
    snapshot per tick: memory is O(buckets x names) instead of
    O(ticks x names) — ~45x less at default settings (120 min @ 1 s).
    Tradeoff: values leave the window in bucket-sized groups, up to one
    bucket span later than exact — negligible for a multi-minute average.
    """

    def __init__(self, retention_seconds: int, n_fields: int):
        self.retention_seconds = retention_seconds
        self._n_fields = n_fields
        # {name: [field_sums..., tick_count]} over the whole window
        self._acc: dict[str, list] = {}
        # Sealed buckets: [start_ts, last_ts, tick_count, {name: [field_sums..., tick_count]}]
        self._buckets: deque = deque()
        self._current: list | None = None  # same shape as a sealed bucket
        self._total_samples = 0

    @property
    def total_samples(self) -> int:
        """Number of ticks currently inside the window."""
        return self._total_samples

    def span_seconds(self) -> float:
        """Time between the oldest and newest tick in the window."""
        if self._current is not None:
            newest = self._current[1]
            oldest = self._buckets[0][0] if self._buckets else self._current[0]
        elif self._buckets:
            newest = self._buckets[-1][1]
            oldest = self._buckets[0][0]
        else:
            return 0.0
        return newest - oldest

    def items(self):
        """Yield (name, field_sums, tick_count) for every name in the window."""
        n = self._n_fields
        for name, entry in self._acc.items():
            if entry[n] > 0:
                yield name, entry[:n], entry[n]

    def add(self, now: float, snapshot: dict[str, tuple]) -> None:
        """Add one tick's per-name values and expire old buckets."""
        n = self._n_fields
        if self._current is None:
            self._current = [now, now, 0, {}]
        cur = self._current
        cur[1] = now
        cur[2] += 1
        bucket_map = cur[3]

        for name, values in snapshot.items():
            acc_entry = self._acc.get(name)
            if acc_entry is None:
                acc_entry = self._acc[name] = [0.0] * n + [0]
            b_entry = bucket_map.get(name)
            if b_entry is None:
                b_entry = bucket_map[name] = [0.0] * n + [0]
            for i in range(n):
                acc_entry[i] += values[i]
                b_entry[i] += values[i]
            acc_entry[n] += 1
            b_entry[n] += 1

        self._total_samples += 1

        # Seal the current bucket once it covers a full span
        if now - cur[0] >= Defaults.ROLLING_BUCKET_SECONDS:
            self._buckets.append(cur)
            self._current = None

        # Expire buckets whose newest tick left the retention window
        cutoff = now - self.retention_seconds
        while self._buckets and self._buckets[0][1] < cutoff:
            _, _, ticks, expired = self._buckets.popleft()
            self._total_samples -= ticks
            for name, b_entry in expired.items():
                acc_entry = self._acc.get(name)
                if acc_entry is None:
                    continue
                for i in range(n):
                    acc_entry[i] -= b_entry[i]
                acc_entry[n] -= b_entry[n]
                if acc_entry[n] <= 0:
                    del self._acc[name]
