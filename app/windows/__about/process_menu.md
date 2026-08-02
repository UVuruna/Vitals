# Process Menu

**Script:** [Process Menu (script)](../process_menu.py)

## Purpose

The right-click process menu and the actions it offers. Right-clicking any
row in any of the three tables opens a menu that is half INFORMATION (the
signing company, every PID, the exe path — each line click-to-copy) and half
ACTIONS (kill, open file location, set priority).

Everything here works on LIVE processes looked up by display name at the
moment of the click, never on the row's rendered numbers: the table shows an
aggregate that may be seconds old, and killing something on stale identity is
exactly the mistake to avoid.

## Connections

### Uses

- [Icons](../../__about/icons.md) — `icons.swatch()`, the company-color chip on the first info line
- [Color Management](../../__about/color_management.md) — `ProcessColorManager` (company name lookup, process color for the swatch)
- [Dialogs (subfolder)](../../dialogs/___dialogs.md) — `KillConfirmDialog`, `PriorityDialog` (`process_dialog.py`)
- [Process Actions](../../__about/process_actions.md) — `find_processes()`, `get_current_priority()`, `get_exe_path()`, `kill_processes()`, `open_file_location()`, `set_priority()`
- [Styles](../../__about/styles.md) — `Dimensions.MENU_LINE_CHARS` (company-name wrap width), `context_menu_style()`

### Used by

- [Base Window](base_window.md) — `_connect_table_selection()` wires each table's `customContextMenuRequested` to `show_process_menu()`

## Functions

### `show_process_menu(window, pos, table, has_total_row) -> None`
Builds and executes the context menu for the row under `pos`. Blocks the Σ
total row when `has_total_row` is set. Info lines (company — wrapped across
as many lines as it needs, with the row's own color as a swatch — PIDs in
chunks of 10, exe name) are each click-to-copy; the action items dispatch to
the three functions below.

### `do_kill(window, process_name) -> None`
Confirms via `KillConfirmDialog`, then calls `kill_processes()`; any errors
are surfaced in a `QMessageBox`.

### `do_open_location(window, process_name) -> None`
Resolves the exe path via `get_exe_path()` and opens Explorer with it
selected via `open_file_location()`.

### `do_set_priority(window, process_name) -> None`
Reads the current priority via `get_current_priority()`, confirms the new one
via `PriorityDialog`, then applies it via `set_priority()`; any errors are
surfaced in a `QMessageBox`.
