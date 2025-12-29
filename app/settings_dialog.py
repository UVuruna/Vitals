"""
Settings Dialog

Configuration dialog for Process Monitor settings.
"""

from dataclasses import dataclass
from typing import Optional

import psutil
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .monitor import MonitorMode
from .styles import Colors, Defaults, Dimensions, Fonts


@dataclass
class MonitorSettings:
    """Application settings container."""

    mode: MonitorMode = MonitorMode.CPU
    current_rows: int = Defaults.CURRENT_ROWS
    history_rows: int = Defaults.HISTORY_ROWS
    refresh_rate_ms: int = Defaults.REFRESH_RATE_MS
    retention_minutes: int = Defaults.RETENTION_MINUTES
    memory_unit: str = Defaults.MEMORY_UNIT
    cpu_threads: int = 0
    ram_gb: int = 0

    def __post_init__(self):
        if self.cpu_threads == 0:
            self.cpu_threads = psutil.cpu_count() or 8
        if self.ram_gb == 0:
            self.ram_gb = round(psutil.virtual_memory().total / (1024 ** 3))


class SettingsDialog(QDialog):
    """
    Settings configuration dialog.

    Allows user to configure monitoring mode and display options.
    """

    def __init__(self, parent: Optional[QWidget] = None, settings: Optional[MonitorSettings] = None):
        super().__init__(parent)
        self.settings = settings or MonitorSettings()
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        """Initialize the UI components."""
        self.setWindowTitle("Process Monitor - Settings")
        self.setFixedSize(Dimensions.SETTINGS_WIDTH, Dimensions.SETTINGS_HEIGHT)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Colors.BACKGROUND};
            }}
            QGroupBox {{
                font-family: {Fonts.FAMILY};
                font-size: {Fonts.SIZE_BODY}pt;
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}
            QLabel {{
                font-family: {Fonts.FAMILY};
                font-size: {Fonts.SIZE_BODY}pt;
            }}
            QPushButton {{
                font-family: {Fonts.FAMILY};
                font-size: {Fonts.SIZE_BODY}pt;
                padding: 8px 20px;
                border-radius: 4px;
            }}
            QPushButton#startButton {{
                background-color: {Colors.ACCENT_CPU};
                color: white;
                font-weight: bold;
            }}
            QPushButton#startButton:hover {{
                background-color: #FF5252;
            }}
            QComboBox, QSpinBox {{
                font-family: {Fonts.FAMILY};
                font-size: {Fonts.SIZE_BODY}pt;
                padding: 4px;
            }}
            QSlider::groove:horizontal {{
                height: 6px;
                background: #ddd;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {Colors.ACCENT_CPU};
                width: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(Dimensions.SPACING)
        layout.setContentsMargins(
            Dimensions.MARGIN,
            Dimensions.MARGIN,
            Dimensions.MARGIN,
            Dimensions.MARGIN,
        )

        # Monitor Mode Group
        mode_group = self._create_mode_group()
        layout.addWidget(mode_group)

        # Display Settings Group
        display_group = self._create_display_group()
        layout.addWidget(display_group)

        # System Settings Group
        system_group = self._create_system_group()
        layout.addWidget(system_group)

        # Buttons
        layout.addStretch()
        button_layout = self._create_buttons()
        layout.addLayout(button_layout)

    def _create_mode_group(self) -> QGroupBox:
        """Create monitor mode selection group."""
        group = QGroupBox("Monitor Mode")
        layout = QHBoxLayout(group)

        self.mode_group = QButtonGroup(self)

        self.cpu_radio = QRadioButton("CPU Usage")
        self.cpu_radio.setChecked(True)
        self.mode_group.addButton(self.cpu_radio, 0)
        layout.addWidget(self.cpu_radio)

        self.memory_radio = QRadioButton("Memory Usage")
        self.mode_group.addButton(self.memory_radio, 1)
        layout.addWidget(self.memory_radio)

        layout.addStretch()

        return group

    def _create_display_group(self) -> QGroupBox:
        """Create display settings group."""
        group = QGroupBox("Display Settings")
        layout = QFormLayout(group)

        # Current rows
        self.current_rows_spin = QSpinBox()
        self.current_rows_spin.setRange(1, 15)
        self.current_rows_spin.setValue(Defaults.CURRENT_ROWS)
        layout.addRow("Current processes:", self.current_rows_spin)

        # History rows
        self.history_rows_spin = QSpinBox()
        self.history_rows_spin.setRange(1, 15)
        self.history_rows_spin.setValue(Defaults.HISTORY_ROWS)
        layout.addRow("History records:", self.history_rows_spin)

        # Refresh rate slider
        refresh_container = QWidget()
        refresh_layout = QHBoxLayout(refresh_container)
        refresh_layout.setContentsMargins(0, 0, 0, 0)

        self.refresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.refresh_slider.setRange(5, 50)  # 500ms to 5000ms (in 100ms steps)
        self.refresh_slider.setValue(Defaults.REFRESH_RATE_MS // 100)
        self.refresh_slider.valueChanged.connect(self._on_refresh_changed)
        refresh_layout.addWidget(self.refresh_slider)

        self.refresh_label = QLabel(f"{Defaults.REFRESH_RATE_MS} ms")
        self.refresh_label.setMinimumWidth(60)
        refresh_layout.addWidget(self.refresh_label)

        layout.addRow("Refresh rate:", refresh_container)

        # Retention time slider
        retention_container = QWidget()
        retention_layout = QHBoxLayout(retention_container)
        retention_layout.setContentsMargins(0, 0, 0, 0)

        self.retention_slider = QSlider(Qt.Orientation.Horizontal)
        self.retention_slider.setRange(10, 360)
        self.retention_slider.setValue(Defaults.RETENTION_MINUTES)
        self.retention_slider.valueChanged.connect(self._on_retention_changed)
        retention_layout.addWidget(self.retention_slider)

        self.retention_label = QLabel(f"{Defaults.RETENTION_MINUTES} min")
        self.retention_label.setMinimumWidth(60)
        retention_layout.addWidget(self.retention_label)

        layout.addRow("History retention:", retention_container)

        return group

    def _create_system_group(self) -> QGroupBox:
        """Create system settings group."""
        group = QGroupBox("System Settings")
        layout = QFormLayout(group)

        # Memory unit
        self.memory_unit_combo = QComboBox()
        self.memory_unit_combo.addItems(["KB", "MB", "GB"])
        self.memory_unit_combo.setCurrentText(Defaults.MEMORY_UNIT)
        layout.addRow("Memory unit:", self.memory_unit_combo)

        # CPU threads
        detected_threads = psutil.cpu_count() or 8
        self.cpu_threads_combo = QComboBox()
        thread_options = [str(2 ** i) for i in range(1, 8)]  # 2, 4, 8, 16, 32, 64, 128
        self.cpu_threads_combo.addItems(thread_options)
        self.cpu_threads_combo.setCurrentText(str(detected_threads))
        layout.addRow("CPU threads:", self.cpu_threads_combo)

        # RAM
        detected_ram = round(psutil.virtual_memory().total / (1024 ** 3))
        self.ram_combo = QComboBox()
        ram_options = [str(2 ** i) for i in range(2, 8)]  # 4, 8, 16, 32, 64, 128
        self.ram_combo.addItems(ram_options)
        self.ram_combo.setCurrentText(str(detected_ram))
        layout.addRow("RAM (GB):", self.ram_combo)

        return group

    def _create_buttons(self) -> QHBoxLayout:
        """Create dialog buttons."""
        layout = QHBoxLayout()
        layout.addStretch()

        self.start_button = QPushButton("Start Monitoring")
        self.start_button.setObjectName("startButton")
        self.start_button.clicked.connect(self.accept)
        layout.addWidget(self.start_button)

        return layout

    def _on_refresh_changed(self, value: int):
        """Handle refresh rate slider change."""
        ms = value * 100
        self.refresh_label.setText(f"{ms} ms")

    def _on_retention_changed(self, value: int):
        """Handle retention slider change."""
        self.retention_label.setText(f"{value} min")

    def _load_settings(self):
        """Load current settings into UI."""
        if self.settings.mode == MonitorMode.MEMORY:
            self.memory_radio.setChecked(True)
        else:
            self.cpu_radio.setChecked(True)

        self.current_rows_spin.setValue(self.settings.current_rows)
        self.history_rows_spin.setValue(self.settings.history_rows)
        self.refresh_slider.setValue(self.settings.refresh_rate_ms // 100)
        self.retention_slider.setValue(self.settings.retention_minutes)
        self.memory_unit_combo.setCurrentText(self.settings.memory_unit)
        self.cpu_threads_combo.setCurrentText(str(self.settings.cpu_threads))
        self.ram_combo.setCurrentText(str(self.settings.ram_gb))

    def get_settings(self) -> MonitorSettings:
        """Get settings from UI values."""
        return MonitorSettings(
            mode=MonitorMode.MEMORY if self.memory_radio.isChecked() else MonitorMode.CPU,
            current_rows=self.current_rows_spin.value(),
            history_rows=self.history_rows_spin.value(),
            refresh_rate_ms=self.refresh_slider.value() * 100,
            retention_minutes=self.retention_slider.value(),
            memory_unit=self.memory_unit_combo.currentText(),
            cpu_threads=int(self.cpu_threads_combo.currentText()),
            ram_gb=int(self.ram_combo.currentText()),
        )
