"""
Process Actions

Live process operations: kill, set priority, open file location.
All functions accept live psutil.Process objects to avoid stale state.
"""

import subprocess
from typing import Optional

import psutil

from .styles import get_process_display_name


PRIORITY_CLASSES = [
    ("Realtime",     psutil.REALTIME_PRIORITY_CLASS),
    ("High",         psutil.HIGH_PRIORITY_CLASS),
    ("Above Normal", psutil.ABOVE_NORMAL_PRIORITY_CLASS),
    ("Normal",       psutil.NORMAL_PRIORITY_CLASS),
    ("Below Normal", psutil.BELOW_NORMAL_PRIORITY_CLASS),
    ("Idle",         psutil.IDLE_PRIORITY_CLASS),
]


def find_processes(display_name: str) -> list[psutil.Process]:
    """Return all live processes whose display name matches the given display name."""
    result = []
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            if get_process_display_name(proc.info['name']) == display_name:
                result.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return result


def kill_processes(procs: list[psutil.Process]) -> tuple[int, list[str]]:
    """
    Kill all given processes.

    Returns:
        (killed_count, error_messages)
    """
    killed = 0
    errors = []
    for proc in procs:
        try:
            proc.kill()
            killed += 1
        except psutil.NoSuchProcess:
            killed += 1  # Already gone — counts as success
        except psutil.AccessDenied:
            errors.append(f"PID {proc.pid}: Access denied")
        except Exception as e:
            errors.append(f"PID {proc.pid}: {e}")
    return killed, errors


def get_exe_path(procs: list[psutil.Process]) -> Optional[str]:
    """Return the exe path of the first accessible process."""
    for proc in procs:
        try:
            path = proc.exe()
            if path:
                return path
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def open_file_location(exe_path: str):
    """Open Windows Explorer with the exe file selected."""
    subprocess.Popen(['explorer.exe', f'/select,{exe_path}'])


def get_current_priority(procs: list[psutil.Process]) -> Optional[int]:
    """Return the Windows priority class of the first accessible process."""
    for proc in procs:
        try:
            return proc.nice()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def set_priority(procs: list[psutil.Process], priority_class: int) -> tuple[int, list[str]]:
    """
    Set the Windows priority class for all given processes.

    Returns:
        (changed_count, error_messages)
    """
    changed = 0
    errors = []
    for proc in procs:
        try:
            proc.nice(priority_class)
            changed += 1
        except psutil.NoSuchProcess:
            pass
        except psutil.AccessDenied:
            errors.append(f"PID {proc.pid}: Access denied")
        except Exception as e:
            errors.append(f"PID {proc.pid}: {e}")
    return changed, errors
