# Process Dialog

**Script:** [Process Dialog (script)](../process_dialog.py)

## Purpose

The two process-action confirmation dialogs shown from a monitor window's
right-click menu: `KillConfirmDialog` before killing all instances of a
process, `PriorityDialog` for picking a new priority class. Both share a
header (the process name, colored with its swatch if known) and a content
area via the private `_ProcessDialogBase`. Each takes a plain `Palette`, not
a `ThemeScope` — being modal, reading the palette once at construction from
the window that opened it is enough; there is no flip to follow.

## Connections

### Uses
- [Process Actions](../../__about/process_actions.md) — `PRIORITY_CLASSES`, the label/value pairs `PriorityDialog` builds its radio buttons from
- [Styles](../../__about/styles.md) — `Fonts`
- [Theme](../../__about/theme.md) — `Palette`, taken (not looked up) at construction

### Used by
- [Process Menu](../../windows/__about/process_menu.md) — builds each dialog with `window._theme.palette` and a process color from `ProcessColorManager`

## Classes

### _ProcessDialogBase (QDialog)
Private base, not exported. `__init__(parent, process_name, title, palette, proc_color=None)`
sets the modal dialog's stylesheet from `palette` and lays out a `CARD`-colored
header (the process name, in `proc_color` if given) above a content area
(`self._content`, a `QVBoxLayout`) that subclasses fill in.

### KillConfirmDialog(_ProcessDialogBase)
`KillConfirmDialog(parent, process_name, count, palette, proc_color=None)` —
a confirmation message plus Cancel/Kill buttons; accepts on Kill.

### PriorityDialog(_ProcessDialogBase)
`PriorityDialog(parent, process_name, current_priority, palette, proc_color=None)` —
a `QButtonGroup` of radio buttons over `PRIORITY_CLASSES`, the one matching
`current_priority` pre-checked, plus Cancel/Apply. `get_selected_priority()`
returns the checked button's Windows priority-class constant, or `None`.
