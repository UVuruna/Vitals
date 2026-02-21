"""
Color Management

Handles all color logic for the Process Monitor:
- Company-based process name coloring — hues distributed evenly as 360°/N where N grows
  as new companies are discovered; all named-company processes get a color, no-company gray.
- Value-based usage coloring (per-monitor-mode thresholds: CPU and Memory are independent)
- Application color palette (moved from styles.py)

Config is read from config/config.json — edit that file to tune value color thresholds.
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

# Gray for processes with no company information at all
_DEFAULT_NO_COMPANY_COLOR = "#999999"

# HSL parameters for named-company hues (pastel, readable on dark background)
_COMPANY_HUE_SATURATION = 0.35
_COMPANY_HUE_LIGHTNESS = 0.70


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

def _company_hue_color(index: int, total: int) -> QColor:
    """
    Return a pastel QColor for company at discovery index `index` out of `total`.

    Hues are evenly distributed: hue = index / total * 360°.
    Saturation and lightness are fixed for readability on dark backgrounds.
    """
    hue = (index / total) * 360.0
    return QColor.fromHslF(hue / 360.0, _COMPANY_HUE_SATURATION, _COMPANY_HUE_LIGHTNESS)


class ProcessColorManager:
    """
    Manages color assignment for processes.

    Company-based coloring:
      - lookup_company() is called from the background thread for each new process name.
      - get_process_color() is called from the main thread during table rendering.
      - Every named company gets a hue computed as index/N * 360° where N is the total
        number of distinct named companies discovered so far. Colors shift as N grows.
      - Processes with no company info get a fixed gray "no company" color.

    Value-based coloring:
      - get_value_color(pct, mode) maps 0-100% to a color using per-mode thresholds.
      - CPU and Memory maintain independent threshold lists.
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
        # {company_name -> discovery index} — used for hue computation
        self._company_idx: dict[str, int] = {}
        # Total named companies discovered so far
        self._company_count_named: int = 0

        # Gray for processes with no company info
        self._no_company_color = QColor(_DEFAULT_NO_COMPANY_COLOR)

        # Value color ranges — CPU and Memory start from same config, tuned independently
        self._value_ranges_cpu: list[tuple[float, QColor]] = []
        self._value_ranges_memory: list[tuple[float, QColor]] = []

        self._load_config()

    def _load_config(self):
        """Load color configuration from config/config.json."""
        config_path = _get_config_path()

        value_ranges_data = _DEFAULT_VALUE_RANGES

        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    data = json.load(f)

                if "value_colors" in data and "ranges" in data["value_colors"]:
                    value_ranges_data = data["value_colors"]["ranges"]

            except Exception:
                pass

        parsed_ranges = [
            (float(entry["max_pct"]), QColor(entry["color"]))
            for entry in value_ranges_data
        ]

        # CPU and Memory start from the same config; each can be tuned independently
        self._value_ranges_cpu = list(parsed_ranges)
        self._value_ranges_memory = list(parsed_ranges)

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

                # Record discovery index on first encounter of this company.
                # Hue = discovery_index / total_companies * 360° — recalculated dynamically.
                if prev == 0:
                    self._company_idx[company] = self._company_count_named
                    self._company_count_named += 1

    def get_process_color(self, name: str) -> Optional[QColor]:
        """
        Return the color for a process name text (main thread).

        Returns None for unknown names (not yet looked up).
        Returns a hue color (evenly distributed across 360°) for named-company processes.
        Returns no_company_color (gray) for processes with no company info.
        """
        with QMutexLocker(self._mutex):
            if name not in self._company_cache:
                return None
            company = self._company_cache[name]
            if not company:
                return self._no_company_color
            n = self._company_count_named
            i = self._company_idx.get(company, 0)

        return _company_hue_color(i, n)

    def update_value_thresholds(self, thresholds: list, mode: str):
        """Update the 4 color zone thresholds in-memory (session only, resets on restart).

        Args:
            thresholds: 4 ascending int values [t1, t2, t3, t4] in range 1-99.
            mode:       "cpu" or "memory"
        """
        with QMutexLocker(self._mutex):
            ranges = self._value_ranges_cpu if mode == "cpu" else self._value_ranges_memory
            colors = [color for _, color in ranges]
            new_ranges = [(float(t), colors[i]) for i, t in enumerate(thresholds)]
            new_ranges.append((100.0, colors[-1]))
            if mode == "cpu":
                self._value_ranges_cpu = new_ranges
            else:
                self._value_ranges_memory = new_ranges

    def get_value_ranges(self, mode: str) -> list[tuple[float, QColor]]:
        """Return value color ranges for UI display (ColorScaleWidget).

        Args:
            mode: "cpu" or "memory"
        """
        with QMutexLocker(self._mutex):
            ranges = self._value_ranges_cpu if mode == "cpu" else self._value_ranges_memory
            return list(ranges)

    def get_legend(self) -> list[tuple[str, QColor, int]]:
        """Return (label, color, count) sorted by count descending.

        Hues are recomputed dynamically from current total company count.
        Includes an 'Unknown' entry at the end for processes with no company info.
        """
        with QMutexLocker(self._mutex):
            n = self._company_count_named
            result = []
            for company, count in sorted(
                self._company_counts.items(), key=lambda x: -x[1]
            ):
                i = self._company_idx.get(company, 0)
                color = _company_hue_color(i, n) if n > 0 else self._no_company_color
                result.append((company, color, count))

            no_company_count = sum(
                1 for company in self._company_cache.values() if company is None
            )
            if no_company_count > 0:
                result.append(("Unknown", self._no_company_color, no_company_count))

            return result

    def get_value_color(self, pct: float, mode: str) -> QColor:
        """
        Return a color for a usage percentage mapped to the configured thresholds.

        Args:
            pct:  Usage as 0-100 (e.g. 20.0 for 20%)
            mode: "cpu" or "memory"

        Returns:
            QColor from the configured value_colors ranges for the given mode
        """
        with QMutexLocker(self._mutex):
            ranges = self._value_ranges_cpu if mode == "cpu" else self._value_ranges_memory

        for max_pct_val, color in ranges:
            if pct <= max_pct_val:
                return color
        return ranges[-1][1]
