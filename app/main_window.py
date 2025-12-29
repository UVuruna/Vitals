"""
Main Window - Process Monitor Display
"""

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QFont, QPalette, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .monitor import MonitorMode, ProcessMonitor
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

    def __init__(self):
        super().__init__()
        self.settings: Optional[MonitorSettings] = None
        self.monitor: Optional[ProcessMonitor] = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update)
        self.is_paused = False

        self._apply_dark_theme()
        self._setup_ui()
        self._show_settings()

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

        layout.addWidget(self.header_widget)

        # Current Processes
        current_title = QLabel("Current Processes")
        current_title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        current_title.setStyleSheet(f"color: {self.TEXT};")
        layout.addWidget(current_title)

        self.current_table = self._create_table(7, has_cores=True)
        layout.addWidget(self.current_table)

        # History
        history_title = QLabel("Historical Peak Usage")
        history_title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        history_title.setStyleSheet(f"color: {self.TEXT};")
        layout.addWidget(history_title)

        self.history_table = self._create_table(4, has_cores=True, has_time=True)
        layout.addWidget(self.history_table)

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

    def _create_table(self, rows: int, has_cores: bool = False, has_time: bool = False) -> QTableWidget:
        """Create a styled table."""
        cols = 2  # Process, Usage
        headers = ["Process", "Usage"]

        if has_cores:
            cols += 1
            headers.append("Cores")
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
                background-color: {self.CARD_COLOR};
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
        self.timer.stop()
        dialog = SettingsDialog(self, self.settings)
        if dialog.exec():
            self.settings = dialog.get_settings()
            self._apply_settings()
            self._start_monitoring()

    def _apply_settings(self):
        """Apply settings."""
        if not self.settings:
            return

        # Create monitor
        self.monitor = ProcessMonitor(
            mode=self.settings.mode,
            cpu_threads=self.settings.cpu_threads,
            ram_gb=self.settings.ram_gb,
        )
        self.monitor.set_history_settings(
            self.settings.history_rows,
            self.settings.retention_minutes,
        )

        # Update title
        is_cpu = self.settings.mode == MonitorMode.CPU
        self.title_label.setText("CPU Monitor" if is_cpu else "Memory Monitor")

        # Rebuild tables with correct columns
        self._rebuild_tables()

        # Resize window
        row_height = 32
        total_rows = self.settings.current_rows + self.settings.history_rows
        new_height = 200 + (total_rows + 2) * row_height + 100
        self.resize(520, new_height)

    def _rebuild_tables(self):
        """Rebuild tables based on mode."""
        if not self.settings:
            return

        is_cpu = self.settings.mode == MonitorMode.CPU

        # Get parent layout
        layout = self.centralWidget().layout()

        # Remove old tables
        layout.removeWidget(self.current_table)
        layout.removeWidget(self.history_table)
        self.current_table.deleteLater()
        self.history_table.deleteLater()

        # Create new tables - Cores only for CPU mode
        self.current_table = self._create_table(
            self.settings.current_rows,
            has_cores=is_cpu,
            has_time=False
        )
        self.history_table = self._create_table(
            self.settings.history_rows,
            has_cores=is_cpu,
            has_time=True
        )

        # Insert at correct positions (after labels)
        layout.insertWidget(2, self.current_table)
        layout.insertWidget(4, self.history_table)

    def _start_monitoring(self):
        """Start monitoring."""
        if self.settings:
            self.timer.start(self.settings.refresh_rate_ms)
            self.is_paused = False
            self.pause_btn.setText("Pause")

    def _toggle_pause(self):
        """Toggle pause."""
        if self.is_paused:
            self.timer.start(self.settings.refresh_rate_ms if self.settings else 2000)
            self.is_paused = False
            self.pause_btn.setText("Pause")
        else:
            self.timer.stop()
            self.is_paused = True
            self.pause_btn.setText("Resume")

    def _update(self):
        """Update display."""
        if not self.monitor or not self.settings:
            return

        unit = self.settings.memory_unit
        is_cpu = self.settings.mode == MonitorMode.CPU

        # Get processes
        processes = self.monitor.get_processes(self.settings.current_rows)
        self.monitor.update_history(processes)

        # Update header
        self.current_label.setText(f"Current: {self.monitor.get_total_display(unit)}")
        self.peak_label.setText(self.monitor.get_max_display(unit))

        # Update current table
        for row, proc in enumerate(processes):
            if row >= self.current_table.rowCount():
                break

            self.current_table.setItem(row, 0, QTableWidgetItem(proc.name))
            self.current_table.setItem(row, 1, QTableWidgetItem(self.monitor.format_value(proc.value, unit)))

            if is_cpu:
                cores_text = f"{proc.cores_used:.1f}" if proc.cores_used >= 0.1 else ""
                self.current_table.setItem(row, 2, QTableWidgetItem(cores_text))

        # Clear empty rows
        for row in range(len(processes), self.current_table.rowCount()):
            for col in range(self.current_table.columnCount()):
                self.current_table.setItem(row, col, QTableWidgetItem(""))

        # Update history table
        history = self.monitor.get_history()
        for row, record in enumerate(history):
            if row >= self.history_table.rowCount():
                break

            self.history_table.setItem(row, 0, QTableWidgetItem(record.name))
            self.history_table.setItem(row, 1, QTableWidgetItem(self.monitor.format_value(record.value, unit)))

            col = 2
            if is_cpu:
                cores_text = f"{record.cores_used:.1f}" if record.cores_used >= 0.1 else ""
                self.history_table.setItem(row, col, QTableWidgetItem(cores_text))
                col += 1

            self.history_table.setItem(row, col, QTableWidgetItem(record.time_str))

        # Clear empty rows
        for row in range(len(history), self.history_table.rowCount()):
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
        self.timer.stop()
        super().closeEvent(event)
