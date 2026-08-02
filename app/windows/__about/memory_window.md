# Memory Window

**Script:** [Memory Window (script)](../memory_window.py)

## Purpose

`MemoryWindow` is the Memory monitor gadget. Everything shared with the other
two modes lives in [Base Window](base_window.md); this file is only what
Memory mode does differently: it listens on `memory_data_ready`, adds the
Commit column, shows Committed / DRAM Read / DRAM Write from HWiNFO, and
colors two INDEPENDENT scales — working set (`item.value`) against total RAM,
commit (`item.vms`) against the system commit limit.

## Connections

### Uses

- [Base Window](base_window.md) — `BaseMonitorWindow`, the parent class
- [Collect (subfolder)](../../collect/___collect.md) — `SharedDataCollector` (`collector.py`), `MonitorData`/`MonitorMode` (`monitor_data.py`)
- [Dialogs (subfolder)](../../dialogs/___dialogs.md) — `MemorySettingsDialog` (`mode_dialogs.py`)
- [Settings](../../__about/settings.md) — `MemorySettings`, `InitialSettings`

### Used by

- [Window Manager](../../__about/window_manager.md) — creates the Memory window on demand and holds it
- [Package Exports (script)](../../__init__.py) — re-exports `MemoryWindow`

## Classes

### MemoryWindow (BaseMonitorWindow)

Implements the template hooks: `_get_mode()` → `MonitorMode.MEMORY`,
`_get_title()` → `"Memory"`, `_get_mode_cols()` → `"mem"`,
`_get_window_key()` → `"memory"`, `_configure_collector()` →
`collector.configure_memory(...)`, `_create_settings_dialog()` →
`MemorySettingsDialog`, `_settings_from_initial()` → builds a
`MemorySettings`.

Carries its own `_commit_limit_bytes` (from `InitialSettings`, not the shared
per-mode settings) used to color the Commit column.

Mode-specific column fillers: `_fill_memory_cols()` (Usage colored against
`ram_bytes`, Commit colored against `_commit_limit_bytes`),
`_fill_memory_history_cols()` (adds Time), `_fill_memory_rolling_cols()`
(adds Uptime, muted once it reaches the retention window). `_render_data()`
fills the Committed/Read/Write sensor row from `data.hwinfo`, then the
current table's Σ row (both Usage and Commit totals colored against their own
scale), the history table and the dynamically-sized rolling table.
