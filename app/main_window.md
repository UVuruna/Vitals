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
- [Theme](theme.md) — `window_theme(key)` resolves this window's own `ThemeScope` (`self._theme`); every stylesheet reads `self._theme.palette`, and `self._theme.changed` triggers a restyle
- [Theme Transition](transition.md) — `flip_window_theme()` for the header switch's own-window-only flip
- [Icons](icons.md) — `IconButton` (header pause/play and settings), `swatch()` (context-menu company chip)
- [Day/Night Switch](theme_switch.md) — one switch per window header, flipping that window alone
- [Settings Dialog](settings_dialog.md) — `InitialSettings` for `_settings_from_initial()`
- [Network Monitor](network_monitor.md) — `get_link_speed_mbps()` (via `NetworkWindow._resolve_max_bytes`)

### Used by

- [Window Manager](window_manager.md) — creates the windows, links CPU/Memory as refresh-rate peers, pushes shared settings, drives the exit sequence
- [Tray Controller](tray.md) — calls `show_from_tray()` / `close()` on each window to toggle visibility
- `app/__init__.py` — re-exports `CPUWindow`, `MemoryWindow`, `NetworkWindow`, `BaseMonitorWindow`

---

## Classes

### TotalRowDelegate

`QStyledItemDelegate` that paints the Σ total row with a distinct background.
QSS-styled `QTableWidget`s ignore `QTableWidgetItem.setBackground()`, so this
delegate bypasses the style engine and paints directly — the only way to
color one specific row differently under a stylesheet. `TotalRowDelegate(table, scope)`
reads its owning window's `ThemeScope.palette` at **paint time**, so a theme
flip needs no delegate rebuild — and a table in the Memory window keeps
painting Memory's theme while CPU flips to the other.

### DoubleClickSplitter / DoubleClickSplitterHandle

`QSplitter` whose handle resets to an equal 50/50 split on double-click.

### BaseMonitorWindow (QMainWindow)

Owns the whole window: header (controls, title, Day/Night switch, total),
HWiNFO sensor row, splitter with a current-processes table and a toggleable
history/rolling-average stack, context-menu process actions, theme restyling,
and window-layout persistence.

Each window owns its own theme. At the top of `__init__`, `self._theme` is
resolved from `window_theme(self._get_window_key())` — the CPU, Memory and
Network windows each get their own independent `ThemeScope`, so the switch in
one header can never leak into the other two. Every stylesheet in the class
reads `self._theme.palette`, and the window connects `self._theme.changed`
to `_apply_theme()`.

#### Header layout

A control column on the left, the data column on the right:

```
[⏸/▶] [⚙]     CPU ......................... 54.2% (3.38%)
[ ~switch~ ]   Temperature     Power      Electric
                 58.9°C        38.4 W      18.5 A
```

**Title and Total always share one row** (owner 2026-07-24). The Day/Night
switch sits under the two icon buttons, level with the HWiNFO sensor row.
When there are no sensors to show, both columns are `AlignVCenter`, so the
two-row control block and the single title row centre against each other:

```
[⏸/▶] [⚙]
[ ~switch~ ]   CPU ......................... 40.5% (2.53%)
```

The icon buttons replaced the old **menu bar**, which carried nothing but
Pause and Settings — each duplicated — while the title bar's X already closes
the window. Exit now lives only in the [Tray Controller](tray.md)'s menu.

#### Hooks subclasses must implement

| Hook | Purpose |
|------|---------|
| `_get_mode()` / `_get_title()` / `_get_mode_cols()` / `_get_window_key()` | Identify the mode, window title, extra table columns (`"cpu"`/`"mem"`/`"net"`), and `last_setup.json` layout key. |
| `_has_total_row()` | Whether the current table has a Σ row (`True` for CPU/Memory, `False` for `NetworkWindow`). |
| `_configure_collector()` | Configure this mode on the shared `SharedDataCollector` (called once at startup and on every settings change; the mode stays enabled for the app's lifetime — hiding a window no longer disables it). |
| `_create_settings_dialog()` | Return this mode's settings dialog instance. |
| `_store_settings(new_settings)` | Store new settings; `NetworkWindow` overrides to also recompute max-speed color thresholds. |
| `_render_data(data)` | Draw one `MonitorData`/`NetworkMonitorData` tick into the tables and header. Called by `_on_data_ready` and again by `_apply_theme()`. |
| `_settings_from_initial(initial)` | Build this mode's settings dataclass out of the shared `InitialSettings`. Used by the constructor AND by the setup screen, so there is one definition per mode. |

#### Template methods (shared logic, not overridden)

| Method | Description |
|--------|-------------|
| `_on_data_ready(data)` | Collector signal handler: stores the tick as `_last_data` and renders it. Does neither while paused, so the display stays frozen. |
| `_adopt_settings(new)` | Apply a settings object — collector, tables, fonts. Returns the previous settings, or `None` if nothing changed. |
| `apply_shared_settings(initial)` | Adopt settings pushed from the shared setup screen via the [Window Manager](window_manager.md). |
| `_show_settings()` | Opens this window's settings dialog; on accept adopts the new settings and syncs a visible peer window's refresh rate (CPU/Memory only — paired by the window manager). |
| `_apply_settings(prev_settings)` | Reconfigures the collector; rebuilds tables only if row counts changed. |
| `_sync_refresh_rate(ms)` | Applies a refresh-rate change pushed from the peer window, without rebuilding tables. |
| `_rebuild_tables()` | Recreates the current/history/rolling tables after a row-count change, reapplying saved column widths. |
| `_hide_to_tray()` | Saves the window layout and hides the window. The shared collector keeps running (CPU/Memory come from one bulk syscall regardless of visibility), so peaks/history stay continuous. Called by the native title-bar X (`closeEvent`), `Esc`, the tray checkboxes, and the tray "Minimize". |
| `show_from_tray()` | Shows/raises/activates the window (its monitor never stopped). |
| `closeEvent(event)` | **Hides to the tray instead of exiting** (`_hide_to_tray()`); accepts the close only during OS session end (`isSavingSession()`) so logoff/shutdown isn't blocked. Real exit goes through `QApplication.quit()` — the tray menu's **Exit**. |
| `keyPressEvent(event)` | `Esc` → `_hide_to_tray()`; `Space` → `_toggle_pause()`. |
| `_save_window_layout()` / `_restore_window_layout()` | Persist/restore geometry, font size, splitter sizes, bottom-page toggle, and column widths via [Persistence](persistence.md). |
| `_on_context_menu(pos, table, has_total_row)` | Right-click menu: the signing **company name** (wrapped over as many rows as it needs, with the row's own color as a swatch), the PIDs, the exe name, then Kill Process, Open File Location, Set Priority. Any info line copies its value to the clipboard. Delegates to [Process Actions (script)](process_actions.py) and shows [Process Dialog (script)](process_dialog.py) confirmation dialogs. |
| `_flip_theme()` | Flips THIS window's theme via `flip_window_theme(self._theme, self)` — the header switch's action, covering this window alone. |
| `_apply_theme()` | (Re)styles every widget in the window from `self._theme.palette`. Runs at startup and on every flip of this window's own scope. |
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

**A theme flip re-renders the last tick.** Table CELL colors are per-item
brushes, not stylesheet properties, so restyling cannot reach them — they
used to be corrected only by the NEXT collector signal, which at a slow
refresh rate left the window visibly half-flipped (the owner reported exactly
this). `_apply_theme()` now re-runs `_render_data(self._last_data)`, so every
process and value color is recomputed in the new palette immediately. The
[Theme Transition](transition.md) cover then hides even that repaint.

**One `_apply_theme()` owns every stylesheet.** Colors are never written at
widget-construction time and left there; the single restyle method is
connected to `self._theme.changed` — this window's OWN scope, not a global
one — so no widget can be left painted in the theme that happened to be
active when it was built, and a flip of one window can never repaint another.

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

**CPU/Memory refresh-rate peering** (`_peer_window`, wired by the [Window Manager](window_manager.md)) syncs
one window's rate change to the other since both read from the same
`SharedDataCollector` tick. No visibility guard is needed — hidden peers keep
monitoring, so syncing their rate is always correct.
