"""
Main Window - Process Monitor Display
"""

import json
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QEvent, QRect
from PySide6.QtGui import QAction, QFont, QIcon, QPalette, QColor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QSplitterHandle,
    QStackedWidget,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .monitor import MonitorMode, MonitorData, NetworkMonitorData, SharedDataCollector
from .color_management import ProcessColorManager
from .persistence import get_base_path, load_last_setup, save_last_setup
from .settings_dialog import (
    InitialSettings,
    CPUSettings,
    MemorySettings,
    NetworkSettings,
    CPUSettingsDialog,
    MemorySettingsDialog,
    NetworkSettingsDialog,
)
from .process_actions import (
    find_processes,
    kill_processes,
    get_exe_path,
    open_file_location,
    get_current_priority,
    set_priority,
)
from .process_dialog import KillConfirmDialog, PriorityDialog
from .styles import CONTEXT_MENU_STYLE, Colors, Defaults, Fonts, FontScale, format_speed, format_bytes_total


class TotalRowDelegate(QStyledItemDelegate):
    """Draws the Σ total row with a distinct header background color.

    QSS-styled tables ignore QTableWidgetItem.setBackground(); this delegate
    bypasses the style engine and paints the background directly.
    """

    ROLE = Qt.ItemDataRole.UserRole + 100

    def __init__(self, bg_color: str, text_color: str, parent=None):
        super().__init__(parent)
        self._bg = QColor(bg_color)
        self._text = QColor(text_color)

    def paint(self, painter, option, index):
        if not index.data(self.ROLE):
            super().paint(painter, option, index)
            return

        painter.save()
        painter.fillRect(option.rect, self._bg)

        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        fg_brush = index.data(Qt.ItemDataRole.ForegroundRole)
        if fg_brush is not None:
            painter.setPen(fg_brush.color() if hasattr(fg_brush, 'color') else QColor(fg_brush))
        else:
            painter.setPen(self._text)

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

    # Default temperature thresholds
    DEFAULT_TEMP_CONFIG = {
        "normal": Colors.TEXT,
        "warning": Colors.TEMP_WARNING,
        "critical": Colors.TEMP_CRITICAL,
        "warning_threshold": 60,
        "critical_threshold": 75,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        # Gadget mode: Tool windows have no taskbar button and no Alt-Tab
        # entry — the tray icon (app/tray.py) is the app's single identity
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.is_paused = False
        self._saved_col_widths_current: list[int] | None = None
        self._saved_col_widths_history: list[int] | None = None
        self._saved_col_widths_rolling: list[int] | None = None
        self._layout_restored: bool = False
        self._peer_window: 'BaseMonitorWindow | None' = None
        self._bottom_page: int = 0  # 0 = Peak Usage, 1 = Rolling Average

        # Font scale base size (set by subclass via _initial_settings before super().__init__)
        self._font_base: int = getattr(self, '_initial_settings', None)
        self._font_base = self._font_base.font_size if self._font_base else Defaults.FONT_SIZE

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

        app = QApplication.instance()
        if app:
            app.applicationStateChanged.connect(self._on_app_state_changed)

    def showEvent(self, event):
        """Set native Windows icon after window is shown for taskbar."""
        super().showEvent(event)
        if not getattr(self, '_native_icon_set', False):
            self._native_icon_set = True
            self._set_native_taskbar_icon()
        if not self._layout_restored:
            self._layout_restored = True
            self._restore_window_layout()
            self._ensure_on_screen()

    def _ensure_on_screen(self):
        """Move window onto visible screen area if it is fully off-screen."""
        rect = self.frameGeometry()
        on_screen = any(
            screen.availableGeometry().intersects(rect)
            for screen in QApplication.screens()
        )
        if not on_screen:
            primary = QApplication.primaryScreen().availableGeometry()
            self.move(
                primary.x() + (primary.width() - rect.width()) // 2,
                primary.y() + (primary.height() - rect.height()) // 2,
            )

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

    def _has_total_row(self) -> bool:
        """Whether the current-processes table has a Σ total row.

        True for CPU/Memory; NetworkWindow overrides to False.
        """
        return True

    def _configure_collector(self):
        """Configure the shared collector with this mode's current settings. Must be overridden in subclasses."""
        raise NotImplementedError("Subclasses must implement _configure_collector()")

    def _disable_collector(self):
        """Disable this mode's collection on the shared collector. Must be overridden in subclasses."""
        raise NotImplementedError("Subclasses must implement _disable_collector()")

    def _create_settings_dialog(self):
        """Create and return this mode's settings dialog. Must be overridden in subclasses."""
        raise NotImplementedError("Subclasses must implement _create_settings_dialog()")

    def _store_settings(self, new_settings):
        """Store new settings. NetworkWindow overrides to also recompute max-speed thresholds."""
        self._settings = new_settings

    def _show_settings(self):
        """Show settings dialog and apply any changes.

        Compares old vs new settings, applies them to the collector (rebuilding
        tables if row counts changed), re-applies fonts if the font size changed,
        and syncs a visible peer window's refresh rate if it changed (NetworkWindow
        has no peer, so the guard below is always a no-op for it).
        """
        dialog = self._create_settings_dialog()
        if dialog.exec():
            new_settings = dialog.get_settings()
            if new_settings == self._settings:
                return
            prev = self._settings
            self._store_settings(new_settings)
            self._apply_settings(prev)
            if new_settings.font_size != prev.font_size:
                self._font_base = new_settings.font_size
                self._apply_fonts()
            # Sync only a visible peer — a hidden window's monitor is disabled
            # and re-configuring it would re-enable collection for nothing
            if (
                self._peer_window is not None
                and self._peer_window.isVisible()
                and new_settings.refresh_rate_ms != prev.refresh_rate_ms
            ):
                self._peer_window._sync_refresh_rate(new_settings.refresh_rate_ms)

    def _sync_refresh_rate(self, refresh_rate_ms: int):
        """Sync refresh rate from peer window without rebuilding tables."""
        if self._settings.refresh_rate_ms == refresh_rate_ms:
            return
        self._settings.refresh_rate_ms = refresh_rate_ms
        self._configure_collector()

    def _apply_settings(self, prev_settings=None):
        """Apply current settings to collector. Rebuilds tables only if row counts changed."""
        self._configure_collector()
        rows_changed = (
            prev_settings is None
            or prev_settings.current_rows != self._settings.current_rows
            or prev_settings.history_rows != self._settings.history_rows
        )
        if rows_changed:
            self._rebuild_tables()

    def _apply_col_widths(self, table: QTableWidget, widths: list[int]):
        """Apply saved widths to interactive columns (col 2 onward)."""
        for i, w in enumerate(widths):
            col = i + 2
            if col < table.columnCount():
                table.setColumnWidth(col, w)

    def _save_window_layout(self):
        """Save window geometry, splitter sizes, and column widths to last_setup.json."""
        data = load_last_setup()
        if "windows" not in data:
            data["windows"] = {}
        geo = self.geometry()
        data["windows"][self._get_window_key()] = {
            "x": geo.x(), "y": geo.y(),
            "width": geo.width(), "height": geo.height(),
            "font_size": self._font_base,
            "splitter": self.splitter.sizes(),
            "bottom_page": self._bottom_page,
            "current_cols": [
                self.current_table.columnWidth(c)
                for c in range(2, self.current_table.columnCount())
            ],
            "history_cols": [
                self.history_table.columnWidth(c)
                for c in range(2, self.history_table.columnCount())
            ],
            "rolling_cols": [
                self.rolling_table.columnWidth(c)
                for c in range(2, self.rolling_table.columnCount())
            ],
        }
        save_last_setup(data)

    def _restore_window_layout(self):
        """Restore window geometry, splitter sizes, and column widths from last_setup.json."""
        data = load_last_setup()
        layout = data.get("windows", {}).get(self._get_window_key())
        if not layout:
            return
        x, y, w, h = layout.get("x"), layout.get("y"), layout.get("width"), layout.get("height")
        if all(v is not None for v in [x, y, w, h]):
            saved_rect = QRect(x, y, w, h)
            on_screen = any(
                screen.availableGeometry().intersects(saved_rect)
                for screen in QApplication.screens()
            )
            if on_screen:
                self.setGeometry(x, y, w, h)
            else:
                primary = QApplication.primaryScreen().availableGeometry()
                new_x = primary.x() + (primary.width() - w) // 2
                new_y = primary.y() + (primary.height() - h) // 2
                self.setGeometry(new_x, new_y, w, h)
        saved_font = layout.get("font_size")
        if saved_font is not None and saved_font != self._font_base:
            self._font_base = int(saved_font)
            self._apply_fonts()
        splitter_sizes = layout.get("splitter")
        if isinstance(splitter_sizes, list) and len(splitter_sizes) == 2:
            self.splitter.setSizes(splitter_sizes)
        bottom_page = layout.get("bottom_page", 0)
        if bottom_page in (0, 1):
            self._bottom_page = bottom_page
            self.bottom_stack.setCurrentIndex(bottom_page)
            if bottom_page == 0:
                self.bottom_toggle_btn.setText("◀ Peak Usage ▶")
                self.peak_label.setVisible(True)
            else:
                self.bottom_toggle_btn.setText("◀ Rolling Average ▶")
        current_cols = layout.get("current_cols")
        if isinstance(current_cols, list):
            self._saved_col_widths_current = current_cols
            self._apply_col_widths(self.current_table, current_cols)
        history_cols = layout.get("history_cols")
        if isinstance(history_cols, list):
            self._saved_col_widths_history = history_cols
            self._apply_col_widths(self.history_table, history_cols)
        rolling_cols = layout.get("rolling_cols")
        if isinstance(rolling_cols, list):
            self._saved_col_widths_rolling = rolling_cols
            self._apply_col_widths(self.rolling_table, rolling_cols)

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
            return Colors.TEXT

        if temp >= self.temp_config["critical_threshold"]:
            return self.temp_config["critical"]
        elif temp >= self.temp_config["warning_threshold"]:
            return self.temp_config["warning"]
        else:
            return self.temp_config["normal"]

    def _apply_dark_theme(self):
        """Apply dark theme to window."""
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(Colors.BACKGROUND))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(Colors.TEXT))
        palette.setColor(QPalette.ColorRole.Base, QColor(Colors.CARD))
        palette.setColor(QPalette.ColorRole.Text, QColor(Colors.TEXT))
        palette.setColor(QPalette.ColorRole.Button, QColor(Colors.HEADER))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(Colors.TEXT))
        self.setPalette(palette)

    def _font(self, offset: int, bold: bool = False) -> QFont:
        """Create a proportionally scaled font.

        Uses FontScale offsets: TITLE(+5), SECTION(+2), SUBTITLE(+1),
        BODY(0), SMALL(-1), TINY(-2).
        """
        weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
        return QFont(Fonts.FAMILY, FontScale.size(self._font_base, offset), weight)

    def _apply_fonts(self):
        """Re-apply all fonts after font_size change. Updates labels, buttons, and tables."""
        self.title_label.setFont(self._font(FontScale.TITLE, bold=True))
        self.total_label.setFont(self._font(FontScale.SUBTITLE))
        for lbl in self.sensor_name_labels:
            lbl.setFont(self._font(FontScale.TINY))
        for lbl in self.sensor_value_labels:
            lbl.setFont(self._font(FontScale.BODY))
        self.current_title.setFont(self._font(FontScale.SECTION, bold=True))
        self.bottom_toggle_btn.setFont(self._font(FontScale.SECTION, bold=True))
        self.peak_label.setFont(self._font(FontScale.SMALL))
        self.menuBar().setFont(self._font(FontScale.BODY))
        # Update table row heights and header font
        row_h = FontScale.row_height(self._font_base)
        header_css = f"""
            QHeaderView::section {{
                background-color: {Colors.HEADER};
                color: {Colors.TEXT};
                font-family: {Fonts.FAMILY};
                font-size: {FontScale.size(self._font_base, FontScale.SMALL)}pt;
                font-weight: bold;
                padding: 8px;
                border: none;
            }}
        """
        content_font = self._font(FontScale.SMALL)
        for table in (self.current_table, self.history_table, self.rolling_table):
            table.setFont(content_font)
            table.verticalHeader().setDefaultSectionSize(row_h)
            table.horizontalHeader().setStyleSheet(header_css)

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
            background-color: {Colors.CARD};
            border-radius: 8px;
        """)
        header_layout = QVBoxLayout(self.header_widget)
        header_layout.setContentsMargins(16, 12, 16, 12)

        # Title row: title on left, total value on right
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel(self._get_title())
        self.title_label.setFont(self._font(FontScale.TITLE, bold=True))
        self.title_label.setStyleSheet(f"color: {Colors.TEXT}; background: transparent;")
        title_row.addWidget(self.title_label)

        title_row.addStretch()

        self.total_label = QLabel("")
        self.total_label.setFont(self._font(FontScale.SUBTITLE))
        self.total_label.setStyleSheet(f"color: {Colors.TEXT}; background: transparent;")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(self.total_label)

        header_layout.addLayout(title_row)


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
            name_lbl.setFont(self._font(FontScale.TINY))
            name_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; background: transparent;")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col_layout.addWidget(name_lbl)

            value_lbl = QLabel("")
            value_lbl.setFont(self._font(FontScale.BODY))
            value_lbl.setStyleSheet(f"color: {Colors.TEXT}; background: transparent;")
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
                background-color: {Colors.HEADER};
                height: 4px;
            }}
            QSplitter::handle:hover {{
                background-color: {Colors.ACCENT};
            }}
        """)

        # Current Processes section
        self.current_section = QWidget()
        current_layout = QVBoxLayout(self.current_section)
        current_layout.setContentsMargins(0, 0, 0, 4)
        current_layout.setSpacing(4)

        self.current_title = QLabel("Current Processes")
        self.current_title.setFont(self._font(FontScale.SECTION, bold=True))
        self.current_title.setStyleSheet(f"color: {Colors.TEXT};")
        current_layout.addWidget(self.current_title)

        self.current_table = self._create_table(7, mode_cols=self._get_mode_cols(), bg_color=Colors.CURRENT_BG)
        current_layout.addWidget(self.current_table)

        self.splitter.addWidget(self.current_section)

        # History / Rolling Average section (toggle between two views)
        self.history_section = QWidget()
        history_layout = QVBoxLayout(self.history_section)
        history_layout.setContentsMargins(0, 4, 0, 0)
        history_layout.setSpacing(4)

        bottom_header_row = QHBoxLayout()
        bottom_header_row.setContentsMargins(0, 0, 0, 0)

        self.bottom_toggle_btn = QPushButton("◀ Peak Usage ▶")
        self.bottom_toggle_btn.setFont(self._font(FontScale.SECTION, bold=True))
        self.bottom_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT};
                border: none;
                padding: 0;
                text-align: left;
            }}
            QPushButton:hover {{
                color: {Colors.ACCENT};
            }}
        """)
        self.bottom_toggle_btn.clicked.connect(self._toggle_bottom_table)
        bottom_header_row.addWidget(self.bottom_toggle_btn)
        bottom_header_row.addStretch()

        self.peak_label = QLabel("Peak: --")
        self.peak_label.setFont(self._font(FontScale.SMALL))
        self.peak_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; background: transparent;")
        bottom_header_row.addWidget(self.peak_label)
        history_layout.addLayout(bottom_header_row)

        self.bottom_stack = QStackedWidget()
        self.history_table = self._create_table(4, mode_cols=self._get_mode_cols(), has_time=True, bg_color=Colors.HISTORY_BG)
        self.rolling_table = self._create_table(0, mode_cols=self._get_mode_cols(), has_time=False, bg_color=Colors.ROLLING_BG, has_uptime=True)
        self.bottom_stack.addWidget(self.history_table)   # index 0 = Peak Usage
        self.bottom_stack.addWidget(self.rolling_table)   # index 1 = Rolling Average
        history_layout.addWidget(self.bottom_stack)

        self.splitter.addWidget(self.history_section)

        # Set initial sizes (current gets more space)
        self.splitter.setSizes([300, 150])

        layout.addWidget(self.splitter)

        # Menu bar — contains File, View, and a clickable Pause action
        menubar = self.menuBar()
        menubar.setStyleSheet(f"""
            QMenuBar {{
                background-color: {Colors.BACKGROUND};
                color: {Colors.TEXT};
            }}
            QMenuBar::item:selected {{
                background-color: {Colors.HEADER};
            }}
        """)

        file_menu = menubar.addMenu("File")
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self._show_settings)
        file_menu.addAction(settings_action)
        # Exit quits the whole app — plain close() only hides to the tray
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(QApplication.instance().quit)
        file_menu.addAction(exit_action)

        view_menu = menubar.addMenu("View")
        pause_action = QAction("Pause/Resume", self)
        pause_action.triggered.connect(self._toggle_pause)
        view_menu.addAction(pause_action)

        # Pause as a direct menubar action (clickable text in the bar itself)
        self._pause_action = QAction("Pause", self)
        self._pause_action.triggered.connect(self._toggle_pause)
        menubar.addAction(self._pause_action)

    def _toggle_bottom_table(self):
        """Switch between Peak Usage (index 0) and Rolling Average (index 1)."""
        self._bottom_page = 1 - self._bottom_page
        self.bottom_stack.setCurrentIndex(self._bottom_page)
        if self._bottom_page == 0:
            self.bottom_toggle_btn.setText("◀ Peak Usage ▶")
            self.peak_label.setVisible(True)
        else:
            self.bottom_toggle_btn.setText("◀ Rolling Average ▶")

    def _make_total_item(self, text: str) -> QTableWidgetItem:
        """Create a styled QTableWidgetItem for the Σ total row."""
        item = QTableWidgetItem(text)
        item.setData(TotalRowDelegate.ROLE, True)
        item.setForeground(QColor(Colors.TEXT))
        item.setFont(self._font(FontScale.SMALL, bold=True))
        return item

    def _fill_process_rows(self, table: QTableWidget, data, fill_cols_fn, *, limit: int | None = None):
        """Fill table rows with process data. Handles row number, name+color+tooltip, and clearing.

        Args:
            table: Target QTableWidget.
            data: List of ProcessInfo or HistoryRecord items.
            fill_cols_fn: Callable(table, row, item, color_mgr) that fills mode-specific columns.
            limit: Max rows to fill (defaults to table.rowCount()).
        """
        color_mgr = ProcessColorManager()
        max_rows = limit if limit is not None else table.rowCount()

        for row, item in enumerate(data):
            if row >= max_rows:
                break
            table.setItem(row, 0, QTableWidgetItem(str(row + 1)))

            name_item = QTableWidgetItem(item.name)
            proc_color = color_mgr.get_process_color(item.name)
            if proc_color:
                name_item.setForeground(proc_color)
            company = color_mgr.get_company_name(item.name)
            if company:
                name_item.setToolTip(company)
            table.setItem(row, 1, name_item)

            fill_cols_fn(table, row, item, color_mgr)

        for row in range(min(len(data), max_rows), max_rows):
            for col in range(table.columnCount()):
                table.setItem(row, col, QTableWidgetItem(""))

        return color_mgr

    def _create_table(self, rows: int, mode_cols: str = "none", has_time: bool = False, bg_color: str = None, has_total_row: bool = False, has_uptime: bool = False) -> QTableWidget:
        """Create a styled table.

        Args:
            rows: Number of rows
            mode_cols: "cpu" for Parallel+Threads, "mem" for Commit, "none" for no extra cols
            has_time: Add Time column
            bg_color: Background color
            has_uptime: Add Uptime column (rolling average table only)
        """
        if bg_color is None:
            bg_color = Colors.CARD

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
        table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {bg_color};
                color: {Colors.TEXT};
                border: none;
                border-radius: 6px;
                outline: none;
            }}
            QTableWidget::item {{
                padding: 4px 8px;
                border-bottom: 1px solid {Colors.HEADER};
            }}
            QTableWidget::item:selected {{
                background-color: {Colors.HEADER};
                color: {Colors.TEXT};
            }}
            QHeaderView::section {{
                background-color: {Colors.HEADER};
                color: {Colors.TEXT};
                font-family: {Fonts.FAMILY};
                font-size: {FontScale.size(self._font_base, FontScale.SMALL)}pt;
                font-weight: bold;
                padding: 8px;
                border: none;
            }}
        """)

        table.verticalHeader().setDefaultSectionSize(FontScale.row_height(self._font_base))

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
        table.setFont(self._font(FontScale.SMALL))

        # Enable hover events for tooltips and install delegate for total row background
        table.viewport().setMouseTracking(True)
        table.setItemDelegate(TotalRowDelegate(Colors.HEADER, Colors.TEXT, table))

        return table

    def _rebuild_tables(self):
        """Rebuild tables with current settings."""
        current_layout = self.current_section.layout()

        # Remove old tables
        current_layout.removeWidget(self.current_table)
        self.current_table.deleteLater()

        self.bottom_stack.removeWidget(self.history_table)
        self.history_table.deleteLater()
        self.bottom_stack.removeWidget(self.rolling_table)
        self.rolling_table.deleteLater()

        mode_cols = self._get_mode_cols()

        # Create new tables
        self.current_table = self._create_table(
            self._settings.current_rows,
            mode_cols=mode_cols,
            has_time=False,
            bg_color=Colors.CURRENT_BG,
            has_total_row=self._has_total_row(),
        )
        self.history_table = self._create_table(
            self._settings.history_rows,
            mode_cols=mode_cols,
            has_time=True,
            bg_color=Colors.HISTORY_BG,
        )
        self.rolling_table = self._create_table(
            0,
            mode_cols=mode_cols,
            has_time=False,
            bg_color=Colors.ROLLING_BG,
            has_uptime=True,
        )

        # Add to layouts
        current_layout.addWidget(self.current_table)
        self.bottom_stack.insertWidget(0, self.history_table)
        self.bottom_stack.insertWidget(1, self.rolling_table)
        self.bottom_stack.setCurrentIndex(self._bottom_page)

        # Re-apply saved column widths after rebuild
        if self._saved_col_widths_current:
            self._apply_col_widths(self.current_table, self._saved_col_widths_current)
        if self._saved_col_widths_history:
            self._apply_col_widths(self.history_table, self._saved_col_widths_history)
        if self._saved_col_widths_rolling:
            self._apply_col_widths(self.rolling_table, self._saved_col_widths_rolling)

        self._connect_table_selection()

    def _connect_table_selection(self):
        """Connect row-selection signals after table creation or rebuild."""
        cur = self.current_table
        hist = self.history_table
        roll = self.rolling_table
        cur.cellClicked.connect(
            lambda r, c, t=cur: self._on_cell_clicked(t, r, has_total_row=True)
        )
        hist.cellClicked.connect(
            lambda r, c, t=hist: self._on_cell_clicked(t, r, has_total_row=False)
        )
        roll.cellClicked.connect(
            lambda r, c, t=roll: self._on_cell_clicked(t, r, has_total_row=False)
        )
        cur.viewport().installEventFilter(self)
        hist.viewport().installEventFilter(self)
        roll.viewport().installEventFilter(self)
        # Context menu for process actions (all three tables)
        cur.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        cur.customContextMenuRequested.connect(
            lambda pos, t=cur: self._on_context_menu(pos, t, has_total_row=True)
        )
        hist.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hist.customContextMenuRequested.connect(
            lambda pos, t=hist: self._on_context_menu(pos, t, has_total_row=False)
        )
        roll.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        roll.customContextMenuRequested.connect(
            lambda pos, t=roll: self._on_context_menu(pos, t, has_total_row=False)
        )

    def _on_cell_clicked(self, table: QTableWidget, row: int, has_total_row: bool):
        """Toggle row highlight; Σ total row is never selectable."""
        if has_total_row and row == table.rowCount() - 1:
            table.clearSelection()
            return
        prev = getattr(table, '_last_clicked_row', None)
        if prev == row:
            table.clearSelection()
            table._last_clicked_row = None
        else:
            table._last_clicked_row = row

    def eventFilter(self, obj, event):
        """Clear row selection when clicking empty space inside a table viewport."""
        if event.type() == QEvent.Type.MouseButtonPress:
            for table in (self.current_table, self.history_table, self.rolling_table):
                if obj is table.viewport() and not table.indexAt(event.pos()).isValid():
                    table.clearSelection()
                    table._last_clicked_row = None
        return super().eventFilter(obj, event)

    def _on_app_state_changed(self, state):
        """Clear table selection when the application loses OS-level focus."""
        if state != Qt.ApplicationState.ApplicationActive:
            for table in (self.current_table, self.history_table, self.rolling_table):
                table.clearSelection()
                table._last_clicked_row = None

    def _set_monitor_enabled(self, enabled: bool):
        """Resume or pause this mode's collection when the window is shown/hidden."""
        if enabled:
            self._apply_settings(self._settings)
        else:
            self._disable_collector()

    def show_from_tray(self):
        """Re-show a hidden window and resume its monitor."""
        self._set_monitor_enabled(True)
        if not self._collector.isRunning():
            self._collector.start()
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        """Hide to the tray instead of exiting; the monitor pauses while hidden.

        Real application exit goes through QApplication.quit() (File > Exit or
        the tray menu). During OS session end (logoff/shutdown) the close is
        accepted so Windows is not blocked by the ignored event.
        """
        self._save_window_layout()
        self._set_monitor_enabled(False)
        if QApplication.instance().isSavingSession():
            super().closeEvent(event)
            return
        event.ignore()
        self.hide()

    # -------------------------------------------------------------------------
    # Context menu — process actions
    # -------------------------------------------------------------------------

    def _on_context_menu(self, pos, table: QTableWidget, has_total_row: bool = False):
        """Show process action menu on right-click in any process table."""
        index = table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        # Block Σ total row (always the last row in current processes table)
        if has_total_row and row == table.rowCount() - 1:
            return
        name_item = table.item(row, 1)
        if not name_item or not name_item.text():
            return

        process_name = name_item.text()

        # Gather live process info for the info section
        procs = find_processes(process_name)
        pids = [p.pid for p in procs]
        exe_path = get_exe_path(procs) if procs else None

        # Full PID string for clipboard copy
        pid_clipboard = ", ".join(str(p) for p in pids)

        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLE)

        # Info section — PIDs split 10 per row, click any line to copy all
        pid_actions: list = []
        if pids:
            label = "PIDs" if len(pids) > 1 else "PID"
            chunks = [pids[i:i + 10] for i in range(0, len(pids), 10)]
            for i, chunk in enumerate(chunks):
                chunk_str = ", ".join(str(p) for p in chunk)
                prefix = f"{label}: " if i == 0 else "  "
                act = menu.addAction(f"{prefix}{chunk_str}")
                act.setToolTip("Click to copy all PIDs to clipboard")
                pid_actions.append(act)

        exe_action = None
        if exe_path:
            exe_action = menu.addAction(f"EXE: {Path(exe_path).name}")
            exe_action.setToolTip(f"{exe_path}\nClick to copy to clipboard")

        if pid_actions or exe_action:
            menu.addSeparator()

        kill_action = menu.addAction("Kill Process...")
        menu.addSeparator()
        open_action = menu.addAction("Open File Location")
        menu.addSeparator()
        priority_action = menu.addAction("Set Priority...")

        action = menu.exec(table.viewport().mapToGlobal(pos))

        if action is None:
            return
        if action in pid_actions:
            QApplication.clipboard().setText(pid_clipboard)
        elif action == exe_action:
            QApplication.clipboard().setText(exe_path)
        elif action == kill_action:
            self._do_kill(process_name)
        elif action == open_action:
            self._do_open_location(process_name)
        elif action == priority_action:
            self._do_set_priority(process_name)

    def _do_kill(self, process_name: str):
        """Kill all instances of the process after confirmation."""
        procs = find_processes(process_name)
        if not procs:
            QMessageBox.information(self, "Kill Process", f"No running instances of '{process_name}' found.")
            return
        color_mgr = ProcessColorManager()
        proc_color = color_mgr.get_process_color(process_name)
        dialog = KillConfirmDialog(self, process_name, len(procs), proc_color)
        if dialog.exec():
            killed, errors = kill_processes(procs)
            if errors:
                QMessageBox.warning(
                    self, "Kill Process",
                    f"Killed {killed} instance(s).\n\nErrors:\n" + "\n".join(errors),
                )

    def _do_open_location(self, process_name: str):
        """Open Explorer with the process exe file selected."""
        procs = find_processes(process_name)
        if not procs:
            QMessageBox.information(self, "Open File Location", f"No running instances of '{process_name}' found.")
            return
        path = get_exe_path(procs)
        if not path:
            QMessageBox.warning(self, "Open File Location", "Could not get file path. Access denied.")
            return
        open_file_location(path)

    def _do_set_priority(self, process_name: str):
        """Set Windows priority class for all instances of the process."""
        procs = find_processes(process_name)
        if not procs:
            QMessageBox.information(self, "Set Priority", f"No running instances of '{process_name}' found.")
            return
        color_mgr = ProcessColorManager()
        proc_color = color_mgr.get_process_color(process_name)
        current_prio = get_current_priority(procs)
        dialog = PriorityDialog(self, process_name, current_prio, proc_color)
        if dialog.exec():
            new_prio = dialog.get_selected_priority()
            if new_prio is not None:
                changed, errors = set_priority(procs, new_prio)
                if errors:
                    QMessageBox.warning(
                        self, "Set Priority",
                        f"Updated {changed} instance(s).\n\nErrors:\n" + "\n".join(errors),
                    )

    def _toggle_pause(self):
        """Toggle pause. Must be implemented by subclasses for proper pause/resume."""
        self.is_paused = not self.is_paused
        self._pause_action.setText("Resume" if self.is_paused else "Pause")

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
        self._settings = CPUSettings(
            current_rows=initial_settings.current_rows,
            history_rows=initial_settings.history_rows,
            refresh_rate_ms=initial_settings.refresh_rate_ms,
            retention_minutes=initial_settings.retention_minutes,
            font_size=initial_settings.font_size,
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

    def _configure_collector(self):
        """Configure the shared collector for CPU monitoring using current settings."""
        self._collector.configure_cpu(
            cpu_threads=self._initial_settings.cpu_threads,
            ram_gb=self._initial_settings.ram_gb,
            current_rows=self._settings.current_rows,
            history_rows=self._settings.history_rows,
            retention_minutes=self._settings.retention_minutes,
            refresh_rate_ms=self._settings.refresh_rate_ms,
        )

    def _disable_collector(self):
        """Disable CPU collection on the shared collector."""
        self._collector.disable_cpu()

    def _create_settings_dialog(self):
        """Create the CPU settings dialog."""
        return CPUSettingsDialog(self, self._settings)

    def _fill_cpu_cols(self, table, row, item, color_mgr):
        """Fill CPU-specific columns: Usage, Count, Threads."""
        monitor = self._collector.cpu_monitor
        value_str = monitor.format_value(item.value, "MB") if monitor else f"{item.value:.0f}"
        value_item = QTableWidgetItem(value_str)
        if monitor:
            pct = item.value / (monitor.cpu_threads * 100) * 100
            value_item.setForeground(color_mgr.get_value_color(pct, "cpu"))
        table.setItem(row, 2, value_item)
        table.setItem(row, 3, QTableWidgetItem(str(item.count)))
        table.setItem(row, 4, QTableWidgetItem(str(item.threads) if item.threads > 0 else ""))

    def _fill_cpu_history_cols(self, table, row, item, color_mgr):
        """Fill CPU history columns: Usage, Count, Threads, Time."""
        self._fill_cpu_cols(table, row, item, color_mgr)
        table.setItem(row, 5, QTableWidgetItem(item.time_str))

    def _fill_cpu_rolling_cols(self, table, row, item, color_mgr):
        """Fill CPU rolling columns: Usage, Count, Threads, Uptime."""
        self._fill_cpu_cols(table, row, item, color_mgr)
        uptime_min = round(item.uptime_seconds / 60)
        uptime_item = QTableWidgetItem(f"{uptime_min}m")
        if uptime_min >= self._settings.retention_minutes:
            uptime_item.setForeground(QColor(Colors.TEXT_MUTED))
        table.setItem(row, 5, uptime_item)

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

        # CPU mode: Temperature, Power, Electric
        cpu_has_data = any([hwinfo.cpu_tctl, hwinfo.cpu_power, hwinfo.cpu_edc])
        self.sensor_widget.setVisible(cpu_has_data)
        if cpu_has_data:
            sensor_names = ["Temperature", "Power", "Electric"]
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
        total_row = self.current_table.rowCount() - 1
        color_mgr = self._fill_process_rows(
            self.current_table, data.processes, self._fill_cpu_cols, limit=total_row)

        # Fill Σ total row
        totals = data.process_totals
        self.current_table.setItem(total_row, 0, self._make_total_item("Σ"))
        self.current_table.setItem(total_row, 1, self._make_total_item("Total"))
        usage_str = monitor.format_value(totals.value, "MB") if monitor else f"{totals.value:.0f}"
        usage_item = self._make_total_item(usage_str)
        if monitor:
            pct = totals.value / (monitor.cpu_threads * 100) * 100
            usage_item.setForeground(color_mgr.get_value_color(pct, "cpu_all"))
        self.current_table.setItem(total_row, 2, usage_item)
        self.current_table.setItem(total_row, 3, self._make_total_item(str(totals.count)))
        self.current_table.setItem(total_row, 4, self._make_total_item(str(totals.threads) if totals.threads > 0 else ""))

        # Update history table
        self._fill_process_rows(self.history_table, data.history, self._fill_cpu_history_cols)

        # Update rolling average table (dynamic row count)
        self.rolling_table.setRowCount(len(data.rolling_average))
        self._fill_process_rows(self.rolling_table, data.rolling_average, self._fill_cpu_rolling_cols)


class MemoryWindow(BaseMonitorWindow):
    """Memory Monitor window."""

    def __init__(self, initial_settings: InitialSettings, collector: SharedDataCollector, parent=None):
        self._initial_settings = initial_settings
        self._collector = collector
        self._settings = MemorySettings(
            current_rows=initial_settings.current_rows,
            history_rows=initial_settings.history_rows,
            refresh_rate_ms=initial_settings.refresh_rate_ms,
            retention_minutes=initial_settings.retention_minutes,
            memory_unit=initial_settings.memory_unit,
            font_size=initial_settings.font_size,
        )
        self._commit_limit_bytes: int = initial_settings.commit_limit_bytes
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

    def _configure_collector(self):
        """Configure the shared collector for Memory monitoring using current settings."""
        self._collector.configure_memory(
            cpu_threads=self._initial_settings.cpu_threads,
            ram_gb=self._initial_settings.ram_gb,
            current_rows=self._settings.current_rows,
            history_rows=self._settings.history_rows,
            retention_minutes=self._settings.retention_minutes,
            refresh_rate_ms=self._settings.refresh_rate_ms,
            memory_unit=self._settings.memory_unit,
        )

    def _disable_collector(self):
        """Disable Memory collection on the shared collector."""
        self._collector.disable_memory()

    def _create_settings_dialog(self):
        """Create the Memory settings dialog."""
        return MemorySettingsDialog(self, self._settings)

    def _fill_memory_cols(self, table, row, item, color_mgr):
        """Fill Memory-specific columns: Usage, Commit."""
        monitor = self._collector.memory_monitor
        unit = self._settings.memory_unit
        value_str = monitor.format_value(item.value, unit) if monitor else f"{item.value:.0f}"
        value_item = QTableWidgetItem(value_str)
        if monitor:
            pct = item.value / monitor.ram_bytes * 100
            value_item.setForeground(color_mgr.get_value_color(pct, "memory"))
        table.setItem(row, 2, value_item)
        commit_str = monitor.format_value(item.vms, unit) if monitor else ""
        commit_item = QTableWidgetItem(commit_str)
        if monitor and self._commit_limit_bytes > 0:
            commit_pct = item.vms / self._commit_limit_bytes * 100
            commit_item.setForeground(color_mgr.get_value_color(commit_pct, "memory_total"))
        table.setItem(row, 3, commit_item)

    def _fill_memory_history_cols(self, table, row, item, color_mgr):
        """Fill Memory history columns: Usage, Commit, Time."""
        self._fill_memory_cols(table, row, item, color_mgr)
        table.setItem(row, 4, QTableWidgetItem(item.time_str))

    def _fill_memory_rolling_cols(self, table, row, item, color_mgr):
        """Fill Memory rolling columns: Usage, Commit, Uptime."""
        self._fill_memory_cols(table, row, item, color_mgr)
        uptime_min = round(item.uptime_seconds / 60)
        uptime_item = QTableWidgetItem(f"{uptime_min}m")
        if uptime_min >= self._settings.retention_minutes:
            uptime_item.setForeground(QColor(Colors.TEXT_MUTED))
        table.setItem(row, 4, uptime_item)

    def _on_data_ready(self, data: MonitorData):
        """Handle data from collector."""
        if self.is_paused:
            return

        monitor = self._collector.memory_monitor
        unit = self._settings.memory_unit

        # Update header
        self.total_label.setText(data.total_display)
        self.peak_label.setText(data.max_display)

        # Get HWiNFO sensor data
        hwinfo = data.hwinfo

        # Memory mode: Committed, Read, Write
        mem_has_data = any([hwinfo.virt_committed, hwinfo.dram_read, hwinfo.dram_write])
        self.sensor_widget.setVisible(mem_has_data)
        if mem_has_data:
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
                self.sensor_value_labels[i].setStyleSheet(f"color: {Colors.TEXT}; background: transparent;")

        # Update current table
        total_row = self.current_table.rowCount() - 1
        color_mgr = self._fill_process_rows(
            self.current_table, data.processes, self._fill_memory_cols, limit=total_row)

        # Fill Σ total row
        totals = data.process_totals
        self.current_table.setItem(total_row, 0, self._make_total_item("Σ"))
        self.current_table.setItem(total_row, 1, self._make_total_item("Total"))
        usage_str = monitor.format_value(totals.value, unit) if monitor else f"{totals.value:.0f}"
        usage_item = self._make_total_item(usage_str)
        if monitor:
            pct = totals.value / monitor.ram_bytes * 100
            usage_item.setForeground(color_mgr.get_value_color(pct, "memory_all"))
        self.current_table.setItem(total_row, 2, usage_item)
        total_commit_str = monitor.format_value(totals.vms, unit) if monitor else ""
        total_commit_item = self._make_total_item(total_commit_str)
        if monitor and self._commit_limit_bytes > 0:
            total_commit_pct = totals.vms / self._commit_limit_bytes * 100
            total_commit_item.setForeground(color_mgr.get_value_color(total_commit_pct, "memory_all_total"))
        self.current_table.setItem(total_row, 3, total_commit_item)

        # Update history table
        self._fill_process_rows(self.history_table, data.history, self._fill_memory_history_cols)

        # Update rolling average table (dynamic row count)
        self.rolling_table.setRowCount(len(data.rolling_average))
        self._fill_process_rows(self.rolling_table, data.rolling_average, self._fill_memory_rolling_cols)


class NetworkWindow(BaseMonitorWindow):
    """Network Monitor window."""

    def __init__(self, initial_settings: InitialSettings, collector: SharedDataCollector, parent=None):
        self._initial_settings = initial_settings
        self._collector = collector
        self._settings = NetworkSettings(
            current_rows=initial_settings.current_rows,
            history_rows=initial_settings.history_rows,
            refresh_rate_ms=initial_settings.refresh_rate_ms,
            retention_minutes=initial_settings.retention_minutes,
            network_unit=initial_settings.network_unit,
            sort_mode=initial_settings.network_sort_mode,
            max_download_mbps=initial_settings.network_max_download_mbps,
            max_upload_mbps=initial_settings.network_max_upload_mbps,
            font_size=initial_settings.font_size,
        )
        # Max speed in bytes/sec for color scale percentage calculation
        self._max_dl_bytes = self._resolve_max_bytes(initial_settings.network_max_download_mbps)
        self._max_ul_bytes = self._resolve_max_bytes(initial_settings.network_max_upload_mbps)
        super().__init__(parent)

        # Connect to collector signal
        self._collector.network_data_ready.connect(self._on_data_ready)

        # Configure and start collector
        self._apply_settings()
        if not self._collector.isRunning():
            self._collector.start()

    @staticmethod
    def _resolve_max_bytes(mbps: int) -> float:
        """Convert a max-speed setting (Mbps) to bytes/sec.

        0 means "auto" in the settings UI — resolve it to the detected link
        speed so color coding keeps working instead of silently turning off.
        """
        from .network_monitor import get_link_speed_mbps
        resolved = mbps or get_link_speed_mbps()
        return resolved * 1_000_000 / 8

    def _get_mode(self) -> MonitorMode:
        return MonitorMode.NETWORK

    def _get_title(self) -> str:
        return "Network Monitor"

    def _get_mode_cols(self) -> str:
        return "net"

    def _get_window_key(self) -> str:
        return "network"

    def _has_total_row(self) -> bool:
        return False

    def _configure_collector(self):
        """Configure the shared collector for Network monitoring using current settings."""
        self._collector.configure_network(
            current_rows=self._settings.current_rows,
            history_rows=self._settings.history_rows,
            retention_minutes=self._settings.retention_minutes,
            refresh_rate_ms=self._settings.refresh_rate_ms,
            network_unit=self._settings.network_unit,
            sort_mode=self._settings.sort_mode,
            max_download_mbps=self._settings.max_download_mbps,
            max_upload_mbps=self._settings.max_upload_mbps,
        )

    def _disable_collector(self):
        """Disable Network collection on the shared collector."""
        self._collector.disable_network()

    def _create_settings_dialog(self):
        """Create the Network settings dialog."""
        return NetworkSettingsDialog(self, self._settings)

    def _store_settings(self, new_settings):
        """Store new settings and recompute max-speed color thresholds."""
        self._settings = new_settings
        self._max_dl_bytes = self._resolve_max_bytes(new_settings.max_download_mbps)
        self._max_ul_bytes = self._resolve_max_bytes(new_settings.max_upload_mbps)

    def _fill_net_cols(self, table, row, item, color_mgr):
        """Fill Network-specific columns: Download, Upload."""
        unit = self._settings.network_unit
        dl_str = format_speed(item.download, unit)
        dl_item = QTableWidgetItem(dl_str)
        if self._max_dl_bytes > 0:
            dl_pct = item.download / self._max_dl_bytes * 100
            dl_item.setForeground(color_mgr.get_value_color(dl_pct, "net_dl"))
        table.setItem(row, 2, dl_item)

        ul_str = format_speed(item.upload, unit)
        ul_item = QTableWidgetItem(ul_str)
        if self._max_ul_bytes > 0:
            ul_pct = item.upload / self._max_ul_bytes * 100
            ul_item.setForeground(color_mgr.get_value_color(ul_pct, "net_ul"))
        table.setItem(row, 3, ul_item)

    def _fill_net_history_cols(self, table, row, item, color_mgr):
        """Fill Network history columns: Download, Upload, Time."""
        self._fill_net_cols(table, row, item, color_mgr)
        table.setItem(row, 4, QTableWidgetItem(item.time_str))

    def _fill_net_rolling_cols(self, table, row, item, color_mgr):
        """Fill Network rolling columns: Download, Upload, Uptime."""
        self._fill_net_cols(table, row, item, color_mgr)
        uptime_min = round(item.uptime_seconds / 60)
        uptime_item = QTableWidgetItem(f"{uptime_min}m")
        if uptime_min >= self._settings.retention_minutes:
            uptime_item.setForeground(QColor(Colors.TEXT_MUTED))
        table.setItem(row, 4, uptime_item)

    def _on_data_ready(self, data: NetworkMonitorData):
        """Handle data from collector."""
        if self.is_paused:
            return

        # ETW tracer unavailable — show the reason instead of zeros
        if data.error:
            self.total_label.setText("↓ --")
            self.peak_label.setText(data.error)
            self.sensor_widget.setVisible(False)
            return

        unit = self._settings.network_unit

        # Update header — big number = current download speed
        self.total_label.setText(f"↓ {format_speed(data.current_download, unit)}")
        self.peak_label.setText(data.peak_display)

        # Sensor row: Upload speed, Total Download, Total Upload
        self.sensor_widget.setVisible(True)
        self.sensor_name_labels[0].setText("Upload")
        self.sensor_value_labels[0].setText(f"↑ {format_speed(data.current_upload, unit)}")
        self.sensor_value_labels[0].setStyleSheet(f"color: {Colors.TEXT}; background: transparent;")

        self.sensor_name_labels[1].setText("Total ↓")
        self.sensor_value_labels[1].setText(format_bytes_total(data.cumulative_download, unit))
        self.sensor_value_labels[1].setStyleSheet(f"color: {Colors.TEXT}; background: transparent;")

        self.sensor_name_labels[2].setText("Total ↑")
        self.sensor_value_labels[2].setText(format_bytes_total(data.cumulative_upload, unit))
        self.sensor_value_labels[2].setStyleSheet(f"color: {Colors.TEXT}; background: transparent;")

        # Update current table (no total row for network)
        self._fill_process_rows(
            self.current_table, data.processes, self._fill_net_cols,
            limit=self.current_table.rowCount(),
        )

        # Update history table
        self._fill_process_rows(self.history_table, data.history, self._fill_net_history_cols)

        # Update rolling average table (dynamic row count)
        self.rolling_table.setRowCount(len(data.rolling_average))
        self._fill_process_rows(self.rolling_table, data.rolling_average, self._fill_net_rolling_cols)
