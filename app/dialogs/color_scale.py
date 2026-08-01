"""ColorScaleWidget — the draggable usage-color scale.

The five usage zones of one color mode, drawn as a gradient bar with four
diamond handles on the boundaries between them. Dragging a handle moves that
boundary; the owning settings dialog reads `thresholds` back on Apply and
hands them to `ProcessColorManager.update_value_thresholds()`.
"""

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..theme import ThemeScope


# ══════════════════════════ THE COLOR SCALE WIDGET ══════════════════════════

class ColorScaleWidget(QWidget):
    """
    Visual widget showing the 5-color gradient with 4 draggable threshold handles.

    Each diamond handle marks the boundary between adjacent color zones and is
    colored with its zone's color. Dragging adjusts where that transition occurs.
    """

    thresholds_changed = Signal(list)  # list of 4 int thresholds

    _BAR_Y = 10
    _BAR_H = 14
    _HANDLE_R = 7

    def __init__(
        self,
        colors: list,       # 5 QColors for the 5 zones
        thresholds: list,   # 4 int values in ascending order [t1, t2, t3, t4]
        scope: ThemeScope,  # the theme its handle outline and labels follow
        parent: Optional[QWidget] = None,
        scale_max: int = 100,
    ):
        super().__init__(parent)
        self._theme = scope
        self._colors = list(colors)
        self._thresholds = list(thresholds)
        self._scale_max = scale_max
        self._drag_idx: Optional[int] = None
        self.setMinimumHeight(56)
        self.setMouseTracking(True)

    # --- geometry helpers ---

    def _bar_x1(self) -> float:
        return float(self._HANDLE_R + 6)

    def _bar_x2(self) -> float:
        return float(self.width() - self._HANDLE_R - 6)

    def _bar_w(self) -> float:
        return self._bar_x2() - self._bar_x1()

    def _pct_to_x(self, pct: int) -> float:
        return self._bar_x1() + pct / self._scale_max * self._bar_w()

    def _x_to_pct(self, x: float) -> int:
        raw = (x - self._bar_x1()) / self._bar_w() * self._scale_max
        return max(0, min(self._scale_max, round(raw)))

    # --- painting ---

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self._theme.palette

        bar_x1 = self._bar_x1()
        bar_y = float(self._BAR_Y)
        bar_h = float(self._BAR_H)
        bar_w = self._bar_w()

        # Draw 5 color segments
        pcts = [0] + self._thresholds + [self._scale_max]
        for i, color in enumerate(self._colors):
            x1 = bar_x1 + pcts[i] / self._scale_max * bar_w
            x2 = bar_x1 + pcts[i + 1] / self._scale_max * bar_w
            painter.fillRect(QRectF(x1, bar_y, max(x2 - x1, 0), bar_h), color)

        # Draw 4 diamond handles (each colored with the zone it ends)
        for i, t in enumerate(self._thresholds):
            x = self._pct_to_x(t)
            cy = bar_y + bar_h / 2
            r = float(self._HANDLE_R)
            zone_color = self._colors[i].lighter(150)
            painter.setBrush(QBrush(zone_color))
            painter.setPen(QPen(QColor(palette.TEXT), 1.0))
            painter.drawConvexPolygon([
                QPointF(x,     cy - r),
                QPointF(x + r, cy),
                QPointF(x,     cy + r),
                QPointF(x - r, cy),
            ])

        # Percentage labels below handles
        painter.setPen(QColor(palette.TEXT_MUTED))
        painter.setFont(QFont("Segoe UI", 9))
        fm = painter.fontMetrics()
        for t in self._thresholds:
            label = f"{t}%"
            lw = fm.horizontalAdvance(label)
            lx = self._pct_to_x(t) - lw / 2
            lx = max(0.0, min(lx, float(self.width() - lw)))
            painter.drawText(QPointF(lx, bar_y + bar_h + 14), label)

    # --- mouse interaction ---

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x = event.position().x()
        hit_radius = self._HANDLE_R + 10
        best_idx = None
        best_dist = float('inf')
        for i, t in enumerate(self._thresholds):
            dist = abs(x - self._pct_to_x(t))
            if dist < hit_radius and dist < best_dist:
                best_dist = dist
                best_idx = i
        self._drag_idx = best_idx
        if best_idx is not None:
            self.setCursor(Qt.CursorShape.SizeHorCursor)

    def mouseMoveEvent(self, event):
        if self._drag_idx is None:
            return
        pct = self._x_to_pct(event.position().x())
        lo = (self._thresholds[self._drag_idx - 1] + 1) if self._drag_idx > 0 else 1
        hi = (self._thresholds[self._drag_idx + 1] - 1) if self._drag_idx < len(self._thresholds) - 1 else self._scale_max - 1
        self._thresholds[self._drag_idx] = max(lo, min(hi, pct))
        self.update()
        self.thresholds_changed.emit(list(self._thresholds))

    def mouseReleaseEvent(self, event):
        self._drag_idx = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    @property
    def thresholds(self) -> list:
        return list(self._thresholds)

    def set_thresholds(self, thresholds: list) -> None:
        """Update displayed thresholds (e.g. from saved settings) and repaint."""
        self._thresholds = list(thresholds)
        self.update()
