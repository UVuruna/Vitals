# Startup

**Script:** [Startup (script)](../startup.py)

## Purpose

Start-with-Windows registration, behind one toggle in the setup screen. Two
mechanisms exist because one does not cover both ways Vitals runs:

- **Frozen exe** — a Task Scheduler task with `/rl highest`. Vitals needs
  elevation for the ETW network trace, and Windows SILENTLY SKIPS
  `HKCU\...\Run` entries that point at a UAC-elevated exe, so the Run key
  cannot work here. The task name matches the one `setup/installer.nsi`
  creates, so the in-app toggle and the installer control the same task.
- **Dev mode** — the plain `HKCU\...\Run` value, launched through
  `pythonw.exe` so no console window appears.

This module was created by the god-file split: it did not exist before, and
carries no legacy documentation.

## Connections

### Uses
- stdlib only — `subprocess` (`schtasks.exe`, no flashed console window),
  `winreg`, `pathlib`, `sys`

### Used by
- [Dialogs (subfolder)](../dialogs/___dialogs.md) — the setup screen's autostart checkbox reads `is_startup_registered()` and writes `set_startup_registered()`

## Functions

| Function | Description |
|----------|--------------|
| `is_startup_registered()` | Frozen exe: queries the shared Task Scheduler task. Dev mode: checks the HKCU Run value. |
| `set_startup_registered(enabled)` | Frozen exe: creates/deletes the Task Scheduler task (`/rl highest`) and cleans up any legacy Run entry. Dev mode: sets/deletes the HKCU Run value. Failures are reported to stderr, never raised. |

## Design Decisions

- **Two mechanisms, chosen by `sys.frozen`, not one that tries to cover
  both.** A UAC-elevated exe registered in `HKCU\...\Run` is silently
  skipped by Windows at logon — there is no way to make the Run key work for
  the shipped app, so the frozen path uses Task Scheduler exclusively.
- **The Task Scheduler task name is shared with the installer.** Both
  `setup/installer.nsi` and this module use the same `_STARTUP_APP_NAME`, so
  the in-app toggle and the installer's own autostart option control the
  identical task rather than each silently fighting the other.
- **A legacy `HKCU\...\Run` entry from a pre-2.0.214 build is actively
  cleaned up** on every `set_startup_registered()` call for the frozen exe —
  dead weight at best, since Windows never honored it for an elevated app.
- **Every failure is a documented fallback, not a crash.** `schtasks`
  exit codes and registry errors are reported to stderr; the setup screen's
  toggle keeps working even if the underlying registration call failed.
