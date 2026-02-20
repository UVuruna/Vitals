"""
UI Styling Constants

Colors, fonts, and dimensions for the Process Monitor application.
"""

from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Colors:
    """Application color palette."""

    # Background colors
    BACKGROUND = "#ECF5F9"

    # Current processes (red theme)
    CURRENT_HEADER = "#FFC6C6"
    CURRENT_BODY = "#FFE2E2"

    # Historical processes (blue theme)
    HISTORY_HEADER = "#A2D2FF"
    HISTORY_BODY = "#E2F1FF"

    # Text
    TEXT_PRIMARY = "#060606"
    TEXT_SECONDARY = "#444444"

    # Accents
    ACCENT_CPU = "#FF6B6B"
    ACCENT_MEMORY = "#4ECDC4"
    ACCENT_CORES = "#95E1D3"


@dataclass(frozen=True)
class Dimensions:
    """Window and widget dimensions."""

    WINDOW_WIDTH = 500
    WINDOW_MIN_HEIGHT = 400

    MARGIN = 10
    SPACING = 8

    TABLE_ROW_HEIGHT = 28
    HEADER_HEIGHT = 50

    # Settings dialog
    SETTINGS_WIDTH = 450
    SETTINGS_HEIGHT = 400


@dataclass(frozen=True)
class Fonts:
    """Font configurations."""

    FAMILY = "Segoe UI"

    SIZE_HEADER = 14
    SIZE_BODY = 11
    SIZE_SMALL = 10


# Default configuration values
class Defaults:
    """Default settings values."""

    CURRENT_ROWS = 7
    HISTORY_ROWS = 4
    REFRESH_RATE_MS = 1000
    RETENTION_MINUTES = 120

    MEMORY_UNIT = "MB"

    # These are auto-detected but can be overridden
    CPU_THREADS = None  # Auto-detect
    RAM_GB = None  # Auto-detect


# Memory unit conversions
MEMORY_UNITS = {
    "KB": 1024,
    "MB": 1024 ** 2,
    "GB": 1024 ** 3,
}

# Process name mappings for aggregation
PROCESS_ALIASES = {
    "Code": "Visual Studio Code",
    "code": "Visual Studio Code",
    "logi": "Logi Options+",
    "steam": "Steam",
    "nv": "NVIDIA",
    "msedge": "Microsoft Edge",
    "chrome": "Chrome",
    "firefox": "Firefox",
    "Discord": "Discord",
    "Spotify": "Spotify",
}


@lru_cache(maxsize=512)
def get_process_display_name(name: str) -> str:
    """
    Convert process name to display-friendly name.

    Groups related processes under common names.

    Args:
        name: Original process name (e.g., "Code.exe")

    Returns:
        Display name (e.g., "Visual Studio Code")
    """
    # Remove .exe extension
    if name.lower().endswith('.exe'):
        name = name[:-4]

    # Check aliases (prefix matching)
    for prefix, display_name in PROCESS_ALIASES.items():
        if name.lower().startswith(prefix.lower()):
            return display_name

    return name
