# Base Window

**Script:** [Base Window (script)](../base_window.py) ·
**Flow:** [diagram](../__flow/base_window.md)

## Purpose

`BaseMonitorWindow` is the template every monitor window is built from. Its
one responsibility is to BE a monitor gadget: it owns the window shell
(`Qt.Tool`, hide-to-tray, keys, focus), the header/banner/splitter layout,
this window's own theme scope, the settings round-trip, and the orchestration
of one collector tick into three tables. Everything it does NOT own it
delegates to a sibling module — placement, shell integration, the table
factory, table widgets, the status banner, layout persistence and the process
menu. Subclasses ([CPU Window](cpu_window.md), [Memory Window](memory_window.md),
[Network Window](network_window.md)) fill in only what differs per mode: the
collector signal to listen on, which columns exist, and how one tick renders.

Every window owns its own `ThemeScope` (owner 2026-07-26): the Day/Night
switch in its header flips THIS window alone, and every color it paints —
chrome, table QSS, per-cell brushes — is read from `self._theme.palette`.
Nothing here may reach for an app-wide theme, or a flip would leak into the
other two gadgets.

## Connections

### Uses

- [Placement](placement.md) — `place_on_screen()`, called from `showEvent()` on every show
- [Shell](shell.md) — `relaunch_elevated()` (the status banner's NEEDS_ADMIN remedy), `set_native_taskbar_icon()` (once per window, from `showEvent()`)
- [Status Banner](status_banner.md) — `StatusBanner`, built in `_setup_ui()` and driven by `show_status()`
- [Table Factory](table_factory.md) — `create_table()`, `header_css()`, `style_table()`
- [Table Widgets](table_widgets.md) — `DoubleClickSplitter` (the current/history splitter), `TotalRowDelegate.ROLE` (marking Σ-row items)
- [Layout Store](layout_store.md) — `_save_window_layout()`/`_restore_window_layout()` delegate straight to `layout_store.save()`/`.restore()`
- [Process Menu](process_menu.md) — `_connect_table_selection()` wires every table's context menu to `process_menu.show_process_menu()`
- [Theme](../../__about/theme.md) — `window_theme(key)` resolves `self._theme`
- [Theme Switch](../../__about/theme_switch.md) — `DayNightSwitch` in the header
- [Theme Transition](../../__about/transition.md) — `flip_window_theme()` for `_flip_theme()`
- [Icons](../../__about/icons.md) — `IconButton` (pause/settings), the `icons` module (pause/play glyphs)
- [Color Management](../../__about/color_management.md) — `ProcessColorManager`, instantiated per render in `_fill_process_rows()`
- [Persistence](../../__about/persistence.md) — `get_base_path()` for the window icon
- [Settings](../../__about/settings.md) — `InitialSettings`
- [Styles](../../__about/styles.md) — `Defaults`, `Dimensions`, `FontScale`, `scaled_font`
- [Collect (subfolder)](../../collect/___collect.md) — `MonitorData`, `MonitorMode` (`monitor_data.py`), `NEEDS_ADMIN` (`network_trace.py`)

### Used by

- [CPU Window](cpu_window.md), [Memory Window](memory_window.md), [Network Window](network_window.md) — the three subclasses
- [Window Manager](../../__about/window_manager.md) — via each subclass, holds `BaseMonitorWindow` references and calls its shared lifecycle methods (`show_from_tray()`, `_hide_to_tray()`, `apply_shared_settings()`, `_save_window_layout()`)

## Classes

### BaseMonitorWindow (QMainWindow)

The template-method base. Not instantiated directly.

**State:** `_theme` (this window's `ThemeScope`), `is_paused`, `_last_data`
(the most recent tick, kept so a theme flip can re-render it immediately),
`_peer_window` (CPU/Memory refresh-rate peer, wired by the Window Manager),
`_bottom_page` (0 = Peak Usage, 1 = Rolling Average), `temp_config` (trip
points loaded from `config/config.json`, colors always come from the palette).

**Hooks every subclass must implement:** `_get_mode()`, `_get_title()`,
`_get_mode_cols()`, `_get_window_key()`, `_configure_collector()`,
`_create_settings_dialog()`, `_settings_from_initial(initial)`,
`_render_data(data)`. Optional overrides: `_has_total_row()` (default
`True`; `NetworkWindow` returns `False`), `_store_settings(new_settings)`
(default just assigns; `NetworkWindow` also recomputes max-speed thresholds).

**Shared template methods (not overridden):**
- `showEvent()` — sets the native icon once, restores the saved layout once,
  and always re-clamps via `place_on_screen()` (screens can change while the
  window is hidden in the tray).
- `_hide_to_tray()` / `show_from_tray()` / `closeEvent()` — the hide-not-quit
  lifecycle; the collector keeps running while hidden.
- `keyPressEvent()` — `Esc` closes (hides), `Space` toggles pause.
- `_adopt_settings()` / `apply_shared_settings()` / `_show_settings()` /
  `_sync_refresh_rate()` / `_apply_settings()` — the settings round-trip:
  diff old vs. new, reconfigure the collector, rebuild tables only if row
  counts changed, and sync a CPU/Memory peer's refresh rate.
- `_flip_theme()` / `_apply_theme()` — this window's own theme flip; see
  [flow](../__flow/base_window.md).
- `_setup_ui()` — builds the header (control column + data column), the
  hidden status banner, and the splitter; see the layout sketch in the
  [flow doc](../__flow/base_window.md).
- `show_status()` / `_on_status_action()` — raises/hides the status banner
  and dispatches its remedy button by the failure's CODE (relaunch elevated
  for `NEEDS_ADMIN`, otherwise re-run `_configure_collector()`).
- `_create_table()` / `_make_total_item()` / `_fill_process_rows()` /
  `_rebuild_tables()` / `_connect_table_selection()` / `_on_cell_clicked()` /
  `eventFilter()` / `_on_app_state_changed()` — table plumbing shared by all
  three tables in all three modes.
- `_show_bottom_page()` / `_toggle_bottom_table()` / `_toggle_pause()` /
  `_on_data_ready()` — the tick path; see [flow](../__flow/base_window.md).

### Why this file stays whole

At 886 lines `base_window.py` sits in the Structure Law's smell band
(~500–1,000), which requires answering in writing whether it holds more than
one responsibility. It does not: it is ONE class with ONE responsibility —
the monitor-window template (shell + layout + settings round-trip + tick
orchestration). Every separable concern already lives in a sibling module in
this folder — placement, shell integration, the table factory and table
widgets, the status banner, layout persistence, the process menu — leaving
only the QMainWindow subclass's own construction and lifecycle code. Splitting
further would mean breaking one cohesive class into mixins, which fragments a
single responsibility across files instead of separating two different ones —
exactly the outcome Rule #20 warns against.
