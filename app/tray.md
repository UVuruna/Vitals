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

- [Styles](styles.md) — `CONTEXT_MENU_STYLE` for the tray menu

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

Builds one checkable menu action per window (`window.windowTitle()`) plus a
separator, **Minimize**, and **Exit**, and shows the tray icon immediately.

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
