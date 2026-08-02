# Tray Controller

**Script:** [Tray Controller (script)](../tray.py)

## Purpose

Owns the single system tray icon that represents the whole application in
gadget mode. The monitor windows are `Qt.Tool` windows with no taskbar
button and no Alt-Tab entry, so this tray icon is the app's only persistent
shell identity: its menu shows/hides each monitor window, opens the shared
Settings screen, and its **Exit** action is the ONLY way to quit — a
window's X only hides it.

## Connections

### Uses
- [Styles](styles.md) — `context_menu_style()` for the tray menu
- [Theme](theme.md) — `app_theme()`, whose `changed` signal restyles the menu on a global flip; the tray follows the app-wide scope, never a monitor window's, since it outlives every window and belongs to none of them
- [Window Manager](window_manager.md) — `MODES` builds the menu's per-window entries; toggles visibility, drives Minimize, Reset positions and the exit sequence
- [Dialogs (subfolder)](../dialogs/___dialogs.md) — `InitialSettingsDialog`, opened by the menu's **Settings** action

### Used by
- `main.py` — constructs one `TrayController(app.windowIcon(), manager)` and keeps a reference alive for the whole `app.exec()` lifetime; wires `app.aboutToQuit` to `prepare_exit()`

## Classes

### TrayController
Not a `QObject` subclass — a plain owner object. Keeping a live Python
reference is required, since nothing else keeps the underlying
`QSystemTrayIcon` alive.

`TrayController(icon, manager: WindowManager)` builds one checkable menu
action per mode in `window_manager.MODES` (CPU / Memory / Network — present
whether or not that window has been created yet), then a separator,
**Settings**, **Reset window positions**, another separator, **Minimize**
and **Exit** — and shows the tray icon immediately.

| Method | Description |
|--------|--------------|
| `_apply_theme()` | Restyles the tray menu from `app_theme().palette`. |
| `_show_settings()` | Opens `InitialSettingsDialog`; on accept, hands the result to `manager.apply_settings()`. |
| `prepare_exit()` | Hides the tray icon and every window at once, saving layouts first — runs synchronously from the Exit click AND (harmlessly, as a no-op on already-hidden windows) from `aboutToQuit`. |
| `_exit_app()` | `prepare_exit()`, then `QApplication.instance().quit()`. |
| `_refresh_checks()` | Runs on `QMenu.aboutToShow` — syncs each action's checkmark to the window's live `isVisible()`. |
| `_on_activated(reason)` | Double-click toggles all windows: hides them if any is visible, else shows them all. |

## Design Decisions

- **One tray icon for the whole app, not one per window.** Gadget-mode
  windows have no taskbar presence, so without a shared tray icon a user who
  closed every window would have no way back short of relaunching the app.
- **Checkmarks are read from `isVisible()` on every menu open, not
  cached.** Visibility can change from several places (closeEvent,
  `show_from_tray()`, OS session events); a separate "is checked" flag would
  drift, while reading live state on `aboutToShow` is always correct and
  cheap enough to recompute every time.
- **The tray follows the app-wide theme scope, never a monitor window's.**
  Each of the three windows carries its own independent theme; the tray
  cannot follow one of them without arbitrarily picking a favorite, so it
  restyles from `app_theme()` — the same scope the setup screen's global
  switch moves.
- **`_show_settings()` reads `get_settings()` BEFORE calling
  `deleteLater()`, never `WA_DeleteOnClose`.** `QDialog.exec()` would
  destroy a `WA_DeleteOnClose` dialog before returning, so reading its
  settings afterward would hit an already-freed object. The dialog is also
  parentless, so nothing else would ever free it either — read, then
  `deleteLater()`, is the only ordering that both works and cleans up.
- **Exit is synchronous, not deferred to `aboutToQuit` alone.**
  `prepare_exit()` hides the tray icon and every window together before the
  slower teardown (collector stop, ETW session stop) begins, so the whole
  app visibly vanishes at once instead of one window at a time.
