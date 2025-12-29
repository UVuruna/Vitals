"""
Main Window - Process Monitor Display
"""

import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont, QPalette, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .monitor import MonitorMode, MonitorWorker, MonitorData
from .settings_dialog import MonitorSettings, SettingsDialog


class MainWindow(QMainWindow):
    """Main application window."""

    # Colors matching settings dialog
    BG_COLOR = "#1e1e2e"
    CARD_COLOR = "#2a2a3e"
    HEADER_COLOR = "#3a3a4e"
    ACCENT = "#e94560"
    TEXT = "#ffffff"
    TEXT_MUTED = "#aaaaaa"

    # Different colors for current vs history
    CURRENT_BG = "#2d2d42"  # Slightly purple tint
    HISTORY_BG = "#2a3a3e"  # Slightly teal tint

    # Default temperature thresholds
    DEFAULT_TEMP_CONFIG = {
        "normal": "#ffffff",
        "warning": "#ffa500",
        "critical": "#ff4444",
        "warning_threshold": 60,
        "critical_threshold": 75,
    }

    def __init__(self):
        super().__init__()
        self.settings: Optional[MonitorSettings] = None
        self.worker = MonitorWorker(self)
        self.worker.data_ready.connect(self._on_data_ready)
        self.is_paused = False

        self._load_config()
        self._apply_dark_theme()
        self._setup_ui()
        self._show_settings()

    def _load_config(self):
        """Load temperature color config from JSON."""
        config_path = Path(__file__).parent.parent / "config.json"
        self.temp_config = self.DEFAULT_TEMP_CONFIG.copy()

        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    data = json.load(f)
                    if "temp_colors" in data:
                        self.temp_config.update(data["temp_colors"])
            except Exception:
                pass

    def _get_temp_color(self, temp: Optional[float]) -> str:
        """Get color for temperature value based on config thresholds."""
        if temp is None:
            return self.TEXT

        if temp >= self.temp_config["critical_threshold"]:
            return self.temp_config["critical"]
        elif temp >= self.temp_config["warning_threshold"]:
            return self.temp_config["warning"]
        else:
            return self.temp_config["normal"]

    def _apply_dark_theme(self):
        """Apply dark theme to window."""
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(self.BG_COLOR))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(self.TEXT))
        palette.setColor(QPalette.ColorRole.Base, QColor(self.CARD_COLOR))
        palette.setColor(QPalette.ColorRole.Text, QColor(self.TEXT))
        palette.setColor(QPalette.ColorRole.Button, QColor(self.HEADER_COLOR))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(self.TEXT))
        self.setPalette(palette)

    def _setup_ui(self):
        """Initialize the main UI."""
        self.setWindowTitle("Process Monitor")
        self.setMinimumWidth(520)
        self.setMinimumHeight(500)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Header
        self.header_widget = QWidget()
        self.header_widget.setStyleSheet(f"""
            background-color: {self.CARD_COLOR};
            border-radius: 8px;
        """)
        header_layout = QVBoxLayout(self.header_widget)
        header_layout.setContentsMargins(16, 12, 16, 12)

        self.title_label = QLabel("CPU Monitor")
        self.title_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.title_label.setStyleSheet(f"color: {self.TEXT}; background: transparent;")
        header_layout.addWidget(self.title_label)

        self.current_label = QLabel("Current: --")
        self.current_label.setFont(QFont("Segoe UI", 12))
        self.current_label.setStyleSheet(f"color: {self.TEXT}; background: transparent;")
        header_layout.addWidget(self.current_label)

        self.peak_label = QLabel("Peak: --")
        self.peak_label.setFont(QFont("Segoe UI", 10))
        self.peak_label.setStyleSheet(f"color: {self.TEXT_MUTED}; background: transparent;")
        header_layout.addWidget(self.peak_label)

        # HWiNFO sensors row (spread across width)
        self.sensor_widget = QWidget()
        self.sensor_widget.setStyleSheet("background: transparent;")
        sensor_layout = QHBoxLayout(self.sensor_widget)
        sensor_layout.setContentsMargins(0, 4, 0, 0)
        sensor_layout.setSpacing(0)

        self.sensor_labels: list[QLabel] = []
        for _ in range(3):
            lbl = QLabel("")
            lbl.setFont(QFont("Segoe UI", 11))
            lbl.setStyleSheet(f"color: {self.TEXT}; background: transparent;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sensor_layout.addWidget(lbl)
            self.sensor_labels.append(lbl)

        header_layout.addWidget(self.sensor_widget)

        layout.addWidget(self.header_widget)

        # Splitter for resizable sections
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {self.HEADER_COLOR};
                height: 4px;
            }}
            QSplitter::handle:hover {{
                background-color: {self.ACCENT};
            }}
        """)

        # Current Processes section
        self.current_section = QWidget()
        current_layout = QVBoxLayout(self.current_section)
        current_layout.setContentsMargins(0, 0, 0, 4)
        current_layout.setSpacing(4)

        self.current_title = QLabel("Current Processes")
        self.current_title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.current_title.setStyleSheet(f"color: {self.TEXT};")
        current_layout.addWidget(self.current_title)

        self.current_table = self._create_table(7, has_cores=True, bg_color=self.CURRENT_BG)
        current_layout.addWidget(self.current_table)

        self.splitter.addWidget(self.current_section)

        # History section
        self.history_section = QWidget()
        history_layout = QVBoxLayout(self.history_section)
        history_layout.setContentsMargins(0, 4, 0, 0)
        history_layout.setSpacing(4)

        self.history_title = QLabel("Historical Peak Usage")
        self.history_title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.history_title.setStyleSheet(f"color: {self.TEXT};")
        history_layout.addWidget(self.history_title)

        self.history_table = self._create_table(4, has_cores=True, has_time=True, bg_color=self.HISTORY_BG)
        history_layout.addWidget(self.history_table)

        self.splitter.addWidget(self.history_section)

        # Set initial sizes (current gets more space)
        self.splitter.setSizes([300, 150])

        layout.addWidget(self.splitter)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setFont(QFont("Segoe UI", 11))
        self.pause_btn.setFixedSize(100, 36)
        self.pause_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.HEADER_COLOR};
                color: {self.TEXT};
                border: none;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: #4a4a5e;
            }}
        """)
        self.pause_btn.clicked.connect(self._toggle_pause)
        btn_layout.addWidget(self.pause_btn)

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setFont(QFont("Segoe UI", 11))
        self.settings_btn.setFixedSize(100, 36)
        self.settings_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.HEADER_COLOR};
                color: {self.TEXT};
                border: none;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: #4a4a5e;
            }}
        """)
        self.settings_btn.clicked.connect(self._show_settings)
        btn_layout.addWidget(self.settings_btn)

        layout.addLayout(btn_layout)

        # Menu
        menubar = self.menuBar()
        menubar.setStyleSheet(f"""
            QMenuBar {{
                background-color: {self.BG_COLOR};
                color: {self.TEXT};
            }}
            QMenuBar::item:selected {{
                background-color: {self.HEADER_COLOR};
            }}
        """)

        file_menu = menubar.addMenu("File")
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self._show_settings)
        file_menu.addAction(settings_action)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        view_menu = menubar.addMenu("View")
        pause_action = QAction("Pause/Resume", self)
        pause_action.triggered.connect(self._toggle_pause)
        view_menu.addAction(pause_action)

    def _create_table(self, rows: int, has_cores: bool = False, has_time: bool = False, bg_color: str = None) -> QTableWidget:
        """Create a styled table."""
        if bg_color is None:
            bg_color = self.CARD_COLOR

        cols = 2  # Process, Usage
        headers = ["Process", "Usage"]

        if has_cores:
            cols += 1
            headers.append("Threads")
        if has_time:
            cols += 1
            headers.append("Time")

        table = QTableWidget(rows, cols)
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)

        # Column widths
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(1, 100)

        col_idx = 2
        if has_cores:
            header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Fixed)
            table.setColumnWidth(col_idx, 60)
            col_idx += 1
        if has_time:
            header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Fixed)
            table.setColumnWidth(col_idx, 60)

        # Styling
        table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {bg_color};
                color: {self.TEXT};
                border: none;
                border-radius: 6px;
            }}
            QTableWidget::item {{
                padding: 4px 8px;
                border-bottom: 1px solid {self.HEADER_COLOR};
            }}
            QHeaderView::section {{
                background-color: {self.HEADER_COLOR};
                color: {self.TEXT};
                font-weight: bold;
                padding: 8px;
                border: none;
            }}
        """)

        table.verticalHeader().setDefaultSectionSize(32)

        return table

    def _show_settings(self):
        """Show settings dialog."""
        self.worker.stop()
        is_first_run = self.settings is None

        dialog = SettingsDialog(self, self.settings)
        if dialog.exec():
            new_settings = dialog.get_settings()
            self._apply_settings(new_settings)
            self._start_monitoring()
        elif is_first_run:
            # Exit app if settings rejected on first run
            import os
            os._exit(0)

    def _apply_settings(self, new_settings: MonitorSettings):
        """Apply settings, preserving history if mode unchanged."""
        self.settings = new_settings

        # Configure the worker (handles mode change internally)
        self.worker.configure(
            mode=new_settings.mode,
            cpu_threads=new_settings.cpu_threads,
            ram_gb=new_settings.ram_gb,
            current_rows=new_settings.current_rows,
            history_rows=new_settings.history_rows,
            retention_minutes=new_settings.retention_minutes,
            refresh_rate_ms=new_settings.refresh_rate_ms,
            memory_unit=new_settings.memory_unit,
        )

        # Update title
        is_cpu = new_settings.mode == MonitorMode.CPU
        self.title_label.setText("CPU Monitor" if is_cpu else "Memory Monitor")

        # Rebuild tables with correct columns
        self._rebuild_tables()

        # Resize window
        row_height = 32
        total_rows = new_settings.current_rows + new_settings.history_rows
        new_height = 200 + (total_rows + 2) * row_height + 100
        self.resize(520, new_height)

    def _rebuild_tables(self):
        """Rebuild tables based on mode."""
        if not self.settings:
            return

        is_cpu = self.settings.mode == MonitorMode.CPU

        # Get section layouts
        current_layout = self.current_section.layout()
        history_layout = self.history_section.layout()

        # Remove old tables
        current_layout.removeWidget(self.current_table)
        history_layout.removeWidget(self.history_table)
        self.current_table.deleteLater()
        self.history_table.deleteLater()

        # Create new tables - Threads only for CPU mode
        self.current_table = self._create_table(
            self.settings.current_rows,
            has_cores=is_cpu,
            has_time=False,
            bg_color=self.CURRENT_BG
        )
        self.history_table = self._create_table(
            self.settings.history_rows,
            has_cores=is_cpu,
            has_time=True,
            bg_color=self.HISTORY_BG
        )

        # Add to section layouts (after title labels)
        current_layout.addWidget(self.current_table)
        history_layout.addWidget(self.history_table)

    def _start_monitoring(self):
        """Start monitoring."""
        if self.settings:
            self.worker.start()
            self.is_paused = False
            self.pause_btn.setText("Pause")

    def _toggle_pause(self):
        """Toggle pause."""
        if self.is_paused:
            self.worker.start()
            self.is_paused = False
            self.pause_btn.setText("Pause")
        else:
            self.worker.stop()
            self.is_paused = True
            self.pause_btn.setText("Resume")

    def _on_data_ready(self, data: MonitorData):
        """Handle data from worker thread (runs on main thread via signal)."""
        if not self.settings:
            return

        unit = self.settings.memory_unit
        is_cpu = self.settings.mode == MonitorMode.CPU
        monitor = self.worker.monitor

        # Update header
        self.current_label.setText(f"Current: {data.total_display}")
        self.peak_label.setText(data.max_display)

        # Get HWiNFO sensor data
        hwinfo = data.hwinfo

        if is_cpu:
            # CPU mode: show CPU temps + power in 3 columns
            sensors = [
                (f"Tctl: {hwinfo.cpu_tctl:.0f}°C", hwinfo.cpu_tctl) if hwinfo.cpu_tctl else ("", None),
                (f"{hwinfo.cpu_power:.1f} W", None) if hwinfo.cpu_power else ("", None),
                (f"CCD1: {hwinfo.cpu_ccd1:.0f}°C", hwinfo.cpu_ccd1) if hwinfo.cpu_ccd1 else ("", None),
            ]
            for i, (text, value) in enumerate(sensors):
                self.sensor_labels[i].setText(text)
                self.sensor_labels[i].setStyleSheet(
                    f"color: {self._get_temp_color(value)}; background: transparent;"
                )
        else:
            # Memory mode: show ambient temp and DRAM bandwidth
            extras = [
                (f"Amb: {hwinfo.ambient_temp:.0f}°C", hwinfo.ambient_temp) if hwinfo.ambient_temp else ("", None),
                (f"R: {hwinfo.dram_read:,.0f} MB/s", None) if hwinfo.dram_read else ("", None),
                (f"W: {hwinfo.dram_write:,.0f} MB/s", None) if hwinfo.dram_write else ("", None),
            ]
            for i, (text, value) in enumerate(extras):
                self.sensor_labels[i].setText(text)
                self.sensor_labels[i].setStyleSheet(
                    f"color: {self._get_temp_color(value) if value else self.TEXT}; background: transparent;"
                )

        # Update current table
        for row, proc in enumerate(data.processes):
            if row >= self.current_table.rowCount():
                break

            self.current_table.setItem(row, 0, QTableWidgetItem(proc.name))
            value_str = monitor.format_value(proc.value, unit) if monitor else f"{proc.value:.0f}"
            self.current_table.setItem(row, 1, QTableWidgetItem(value_str))

            if is_cpu:
                threads_text = str(proc.threads) if proc.threads > 0 else ""
                self.current_table.setItem(row, 2, QTableWidgetItem(threads_text))

        # Clear empty rows
        for row in range(len(data.processes), self.current_table.rowCount()):
            for col in range(self.current_table.columnCount()):
                self.current_table.setItem(row, col, QTableWidgetItem(""))

        # Update history table
        for row, record in enumerate(data.history):
            if row >= self.history_table.rowCount():
                break

            self.history_table.setItem(row, 0, QTableWidgetItem(record.name))
            value_str = monitor.format_value(record.value, unit) if monitor else f"{record.value:.0f}"
            self.history_table.setItem(row, 1, QTableWidgetItem(value_str))

            col = 2
            if is_cpu:
                threads_text = str(record.threads) if record.threads > 0 else ""
                self.history_table.setItem(row, col, QTableWidgetItem(threads_text))
                col += 1

            self.history_table.setItem(row, col, QTableWidgetItem(record.time_str))

        # Clear empty rows
        for row in range(len(data.history), self.history_table.rowCount()):
            for col in range(self.history_table.columnCount()):
                self.history_table.setItem(row, col, QTableWidgetItem(""))

    def keyPressEvent(self, event):
        """Handle keys."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_Space:
            self._toggle_pause()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        """Handle close."""
        self.worker.stop()
        super().closeEvent(event)
