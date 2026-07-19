# Process Monitor

**Script:** [monitor.py (script)](monitor.py)

---

## Purpose

Core data-collection layer. Collects CPU, Memory, and Network usage per
process and distributes it to all open windows from a single background
thread. CPU and Memory data come from one bulk `NtQuerySystemInformation`
call per tick (not per-process psutil calls); Network data comes from the
ETW tracer in [Network Monitor](network_monitor.md). Also reads optional
HWiNFO sensor data (CPU temperature/power, DRAM bandwidth) from shared memory.

---

## Connections

### Uses

- [Styles](styles.md) — `Defaults`, `MEMORY_UNITS`, `format_pct`, `format_speed`, `get_process_display_name`
- [Color Management](color_management.md) — `ProcessColorManager` (company lookup runs inside the collector loop)
- [Network Monitor](network_monitor.md) — `NetworkTracer`, lazily imported by `configure_network()`
- `psutil` — CPU count, virtual memory totals
- Windows APIs (`ctypes`) — `ntdll.NtQuerySystemInformation` (bulk process data), `psapi.GetPerformanceInfo` (commit limit), HWiNFO shared-memory section

### Used by

- [Main Window](main_window.md) — `BaseMonitorWindow` subclasses hold a `SharedDataCollector` instance and read `cpu_monitor`/`memory_monitor`/`network_monitor`
- [Settings Dialog](settings_dialog.md) — `get_commit_limit_bytes()` for the Commit color-scale max
- `main.py` — creates the one `SharedDataCollector()` and starts it
- `app/__init__.py` — re-exports `MonitorMode`, `ProcessMonitor`, `SharedDataCollector`

---

## Classes

### MonitorMode (Enum)

`CPU`, `MEMORY`, `NETWORK`, `BOTH` (BOTH is a launch-dialog convenience value, not read by the collector).

### ProcessInfo / HistoryRecord / MonitorStats / MonitorData

Per-process snapshot, peak-history record, running totals, and the bundle
`SharedDataCollector` emits on `cpu_data_ready`/`memory_data_ready`. Key
`ProcessInfo` fields: `name`, `value` (CPU % or memory bytes), `threads`,
`count` (parallel process count in the group), `vms` (commit size),
`uptime_seconds` (rolling-average rows only).

### NetworkProcessInfo / NetworkHistoryRecord / NetworkMonitorData

Network equivalents (`download`/`upload` bytes/sec instead of a single
`value`). `NetworkMonitorData.error` is non-empty when the ETW tracer failed
to start — the Network window shows this string instead of zeros.

### RollingWindow

Shared rolling-average accumulator used by both `ProcessMonitor` (4 fields:
value, threads, count, vms) and `NetworkMonitor` (2 fields: download, upload).

| Method | Description |
|--------|-------------|
| `add(now, snapshot)` | Adds one tick's per-name values; seals and expires buckets. |
| `items()` | Yields `(name, field_sums, tick_count)` for every name currently in the window. |
| `span_seconds()` | Time between the oldest and newest tick in the window. |
| `total_samples` (property) | Number of ticks currently inside the window. |

### ProcessMonitor

Per-mode (CPU or Memory) monitor: aggregates processes by name, tracks
history and rolling averages.

| Method | Description |
|--------|-------------|
| `set_mode(mode)` | Switch CPU/Memory mode; resets stats. |
| `set_history_settings(max_size, retention_minutes)` | Configure history size and retention. |
| `set_refresh_rate(refresh_rate_ms)` | Store the refresh rate (used to compute uptime from sample count). |
| `update_history(processes)` | Update peak-usage records from the latest snapshot. |
| `get_history()` | Peak records sorted by value descending. |
| `update_rolling_average(aggregated)` | Feed one tick's aggregated data into the `RollingWindow`. |
| `get_rolling_average(limit)` | Per-process averages across the rolling window, sorted descending. |
| `format_value(value, unit)` | Format a raw value (% or bytes) for display. |
| `get_total_display(unit)` / `get_max_display(unit)` | Formatted current-total / peak strings for the header. |
| `get_hwinfo_data()` | Lazily creates and reads the shared `HWiNFOSharedMemory` reader. |

### NetworkMonitor

Network equivalent of `ProcessMonitor`. `sort_mode` is `"total"`,
`"download"`, or `"upload"`; controls both current-table ordering and which
history/rolling records survive.

| Method | Description |
|--------|-------------|
| `process_snapshot(pid_bytes, pid_to_name, elapsed_sec, limit)` | Aggregates ETW per-PID bytes into per-name rates, updates cumulative totals, peak buffer, and the rolling window; returns the top N. |
| `get_rolling_average(limit)` | Per-process rolling averages sorted by `sort_mode`. |
| `update_history(processes)` / `get_history()` | Peak-record tracking, same pattern as `ProcessMonitor`. |
| `get_peak_display(unit)` | Formatted peak download-speed string for the header. |

### SharedDataCollector (QThread singleton)

One background thread collects for **all** enabled modes and emits to every
subscriber — see Design Decisions.

Signals: `cpu_data_ready(MonitorData)`, `memory_data_ready(MonitorData)`,
`network_data_ready(NetworkMonitorData)`.

| Method | Description |
|--------|-------------|
| `configure_cpu(...)` / `configure_memory(...)` / `configure_network(...)` | Called by the owning window at startup and whenever settings change; lazily creates the mode's `ProcessMonitor`/`NetworkMonitor` and (for network) starts the `NetworkTracer`. A configured mode stays enabled for the app's lifetime — hiding a window no longer disables it (CPU/Memory share one bulk syscall, so pausing saves nothing). |
| `run()` | Main loop: one bulk collect per tick, dispatches to whichever modes are enabled, sleeps in chunks. |
| `stop()` | Signals the loop to exit, stops the tracer if running, joins the thread (2s timeout). |
| `cpu_monitor` / `memory_monitor` / `network_monitor` (properties) | Access the underlying per-mode monitor instances. |
| `reset_instance()` (classmethod) | Stops and clears the singleton — used at app shutdown. |

---

## Functions

`get_commit_limit_bytes()` — system commit limit (RAM + page files) via
`GetPerformanceInfo`; falls back to physical RAM total if the WinAPI call
raises.

---

## Design Decisions

**One `NtQuerySystemInformation` call per tick, not per-process psutil calls.**
`_collect_processes_bulk()` replaces ~300 per-process kernel transitions with
one system-wide call, cutting collector CPU usage roughly 10–20×. CPU deltas
are computed from `UserTime`/`KernelTime` against the previous tick's cached
values (`_prev_cpu_times`), so the very first tick after CPU mode is enabled
has no baseline and is discarded (`_first_cpu_tick`).

**`SharedDataCollector` is a singleton QThread, not one thread per window.**
CPU, Memory, and Network windows all need the same per-tick process
enumeration; running three independent collectors would triplicate the
kernel call and (for Network) fight over the same ETW session. Enabling a
mode just registers it with the one running thread; the tick interval is the
`min()` of all enabled modes' refresh rates.

**`RollingWindow` uses bucketed expiry, not one snapshot per tick.** Storing
every tick's per-name values individually would be O(ticks × names) memory —
at 120 min retention and 1s refresh that's 7200 snapshots. Merging ticks into
`Defaults.ROLLING_BUCKET_SECONDS`-wide buckets drops this to
O(buckets × names), ~45× less, at the cost of values leaving the window in
bucket-sized groups (up to one bucket span late) — negligible for a
multi-minute average.

**The collector sleeps in `Defaults.COLLECTOR_SLEEP_CHUNK_MS` chunks**, not
one `msleep(interval)` call, so `stop()` interrupts within one chunk instead
of waiting out a full slow-refresh-rate interval.
