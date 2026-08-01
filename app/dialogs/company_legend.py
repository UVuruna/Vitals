"""CompanyLegendDialog — which color belongs to which company.

Opened from a per-mode settings dialog, so it renders in the theme of the
window that owns it. The list is the color ranking itself: the busiest
company first in plain contrast, then the blue-to-red wheel by process count,
then "Other" and "Unknown". Each row expands to the individual process names
behind it, and the two sliders tune THAT theme's wheel saturation/lightness.

A 1-second timer re-reads the legend and rebuilds it only when the company
set or the counts actually changed — the process list moves constantly, the
legend must not flicker with it.
"""

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..color_management import ProcessColorManager
from ..persistence import get_base_path
from ..theme import ThemeScope


# ═══════════════════════════ THE LEGEND DIALOG ═══════════════════════════

class CompanyLegendDialog(QDialog):
    """Shows all detected companies and their assigned colors.

    Opened from a per-mode settings dialog, so it renders in the theme of the
    window that owns it — and the Saturation/Lightness sliders tune THAT
    theme's wheel params, leaving the other theme's untouched.
    """

    def __init__(self, scope: ThemeScope, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._theme = scope
        self.setWindowTitle("Company Color Legend")
        self.resize(340, 440)

        icon_path = get_base_path() / "assets" / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        colors = scope.palette
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(colors.BACKGROUND))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(colors.TEXT))
        palette.setColor(QPalette.ColorRole.Base, QColor(colors.CARD))
        palette.setColor(QPalette.ColorRole.Text, QColor(colors.TEXT))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self._expanded: set[str] = set()

        self._setup_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1000)
        self._refresh_timer.timeout.connect(self._refresh_legend)
        self._refresh_timer.start()

    def _setup_ui(self):
        palette = self._theme.palette
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Company Color Legend")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {palette.TEXT}; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{ background: {palette.CARD}; width: 8px; border-radius: 4px; }}
            QScrollBar::handle:vertical {{ background: {palette.BORDER}; border-radius: 4px; }}
        """)
        self._rebuild_legend_content()
        layout.addWidget(self._scroll)

        # The list is ranked by process count, and so is the color scale:
        # the top entry is plain contrast, the rest walk blue -> red.
        top_word = "White" if self._theme.is_dark() else "Black"
        note = QLabel(
            f"{top_word} = most processes  ·  blue → red by count  ·  Gray = no company info"
        )
        note.setFont(QFont("Segoe UI", 8))
        note.setStyleSheet(f"color: {palette.TEXT_DISABLED}; background: transparent;")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setWordWrap(True)
        layout.addWidget(note)

        # Hue color sliders
        sat_init, light_init = ProcessColorManager().get_hue_params(palette)

        slider_style = f"""
            QSlider::groove:horizontal {{
                height: 4px; background: {palette.HEADER}; border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 14px; height: 14px; margin: -5px 0;
                background: {palette.ACCENT}; border-radius: 7px;
            }}
            QSlider::sub-page:horizontal {{ background: {palette.ACCENT}; border-radius: 2px; }}
        """

        for label_text, attr_slider, attr_val, init_val in [
            ("Saturation", "_sat_slider", "_sat_val", sat_init),
            ("Lightness",  "_light_slider", "_light_val", light_init),
        ]:
            row_w = QWidget()
            row_w.setStyleSheet("background: transparent;")
            row = QHBoxLayout(row_w)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)

            lbl = QLabel(label_text)
            lbl.setFont(QFont("Segoe UI", 9))
            lbl.setStyleSheet(f"color: {palette.TEXT_MUTED}; background: transparent;")
            lbl.setFixedWidth(70)
            row.addWidget(lbl)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(int(init_val * 100))
            slider.setStyleSheet(slider_style)
            row.addWidget(slider, 1)
            setattr(self, attr_slider, slider)

            val_lbl = QLabel(f"{int(init_val * 100)}%")
            val_lbl.setFont(QFont("Segoe UI", 9))
            val_lbl.setStyleSheet(f"color: {palette.TEXT_MUTED}; background: transparent;")
            val_lbl.setFixedWidth(34)
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(val_lbl)
            setattr(self, attr_val, val_lbl)

            slider.valueChanged.connect(self._on_hue_params_changed)
            layout.addWidget(row_w)

        close_btn = QPushButton("Close")
        close_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        close_btn.setFixedHeight(36)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {palette.HEADER}; color: {palette.TEXT}; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background-color: {palette.BORDER}; }}
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _rebuild_legend_content(self):
        palette = self._theme.palette
        color_mgr = ProcessColorManager()
        legend = color_mgr.get_legend(palette)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(4)
        content_layout.setContentsMargins(0, 0, 4, 0)

        if not legend:
            empty = QLabel("No companies detected yet.\nStart monitoring to populate.")
            empty.setFont(QFont("Segoe UI", 10))
            empty.setStyleSheet(f"color: {palette.TEXT_DIM}; background: transparent;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            content_layout.addWidget(empty)
        else:
            toggle_style = f"""
                QPushButton {{
                    background: transparent; color: {palette.TEXT_DIM};
                    border: none; padding: 0;
                }}
                QPushButton:hover {{ color: {palette.TEXT}; }}
            """
            for company, color, proc_count in legend:
                is_expanded = company in self._expanded

                row_w = QWidget()
                row_w.setStyleSheet("background: transparent;")
                row = QHBoxLayout(row_w)
                row.setContentsMargins(2, 1, 2, 1)
                row.setSpacing(10)

                swatch = QLabel()
                swatch.setFixedSize(14, 14)
                swatch.setStyleSheet(
                    f"background-color: {color.name()}; border-radius: 3px;"
                )
                row.addWidget(swatch)

                name_lbl = QLabel(company)
                name_lbl.setFont(QFont("Segoe UI", 10))
                name_lbl.setStyleSheet(f"color: {palette.TEXT}; background: transparent;")
                row.addWidget(name_lbl, 1)

                count_lbl = QLabel(str(proc_count))
                count_lbl.setFont(QFont("Segoe UI", 10))
                count_lbl.setStyleSheet(f"color: {palette.TEXT_FAINT}; background: transparent;")
                count_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                row.addWidget(count_lbl)

                toggle_btn = QPushButton("▼" if is_expanded else "▶")
                toggle_btn.setFixedSize(20, 20)
                toggle_btn.setFont(QFont("Segoe UI", 8))
                toggle_btn.setStyleSheet(toggle_style)
                toggle_btn.clicked.connect(lambda checked, c=company: self._toggle_company(c))
                row.addWidget(toggle_btn)

                content_layout.addWidget(row_w)

                if is_expanded:
                    if company == "Other":
                        sub_items = color_mgr.get_singleton_companies()
                    elif company == "Unknown":
                        sub_items = color_mgr.get_company_processes(None)
                    else:
                        sub_items = color_mgr.get_company_processes(company)

                    for item_name in sub_items:
                        sub_w = QWidget()
                        sub_w.setStyleSheet("background: transparent;")
                        sub_row = QHBoxLayout(sub_w)
                        sub_row.setContentsMargins(28, 0, 2, 0)
                        sub_row.setSpacing(10)

                        sub_lbl = QLabel(item_name)
                        sub_lbl.setFont(QFont("Segoe UI", 9))
                        sub_lbl.setStyleSheet(f"color: {palette.TEXT_MUTED}; background: transparent;")
                        sub_row.addWidget(sub_lbl, 1)

                        content_layout.addWidget(sub_w)

        content_layout.addStretch()
        self._scroll.setWidget(content)
        self._legend_data = legend

    def _toggle_company(self, label: str):
        if label in self._expanded:
            self._expanded.discard(label)
        else:
            self._expanded.add(label)
        self._rebuild_legend_content()

    def _refresh_legend(self):
        legend = ProcessColorManager().get_legend(self._theme.palette)
        current_key = [(c, n) for c, _, n in legend]
        cached_key = [(c, n) for c, _, n in self._legend_data] if self._legend_data else []
        if current_key != cached_key:
            self._rebuild_legend_content()

    def _on_hue_params_changed(self):
        sat = self._sat_slider.value() / 100.0
        light = self._light_slider.value() / 100.0
        self._sat_val.setText(f"{self._sat_slider.value()}%")
        self._light_val.setText(f"{self._light_slider.value()}%")
        ProcessColorManager().update_hue_params(self._theme.palette, sat, light)
        self._rebuild_legend_content()
