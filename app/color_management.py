"""
Color Management

Handles all data-driven color logic for Vitals:

- Company-based process name coloring, ranked by how many process names a
  company runs (owner 2026-07-24):
    1. The company with the MOST processes gets the theme's plain contrast
       color — white on dark, black on light. It is almost always the OS
       vendor, so the busiest name in the table stays neutral.
    2. Every other named company walks a BLUE -> RED color wheel, running
       counter-clockwise from blue through cyan/green/yellow to red as the
       process count drops. Companies with a single process name share the
       last (red) slot as "Other".
    3. Processes with no company information at all are GRAY — the reserved
       "Unknown" color, never part of the wheel.
- Value-based usage coloring (per-monitor-mode thresholds: CPU, Memory and
  Network are independent).

Both are theme-aware. The wheel's saturation/lightness and the value-color
lightness come from the ACTIVE palette (theme.py), and every cached color is
rebuilt when the theme flips — light mode gets darker tints for contrast on
a pale surface, dark mode lighter ones.

Config is read from config/config.json — edit that file to tune value color
thresholds. The authored hexes are the hues only; each theme re-shades them
(root Rule #19 — compute the variants, never author them twice).
"""

import ctypes
import json
import sys
from typing import Optional

import psutil
from PySide6.QtCore import QMutex, QMutexLocker
from PySide6.QtGui import QColor

from .persistence import get_base_path, load_last_setup, save_last_setup
from .theme import shade_for_theme, theme, theme_manager, wheel_color


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

_MODE_KEYS = (
    "cpu", "cpu_all", "memory", "memory_total",
    "memory_all", "memory_all_total", "net_dl", "net_ul",
)


# ---------------------------------------------------------------------------
# Windows Version API — reads CompanyName from PE version info
# ---------------------------------------------------------------------------

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

    Company-based coloring (three tiers, ranked by process-name count):
      - Rank 0 (most process names): the theme's COMPANY_TOP contrast color
        (white on dark, black on light).
      - Ranks 1..N and "Other": the BLUE -> RED wheel. Rank 1 is blue; each
        lower rank steps toward red; the singleton-company group "Other"
        always occupies the last (red) slot.
      - No company info: the theme's reserved COMPANY_UNKNOWN gray.

    Ranks are recomputed every refresh from the ACTIVE process set, so the
    ordering the legend shows is exactly the ordering the colors follow.
    Ties are broken by company name so equal counts never flicker.

    Value-based coloring:
      - get_value_color(pct, mode) maps 0-100% to a color using per-mode
        thresholds, re-shaded for the active theme.
      - Each mode maintains an independent threshold list.
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
        # {company_name -> rank} for companies with more than one process name;
        # rank 0 = most processes. Recomputed every refresh_active_counts().
        self._company_rank: dict[str, int] = {}
        # Number of slots on the blue->red wheel (ranks 1.. plus "Other")
        self._wheel_slots: int = 1

        # Per-theme wheel saturation/lightness, seeded from each palette and
        # overridden by whatever the user saved for that theme.
        self._hue_params: dict[str, tuple[float, float]] = {}

        # Value color ranges as AUTHORED (theme-neutral hues + thresholds)
        self._value_ranges: dict[str, list[tuple[float, QColor]]] = {}
        # The same ranges re-shaded for the ACTIVE theme (what the UI reads)
        self._themed_ranges: dict[str, list[tuple[float, QColor]]] = {}

        self._load_config()
        theme_manager().changed.connect(self._on_theme_changed)

    # --- configuration ------------------------------------------------

    def _load_config(self):
        """Load color configuration from config/config.json.

        An unreadable or invalid config.json is reported to stderr and the
        _DEFAULT_VALUE_RANGES fallback is kept (documented behavior).
        """
        config_path = get_base_path() / "config" / "config.json"

        value_ranges_data = _DEFAULT_VALUE_RANGES

        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    data = json.load(f)

                if "value_colors" in data and "ranges" in data["value_colors"]:
                    value_ranges_data = data["value_colors"]["ranges"]

            except (OSError, ValueError) as e:
                print(f"[Vitals] Invalid {config_path}: {e} - using default value colors", file=sys.stderr)

        def parse(entries) -> list[tuple[float, QColor]]:
            return [(float(e["max_pct"]), QColor(e["color"])) for e in entries]

        # CPU, Memory and Memory Total start from the config ranges; the Σ
        # total rows and the two network scales have their own defaults.
        per_process = parse(value_ranges_data)
        cpu_all = parse(_DEFAULT_VALUE_RANGES_CPU_ALL)
        mem_all = parse(_DEFAULT_VALUE_RANGES_MEM_ALL)
        self._value_ranges = {
            "cpu": list(per_process),
            "memory": list(per_process),
            "memory_total": list(per_process),
            "cpu_all": list(cpu_all),
            "memory_all": list(mem_all),
            "memory_all_total": list(mem_all),
            "net_dl": parse(_DEFAULT_VALUE_RANGES_NET_DL),
            "net_ul": parse(_DEFAULT_VALUE_RANGES_NET_UL),
        }

        setup_data = load_last_setup()

        # Per-theme wheel params: seeded from each palette, overridden by the
        # user's saved values for that theme. Shape checks are required —
        # pre-2.2 versions stored ONE flat {saturation, lightness} pair, which
        # is discarded rather than applied to both themes.
        from .theme import THEMES
        saved_hue = setup_data.get("hue_params", {})
        for name, palette in THEMES.items():
            sat, light = palette.HUE_SATURATION, palette.HUE_LIGHTNESS
            entry = saved_hue.get(name) if isinstance(saved_hue, dict) else None
            if isinstance(entry, dict):
                sat = float(entry.get("saturation", sat))
                light = float(entry.get("lightness", light))
            self._hue_params[name] = (sat, light)

        # Restore saved color thresholds (overrides defaults)
        saved_thresholds = setup_data.get("color_thresholds", {})
        if isinstance(saved_thresholds, dict):
            for mode_key in _MODE_KEYS:
                saved = saved_thresholds.get(mode_key)
                if isinstance(saved, list) and len(saved) == 4:
                    self._apply_threshold_values(mode_key, saved)

        self._rebuild_themed_ranges()

    def _rebuild_themed_ranges(self):
        """Re-shade every authored value range for the ACTIVE theme.

        Called on load, on a threshold edit and on a theme flip — so
        get_value_color() stays a plain list walk on the refresh hot path.
        Must be called while holding self._mutex, or during single-threaded init.
        """
        palette = theme()
        self._themed_ranges = {
            mode: [(t, shade_for_theme(color, palette)) for t, color in ranges]
            for mode, ranges in self._value_ranges.items()
        }

    def _on_theme_changed(self):
        """Rebuild every theme-derived color cache after a Day/Night flip."""
        with QMutexLocker(self._mutex):
            self._rebuild_themed_ranges()

    # --- company discovery --------------------------------------------

    def lookup_company(self, name: str, pid: int):
        """
        Register a process name and resolve its company (background thread).

        Safe to call on every refresh — fast no-op for already-cached names.
        Ranking itself is done by refresh_active_counts(), which runs right
        after this on the same cycle.

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
            self._company_cache.setdefault(name, company)

    def refresh_active_counts(self, active_names):
        """Recalculate company counts and ranks from the ACTIVE process names.

        Called every monitor refresh cycle so both counts and colors always
        reflect the processes actually running. Only names already resolved
        in _company_cache are counted — new names are handled by
        lookup_company and are included on the next cycle.

        Ranking is by process-name count descending, ties broken by company
        name, so two companies with equal counts keep a stable order (and
        therefore stable colors) between cycles.
        """
        counts: dict[str, int] = {}
        with QMutexLocker(self._mutex):
            for name in active_names:
                company = self._company_cache.get(name)
                if company:
                    counts[company] = counts.get(company, 0) + 1
            self._company_counts = counts

            multi = sorted(
                ((c, n) for c, n in counts.items() if n > 1),
                key=lambda item: (-item[1], item[0]),
            )
            self._company_rank = {company: i for i, (company, _n) in enumerate(multi)}
            # Rank 0 is the plain contrast color, so the wheel carries ranks
            # 1.. plus the "Other" slot — at least one slot always exists.
            self._wheel_slots = max(len(multi) - 1, 0) + 1

    # --- company colors -----------------------------------------------

    def _slot_color(self, company: Optional[str]) -> QColor:
        """Return the wheel/contrast color for a company. Caller holds the mutex."""
        palette = theme()
        rank = self._company_rank.get(company)
        if rank == 0:
            return QColor(palette.COMPANY_TOP)
        slots = self._wheel_slots
        # An unranked company is a singleton — it shares the last ("Other") slot
        slot = slots - 1 if rank is None else rank - 1
        sat, light = self._hue_params[palette.name]
        return wheel_color(slot, slots, sat, light)

    def get_process_color(self, name: str) -> Optional[QColor]:
        """
        Return the color for a process name text (main thread).

        Returns None if the name has not been looked up yet, the theme's
        COMPANY_UNKNOWN gray for processes with no company info, and the
        ranked contrast/wheel color otherwise.
        """
        with QMutexLocker(self._mutex):
            if name not in self._company_cache:
                return None
            company = self._company_cache[name]
            if not company:
                return QColor(theme().COMPANY_UNKNOWN)
            return self._slot_color(company)

    def get_company_name(self, name: str) -> Optional[str]:
        """Return the resolved company name for a process display name, or None if unknown."""
        with QMutexLocker(self._mutex):
            return self._company_cache.get(name)

    def get_hue_params(self) -> tuple[float, float]:
        """Return the ACTIVE theme's (saturation, lightness) for wheel colors."""
        with QMutexLocker(self._mutex):
            return self._hue_params[theme().name]

    def update_hue_params(self, saturation: float, lightness: float):
        """Update the ACTIVE theme's wheel saturation/lightness and persist it.

        Each theme keeps its own pair — light mode needs darker, more
        saturated tints than dark mode, so tuning one never disturbs the other.

        Args:
            saturation: 0.0–1.0
            lightness:  0.0–1.0
        """
        name = theme().name
        with QMutexLocker(self._mutex):
            self._hue_params[name] = (saturation, lightness)

        data = load_last_setup()
        # Replace the pre-2.2 flat {saturation, lightness} shape outright
        if not isinstance(data.get("hue_params"), dict) or "saturation" in data.get("hue_params", {}):
            data["hue_params"] = {}
        data["hue_params"][name] = {"saturation": saturation, "lightness": lightness}
        save_last_setup(data)

    # --- value colors -------------------------------------------------

    def _apply_threshold_values(self, mode: str, thresholds: list):
        """Apply threshold values to the authored range list (no save).

        Must be called while holding self._mutex, or during single-threaded init.
        """
        colors = [color for _, color in self._value_ranges[mode]]
        new_ranges = [(float(t), colors[i]) for i, t in enumerate(thresholds)]
        new_ranges.append((100.0, colors[-1]))
        self._value_ranges[mode] = new_ranges

    def update_value_thresholds(self, thresholds: list, mode: str):
        """Update the 4 color zone thresholds in-memory and persist to last_setup.json.

        Args:
            thresholds: 4 ascending int values [t1, t2, t3, t4] in range 1-99.
            mode:       one of _MODE_KEYS
        """
        with QMutexLocker(self._mutex):
            self._apply_threshold_values(mode, thresholds)
            self._rebuild_themed_ranges()

        data = load_last_setup()
        # Replace legacy list-shaped color_thresholds (pre-2.0 format) outright
        if not isinstance(data.get("color_thresholds"), dict):
            data["color_thresholds"] = {}
        data["color_thresholds"][mode] = thresholds
        save_last_setup(data)

    def get_value_ranges(self, mode: str) -> list[tuple[float, QColor]]:
        """Return theme-shaded value color ranges for UI display (ColorScaleWidget).

        Args:
            mode: one of _MODE_KEYS
        """
        with QMutexLocker(self._mutex):
            return list(self._themed_ranges[mode])

    def get_value_color(self, pct: float, mode: str) -> QColor:
        """
        Return a color for a usage percentage mapped to the configured thresholds.

        Args:
            pct:  Usage as 0-100 (e.g. 20.0 for 20%)
            mode: one of _MODE_KEYS

        Returns:
            The theme-shaded color for the zone `pct` falls into.
        """
        with QMutexLocker(self._mutex):
            ranges = self._themed_ranges[mode]

        for max_pct_val, color in ranges:
            if pct <= max_pct_val:
                return color
        return ranges[-1][1]

    # --- legend -------------------------------------------------------

    def get_legend(self) -> list[tuple[str, QColor, int]]:
        """Return (label, color, count) sorted by count descending.

        The order IS the color ranking: the first entry carries the plain
        contrast color, the rest walk the blue->red wheel. Singleton
        companies are grouped into "Other" (the last, red slot) and
        processes with no company info appear last as "Unknown" (gray).
        """
        with QMutexLocker(self._mutex):
            result = []
            singleton_count = 0

            for company, count in sorted(
                self._company_counts.items(), key=lambda x: (-x[1], x[0])
            ):
                if count > 1:
                    result.append((company, self._slot_color(company), count))
                else:
                    singleton_count += 1

            if singleton_count > 0:
                result.append(("Other", self._slot_color(None), singleton_count))

            no_company_count = sum(
                1 for c in self._company_cache.values() if c is None
            )
            if no_company_count > 0:
                result.append(
                    ("Unknown", QColor(theme().COMPANY_UNKNOWN), no_company_count)
                )

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
