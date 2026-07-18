"""
Persistence - single access point for config/last_setup.json.

All reads and writes of the user's saved setup (monitor selection, display
settings, window layouts, color thresholds, hue params) go through this module.

Guarantees:
- Atomic writes: data is written to a temp file and swapped in with os.replace,
  so a crash or forced shutdown can never leave a truncated file behind.
- Corruption recovery (documented fallback): an unreadable or invalid file is
  treated as empty - load_last_setup() returns {} and the next save overwrites
  the bad file with valid content, instead of failing forever.
"""

import json
import os
import sys
from pathlib import Path


def get_base_path() -> Path:
    """Root folder for bundled, read-only resources (icons, config defaults, app_info.json).

    Frozen exe: the PyInstaller temp extraction dir (sys._MEIPASS) - read-only,
                recreated on every launch.
    Dev mode:   the project root.

    Contrast with get_data_dir(): this resolves resources shipped with the
    app itself, not the user's writable settings.
    """
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent


def get_data_dir() -> Path:
    """Root folder for user-writable app data (settings, logs).

    Frozen exe: %APPDATA%\\PMUsage - always writable, no admin needed.
    Dev mode:   the project root.

    Contrast with get_base_path(): this resolves the user's writable settings
    dir, not the bundled read-only resources shipped with the app.
    """
    if getattr(sys, 'frozen', False):
        appdata = os.environ.get('APPDATA') or os.environ.get('LOCALAPPDATA')
        return Path(appdata) / 'PMUsage' if appdata else Path(sys.executable).parent
    return Path(__file__).parent.parent


def get_last_setup_path() -> Path:
    """Resolve config/last_setup.json for user-writable storage."""
    return get_data_dir() / "config" / "last_setup.json"


def load_last_setup() -> dict:
    """Load the saved setup dict. Returns {} if the file is missing or invalid.

    An invalid file (e.g. truncated by a crash during an old non-atomic write)
    is reported to stderr and treated as empty, so the next save replaces it
    with valid content instead of every save failing silently forever.
    """
    path = get_last_setup_path()
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        print(f"[PMUsage] Invalid {path}: {e} - treating as empty", file=sys.stderr)
        return {}


def save_last_setup(data: dict) -> None:
    """Atomically write the full setup dict to last_setup.json.

    Writes to a temp file first, then swaps it in with os.replace, so the
    target file is never left truncated. A failed save is reported to stderr
    and the app keeps running with in-memory settings (best-effort by design:
    a save failure on close must not crash the app).
    """
    path = get_last_setup_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except OSError as e:
        print(f"[PMUsage] Failed to save {path}: {e}", file=sys.stderr)
