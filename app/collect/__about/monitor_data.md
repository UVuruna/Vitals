# Monitor Data

**Script:** [Monitor Data (script)](../monitor_data.py)

## Purpose

The records the collector emits — the contract between the data layer and
the windows. Keeping every dataclass and the `MonitorMode` enum in one module
means a window can import the SHAPE of its tick without importing the
collector that produced it, and the collector can be read without hunting
for what its signals carry.

## Connections

### Uses
- [HWiNFO Reader](hwinfo.md) — `HWiNFOData`, the type of `MonitorData.hwinfo`
- [Network Trace](network_trace.md) — `TraceFailure`, the type of
  `NetworkMonitorData.error`

### Used by
- [Process Stats](process_stats.md) — `HistoryRecord`, `MonitorMode`,
  `MonitorStats`, `ProcessInfo`
- [Network Stats](network_stats.md) — `NetworkHistoryRecord`,
  `NetworkProcessInfo`
- [Collector](collector.md) — builds and emits `MonitorData` /
  `NetworkMonitorData` each tick
- `app/__init__.py` — re-exports `MonitorMode`
- [Windows (subfolder)](../../windows/___windows.md) — `base_window.py`,
  `cpu_window.py`, `memory_window.py` and `network_window.py` all import
  `MonitorMode` and either `MonitorData` or `NetworkMonitorData` to type
  their `_render_data()` / tick handlers

## Classes

### `MonitorMode` (Enum)
`CPU`, `MEMORY`, `NETWORK`, `BOTH` — `BOTH` is a launch-dialog convenience
value (opens both CPU and Memory windows); the collector itself never reads
it.

### `ProcessInfo` / `HistoryRecord` / `MonitorStats` / `MonitorData`
Per-process snapshot, peak-history record, running totals, and the bundle
`SharedDataCollector` emits on `cpu_data_ready` / `memory_data_ready`.
`ProcessInfo.value` is CPU % or memory bytes depending on mode;
`uptime_seconds` is populated only in rolling-average rows.

### `NetworkProcessInfo` / `NetworkHistoryRecord` / `NetworkMonitorData`
Network equivalents — `download` / `upload` bytes/sec instead of a single
`value`. `NetworkMonitorData.error` is an `Optional[TraceFailure]`, set
whenever the ETW tracer is unavailable (never started, or died mid-session);
the Network window's status banner reads `.reason` / `.action` from it
instead of showing zeros.
