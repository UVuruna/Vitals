"""
Settings Dialog - Simple and Working
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import psutil
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QPalette, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .monitor import MonitorMode
from .styles import Defaults


def get_base_path() -> Path:
    """Get base path for resources (handles PyInstaller frozen exe)."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent


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


class SettingsDialog(QDialog):
    """Settings configuration dialog."""

    def __init__(self, parent: Optional[QWidget] = None, settings: Optional[MonitorSettings] = None):
        super().__init__(parent)
        self.settings = settings or MonitorSettings()

        # Set dark palette for entire dialog
        self.setWindowTitle("Process Monitor - Settings")
        self.setFixedSize(480, 580)

        # Set window icon
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
        """Create a styled label."""
        label = QLabel(text)
        weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
        label.setFont(QFont("Segoe UI", size, weight))
        label.setStyleSheet(f"color: {color}; background: transparent;")
        return label

    def _make_combo(self, items: list, default: str) -> QComboBox:
        """Create a styled combo box."""
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
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
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
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 24, 32, 24)

        # Title
        title = self._make_label("Process Monitor", 20, bold=True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = self._make_label("Configure monitoring preferences", 10, color="#888888")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(12)

        # === Monitor Mode ===
        layout.addWidget(self._make_label("Monitor Mode", 12, bold=True))

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)

        self.cpu_btn = QPushButton("CPU Usage")
        self.cpu_btn.setFont(QFont("Segoe UI", 11))
        self.cpu_btn.setFixedHeight(36)
        self.cpu_btn.setCheckable(True)
        self.cpu_btn.setChecked(True)
        self.cpu_btn.clicked.connect(lambda: self._set_mode(MonitorMode.CPU))
        mode_row.addWidget(self.cpu_btn)

        self.mem_btn = QPushButton("Memory Usage")
        self.mem_btn.setFont(QFont("Segoe UI", 11))
        self.mem_btn.setFixedHeight(36)
        self.mem_btn.setCheckable(True)
        self.mem_btn.clicked.connect(lambda: self._set_mode(MonitorMode.MEMORY))
        mode_row.addWidget(self.mem_btn)

        self._update_mode_buttons()
        layout.addLayout(mode_row)

        layout.addSpacing(8)

        # === Display Settings ===
        layout.addWidget(self._make_label("Display Settings", 12, bold=True))

        # Current processes
        row1 = QHBoxLayout()
        row1.addWidget(self._make_label("Current processes:", 11, color="#aaaaaa"))
        row1.addStretch()
        self.current_combo = self._make_combo([str(i) for i in range(1, 16)], "7")
        row1.addWidget(self.current_combo)
        layout.addLayout(row1)

        # History records
        row2 = QHBoxLayout()
        row2.addWidget(self._make_label("History records:", 11, color="#aaaaaa"))
        row2.addStretch()
        self.history_combo = self._make_combo([str(i) for i in range(1, 16)], "4")
        row2.addWidget(self.history_combo)
        layout.addLayout(row2)

        # Refresh rate
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

        # History retention
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

        # === Memory Settings ===
        layout.addWidget(self._make_label("Memory Settings", 12, bold=True))

        # Memory unit
        row5 = QHBoxLayout()
        row5.addWidget(self._make_label("Display unit:", 11, color="#aaaaaa"))
        row5.addStretch()
        self.unit_combo = self._make_combo(["KB", "MB", "GB"], "MB")
        row5.addWidget(self.unit_combo)
        layout.addLayout(row5)

        # System info (read-only)
        cpu_threads = psutil.cpu_count() or 8
        ram_gb = round(psutil.virtual_memory().total / (1024 ** 3))

        info_label = self._make_label(f"Detected: {cpu_threads} CPU threads, {ram_gb} GB RAM", 10, color="#666666")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_label)

        layout.addStretch()

        # Start Button
        self.start_btn = QPushButton("Start Monitoring")
        self.start_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.start_btn.setFixedHeight(44)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #e94560;
                color: white;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #ff6b6b;
            }
        """)
        self.start_btn.clicked.connect(self.accept)
        layout.addWidget(self.start_btn)

    def _update_mode_buttons(self):
        """Update mode button styles."""
        active_style = """
            QPushButton {
                background-color: #e94560;
                color: white;
                border: none;
                border-radius: 6px;
            }
        """
        inactive_style = """
            QPushButton {
                background-color: #3a3a4e;
                color: #888888;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #4a4a5e;
            }
        """
        self.cpu_btn.setStyleSheet(active_style if self.cpu_btn.isChecked() else inactive_style)
        self.mem_btn.setStyleSheet(active_style if self.mem_btn.isChecked() else inactive_style)

    def _set_mode(self, mode: MonitorMode):
        """Set monitoring mode."""
        is_cpu = mode == MonitorMode.CPU
        self.cpu_btn.setChecked(is_cpu)
        self.mem_btn.setChecked(not is_cpu)
        self._update_mode_buttons()

    def _load_settings(self):
        """Load current settings into UI."""
        self._set_mode(self.settings.mode)
        self.current_combo.setCurrentText(str(self.settings.current_rows))
        self.history_combo.setCurrentText(str(self.settings.history_rows))
        self.refresh_slider.setValue(self.settings.refresh_rate_ms // 100)
        self.retention_slider.setValue(self.settings.retention_minutes)
        self.unit_combo.setCurrentText(self.settings.memory_unit)

    def get_settings(self) -> MonitorSettings:
        """Get settings from UI values."""
        return MonitorSettings(
            mode=MonitorMode.CPU if self.cpu_btn.isChecked() else MonitorMode.MEMORY,
            current_rows=int(self.current_combo.currentText()),
            history_rows=int(self.history_combo.currentText()),
            refresh_rate_ms=self.refresh_slider.value() * 100,
            retention_minutes=self.retention_slider.value(),
            memory_unit=self.unit_combo.currentText(),
        )


class InitialSettingsDialog(QDialog):
    """Initial settings dialog with checkbox mode selection."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Process Monitor - Setup")
        self.setFixedSize(480, 580)

        # Set window icon
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
        """Create a styled label."""
        label = QLabel(text)
        weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
        label.setFont(QFont("Segoe UI", size, weight))
        label.setStyleSheet(f"color: {color}; background: transparent;")
        return label

    def _make_combo(self, items: list, default: str) -> QComboBox:
        """Create a styled combo box."""
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
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
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
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 24, 32, 24)

        # Title
        title = self._make_label("Process Monitor", 20, bold=True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = self._make_label("Select monitors to open", 10, color="#888888")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(12)

        # === Monitor Mode (Checkboxes) ===
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

        # Apply initial button styles (can't call _update_mode_buttons yet - start_btn not created)
        active_style = """
            QPushButton {
                background-color: #e94560;
                color: white;
                border: none;
                border-radius: 6px;
            }
        """
        inactive_style = """
            QPushButton {
                background-color: #3a3a4e;
                color: #888888;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #4a4a5e;
            }
        """
        self.cpu_btn.setStyleSheet(active_style)
        self.mem_btn.setStyleSheet(inactive_style)

        layout.addLayout(mode_row)

        # Hint text
        hint = self._make_label("Select one or both monitors", 9, color="#666666")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        layout.addSpacing(8)

        # === Display Settings ===
        layout.addWidget(self._make_label("Display Settings", 12, bold=True))

        # Current processes
        row1 = QHBoxLayout()
        row1.addWidget(self._make_label("Current processes:", 11, color="#aaaaaa"))
        row1.addStretch()
        self.current_combo = self._make_combo([str(i) for i in range(1, 16)], str(Defaults.CURRENT_ROWS))
        row1.addWidget(self.current_combo)
        layout.addLayout(row1)

        # History records
        row2 = QHBoxLayout()
        row2.addWidget(self._make_label("History records:", 11, color="#aaaaaa"))
        row2.addStretch()
        self.history_combo = self._make_combo([str(i) for i in range(1, 16)], str(Defaults.HISTORY_ROWS))
        row2.addWidget(self.history_combo)
        layout.addLayout(row2)

        # Refresh rate
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

        # History retention
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

        # === Memory Settings ===
        layout.addWidget(self._make_label("Memory Settings", 12, bold=True))

        # Memory unit
        row5 = QHBoxLayout()
        row5.addWidget(self._make_label("Display unit:", 11, color="#aaaaaa"))
        row5.addStretch()
        self.unit_combo = self._make_combo(["KB", "MB", "GB"], Defaults.MEMORY_UNIT)
        row5.addWidget(self.unit_combo)
        layout.addLayout(row5)

        # System info
        cpu_threads = psutil.cpu_count() or 8
        ram_gb = round(psutil.virtual_memory().total / (1024 ** 3))
        info_label = self._make_label(f"Detected: {cpu_threads} CPU threads, {ram_gb} GB RAM", 10, color="#666666")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_label)

        layout.addStretch()

        # Start Button
        self.start_btn = QPushButton("Start Monitoring")
        self.start_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.start_btn.setFixedHeight(44)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #e94560;
                color: white;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #ff6b6b;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
        """)
        self.start_btn.clicked.connect(self._on_start)
        layout.addWidget(self.start_btn)

    def _update_mode_buttons(self):
        """Update mode button styles (both can be selected)."""
        active_style = """
            QPushButton {
                background-color: #e94560;
                color: white;
                border: none;
                border-radius: 6px;
            }
        """
        inactive_style = """
            QPushButton {
                background-color: #3a3a4e;
                color: #888888;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #4a4a5e;
            }
        """
        self.cpu_btn.setStyleSheet(active_style if self.cpu_btn.isChecked() else inactive_style)
        self.mem_btn.setStyleSheet(active_style if self.mem_btn.isChecked() else inactive_style)

        # Disable start if nothing selected
        self.start_btn.setEnabled(self.cpu_btn.isChecked() or self.mem_btn.isChecked())

    def _on_start(self):
        """Handle start button click."""
        if not self.cpu_btn.isChecked() and not self.mem_btn.isChecked():
            return
        self.accept()

    def get_settings(self) -> InitialSettings:
        """Get settings from dialog."""
        return InitialSettings(
            cpu_enabled=self.cpu_btn.isChecked(),
            memory_enabled=self.mem_btn.isChecked(),
            current_rows=int(self.current_combo.currentText()),
            history_rows=int(self.history_combo.currentText()),
            refresh_rate_ms=self.refresh_slider.value() * 100,
            retention_minutes=self.retention_slider.value(),
            memory_unit=self.unit_combo.currentText(),
        )


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


class CPUSettingsDialog(QDialog):
    """Settings dialog for CPU window (no mode selection, no memory unit)."""

    def __init__(self, parent: Optional[QWidget] = None, settings: Optional[CPUSettings] = None):
        super().__init__(parent)
        self.settings = settings or CPUSettings()
        self.setWindowTitle("CPU Monitor - Settings")
        self.setFixedSize(400, 380)

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
        """Create a styled label."""
        label = QLabel(text)
        weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
        label.setFont(QFont("Segoe UI", size, weight))
        label.setStyleSheet(f"color: {color}; background: transparent;")
        return label

    def _make_combo(self, items: list, default: str) -> QComboBox:
        """Create a styled combo box."""
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
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 24, 32, 24)

        title = self._make_label("CPU Monitor Settings", 16, bold=True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(12)

        # Current processes
        row1 = QHBoxLayout()
        row1.addWidget(self._make_label("Current processes:", 11, color="#aaaaaa"))
        row1.addStretch()
        self.current_combo = self._make_combo([str(i) for i in range(1, 16)], "7")
        row1.addWidget(self.current_combo)
        layout.addLayout(row1)

        # History records
        row2 = QHBoxLayout()
        row2.addWidget(self._make_label("History records:", 11, color="#aaaaaa"))
        row2.addStretch()
        self.history_combo = self._make_combo([str(i) for i in range(1, 16)], "4")
        row2.addWidget(self.history_combo)
        layout.addLayout(row2)

        # Refresh rate
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

        # Retention
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

        layout.addStretch()

        # Apply button
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

    def _load_settings(self):
        """Load current settings into UI."""
        self.current_combo.setCurrentText(str(self.settings.current_rows))
        self.history_combo.setCurrentText(str(self.settings.history_rows))
        self.refresh_slider.setValue(self.settings.refresh_rate_ms // 100)
        self.retention_slider.setValue(self.settings.retention_minutes)

    def get_settings(self) -> CPUSettings:
        """Get settings from UI values."""
        return CPUSettings(
            current_rows=int(self.current_combo.currentText()),
            history_rows=int(self.history_combo.currentText()),
            refresh_rate_ms=self.refresh_slider.value() * 100,
            retention_minutes=self.retention_slider.value(),
        )


class MemorySettingsDialog(QDialog):
    """Settings dialog for Memory window (no mode selection, has memory unit)."""

    def __init__(self, parent: Optional[QWidget] = None, settings: Optional[MemorySettings] = None):
        super().__init__(parent)
        self.settings = settings or MemorySettings()
        self.setWindowTitle("Memory Monitor - Settings")
        self.setFixedSize(400, 440)

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
        """Create a styled label."""
        label = QLabel(text)
        weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
        label.setFont(QFont("Segoe UI", size, weight))
        label.setStyleSheet(f"color: {color}; background: transparent;")
        return label

    def _make_combo(self, items: list, default: str) -> QComboBox:
        """Create a styled combo box."""
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
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 24, 32, 24)

        title = self._make_label("Memory Monitor Settings", 16, bold=True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(12)

        # Current processes
        row1 = QHBoxLayout()
        row1.addWidget(self._make_label("Current processes:", 11, color="#aaaaaa"))
        row1.addStretch()
        self.current_combo = self._make_combo([str(i) for i in range(1, 16)], "7")
        row1.addWidget(self.current_combo)
        layout.addLayout(row1)

        # History records
        row2 = QHBoxLayout()
        row2.addWidget(self._make_label("History records:", 11, color="#aaaaaa"))
        row2.addStretch()
        self.history_combo = self._make_combo([str(i) for i in range(1, 16)], "4")
        row2.addWidget(self.history_combo)
        layout.addLayout(row2)

        # Refresh rate
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

        # Retention
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

        # Memory unit
        layout.addWidget(self._make_label("Memory Settings", 12, bold=True))
        row5 = QHBoxLayout()
        row5.addWidget(self._make_label("Display unit:", 11, color="#aaaaaa"))
        row5.addStretch()
        self.unit_combo = self._make_combo(["KB", "MB", "GB"], "MB")
        row5.addWidget(self.unit_combo)
        layout.addLayout(row5)

        layout.addStretch()

        # Apply button
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

    def _load_settings(self):
        """Load current settings into UI."""
        self.current_combo.setCurrentText(str(self.settings.current_rows))
        self.history_combo.setCurrentText(str(self.settings.history_rows))
        self.refresh_slider.setValue(self.settings.refresh_rate_ms // 100)
        self.retention_slider.setValue(self.settings.retention_minutes)
        self.unit_combo.setCurrentText(self.settings.memory_unit)

    def get_settings(self) -> MemorySettings:
        """Get settings from UI values."""
        return MemorySettings(
            current_rows=int(self.current_combo.currentText()),
            history_rows=int(self.history_combo.currentText()),
            refresh_rate_ms=self.refresh_slider.value() * 100,
            retention_minutes=self.retention_slider.value(),
            memory_unit=self.unit_combo.currentText(),
        )
