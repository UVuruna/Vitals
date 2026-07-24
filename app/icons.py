"""
SVG Icons — rendering and theme tinting.

Every icon in the app is ONE master SVG in assets/icons/, rasterized on
demand at the size and tint the caller needs (root Rule #19 — compute the
variants, never ship a per-theme/per-size copy of the same glyph).

Two kinds of art live here:
  - GLYPHS (pause, play, settings) — authored as solid white shapes and
    re-tinted at render time, so they follow the active theme's ICON token.
  - ART (the Day/Night switch track and its sun/moon knob) — full-color
    illustrations rendered as-is, shared with the owner's website switch.

Rasterized results are cached: the same (name, size, color) is rendered
once per process, so the switch animation and a theme flip only blit.
"""

from functools import lru_cache

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QPushButton

from .persistence import get_base_path
from .theme import theme, theme_manager

# Glyph names (assets/icons/<name>.svg)
PAUSE = "pause"
PLAY = "play"
SETTINGS = "settings"

# Day/Night switch art
TRACK_NIGHT = "switch_night"
TRACK_DAY = "switch_day"
KNOB_MOON = "moon"
KNOB_SUN = "sun"


def icon_path(name: str) -> str:
    """Absolute path to an icon SVG (works frozen and from source)."""
    return str(get_base_path() / "assets" / "icons" / f"{name}.svg")


@lru_cache(maxsize=64)
def _render(name: str, width: int, height: int) -> QPixmap:
    """Rasterize an SVG into a transparent pixmap of exactly width x height."""
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(icon_path(name)).render(painter, QRectF(0, 0, width, height))
    painter.end()
    return pixmap


@lru_cache(maxsize=64)
def glyph(name: str, size: int, color: str) -> QPixmap:
    """Return a single-color glyph pixmap tinted to `color`.

    The master SVG is authored solid white; SourceIn composition replaces
    its color while keeping the anti-aliased alpha edges.
    """
    pixmap = _render(name, size, size).copy()
    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(color))
    painter.end()
    return pixmap


def art(name: str, width: int, height: int) -> QPixmap:
    """Return full-color illustration art (switch track / knob) at a size."""
    return _render(name, width, height)


def swatch(color: QColor, size: int = 12, radius: int = 3) -> QIcon:
    """Return a rounded color-chip icon — used as a menu/legend color swatch."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
    painter.end()
    return QIcon(pixmap)


class IconButton(QPushButton):
    """Flat, borderless icon button that re-tints itself on a theme flip.

    Used for the header's pause/play and settings controls — the two actions
    that replaced the old menu bar (owner 2026-07-24). The glyph name may be
    swapped at runtime (`set_glyph`) so one button can toggle pause/play.
    """

    def __init__(self, name: str, tooltip: str, size: int = 18, parent=None):
        super().__init__(parent)
        self._name = name
        self._glyph_size = size
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(size + 10, size + 10)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.apply_theme()
        theme_manager().changed.connect(self.apply_theme)

    def set_glyph(self, name: str) -> None:
        """Swap the displayed glyph (e.g. pause <-> play)."""
        self._name = name
        self.apply_theme()

    def apply_theme(self) -> None:
        """Re-tint the glyph and restyle the hover surface for the active theme."""
        palette = theme()
        self.setIcon(QIcon(glyph(self._name, self._glyph_size, palette.ICON)))
        self.setIconSize(
            glyph(self._name, self._glyph_size, palette.ICON).size()
        )
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {palette.HEADER};
            }}
        """)
