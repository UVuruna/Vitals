"""Start-with-Windows registration.

Two mechanisms, because one does not cover both ways Vitals runs:

- **Frozen exe** — a Task Scheduler task with `/rl highest`. Vitals needs
  elevation for the ETW network trace, and Windows SILENTLY SKIPS `HKCU\\...\\Run`
  entries that point at a UAC-elevated exe, so the Run key cannot work here.
  The task name matches the one `setup/installer.nsi` creates, so the in-app
  toggle and the installer control the same task.
- **Dev mode** — the plain `HKCU\\...\\Run` value, launched through
  `pythonw.exe` so no console window appears.

Failures are reported to stderr and never crash the setup screen.
"""

import subprocess
import sys
import winreg
from pathlib import Path


# ══════════════════════════ REGISTRATION IDENTITY ══════════════════════════

# Name of both the HKCU Run value (dev mode) and the Task Scheduler task
# created by the installer (setup/installer.nsi APP_NAME) — they must match
# so the in-app toggle controls the same task the installer creates.
_STARTUP_APP_NAME = "Vitals"
_STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _get_startup_exe_path() -> str:
    """Return the command to register in Windows startup."""
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'
    # Dev mode: use pythonw.exe to avoid a console window
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    main_py = Path(__file__).parent.parent / "main.py"
    return f'"{pythonw}" "{main_py}"'


def _run_schtasks(*args: str) -> int:
    """Run schtasks.exe without flashing a console window. Returns exit code."""
    return subprocess.run(
        ["schtasks", *args],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ).returncode


def _delete_legacy_run_value() -> None:
    """Remove the HKCU Run entry left by pre-2.0.214 versions.

    Windows silently skips Run entries pointing to UAC-elevated exes,
    so for the frozen app this entry is dead weight at best.
    """
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE,
        )
        try:
            winreg.DeleteValue(key, _STARTUP_APP_NAME)
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except OSError as e:
        print(f"[Vitals] Legacy Run cleanup failed: {e}", file=sys.stderr)


# ═════════════════════════════ PUBLIC TOGGLE ═════════════════════════════

def is_startup_registered() -> bool:
    """Return True if the app autostarts with Windows.

    Frozen exe: checks the Task Scheduler task shared with the installer
    (Registry Run is silently skipped for UAC-elevated apps).
    Dev mode:   checks the HKCU Run registry entry.
    """
    if getattr(sys, 'frozen', False):
        return _run_schtasks("/query", "/tn", _STARTUP_APP_NAME) == 0
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STARTUP_REG_KEY)
        winreg.QueryValueEx(key, _STARTUP_APP_NAME)
        winreg.CloseKey(key)
        return True
    except OSError:
        return False


def set_startup_registered(enabled: bool) -> None:
    """Add or remove Windows autostart.

    Frozen exe: creates/deletes the same Task Scheduler task the installer
    manages (/rl highest, required for elevated apps) and cleans any legacy
    Run entry. Dev mode: uses the HKCU Run registry entry.
    Failures are reported to stderr but never crash the dialog.
    """
    if getattr(sys, 'frozen', False):
        _delete_legacy_run_value()
        if enabled:
            rc = _run_schtasks(
                "/create", "/tn", _STARTUP_APP_NAME,
                "/tr", _get_startup_exe_path(),
                "/sc", "onlogon", "/rl", "highest", "/f",
            )
            if rc != 0:
                print(f"[Vitals] schtasks /create failed (exit {rc})", file=sys.stderr)
        elif is_startup_registered():
            rc = _run_schtasks("/delete", "/tn", _STARTUP_APP_NAME, "/f")
            if rc != 0:
                print(f"[Vitals] schtasks /delete failed (exit {rc})", file=sys.stderr)
        return
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _STARTUP_REG_KEY,
            0, winreg.KEY_SET_VALUE,
        )
        if enabled:
            winreg.SetValueEx(key, _STARTUP_APP_NAME, 0, winreg.REG_SZ, _get_startup_exe_path())
        else:
            try:
                winreg.DeleteValue(key, _STARTUP_APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except OSError as e:
        print(f"[Vitals] Startup registry update failed: {e}", file=sys.stderr)
