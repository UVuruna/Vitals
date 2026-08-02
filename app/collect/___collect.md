# collect/

The data-acquisition layer. Everything that produces monitor data lives
here: raw Windows kernel queries (bulk process snapshot, HWiNFO sensors, the
ETW network trace) at the bottom, per-mode statistics (CPU/Memory history and
rolling averages, network rates and peaks) on top, and one `QThread`
collector that ticks them all once per interval and emits to whichever
windows are open. Nothing in this folder imports a Qt widget or knows a
theme exists — it answers "what is the system doing right now", nothing
about how that gets drawn.

## Files

| File | Tier | One line |
|------|------|----------|
| `system_query.py` | Algorithmic | bulk `NtQuerySystemInformation` process snapshot + commit limit — [about](__about/system_query.md) · [flow](__flow/system_query.md) |
| `hwinfo.py` | Standard | HWiNFO shared-memory sensor reader — [about](__about/hwinfo.md) |
| `rolling_window.py` | Algorithmic | shared rolling-average accumulator/bucket engine — [about](__about/rolling_window.md) · [flow](__flow/rolling_window.md) |
| `monitor_data.py` | Standard | the collector's emitted record shapes — [about](__about/monitor_data.md) |
| `process_stats.py` | Algorithmic | per-mode CPU/Memory statistics — [about](__about/process_stats.md) · [flow](__flow/process_stats.md) |
| `network_stats.py` | Standard | per-process network rate statistics — [about](__about/network_stats.md) |
| `network_trace.py` | Algorithmic | ETW kernel trace for per-process network bytes — [about](__about/network_trace.md) · [flow](__flow/network_trace.md) |
| `collector.py` | Algorithmic | the `QThread` that ticks and emits — [about](__about/collector.md) · [flow](__flow/collector.md) |
| `__init__.py` | Trivial | package docstring only |

## Connections

### Uses
- [Styles](../__about/styles.md) — `Defaults`, `MEMORY_UNITS`, `format_pct()`,
  `format_speed()`, `get_process_display_name()`: the non-color config home
  for every tunable value this layer reads
- [Color Management](../__about/color_management.md) — `ProcessColorManager`;
  company lookup runs inside the collector loop, once per aggregated process
  per tick
- `app/persistence.py` — `get_data_dir()` resolves the opt-in ETW debug log
  path (`../__about/persistence.md`)
- `psutil`, Windows APIs via `ctypes` (`ntdll`, `psapi`, `advapi32`,
  `kernel32`) — external, not project docs

### Used by
- [App (folder)](../___app.md) — `app/__init__.py` re-exports
  `SharedDataCollector`, `MonitorMode`, `ProcessMonitor`
- [Windows (subfolder)](../windows/___windows.md) — every monitor window
  configures the collector for its mode and renders what it emits;
  `base_window.py` and `status_banner.py` read `NEEDS_ADMIN` to choose the
  Network status banner's remedy
- [Dialogs (subfolder)](../dialogs/___dialogs.md) — `setup_dialog.py` and
  `mode_dialogs.py` read `get_commit_limit_bytes()` / `get_link_speed_mbps()`
  for default values and color-scale sizing
- `app/settings.py` — `InitialSettings.commit_limit_bytes` calls
  `get_commit_limit_bytes()`
- `app/window_manager.py` — holds the one collector instance and hands it to
  each window it creates
- `main.py` — creates the singleton collector, starts it, stops it and
  resets it at shutdown

## Design Decisions

**One bulk kernel call, not per-process `psutil` calls.**
`collect_processes_bulk()` replaces ~300 per-process
`NtQueryInformationProcess` kernel transitions with one system-wide
`NtQuerySystemInformation` call, cutting the collector's CPU usage roughly
10–20×. This is why the hot path goes through raw `ctypes` in
[System Query](__about/system_query.md) instead of `psutil.process_iter()` —
`psutil` is still used elsewhere in this layer for one-shot, non-per-process
facts (`cpu_count()`, `virtual_memory()`, `net_if_stats()`) where the bulk
call buys nothing.

**No Qt-widget or theme knowledge.** `collector.py` uses Qt's threading
primitives (`QThread`, `Signal`, `QMutex`) because that IS the concurrency
model the app is built on, but nothing here imports a widget, a palette, or
a `ThemeScope`. The layer's output (`MonitorData`, `NetworkMonitorData`) is
plain dataclasses — a window decides how to render them, this folder only
decides what they contain. That separation is what lets the data layer be
read and reasoned about without dragging in the GUI.

**The ETW tracer is separated from the network statistics.**
`network_trace.py` owns the kernel session and produces raw
`{pid: (bytes_recv, bytes_sent)}` counters; `network_stats.py` turns those
into rates, peaks and rolling averages. The same split exists for CPU/Memory
(`system_query.py` raw vs. `process_stats.py` processed) — a raw source that
can fail in OS-specific ways stays isolated from the statistics logic that
has nothing to do with ETW at all.

**Failures are structured `TraceFailure` values, never message strings.**
A bare error string forces the UI to either show developer text or
string-match on it to pick a remedy. `TraceFailure.code` lets the Network
window choose the right action directly — relaunching elevated cannot fix
`OTHER_INSTANCE`, and retrying can never fix `NEEDS_ADMIN` — while `reason`
and `action` are the two lines the status banner actually shows.
