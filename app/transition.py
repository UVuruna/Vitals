"""
Theme Transition — the snapshot cover that hides the theme repaint.

A live theme flip cannot repaint every widget in one atomic step: window
chrome, table stylesheets and the per-cell process colors land over several
paint passes, so for a moment the window is visibly half-converted (the owner
reported exactly this — a "partial change" with light-theme chrome behind
dark-theme process names).

The fix is the mechanism PromptPainter uses (root Rule #5 — reuse the shape
that already works): grab the affected windows into borderless, always-on-top
covers, composite the NEXT theme's big sun or moon in the middle, force the
covers painted, flip the theme hidden behind them, then fade the covers out.
The user sees the old theme, a sun/moon, and the finished new theme — never
the cascade.

Which windows get covered is exactly the flip's reach: `flip_window_theme()`
covers the one window it changes, `flip_app_theme()` covers every visible
window because it changes all of them.

The cover is a pure visual nicety. Any failure to build one is reported and
the flip still happens instantly (root Rule #1's documented-fallback case):
the cover must never be the reason the theme toggle stops working.
"""

import sys
from typing import Sequence

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication, QWidget

from . import icons
from .styles import Transition
from .theme import LIGHT, ThemeScope, app_theme, set_theme_everywhere


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


def _raise_covers(targets: Sequence[QWidget], next_name: str) -> list[_Cover]:
    """Freeze every target under a painted cover carrying the next theme's icon."""
    icon = icons.KNOB_SUN if next_name == LIGHT.name else icons.KNOB_MOON

    covers: list[_Cover] = []
    for window in targets:
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
    return covers


def _drop_covers(covers: list[_Cover]) -> None:
    """Let the restyle cascade settle while still hidden, then fade the covers."""
    QApplication.processEvents()
    for cover in covers:
        cover.fade_out()


def flip_window_theme(scope: ThemeScope, window: QWidget) -> str:
    """Flip ONE window's theme behind a cover on that window alone.

    The switch in a monitor window's header reaches only that window (owner
    2026-07-26), so only that window is covered — the other two gadgets are
    not repainting and must not be frozen for the fade.

    Returns the newly active theme name.
    """
    next_name = scope.next_name()
    covers = _raise_covers([window], next_name)
    scope.set_theme(next_name)
    _drop_covers(covers)
    return next_name


def flip_app_theme() -> str:
    """Flip the app theme and force it on every monitor window, covering all.

    This is the setup screen's switch — the global one. Every visible window
    changes, so every visible window is covered: one uncovered gadget would
    show the cascade the cover exists to hide.

    Returns the newly active theme name.
    """
    next_name = app_theme().next_name()
    covers = _raise_covers(_visible_windows(), next_name)
    set_theme_everywhere(next_name)
    _drop_covers(covers)
    return next_name
