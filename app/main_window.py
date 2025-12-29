"""
Main Window

Primary application window with process monitoring display.
"""

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenuBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .monitor import MonitorMode, ProcessMonitor
from .settings_dialog import MonitorSettings, SettingsDialog
from .styles import Colors, Dimensions, Fonts


class HeaderWidget(QFrame):
    """Header showing current total usage and peak."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"""
            HeaderWidget {{
                background-color: {Colors.CURRENT_HEADER};
                border-radius: 6px;
                padding: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # Title label
        self.title_label = QLabel("CPU Monitor")
        self.title_label.setStyleSheet(f"""
            font-family: {Fonts.FAMILY};
            font-size: {Fonts.SIZE_HEADER}pt;
            font-weight: bold;
            color: {Colors.TEXT_PRIMARY};
        """)
        layout.addWidget(self.title_label)

        # Current usage label
        self.current_label = QLabel("Current: --")
        self.current_label.setStyleSheet(f"""
            font-family: {Fonts.FAMILY};
            font-size: {Fonts.SIZE_BODY}pt;
            color: {Colors.TEXT_PRIMARY};
        """)
        layout.addWidget(self.current_label)

        # Peak usage label
        self.peak_label = QLabel("Peak: --")
        self.peak_label.setStyleSheet(f"""
            font-family: {Fonts.FAMILY};
            font-size: {Fonts.SIZE_SMALL}pt;
            color: {Colors.TEXT_SECONDARY};
        """)
        layout.addWidget(self.peak_label)

    def set_mode(self, mode: MonitorMode):
        """Update header for mode."""
        if mode == MonitorMode.CPU:
            self.title_label.setText("CPU Monitor")
            self.setStyleSheet(f"""
                HeaderWidget {{
                    background-color: {Colors.CURRENT_HEADER};
                    border-radius: 6px;
                }}
            """)
        else:
            self.title_label.setText("Memory Monitor")
            self.setStyleSheet(f"""
                HeaderWidget {{
                    background-color: {Colors.HISTORY_HEADER};
                    border-radius: 6px;
                }}
            """)

    def update_stats(self, current: str, peak: str):
        """Update displayed statistics."""
        self.current_label.setText(f"Current: {current}")
        self.peak_label.setText(peak)


class ProcessTable(QTableWidget):
    """Table for displaying process information."""

    def __init__(
        self,
        rows: int,
        show_cores: bool = True,
        header_color: str = Colors.CURRENT_HEADER,
        body_color: str = Colors.CURRENT_BODY,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.show_cores = show_cores
        self.header_color = header_color
        self.body_color = body_color
        self._setup_ui(rows)

    def _setup_ui(self, rows: int):
        """Initialize table UI."""
        # Columns: Process, Value, Cores (optional)
        cols = 3 if self.show_cores else 2
        self.setColumnCount(cols)
        self.setRowCount(rows)

        headers = ["Process", "Usage"]
        if self.show_cores:
            headers.append("Cores")
        self.setHorizontalHeaderLabels(headers)

        # Styling
        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {self.body_color};
                border: none;
                border-radius: 6px;
                font-family: {Fonts.FAMILY};
                font-size: {Fonts.SIZE_BODY}pt;
            }}
            QTableWidget::item {{
                padding: 4px 8px;
                border-bottom: 1px solid rgba(0,0,0,0.05);
            }}
            QHeaderView::section {{
                background-color: {self.header_color};
                font-family: {Fonts.FAMILY};
                font-size: {Fonts.SIZE_BODY}pt;
                font-weight: bold;
                padding: 6px;
                border: none;
            }}
        """)

        # Configure columns
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(1, 100)
        if self.show_cores:
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(2, 60)

        # Hide row numbers
        self.verticalHeader().setVisible(False)

        # Row height
        self.verticalHeader().setDefaultSectionSize(Dimensions.TABLE_ROW_HEIGHT)

        # Selection behavior
        self.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

    def set_row_count(self, count: int):
        """Update number of rows."""
        self.setRowCount(count)

    def set_data(self, data: list[tuple[str, str, str]]):
        """
        Set table data.

        Args:
            data: List of (name, value, cores) tuples
        """
        for row, item in enumerate(data):
            if row >= self.rowCount():
                break

            name_item = QTableWidgetItem(item[0])
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.setItem(row, 0, name_item)

            value_item = QTableWidgetItem(item[1])
            value_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.setItem(row, 1, value_item)

            if self.show_cores and len(item) > 2:
                cores_item = QTableWidgetItem(item[2])
                cores_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.setItem(row, 2, cores_item)

        # Clear remaining rows
        for row in range(len(data), self.rowCount()):
            self.setItem(row, 0, QTableWidgetItem(""))
            self.setItem(row, 1, QTableWidgetItem(""))
            if self.show_cores:
                self.setItem(row, 2, QTableWidgetItem(""))


class HistoryTable(ProcessTable):
    """Table for historical high-usage records with timestamps."""

    def __init__(self, rows: int, show_cores: bool = True, parent: Optional[QWidget] = None):
        super().__init__(
            rows,
            show_cores=show_cores,
            header_color=Colors.HISTORY_HEADER,
            body_color=Colors.HISTORY_BODY,
            parent=parent,
        )
        self._add_time_column()

    def _add_time_column(self):
        """Add timestamp column."""
        cols = self.columnCount()
        self.setColumnCount(cols + 1)

        headers = ["Process", "Peak", "Time"]
        if self.show_cores:
            headers.insert(2, "Cores")
        self.setHorizontalHeaderLabels(headers)

        # Adjust column widths
        header = self.horizontalHeader()
        time_col = cols
        header.setSectionResizeMode(time_col, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(time_col, 60)

    def set_data(self, data: list[tuple[str, str, str, str]]):
        """
        Set table data with timestamps.

        Args:
            data: List of (name, value, cores, time) tuples
        """
        for row, item in enumerate(data):
            if row >= self.rowCount():
                break

            name_item = QTableWidgetItem(item[0])
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.setItem(row, 0, name_item)

            value_item = QTableWidgetItem(item[1])
            value_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.setItem(row, 1, value_item)

            col_offset = 2
            if self.show_cores:
                cores_item = QTableWidgetItem(item[2])
                cores_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.setItem(row, 2, cores_item)
                col_offset = 3

            time_item = QTableWidgetItem(item[3] if len(item) > 3 else item[2])
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row, col_offset, time_item)

        # Clear remaining rows
        for row in range(len(data), self.rowCount()):
            for col in range(self.columnCount()):
                self.setItem(row, col, QTableWidgetItem(""))


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.settings: Optional[MonitorSettings] = None
        self.monitor: Optional[ProcessMonitor] = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update)
        self.is_paused = False

        self._setup_ui()
        self._show_settings()

    def _setup_ui(self):
        """Initialize the main UI."""
        self.setWindowTitle("Process Monitor")
        self.setMinimumWidth(Dimensions.WINDOW_WIDTH)
        self.setMinimumHeight(Dimensions.WINDOW_MIN_HEIGHT)

        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {Colors.BACKGROUND};
            }}
        """)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(
            Dimensions.MARGIN,
            Dimensions.MARGIN,
            Dimensions.MARGIN,
            Dimensions.MARGIN,
        )
        layout.setSpacing(Dimensions.SPACING)

        # Header
        self.header = HeaderWidget()
        layout.addWidget(self.header)

        # Current processes section
        current_label = QLabel("Current Processes")
        current_label.setStyleSheet(f"""
            font-family: {Fonts.FAMILY};
            font-size: {Fonts.SIZE_BODY}pt;
            font-weight: bold;
            color: {Colors.TEXT_PRIMARY};
            padding: 4px 0;
        """)
        layout.addWidget(current_label)

        self.current_table = ProcessTable(7)
        layout.addWidget(self.current_table)

        # History section
        history_label = QLabel("Historical Peak Usage")
        history_label.setStyleSheet(f"""
            font-family: {Fonts.FAMILY};
            font-size: {Fonts.SIZE_BODY}pt;
            font-weight: bold;
            color: {Colors.TEXT_PRIMARY};
            padding: 4px 0;
        """)
        layout.addWidget(history_label)

        self.history_table = HistoryTable(4)
        layout.addWidget(self.history_table)

        # Control buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.pause_button = QPushButton("Pause")
        self.pause_button.setStyleSheet(f"""
            QPushButton {{
                font-family: {Fonts.FAMILY};
                font-size: {Fonts.SIZE_BODY}pt;
                padding: 6px 16px;
                border-radius: 4px;
                background-color: #ddd;
            }}
            QPushButton:hover {{
                background-color: #ccc;
            }}
        """)
        self.pause_button.clicked.connect(self._toggle_pause)
        button_layout.addWidget(self.pause_button)

        self.settings_button = QPushButton("Settings")
        self.settings_button.setStyleSheet(f"""
            QPushButton {{
                font-family: {Fonts.FAMILY};
                font-size: {Fonts.SIZE_BODY}pt;
                padding: 6px 16px;
                border-radius: 4px;
                background-color: #ddd;
            }}
            QPushButton:hover {{
                background-color: #ccc;
            }}
        """)
        self.settings_button.clicked.connect(self._show_settings)
        button_layout.addWidget(self.settings_button)

        layout.addLayout(button_layout)

        # Menu bar
        self._create_menu()

    def _create_menu(self):
        """Create menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self._show_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("View")

        pause_action = QAction("Pause/Resume", self)
        pause_action.triggered.connect(self._toggle_pause)
        view_menu.addAction(pause_action)

    def _show_settings(self):
        """Show settings dialog."""
        self.timer.stop()

        dialog = SettingsDialog(self, self.settings)
        if dialog.exec():
            self.settings = dialog.get_settings()
            self._apply_settings()
            self._start_monitoring()

    def _apply_settings(self):
        """Apply settings to UI and monitor."""
        if not self.settings:
            return

        # Create or update monitor
        self.monitor = ProcessMonitor(
            mode=self.settings.mode,
            cpu_threads=self.settings.cpu_threads,
            ram_gb=self.settings.ram_gb,
        )
        self.monitor.set_history_settings(
            self.settings.history_rows,
            self.settings.retention_minutes,
        )

        # Update UI
        self.header.set_mode(self.settings.mode)
        self.current_table.set_row_count(self.settings.current_rows)
        self.current_table.show_cores = (self.settings.mode == MonitorMode.CPU)
        self.history_table.set_row_count(self.settings.history_rows)
        self.history_table.show_cores = (self.settings.mode == MonitorMode.CPU)

        # Resize window
        row_height = Dimensions.TABLE_ROW_HEIGHT
        header_height = Dimensions.HEADER_HEIGHT
        total_rows = self.settings.current_rows + self.settings.history_rows
        new_height = (
            header_height + 80 +  # Header widget
            (total_rows + 2) * row_height +  # Table rows + headers
            100  # Labels, buttons, margins
        )
        self.resize(Dimensions.WINDOW_WIDTH, new_height)

    def _start_monitoring(self):
        """Start the monitoring timer."""
        if self.settings:
            self.timer.start(self.settings.refresh_rate_ms)
            self.is_paused = False
            self.pause_button.setText("Pause")

    def _toggle_pause(self):
        """Toggle pause state."""
        if self.is_paused:
            self.timer.start(self.settings.refresh_rate_ms if self.settings else 2000)
            self.is_paused = False
            self.pause_button.setText("Pause")
        else:
            self.timer.stop()
            self.is_paused = True
            self.pause_button.setText("Resume")

    def _update(self):
        """Update display with current process data."""
        if not self.monitor or not self.settings:
            return

        # Get current processes
        processes = self.monitor.get_processes(self.settings.current_rows)

        # Update history
        self.monitor.update_history(processes)

        # Update header
        unit = self.settings.memory_unit
        self.header.update_stats(
            self.monitor.get_total_display(unit),
            self.monitor.get_max_display(unit),
        )

        # Update current table
        current_data = []
        for proc in processes:
            value = self.monitor.format_value(proc.value, unit)
            cores = self.monitor.format_cores(proc.cores_used) if self.settings.mode == MonitorMode.CPU else ""
            current_data.append((proc.name, value, cores))
        self.current_table.set_data(current_data)

        # Update history table
        history = self.monitor.get_history()
        history_data = []
        for record in history:
            value = self.monitor.format_value(record.value, unit)
            cores = self.monitor.format_cores(record.cores_used) if self.settings.mode == MonitorMode.CPU else ""
            history_data.append((record.name, value, cores, record.time_str))
        self.history_table.set_data(history_data)

    def keyPressEvent(self, event):
        """Handle key press events."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_Space:
            self._toggle_pause()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        """Handle window close."""
        self.timer.stop()
        super().closeEvent(event)
