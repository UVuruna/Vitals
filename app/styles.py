"""
UI Styling Constants

Fonts, dimensions, and layout constants for the Process Monitor application.
Color management has been moved to color_management.py.
"""

from dataclasses import dataclass
from functools import lru_cache


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
    MAX_ROWS = 30
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


CONTEXT_MENU_STYLE = """
    QMenu {
        background-color: #2a2a3e;
        color: #ffffff;
        border: 1px solid #3a3a4e;
        padding: 4px;
    }
    QMenu::item {
        padding: 6px 24px;
        border-radius: 3px;
    }
    QMenu::item:selected {
        background-color: #3a3a4e;
    }
    QMenu::item:disabled {
        color: #666666;
    }
    QMenu::separator {
        height: 1px;
        background-color: #3a3a4e;
        margin: 4px 0;
    }
"""


def format_pct(value: float) -> str:
    """
    Format a percentage value with adaptive decimal precision.

    Always occupies at most 3 significant digits before the '%':
      >= 100  → integer      e.g. "100%", "1600%"
      >= 10   → 1 decimal    e.g. "10.0%", "99.9%"
      < 10    → 2 decimals   e.g. "0.05%", "9.99%"
    """
    if value >= 100:
        return f"{value:.0f}%"
    elif value >= 10:
        return f"{value:.1f}%"
    else:
        return f"{value:.2f}%"


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
