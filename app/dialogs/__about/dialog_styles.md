# Dialog Styles

**Script:** [Dialog Styles (script)](../dialog_styles.py)

## Purpose

Pure QSS builder functions for the settings-dialog widget family — one
function per widget kind, each taking the `Palette` to render in and
returning a stylesheet string. Never a module-level f-string: a dialog is
themed by the window that opened it, and two open dialogs can be on
different themes, so nothing here may look up a theme of its own. A
module-level constant would freeze whichever palette happened to be active
at import time — the exact bug `ThemeScope` exists to prevent.
`BaseSettingsDialog._themed_sheet()` registers these as restylers, which is
what lets the setup screen follow a live theme flip.

## Connections

### Uses
- [Theme](../../__about/theme.md) — `Palette`, the single argument every builder takes

### Used by
- [Base Settings Dialog](base_dialog.md) — `combo_style`, `slider_style`, `spinbox_style` for the shared factories
- [Setup Dialog](setup_dialog.md) — `mode_button_style` (mode buttons + autostart toggle), `start_button_style` (the primary action button)
- [Mode Dialogs](mode_dialogs.md) — `apply_button_style` (all three dialogs' Apply button)

## Functions

| Function | Description |
|----------|-------------|
| `spinbox_style(palette)` | QSS for a numeric input; hides the up/down buttons. |
| `slider_style(palette)` | QSS for a settings slider (groove, handle, filled sub-page). |
| `combo_style(palette)` | QSS for a dropdown, including its popup list and drop-down arrow. |
| `start_button_style(palette)` | QSS for the setup screen's primary action button, with a disabled state. |
| `mode_button_style(palette, active)` | QSS for a selectable mode/toggle button — accent-filled when `active`, muted otherwise. |
| `apply_button_style(palette)` | QSS for a per-mode dialog's Apply button — one builder shared by all three. |
