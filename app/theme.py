"""
Theme Engine — Dark / Light palettes and the live theme flip.

The single source of truth for every color in the app. Two coordinated
palettes (DARK, LIGHT) are selected per **scope**: every widget that paints
a color reads it from the `ThemeScope` that governs it, at paint/restyle
time, never at import time.

Scopes, not one global theme (owner 2026-07-26): each monitor window owns
its own scope, so the Day/Night switch in the CPU header flips the CPU
window ALONE — Memory and Network keep theirs. The app-wide scope
(`app_theme()`) styles the tray menu and the setup screen, and the setup
screen's switch is the GLOBAL one: it forces its choice on every window
through `set_theme_everywhere()`.

Why a live lookup and not a module constant: the old `styles.Colors` was a
frozen dataclass read as `Colors.TEXT` inside module-level f-strings, so
every stylesheet froze the dark palette at import. A runtime flip requires
reading `scope.palette` at restyle time and re-running the stylesheet
builders when `scope.changed` fires.

Color derivation (root Rule #19 — compute, don't generate): the LIGHT
palette's process/value colors are NOT a second hand-authored table. One
set of authored hues is reshaded per theme by `shade_for_theme()`: light
mode gets darker tints (readable on a pale surface), dark mode keeps the
authored light tints. One place to tune, both themes follow.
"""

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor

from .persistence import load_last_setup, save_last_setup


@dataclass(frozen=True)
class Palette:
    """One complete theme palette.

    Chrome tokens (surfaces, text, accent) style the window and dialogs.
    Data tokens (COMPANY_*, HUE_*, VALUE_LIGHTNESS) drive the process- and
    value-coloring in color_management.py, which is why they live here
    rather than in that module: they must flip with the theme.
    """

    name: str

    # --- Surfaces (elevation steps, never flat gray) ---
    BACKGROUND: str
    CARD: str
    HEADER: str
    BORDER: str
    SECTION_BG: str      # table body — one shared surface for all three sections

    # --- Accent (one interactive hue) ---
    ACCENT: str
    ACCENT_HOVER: str

    # --- Confirming action (the Priority dialog's Apply button) ---
    CONFIRM: str
    CONFIRM_HOVER: str

    # --- Text ---
    TEXT: str
    TEXT_MUTED: str
    TEXT_DIM: str
    TEXT_FAINT: str
    TEXT_DISABLED: str

    # --- Header control icons (pause/play, settings gear) ---
    ICON: str
    ICON_HOVER: str

    # --- Temperature thresholds (HWiNFO sensor readout) ---
    TEMP_WARNING: str
    TEMP_CRITICAL: str

    # --- Process name coloring ---
    COMPANY_TOP: str      # the company with the MOST processes — white / black
    COMPANY_UNKNOWN: str  # processes with no company info at all — gray

    # --- Color-wheel defaults for the remaining companies ---
    HUE_SATURATION: float
    HUE_LIGHTNESS: float

    # --- Value (usage %) colors: target lightness for the authored hues ---
    VALUE_LIGHTNESS: float


# The dark palette is the app's original look — navy-tinted surfaces with a
# crimson accent, kept verbatim so an existing user sees no change until the
# switch is thrown.
DARK = Palette(
    name="dark",
    BACKGROUND="#1e1e2e",
    CARD="#2a2a3e",
    HEADER="#3a3a4e",
    BORDER="#4a4a5e",
    SECTION_BG="#2d2d42",
    ACCENT="#e94560",
    ACCENT_HOVER="#ff6b6b",
    CONFIRM="#3a6a3a",
    CONFIRM_HOVER="#4a8a4a",
    TEXT="#ffffff",
    TEXT_MUTED="#aaaaaa",
    TEXT_DIM="#888888",
    TEXT_FAINT="#666666",
    TEXT_DISABLED="#555555",
    ICON="#b9bcd0",
    ICON_HOVER="#ffffff",
    TEMP_WARNING="#ffa500",
    TEMP_CRITICAL="#ff4444",
    COMPANY_TOP="#ffffff",
    COMPANY_UNKNOWN="#9a9aa8",
    HUE_SATURATION=0.84,
    HUE_LIGHTNESS=0.84,
    VALUE_LIGHTNESS=0.60,
)

# The light palette mirrors the dark one's structure with the same indigo
# tint, so the app keeps its identity in both modes: a cool off-white page
# with white cards (elevation rises toward white in light mode) and a
# deepened crimson accent that still clears 4.5:1 against white.
LIGHT = Palette(
    name="light",
    BACKGROUND="#eceef6",
    CARD="#ffffff",
    HEADER="#dfe2ee",
    BORDER="#c7cbdd",
    SECTION_BG="#f7f8fc",
    ACCENT="#d1274a",
    ACCENT_HOVER="#e94560",
    CONFIRM="#2e7d32",
    CONFIRM_HOVER="#388e3c",
    TEXT="#16161f",
    TEXT_MUTED="#4c5162",
    TEXT_DIM="#676d80",
    TEXT_FAINT="#878da0",
    TEXT_DISABLED="#a9aec0",
    ICON="#4c5162",
    ICON_HOVER="#16161f",
    TEMP_WARNING="#b26a00",
    TEMP_CRITICAL="#c62828",
    COMPANY_TOP="#000000",
    COMPANY_UNKNOWN="#6b7280",
    HUE_SATURATION=0.84,
    HUE_LIGHTNESS=0.34,
    VALUE_LIGHTNESS=0.36,
)

THEMES: dict[str, Palette] = {DARK.name: DARK, LIGHT.name: LIGHT}

DEFAULT_THEME = DARK.name


# ---------------------------------------------------------------------------
# Color-wheel geometry — the company hue ramp
# ---------------------------------------------------------------------------

# The wheel runs BLUE -> RED, counter-clockwise on the HSL circle (owner
# 2026-07-24): the first colored slot is blue and each further slot steps
# down through cyan / green / yellow to red. Magenta-purple (240-360 deg) is
# deliberately skipped so the ramp reads as one cool-to-warm scale.
HUE_START_DEG = 240.0   # blue — first colored slot
HUE_END_DEG = 0.0       # red  — last colored slot ("Other")


def wheel_hue(slot: int, slots: int) -> float:
    """Hue in degrees for colored slot `slot` of `slots` (0-based).

    Slot 0 is blue (HUE_START_DEG), the last slot is red (HUE_END_DEG); a
    lone slot gets the blue start rather than a degenerate division.
    """
    if slots <= 1:
        return HUE_START_DEG
    span = HUE_START_DEG - HUE_END_DEG
    return HUE_START_DEG - span * (slot / (slots - 1))


def wheel_color(slot: int, slots: int, saturation: float, lightness: float) -> QColor:
    """Return the QColor for one slot on the blue-to-red company wheel."""
    return QColor.fromHslF(wheel_hue(slot, slots) / 360.0, saturation, lightness)


def shade_for_theme(color: QColor, palette: Palette) -> QColor:
    """Re-shade an authored hue to the given theme's readable lightness.

    Hue and saturation are preserved; only lightness moves — light mode
    darkens the tint so it stays legible on a pale surface, dark mode keeps
    the authored light tint. This is what makes ONE set of configured value
    colors serve both themes (root Rule #19).
    """
    h, s, _l, a = color.getHslF()
    return QColor.fromHslF(max(0.0, h), s, palette.VALUE_LIGHTNESS, a)


# ---------------------------------------------------------------------------
# ThemeScope — one independently themed surface
# ---------------------------------------------------------------------------

class ThemeScope(QObject):
    """The active palette for one surface, plus a flip notification.

    A scope is what makes per-window themes possible: a monitor window reads
    every color from ITS scope, so flipping one window leaves the others
    exactly as they were. `changed` fires AFTER the palette is swapped, so a
    slot can simply re-read `scope.palette` and rebuild its stylesheets.

    `key` is the `last_setup.json` slot the choice is remembered in:
      - `None` — the app-wide scope, saved as `theme`
      - a window key ('cpu' / 'memory' / 'network') — saved as
        `windows.<key>.theme`

    A window that has never been themed on its own starts from the app-wide
    choice, so a fresh install still opens all three gadgets in one look.
    """

    changed = Signal()

    def __init__(self, key: Optional[str] = None):
        super().__init__()
        self._key = key
        data = load_last_setup()
        if key is None:
            saved = data.get("theme")
        else:
            saved = data.get("windows", {}).get(key, {}).get("theme") or data.get("theme")
        self._palette = THEMES.get(saved, THEMES[DEFAULT_THEME])

    @property
    def palette(self) -> Palette:
        """The palette this scope currently paints with."""
        return self._palette

    @property
    def name(self) -> str:
        """The active theme name ('dark' or 'light')."""
        return self._palette.name

    def is_dark(self) -> bool:
        """True when the dark palette is active."""
        return self._palette is DARK

    def next_name(self) -> str:
        """The name of the OTHER theme — what a flip would activate."""
        return LIGHT.name if self.is_dark() else DARK.name

    def set_theme(self, name: str) -> None:
        """Activate a theme by name, remember it, and notify every listener.

        A no-op when the theme is already active, so a global flip that
        matches a window's current theme costs nothing and a switch
        reflecting an external change cannot cause a redundant restyle.
        """
        palette = THEMES[name]
        if palette is self._palette:
            return
        self._palette = palette
        self._persist(name)
        self.changed.emit()

    def _persist(self, name: str) -> None:
        """Write this scope's choice into its own last_setup.json slot."""
        data = load_last_setup()
        if self._key is None:
            data["theme"] = name
        else:
            data.setdefault("windows", {}).setdefault(self._key, {})["theme"] = name
        save_last_setup(data)


_app_scope: Optional[ThemeScope] = None
_window_scopes: dict[str, ThemeScope] = {}


def app_theme() -> ThemeScope:
    """The app-wide scope — tray menu, setup screen, default for a new window."""
    global _app_scope
    if _app_scope is None:
        _app_scope = ThemeScope()
    return _app_scope


def window_theme(key: str) -> ThemeScope:
    """The scope for one monitor window ('cpu' | 'memory' | 'network').

    Created on first use and kept for the app's lifetime, so a window that is
    hidden and shown again comes back in the theme the user left it in.
    """
    scope = _window_scopes.get(key)
    if scope is None:
        scope = ThemeScope(key)
        _window_scopes[key] = scope
    return scope


def set_theme_everywhere(name: str) -> None:
    """Force one theme on the app AND on every monitor window.

    This is what the setup screen's switch does (owner 2026-07-26): unlike a
    window header switch it is global. It moves the app scope, every live
    window scope, and the REMEMBERED choice of a window that is not open yet
    — without that last step, opening that window later would resurrect the
    theme it carried before the global change.
    """
    app_theme().set_theme(name)
    for scope in _window_scopes.values():
        scope.set_theme(name)

    data = load_last_setup()
    stale = [
        entry for entry in data.get("windows", {}).values()
        if entry.get("theme", name) != name
    ]
    for entry in stale:
        entry["theme"] = name
    if stale:
        save_last_setup(data)
