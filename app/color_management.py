"""
Color Management

Handles all color logic for the Process Monitor:
- Company-based process name coloring (reads Windows CompanyName from exe, once per new process)
- Value-based usage coloring (normalized % ranges)
- Application color palette (moved from styles.py)

Config is read from config/config.json — edit that file to tune colors and thresholds.
"""

import ctypes
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import psutil
from PySide6.QtCore import QMutex, QMutexLocker
from PySide6.QtGui import QColor


# ---------------------------------------------------------------------------
# Application color palette (dark theme constants)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Colors:
    """Application color palette (dark theme)."""

    BACKGROUND = "#1e1e2e"
    CARD = "#2a2a3e"
    HEADER = "#3a3a4e"
    ACCENT = "#e94560"
    TEXT = "#ffffff"
    TEXT_MUTED = "#aaaaaa"

    CURRENT_BG = "#2d2d42"
    HISTORY_BG = "#2a3a3e"


# ---------------------------------------------------------------------------
# Default fallbacks (used if config.json is missing or incomplete)
# ---------------------------------------------------------------------------

_DEFAULT_VALUE_RANGES = [
    {"max_pct": 3,   "color": "#5B9BD5"},
    {"max_pct": 8,   "color": "#6AAF6A"},
    {"max_pct": 20,  "color": "#C8B040"},
    {"max_pct": 40,  "color": "#D4803A"},
    {"max_pct": 100, "color": "#C85555"},
]

_DEFAULT_COMPANY_PALETTE = [
    "#C99B9B", "#C9AE9B", "#C9C09B", "#C0C99B", "#AEC99C",
    "#9CC99C", "#9CC9AE", "#9CC9C0", "#9CC0C9", "#9CAEC9",
    "#9C9CC9", "#AE9CC9", "#C09CC9", "#C99CC0", "#C99CAE",
]

_DEFAULT_OTHER_COLOR = "#888888"


# ---------------------------------------------------------------------------
# Windows Version API — reads CompanyName from PE version info
# ---------------------------------------------------------------------------

def _get_config_path() -> Path:
    """Resolve config/config.json path for both dev and frozen (PyInstaller) env."""
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent.parent
    return base / "config" / "config.json"


try:
    _ver_dll = ctypes.windll.version
    _GetFileVersionInfoSizeW = _ver_dll.GetFileVersionInfoSizeW
    _GetFileVersionInfoW = _ver_dll.GetFileVersionInfoW
    _VerQueryValueW = _ver_dll.VerQueryValueW
    _VERSION_API_AVAILABLE = True
except Exception:
    _VERSION_API_AVAILABLE = False


def _read_company_name(exe_path: str) -> Optional[str]:
    """
    Read CompanyName string from Windows PE version info.

    Uses GetFileVersionInfoW + VerQueryValueW via ctypes.
    Returns the company name string, or None if unavailable.
    """
    if not _VERSION_API_AVAILABLE or not exe_path:
        return None

    try:
        size = _GetFileVersionInfoSizeW(exe_path, None)
        if not size:
            return None

        buf = ctypes.create_string_buffer(size)
        if not _GetFileVersionInfoW(exe_path, 0, size, buf):
            return None

        # Get translation table (language + codepage pairs)
        p_trans = ctypes.c_void_p()
        trans_len = ctypes.c_uint()
        if not _VerQueryValueW(buf, r"\VarFileInfo\Translation",
                               ctypes.byref(p_trans), ctypes.byref(trans_len)):
            return None

        if not p_trans.value or trans_len.value < 4:
            return None

        # First LANGANDCODEPAGE entry: WORD language, WORD codepage
        trans = ctypes.cast(p_trans, ctypes.POINTER(ctypes.c_uint16))
        lang = trans[0]
        cp   = trans[1]

        key = f"\\StringFileInfo\\{lang:04X}{cp:04X}\\CompanyName"

        p_val = ctypes.c_void_p()
        val_len = ctypes.c_uint()
        if not _VerQueryValueW(buf, key, ctypes.byref(p_val), ctypes.byref(val_len)):
            return None

        if not p_val.value or not val_len.value:
            return None

        company = ctypes.wstring_at(p_val.value, val_len.value).rstrip('\x00').strip()
        return company if company else None

    except Exception:
        return None


# ---------------------------------------------------------------------------
# ProcessColorManager — singleton, thread-safe
# ---------------------------------------------------------------------------

class ProcessColorManager:
    """
    Manages color assignment for processes.

    Company-based coloring:
      - lookup_company() is called from the background thread for each new process name.
      - get_process_color() is called from the main thread during table rendering.
      - Companies with >1 distinct process names receive a unique palette color.
      - Companies with only 1 process name get the "other" color (neutral).

    Value-based coloring:
      - get_value_color() maps a normalized 0-100% to a color from the configured ranges.
    """

    _instance: Optional['ProcessColorManager'] = None
    _class_lock = QMutex()

    def __new__(cls):
        with QMutexLocker(cls._class_lock):
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._mutex = QMutex()

        # {process_display_name -> company_name or None}
        self._company_cache: dict[str, Optional[str]] = {}
        # {company_name -> count of distinct process names}
        self._company_counts: dict[str, int] = {}
        # {company_name -> QColor} — only set when count goes above 1
        self._color_assignments: dict[str, QColor] = {}
        self._next_palette_idx = 0

        # Loaded from config.json
        self._value_ranges: list[tuple[float, QColor]] = []
        self._company_palette: list[QColor] = []
        self._other_color = QColor(_DEFAULT_OTHER_COLOR)

        self._load_config()

    def _load_config(self):
        """Load color configuration from config/config.json."""
        config_path = _get_config_path()

        value_ranges_data = _DEFAULT_VALUE_RANGES
        company_palette_data = _DEFAULT_COMPANY_PALETTE
        other_color_str = _DEFAULT_OTHER_COLOR

        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    data = json.load(f)

                if "value_colors" in data and "ranges" in data["value_colors"]:
                    value_ranges_data = data["value_colors"]["ranges"]

                if "company_colors" in data:
                    cc = data["company_colors"]
                    if "palette" in cc:
                        company_palette_data = cc["palette"]
                    if "other_color" in cc:
                        other_color_str = cc["other_color"]

            except Exception:
                pass

        self._value_ranges = [
            (float(entry["max_pct"]), QColor(entry["color"]))
            for entry in value_ranges_data
        ]
        self._company_palette = [QColor(c) for c in company_palette_data]
        self._other_color = QColor(other_color_str)

    def lookup_company(self, name: str, pid: int):
        """
        Register a process name and resolve its company (background thread).

        Safe to call on every refresh — fast no-op for already-cached names.

        Args:
            name: Display process name (after alias mapping)
            pid:  A representative PID for this process name
        """
        with QMutexLocker(self._mutex):
            if name in self._company_cache:
                return

        # Read exe path and company outside the lock (slow I/O)
        company: Optional[str] = None
        try:
            exe_path = psutil.Process(pid).exe()
            company = _read_company_name(exe_path)
        except Exception:
            pass

        with QMutexLocker(self._mutex):
            if name in self._company_cache:
                return  # Another thread beat us (shouldn't happen — single BG thread)

            self._company_cache[name] = company

            if company:
                prev = self._company_counts.get(company, 0)
                self._company_counts[company] = prev + 1

                # Assign a palette color the moment a company reaches 2 distinct processes
                if prev == 1 and company not in self._color_assignments:
                    if self._next_palette_idx < len(self._company_palette):
                        self._color_assignments[company] = (
                            self._company_palette[self._next_palette_idx]
                        )
                        self._next_palette_idx += 1

    def get_process_color(self, name: str) -> Optional[QColor]:
        """
        Return the color for a process name text (main thread).

        Returns None for unknown names (not yet looked up).
        Returns the assigned company color for multi-process companies.
        Returns other_color for singleton companies.
        """
        with QMutexLocker(self._mutex):
            if name not in self._company_cache:
                return None
            company = self._company_cache[name]
            if not company:
                return None
            return self._color_assignments.get(company, self._other_color)

    def update_value_thresholds(self, thresholds: list):
        """Update the 4 color zone thresholds in-memory (session only, resets on restart).

        Args:
            thresholds: 4 ascending int values [t1, t2, t3, t4] in range 1-99.
        """
        with QMutexLocker(self._mutex):
            colors = [color for _, color in self._value_ranges]
            self._value_ranges = [
                (float(t), colors[i]) for i, t in enumerate(thresholds)
            ]
            self._value_ranges.append((100.0, colors[-1]))

    def get_value_ranges(self) -> list[tuple[float, QColor]]:
        """Return value color ranges for UI display (ColorScaleWidget)."""
        with QMutexLocker(self._mutex):
            return list(self._value_ranges)

    def get_legend(self) -> list[tuple[str, QColor, int]]:
        """Return (company, color, distinct_process_count) sorted by count descending."""
        with QMutexLocker(self._mutex):
            result = []
            for company, count in sorted(
                self._company_counts.items(), key=lambda x: -x[1]
            ):
                color = self._color_assignments.get(company, self._other_color)
                result.append((company, color, count))
            return result

    def get_value_color(self, pct: float) -> QColor:
        """
        Return a color for a usage percentage mapped directly to the configured thresholds.

        Args:
            pct: Usage as 0-100 (e.g. 20.0 for 20%)

        Returns:
            QColor from the configured value_colors ranges
        """
        with QMutexLocker(self._mutex):
            ranges = self._value_ranges

        for max_pct_val, color in ranges:
            if pct <= max_pct_val:
                return color
        return ranges[-1][1]
