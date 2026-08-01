"""Building and styling one process table.

All three tables in a monitor window (current, peak, rolling) are the same
table with a different column set, so ONE factory builds them: it decides the
columns from the mode, sets the resize modes, applies the window's palette and
font, and installs the Σ delegate and the auto-fit header.

The QSS builders are separate from `create_table()` on purpose: a theme flip
must be able to restyle a live table without rebuilding it.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QTableWidget

from ..styles import FontScale, Fonts, scaled_font
from ..theme import Palette, ThemeScope
from .table_widgets import ContentWidthHeader, TotalRowDelegate


# ════════════════════════════════ STYLING ════════════════════════════════

def header_css(palette: Palette, font_base: int) -> str:
    """QSS for a table's horizontal header, in a window's theme and font."""
    return f"""
            QHeaderView::section {{
                background-color: {palette.HEADER};
                color: {palette.TEXT};
                font-family: {Fonts.FAMILY};
                font-size: {FontScale.size(font_base, FontScale.SMALL)}pt;
                font-weight: bold;
                padding: 8px;
                border: none;
            }}
        """


def style_table(table: QTableWidget, palette: Palette, font_base: int) -> None:
    """Apply a window's palette as QSS to one process table.

    All three sections (current, peak, rolling) share one surface color —
    a per-section tint made the same data look like three different kinds
    of table for no reason (owner 2026-07-24).
    """
    table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {palette.SECTION_BG};
                color: {palette.TEXT};
                border: none;
                border-radius: 6px;
                outline: none;
            }}
            QTableWidget::item {{
                padding: 4px 8px;
                border-bottom: 1px solid {palette.HEADER};
            }}
            QTableWidget::item:selected {{
                background-color: {palette.HEADER};
                color: {palette.TEXT};
            }}
            {header_css(palette, font_base)}
        """)
    # The header carries its OWN stylesheet (set by the window's _apply_fonts,
    # which must restyle it without rebuilding the table). A per-widget sheet
    # wins over the table's, so it has to be refreshed here too or a theme
    # flip would leave the column headers in the old palette.
    table.horizontalHeader().setStyleSheet(header_css(palette, font_base))


# ════════════════════════════════ THE FACTORY ════════════════════════════════

def create_table(
    rows: int,
    scope: ThemeScope,
    font_base: int,
    mode_cols: str = "none",
    has_time: bool = False,
    has_total_row: bool = False,
    has_uptime: bool = False,
) -> QTableWidget:
    """Create a styled table.

    Args:
        rows: Number of rows
        scope: the window's theme scope (the Σ delegate keeps reading it)
        font_base: the window's base font size in points
        mode_cols: "cpu" for Parallel+Threads, "mem" for Commit, "net" for
            Download+Upload, "none" for no extra cols
        has_time: Add Time column
        has_total_row: Reserve one extra row for the Σ totals
        has_uptime: Add Uptime column (rolling average table only)
    """
    cols = 3  # #, Process, Usage
    headers = ["#", "Process", "Usage"]

    if mode_cols == "cpu":
        cols += 2
        headers += ["Parallel", "Threads"]
    elif mode_cols == "mem":
        cols += 1
        headers.append("Commit")
    elif mode_cols == "net":
        # Replace "Usage" with "Download" and add "Upload"
        headers[2] = "Download"
        cols += 1
        headers.append("Upload")
    if has_time:
        cols += 1
        headers.append("Time")
    if has_uptime:
        cols += 1
        headers.append("Uptime")

    table = QTableWidget(rows + 1 if has_total_row else rows, cols)
    # Swapped in before any header configuration: double-clicking a resize
    # handle must fit the column to its values, not to the column title.
    table.setHorizontalHeader(ContentWidthHeader(table))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setShowGrid(False)

    # Column widths (all data columns are user-resizable)
    header = table.horizontalHeader()
    # # column (row number) - fit to content
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    # Process column (stretch to fill remaining space)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    # Usage column - interactive (user-draggable), initially sized to content
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)

    col_idx = 3
    if mode_cols == "cpu":
        header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)  # Parallel
        col_idx += 1
        header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)  # Threads
        col_idx += 1
    elif mode_cols == "mem":
        header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)  # Commit
        col_idx += 1
    elif mode_cols == "net":
        header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)  # Upload
        col_idx += 1
    if has_time:
        header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)
        col_idx += 1
    if has_uptime:
        header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)

    # Styling
    style_table(table, scope.palette, font_base)

    table.verticalHeader().setDefaultSectionSize(FontScale.row_height(font_base))

    # Left-align header text for all columns except # and Process (so narrow columns clip from right)
    align_left = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    for col in range(2, cols):
        table.horizontalHeader().model().setHeaderData(
            col, Qt.Orientation.Horizontal, align_left, Qt.ItemDataRole.TextAlignmentRole
        )

    # Set initial widths for interactive columns based on header text (one-time)
    table.resizeColumnToContents(2)
    col_idx = 3
    if mode_cols == "cpu":
        table.resizeColumnToContents(col_idx)  # Parallel
        col_idx += 1
        table.resizeColumnToContents(col_idx)  # Threads
        col_idx += 1
    elif mode_cols == "mem":
        table.resizeColumnToContents(col_idx)  # Commit
        col_idx += 1
    if has_time:
        table.resizeColumnToContents(col_idx)
        col_idx += 1
    if has_uptime:
        table.resizeColumnToContents(col_idx)

    # Set table content font (inherited by all QTableWidgetItems)
    table.setFont(scaled_font(font_base, FontScale.SMALL))

    # Enable hover events for tooltips and install delegate for total row background
    table.viewport().setMouseTracking(True)
    table.setItemDelegate(TotalRowDelegate(table, scope))

    return table
