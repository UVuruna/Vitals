# Setup Dialog

**Script:** [Setup Dialog (script)](../setup_dialog.py) ·
**Flow:** [diagram](../__flow/setup_dialog.md)

## Purpose

`InitialSettingsDialog` is the app's front door: the one place to configure
every monitor at once (which windows open, rows, refresh rate, retention,
units, fonts, network options, Start-with-Windows). It is shown once at
launch and again from the tray's **Settings** action, so one edit reaches
all three monitors instead of hunting through three per-window dialogs. It
is also the only settings surface with a Day/Night switch, and that switch
is the GLOBAL one — a monitor window's own header switch flips that window
alone, this one flips the whole app scope. That is why this dialog restyles
live (registers for `self._theme.changed`) while the per-mode dialogs in
[Mode Dialogs](mode_dialogs.md) style once and never see a flip.

## Connections

### Uses
- [Base Settings Dialog](base_dialog.md) — the shared base class, factories and row builders
- [Dialog Styles](dialog_styles.md) — `mode_button_style` (the 3 mode buttons and the autostart toggle), `start_button_style` (the primary action button)
- [Persistence](../../__about/persistence.md) — `load_last_setup()`, restoring the previous session's controls
- [Settings](../../__about/settings.md) — `InitialSettings`, `save_initial_settings()`
- [Startup](../../__about/startup.md) — `is_startup_registered()`, `set_startup_registered()`
- [Styles](../../__about/styles.md) — `Defaults`
- [Theme](../../__about/theme.md) — `app_theme()`, the scope this dialog binds to
- [Day/Night Switch](../../__about/theme_switch.md) — `DayNightSwitch`
- [Theme Transition](../../__about/transition.md) — `flip_app_theme()`, what this dialog's switch calls
- [Network Trace](../../collect/__about/network_trace.md) — `get_link_speed_mbps()`, the default value for the max-download/upload spinboxes

### Used by
- [App (folder)](../../___app.md) — `main.py` shows `InitialSettingsDialog` before any window is created; `app/__init__.py` re-exports it
- [Tray Controller](../../__about/tray.md) — reopens it from the tray menu's **Settings** action

## Classes

### InitialSettingsDialog (BaseSettingsDialog)
`InitialSettingsDialog(parent=None, first_run=True)` — binds to `app_theme()`,
not any window's scope, since it exists before any monitor window does.
`first_run=False` (the tray's Settings action) only changes the subtitle
text and labels the primary button **Apply** instead of **Start
Monitoring**; everything else is identical, so there is one screen rather
than two.

| Method | Description |
|--------|-------------|
| `_setup_ui()` | Builds every zone described in the [flow doc](../__flow/setup_dialog.md)'s layout sketch, in order, then restores the previous session via `_apply_last_setup(load_last_setup())`. |
| `_update_mode_buttons()` | Restyles the 3 mode buttons for their checked state, shows/hides the network settings container, and enables/disables the start button. Registered as a restyler (it already repaints on click) and doubles as the global-flip handler. |
| `_update_startup_toggle()` | Restyles the autostart toggle for its checked state and updates its ON/OFF text. Also registered as a restyler. |
| `_on_start()` | Registers/unregisters Windows autostart, saves the settings, and accepts — see the [flow doc](../__flow/setup_dialog.md). |
| `_apply_last_setup(saved)` | Pushes a previously saved settings dict into the controls, guarded per key so a partial/older save file does not fail. |
| `get_settings()` | Reads every control back into a fresh `InitialSettings`. |
