"""
Theme Transition — the snapshot cover that hides the theme repaint.

A live theme flip cannot repaint every widget in one atomic step: window
chrome, table stylesheets and the per-cell process colors land over several
paint passes, so for a moment the window is visibly half-converted (the owner
reported exactly this — a "partial change" with light-theme chrome behind
dark-theme process names).

The fix is the mechanism PromptPainter uses (root Rule #5 — reuse the shape
that already works): grab EVERY visible window into a borderless, always-on-
top cover, composite the NEXT theme's big sun or moon in the middle, force the
covers painted, flip the theme hidden behind them, then fade the covers out.
The user sees the old theme, a sun/moon, and the finished new theme — never
the cascade.

The cover is a pure visual nicety. Any failure to build one is reported and
the flip still happens instantly (root Rule #1's documented-fallback case):
the cover must never be the reason the theme toggle stops working.
"""

import sys

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication, QWidget

from . import icons
from .styles import Transition
from .theme import DARK, LIGHT, theme_manager


class _Cover(QWidget):
    """A frozen snapshot of one window, with the next theme's icon centred.

    Borderless, always on top, click-through and never focus-stealing — it
    exists only to be looked at for the length of the fade.
    """

    def __init__(self, target: QWidget, icon_name: str):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self._snapshot = target.grab()

        size = target.size()
        diameter = min(size.width(), size.height()) * Transition.ICON_FRAC
        diameter = round(
            max(Transition.ICON_MIN, min(Transition.ICON_MAX, diameter))
        )
        self._icon = icons.art(icon_name, diameter, diameter)

        self.setGeometry(QRect(target.mapToGlobal(target.rect().topLeft()), size))
        self._anim: QPropertyAnimation | None = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(0, 0, self._snapshot)
        painter.drawPixmap(
            (self.width() - self._icon.width()) // 2,
            (self.height() - self._icon.height()) // 2,
            self._icon,
        )

    def fade_out(self):
        """Ramp the window opacity 1 -> 0, then destroy the cover.

        Ease-out: the stale snapshot clears fast and then settles, so the new
        theme is readable well before the animation ends.
        """
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(Transition.FADE_MS)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        anim.finished.connect(self.close)
        self._anim = anim  # keep a reference — a local would be collected
        anim.start()


def _visible_windows() -> list[QWidget]:
    """Every visible top-level window of this app, covers themselves excluded."""
    return [
        widget
        for widget in QApplication.topLevelWidgets()
        if widget.isWindow() and widget.isVisible() and not isinstance(widget, _Cover)
    ]


def flip_theme() -> str:
    """Flip Dark <-> Light behind a snapshot cover on EVERY visible window.

    Covering all windows (not just the one that was clicked) matters because
    the three gadgets and any open dialog flip together — one uncovered window
    would show the cascade the cover exists to hide.

    Returns the newly active theme name.
    """
    next_name = LIGHT.name if theme_manager().is_dark() else DARK.name
    icon = icons.KNOB_SUN if next_name == LIGHT.name else icons.KNOB_MOON

    covers: list[_Cover] = []
    for window in _visible_windows():
        try:
            covers.append(_Cover(window, icon))
        except Exception as e:
            # Cosmetic only — never block the flip (see the module docstring)
            print(f"[Vitals] Theme cover unavailable: {e}", file=sys.stderr)

    for cover in covers:
        cover.show()
        cover.raise_()
    # Force the covers actually painted BEFORE anything under them changes
    QApplication.processEvents()

    theme_manager().set_theme(next_name)

    # Let the whole restyle cascade settle while it is still hidden
    QApplication.processEvents()

    for cover in covers:
        cover.fade_out()

    return next_name
