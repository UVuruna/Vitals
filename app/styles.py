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


class FontScale:
    """Proportional font scaling (like em/rem in CSS).

    All sizes are defined as offsets from a base size.
    Default base = 11pt reproduces the original hardcoded sizes.
    """

    # Offsets from base size
    TITLE = 5       # base + 5 → 16pt at default (window title)
    SECTION = 2     # base + 2 → 13pt at default (section headers)
    SUBTITLE = 1    # base + 1 → 12pt at default (total label, buttons)
    BODY = 0        # base     → 11pt at default (standard text)
    SMALL = -1      # base - 1 → 10pt at default (secondary text)
    TINY = -2       # base - 2 →  9pt at default (core labels)

    MIN_SIZE = 6    # Absolute minimum font size (pt)

    @staticmethod
    def size(base: int, offset: int) -> int:
        """Compute a scaled font size from base + offset, clamped to MIN_SIZE."""
        return max(FontScale.MIN_SIZE, base + offset)

    @staticmethod
    def row_height(base: int) -> int:
        """Compute table row height proportional to base font size."""
        # Default: base=11 → row_height=28. Scale linearly.
        return round(28 * base / 11)


# Default configuration values
class Defaults:
    """Default settings values."""

    CURRENT_ROWS = 7
    HISTORY_ROWS = 4
    MAX_ROWS = 30
    REFRESH_RATE_MS = 1000
    RETENTION_MINUTES = 120

    MEMORY_UNIT = "MB"
    NETWORK_UNIT = "MB/s"
    FONT_SIZE = 11

    # These are auto-detected but can be overridden
    CPU_THREADS = None  # Auto-detect
    RAM_GB = None  # Auto-detect

    # Network defaults (Mbps — user overrides in settings)
    NETWORK_MAX_DOWNLOAD_MBPS = 0  # 0 = auto-detect from link speed
    NETWORK_MAX_UPLOAD_MBPS = 0    # 0 = auto-detect from link speed
    NETWORK_SORT_MODE = "total"    # "total", "download", or "upload"


# Memory unit conversions
MEMORY_UNITS = {
    "KB": 1024,
    "MB": 1024 ** 2,
    "GB": 1024 ** 3,
}

# Network speed unit conversions (bytes/sec to display unit)
NETWORK_UNITS = {
    "KB/s": 1024,
    "MB/s": 1024 ** 2,
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


def format_speed(bytes_per_sec: float, unit: str = "MB/s") -> str:
    """Format a bytes/sec value in the user's selected network unit.

    Args:
        bytes_per_sec: Raw speed in bytes per second.
        unit: Display unit ("KB/s" or "MB/s").

    Returns:
        Formatted string like "1,234 KB/s" or "12.34 MB/s".
    """
    divisor = NETWORK_UNITS.get(unit, NETWORK_UNITS["MB/s"])
    value = bytes_per_sec / divisor
    if unit == "MB/s":
        if value >= 100:
            return f"{value:,.0f} {unit}"
        return f"{value:,.2f} {unit}"
    return f"{value:,.0f} {unit}"


def format_bytes_total(total_bytes: float, unit: str = "MB/s") -> str:
    """Format cumulative byte count in a human-readable unit (MB or GB).

    Automatically picks GB for values >= 1 GB, else MB.
    """
    if total_bytes >= 1024 ** 3:
        return f"{total_bytes / (1024 ** 3):,.2f} GB"
    if total_bytes >= 1024 ** 2:
        return f"{total_bytes / (1024 ** 2):,.1f} MB"
    return f"{total_bytes / 1024:,.0f} KB"


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
