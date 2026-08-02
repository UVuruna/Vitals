# Shell

**Script:** [Shell (script)](../shell.py)

## Purpose

Two things Vitals needs from the Windows shell that Qt does not offer, both
plain `ctypes` calls into shell32/user32:

- **An elevated relaunch.** The ETW kernel trace cannot be started from a
  medium-integrity process, so no in-process retry can ever fix
  `NEEDS_ADMIN` — only a brand-new elevated process can.
- **A per-window taskbar identity.** When several windows share one
  process-level AppUserModelID, Windows shows the exe's group icon instead of
  each window's own; setting `PKEY_AppUserModel_ID` and
  `PKEY_AppUserModel_RelaunchIconResource` per window through
  `IPropertyStore` tells the shell exactly which icon to use.

Icon cosmetics are best-effort by design: a failure is reported to stderr and
swallowed, never allowed to take the window down with it.

## Connections

### Uses

- none — talks directly to the Windows shell (ctypes/COM) and PySide6; no other Vitals component

### Used by

- [Base Window](base_window.md) — `showEvent()` calls `set_native_taskbar_icon()` once per window; `_on_status_action()` calls `relaunch_elevated()` when the status banner's failure code is `NEEDS_ADMIN`

## Functions

### `relaunch_elevated() -> None`
Restarts Vitals with Administrator rights via `ShellExecuteW(..., "runas", ...)`,
then quits this instance. A `ShellExecuteW` result `> 32` means the shell
accepted the request; anything else — including the user declining the UAC
prompt — leaves the current instance running and is reported to stderr, never
silently swallowed.

### `set_native_taskbar_icon(window, ico_path) -> None`
Sets a per-window icon via `IPropertyStore` (`PK_ID`, `PK_ICON`) with a
`WM_SETICON` fallback. Best-effort: any failure is caught and printed to
stderr, never raised.
