# Network Stats

**Script:** [Network Stats (script)](../network_stats.py)

## Purpose

`NetworkMonitor` is the network mode's counterpart to `ProcessMonitor`: it
takes the ETW tracer's raw per-PID byte counters, turns them into
per-process rates, and keeps the peak history, the rolling averages and the
cumulative totals the Network window shows. It never touches ETW itself —
the tracer in [Network Trace](network_trace.md) owns that; this module only
consumes the `{pid: (bytes_recv, bytes_sent)}` snapshots it produces.

## Connections

### Uses
- [Styles](../../__about/styles.md) — `format_speed()`
- [Monitor Data](monitor_data.md) — `NetworkHistoryRecord`,
  `NetworkProcessInfo`
- [Rolling Window](rolling_window.md) — the 2-field (download, upload)
  averaging engine

### Used by
- [Collector](collector.md) — one `NetworkMonitor` instance, created on
  first `configure_network()` call

## Classes

### `NetworkMonitor`
Tracks per-process network traffic, history peaks, cumulative totals and
rolling averages. `sort_mode` (`"total"`, `"download"`, or `"upload"`)
controls both current-table ordering and which history/rolling records
survive when the top-N list is trimmed.

- `process_snapshot(pid_bytes, pid_to_name, elapsed_sec, limit)` —
  aggregates ETW per-PID bytes into per-process-name rates, updates
  cumulative totals and the peak buffer, feeds the rolling window, and
  returns the top N sorted by `sort_mode`
- `update_history(processes)` / `get_history()` — peak-record tracking, same
  pattern as `ProcessMonitor.update_history()`
- `get_rolling_average(limit)` — per-process rolling averages sorted by
  `sort_mode`
- `get_peak_display(unit)` — formatted peak download-speed string for the
  header
