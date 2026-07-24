# Main Window

**Script:** [main_window.py (script)](main_window.py)

---

## Purpose

The three monitor windows (CPU, Memory, Network). Each is a `Qt.Tool` window
— a desktop-gadget with no taskbar button and no Alt-Tab entry — built from a
shared `BaseMonitorWindow` using the template-method pattern: the base class
owns all UI construction, layout persistence, context-menu actions, and the
close/pause lifecycle; each mode subclass only supplies the small set of
hooks that differ (which collector to configure, which columns to fill,
which settings dialog to open).

---

## Connections

### Uses

- [Monitor](monitor.md) — `MonitorMode`, `MonitorData`, `NetworkMonitorData`, `SharedDataCollector`
- [Color Management](color_management.md) — `ProcessColorManager`
- [Persistence](persistence.md) — `get_base_path()` (window icon), `load_last_setup()`/`save_last_setup()` (window layout)
- [Settings Dialog](settings_dialog.md) — `InitialSettings`, `CPUSettings`, `MemorySettings`, `NetworkSettings`, `CPUSettingsDialog`, `MemorySettingsDialog`, `NetworkSettingsDialog`
- [Process Actions (script)](process_actions.py) — `find_processes`, `kill_processes`, `get_exe_path`, `open_file_location`, `get_current_priority`, `set_priority`
- [Process Dialog (script)](process_dialog.py) — `KillConfirmDialog`, `PriorityDialog`
- [Styles](styles.md) — `context_menu_style`, `Defaults`, `Dimensions`, `Fonts`, `FontScale`, `format_speed`, `format_bytes_total`
- [Theme](theme.md) — `theme()` for every stylesheet, `theme_manager().changed` to restyle on a flip
- [Icons](icons.md) — `IconButton` (header pause/play and settings), `swatch()` (context-menu company chip)
- [Day/Night Switch](theme_switch.md) — one switch per window header
- [Network Monitor](network_monitor.md) — `get_link_speed_mbps()` (via `NetworkWindow._resolve_max_bytes`)

### Used by

- `main.py` — creates `CPUWindow`/`MemoryWindow`/`NetworkWindow`, links CPU/Memory as refresh-rate peers, connects `aboutToQuit` to save visible windows' layouts
- [Tray Controller](tray.md) — calls `show_from_tray()` / `close()` on each window to toggle visibility
- `app/__init__.py` — re-exports `CPUWindow`, `MemoryWindow`, `NetworkWindow`, `BaseMonitorWindow`

---

## Classes

### TotalRowDelegate

`QStyledItemDelegate` that paints the Σ total row with a distinct background.
QSS-styled `QTableWidget`s ignore `QTableWidgetItem.setBackground()`, so this
delegate bypasses the style engine and paints directly — the only way to
color one specific row differently under a stylesheet. It reads the palette
at **paint time**, so a theme flip needs no delegate rebuild.

### DoubleClickSplitter / DoubleClickSplitterHandle

`QSplitter` whose handle resets to an equal 50/50 split on double-click.

### BaseMonitorWindow (QMainWindow)

Owns the whole window: header (controls, title, Day/Night switch, total),
HWiNFO sensor row, splitter with a current-processes table and a toggleable
history/rolling-average stack, context-menu process actions, theme restyling,
and window-layout persistence.

#### Header layout

```
[⏸/▶] [⚙]  CPU Monitor                          (Day/Night switch)
                                                     54.2% (3.38%)
              Temperature      Power       Electric
                 58.9°C        38.4 W       18.5 A
```

The two icon buttons replaced the old **menu bar** (owner 2026-07-24), which
carried nothing but Pause and Settings — each duplicated — while the title
bar's X already closes the window. Exit now lives only in the
[Tray Controller](tray.md)'s menu.

#### Hooks subclasses must implement

| Hook | Purpose |
|------|---------|
| `_get_mode()` / `_get_title()` / `_get_mode_cols()` / `_get_window_key()` | Identify the mode, window title, extra table columns (`"cpu"`/`"mem"`/`"net"`), and `last_setup.json` layout key. |
| `_has_total_row()` | Whether the current table has a Σ row (`True` for CPU/Memory, `False` for `NetworkWindow`). |
| `_configure_collector()` | Configure this mode on the shared `SharedDataCollector` (called once at startup and on every settings change; the mode stays enabled for the app's lifetime — hiding a window no longer disables it). |
| `_create_settings_dialog()` | Return this mode's settings dialog instance. |
| `_store_settings(new_settings)` | Store new settings; `NetworkWindow` overrides to also recompute max-speed color thresholds. |
| `_on_data_ready(data)` | Handle a `MonitorData`/`NetworkMonitorData` signal — fills tables and the header. |

#### Template methods (shared logic, not overridden)

| Method | Description |
|--------|-------------|
| `_show_settings()` | Opens the settings dialog; on accept, diffs old vs. new settings, applies them, re-applies fonts if changed, and syncs a visible peer window's refresh rate (CPU/Memory only — set up in `main.py`). |
| `_apply_settings(prev_settings)` | Reconfigures the collector; rebuilds tables only if row counts changed. |
| `_sync_refresh_rate(ms)` | Applies a refresh-rate change pushed from the peer window, without rebuilding tables. |
| `_rebuild_tables()` | Recreates the current/history/rolling tables after a row-count change, reapplying saved column widths. |
| `_hide_to_tray()` | Saves the window layout and hides the window. The shared collector keeps running (CPU/Memory come from one bulk syscall regardless of visibility), so peaks/history stay continuous. Called by the native title-bar X (`closeEvent`), `Esc`, the tray checkboxes, and the tray "Minimize". |
| `show_from_tray()` | Shows/raises/activates the window (its monitor never stopped). |
| `closeEvent(event)` | **Hides to the tray instead of exiting** (`_hide_to_tray()`); accepts the close only during OS session end (`isSavingSession()`) so logoff/shutdown isn't blocked. Real exit goes through `QApplication.quit()` — the tray menu's **Exit**. |
| `keyPressEvent(event)` | `Esc` → `_hide_to_tray()`; `Space` → `_toggle_pause()`. |
| `_save_window_layout()` / `_restore_window_layout()` | Persist/restore geometry, font size, splitter sizes, bottom-page toggle, and column widths via [Persistence](persistence.md). |
| `_on_context_menu(pos, table, has_total_row)` | Right-click menu: the signing **company name** (wrapped over as many rows as it needs, with the row's own color as a swatch), the PIDs, the exe name, then Kill Process, Open File Location, Set Priority. Any info line copies its value to the clipboard. Delegates to [Process Actions (script)](process_actions.py) and shows [Process Dialog (script)](process_dialog.py) confirmation dialogs. |
| `_apply_theme()` | (Re)styles every widget in the window from the active palette. Runs at startup and on every Day/Night flip. |
| `_style_table(table)` / `_header_css()` | Build one table's QSS and its header QSS from the active palette and font base. |
| `_toggle_pause()` | Flips the pause state and swaps the header button's glyph between pause and play. |

### CPUWindow / MemoryWindow / NetworkWindow (BaseMonitorWindow)

Implement the hooks above plus mode-specific column fillers
(`_fill_cpu_cols`/`_fill_memory_cols`/`_fill_net_cols` and their
`_history`/`_rolling` variants) and `_on_data_ready`.

`NetworkWindow` additionally has:

| Method | Description |
|--------|-------------|
| `_resolve_max_bytes(mbps)` (static) | Converts a max-speed setting to bytes/sec; `0` means "auto" — resolved via `get_link_speed_mbps()` from [Network Monitor](network_monitor.md) so color coding keeps working instead of silently turning off. |

---

## Design Decisions

**Gadget mode (`Qt.Tool`) with tray-driven visibility.** Setting
`Qt.WindowType.Tool` removes the taskbar button and Alt-Tab entry, matching
desktop-gadget behavior, while keeping the native title bar (so normal
move/resize and the X button work). Combined with
`app.setQuitOnLastWindowClosed(False)` in `main.py`, closing a window (its X or
`Esc`) only hides it — the [Tray Controller](tray.md) is the only way to bring
it back or to actually quit.

**Hiding a window does NOT pause its monitor.** CPU and Memory both come from a
single bulk `NtQuerySystemInformation` call per collector tick, so "pausing" a
hidden mode would save essentially nothing while breaking continuous
peak/history tracking. Windows just `hide()`/`show()`; the collector runs for
the app's whole lifetime and stops only at exit (`main.py`).

**One `_apply_theme()` owns every stylesheet.** Colors are never written at
widget-construction time and left there; the single restyle method is
connected to `theme_manager().changed`, so no widget can be left painted in
the theme that happened to be active when it was built.

**The header stylesheet is applied twice, on purpose.** `_apply_fonts()` sets
a stylesheet directly on each table's `QHeaderView` (it must restyle the
header font without rebuilding the table). A per-widget stylesheet wins over
the parent table's, so `_style_table()` refreshes the header's own sheet too —
otherwise a theme flip left the column headers in the old palette.

**All three sections share one surface color.** Current, Peak and Rolling used
to have three different tinted backgrounds; the same data in three colors read
as three unrelated kinds of table, so they now share `SECTION_BG`
(owner 2026-07-24).

**One unified `self._settings` attribute** (not separate per-field state)
holds the current `CPUSettings`/`MemorySettings`/`NetworkSettings` dataclass,
so `_show_settings()` can diff old vs. new as a single object comparison.

**CPU/Memory refresh-rate peering** (`_peer_window`, wired in `main.py`) syncs
one window's rate change to the other since both read from the same
`SharedDataCollector` tick. No visibility guard is needed — hidden peers keep
monitoring, so syncing their rate is always correct.
