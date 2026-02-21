"""
Main Window - Process Monitor Display
"""

import json
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer


def get_base_path() -> Path:
    """Get base path for resources (handles PyInstaller frozen exe)."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent


from PySide6.QtGui import QAction, QFont, QIcon, QPalette, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QSplitterHandle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .monitor import MonitorMode, MonitorData, SharedDataCollector
from .color_management import ProcessColorManager
from .settings_dialog import (
    InitialSettings,
    CPUSettings,
    MemorySettings,
    CPUSettingsDialog,
    MemorySettingsDialog,
    get_last_setup_path,
)


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


class BaseMonitorWindow(QMainWindow):
    """Base class for monitor windows (CPU and Memory)."""

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_paused = False
        self._saved_col_widths_current: list[int] | None = None
        self._saved_col_widths_history: list[int] | None = None
        self._layout_restored: bool = False

        # Set window icon (Qt level)
        base = get_base_path()
        icon_path = base / "assets" / "icon.ico"
        if not icon_path.exists():
            icon_path = base / "assets" / "icon.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self._ico_path = icon_path

        self._load_config()
        self._apply_dark_theme()
        self._setup_ui()

    def showEvent(self, event):
        """Set native Windows icon after window is shown for taskbar."""
        super().showEvent(event)
        if not getattr(self, '_native_icon_set', False):
            self._native_icon_set = True
            self._set_native_taskbar_icon()
        if not self._layout_restored:
            self._layout_restored = True
            self._restore_window_layout()

    def _set_native_taskbar_icon(self):
        """Set per-window icon via COM IPropertyStore + WM_SETICON.

        When multiple windows share a process-level AppUserModelID, Windows
        uses the group icon (from the exe) instead of per-window icons.
        Setting PKEY_AppUserModel_ID and PKEY_AppUserModel_RelaunchIconResource
        per-window via IPropertyStore tells the shell exactly which icon to use.
        """
        try:
            import ctypes
            from ctypes import (
                Structure, c_ulong, c_ushort, c_byte, c_void_p,
                c_wchar_p, POINTER, byref, HRESULT, WINFUNCTYPE,
            )

            ico_path = getattr(self, '_ico_path', None)
            if not ico_path or not ico_path.exists():
                return

            hwnd = int(self.winId())
            ico_abs = str(ico_path.resolve())

            # --- COM structures for IPropertyStore ---
            class GUID(Structure):
                _fields_ = [
                    ('Data1', c_ulong), ('Data2', c_ushort),
                    ('Data3', c_ushort), ('Data4', c_byte * 8),
                ]

            class PROPERTYKEY(Structure):
                _fields_ = [('fmtid', GUID), ('pid', c_ulong)]

            class PROPVARIANT(Structure):
                _fields_ = [
                    ('vt', c_ushort), ('r1', c_ushort),
                    ('r2', c_ushort), ('r3', c_ushort),
                    ('ptr', c_void_p), ('_pad', c_void_p),
                ]

            VT_LPWSTR = 31

            IID_IPropertyStore = GUID(
                0x886D8EEB, 0x8CF2, 0x4446,
                (c_byte * 8)(0x8D, 0x02, 0xCD, 0xBA, 0x1D, 0xBD, 0xCF, 0x99),
            )
            APPMODEL_FMTID = GUID(
                0x9F4C2855, 0x9F79, 0x4B39,
                (c_byte * 8)(0xA8, 0xD0, 0xE1, 0xD4, 0x2D, 0xE1, 0xD5, 0xF3),
            )
            PK_ID = PROPERTYKEY(APPMODEL_FMTID, 5)    # AppUserModel_ID
            PK_ICON = PROPERTYKEY(APPMODEL_FMTID, 3)  # RelaunchIconResource

            pps = c_void_p()
            hr = ctypes.windll.shell32.SHGetPropertyStoreForWindow(
                hwnd, byref(IID_IPropertyStore), byref(pps),
            )
            if hr == 0 and pps:
                try:
                    vt_ptr = ctypes.cast(pps, POINTER(c_void_p))[0]
                    vt = ctypes.cast(vt_ptr, POINTER(c_void_p * 8)).contents
                    SET_FN = WINFUNCTYPE(
                        HRESULT, c_void_p,
                        POINTER(PROPERTYKEY), POINTER(PROPVARIANT),
                    )
                    SetValue = SET_FN(vt[6])

                    def _set_prop(key, text):
                        pv = PROPVARIANT()
                        pv.vt = VT_LPWSTR
                        buf = c_wchar_p(text)
                        pv.ptr = ctypes.cast(buf, c_void_p)
                        SetValue(pps, byref(key), byref(pv))

                    _set_prop(PK_ID, "PCGadgets.PMUsage")

                    # Icon resource: exe when frozen, ico file from source
                    if getattr(sys, 'frozen', False):
                        _set_prop(PK_ICON, f"{sys.executable},0")
                    else:
                        _set_prop(PK_ICON, f"{ico_abs},0")
                finally:
                    REL_FN = WINFUNCTYPE(c_ulong, c_void_p)
                    REL_FN(vt[2])(pps)

            # --- WM_SETICON fallback ---
            if ico_abs.endswith('.ico'):
                LR_LOADFROMFILE = 0x00000010
                hbig = ctypes.windll.user32.LoadImageW(
                    None, ico_abs, 1, 32, 32, LR_LOADFROMFILE,
                )
                hsmall = ctypes.windll.user32.LoadImageW(
                    None, ico_abs, 1, 16, 16, LR_LOADFROMFILE,
                )
                if hbig:
                    ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hbig)
                if hsmall:
                    ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hsmall)
        except Exception:
            pass

    def _get_mode(self) -> MonitorMode:
        """Get the monitor mode. Must be overridden in subclasses."""
        raise NotImplementedError("Subclasses must implement _get_mode()")

    def _get_title(self) -> str:
        """Get the window title. Must be overridden in subclasses."""
        raise NotImplementedError("Subclasses must implement _get_title()")

    def _get_mode_cols(self) -> str:
        """Get mode columns ('cpu' or 'none'). Must be overridden in subclasses."""
        raise NotImplementedError("Subclasses must implement _get_mode_cols()")

    def _get_window_key(self) -> str:
        """Return JSON key for this window's layout ('cpu' or 'memory')."""
        raise NotImplementedError("Subclasses must implement _get_window_key()")

    def _show_settings(self):
        """Show settings dialog. Must be overridden in subclasses."""
        raise NotImplementedError("Subclasses must implement _show_settings()")

    def _apply_col_widths(self, table: QTableWidget, widths: list[int]):
        """Apply saved widths to interactive columns (col 2 onward)."""
        for i, w in enumerate(widths):
            col = i + 2
            if col < table.columnCount():
                table.setColumnWidth(col, w)

    def _save_window_layout(self):
        """Save window geometry, splitter sizes, and column widths to last_setup.json."""
        path = get_last_setup_path()
        try:
            data = {}
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            if "windows" not in data:
                data["windows"] = {}
            geo = self.geometry()
            data["windows"][self._get_window_key()] = {
                "x": geo.x(), "y": geo.y(),
                "width": geo.width(), "height": geo.height(),
                "splitter": self.splitter.sizes(),
                "current_cols": [
                    self.current_table.columnWidth(c)
                    for c in range(2, self.current_table.columnCount())
                ],
                "history_cols": [
                    self.history_table.columnWidth(c)
                    for c in range(2, self.history_table.columnCount())
                ],
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _restore_window_layout(self):
        """Restore window geometry, splitter sizes, and column widths from last_setup.json."""
        path = get_last_setup_path()
        if not path.exists():
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        layout = data.get("windows", {}).get(self._get_window_key())
        if not layout:
            return
        x, y, w, h = layout.get("x"), layout.get("y"), layout.get("width"), layout.get("height")
        if all(v is not None for v in [x, y, w, h]):
            self.setGeometry(x, y, w, h)
        splitter_sizes = layout.get("splitter")
        if isinstance(splitter_sizes, list) and len(splitter_sizes) == 2:
            self.splitter.setSizes(splitter_sizes)
        current_cols = layout.get("current_cols")
        if isinstance(current_cols, list):
            self._saved_col_widths_current = current_cols
            self._apply_col_widths(self.current_table, current_cols)
        history_cols = layout.get("history_cols")
        if isinstance(history_cols, list):
            self._saved_col_widths_history = history_cols
            self._apply_col_widths(self.history_table, history_cols)

    def _load_config(self):
        """Load temperature color config from JSON."""
        config_path = get_base_path() / "config" / "config.json"
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
        self.setWindowTitle(self._get_title())
        self.setMinimumWidth(340)
        self.setMinimumHeight(400)

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

        # Title row: title on left, total value on right
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel(self._get_title())
        self.title_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.title_label.setStyleSheet(f"color: {self.TEXT}; background: transparent;")
        title_row.addWidget(self.title_label)

        title_row.addStretch()

        self.total_label = QLabel("")
        self.total_label.setFont(QFont("Segoe UI", 12))
        self.total_label.setStyleSheet(f"color: {self.TEXT}; background: transparent;")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(self.total_label)

        header_layout.addLayout(title_row)

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

        self.sensor_name_labels: list[QLabel] = []
        self.sensor_value_labels: list[QLabel] = []
        for _ in range(3):
            col = QWidget()
            col.setStyleSheet("background: transparent;")
            col_layout = QVBoxLayout(col)
            col_layout.setContentsMargins(0, 0, 0, 0)
            col_layout.setSpacing(1)

            name_lbl = QLabel("")
            name_lbl.setFont(QFont("Segoe UI", 9))
            name_lbl.setStyleSheet(f"color: {self.TEXT_MUTED}; background: transparent;")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col_layout.addWidget(name_lbl)

            value_lbl = QLabel("")
            value_lbl.setFont(QFont("Segoe UI", 11))
            value_lbl.setStyleSheet(f"color: {self.TEXT}; background: transparent;")
            value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col_layout.addWidget(value_lbl)

            sensor_layout.addWidget(col)
            self.sensor_name_labels.append(name_lbl)
            self.sensor_value_labels.append(value_lbl)

        header_layout.addWidget(self.sensor_widget)

        layout.addWidget(self.header_widget)

        # Splitter for resizable sections (double-click resets to 50-50)
        self.splitter = DoubleClickSplitter(Qt.Orientation.Vertical)
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

        self.current_table = self._create_table(7, mode_cols=self._get_mode_cols(), bg_color=self.CURRENT_BG)
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

        self.history_table = self._create_table(4, mode_cols=self._get_mode_cols(), has_time=True, bg_color=self.HISTORY_BG)
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

    def _create_table(self, rows: int, mode_cols: str = "none", has_time: bool = False, bg_color: str = None) -> QTableWidget:
        """Create a styled table.

        Args:
            rows: Number of rows
            mode_cols: "cpu" for Parallel+Threads, "mem" for Commit, "none" for no extra cols
            has_time: Add Time column
            bg_color: Background color
        """
        if bg_color is None:
            bg_color = self.CARD_COLOR

        cols = 3  # #, Process, Usage
        headers = ["#", "Process", "Usage"]

        if mode_cols == "cpu":
            cols += 2
            headers += ["Parallel", "Threads"]
        elif mode_cols == "mem":
            cols += 1
            headers.append("Commit")
        if has_time:
            cols += 1
            headers.append("Time")

        table = QTableWidget(rows, cols)
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
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
        if has_time:
            header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)

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

        return table

    def _rebuild_tables(self):
        """Rebuild tables based on current settings."""
        raise NotImplementedError("Subclasses must implement _rebuild_tables()")

    def _toggle_pause(self):
        """Toggle pause. Must be implemented by subclasses for proper pause/resume."""
        self.is_paused = not self.is_paused
        self.pause_btn.setText("Resume" if self.is_paused else "Pause")

    def _on_data_ready(self, data: MonitorData):
        """Handle data from collector (runs on main thread via signal)."""
        raise NotImplementedError("Subclasses must implement _on_data_ready()")

    def keyPressEvent(self, event):
        """Handle keys."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_Space:
            self._toggle_pause()
        else:
            super().keyPressEvent(event)


class CPUWindow(BaseMonitorWindow):
    """CPU Monitor window."""

    def __init__(self, initial_settings: InitialSettings, collector: SharedDataCollector, parent=None):
        self._initial_settings = initial_settings
        self._collector = collector
        self._cpu_settings = CPUSettings(
            current_rows=initial_settings.current_rows,
            history_rows=initial_settings.history_rows,
            refresh_rate_ms=initial_settings.refresh_rate_ms,
            retention_minutes=initial_settings.retention_minutes,
        )
        super().__init__(parent)

        # Connect to collector signal
        self._collector.cpu_data_ready.connect(self._on_data_ready)

        # Configure and start collector
        self._apply_settings()
        if not self._collector.isRunning():
            self._collector.start()

    def _get_mode(self) -> MonitorMode:
        return MonitorMode.CPU

    def _get_title(self) -> str:
        return "CPU Monitor"

    def _get_mode_cols(self) -> str:
        return "cpu"

    def _get_window_key(self) -> str:
        return "cpu"

    def _show_settings(self):
        """Show CPU settings dialog."""
        dialog = CPUSettingsDialog(self, self._cpu_settings)
        if dialog.exec():
            self._cpu_settings = dialog.get_settings()
            self._apply_settings()

    def _apply_settings(self):
        """Apply current settings to collector."""
        self._collector.configure_cpu(
            cpu_threads=self._initial_settings.cpu_threads,
            ram_gb=self._initial_settings.ram_gb,
            current_rows=self._cpu_settings.current_rows,
            history_rows=self._cpu_settings.history_rows,
            retention_minutes=self._cpu_settings.retention_minutes,
            refresh_rate_ms=self._cpu_settings.refresh_rate_ms,
        )
        self._rebuild_tables()

        # Resize window based on row count
        row_height = 32
        total_rows = self._cpu_settings.current_rows + self._cpu_settings.history_rows
        new_height = 200 + (total_rows + 2) * row_height + 100
        self.resize(400, new_height)

    def _rebuild_tables(self):
        """Rebuild tables with current settings."""
        # Get section layouts
        current_layout = self.current_section.layout()
        history_layout = self.history_section.layout()

        # Remove old tables
        current_layout.removeWidget(self.current_table)
        history_layout.removeWidget(self.history_table)
        self.current_table.deleteLater()
        self.history_table.deleteLater()

        # Create new tables
        self.current_table = self._create_table(
            self._cpu_settings.current_rows,
            mode_cols="cpu",
            has_time=False,
            bg_color=self.CURRENT_BG
        )
        self.history_table = self._create_table(
            self._cpu_settings.history_rows,
            mode_cols="cpu",
            has_time=True,
            bg_color=self.HISTORY_BG
        )

        # Add to section layouts (after title labels)
        current_layout.addWidget(self.current_table)
        history_layout.addWidget(self.history_table)

        # Re-apply saved column widths after rebuild
        if self._saved_col_widths_current:
            self._apply_col_widths(self.current_table, self._saved_col_widths_current)
        if self._saved_col_widths_history:
            self._apply_col_widths(self.history_table, self._saved_col_widths_history)

    def _on_data_ready(self, data: MonitorData):
        """Handle data from collector."""
        if self.is_paused:
            return

        monitor = self._collector.cpu_monitor

        # Update header
        self.total_label.setText(data.total_display)
        self.peak_label.setText(data.max_display)

        # Get HWiNFO sensor data
        hwinfo = data.hwinfo

        # CPU mode: Temperature, Power, Current
        sensor_names = ["Temperature", "Power", "Current"]
        sensor_data = [
            (f"{hwinfo.cpu_tctl:.1f}°C", hwinfo.cpu_tctl) if hwinfo.cpu_tctl else ("—", None),
            (f"{hwinfo.cpu_power:.1f} W", None) if hwinfo.cpu_power else ("—", None),
            (f"{hwinfo.cpu_edc:.1f} A", None) if hwinfo.cpu_edc else ("—", None),
        ]
        for i, (name, (value_text, temp_val)) in enumerate(zip(sensor_names, sensor_data)):
            self.sensor_name_labels[i].setText(name)
            self.sensor_value_labels[i].setText(value_text)
            self.sensor_value_labels[i].setStyleSheet(
                f"color: {self._get_temp_color(temp_val)}; background: transparent;"
            )

        # Update current table
        color_mgr = ProcessColorManager()
        for row, proc in enumerate(data.processes):
            if row >= self.current_table.rowCount():
                break

            self.current_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))

            name_item = QTableWidgetItem(proc.name)
            proc_color = color_mgr.get_process_color(proc.name)
            if proc_color:
                name_item.setForeground(proc_color)
            self.current_table.setItem(row, 1, name_item)

            value_str = monitor.format_value(proc.value, "MB") if monitor else f"{proc.value:.0f}"
            value_item = QTableWidgetItem(value_str)
            if monitor:
                pct = proc.value / (monitor.cpu_threads * 100) * 100
                value_item.setForeground(color_mgr.get_value_color(pct, "cpu"))
            self.current_table.setItem(row, 2, value_item)

            self.current_table.setItem(row, 3, QTableWidgetItem(str(proc.count)))
            self.current_table.setItem(row, 4, QTableWidgetItem(str(proc.threads) if proc.threads > 0 else ""))

        # Clear empty rows
        for row in range(len(data.processes), self.current_table.rowCount()):
            for col in range(self.current_table.columnCount()):
                self.current_table.setItem(row, col, QTableWidgetItem(""))

        # Update history table
        for row, record in enumerate(data.history):
            if row >= self.history_table.rowCount():
                break

            self.history_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))

            name_item = QTableWidgetItem(record.name)
            proc_color = color_mgr.get_process_color(record.name)
            if proc_color:
                name_item.setForeground(proc_color)
            self.history_table.setItem(row, 1, name_item)

            value_str = monitor.format_value(record.value, "MB") if monitor else f"{record.value:.0f}"
            value_item = QTableWidgetItem(value_str)
            if monitor:
                pct = record.value / (monitor.cpu_threads * 100) * 100
                value_item.setForeground(color_mgr.get_value_color(pct, "cpu"))
            self.history_table.setItem(row, 2, value_item)

            self.history_table.setItem(row, 3, QTableWidgetItem(str(record.count)))
            self.history_table.setItem(row, 4, QTableWidgetItem(str(record.threads) if record.threads > 0 else ""))
            self.history_table.setItem(row, 5, QTableWidgetItem(record.time_str))

        # Clear empty rows
        for row in range(len(data.history), self.history_table.rowCount()):
            for col in range(self.history_table.columnCount()):
                self.history_table.setItem(row, col, QTableWidgetItem(""))

    def closeEvent(self, event):
        """Handle close - disable CPU monitoring."""
        self._save_window_layout()
        self._collector.cpu_data_ready.disconnect(self._on_data_ready)
        self._collector.disable_cpu()
        super().closeEvent(event)


class MemoryWindow(BaseMonitorWindow):
    """Memory Monitor window."""

    def __init__(self, initial_settings: InitialSettings, collector: SharedDataCollector, parent=None):
        self._initial_settings = initial_settings
        self._collector = collector
        self._memory_settings = MemorySettings(
            current_rows=initial_settings.current_rows,
            history_rows=initial_settings.history_rows,
            refresh_rate_ms=initial_settings.refresh_rate_ms,
            retention_minutes=initial_settings.retention_minutes,
            memory_unit=initial_settings.memory_unit,
        )
        super().__init__(parent)

        # Connect to collector signal
        self._collector.memory_data_ready.connect(self._on_data_ready)

        # Configure and start collector
        self._apply_settings()
        if not self._collector.isRunning():
            self._collector.start()

    def _get_mode(self) -> MonitorMode:
        return MonitorMode.MEMORY

    def _get_title(self) -> str:
        return "Memory Monitor"

    def _get_mode_cols(self) -> str:
        return "mem"

    def _get_window_key(self) -> str:
        return "memory"

    def _show_settings(self):
        """Show Memory settings dialog."""
        dialog = MemorySettingsDialog(self, self._memory_settings)
        if dialog.exec():
            self._memory_settings = dialog.get_settings()
            self._apply_settings()

    def _apply_settings(self):
        """Apply current settings to collector."""
        self._collector.configure_memory(
            cpu_threads=self._initial_settings.cpu_threads,
            ram_gb=self._initial_settings.ram_gb,
            current_rows=self._memory_settings.current_rows,
            history_rows=self._memory_settings.history_rows,
            retention_minutes=self._memory_settings.retention_minutes,
            refresh_rate_ms=self._memory_settings.refresh_rate_ms,
            memory_unit=self._memory_settings.memory_unit,
        )
        self._rebuild_tables()

        # Resize window based on row count
        row_height = 32
        total_rows = self._memory_settings.current_rows + self._memory_settings.history_rows
        new_height = 200 + (total_rows + 2) * row_height + 100
        self.resize(400, new_height)

    def _rebuild_tables(self):
        """Rebuild tables with current settings."""
        # Get section layouts
        current_layout = self.current_section.layout()
        history_layout = self.history_section.layout()

        # Remove old tables
        current_layout.removeWidget(self.current_table)
        history_layout.removeWidget(self.history_table)
        self.current_table.deleteLater()
        self.history_table.deleteLater()

        # Create new tables
        self.current_table = self._create_table(
            self._memory_settings.current_rows,
            mode_cols="mem",
            has_time=False,
            bg_color=self.CURRENT_BG
        )
        self.history_table = self._create_table(
            self._memory_settings.history_rows,
            mode_cols="mem",
            has_time=True,
            bg_color=self.HISTORY_BG
        )

        # Add to section layouts (after title labels)
        current_layout.addWidget(self.current_table)
        history_layout.addWidget(self.history_table)

        # Re-apply saved column widths after rebuild
        if self._saved_col_widths_current:
            self._apply_col_widths(self.current_table, self._saved_col_widths_current)
        if self._saved_col_widths_history:
            self._apply_col_widths(self.history_table, self._saved_col_widths_history)

    def _on_data_ready(self, data: MonitorData):
        """Handle data from collector."""
        if self.is_paused:
            return

        monitor = self._collector.memory_monitor
        unit = self._memory_settings.memory_unit

        # Update header
        self.total_label.setText(data.total_display)
        self.peak_label.setText(data.max_display)

        # Get HWiNFO sensor data
        hwinfo = data.hwinfo

        # Memory mode: Committed, Read, Write
        committed_str = (
            monitor.format_value(hwinfo.virt_committed, unit)
            if (monitor and hwinfo.virt_committed)
            else "—"
        )
        sensor_names = ["Committed", "Read", "Write"]
        sensor_values = [
            committed_str,
            f"{hwinfo.dram_read:,.0f} MB/s" if hwinfo.dram_read else "—",
            f"{hwinfo.dram_write:,.0f} MB/s" if hwinfo.dram_write else "—",
        ]
        for i, (name, value_text) in enumerate(zip(sensor_names, sensor_values)):
            self.sensor_name_labels[i].setText(name)
            self.sensor_value_labels[i].setText(value_text)
            self.sensor_value_labels[i].setStyleSheet(f"color: {self.TEXT}; background: transparent;")

        # Update current table
        color_mgr = ProcessColorManager()
        for row, proc in enumerate(data.processes):
            if row >= self.current_table.rowCount():
                break

            self.current_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))

            name_item = QTableWidgetItem(proc.name)
            proc_color = color_mgr.get_process_color(proc.name)
            if proc_color:
                name_item.setForeground(proc_color)
            self.current_table.setItem(row, 1, name_item)

            value_str = monitor.format_value(proc.value, unit) if monitor else f"{proc.value:.0f}"
            value_item = QTableWidgetItem(value_str)
            if monitor:
                pct = proc.value / monitor.ram_bytes * 100
                value_item.setForeground(color_mgr.get_value_color(pct, "memory"))
            self.current_table.setItem(row, 2, value_item)

            commit_str = monitor.format_value(proc.vms, unit) if (monitor and proc.vms > 0) else ""
            self.current_table.setItem(row, 3, QTableWidgetItem(commit_str))

        # Clear empty rows
        for row in range(len(data.processes), self.current_table.rowCount()):
            for col in range(self.current_table.columnCount()):
                self.current_table.setItem(row, col, QTableWidgetItem(""))

        # Update history table
        for row, record in enumerate(data.history):
            if row >= self.history_table.rowCount():
                break

            self.history_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))

            name_item = QTableWidgetItem(record.name)
            proc_color = color_mgr.get_process_color(record.name)
            if proc_color:
                name_item.setForeground(proc_color)
            self.history_table.setItem(row, 1, name_item)

            value_str = monitor.format_value(record.value, unit) if monitor else f"{record.value:.0f}"
            value_item = QTableWidgetItem(value_str)
            if monitor:
                pct = record.value / monitor.ram_bytes * 100
                value_item.setForeground(color_mgr.get_value_color(pct, "memory"))
            self.history_table.setItem(row, 2, value_item)

            commit_str = monitor.format_value(record.vms, unit) if (monitor and record.vms > 0) else ""
            self.history_table.setItem(row, 3, QTableWidgetItem(commit_str))
            self.history_table.setItem(row, 4, QTableWidgetItem(record.time_str))

        # Clear empty rows
        for row in range(len(data.history), self.history_table.rowCount()):
            for col in range(self.history_table.columnCount()):
                self.history_table.setItem(row, col, QTableWidgetItem(""))

    def closeEvent(self, event):
        """Handle close - disable Memory monitoring."""
        self._save_window_layout()
        self._collector.memory_data_ready.disconnect(self._on_data_ready)
        self._collector.disable_memory()
        super().closeEvent(event)
