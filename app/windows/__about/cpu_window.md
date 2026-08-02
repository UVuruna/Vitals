# CPU Window

**Script:** [CPU Window (script)](../cpu_window.py)

## Purpose

`CPUWindow` is the CPU monitor gadget. Everything shared with the other two
modes lives in [Base Window](base_window.md); this file is only what CPU mode
does differently: it listens on `cpu_data_ready`, adds the Parallel and
Threads columns, shows Temperature / Power / Electric from HWiNFO in the
sensor row, and colors usage against `cpu_threads * 100` — a 16-thread
machine tops out at 1600% aggregate usage, not 100%.

## Connections

### Uses

- [Base Window](base_window.md) — `BaseMonitorWindow`, the parent class
- [Collect (subfolder)](../../collect/___collect.md) — `SharedDataCollector` (`collector.py`), `MonitorData`/`MonitorMode` (`monitor_data.py`)
- [Dialogs (subfolder)](../../dialogs/___dialogs.md) — `CPUSettingsDialog` (`mode_dialogs.py`)
- [Settings](../../__about/settings.md) — `CPUSettings`, `InitialSettings`

### Used by

- [Window Manager](../../__about/window_manager.md) — creates the CPU window on demand and holds it
- [Package Exports (script)](../../__init__.py) — re-exports `CPUWindow`

## Classes

### CPUWindow (BaseMonitorWindow)

Implements the template hooks: `_get_mode()` → `MonitorMode.CPU`,
`_get_title()` → `"CPU"`, `_get_mode_cols()` → `"cpu"`, `_get_window_key()` →
`"cpu"`, `_configure_collector()` → `collector.configure_cpu(...)`,
`_create_settings_dialog()` → `CPUSettingsDialog`, `_settings_from_initial()`
→ builds a `CPUSettings`.

Mode-specific column fillers: `_fill_cpu_cols()` (Usage colored against
`cpu_threads * 100`, Count, Threads), `_fill_cpu_history_cols()` (adds Time),
`_fill_cpu_rolling_cols()` (adds Uptime, muted once it reaches the retention
window). `_render_data()` fills the Temperature/Power/Electric sensor row
from `data.hwinfo`, then the current table's Σ row, the history table and the
dynamically-sized rolling table.
