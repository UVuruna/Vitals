# Process Stats

**Script:** [Process Stats (script)](../process_stats.py) ·
**Flow:** [diagram](../__flow/process_stats.md)

## Purpose

`ProcessMonitor` turns the raw per-tick aggregate from
[System Query](system_query.md) into what a window actually shows: the
top-N table, the historical peak records, the rolling averages, and the
formatted header strings. One instance per mode — the collector owns a CPU
one and a Memory one — so their histories, peak buffers and retention
settings never mix. See [flow](../__flow/process_stats.md) for one tick's
path through the extract / history / rolling steps.

## Connections

### Uses
- [Styles](../../__about/styles.md) — `MEMORY_UNITS`, `format_pct()`
- [HWiNFO Reader](hwinfo.md) — `HWiNFOData`, `read_sensors()`
- [Monitor Data](monitor_data.md) — `HistoryRecord`, `MonitorMode`,
  `MonitorStats`, `ProcessInfo`
- [Rolling Window](rolling_window.md) — the 4-field (value, threads, count,
  vms) averaging engine
- [System Query](system_query.md) — `COUNT_IDX`, `CPU_IDX`, `RSS_IDX`,
  `THREADS_IDX`, `VMS_IDX` layout constants

### Used by
- [Collector](collector.md) — owns one `ProcessMonitor(mode=CPU)` and one
  `ProcessMonitor(mode=MEMORY)`, calls `_extract_cpu_top()` /
  `_extract_mem_top()`, `update_history()`, `update_rolling_average()` each
  tick
- `app/__init__.py` — re-exports `ProcessMonitor`

## Classes

### `ProcessMonitor`
Per-mode (CPU or Memory) monitor: aggregates processes by name, tracks
history and rolling averages.

- `_extract_cpu_top(aggregated, total_cpu, limit)` /
  `_extract_mem_top(aggregated, total_rss, limit)` — top-N extraction plus
  stats/peak-buffer update; see [flow](../__flow/process_stats.md) for the
  `_first_cpu_tick` guard
- `update_history(processes)` / `get_history()` — peak-usage records,
  bounded by `history_max_size` and evicted by lowest value
- `update_rolling_average(aggregated)` / `get_rolling_average(limit)` —
  feeds and reads the `RollingWindow`
- `format_value(value, unit)` / `get_total_display(unit)` /
  `get_max_display(unit)` — header string formatting
- `get_hwinfo_data()` — thin pass-through to `hwinfo.read_sensors()`
