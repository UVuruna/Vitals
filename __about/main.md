# Entry Point

**Script:** [Entry Point (script)](../main.py) ·
**Flow:** [diagram](../__flow/main.md)

## Purpose

`main()` is the single process bootstrap for Vitals. It sets the Windows
taskbar identity, brings up Qt, loads the app's own metadata and the
monorepo's company metadata, shows the one-time initial settings dialog, and
then wires the three long-lived objects that make up the running app — the
data collector, the window manager, and the tray — before handing control to
the Qt event loop. Everything the rest of the app depends on (which windows
exist, which theme they start in, whether the collector is even running) is
decided here, once, before `app.exec()` is called.

## Connections

### Uses
- [Persistence](../app/__about/persistence.md) — `get_base_path()` resolves
  `setup/app_info.json`, `assets/icon.ico` and the monorepo-root
  `company.json` correctly in both a dev checkout and a frozen exe
- [Initial Settings Dialog](../app/dialogs/__about/setup_dialog.md) — shown
  once at startup; the app quits immediately (`return 0`) if the user
  rejects it, before any long-lived object is created
- [Collector](../app/collect/__about/collector.md) — `SharedDataCollector`
  is created as a singleton here, started after the windows are wired, and
  stopped/reset after the event loop returns
- [Window Manager](../app/__about/window_manager.md) — receives the
  dialog's `InitialSettings` and owns lazy creation of the CPU/Memory/
  Network windows from them
- [Tray](../app/__about/tray.md) — the single tray icon; its `prepare_exit`
  is wired to `aboutToQuit` here

### Used by
- none (entry point / not yet wired)

## Functions

### `main() -> int`
The whole bootstrap, in order:

1. Best-effort `SetCurrentProcessExplicitAppUserModelID` — cosmetic taskbar
   grouping only; a failure is logged to stderr and never aborts startup.
2. Create the `QApplication`.
3. Load `setup/app_info.json` and the monorepo-root `company.json`, and use
   them to set the Qt application name/version/organization.
4. Set the window icon (`assets/icon.ico`, falling back to `icon.svg`).
5. Show `InitialSettingsDialog`; return `0` immediately if it is rejected.
6. Create the `SharedDataCollector` singleton and the `WindowManager`, and
   apply the dialog's settings to the manager.
7. Enter gadget mode (`setQuitOnLastWindowClosed(False)`), create the
   `TrayController`, and connect `aboutToQuit` to `tray.prepare_exit`.
8. Start the collector if it is not already running, then call `app.exec()`.
9. On return, stop the collector and reset its singleton, then return the
   Qt exit code.

See [the flow diagram](../__flow/main.md) for why step 7's connection exists
alongside the tray's own synchronous Exit handler.
