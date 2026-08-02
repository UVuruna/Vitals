# Window Manager

**Script:** [Window Manager (script)](../window_manager.py)

## Purpose

Owns the three monitor windows as one group. Which monitors exist used to
be decided once, in `main.py`, from the setup screen's checkboxes — so
turning a monitor on later meant restarting the app. This module makes that
a runtime decision: it creates each window the first time it is actually
needed, shows and hides them, pushes one set of settings into all of them,
and keeps the CPU/Memory refresh-rate peering wired. A window is never
destroyed once created — hiding is enough, and its monitor keeps running so
peaks and history stay continuous.

## Connections

### Uses
- [Persistence](persistence.md) — `load_last_setup()` / `save_last_setup()`, to check for a remembered window position and to drop x/y on reset
- [Settings](settings.md) — `InitialSettings`, the one settings object all three modes read themselves out of
- [Styles](styles.md) — `Dimensions.WINDOW_GAP`, the cascade spacing between newly created windows
- [Collect (subfolder)](../collect/___collect.md) — the shared `SharedDataCollector` handed to every window it creates
- [Windows (subfolder)](../windows/___windows.md) — `BaseMonitorWindow`, `CPUWindow`, `MemoryWindow`, `NetworkWindow`, and `place_on_screen()` / `target_screen()`, the sole placement authority

### Used by
- [Tray](tray.md) — toggles windows, opens Settings, and drives the exit sequence
- `main.py` — creates the manager and applies the startup settings
- `app/__init__.py` — re-exports `WindowManager`

## Constants

`MODES` — the display order and the `InitialSettings` flag that enables
each mode: `("cpu", "cpu_enabled")`, `("memory", "memory_enabled")`,
`("network", "network_enabled")`. The tray builds its menu from this, so a
fourth monitor mode would need no tray changes.

## Classes

### WindowManager

| Method | Description |
|--------|--------------|
| `existing()` | Every window created so far, in display order. |
| `window(key)` | One mode's window, or `None` if never needed. |
| `is_visible(key)` | Whether a mode's window exists and is on screen. |
| `show(key)` | Show a mode's window, creating it on first use. |
| `hide(key)` / `set_visible(key, visible)` | Hide, or show/hide by flag. |
| `hide_all()` / `show_all()` / `any_visible()` | Group operations for the tray's Minimize and double-click toggle. |
| `apply_settings(settings)` | Adopts one `InitialSettings` for every monitor and matches window visibility to its mode flags. |
| `reset_positions()` | Forgets every window's remembered x/y and re-places them all. |
| `prepare_exit()` | Saves every visible window's layout, then hides them all at once. |

## Design Decisions

- **Lazy creation, never destruction.** Building a `NetworkWindow` starts
  the ETW kernel trace, so creating all three up front would pay for a
  monitor the user did not ask for; keeping a window after it is hidden
  keeps its peak/history record continuous, which destroying and rebuilding
  would throw away.
- **Peering lives here.** `_link_peers()` runs whenever a window is
  created, wiring CPU and Memory as refresh-rate peers — both read from the
  same collector tick, so changing one window's rate has to move the
  other's with it. This is correct regardless of which order the monitors
  get switched on in.
- **`_create()` only positions a window with no REMEMBERED spot, and
  thinks entirely in frame space.** A window the user parked deliberately
  must never be shoved because a sibling opens later. The first such window
  is centred on `target_screen()`'s available geometry; every later one
  cascades off the previous window's `frameGeometry()` by
  `Dimensions.WINDOW_GAP`. Both operands are frame-space — mixing a frame
  `x()` with a client `width()` would drift the gap by the window's border
  on every step. `place_on_screen()` still gets the final say on show.
- **`reset_positions()` drops ONLY x/y.** Never `width`/`height`/
  `splitter`/`*_cols`, and never the per-window `theme` key that shares the
  same `last_setup.json` entry — those are the user's, not the accident's.
  It is the in-app escape hatch for a stranded gadget, exposed from the
  tray menu.
