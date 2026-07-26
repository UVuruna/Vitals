"""
DayNightSwitch — the Day/Night theme toggle.

An image pill ported from the owner's website switch (the same track and
sun/moon art PromptPainter uses, root Rule #5 — reuse, never re-author):
OFF/left is the MOON on a dark starfield track, ON/right is the SUN on a
sky-and-clouds track. A click flips a theme synchronously, then the knob
slides as an eased flourish.

The switch is deliberately dumb about REACH: it renders and animates one
`ThemeScope`, and delegates the actual flip to the callable it was built
with. That is what lets the same widget be a per-window toggle in a monitor
header (`flip_window_theme`) and the global toggle on the setup screen
(`flip_app_theme`) with no branch inside it. Each switch follows its own
scope's `changed`, so a global flip slides all four at once while a window
flip slides only that window's.
"""

from typing import Callable

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from . import icons
from .styles import Switch
from .theme import ThemeScope


class DayNightSwitch(QWidget):
    """The mini Day/Night pill toggle shown in each window header.

    Geometry scales from `Switch.HEIGHT` (styles.py); the four pixmaps
    (two tracks, two knob sizes for rest/hover) are rasterized ONCE at
    construction and cached in icons.py, so a slide only blits.

    Args:
        scope: the ThemeScope this switch displays.
        flip:  what a click performs — the transition that changes `scope`
               (and, for the global switch, everything else with it).
    """

    def __init__(self, scope: ThemeScope, flip: Callable[[], str], parent=None):
        super().__init__(parent)
        self._theme = scope
        self._flip = flip
        self._track_w = round(Switch.HEIGHT * Switch.ASPECT)
        self._knob_d = round(Switch.HEIGHT * Switch.KNOB_FACTOR)
        self._pad = Switch.PAD
        inset = (Switch.HEIGHT - self._knob_d) / 2
        self._x_off = self._pad + inset
        self._x_on = self._pad + self._track_w - self._knob_d - inset

        self.setFixedSize(
            self._track_w + 2 * self._pad, Switch.HEIGHT + 2 * self._pad
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # No default tooltip: the reach differs per switch, and every caller
        # sets one that says whether the flip is for this window or for all.
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        self._hover = False
        self._on = not scope.is_dark()  # sun (right) = light theme
        self._knob_x = self._x_on if self._on else self._x_off

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(Switch.ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim.valueChanged.connect(self._on_anim_value)

        scope.changed.connect(self._sync_from_theme)

    # --- events -------------------------------------------------------

    def mousePressEvent(self, event):
        """Run the configured flip behind its snapshot cover.

        The knob slide is driven by the resulting `changed` signal in
        `_sync_from_theme`, never directly here — so a switch that moves
        because ANOTHER switch flipped its scope follows the identical path.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self._flip()
        else:
            super().mousePressEvent(event)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    # --- animation ----------------------------------------------------

    def _sync_from_theme(self):
        """Slide the knob to match this scope's now-active theme."""
        on = not self._theme.is_dark()
        if on == self._on:
            return
        self._on = on
        self._anim.stop()
        self._anim.setStartValue(float(self._knob_x))
        self._anim.setEndValue(float(self._x_on if on else self._x_off))
        self._anim.start()

    def _on_anim_value(self, value):
        self._knob_x = float(value)
        self.update()

    # --- painting -----------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # The track hard-swaps night <-> day as the knob passes the midpoint,
        # so the pill art always matches the side the knob has committed to.
        day = self._knob_x > (self._x_off + self._x_on) / 2
        track = icons.art(
            icons.TRACK_DAY if day else icons.TRACK_NIGHT,
            self._track_w, Switch.HEIGHT,
        )
        painter.drawPixmap(self._pad, self._pad, track)

        # The knob art already carries the sun's rays / the moon's craters.
        # The sun is drawn into a larger cell than the knob so its rays reach
        # past the disc without shrinking the disc itself.
        diameter = self._knob_d * (Switch.HOVER_SCALE if self._hover else 1.0)
        cell = diameter * (Switch.SUN_CELL_SCALE if day else 1.0)
        knob = icons.art(
            icons.KNOB_SUN if day else icons.KNOB_MOON, round(cell), round(cell),
        )
        cx = self._knob_x + self._knob_d / 2
        cy = self._pad + Switch.HEIGHT / 2
        painter.drawPixmap(
            QRectF(cx - cell / 2, cy - cell / 2, cell, cell), knob,
            QRectF(knob.rect()),
        )
