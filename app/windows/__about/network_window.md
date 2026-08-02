# Network Window

**Script:** [Network Window (script)](../network_window.py)

## Purpose

`NetworkWindow` is the Network monitor gadget. Everything shared with the
other two modes lives in [Base Window](base_window.md); this file is only
what Network mode does differently: it listens on `network_data_ready`,
replaces Usage with Download + Upload, has NO Σ total row (a sum of speeds is
not a meaningful "total" — `_has_total_row()` returns `False`), puts the
current upload speed and both cumulative totals in the sensor row, and colors
each direction against its own configured (or auto-detected) max speed.

It is also the only window that can be told its data source is unavailable:
when a tick carries a `TraceFailure`, [Status Banner](status_banner.md) goes
up and every table is EMPTIED — leaving the last live rows next to a failure
notice would read as "these are current", which they are not.

## Connections

### Uses

- [Base Window](base_window.md) — `BaseMonitorWindow`, the parent class; `show_status()` for the `TraceFailure` banner
- [Status Banner](status_banner.md) — raised via `self.show_status(data.error)` / cleared via `self.show_status(None)`
- [Collect (subfolder)](../../collect/___collect.md) — `SharedDataCollector` (`collector.py`), `MonitorMode`/`NetworkMonitorData` (`monitor_data.py`), `get_link_speed_mbps()` (`network_trace.py`, resolves "auto" max speed)
- [Dialogs (subfolder)](../../dialogs/___dialogs.md) — `NetworkSettingsDialog` (`mode_dialogs.py`)
- [Settings](../../__about/settings.md) — `NetworkSettings`, `InitialSettings`
- [Styles](../../__about/styles.md) — `format_speed()`, `format_bytes_total()`

### Used by

- [Window Manager](../../__about/window_manager.md) — creates the Network window on demand and holds it
- [Package Exports (script)](../../__init__.py) — re-exports `NetworkWindow`

## Classes

### NetworkWindow (BaseMonitorWindow)

Implements the template hooks: `_get_mode()` → `MonitorMode.NETWORK`,
`_get_title()` → `"Network"`, `_get_mode_cols()` → `"net"`,
`_get_window_key()` → `"network"`, `_has_total_row()` → `False`,
`_configure_collector()` → `collector.configure_network(...)`,
`_create_settings_dialog()` → `NetworkSettingsDialog`,
`_settings_from_initial()` → builds a `NetworkSettings`.

Overrides `_store_settings()` to also recompute `_max_dl_bytes`/
`_max_ul_bytes` whenever settings change, via the static
`_resolve_max_bytes(mbps)`: a `0` setting means "auto" and is resolved
through `get_link_speed_mbps()` so color coding keeps working instead of
silently turning off.

Mode-specific column fillers: `_fill_net_cols()` (Download/Upload, each
colored against its own max-bytes scale), `_fill_net_history_cols()` (adds
Time), `_fill_net_rolling_cols()` (adds Uptime, muted once it reaches the
retention window). `_render_data()` first checks `data.error`: on a
`TraceFailure` it raises the status banner and blanks the header and every
table cell, and returns; otherwise it clears the banner, sets the header's big
number to the current download speed, fills the Upload/Total↓/Total↑ sensor
row, and fills the current (no Σ row), history and rolling tables.
