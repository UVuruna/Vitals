"""BaseMonitorWindow — the template every monitor window is built from.

One responsibility: BE a monitor gadget. It owns the window shell (Qt.Tool,
hide-to-tray, keys, focus), the header/banner/splitter layout, this window's
theme scope, the settings round-trip, and the orchestration of one tick into
three tables. Everything it does NOT own it delegates to a module beside it —
placement, shell integration, the table factory, the status banner, layout
persistence and the process menu.

Subclasses fill in only what differs per mode: the collector signal to listen
on, which columns exist, and how one tick renders (`_render_data`).

Every window owns its own `ThemeScope` (owner 2026-07-26): the Day/Night
switch in its header flips THIS window alone, and every color it paints —
chrome, table QSS, per-cell brushes — is read from `self._theme.palette`.
Nothing here may reach for an app-wide theme, or a flip would leak into the
other two gadgets.
"""

import json
import sys
from typing import Optional

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from ..collect.monitor_data import MonitorData, MonitorMode
from ..collect.network_trace import NEEDS_ADMIN
from ..color_management import ProcessColorManager
from ..icons import IconButton
from ..persistence import get_base_path
from ..settings import InitialSettings
from ..styles import Defaults, Dimensions, FontScale, scaled_font
from ..theme import window_theme
from ..theme_switch import DayNightSwitch
from ..transition import flip_window_theme
from . import layout_store, process_menu
from .placement import place_on_screen
from .shell import relaunch_elevated, set_native_taskbar_icon
from .status_banner import StatusBanner
from .table_factory import create_table, header_css, style_table
from .table_widgets import DoubleClickSplitter, TotalRowDelegate


# ═════════════════════════ THE MONITOR WINDOW TEMPLATE ═════════════════════════

class BaseMonitorWindow(QMainWindow):
    """Base class for monitor windows (CPU, Memory and Network).

    Each window owns its own `ThemeScope` (owner 2026-07-26): the Day/Night
    switch in its header flips THIS window only, and every color it paints —
    chrome, table QSS, per-cell brushes — is read from `self._theme.palette`.
    Nothing here may reach for an app-wide theme, or a flip would leak into
    the other two gadgets.
    """

    # Temperature thresholds in °C — the COLORS themselves come from the
    # active palette (TEXT / TEMP_WARNING / TEMP_CRITICAL) so they follow the
    # theme; only the trip points are configurable.
    DEFAULT_TEMP_THRESHOLDS = {
        "warning_threshold": 60,
        "critical_threshold": 75,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        # Gadget mode: Tool windows have no taskbar button and no Alt-Tab
        # entry — the tray icon (app/tray.py) is the app's single identity.
        # The native title bar keeps normal move/resize/close behavior.
        self.setWindowFlag(Qt.WindowType.Tool, True)
        # This window's own theme — resolved before any widget is built, so
        # every child can be handed the scope it must follow.
        self._theme = window_theme(self._get_window_key())
        self.is_paused = False
        self._saved_col_widths_current: list[int] | None = None
        self._saved_col_widths_history: list[int] | None = None
        self._saved_col_widths_rolling: list[int] | None = None
        self._layout_restored: bool = False
        self._peer_window: 'BaseMonitorWindow | None' = None
        self._bottom_page: int = 0  # 0 = Peak Usage, 1 = Rolling Average
        # Splitter sizes stashed while the status banner is up
        self._split_before_status: list[int] | None = None
        # The last rendered tick, kept so a theme flip can repaint every cell
        # IMMEDIATELY instead of waiting for the next collector signal — that
        # wait is what left half the table in the old theme's colors.
        self._last_data = None

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
        self._setup_ui()
        self._apply_theme()
        self._theme.changed.connect(self._apply_theme)

        app = QApplication.instance()
        if app:
            app.applicationStateChanged.connect(self._on_app_state_changed)

    # -------------------------------------------------------------------------
    # Template hooks — every subclass answers these
    # -------------------------------------------------------------------------

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

    def _create_settings_dialog(self):
        """Create and return this mode's settings dialog. Must be overridden in subclasses."""
        raise NotImplementedError("Subclasses must implement _create_settings_dialog()")

    def _settings_from_initial(self, initial: InitialSettings):
        """Build this mode's settings dataclass from the shared setup values.

        The setup screen configures all three monitors at once, so each mode
        has to know how to read itself out of one `InitialSettings`. Used both
        at construction and whenever the setup screen is re-applied.
        """
        raise NotImplementedError("Subclasses must implement _settings_from_initial()")

    def _render_data(self, data: MonitorData):
        """Draw one tick into the header and tables. Implemented per mode."""
        raise NotImplementedError("Subclasses must implement _render_data()")

    def _store_settings(self, new_settings):
        """Store new settings. NetworkWindow overrides to also recompute max-speed thresholds."""
        self._settings = new_settings

    # -------------------------------------------------------------------------
    # Window lifecycle
    # -------------------------------------------------------------------------

    def showEvent(self, event):
        """Set the native icon, restore the layout once, and always re-clamp.

        The clamp runs on EVERY show, not just the first: the screen layout can
        change while a gadget is hidden in the tray, and coming back stranded
        is exactly as unusable as starting stranded.
        """
        super().showEvent(event)
        if not getattr(self, '_native_icon_set', False):
            self._native_icon_set = True
            set_native_taskbar_icon(self, getattr(self, '_ico_path', None))
        if not self._layout_restored:
            self._layout_restored = True
            self._restore_window_layout()
        place_on_screen(self)

    def _hide_to_tray(self):
        """Hide this window to the tray, saving its layout first.

        The shared collector keeps running — CPU/Memory come from one bulk
        NtQuerySystemInformation call regardless of which windows are visible,
        so pausing a hidden mode would save nothing while breaking continuous
        peak/history tracking. The tray icon (or File > Exit) is the only quit.
        """
        self._save_window_layout()
        self.hide()

    def show_from_tray(self):
        """Re-show a hidden window (its monitor never stopped)."""
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        """Hide to the tray instead of exiting (the monitor keeps running).

        Real application exit goes through QApplication.quit() (File > Exit or
        the tray menu). During OS session end (logoff/shutdown) the close is
        accepted so Windows is not blocked by the ignored event.
        """
        if QApplication.instance().isSavingSession():
            self._save_window_layout()
            super().closeEvent(event)
            return
        event.ignore()
        self._hide_to_tray()

    def keyPressEvent(self, event):
        """Handle keys."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_Space:
            self._toggle_pause()
        else:
            super().keyPressEvent(event)

    # -------------------------------------------------------------------------
    # Settings
    # -------------------------------------------------------------------------

    def _adopt_settings(self, new_settings):
        """Apply a new settings object: collector, tables, fonts.

        Returns the PREVIOUS settings, or None when nothing changed.
        """
        prev = self._settings
        if new_settings == prev:
            return None
        self._store_settings(new_settings)
        self._apply_settings(prev)
        if new_settings.font_size != prev.font_size:
            self._font_base = new_settings.font_size
            self._apply_fonts()
        return prev

    def apply_shared_settings(self, initial: InitialSettings):
        """Adopt settings coming from the shared setup screen.

        Called by the window manager after the tray's Settings dialog, so one
        edit reaches every open monitor. No peer sync is needed — the manager
        pushes the same values into each window itself.
        """
        self._initial_settings = initial
        self._adopt_settings(self._settings_from_initial(initial))

    def _show_settings(self):
        """Show this window's settings dialog and apply any changes.

        Applies the new settings to the collector (rebuilding tables if row
        counts changed), re-applies fonts if the font size changed, and syncs
        a visible peer window's refresh rate if it changed (NetworkWindow has
        no peer, so the guard below is always a no-op for it).
        """
        dialog = self._create_settings_dialog()
        accepted = dialog.exec()
        try:
            if not accepted:
                return
            new_settings = dialog.get_settings()
            prev = self._adopt_settings(new_settings)
            if prev is None:
                return
            # Keep the peer's refresh rate in sync (both read from the same
            # collector tick). Hidden peers still monitor, so no visibility guard.
            if (
                self._peer_window is not None
                and new_settings.refresh_rate_ms != prev.refresh_rate_ms
            ):
                self._peer_window._sync_refresh_rate(new_settings.refresh_rate_ms)
        finally:
            # Parented to this window, so C++ owns it — but without this every
            # open leaves another dialog alive as a child for the app's lifetime.
            dialog.deleteLater()

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

    def _save_window_layout(self):
        """Persist this window's geometry, splitter and column widths."""
        layout_store.save(self)

    def _restore_window_layout(self):
        """Restore this window's geometry, splitter and column widths."""
        layout_store.restore(self)

    def _load_config(self):
        """Load temperature thresholds from JSON.

        Only the trip points are configurable — the colors come from the
        active palette so they follow the theme. An unreadable or invalid
        config.json is reported to stderr and the DEFAULT_TEMP_THRESHOLDS
        fallback is kept (documented behavior).
        """
        config_path = get_base_path() / "config" / "config.json"
        self.temp_config = self.DEFAULT_TEMP_THRESHOLDS.copy()

        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    data = json.load(f)
                    temp = data.get("temp_colors", {})
                    for key in self.DEFAULT_TEMP_THRESHOLDS:
                        if key in temp:
                            self.temp_config[key] = temp[key]
            except (OSError, ValueError) as e:
                print(f"[Vitals] Invalid {config_path}: {e} - using default temp thresholds", file=sys.stderr)

    # -------------------------------------------------------------------------
    # Theme
    # -------------------------------------------------------------------------

    def _get_temp_color(self, temp: Optional[float]) -> str:
        """Get this window's theme color for a temperature value."""
        palette = self._theme.palette
        if temp is None:
            return palette.TEXT

        if temp >= self.temp_config["critical_threshold"]:
            return palette.TEMP_CRITICAL
        elif temp >= self.temp_config["warning_threshold"]:
            return palette.TEMP_WARNING
        else:
            return palette.TEXT

    def _flip_theme(self):
        """Flip THIS window's theme (the header switch), covering it alone."""
        flip_window_theme(self._theme, self)

    def _apply_theme(self):
        """(Re)style every widget in this window from ITS palette.

        Runs once at startup and again on every Day/Night flip of this
        window's scope — it is the single place that owns the window's
        stylesheets, so no color can be left frozen at the theme that
        happened to be active at build time.
        """
        palette = self._theme.palette

        qpalette = QPalette()
        qpalette.setColor(QPalette.ColorRole.Window, QColor(palette.BACKGROUND))
        qpalette.setColor(QPalette.ColorRole.WindowText, QColor(palette.TEXT))
        qpalette.setColor(QPalette.ColorRole.Base, QColor(palette.CARD))
        qpalette.setColor(QPalette.ColorRole.Text, QColor(palette.TEXT))
        qpalette.setColor(QPalette.ColorRole.Button, QColor(palette.HEADER))
        qpalette.setColor(QPalette.ColorRole.ButtonText, QColor(palette.TEXT))
        self.setPalette(qpalette)

        self.header_widget.setStyleSheet(
            f"background-color: {palette.CARD}; border-radius: 8px;"
        )
        self.title_label.setStyleSheet(
            f"color: {palette.TEXT}; background: transparent;"
        )
        self.total_label.setStyleSheet(
            f"color: {palette.TEXT}; background: transparent;"
        )
        for lbl in self.sensor_name_labels:
            lbl.setStyleSheet(f"color: {palette.TEXT_MUTED}; background: transparent;")
        # Sensor VALUES carry a temperature color that the next refresh
        # recomputes; reset them to plain text so a flip is never stale.
        for lbl in self.sensor_value_labels:
            lbl.setStyleSheet(f"color: {palette.TEXT}; background: transparent;")
        self.status_banner.apply_theme()
        self.current_title.setStyleSheet(f"color: {palette.TEXT};")
        self.peak_label.setStyleSheet(
            f"color: {palette.TEXT_MUTED}; background: transparent;"
        )
        self.bottom_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {palette.TEXT};
                border: none;
                padding: 0;
                text-align: left;
            }}
            QPushButton:hover {{
                color: {palette.ACCENT};
            }}
        """)
        self.splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {palette.HEADER};
                height: 4px;
            }}
            QSplitter::handle:hover {{
                background-color: {palette.ACCENT};
            }}
        """)
        for table in (self.current_table, self.history_table, self.rolling_table):
            style_table(table, palette, self._font_base)

        # Table CELL colors are per-item brushes, not stylesheet properties, so
        # restyling cannot reach them. Re-render the last tick to recompute
        # every process and value color in the new palette right now; without
        # this the tables keep the old theme's colors until the next collector
        # signal, which at slow refresh rates is a visibly half-flipped window.
        if self._last_data is not None:
            self._render_data(self._last_data)

    def _font(self, offset: int, bold: bool = False):
        """Create a proportionally scaled font.

        Uses FontScale offsets: TITLE(+5), SECTION(+2), SUBTITLE(+1),
        BODY(0), SMALL(-1), TINY(-2).
        """
        return scaled_font(self._font_base, offset, bold)

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
        # Update table row heights and header font
        row_h = FontScale.row_height(self._font_base)
        css = header_css(self._theme.palette, self._font_base)
        content_font = self._font(FontScale.SMALL)
        for table in (self.current_table, self.history_table, self.rolling_table):
            table.setFont(content_font)
            table.verticalHeader().setDefaultSectionSize(row_h)
            table.horizontalHeader().setStyleSheet(css)

    # -------------------------------------------------------------------------
    # Layout
    # -------------------------------------------------------------------------

    def _setup_ui(self):
        """Initialize the main UI."""
        self.setWindowTitle(self._get_title())
        self.setMinimumWidth(Dimensions.WINDOW_MIN_WIDTH)
        self.setMinimumHeight(Dimensions.WINDOW_MIN_HEIGHT)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Header — a control column on the left, the data column on the right.
        #
        #   [pause][gear]   Title .................... Total
        #   [ ~switch~ ]    Temperature  Power  Electric
        #
        # Title and Total ALWAYS share one row (owner 2026-07-24). The switch
        # sits under the two icon buttons, level with the HWiNFO sensor row;
        # when there are no sensors to show, both columns centre against each
        # other so the two-row control block reads as one line with the title.
        # These controls replaced the old menu bar: it offered nothing but
        # Pause and Settings, both duplicated, while the title bar's X already
        # closes the window.
        self.header_widget = QWidget()
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(16, 10, 16, 12)
        header_layout.setSpacing(14)

        controls_widget = QWidget()
        controls_widget.setStyleSheet("background: transparent;")
        controls_col = QVBoxLayout(controls_widget)
        controls_col.setContentsMargins(0, 0, 0, 0)
        controls_col.setSpacing(2)

        icons_row = QHBoxLayout()
        icons_row.setContentsMargins(0, 0, 0, 0)
        icons_row.setSpacing(4)
        self.pause_btn = IconButton(icons.PAUSE, "Pause monitoring", self._theme)
        self.pause_btn.clicked.connect(self._toggle_pause)
        icons_row.addWidget(self.pause_btn)
        self.settings_btn = IconButton(icons.SETTINGS, "Settings", self._theme)
        self.settings_btn.clicked.connect(self._show_settings)
        icons_row.addWidget(self.settings_btn)
        icons_row.addStretch()
        controls_col.addLayout(icons_row)

        switch_row = QHBoxLayout()
        switch_row.setContentsMargins(0, 0, 0, 0)
        switch_row.setSpacing(0)
        # A per-window switch: it flips this gadget alone. The global one
        # lives on the setup screen (tray > Settings).
        self.theme_switch = DayNightSwitch(self._theme, self._flip_theme)
        self.theme_switch.setToolTip("Switch this window between dark and light theme")
        switch_row.addWidget(self.theme_switch)
        switch_row.addStretch()
        controls_col.addLayout(switch_row)

        header_layout.addWidget(
            controls_widget, 0, Qt.AlignmentFlag.AlignVCenter
        )

        data_widget = QWidget()
        data_widget.setStyleSheet("background: transparent;")
        data_col = QVBoxLayout(data_widget)
        data_col.setContentsMargins(0, 0, 0, 0)
        data_col.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel(self._get_title())
        self.title_label.setFont(self._font(FontScale.TITLE, bold=True))
        title_row.addWidget(self.title_label)

        title_row.addStretch()

        self.total_label = QLabel("")
        self.total_label.setFont(self._font(FontScale.SUBTITLE))
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(self.total_label)

        data_col.addLayout(title_row)

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
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col_layout.addWidget(name_lbl)

            value_lbl = QLabel("")
            value_lbl.setFont(self._font(FontScale.BODY))
            value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col_layout.addWidget(value_lbl)

            sensor_layout.addWidget(col)
            self.sensor_name_labels.append(name_lbl)
            self.sensor_value_labels.append(value_lbl)

        data_col.addWidget(self.sensor_widget)

        header_layout.addWidget(
            data_widget, 1, Qt.AlignmentFlag.AlignVCenter
        )

        layout.addWidget(self.header_widget)

        # Status banner — hidden until something is actually wrong, sitting
        # between the header and the data so a failure cannot read as "no data".
        self.status_banner = StatusBanner(
            self._theme, self._font_base, self._on_status_action
        )
        layout.addWidget(self.status_banner)

        # Splitter for resizable sections (double-click resets to 50-50)
        self.splitter = DoubleClickSplitter(Qt.Orientation.Vertical)

        # Current Processes section
        self.current_section = QWidget()
        current_layout = QVBoxLayout(self.current_section)
        current_layout.setContentsMargins(0, 0, 0, 4)
        current_layout.setSpacing(4)

        self.current_title = QLabel("Current Processes")
        self.current_title.setFont(self._font(FontScale.SECTION, bold=True))
        current_layout.addWidget(self.current_title)

        self.current_table = self._create_table(7, mode_cols=self._get_mode_cols())
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
        self.bottom_toggle_btn.clicked.connect(self._toggle_bottom_table)
        bottom_header_row.addWidget(self.bottom_toggle_btn)
        bottom_header_row.addStretch()

        self.peak_label = QLabel("Peak: --")
        self.peak_label.setFont(self._font(FontScale.SMALL))
        bottom_header_row.addWidget(self.peak_label)
        history_layout.addLayout(bottom_header_row)

        self.bottom_stack = QStackedWidget()
        self.history_table = self._create_table(4, mode_cols=self._get_mode_cols(), has_time=True)
        self.rolling_table = self._create_table(0, mode_cols=self._get_mode_cols(), has_time=False, has_uptime=True)
        self.bottom_stack.addWidget(self.history_table)   # index 0 = Peak Usage
        self.bottom_stack.addWidget(self.rolling_table)   # index 1 = Rolling Average
        history_layout.addWidget(self.bottom_stack)

        self.splitter.addWidget(self.history_section)

        # Set initial sizes (current gets more space)
        self.splitter.setSizes([300, 150])

        layout.addWidget(self.splitter)

    # -------------------------------------------------------------------------
    # Status banner
    # -------------------------------------------------------------------------

    def show_status(self, failure) -> None:
        """Raise the banner for a capture failure, or hide it when None.

        The splitter sizes are captured before the banner appears and restored
        after it goes: inserting a widget above the splitter otherwise squeezes
        it, and the next `_save_window_layout()` would persist that squeeze as
        the user's chosen split.
        """
        if failure is None:
            if self.status_banner.isVisible():
                self.status_banner.setVisible(False)
                if self._split_before_status is not None:
                    self.splitter.setSizes(self._split_before_status)
                    self._split_before_status = None
            return

        if not self.status_banner.isVisible():
            self._split_before_status = self.splitter.sizes()
        self.status_banner.show_failure(failure)

    def _on_status_action(self):
        """Run the remedy the banner is offering."""
        if self.status_banner.code == NEEDS_ADMIN:
            relaunch_elevated()
            return
        # Re-entering configure_* rebuilds the tracer: it was set to None when
        # it failed, so this genuinely retries rather than reusing a dead one.
        self._configure_collector()

    # -------------------------------------------------------------------------
    # Tables
    # -------------------------------------------------------------------------

    def _create_table(self, rows: int, mode_cols: str = "none", has_time: bool = False, has_total_row: bool = False, has_uptime: bool = False) -> QTableWidget:
        """Create one of this window's three tables in its theme and font."""
        return create_table(
            rows,
            scope=self._theme,
            font_base=self._font_base,
            mode_cols=mode_cols,
            has_time=has_time,
            has_total_row=has_total_row,
            has_uptime=has_uptime,
        )

    def _make_total_item(self, text: str) -> QTableWidgetItem:
        """Create a styled QTableWidgetItem for the Σ total row."""
        item = QTableWidgetItem(text)
        item.setData(TotalRowDelegate.ROLE, True)
        item.setForeground(QColor(self._theme.palette.TEXT))
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
        palette = self._theme.palette
        max_rows = limit if limit is not None else table.rowCount()

        for row, item in enumerate(data):
            if row >= max_rows:
                break
            table.setItem(row, 0, QTableWidgetItem(str(row + 1)))

            name_item = QTableWidgetItem(item.name)
            proc_color = color_mgr.get_process_color(item.name, palette)
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
            has_total_row=self._has_total_row(),
        )
        self.history_table = self._create_table(
            self._settings.history_rows,
            mode_cols=mode_cols,
            has_time=True,
        )
        self.rolling_table = self._create_table(
            0,
            mode_cols=mode_cols,
            has_time=False,
            has_uptime=True,
        )

        # Add to layouts
        current_layout.addWidget(self.current_table)
        self.bottom_stack.insertWidget(0, self.history_table)
        self.bottom_stack.insertWidget(1, self.rolling_table)
        self.bottom_stack.setCurrentIndex(self._bottom_page)

        # Re-apply saved column widths after rebuild
        if self._saved_col_widths_current:
            layout_store.apply_col_widths(self.current_table, self._saved_col_widths_current)
        if self._saved_col_widths_history:
            layout_store.apply_col_widths(self.history_table, self._saved_col_widths_history)
        if self._saved_col_widths_rolling:
            layout_store.apply_col_widths(self.rolling_table, self._saved_col_widths_rolling)

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
            lambda pos, t=cur: process_menu.show_process_menu(self, pos, t, has_total_row=True)
        )
        hist.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hist.customContextMenuRequested.connect(
            lambda pos, t=hist: process_menu.show_process_menu(self, pos, t, has_total_row=False)
        )
        roll.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        roll.customContextMenuRequested.connect(
            lambda pos, t=roll: process_menu.show_process_menu(self, pos, t, has_total_row=False)
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

    # -------------------------------------------------------------------------
    # Bottom page + pause + ticks
    # -------------------------------------------------------------------------

    def _show_bottom_page(self, page: int):
        """Show Peak Usage (0) or Rolling Average (1) and label the toggle."""
        self._bottom_page = page
        self.bottom_stack.setCurrentIndex(page)
        if page == 0:
            self.bottom_toggle_btn.setText("◀ Peak Usage ▶")
            self.peak_label.setVisible(True)
        else:
            self.bottom_toggle_btn.setText("◀ Rolling Average ▶")

    def _toggle_bottom_table(self):
        """Switch between Peak Usage (index 0) and Rolling Average (index 1)."""
        self._show_bottom_page(1 - self._bottom_page)

    def _toggle_pause(self):
        """Toggle pause and flip the header button between pause and play."""
        self.is_paused = not self.is_paused
        self.pause_btn.set_glyph(icons.PLAY if self.is_paused else icons.PAUSE)
        self.pause_btn.setToolTip(
            "Resume monitoring" if self.is_paused else "Pause monitoring"
        )

    def _on_data_ready(self, data: MonitorData):
        """Handle a collector tick (main thread, via signal).

        Remembers the tick before rendering it, so `_apply_theme()` can
        re-render the very same data in the new palette without waiting for
        the next signal. While paused nothing is stored or drawn — the
        displayed data stays frozen, which is the point of pausing, and a
        theme flip still repaints it from `_last_data`.
        """
        if self.is_paused:
            return
        self._last_data = data
        self._render_data(data)
