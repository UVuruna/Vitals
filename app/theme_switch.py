"""
DayNightSwitch — the Day/Night theme toggle.

An image pill ported from the owner's website switch (the same track and
sun/moon art PromptPainter uses, root Rule #5 — reuse, never re-author):
OFF/left is the MOON on a dark starfield track, ON/right is the SUN on a
sky-and-clouds track. A click flips the app theme synchronously, then the
knob slides as an eased flourish.

Every monitor window carries its own switch, so all of them listen to
`theme_manager().changed` and animate together: flipping the theme in the
CPU window slides the Memory and Network switches too.
"""

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from . import icons
from .styles import Switch
from .theme import theme_manager
from .transition import flip_theme


class DayNightSwitch(QWidget):
    """The mini Day/Night pill toggle shown in each window header.

    Geometry scales from `Switch.HEIGHT` (styles.py); the four pixmaps
    (two tracks, two knob sizes for rest/hover) are rasterized ONCE at
    construction and cached in icons.py, so a slide only blits.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
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
        self.setToolTip("Switch between dark and light theme")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        self._hover = False
        self._on = not theme_manager().is_dark()  # sun (right) = light theme
        self._knob_x = self._x_on if self._on else self._x_off

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(Switch.ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim.valueChanged.connect(self._on_anim_value)

        theme_manager().changed.connect(self._sync_from_theme)

    # --- events -------------------------------------------------------

    def mousePressEvent(self, event):
        """Flip the app theme behind the snapshot cover.

        `flip_theme()` runs the whole transition; the knob slide is driven by
        the resulting `changed` signal in `_sync_from_theme`, so a switch in
        another window follows the identical path.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            flip_theme()
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
        """Slide the knob to match the now-active theme (any window's flip)."""
        on = not theme_manager().is_dark()
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
