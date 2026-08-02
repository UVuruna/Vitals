# windows/

The three gadget windows (CPU, Memory, Network) and everything they are built
from. Each window is a taskbar-less `Qt.Tool` built from the shared
`BaseMonitorWindow` template-method base; the rest of this folder is what that
template delegates to instead of owning itself — screen placement, Windows
shell integration, the process-table widgets and factory, the status banner,
layout persistence, and the right-click process menu.

## Files

| File | Tier | One line |
|------|------|----------|
| `base_window.py` | Algorithmic | the monitor-window template — shell, layout, theme scope, settings round-trip, tick orchestration — [about](__about/base_window.md) · [flow](__flow/base_window.md) |
| `cpu_window.py` | Standard | CPU mode's columns, HWiNFO sensors and usage-vs-thread-count coloring — [about](__about/cpu_window.md) |
| `memory_window.py` | Standard | Memory mode's columns and two independent color scales (working set vs commit) — [about](__about/memory_window.md) |
| `network_window.py` | Standard | Network mode's columns, no Σ row, and the status banner for trace failures — [about](__about/network_window.md) |
| `placement.py` | Algorithmic | the only module that reasons in FRAME coordinates — the clamp that keeps a caption reachable — [about](__about/placement.md) · [flow](__flow/placement.md) |
| `shell.py` | Standard | elevated relaunch and the per-window taskbar icon (ctypes/COM) — [about](__about/shell.md) |
| `table_widgets.py` | Standard | the Σ-row delegate, the values-not-title auto-fit header, the 50/50 splitter — [about](__about/table_widgets.md) |
| `table_factory.py` | Standard | builds and (re)styles one process table from a mode's column set — [about](__about/table_factory.md) |
| `status_banner.py` | Standard | the hidden-by-default failure notice with one remedy button — [about](__about/status_banner.md) |
| `layout_store.py` | Standard | one window's slot in `last_setup.json` — geometry, splitter, column widths — [about](__about/layout_store.md) |
| `process_menu.py` | Standard | the right-click info+actions menu, resolved against LIVE processes — [about](__about/process_menu.md) |
| `__init__.py` | Trivial | package docstring only |

## Connections

### Uses

- [Collect (subfolder)](../collect/___collect.md) — `MonitorData`, `MonitorMode`, `NetworkMonitorData`, `SharedDataCollector`, `TraceFailure`/`NEEDS_ADMIN`, `get_link_speed_mbps()` — the tick contract and the shared collector every window drives
- [Dialogs (subfolder)](../dialogs/___dialogs.md) — the per-mode settings dialogs (`CPUSettingsDialog`, `MemorySettingsDialog`, `NetworkSettingsDialog`) and the kill/priority confirmation dialogs opened from the process menu
- [Theme](../__about/theme.md) — `window_theme()` resolves each window's own `ThemeScope`; every stylesheet reads `scope.palette`
- [Theme Switch](../__about/theme_switch.md) — the header's Day/Night switch
- [Theme Transition](../__about/transition.md) — the covered flip that hides one window's repaint
- [Styles](../__about/styles.md) — dimensions, fonts, defaults and formatters used throughout the folder
- [Icons](../__about/icons.md) — the header's pause/settings icon buttons and the process-menu company swatch
- [Color Management](../__about/color_management.md) — per-process name colors and per-value threshold colors
- [Persistence](../__about/persistence.md) — `last_setup.json` access and the base path for `assets/`
- [Settings](../__about/settings.md) — `InitialSettings` and the per-mode settings dataclasses
- [Process Actions](../__about/process_actions.md) — the live kill/priority/open-location operations behind the process menu
- [App (folder)](../___app.md) — the parent package

### Used by

- [Window Manager](../__about/window_manager.md) — creates the CPU/Memory/Network windows on demand, wires CPU+Memory as refresh-rate peers, pushes shared settings into every open window, and calls `place_on_screen()`/`target_screen()` directly for window cascading and the tray's "Reset window positions"
- [Package Exports (script)](../__init__.py) — re-exports `BaseMonitorWindow`, `CPUWindow`, `MemoryWindow`, `NetworkWindow` as the app package's public API

The Tray Controller and `main.py` never import this folder directly — both
reach the windows only through the Window Manager, which is the one place
that is allowed to know all three exist.

## Design Decisions

- **Gadget mode, tray-only quit.** Every window sets `Qt.WindowType.Tool` — no
  taskbar button, no Alt-Tab entry. Its native title-bar X and `Esc` only hide
  it; the tray icon's Exit is the sole path to `QApplication.quit()`.
- **Theme is per window, never global.** Each window resolves its own
  `ThemeScope` via `window_theme(self._get_window_key())` before building any
  widget. Nothing in this folder may reach for an app-wide theme — a switch
  flip in one window's header must never repaint the other two.
- **Template-method split.** `BaseMonitorWindow` owns everything three modes
  share (shell, layout, settings round-trip, tick orchestration); each mode
  subclass supplies only what differs (the collector signal, the extra
  columns, one `_render_data()`).
- **Frame vs client is a hard module boundary.** `placement.py` is the only
  code that reasons in FRAME coordinates (what the OS caption and borders
  occupy); `layout_store.py` saves and restores CLIENT coordinates and
  deliberately never judges whether a saved position is usable — that
  judgment belongs to `placement.py` alone.
- **Table building is split from table styling.** `table_factory.create_table()`
  is the only place that assembles a table's columns; `style_table()`/
  `header_css()` are separate functions so a theme flip can restyle a LIVE
  table without rebuilding it.
- **`NetworkWindow` is the outlier.** A sum of speeds is not a meaningful
  total, so it is the only window with no Σ row (`_has_total_row()` returns
  `False`); it is also the only window that can raise the status banner, since
  it is the only mode whose data source (the ETW trace) can fail mid-run.
