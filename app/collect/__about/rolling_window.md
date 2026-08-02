# Rolling Window

**Script:** [Rolling Window (script)](../rolling_window.py) ·
**Flow:** [diagram](../__flow/rolling_window.md)

## Purpose

The shared rolling-average engine behind both "Rolling Average" tables.
`ProcessMonitor` feeds it 4 fields per process (value, threads, count, vms);
`NetworkMonitor` feeds it 2 (download, upload). It answers one question per
tick — "what has each name averaged over the last N minutes" — with
tick-accurate totals but O(buckets) memory instead of O(ticks), by merging
ticks into coarse time buckets before they age out. See
[flow](../__flow/rolling_window.md) for the accumulator/bucket mechanics.

## Connections

### Uses
- [Styles](../../__about/styles.md) — `Defaults.ROLLING_BUCKET_SECONDS`, the
  bucket span

### Used by
- [Process Stats](process_stats.md) — one `RollingWindow(retention, n_fields=4)`
  per `ProcessMonitor` instance (CPU and Memory each own theirs)
- [Network Stats](network_stats.md) — one `RollingWindow(retention, n_fields=2)`
  per `NetworkMonitor`

## Classes

### `RollingWindow`
Rolling-average buffer with per-tick accuracy and bucketed expiry.

- `retention_seconds` — how long a tick counts toward the average
- `total_samples` (property) — number of ticks currently inside the window
- `span_seconds()` — time between the oldest and newest tick in the window
- `items()` — yields `(name, field_sums, tick_count)` for every name
  currently retained
- `add(now, snapshot)` — adds one tick's per-name values to the live
  accumulator, rolls the current bucket, and expires whole buckets past
  retention
