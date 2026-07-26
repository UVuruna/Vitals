# Tray Controller

**Script:** [tray.py (script)](tray.py)

---

## Purpose

Owns the single system tray icon that represents the whole application in
gadget mode. Monitor windows (`BaseMonitorWindow` subclasses) are
`Qt.Tool` windows with no taskbar button and no Alt-Tab entry — the tray
icon is the app's only persistent shell identity. Its menu shows/hides each
monitor window, and its **Exit** action is the way to quit the application
(closing a window only hides it — see [Main Window](main_window.md)).

---

## Connections

### Uses

- [Styles](styles.md) — `context_menu_style()` for the tray menu
- [Theme](theme.md) — `app_theme()`, whose `changed` signal restyles the menu on a flip. The tray follows the APP-WIDE scope, never a monitor window's — it outlives every window and belongs to none of them
- [Window Manager](window_manager.md) — toggles each monitor, drives Minimize and the exit sequence; `MODES` builds the menu entries
- [Settings Dialog](settings_dialog.md) — `InitialSettingsDialog`, opened by the menu's **Settings** action, carrying the GLOBAL Day/Night switch that pushes one theme into every monitor window at once

### Used by

- `main.py` — constructs one `TrayController(app.windowIcon(), windows)` after
  creating the enabled monitor windows, and keeps a reference alive for the
  whole `app.exec()` lifetime

---

## Classes

### TrayController

Not a QObject subclass — a plain owner object. Keeping a live Python
reference is required, since nothing else keeps the `QSystemTrayIcon` alive.

#### Constructor

```python
TrayController(icon: QIcon, windows: list[BaseMonitorWindow])
```

Builds one checkable menu action per window (`window.windowTitle()`), a
separator, **Settings**, **Reset window positions**, another separator,
**Minimize**, and **Exit** — and shows the tray icon immediately.

#### Methods (internal callbacks — this is the entire behavior surface)

| Method | Description |
|--------|-------------|
| `_minimize_all()` | "Minimize" menu action: hides every currently visible window to the tray at once (`_hide_to_tray()`), the counterpart to a double-click. Monitors keep running while hidden. |
| `_toggle_window(window, visible)` | Checkbox toggled: `show_from_tray()` to show, `_hide_to_tray()` to hide. |
| `_refresh_checks()` | Runs on `QMenu.aboutToShow` — syncs checkmarks to actual `isVisible()` state before the menu is drawn. |
| `_on_activated(reason)` | Double-click toggles all windows: hides them all (`_minimize_all()`) if any is visible, otherwise re-shows them all via `show_from_tray()`. |

---

## Design Decisions

**One tray icon for the whole app, not one per window.** Gadget-mode windows
have no taskbar presence, so without a shared tray icon a user who closes
every window would have no way to bring any of them back short of relaunching
the app.

**Checkmarks are read from `isVisible()` on every menu open, not cached.**
Window visibility can change from several places (closeEvent, `show_from_tray()`,
OS session events), so tracking a separate "is checked" flag would drift.
Reading live state on `aboutToShow` is always correct and cheap enough to
recompute every time.

**`show_from_tray()`, not `show()`.** Toggling a window back on must also
resume its paused monitor and restart the shared collector thread if it had
fully stopped (see `BaseMonitorWindow.show_from_tray()` in
[Main Window](main_window.md)) — plain `show()` would display stale, frozen
data.

**The tray belongs to no monitor window, so it follows the app-wide theme
scope.** Each of the three windows now carries its own independent theme;
the tray menu cannot follow one of them without arbitrarily picking a
favorite, so it restyles from `app_theme()` instead — the same scope the
setup screen's GLOBAL Day/Night switch moves.

**`_show_settings()` reads `get_settings()` before calling `deleteLater()`,
never `WA_DeleteOnClose`.** `QDialog.exec()` destroys a `WA_DeleteOnClose`
dialog before returning, so the `get_settings()` call right after would hit
an already-freed C++ object and raise `RuntimeError`. The dialog is also
parentless — it belongs to no monitor window — so nothing else would ever
free it either; reading the settings, THEN calling `deleteLater()`, is the
only ordering that both works and cleans up.

**Reset window positions is one line, not a tray method.** The menu action
wires straight to `manager.reset_positions()` — the tray has no state of
its own to update, so a wrapper method here would only forward the call.
