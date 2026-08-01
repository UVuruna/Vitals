"""Custom Qt view classes for the monitor windows.

Three small overrides of Qt behavior that the process tables and the
current/history splitter depend on. They are classes rather than settings
because each redefines a paint or an input gesture Qt gives no hook for.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHeaderView,
    QSplitter,
    QSplitterHandle,
    QStyle,
    QStyledItemDelegate,
    QTableWidget,
)

from ..theme import ThemeScope


# ═══════════════════════════ THE Σ TOTAL ROW ═══════════════════════════

class TotalRowDelegate(QStyledItemDelegate):
    """Draws the Σ total row with a distinct header background color.

    QSS-styled tables ignore QTableWidgetItem.setBackground(); this delegate
    bypasses the style engine and paints the background directly. Colors are
    read from the owning window's scope at paint time, so a theme flip needs
    no delegate rebuild — and a table in the Memory window keeps painting
    Memory's theme while CPU is on the other one.
    """

    ROLE = Qt.ItemDataRole.UserRole + 100

    def __init__(self, table: QTableWidget, scope: ThemeScope):
        super().__init__(table)
        self._theme = scope

    def paint(self, painter, option, index):
        if not index.data(self.ROLE):
            super().paint(painter, option, index)
            return

        palette = self._theme.palette
        painter.save()
        painter.fillRect(option.rect, QColor(palette.HEADER))

        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        fg_brush = index.data(Qt.ItemDataRole.ForegroundRole)
        if fg_brush is not None:
            painter.setPen(fg_brush.color() if hasattr(fg_brush, 'color') else QColor(fg_brush))
        else:
            painter.setPen(QColor(palette.TEXT))

        font = index.data(Qt.ItemDataRole.FontRole)
        if font is not None:
            painter.setFont(font)

        rect = option.rect.adjusted(8, 0, -8, 0)
        align_data = index.data(Qt.ItemDataRole.TextAlignmentRole)
        align = int(align_data) if align_data is not None else int(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        painter.drawText(rect, align, text)
        painter.restore()


# ══════════════════════════ COLUMN AUTO-FIT HEADER ══════════════════════════

class ContentWidthHeader(QHeaderView):
    """Header whose auto-fit sizes a column to its ROW VALUES, not its title.

    Double-clicking a section's resize handle is Qt's "fit to contents"
    gesture, and Qt resizes to `sectionSizeHint()` — the LARGER of the column
    contents and the header label. In a gadget this is the wrong end of the
    trade: "Parallel" and "Threads" are long words holding two-digit numbers,
    so the fit leaves a column three times wider than the data needs and eats
    the width the process names want (owner 2026-07-26).

    This header takes that gesture over and resizes to the view's
    `sizeHintForColumn()`, which measures the rendered ROWS only — and which
    ALREADY includes the table QSS's per-cell padding (measured: "49" at the
    app font hints 36px = 14px text + 16px QSS padding + style margins).
    Nothing is added on top: adding the padding again was exactly the bug
    that left the fitted column wide enough to still show its title.
    Everything else — dragging a handle, the other resize modes — is left
    to Qt.
    """

    def __init__(self, table: QTableWidget):
        super().__init__(Qt.Orientation.Horizontal, table)
        self._table = table

    def _handle_at(self, position: int) -> int:
        """Logical index of the section whose resize handle is at `position`.

        Mirrors Qt's own (private) hit test: the grip on a section's LEFT edge
        resizes the PREVIOUS section, the grip on its right edge resizes the
        section itself. Returns -1 when the position is not on a handle.
        """
        visual = self.visualIndexAt(position)
        if visual < 0:
            return -1
        logical = self.logicalIndex(visual)
        start = self.sectionViewportPosition(logical)
        grip = self.style().pixelMetric(
            QStyle.PixelMetric.PM_HeaderGripMargin, None, self
        )
        if position < start + grip:
            return self.logicalIndex(visual - 1) if visual > 0 else -1
        if position > start + self.sectionSize(logical) - grip:
            return logical
        return -1

    def mouseDoubleClickEvent(self, event):
        """Fit the double-clicked column to its row values.

        Anything that is not an interactive section's handle falls through to
        Qt — only the auto-fit gesture is being redefined here.
        """
        logical = self._handle_at(round(event.position().x()))
        if logical < 0 or self.sectionResizeMode(logical) != QHeaderView.ResizeMode.Interactive:
            super().mouseDoubleClickEvent(event)
            return
        content = self._table.sizeHintForColumn(logical)
        self.resizeSection(logical, max(self.minimumSectionSize(), content))


# ═══════════════════════════ 50-50 RESET SPLITTER ═══════════════════════════

class DoubleClickSplitterHandle(QSplitterHandle):
    """Splitter handle that resets to 50-50 on double-click."""

    def mouseDoubleClickEvent(self, event):
        """Reset splitter to equal sizes on double-click."""
        splitter = self.splitter()
        if splitter:
            total = sum(splitter.sizes())
            equal_size = total // 2
            splitter.setSizes([equal_size, total - equal_size])
        super().mouseDoubleClickEvent(event)


class DoubleClickSplitter(QSplitter):
    """Splitter with double-click to reset to 50-50 split."""

    def createHandle(self):
        """Create custom handle."""
        return DoubleClickSplitterHandle(self.orientation(), self)
