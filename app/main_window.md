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
- [Styles](styles.md) — `CONTEXT_MENU_STYLE`, `Colors`, `Defaults`, `Fonts`, `FontScale`, `format_speed`, `format_bytes_total`
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
color one specific row differently under a stylesheet.

### DoubleClickSplitter / DoubleClickSplitterHandle

`QSplitter` whose handle resets to an equal 50/50 split on double-click.

### BaseMonitorWindow (QMainWindow)

Owns the whole window: header, HWiNFO sensor row, splitter with a
current-processes table and a toggleable history/rolling-average stack, menu
bar, context-menu process actions, and window-layout persistence.

#### Hooks subclasses must implement

| Hook | Purpose |
|------|---------|
| `_get_mode()` / `_get_title()` / `_get_mode_cols()` / `_get_window_key()` | Identify the mode, window title, extra table columns (`"cpu"`/`"mem"`/`"net"`), and `last_setup.json` layout key. |
| `_has_total_row()` | Whether the current table has a Σ row (`True` for CPU/Memory, `False` for `NetworkWindow`). |
| `_configure_collector()` / `_disable_collector()` | Enable/disable this mode on the shared `SharedDataCollector`. |
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
| `_set_monitor_enabled(enabled)` | Resumes (`_apply_settings`) or pauses (`_disable_collector`) this mode's collection — driven by window show/hide. |
| `show_from_tray()` | Resumes the monitor, restarts the collector thread if it had fully stopped, and shows/raises/activates the window. |
| `closeEvent(event)` | **Hides to the tray instead of exiting** and pauses the monitor (`_set_monitor_enabled(False)`); accepts the close only during OS session end (`isSavingSession()`) so logoff/shutdown isn't blocked. Real exit goes through `QApplication.quit()` (File > Exit or the tray menu). |
| `keyPressEvent(event)` | `Esc` → `close()` (hide + pause); `Space` → `_toggle_pause()`. |
| `_save_window_layout()` / `_restore_window_layout()` | Persist/restore geometry, font size, splitter sizes, bottom-page toggle, and column widths via [Persistence](persistence.md). |
| `_on_context_menu(pos, table, has_total_row)` | Right-click menu: copy PIDs/exe path, Kill Process, Open File Location, Set Priority — delegates to [Process Actions (script)](process_actions.py) and shows [Process Dialog (script)](process_dialog.py) confirmation dialogs. |

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
desktop-gadget behavior. Combined with `app.setQuitOnLastWindowClosed(False)`
in `main.py`, closing a window (via the X button or `Esc`) only calls
`hide()` — the [Tray Controller](tray.md) is the only way to bring it back
or to actually quit.

**Closing a window pauses its monitor.** `closeEvent()` calls
`_set_monitor_enabled(False)`, which disables collection for that mode on
the shared collector. A hidden window would otherwise keep consuming CPU
cycles for data nobody can see; `show_from_tray()` resumes it.

**One unified `self._settings` attribute** (not separate per-field state)
holds the current `CPUSettings`/`MemorySettings`/`NetworkSettings` dataclass,
so `_show_settings()` can diff old vs. new as a single object comparison.

**CPU/Memory refresh-rate peering** (`_peer_window`, wired in `main.py`) syncs
one window's rate change to the other since both read from the same
`SharedDataCollector` tick — but only if the peer is currently visible,
since a hidden window's monitor is disabled and reconfiguring it would
re-enable collection for nothing.
