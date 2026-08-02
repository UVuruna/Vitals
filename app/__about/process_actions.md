# Process Actions

**Script:** [Process Actions (script)](../process_actions.py)

## Purpose

Live process operations for the right-click menu: kill, set priority class,
open file location, and the lookups those actions need (matching processes
by display name, reading the current priority, resolving an exe path). Every
function accepts live `psutil.Process` objects rather than caching PIDs, so
a stale handle can never be acted on.

## Connections

### Uses
- [Styles](styles.md) — `get_process_display_name()`, to match a display name back to its live `psutil.Process` objects
- `psutil` — process enumeration, kill, priority (`nice()`), exe path
- stdlib `subprocess` — `explorer /select,` for "Open file location"

### Used by
- [Windows (subfolder)](../windows/___windows.md) — the process context menu wires its Kill / Priority / Open location actions to these functions
- [Dialogs (subfolder)](../dialogs/___dialogs.md) — `PRIORITY_CLASSES`, read by the Priority selection dialog

## Functions

| Function | Description |
|----------|--------------|
| `find_processes(display_name)` | Every live process whose display name (after alias mapping) matches. |
| `kill_processes(procs)` | Kills all given processes; returns `(killed_count, error_messages)`. An already-gone process counts as a success. |
| `get_exe_path(procs)` | The exe path of the first accessible process. |
| `open_file_location(exe_path)` | Opens Explorer with the exe selected. |
| `get_current_priority(procs)` | The Windows priority class of the first accessible process. |
| `set_priority(procs, priority_class)` | Sets the priority class for all given processes; returns `(changed_count, error_messages)`. |

## Constants

`PRIORITY_CLASSES` — the six Windows priority classes as
`(label, psutil constant)` pairs, from `Realtime` down to `Idle`, in the
order the Priority dialog lists them.

## Design Decisions

- **Every function takes live `psutil.Process` objects, never PIDs.** A PID
  can be recycled by the OS between the menu opening and the action firing;
  operating on the `Process` handle the caller already holds avoids acting
  on the wrong process.
- **`AccessDenied` is collected as a per-process error, not raised.** Kill
  and priority-change loops keep going across the rest of the selection and
  report which PIDs failed, rather than aborting the whole batch on the
  first protected process.
- **`NoSuchProcess` during a kill counts as success.** The caller's goal was
  "this process should not be running" — a process that already exited
  satisfies that goal.
