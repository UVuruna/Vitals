# Collector

**Script:** [Collector (script)](../collector.py) ·
**Flow:** [diagram](../__flow/collector.md)

## Purpose

`SharedDataCollector` is a `QThread` singleton — the single background
thread that feeds every open monitor window. One tick makes ONE bulk process
query and, when network mode is enabled, ONE ETW snapshot, feeds the
per-mode statistics objects, and emits a signal per enabled mode — so three
open windows cost exactly what one costs. It also owns the ETW tracer's
lifecycle, including the failure paths: a trace that never started and a
consumer thread that died after a good start both end up as a structured
`TraceFailure` in the Network window's banner rather than as a plausible,
permanent zero. See [flow](../__flow/collector.md) for one tick's path
through the loop.

## Connections

### Uses
- `app/color_management.py` — `ProcessColorManager` (company lookup runs
  inside the collector loop, `../../__about/color_management.md`)
- `app/styles.py` — `Defaults` (`../../__about/styles.md`)
- [HWiNFO Reader](hwinfo.md) — `HWiNFOData` for the no-CPU-monitor fallback
- [Monitor Data](monitor_data.md) — `MonitorData`, `MonitorMode`,
  `NetworkMonitorData`, `ProcessInfo`
- [Network Stats](network_stats.md) — `NetworkMonitor`
- [Network Trace](network_trace.md) — `NetworkTracer` (lazy import),
  `CONSUMER_DIED`, `START_FAILED`, `TraceFailure`
- [Process Stats](process_stats.md) — `ProcessMonitor`
- [System Query](system_query.md) — `COUNT_IDX`, `PID_IDX`, `THREADS_IDX`,
  `VMS_IDX`, `collect_processes_bulk()`

### Used by
- `main.py` — creates the one `SharedDataCollector()`, starts it, stops it
  and resets the singleton at shutdown
- `app/window_manager.py` — holds the collector instance and passes it to
  each monitor window it creates
- `app/__init__.py` — re-exports `SharedDataCollector`
- [Windows (subfolder)](../../windows/___windows.md) — `cpu_window.py`,
  `memory_window.py` and `network_window.py` each call
  `configure_cpu()` / `configure_memory()` / `configure_network()` and
  connect to the matching `*_data_ready` signal

## Classes

### `SharedDataCollector` (QThread singleton)
One background thread collects for all enabled modes and emits to every
subscriber.

Signals: `cpu_data_ready(MonitorData)`, `memory_data_ready(MonitorData)`,
`network_data_ready(NetworkMonitorData)`.

- `configure_cpu(...)` / `configure_memory(...)` / `configure_network(...)` —
  called by the owning window at startup and whenever settings change;
  lazily creates the mode's `ProcessMonitor` / `NetworkMonitor` and (for
  network) starts the `NetworkTracer`. A configured mode stays enabled for
  the app's lifetime — hiding a window does not disable it, since CPU/Memory
  already share one bulk syscall and pausing saves nothing.
- `run()` — the tick loop; see [flow](../__flow/collector.md)
- `stop()` — signals the loop to exit, stops the tracer if running, joins
  the thread (2s timeout)
- `cpu_monitor` / `memory_monitor` / `network_monitor` (properties) —
  access the underlying per-mode monitor instances
- `reset_instance()` (classmethod) — stops and clears the singleton, used
  at app shutdown
