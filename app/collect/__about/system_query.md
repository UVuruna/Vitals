# System Query

**Script:** [System Query (script)](../system_query.py) ·
**Flow:** [diagram](../__flow/system_query.md)

## Purpose

Raw Windows kernel queries via `ctypes` — the app's process data source. Two
calls live here: `collect_processes_bulk()`, ONE
`NtQuerySystemInformation(SystemProcessInformation)` call that returns every
process on the system at once, aggregated by display name; and
`get_commit_limit_bytes()`, the system commit limit via `GetPerformanceInfo`,
used as the Memory window's Commit color-scale maximum. No Qt, no app state —
this module only answers what Windows currently reports.

## Connections

### Uses
- [Styles](../../__about/styles.md) — `get_process_display_name()` maps a raw
  image name to the aggregation key used in the returned dict

### Used by
- [Process Stats](process_stats.md) — imports the `CPU_IDX` / `THREADS_IDX` /
  `RSS_IDX` / `VMS_IDX` / `COUNT_IDX` layout constants to read the aggregated
  entries
- [Collector](collector.md) — calls `collect_processes_bulk()` once per tick
  and reads `PID_IDX` / `THREADS_IDX` / `VMS_IDX` / `COUNT_IDX`
- `app/settings.py` — `InitialSettings.commit_limit_bytes` calls
  `get_commit_limit_bytes()`
- `app/dialogs/mode_dialogs.py` — `MemorySettingsDialog` calls
  `get_commit_limit_bytes()` to size the Commit color scale

## Functions

### `collect_processes_bulk(need_cpu, need_mem, cpu_threads)`
Single kernel call collecting all process data at once — see
[flow](../__flow/system_query.md). Returns
`(aggregated: dict[str, list], total_cpu: float, total_rss: int, pid_to_name: dict[int, str])`.
`aggregated` maps display name to a plain list indexed by `CPU_IDX` (0),
`THREADS_IDX` (1), `RSS_IDX` (2), `VMS_IDX` (3), `COUNT_IDX` (4), `PID_IDX`
(5) — a list, not a dataclass, because this is the hot path: one tick builds
a few hundred of them. CPU deltas are computed against the previous call's
cached `UserTime`/`KernelTime` per PID (module-level `_prev_cpu_times`,
`_prev_collect_time`), so the module is stateful across calls by design.

### `get_commit_limit_bytes()`
System commit limit (RAM + all page files) in bytes via `GetPerformanceInfo`.
Returns `0` if the API reports failure (commit coloring disabled, a
documented fallback); falls back to physical RAM total if the ctypes call
itself raises `OSError`.
