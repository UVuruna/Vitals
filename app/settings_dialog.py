"""
Settings Dialog - Simple and Working
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import psutil
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QBrush, QFont, QIcon, QPainter, QPalette, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .monitor import MonitorMode
from .styles import Defaults
from .color_management import ProcessColorManager


def get_base_path() -> Path:
    """Get base path for resources (handles PyInstaller frozen exe)."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# ColorScaleWidget — visual range slider for value color scale
# ---------------------------------------------------------------------------

class ColorScaleWidget(QWidget):
    """
    Visual range slider showing the 5-color gradient with two draggable handles.

    Left handle (od / from): percentage below which everything is the first color (blue).
    Right handle (do / to): percentage above which everything is the last color (red).
    The gradient is proportionally mapped between the two handles.
    """

    scale_changed = Signal(int, int)  # min_pct, max_pct

    _BAR_Y = 14
    _BAR_H = 12
    _HANDLE_R = 7

    def __init__(
        self,
        value_ranges: list,
        min_pct: int = 0,
        max_pct: int = 100,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._ranges = value_ranges  # [(threshold_pct, QColor), ...]
        self._min = min_pct
        self._max = max_pct
        self._drag: Optional[str] = None
        self.setMinimumHeight(52)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    # --- geometry helpers ---

    def _bar_x1(self) -> float:
        return float(self._HANDLE_R + 4)

    def _bar_x2(self) -> float:
        return float(self.width() - self._HANDLE_R - 4)

    def _bar_w(self) -> float:
        return self._bar_x2() - self._bar_x1()

    def _pct_to_x(self, pct: int) -> float:
        return self._bar_x1() + pct / 100.0 * self._bar_w()

    def _x_to_pct(self, x: float) -> int:
        raw = (x - self._bar_x1()) / self._bar_w() * 100
        return max(0, min(100, round(raw)))

    # --- painting ---

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bar_x1 = self._bar_x1()
        bar_y = float(self._BAR_Y)
        bar_h = float(self._BAR_H)
        bar_w = self._bar_w()

        # Draw color segments proportionally
        prev_pct = 0.0
        for threshold_pct, color in self._ranges:
            x1 = bar_x1 + prev_pct / 100.0 * bar_w
            x2 = bar_x1 + threshold_pct / 100.0 * bar_w
            painter.fillRect(QRectF(x1, bar_y, max(x2 - x1, 0), bar_h), color)
            prev_pct = threshold_pct

        # Dim overlay outside [min, max]
        min_x = self._pct_to_x(self._min)
        max_x = self._pct_to_x(self._max)
        dim = QColor(30, 30, 46, 190)
        if min_x > bar_x1:
            painter.fillRect(QRectF(bar_x1, bar_y, min_x - bar_x1, bar_h), dim)
        bar_x2 = self._bar_x2()
        if max_x < bar_x2:
            painter.fillRect(QRectF(max_x, bar_y, bar_x2 - max_x, bar_h), dim)

        # Dividers between segments (subtle)
        prev_pct = 0.0
        painter.setPen(QColor(30, 30, 46, 80))
        for threshold_pct, _ in self._ranges[:-1]:
            x = bar_x1 + threshold_pct / 100.0 * bar_w
            painter.drawLine(QPointF(x, bar_y), QPointF(x, bar_y + bar_h))
            prev_pct = threshold_pct

        # Handles (diamonds)
        for pct in (self._min, self._max):
            x = self._pct_to_x(pct)
            cy = bar_y + bar_h / 2
            r = float(self._HANDLE_R)
            painter.setBrush(QBrush(QColor("#e94560")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawConvexPolygon([
                QPointF(x, cy - r),
                QPointF(x + r, cy),
                QPointF(x, cy + r),
                QPointF(x - r, cy),
            ])

        # Percentage labels below handles
        painter.setPen(QColor("#aaaaaa"))
        painter.setFont(QFont("Segoe UI", 9))
        fm = painter.fontMetrics()
        for pct in (self._min, self._max):
            label = f"{pct}%"
            lw = fm.horizontalAdvance(label)
            lx = self._pct_to_x(pct) - lw / 2
            lx = max(0.0, min(lx, float(self.width() - lw)))
            painter.drawText(QPointF(lx, bar_y + bar_h + 14), label)

    # --- mouse interaction ---

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x = event.position().x()
        min_x = self._pct_to_x(self._min)
        max_x = self._pct_to_x(self._max)
        dist_min = abs(x - min_x)
        dist_max = abs(x - max_x)
        threshold = self._HANDLE_R + 10
        if dist_min <= threshold or dist_max <= threshold:
            self._drag = 'min' if dist_min <= dist_max else 'max'

    def mouseMoveEvent(self, event):
        if not self._drag:
            return
        pct = self._x_to_pct(event.position().x())
        if self._drag == 'min':
            self._min = max(0, min(pct, self._max - 5))
        else:
            self._max = min(100, max(pct, self._min + 5))
        self.update()
        self.scale_changed.emit(self._min, self._max)

    def mouseReleaseEvent(self, event):
        self._drag = None

    @property
    def min_pct(self) -> int:
        return self._min

    @property
    def max_pct(self) -> int:
        return self._max


# ---------------------------------------------------------------------------
# CompanyLegendDialog
# ---------------------------------------------------------------------------

class CompanyLegendDialog(QDialog):
    """Shows all detected companies and their assigned colors."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Company Color Legend")
        self.setFixedSize(340, 440)

        icon_path = get_base_path() / "assets" / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e2e"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#2a2a3e"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Company Color Legend")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        legend = ProcessColorManager().get_legend()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #2a2a3e; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #4a4a5e; border-radius: 4px; }
        """)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(4)
        content_layout.setContentsMargins(0, 0, 4, 0)

        if not legend:
            empty = QLabel("No companies detected yet.\nStart monitoring to populate.")
            empty.setFont(QFont("Segoe UI", 10))
            empty.setStyleSheet("color: #888888; background: transparent;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            content_layout.addWidget(empty)
        else:
            for company, color, proc_count in legend:
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
                name_lbl.setStyleSheet("color: #ffffff; background: transparent;")
                row.addWidget(name_lbl, 1)

                count_lbl = QLabel(str(proc_count))
                count_lbl.setFont(QFont("Segoe UI", 10))
                count_lbl.setStyleSheet("color: #666666; background: transparent;")
                count_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                row.addWidget(count_lbl)

                content_layout.addWidget(row_w)

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        note = QLabel("Colored = multi-process company  ·  Gray = singleton")
        note.setFont(QFont("Segoe UI", 8))
        note.setStyleSheet("color: #555555; background: transparent;")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(note)

        close_btn = QPushButton("Close")
        close_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        close_btn.setFixedHeight(36)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton { background-color: #3a3a4e; color: #ffffff; border: none; border-radius: 6px; }
            QPushButton:hover { background-color: #4a4a5e; }
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


# ---------------------------------------------------------------------------
# Helper: build color settings section into any layout
# ---------------------------------------------------------------------------

def _build_color_section(
    layout: QVBoxLayout,
    make_label,
) -> 'ColorScaleWidget':
    """
    Add Color Settings label, ColorScaleWidget, and Legend button to layout.
    Returns the ColorScaleWidget so the caller can read min/max on accept.
    """
    layout.addWidget(make_label("Color Settings", 12, bold=True))

    color_mgr = ProcessColorManager()
    scale_min, scale_max = color_mgr.get_value_scale()
    value_ranges = color_mgr.get_value_ranges()

    scale_widget = ColorScaleWidget(value_ranges, scale_min, scale_max)
    layout.addWidget(scale_widget)

    legend_row = QHBoxLayout()
    legend_row.addStretch()
    legend_btn = QPushButton("Company Legend")
    legend_btn.setFont(QFont("Segoe UI", 10))
    legend_btn.setFixedHeight(28)
    legend_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    legend_btn.setStyleSheet("""
        QPushButton {
            background-color: #2a2a3e; color: #888888;
            border: 1px solid #3a3a4e; border-radius: 4px; padding: 0 12px;
        }
        QPushButton:hover { background-color: #3a3a4e; color: #ffffff; }
    """)

    # We need the parent widget to open the dialog — store button reference so
    # the caller can connect it after layout is built.
    scale_widget._legend_btn = legend_btn  # type: ignore[attr-defined]
    legend_row.addWidget(legend_btn)
    layout.addLayout(legend_row)

    return scale_widget


# ---------------------------------------------------------------------------
# Legacy SettingsDialog (unused in current flow, kept for compatibility)
# ---------------------------------------------------------------------------

@dataclass
class MonitorSettings:
    """Application settings container."""
    mode: MonitorMode = MonitorMode.CPU
    current_rows: int = Defaults.CURRENT_ROWS
    history_rows: int = Defaults.HISTORY_ROWS
    refresh_rate_ms: int = Defaults.REFRESH_RATE_MS
    retention_minutes: int = Defaults.RETENTION_MINUTES
    memory_unit: str = Defaults.MEMORY_UNIT

    @property
    def cpu_threads(self) -> int:
        return psutil.cpu_count() or 8

    @property
    def ram_gb(self) -> int:
        return round(psutil.virtual_memory().total / (1024 ** 3))


@dataclass
class InitialSettings:
    """Settings from initial dialog (launcher)."""
    cpu_enabled: bool = True
    memory_enabled: bool = False
    current_rows: int = Defaults.CURRENT_ROWS
    history_rows: int = Defaults.HISTORY_ROWS
    refresh_rate_ms: int = Defaults.REFRESH_RATE_MS
    retention_minutes: int = Defaults.RETENTION_MINUTES
    memory_unit: str = Defaults.MEMORY_UNIT

    @property
    def cpu_threads(self) -> int:
        return psutil.cpu_count() or 8

    @property
    def ram_gb(self) -> int:
        return round(psutil.virtual_memory().total / (1024 ** 3))


# ---------------------------------------------------------------------------
# InitialSettingsDialog  (login screen)
# ---------------------------------------------------------------------------

class InitialSettingsDialog(QDialog):
    """Initial settings dialog with checkbox mode selection."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Process Monitor - Setup")
        self.setFixedSize(480, 690)

        icon_path = get_base_path() / "assets" / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e2e"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#2a2a3e"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#3a3a4e"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#e94560"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self._setup_ui()

    def _make_label(self, text: str, size: int = 12, bold: bool = False, color: str = "#ffffff") -> QLabel:
        label = QLabel(text)
        weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
        label.setFont(QFont("Segoe UI", size, weight))
        label.setStyleSheet(f"color: {color}; background: transparent;")
        return label

    def _make_combo(self, items: list, default: str) -> QComboBox:
        combo = QComboBox()
        combo.addItems(items)
        combo.setCurrentText(default)
        combo.setFont(QFont("Segoe UI", 11))
        combo.setMinimumContentsLength(max(len(item) for item in items))
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setFixedHeight(32)
        combo.setStyleSheet("""
            QComboBox {
                background-color: #3a3a4e;
                color: #ffffff;
                border: 1px solid #4a4a5e;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox::down-arrow {
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #ffffff;
            }
            QComboBox QAbstractItemView {
                background-color: #3a3a4e;
                color: #ffffff;
                selection-background-color: #e94560;
            }
        """)
        return combo

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 24, 32, 24)

        title = self._make_label("Process Monitor", 20, bold=True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = self._make_label("Select monitors to open", 10, color="#888888")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(12)

        # Monitor Mode
        layout.addWidget(self._make_label("Monitor Mode", 12, bold=True))

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)

        self.cpu_btn = QPushButton("CPU Usage")
        self.cpu_btn.setFont(QFont("Segoe UI", 11))
        self.cpu_btn.setFixedHeight(36)
        self.cpu_btn.setCheckable(True)
        self.cpu_btn.setChecked(True)
        self.cpu_btn.clicked.connect(self._update_mode_buttons)
        mode_row.addWidget(self.cpu_btn)

        self.mem_btn = QPushButton("Memory Usage")
        self.mem_btn.setFont(QFont("Segoe UI", 11))
        self.mem_btn.setFixedHeight(36)
        self.mem_btn.setCheckable(True)
        self.mem_btn.setChecked(False)
        self.mem_btn.clicked.connect(self._update_mode_buttons)
        mode_row.addWidget(self.mem_btn)

        active_style = """
            QPushButton { background-color: #e94560; color: white; border: none; border-radius: 6px; }
        """
        inactive_style = """
            QPushButton {
                background-color: #3a3a4e; color: #888888; border: none; border-radius: 6px;
            }
            QPushButton:hover { background-color: #4a4a5e; }
        """
        self.cpu_btn.setStyleSheet(active_style)
        self.mem_btn.setStyleSheet(inactive_style)

        layout.addLayout(mode_row)

        hint = self._make_label("Select one or both monitors", 9, color="#666666")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        layout.addSpacing(8)

        # Display Settings
        layout.addWidget(self._make_label("Display Settings", 12, bold=True))

        row1 = QHBoxLayout()
        row1.addWidget(self._make_label("Current processes:", 11, color="#aaaaaa"))
        row1.addStretch()
        self.current_combo = self._make_combo(
            [str(i) for i in range(1, Defaults.MAX_ROWS + 1)], str(Defaults.CURRENT_ROWS)
        )
        row1.addWidget(self.current_combo)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(self._make_label("History records:", 11, color="#aaaaaa"))
        row2.addStretch()
        self.history_combo = self._make_combo(
            [str(i) for i in range(1, Defaults.MAX_ROWS + 1)], str(Defaults.HISTORY_ROWS)
        )
        row2.addWidget(self.history_combo)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(self._make_label("Refresh rate:", 11, color="#aaaaaa"))
        row3.addStretch()
        self.refresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.refresh_slider.setRange(5, 50)
        self.refresh_slider.setValue(Defaults.REFRESH_RATE_MS // 100)
        self.refresh_slider.setFixedWidth(140)
        self.refresh_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3a3a4e; border-radius: 3px; }
            QSlider::handle:horizontal { background: #e94560; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::sub-page:horizontal { background: #e94560; border-radius: 3px; }
        """)
        row3.addWidget(self.refresh_slider)
        self.refresh_label = self._make_label(f"{Defaults.REFRESH_RATE_MS} ms", 11)
        self.refresh_label.setFixedWidth(65)
        self.refresh_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.refresh_slider.valueChanged.connect(lambda v: self.refresh_label.setText(f"{v * 100} ms"))
        row3.addWidget(self.refresh_label)
        layout.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(self._make_label("History retention:", 11, color="#aaaaaa"))
        row4.addStretch()
        self.retention_slider = QSlider(Qt.Orientation.Horizontal)
        self.retention_slider.setRange(10, 360)
        self.retention_slider.setValue(Defaults.RETENTION_MINUTES)
        self.retention_slider.setFixedWidth(140)
        self.retention_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3a3a4e; border-radius: 3px; }
            QSlider::handle:horizontal { background: #e94560; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::sub-page:horizontal { background: #e94560; border-radius: 3px; }
        """)
        row4.addWidget(self.retention_slider)
        self.retention_label = self._make_label(f"{Defaults.RETENTION_MINUTES} min", 11)
        self.retention_label.setFixedWidth(65)
        self.retention_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.retention_slider.valueChanged.connect(lambda v: self.retention_label.setText(f"{v} min"))
        row4.addWidget(self.retention_label)
        layout.addLayout(row4)

        layout.addSpacing(8)

        # Memory Settings
        layout.addWidget(self._make_label("Memory Settings", 12, bold=True))

        row5 = QHBoxLayout()
        row5.addWidget(self._make_label("Display unit:", 11, color="#aaaaaa"))
        row5.addStretch()
        self.unit_combo = self._make_combo(["KB", "MB", "GB"], Defaults.MEMORY_UNIT)
        row5.addWidget(self.unit_combo)
        layout.addLayout(row5)

        layout.addSpacing(8)

        # Color Settings
        self._color_scale = _build_color_section(layout, self._make_label)
        self._color_scale._legend_btn.clicked.connect(self._show_legend)

        # System info
        cpu_threads = psutil.cpu_count() or 8
        ram_gb = round(psutil.virtual_memory().total / (1024 ** 3))
        info_label = self._make_label(
            f"Detected: {cpu_threads} CPU threads, {ram_gb} GB RAM", 10, color="#666666"
        )
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_label)

        layout.addStretch()

        self.start_btn = QPushButton("Start Monitoring")
        self.start_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.start_btn.setFixedHeight(44)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.setStyleSheet("""
            QPushButton { background-color: #e94560; color: white; border: none; border-radius: 8px; }
            QPushButton:hover { background-color: #ff6b6b; }
            QPushButton:disabled { background-color: #555555; color: #888888; }
        """)
        self.start_btn.clicked.connect(self._on_start)
        layout.addWidget(self.start_btn)

    def _update_mode_buttons(self):
        active_style = """
            QPushButton { background-color: #e94560; color: white; border: none; border-radius: 6px; }
        """
        inactive_style = """
            QPushButton {
                background-color: #3a3a4e; color: #888888; border: none; border-radius: 6px;
            }
            QPushButton:hover { background-color: #4a4a5e; }
        """
        self.cpu_btn.setStyleSheet(active_style if self.cpu_btn.isChecked() else inactive_style)
        self.mem_btn.setStyleSheet(active_style if self.mem_btn.isChecked() else inactive_style)
        self.start_btn.setEnabled(self.cpu_btn.isChecked() or self.mem_btn.isChecked())

    def _show_legend(self):
        CompanyLegendDialog(self).exec()

    def _on_start(self):
        if not self.cpu_btn.isChecked() and not self.mem_btn.isChecked():
            return
        ProcessColorManager().set_value_scale(
            self._color_scale.min_pct, self._color_scale.max_pct
        )
        self.accept()

    def get_settings(self) -> InitialSettings:
        return InitialSettings(
            cpu_enabled=self.cpu_btn.isChecked(),
            memory_enabled=self.mem_btn.isChecked(),
            current_rows=int(self.current_combo.currentText()),
            history_rows=int(self.history_combo.currentText()),
            refresh_rate_ms=self.refresh_slider.value() * 100,
            retention_minutes=self.retention_slider.value(),
            memory_unit=self.unit_combo.currentText(),
        )


# ---------------------------------------------------------------------------
# CPUSettings / MemorySettings dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CPUSettings:
    """Settings for CPU window only."""
    current_rows: int = Defaults.CURRENT_ROWS
    history_rows: int = Defaults.HISTORY_ROWS
    refresh_rate_ms: int = Defaults.REFRESH_RATE_MS
    retention_minutes: int = Defaults.RETENTION_MINUTES


@dataclass
class MemorySettings:
    """Settings for Memory window only."""
    current_rows: int = Defaults.CURRENT_ROWS
    history_rows: int = Defaults.HISTORY_ROWS
    refresh_rate_ms: int = Defaults.REFRESH_RATE_MS
    retention_minutes: int = Defaults.RETENTION_MINUTES
    memory_unit: str = Defaults.MEMORY_UNIT


# ---------------------------------------------------------------------------
# CPUSettingsDialog
# ---------------------------------------------------------------------------

class CPUSettingsDialog(QDialog):
    """Settings dialog for CPU window (no mode selection, no memory unit)."""

    def __init__(self, parent: Optional[QWidget] = None, settings: Optional[CPUSettings] = None):
        super().__init__(parent)
        self.settings = settings or CPUSettings()
        self.setWindowTitle("CPU Monitor - Settings")
        self.setFixedSize(400, 500)

        icon_path = get_base_path() / "assets" / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e2e"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#2a2a3e"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#3a3a4e"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#e94560"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self._setup_ui()
        self._load_settings()

    def _make_label(self, text: str, size: int = 12, bold: bool = False, color: str = "#ffffff") -> QLabel:
        label = QLabel(text)
        weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
        label.setFont(QFont("Segoe UI", size, weight))
        label.setStyleSheet(f"color: {color}; background: transparent;")
        return label

    def _make_combo(self, items: list, default: str) -> QComboBox:
        combo = QComboBox()
        combo.addItems(items)
        combo.setCurrentText(default)
        combo.setFont(QFont("Segoe UI", 11))
        combo.setMinimumContentsLength(max(len(item) for item in items))
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setFixedHeight(32)
        combo.setStyleSheet("""
            QComboBox {
                background-color: #3a3a4e; color: #ffffff;
                border: 1px solid #4a4a5e; border-radius: 4px; padding: 4px 8px;
            }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox::down-arrow {
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #ffffff;
            }
            QComboBox QAbstractItemView {
                background-color: #3a3a4e; color: #ffffff;
                selection-background-color: #e94560;
            }
        """)
        return combo

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 24, 32, 24)

        title = self._make_label("CPU Monitor Settings", 16, bold=True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(12)

        row1 = QHBoxLayout()
        row1.addWidget(self._make_label("Current processes:", 11, color="#aaaaaa"))
        row1.addStretch()
        self.current_combo = self._make_combo([str(i) for i in range(1, Defaults.MAX_ROWS + 1)], "7")
        row1.addWidget(self.current_combo)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(self._make_label("History records:", 11, color="#aaaaaa"))
        row2.addStretch()
        self.history_combo = self._make_combo([str(i) for i in range(1, Defaults.MAX_ROWS + 1)], "4")
        row2.addWidget(self.history_combo)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(self._make_label("Refresh rate:", 11, color="#aaaaaa"))
        row3.addStretch()
        self.refresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.refresh_slider.setRange(5, 50)
        self.refresh_slider.setValue(Defaults.REFRESH_RATE_MS // 100)
        self.refresh_slider.setFixedWidth(140)
        self.refresh_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3a3a4e; border-radius: 3px; }
            QSlider::handle:horizontal { background: #e94560; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::sub-page:horizontal { background: #e94560; border-radius: 3px; }
        """)
        row3.addWidget(self.refresh_slider)
        self.refresh_label = self._make_label(f"{Defaults.REFRESH_RATE_MS} ms", 11)
        self.refresh_label.setFixedWidth(65)
        self.refresh_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.refresh_slider.valueChanged.connect(lambda v: self.refresh_label.setText(f"{v * 100} ms"))
        row3.addWidget(self.refresh_label)
        layout.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(self._make_label("History retention:", 11, color="#aaaaaa"))
        row4.addStretch()
        self.retention_slider = QSlider(Qt.Orientation.Horizontal)
        self.retention_slider.setRange(10, 360)
        self.retention_slider.setValue(120)
        self.retention_slider.setFixedWidth(140)
        self.retention_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3a3a4e; border-radius: 3px; }
            QSlider::handle:horizontal { background: #e94560; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::sub-page:horizontal { background: #e94560; border-radius: 3px; }
        """)
        row4.addWidget(self.retention_slider)
        self.retention_label = self._make_label("120 min", 11)
        self.retention_label.setFixedWidth(65)
        self.retention_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.retention_slider.valueChanged.connect(lambda v: self.retention_label.setText(f"{v} min"))
        row4.addWidget(self.retention_label)
        layout.addLayout(row4)

        layout.addSpacing(8)

        # Color Settings
        self._color_scale = _build_color_section(layout, self._make_label)
        self._color_scale._legend_btn.clicked.connect(self._show_legend)

        layout.addStretch()

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.apply_btn.setFixedHeight(44)
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_btn.setStyleSheet("""
            QPushButton { background-color: #e94560; color: white; border: none; border-radius: 8px; }
            QPushButton:hover { background-color: #ff6b6b; }
        """)
        self.apply_btn.clicked.connect(self.accept)
        layout.addWidget(self.apply_btn)

    def _show_legend(self):
        CompanyLegendDialog(self).exec()

    def accept(self):
        ProcessColorManager().set_value_scale(
            self._color_scale.min_pct, self._color_scale.max_pct
        )
        super().accept()

    def _load_settings(self):
        self.current_combo.setCurrentText(str(self.settings.current_rows))
        self.history_combo.setCurrentText(str(self.settings.history_rows))
        self.refresh_slider.setValue(self.settings.refresh_rate_ms // 100)
        self.retention_slider.setValue(self.settings.retention_minutes)

    def get_settings(self) -> CPUSettings:
        return CPUSettings(
            current_rows=int(self.current_combo.currentText()),
            history_rows=int(self.history_combo.currentText()),
            refresh_rate_ms=self.refresh_slider.value() * 100,
            retention_minutes=self.retention_slider.value(),
        )


# ---------------------------------------------------------------------------
# MemorySettingsDialog
# ---------------------------------------------------------------------------

class MemorySettingsDialog(QDialog):
    """Settings dialog for Memory window (no mode selection, has memory unit)."""

    def __init__(self, parent: Optional[QWidget] = None, settings: Optional[MemorySettings] = None):
        super().__init__(parent)
        self.settings = settings or MemorySettings()
        self.setWindowTitle("Memory Monitor - Settings")
        self.setFixedSize(400, 560)

        icon_path = get_base_path() / "assets" / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e2e"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#2a2a3e"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#3a3a4e"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#e94560"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self._setup_ui()
        self._load_settings()

    def _make_label(self, text: str, size: int = 12, bold: bool = False, color: str = "#ffffff") -> QLabel:
        label = QLabel(text)
        weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
        label.setFont(QFont("Segoe UI", size, weight))
        label.setStyleSheet(f"color: {color}; background: transparent;")
        return label

    def _make_combo(self, items: list, default: str) -> QComboBox:
        combo = QComboBox()
        combo.addItems(items)
        combo.setCurrentText(default)
        combo.setFont(QFont("Segoe UI", 11))
        combo.setMinimumContentsLength(max(len(item) for item in items))
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setFixedHeight(32)
        combo.setStyleSheet("""
            QComboBox {
                background-color: #3a3a4e; color: #ffffff;
                border: 1px solid #4a4a5e; border-radius: 4px; padding: 4px 8px;
            }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox::down-arrow {
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #ffffff;
            }
            QComboBox QAbstractItemView {
                background-color: #3a3a4e; color: #ffffff;
                selection-background-color: #e94560;
            }
        """)
        return combo

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 24, 32, 24)

        title = self._make_label("Memory Monitor Settings", 16, bold=True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(12)

        row1 = QHBoxLayout()
        row1.addWidget(self._make_label("Current processes:", 11, color="#aaaaaa"))
        row1.addStretch()
        self.current_combo = self._make_combo([str(i) for i in range(1, Defaults.MAX_ROWS + 1)], "7")
        row1.addWidget(self.current_combo)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(self._make_label("History records:", 11, color="#aaaaaa"))
        row2.addStretch()
        self.history_combo = self._make_combo([str(i) for i in range(1, Defaults.MAX_ROWS + 1)], "4")
        row2.addWidget(self.history_combo)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(self._make_label("Refresh rate:", 11, color="#aaaaaa"))
        row3.addStretch()
        self.refresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.refresh_slider.setRange(5, 50)
        self.refresh_slider.setValue(Defaults.REFRESH_RATE_MS // 100)
        self.refresh_slider.setFixedWidth(140)
        self.refresh_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3a3a4e; border-radius: 3px; }
            QSlider::handle:horizontal { background: #e94560; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::sub-page:horizontal { background: #e94560; border-radius: 3px; }
        """)
        row3.addWidget(self.refresh_slider)
        self.refresh_label = self._make_label(f"{Defaults.REFRESH_RATE_MS} ms", 11)
        self.refresh_label.setFixedWidth(65)
        self.refresh_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.refresh_slider.valueChanged.connect(lambda v: self.refresh_label.setText(f"{v * 100} ms"))
        row3.addWidget(self.refresh_label)
        layout.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(self._make_label("History retention:", 11, color="#aaaaaa"))
        row4.addStretch()
        self.retention_slider = QSlider(Qt.Orientation.Horizontal)
        self.retention_slider.setRange(10, 360)
        self.retention_slider.setValue(120)
        self.retention_slider.setFixedWidth(140)
        self.retention_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3a3a4e; border-radius: 3px; }
            QSlider::handle:horizontal { background: #e94560; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::sub-page:horizontal { background: #e94560; border-radius: 3px; }
        """)
        row4.addWidget(self.retention_slider)
        self.retention_label = self._make_label("120 min", 11)
        self.retention_label.setFixedWidth(65)
        self.retention_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.retention_slider.valueChanged.connect(lambda v: self.retention_label.setText(f"{v} min"))
        row4.addWidget(self.retention_label)
        layout.addLayout(row4)

        layout.addSpacing(8)

        layout.addWidget(self._make_label("Memory Settings", 12, bold=True))
        row5 = QHBoxLayout()
        row5.addWidget(self._make_label("Display unit:", 11, color="#aaaaaa"))
        row5.addStretch()
        self.unit_combo = self._make_combo(["KB", "MB", "GB"], "MB")
        row5.addWidget(self.unit_combo)
        layout.addLayout(row5)

        layout.addSpacing(8)

        # Color Settings
        self._color_scale = _build_color_section(layout, self._make_label)
        self._color_scale._legend_btn.clicked.connect(self._show_legend)

        layout.addStretch()

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.apply_btn.setFixedHeight(44)
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_btn.setStyleSheet("""
            QPushButton { background-color: #e94560; color: white; border: none; border-radius: 8px; }
            QPushButton:hover { background-color: #ff6b6b; }
        """)
        self.apply_btn.clicked.connect(self.accept)
        layout.addWidget(self.apply_btn)

    def _show_legend(self):
        CompanyLegendDialog(self).exec()

    def accept(self):
        ProcessColorManager().set_value_scale(
            self._color_scale.min_pct, self._color_scale.max_pct
        )
        super().accept()

    def _load_settings(self):
        self.current_combo.setCurrentText(str(self.settings.current_rows))
        self.history_combo.setCurrentText(str(self.settings.history_rows))
        self.refresh_slider.setValue(self.settings.refresh_rate_ms // 100)
        self.retention_slider.setValue(self.settings.retention_minutes)
        self.unit_combo.setCurrentText(self.settings.memory_unit)

    def get_settings(self) -> MemorySettings:
        return MemorySettings(
            current_rows=int(self.current_combo.currentText()),
            history_rows=int(self.history_combo.currentText()),
            refresh_rate_ms=self.refresh_slider.value() * 100,
            retention_minutes=self.retention_slider.value(),
            memory_unit=self.unit_combo.currentText(),
        )
