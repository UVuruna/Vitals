"""
Color Management

Handles all color logic for the Process Monitor:
- Company-based process name coloring:
    Companies with >1 process name get an individual hue (360°/N evenly spaced).
    Companies with exactly 1 process name share a single "Other" color.
    Processes with no company info at all get a fixed near-white color.
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

from .persistence import load_last_setup, save_last_setup


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

# Default thresholds for CPU Σ total row
_DEFAULT_VALUE_RANGES_CPU_ALL = [
    {"max_pct": 20,  "color": "#5B9BD5"},
    {"max_pct": 40,  "color": "#6AAF6A"},
    {"max_pct": 60,  "color": "#C8B040"},
    {"max_pct": 80,  "color": "#D4803A"},
    {"max_pct": 100, "color": "#C85555"},
]

# Default thresholds for Memory Σ total row (Usage and Commit)
_DEFAULT_VALUE_RANGES_MEM_ALL = [
    {"max_pct": 35,  "color": "#5B9BD5"},
    {"max_pct": 50,  "color": "#6AAF6A"},
    {"max_pct": 65,  "color": "#C8B040"},
    {"max_pct": 80,  "color": "#D4803A"},
    {"max_pct": 100, "color": "#C85555"},
]

# Default thresholds for Network download (% of max download speed)
_DEFAULT_VALUE_RANGES_NET_DL = [
    {"max_pct": 5,   "color": "#5B9BD5"},
    {"max_pct": 15,  "color": "#6AAF6A"},
    {"max_pct": 35,  "color": "#C8B040"},
    {"max_pct": 60,  "color": "#D4803A"},
    {"max_pct": 100, "color": "#C85555"},
]

# Default thresholds for Network upload (% of max upload speed)
_DEFAULT_VALUE_RANGES_NET_UL = [
    {"max_pct": 5,   "color": "#5B9BD5"},
    {"max_pct": 15,  "color": "#6AAF6A"},
    {"max_pct": 35,  "color": "#C8B040"},
    {"max_pct": 60,  "color": "#D4803A"},
    {"max_pct": 100, "color": "#C85555"},
]

# Near-white for processes with no company information at all (text color in table)
_DEFAULT_NO_COMPANY_COLOR = "#D2D2D2"

# HSL parameters for named multi-company hues (vivid pastels, readable on dark background)
_COMPANY_HUE_SATURATION = 0.84
_COMPANY_HUE_LIGHTNESS = 0.84


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

def _company_hue_color(index: int, total: int, saturation: float, lightness: float) -> QColor:
    """
    Return a QColor for a multi-company at discovery index `index` out of `total`.

    Hues are evenly distributed: hue = index / total * 360°.
    Saturation and lightness are user-configurable via ProcessColorManager.
    """
    hue = (index / total) * 360.0
    return QColor.fromHslF(hue / 360.0, saturation, lightness)


class ProcessColorManager:
    """
    Manages color assignment for processes.

    Company-based coloring (three tiers):
      - Multi-company (count > 1): individual hue, 360°/N evenly spaced where N = number
        of such companies. When a new multi-company is discovered N grows and all hues shift.
      - Singleton company (count == 1): shared "Other" color (warm tan).
      - No company info: fixed near-white color.

    Legend shows multi-companies individually, singletons grouped as "Other",
    and no-company processes as "Unknown" (white swatch).

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
        # {company_name -> hue index} — only for companies with count > 1
        self._company_multi_idx: dict[str, int] = {}
        # Total companies that have ever reached count > 1 (used for hue spacing)
        self._company_multi_count: int = 0

        # White for processes with no company info
        self._no_company_color = QColor(_DEFAULT_NO_COMPANY_COLOR)

        # HSL parameters for multi-company hue colors (user-configurable)
        self._hue_saturation: float = _COMPANY_HUE_SATURATION
        self._hue_lightness: float = _COMPANY_HUE_LIGHTNESS

        # Value color ranges — CPU, Memory (Usage), and Memory Total start from same config
        self._value_ranges_cpu: list[tuple[float, QColor]] = []
        self._value_ranges_memory: list[tuple[float, QColor]] = []
        self._value_ranges_memory_total: list[tuple[float, QColor]] = []

        # Value color ranges for the Σ (all processes) total row
        self._value_ranges_cpu_all: list[tuple[float, QColor]] = []
        self._value_ranges_memory_all: list[tuple[float, QColor]] = []
        self._value_ranges_memory_all_total: list[tuple[float, QColor]] = []

        # Network color ranges (download and upload have independent scales)
        self._value_ranges_net_dl: list[tuple[float, QColor]] = []
        self._value_ranges_net_ul: list[tuple[float, QColor]] = []

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

        # CPU, Memory, and Memory Total start from the same config; each tuned independently
        self._value_ranges_cpu = list(parsed_ranges)
        self._value_ranges_memory = list(parsed_ranges)
        self._value_ranges_memory_total = list(parsed_ranges)

        # All-processes total row ranges use separate defaults per mode
        parsed_ranges_cpu_all = [
            (float(entry["max_pct"]), QColor(entry["color"]))
            for entry in _DEFAULT_VALUE_RANGES_CPU_ALL
        ]
        parsed_ranges_mem_all = [
            (float(entry["max_pct"]), QColor(entry["color"]))
            for entry in _DEFAULT_VALUE_RANGES_MEM_ALL
        ]
        self._value_ranges_cpu_all = list(parsed_ranges_cpu_all)
        self._value_ranges_memory_all = list(parsed_ranges_mem_all)
        self._value_ranges_memory_all_total = list(parsed_ranges_mem_all)

        # Network color ranges
        parsed_ranges_net_dl = [
            (float(entry["max_pct"]), QColor(entry["color"]))
            for entry in _DEFAULT_VALUE_RANGES_NET_DL
        ]
        parsed_ranges_net_ul = [
            (float(entry["max_pct"]), QColor(entry["color"]))
            for entry in _DEFAULT_VALUE_RANGES_NET_UL
        ]
        self._value_ranges_net_dl = list(parsed_ranges_net_dl)
        self._value_ranges_net_ul = list(parsed_ranges_net_ul)

        # Load user-set hue params and color thresholds from last_setup.json.
        # Shape checks are required: pre-2.0 versions stored color_thresholds
        # as a flat list — legacy or hand-edited data is discarded, not fatal.
        setup_data = load_last_setup()
        hue = setup_data.get("hue_params", {})
        if isinstance(hue, dict):
            if "saturation" in hue:
                self._hue_saturation = float(hue["saturation"])
            if "lightness" in hue:
                self._hue_lightness = float(hue["lightness"])
        # Restore saved color thresholds (overrides defaults)
        saved_thresholds = setup_data.get("color_thresholds", {})
        if isinstance(saved_thresholds, dict):
            for mode_key in ("cpu", "cpu_all", "memory", "memory_total", "memory_all", "memory_all_total", "net_dl", "net_ul"):
                saved = saved_thresholds.get(mode_key)
                if isinstance(saved, list) and len(saved) == 4:
                    self._apply_threshold_values(mode_key, saved)

    def lookup_company(self, name: str, pid: int):
        """
        Register a process name and resolve its company (background thread).

        Safe to call on every refresh — fast no-op for already-cached names.
        When a company's process-name count reaches 2, it is promoted to a
        multi-company and receives its own hue index.

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

                # Promote to multi-company when count goes from 1 → 2.
                # Hue = multi_idx / multi_count * 360° — recalculated dynamically.
                if prev == 1:
                    self._company_multi_idx[company] = self._company_multi_count
                    self._company_multi_count += 1

    def refresh_active_counts(self, active_names):
        """Recalculate company counts from the set of currently active process names.

        Called every monitor refresh cycle so counts always reflect running processes.
        Only names already resolved in _company_cache are counted — new names are
        handled by lookup_company and will be included on the next cycle.

        Hue assignments (_company_multi_idx) are never removed once granted, keeping
        colors stable even if a company temporarily drops to a single active process.
        """
        counts: dict[str, int] = {}
        with QMutexLocker(self._mutex):
            for name in active_names:
                company = self._company_cache.get(name)
                if company:
                    counts[company] = counts.get(company, 0) + 1
            self._company_counts = counts
            for company, count in counts.items():
                if count > 1 and company not in self._company_multi_idx:
                    self._company_multi_idx[company] = self._company_multi_count
                    self._company_multi_count += 1

    def get_process_color(self, name: str) -> Optional[QColor]:
        """
        Return the color for a process name text (main thread).

        Returns None if the name has not been looked up yet.
        Returns a hue color for multi-company processes (count > 1).
        Returns a hue color for singleton-company processes (count == 1) — last slot in ring.
        Returns _no_company_color for processes with no company info.
        """
        with QMutexLocker(self._mutex):
            if name not in self._company_cache:
                return None
            company = self._company_cache[name]
            if not company:
                return self._no_company_color
            count = self._company_counts.get(company, 0)
            n = self._company_multi_count
            total = n + 1  # +1 reserves last slot for "Other"
            i = n if count <= 1 else self._company_multi_idx.get(company, 0)
            sat = self._hue_saturation
            light = self._hue_lightness

        return _company_hue_color(i, total, sat, light)

    def get_company_name(self, name: str) -> Optional[str]:
        """Return the resolved company name for a process display name, or None if unknown."""
        with QMutexLocker(self._mutex):
            return self._company_cache.get(name)

    def get_hue_params(self) -> tuple[float, float]:
        """Return current (saturation, lightness) for multi-company hue colors."""
        with QMutexLocker(self._mutex):
            return self._hue_saturation, self._hue_lightness

    def update_hue_params(self, saturation: float, lightness: float):
        """Update hue saturation and lightness in-memory and persist to last_setup.json.

        Args:
            saturation: 0.0–1.0
            lightness:  0.0–1.0
        """
        with QMutexLocker(self._mutex):
            self._hue_saturation = saturation
            self._hue_lightness = lightness

        data = load_last_setup()
        data["hue_params"] = {"saturation": saturation, "lightness": lightness}
        save_last_setup(data)

    def _get_ranges_ref(self, mode: str) -> list[tuple[float, QColor]]:
        """Return the range list for a given mode key."""
        mapping = {
            "cpu": self._value_ranges_cpu,
            "cpu_all": self._value_ranges_cpu_all,
            "memory": self._value_ranges_memory,
            "memory_total": self._value_ranges_memory_total,
            "memory_all": self._value_ranges_memory_all,
            "memory_all_total": self._value_ranges_memory_all_total,
            "net_dl": self._value_ranges_net_dl,
            "net_ul": self._value_ranges_net_ul,
        }
        return mapping.get(mode, self._value_ranges_memory)

    def _set_ranges(self, mode: str, ranges: list[tuple[float, QColor]]):
        """Set the range list for a given mode key."""
        if mode == "cpu":
            self._value_ranges_cpu = ranges
        elif mode == "cpu_all":
            self._value_ranges_cpu_all = ranges
        elif mode == "memory_total":
            self._value_ranges_memory_total = ranges
        elif mode == "memory_all":
            self._value_ranges_memory_all = ranges
        elif mode == "memory_all_total":
            self._value_ranges_memory_all_total = ranges
        elif mode == "net_dl":
            self._value_ranges_net_dl = ranges
        elif mode == "net_ul":
            self._value_ranges_net_ul = ranges
        else:
            self._value_ranges_memory = ranges

    def _apply_threshold_values(self, mode: str, thresholds: list):
        """Apply threshold values to the correct range list (in-memory only, no save).

        Must be called while holding self._mutex, or during single-threaded init.
        """
        ranges = self._get_ranges_ref(mode)
        colors = [color for _, color in ranges]
        new_ranges = [(float(t), colors[i]) for i, t in enumerate(thresholds)]
        new_ranges.append((100.0, colors[-1]))
        self._set_ranges(mode, new_ranges)

    def update_value_thresholds(self, thresholds: list, mode: str):
        """Update the 4 color zone thresholds in-memory and persist to last_setup.json.

        Args:
            thresholds: 4 ascending int values [t1, t2, t3, t4] in range 1-99.
            mode:       "cpu", "cpu_all", "memory", "memory_total", "memory_all", or "memory_all_total"
        """
        with QMutexLocker(self._mutex):
            self._apply_threshold_values(mode, thresholds)

        data = load_last_setup()
        # Replace legacy list-shaped color_thresholds (pre-2.0 format) outright
        if not isinstance(data.get("color_thresholds"), dict):
            data["color_thresholds"] = {}
        data["color_thresholds"][mode] = thresholds
        save_last_setup(data)

    def get_value_ranges(self, mode: str) -> list[tuple[float, QColor]]:
        """Return value color ranges for UI display (ColorScaleWidget).

        Args:
            mode: "cpu", "memory", "net_dl", "net_ul", etc.
        """
        with QMutexLocker(self._mutex):
            return list(self._get_ranges_ref(mode))

    def get_legend(self) -> list[tuple[str, QColor, int]]:
        """Return (label, color, count) sorted by count descending.

        Multi-companies (count > 1) are listed individually; hue index = their multi_idx.
        Singleton companies (count == 1) are grouped as "Other"; hue index = last slot.
        Total hue ring size = multi_count + 1 (Other always occupies the last slot).
        No-company processes appear as "Unknown" with a white swatch at the end.
        """
        with QMutexLocker(self._mutex):
            n = self._company_multi_count
            total = n + 1  # Other occupies the last slot
            sat = self._hue_saturation
            light = self._hue_lightness
            result = []
            singleton_count = 0

            for company, count in sorted(
                self._company_counts.items(), key=lambda x: -x[1]
            ):
                if count > 1:
                    i = self._company_multi_idx.get(company, 0)
                    color = _company_hue_color(i, total, sat, light)
                    result.append((company, color, count))
                else:
                    singleton_count += 1

            if singleton_count > 0:
                other_color = _company_hue_color(n, total, sat, light)
                result.append(("Other", other_color, singleton_count))

            no_company_count = sum(
                1 for c in self._company_cache.values() if c is None
            )
            if no_company_count > 0:
                result.append(("Unknown", QColor("#ffffff"), no_company_count))

            return result

    def get_singleton_companies(self) -> list[str]:
        """Return sorted list of company names that appear with exactly 1 active process name."""
        with QMutexLocker(self._mutex):
            return sorted(
                company for company, count in self._company_counts.items()
                if count == 1
            )

    def get_company_processes(self, company: Optional[str]) -> list[str]:
        """Return sorted list of active process display names for the given company.

        Pass None to get processes with no company info (Unknown category).
        """
        with QMutexLocker(self._mutex):
            return sorted(
                name for name, comp in self._company_cache.items()
                if comp == company
            )

    def get_value_color(self, pct: float, mode: str) -> QColor:
        """
        Return a color for a usage percentage mapped to the configured thresholds.

        Args:
            pct:  Usage as 0-100 (e.g. 20.0 for 20%)
            mode: "cpu", "memory", "net_dl", "net_ul", etc.

        Returns:
            QColor from the configured value_colors ranges for the given mode
        """
        with QMutexLocker(self._mutex):
            ranges = self._get_ranges_ref(mode)

        for max_pct_val, color in ranges:
            if pct <= max_pct_val:
                return color
        return ranges[-1][1]
