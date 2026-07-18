"""
Settings Dialog - Simple and Working
"""

import sys
import winreg
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import psutil
from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QTimer
from PySide6.QtGui import QBrush, QFont, QIcon, QPainter, QPalette, QPen, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .monitor import MonitorMode
from .persistence import load_last_setup, save_last_setup
from .styles import Defaults, FontScale, MEMORY_UNITS, NETWORK_UNITS
from .color_management import ProcessColorManager


def get_base_path() -> Path:
    """Get base path for resources (handles PyInstaller frozen exe)."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent


# Name of both the HKCU Run value (dev mode) and the Task Scheduler task
# created by the installer (setup/installer.nsi APP_NAME) — they must match
# so the in-app toggle controls the same task the installer creates.
_STARTUP_APP_NAME = "PMUsage"
_STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _get_startup_exe_path() -> str:
    """Return the command to register in Windows startup."""
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'
    # Dev mode: use pythonw.exe to avoid a console window
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    main_py = Path(__file__).parent.parent / "main.py"
    return f'"{pythonw}" "{main_py}"'


def _run_schtasks(*args: str) -> int:
    """Run schtasks.exe without flashing a console window. Returns exit code."""
    import subprocess
    return subprocess.run(
        ["schtasks", *args],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ).returncode


def _delete_legacy_run_value() -> None:
    """Remove the HKCU Run entry left by pre-2.0.214 versions.

    Windows silently skips Run entries pointing to UAC-elevated exes,
    so for the frozen app this entry is dead weight at best.
    """
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE,
        )
        try:
            winreg.DeleteValue(key, _STARTUP_APP_NAME)
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except OSError as e:
        print(f"[PMUsage] Legacy Run cleanup failed: {e}", file=sys.stderr)


def is_startup_registered() -> bool:
    """Return True if the app autostarts with Windows.

    Frozen exe: checks the Task Scheduler task shared with the installer
    (Registry Run is silently skipped for UAC-elevated apps).
    Dev mode:   checks the HKCU Run registry entry.
    """
    if getattr(sys, 'frozen', False):
        return _run_schtasks("/query", "/tn", _STARTUP_APP_NAME) == 0
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STARTUP_REG_KEY)
        winreg.QueryValueEx(key, _STARTUP_APP_NAME)
        winreg.CloseKey(key)
        return True
    except OSError:
        return False


def set_startup_registered(enabled: bool) -> None:
    """Add or remove Windows autostart.

    Frozen exe: creates/deletes the same Task Scheduler task the installer
    manages (/rl highest, required for elevated apps) and cleans any legacy
    Run entry. Dev mode: uses the HKCU Run registry entry.
    Failures are reported to stderr but never crash the dialog.
    """
    if getattr(sys, 'frozen', False):
        _delete_legacy_run_value()
        if enabled:
            rc = _run_schtasks(
                "/create", "/tn", _STARTUP_APP_NAME,
                "/tr", _get_startup_exe_path(),
                "/sc", "onlogon", "/rl", "highest", "/f",
            )
            if rc != 0:
                print(f"[PMUsage] schtasks /create failed (exit {rc})", file=sys.stderr)
        elif is_startup_registered():
            rc = _run_schtasks("/delete", "/tn", _STARTUP_APP_NAME, "/f")
            if rc != 0:
                print(f"[PMUsage] schtasks /delete failed (exit {rc})", file=sys.stderr)
        return
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _STARTUP_REG_KEY,
            0, winreg.KEY_SET_VALUE,
        )
        if enabled:
            winreg.SetValueEx(key, _STARTUP_APP_NAME, 0, winreg.REG_SZ, _get_startup_exe_path())
        else:
            try:
                winreg.DeleteValue(key, _STARTUP_APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except OSError as e:
        print(f"[PMUsage] Startup registry update failed: {e}", file=sys.stderr)


def _save_last_setup(settings: 'InitialSettings') -> None:
    """Persist the last-used login settings to config/last_setup.json."""
    data = load_last_setup()
    data.update({
        "cpu_enabled": settings.cpu_enabled,
        "memory_enabled": settings.memory_enabled,
        "network_enabled": settings.network_enabled,
        "current_rows": settings.current_rows,
        "history_rows": settings.history_rows,
        "refresh_rate_ms": settings.refresh_rate_ms,
        "retention_minutes": settings.retention_minutes,
        "memory_unit": settings.memory_unit,
        "network_unit": settings.network_unit,
        "network_sort_mode": settings.network_sort_mode,
        "network_max_download_mbps": settings.network_max_download_mbps,
        "network_max_upload_mbps": settings.network_max_upload_mbps,
        "font_size": settings.font_size,
    })
    save_last_setup(data)


def _format_bytes_in_unit(total_bytes: int, unit: str) -> str:
    """Format a byte count in the user's selected memory unit (KB/MB/GB)."""
    divisor = MEMORY_UNITS[unit]
    value = total_bytes / divisor
    if unit == "GB":
        return f"{value:.1f} GB"
    return f"{round(value):,} {unit}"


_SPINBOX_STYLE = """
    QSpinBox {
        background-color: #3a3a4e; color: #ffffff;
        border: 1px solid #4a4a5e; border-radius: 4px;
        padding: 4px 8px;
    }
    QSpinBox::up-button, QSpinBox::down-button { width: 0px; }
"""


def _make_spinbox(default: int = 1) -> QSpinBox:
    """Create a styled numeric input (1–100) for row count settings."""
    sb = QSpinBox()
    sb.setRange(1, 100)
    sb.setValue(max(1, min(100, default)))
    sb.setFont(QFont("Segoe UI", 11))
    sb.setFixedHeight(32)
    sb.setFixedWidth(70)
    sb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sb.setStyleSheet(_SPINBOX_STYLE)
    return sb


# ---------------------------------------------------------------------------
# ColorScaleWidget — 4 draggable threshold handles on 5-color gradient bar
# ---------------------------------------------------------------------------

class ColorScaleWidget(QWidget):
    """
    Visual widget showing the 5-color gradient with 4 draggable threshold handles.

    Each diamond handle marks the boundary between adjacent color zones and is
    colored with its zone's color. Dragging adjusts where that transition occurs.
    """

    thresholds_changed = Signal(list)  # list of 4 int thresholds

    _BAR_Y = 10
    _BAR_H = 14
    _HANDLE_R = 7

    def __init__(
        self,
        colors: list,       # 5 QColors for the 5 zones
        thresholds: list,   # 4 int values in ascending order [t1, t2, t3, t4]
        parent: Optional[QWidget] = None,
        scale_max: int = 100,
    ):
        super().__init__(parent)
        self._colors = list(colors)
        self._thresholds = list(thresholds)
        self._scale_max = scale_max
        self._drag_idx: Optional[int] = None
        self.setMinimumHeight(56)
        self.setMouseTracking(True)

    # --- geometry helpers ---

    def _bar_x1(self) -> float:
        return float(self._HANDLE_R + 6)

    def _bar_x2(self) -> float:
        return float(self.width() - self._HANDLE_R - 6)

    def _bar_w(self) -> float:
        return self._bar_x2() - self._bar_x1()

    def _pct_to_x(self, pct: int) -> float:
        return self._bar_x1() + pct / self._scale_max * self._bar_w()

    def _x_to_pct(self, x: float) -> int:
        raw = (x - self._bar_x1()) / self._bar_w() * self._scale_max
        return max(0, min(self._scale_max, round(raw)))

    # --- painting ---

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bar_x1 = self._bar_x1()
        bar_y = float(self._BAR_Y)
        bar_h = float(self._BAR_H)
        bar_w = self._bar_w()

        # Draw 5 color segments
        pcts = [0] + self._thresholds + [self._scale_max]
        for i, color in enumerate(self._colors):
            x1 = bar_x1 + pcts[i] / self._scale_max * bar_w
            x2 = bar_x1 + pcts[i + 1] / self._scale_max * bar_w
            painter.fillRect(QRectF(x1, bar_y, max(x2 - x1, 0), bar_h), color)

        # Draw 4 diamond handles (each colored with the zone it ends)
        for i, t in enumerate(self._thresholds):
            x = self._pct_to_x(t)
            cy = bar_y + bar_h / 2
            r = float(self._HANDLE_R)
            zone_color = self._colors[i].lighter(150)
            painter.setBrush(QBrush(zone_color))
            painter.setPen(QPen(QColor("#ffffff"), 1.0))
            painter.drawConvexPolygon([
                QPointF(x,     cy - r),
                QPointF(x + r, cy),
                QPointF(x,     cy + r),
                QPointF(x - r, cy),
            ])

        # Percentage labels below handles
        painter.setPen(QColor("#aaaaaa"))
        painter.setFont(QFont("Segoe UI", 9))
        fm = painter.fontMetrics()
        for t in self._thresholds:
            label = f"{t}%"
            lw = fm.horizontalAdvance(label)
            lx = self._pct_to_x(t) - lw / 2
            lx = max(0.0, min(lx, float(self.width() - lw)))
            painter.drawText(QPointF(lx, bar_y + bar_h + 14), label)

    # --- mouse interaction ---

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x = event.position().x()
        hit_radius = self._HANDLE_R + 10
        best_idx = None
        best_dist = float('inf')
        for i, t in enumerate(self._thresholds):
            dist = abs(x - self._pct_to_x(t))
            if dist < hit_radius and dist < best_dist:
                best_dist = dist
                best_idx = i
        self._drag_idx = best_idx
        if best_idx is not None:
            self.setCursor(Qt.CursorShape.SizeHorCursor)

    def mouseMoveEvent(self, event):
        if self._drag_idx is None:
            return
        pct = self._x_to_pct(event.position().x())
        lo = (self._thresholds[self._drag_idx - 1] + 1) if self._drag_idx > 0 else 1
        hi = (self._thresholds[self._drag_idx + 1] - 1) if self._drag_idx < len(self._thresholds) - 1 else self._scale_max - 1
        self._thresholds[self._drag_idx] = max(lo, min(hi, pct))
        self.update()
        self.thresholds_changed.emit(list(self._thresholds))

    def mouseReleaseEvent(self, event):
        self._drag_idx = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    @property
    def thresholds(self) -> list:
        return list(self._thresholds)

    def set_thresholds(self, thresholds: list) -> None:
        """Update displayed thresholds (e.g. from saved settings) and repaint."""
        self._thresholds = list(thresholds)
        self.update()


# ---------------------------------------------------------------------------
# CompanyLegendDialog
# ---------------------------------------------------------------------------

class CompanyLegendDialog(QDialog):
    """Shows all detected companies and their assigned colors."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Company Color Legend")
        self.resize(340, 440)

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

        self._expanded: set[str] = set()

        self._setup_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1000)
        self._refresh_timer.timeout.connect(self._refresh_legend)
        self._refresh_timer.start()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Company Color Legend")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #2a2a3e; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #4a4a5e; border-radius: 4px; }
        """)
        self._rebuild_legend_content()
        layout.addWidget(self._scroll)

        note = QLabel("Colored = named company  ·  White = no company info")
        note.setFont(QFont("Segoe UI", 8))
        note.setStyleSheet("color: #555555; background: transparent;")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(note)

        # Hue color sliders
        sat_init, light_init = ProcessColorManager().get_hue_params()

        slider_style = """
            QSlider::groove:horizontal {
                height: 4px; background: #3a3a4e; border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 14px; height: 14px; margin: -5px 0;
                background: #e94560; border-radius: 7px;
            }
            QSlider::sub-page:horizontal { background: #e94560; border-radius: 2px; }
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
            lbl.setStyleSheet("color: #aaaaaa; background: transparent;")
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
            val_lbl.setStyleSheet("color: #aaaaaa; background: transparent;")
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
        close_btn.setStyleSheet("""
            QPushButton { background-color: #3a3a4e; color: #ffffff; border: none; border-radius: 6px; }
            QPushButton:hover { background-color: #4a4a5e; }
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _rebuild_legend_content(self):
        color_mgr = ProcessColorManager()
        legend = color_mgr.get_legend()
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
            toggle_style = """
                QPushButton {
                    background: transparent; color: #888888;
                    border: none; padding: 0;
                }
                QPushButton:hover { color: #ffffff; }
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
                name_lbl.setStyleSheet("color: #ffffff; background: transparent;")
                row.addWidget(name_lbl, 1)

                count_lbl = QLabel(str(proc_count))
                count_lbl.setFont(QFont("Segoe UI", 10))
                count_lbl.setStyleSheet("color: #666666; background: transparent;")
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
                        sub_lbl.setStyleSheet("color: #aaaaaa; background: transparent;")
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
        legend = ProcessColorManager().get_legend()
        current_key = [(c, n) for c, _, n in legend]
        cached_key = [(c, n) for c, _, n in self._legend_data] if self._legend_data else []
        if current_key != cached_key:
            self._rebuild_legend_content()

    def _on_hue_params_changed(self):
        sat = self._sat_slider.value() / 100.0
        light = self._light_slider.value() / 100.0
        self._sat_val.setText(f"{self._sat_slider.value()}%")
        self._light_val.setText(f"{self._light_slider.value()}%")
        ProcessColorManager().update_hue_params(sat, light)
        self._rebuild_legend_content()


# ---------------------------------------------------------------------------
# Helper: build color settings section into any layout
# ---------------------------------------------------------------------------

def _make_legend_btn() -> QPushButton:
    """Create a styled Company Legend button (shared by CPU and Memory dialogs)."""
    btn = QPushButton("Company Legend")
    btn.setFont(QFont("Segoe UI", 10))
    btn.setFixedHeight(28)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet("""
        QPushButton {
            background-color: #2a2a3e; color: #888888;
            border: 1px solid #3a3a4e; border-radius: 4px; padding: 0 12px;
        }
        QPushButton:hover { background-color: #3a3a4e; color: #ffffff; }
    """)
    return btn


def _build_color_section(
    layout: QVBoxLayout,
    make_label,
    show_legend: bool = True,
    mode: str = "cpu",
    title: str = "Color Settings",
    max_info: str = "",
    scale_max: int = 100,
) -> 'ColorScaleWidget':
    """
    Add Color Settings label, ColorScaleWidget, and optionally Legend button to layout.
    Returns the ColorScaleWidget so the caller can read thresholds on accept.

    Args:
        show_legend: If True, adds a Company Legend button below the scale.
        mode:        "cpu", "memory", or "memory_total".
        max_info:    If non-empty, shown right-aligned on the title row as "100% = <max_info>".
    """
    if max_info:
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.addWidget(make_label(title, 12, bold=True))
        title_row.addStretch()
        title_row.addWidget(make_label(f"100% = {max_info}", 9, color="#666666"))
        layout.addLayout(title_row)
    else:
        layout.addWidget(make_label(title, 12, bold=True))

    color_mgr = ProcessColorManager()
    value_ranges = color_mgr.get_value_ranges(mode)
    colors = [color for _, color in value_ranges]
    thresholds = [int(t) for t, _ in value_ranges[:-1]]  # first 4; last is always 100

    scale_widget = ColorScaleWidget(colors, thresholds, scale_max=scale_max)
    layout.addWidget(scale_widget)

    if show_legend:
        legend_row = QHBoxLayout()
        legend_row.addStretch()
        legend_btn = _make_legend_btn()
        scale_widget._legend_btn = legend_btn  # type: ignore[attr-defined]
        legend_row.addWidget(legend_btn)
        layout.addLayout(legend_row)
    else:
        scale_widget._legend_btn = None  # type: ignore[attr-defined]

    return scale_widget


# ---------------------------------------------------------------------------
# MonitorSettings / InitialSettings dataclasses
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
        return psutil.cpu_count()

    @property
    def ram_gb(self) -> int:
        return round(psutil.virtual_memory().total / (1024 ** 3))


@dataclass
class InitialSettings:
    """Settings from initial dialog (launcher)."""
    cpu_enabled: bool = True
    memory_enabled: bool = False
    network_enabled: bool = False
    current_rows: int = Defaults.CURRENT_ROWS
    history_rows: int = Defaults.HISTORY_ROWS
    refresh_rate_ms: int = Defaults.REFRESH_RATE_MS
    retention_minutes: int = Defaults.RETENTION_MINUTES
    memory_unit: str = Defaults.MEMORY_UNIT
    network_unit: str = Defaults.NETWORK_UNIT
    network_sort_mode: str = Defaults.NETWORK_SORT_MODE
    network_max_download_mbps: int = Defaults.NETWORK_MAX_DOWNLOAD_MBPS
    network_max_upload_mbps: int = Defaults.NETWORK_MAX_UPLOAD_MBPS
    font_size: int = Defaults.FONT_SIZE

    @property
    def cpu_threads(self) -> int:
        return psutil.cpu_count()

    @property
    def ram_gb(self) -> int:
        return round(psutil.virtual_memory().total / (1024 ** 3))

    @property
    def commit_limit_bytes(self) -> int:
        from .monitor import get_commit_limit_bytes
        return get_commit_limit_bytes()


# ---------------------------------------------------------------------------
# InitialSettingsDialog  (login screen)
# ---------------------------------------------------------------------------

class InitialSettingsDialog(QDialog):
    """Initial settings dialog with checkbox mode selection."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Process Monitor - Setup")
        self.resize(480, 560)

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

        self.net_btn = QPushButton("Network")
        self.net_btn.setFont(QFont("Segoe UI", 11))
        self.net_btn.setFixedHeight(36)
        self.net_btn.setCheckable(True)
        self.net_btn.setChecked(False)
        self.net_btn.clicked.connect(self._update_mode_buttons)
        mode_row.addWidget(self.net_btn)

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
        self.net_btn.setStyleSheet(inactive_style)

        layout.addLayout(mode_row)

        hint = self._make_label("Select one or more monitors", 9, color="#666666")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        layout.addSpacing(8)

        # Display Settings
        layout.addWidget(self._make_label("Display Settings", 12, bold=True))

        row1 = QHBoxLayout()
        row1.addWidget(self._make_label("Current processes:", 11, color="#aaaaaa"))
        row1.addStretch()
        self.current_spin = _make_spinbox(Defaults.CURRENT_ROWS)
        row1.addWidget(self.current_spin)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(self._make_label("History records:", 11, color="#aaaaaa"))
        row2.addStretch()
        self.history_spin = _make_spinbox(Defaults.HISTORY_ROWS)
        row2.addWidget(self.history_spin)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(self._make_label("Refresh rate:", 11, color="#aaaaaa"))
        row3.addStretch()
        self.refresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.refresh_slider.setRange(1, 10)
        self.refresh_slider.setValue(Defaults.REFRESH_RATE_MS // 500)
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
        self.refresh_slider.valueChanged.connect(lambda v: self.refresh_label.setText(f"{v * 500} ms"))
        row3.addWidget(self.refresh_label)
        layout.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(self._make_label("History retention:", 11, color="#aaaaaa"))
        row4.addStretch()
        self.retention_slider = QSlider(Qt.Orientation.Horizontal)
        self.retention_slider.setRange(1, 36)
        self.retention_slider.setValue(Defaults.RETENTION_MINUTES // 10)
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
        self.retention_slider.valueChanged.connect(lambda v: self.retention_label.setText(f"{v * 10} min"))
        row4.addWidget(self.retention_label)
        layout.addLayout(row4)

        # Font size
        row_font = QHBoxLayout()
        row_font.addWidget(self._make_label("Font size:", 11, color="#aaaaaa"))
        row_font.addStretch()
        self.font_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_slider.setRange(8, 18)
        self.font_slider.setValue(Defaults.FONT_SIZE)
        self.font_slider.setFixedWidth(140)
        self.font_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3a3a4e; border-radius: 3px; }
            QSlider::handle:horizontal { background: #e94560; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::sub-page:horizontal { background: #e94560; border-radius: 3px; }
        """)
        row_font.addWidget(self.font_slider)
        self.font_label = self._make_label(f"{Defaults.FONT_SIZE} pt", 11)
        self.font_label.setFixedWidth(65)
        self.font_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.font_slider.valueChanged.connect(lambda v: self.font_label.setText(f"{v} pt"))
        row_font.addWidget(self.font_label)
        layout.addLayout(row_font)

        layout.addSpacing(8)

        # Memory Settings
        layout.addWidget(self._make_label("Memory Settings", 12, bold=True))

        row5 = QHBoxLayout()
        row5.addWidget(self._make_label("Display unit:", 11, color="#aaaaaa"))
        row5.addStretch()
        self.unit_combo = self._make_combo(["KB", "MB", "GB"], Defaults.MEMORY_UNIT)
        row5.addWidget(self.unit_combo)
        layout.addLayout(row5)

        # Network Settings (visible when network is checked)
        self._net_settings_container = QWidget()
        self._net_settings_container.setStyleSheet("background: transparent;")
        net_layout = QVBoxLayout(self._net_settings_container)
        net_layout.setContentsMargins(0, 0, 0, 0)
        net_layout.setSpacing(8)

        net_layout.addWidget(self._make_label("Network Settings", 12, bold=True))

        row_net_unit = QHBoxLayout()
        row_net_unit.addWidget(self._make_label("Speed unit:", 11, color="#aaaaaa"))
        row_net_unit.addStretch()
        self.net_unit_combo = self._make_combo(["KB/s", "MB/s"], Defaults.NETWORK_UNIT)
        row_net_unit.addWidget(self.net_unit_combo)
        net_layout.addLayout(row_net_unit)

        row_net_sort = QHBoxLayout()
        row_net_sort.addWidget(self._make_label("Sort by:", 11, color="#aaaaaa"))
        row_net_sort.addStretch()
        self.net_sort_combo = self._make_combo(["total", "download", "upload"], Defaults.NETWORK_SORT_MODE)
        row_net_sort.addWidget(self.net_sort_combo)
        net_layout.addLayout(row_net_sort)

        # Auto-detect link speed for default
        from .network_monitor import get_link_speed_mbps
        link_speed = get_link_speed_mbps()

        row_net_dl = QHBoxLayout()
        row_net_dl.addWidget(self._make_label("Max download (Mbps):", 11, color="#aaaaaa"))
        row_net_dl.addStretch()
        self.net_dl_spin = QSpinBox()
        self.net_dl_spin.setRange(0, 100000)
        self.net_dl_spin.setValue(link_speed)
        self.net_dl_spin.setSpecialValueText("auto")
        self.net_dl_spin.setFont(QFont("Segoe UI", 11))
        self.net_dl_spin.setFixedHeight(32)
        self.net_dl_spin.setFixedWidth(100)
        self.net_dl_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.net_dl_spin.setStyleSheet(_SPINBOX_STYLE)
        row_net_dl.addWidget(self.net_dl_spin)
        net_layout.addLayout(row_net_dl)

        row_net_ul = QHBoxLayout()
        row_net_ul.addWidget(self._make_label("Max upload (Mbps):", 11, color="#aaaaaa"))
        row_net_ul.addStretch()
        self.net_ul_spin = QSpinBox()
        self.net_ul_spin.setRange(0, 100000)
        self.net_ul_spin.setValue(link_speed)
        self.net_ul_spin.setSpecialValueText("auto")
        self.net_ul_spin.setFont(QFont("Segoe UI", 11))
        self.net_ul_spin.setFixedHeight(32)
        self.net_ul_spin.setFixedWidth(100)
        self.net_ul_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.net_ul_spin.setStyleSheet(_SPINBOX_STYLE)
        row_net_ul.addWidget(self.net_ul_spin)
        net_layout.addLayout(row_net_ul)

        speed_hint = self._make_label(
            "0 = auto-detect from link speed. Test yours at speedtest.net", 9, color="#666666"
        )
        net_layout.addWidget(speed_hint)

        layout.addWidget(self._net_settings_container)
        self._net_settings_container.setVisible(False)

        # Start with Windows toggle
        startup_row = QHBoxLayout()
        startup_row.addWidget(self._make_label("Start with Windows:", 11, color="#aaaaaa"))
        startup_row.addStretch()
        self.startup_toggle = QPushButton()
        self.startup_toggle.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.startup_toggle.setFixedSize(52, 28)
        self.startup_toggle.setCheckable(True)
        self.startup_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.startup_toggle.clicked.connect(self._update_startup_toggle)
        startup_row.addWidget(self.startup_toggle)
        layout.addLayout(startup_row)

        # Init toggle from actual registry state (not from saved settings)
        self.startup_toggle.setChecked(is_startup_registered())
        self._update_startup_toggle()

        # System info
        cpu_threads = psutil.cpu_count()
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

        # Restore last session settings (no-op if file doesn't exist)
        self._apply_last_setup(load_last_setup())

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
        self.net_btn.setStyleSheet(active_style if self.net_btn.isChecked() else inactive_style)
        self._net_settings_container.setVisible(self.net_btn.isChecked())
        self.start_btn.setEnabled(
            self.cpu_btn.isChecked() or self.mem_btn.isChecked() or self.net_btn.isChecked()
        )

    def _update_startup_toggle(self):
        """Refresh startup toggle button style to match its checked state."""
        if self.startup_toggle.isChecked():
            self.startup_toggle.setText("ON")
            self.startup_toggle.setStyleSheet("""
                QPushButton { background-color: #e94560; color: white; border: none; border-radius: 6px; }
            """)
        else:
            self.startup_toggle.setText("OFF")
            self.startup_toggle.setStyleSheet("""
                QPushButton { background-color: #3a3a4e; color: #888888; border: none; border-radius: 6px; }
                QPushButton:hover { background-color: #4a4a5e; }
            """)

    def _on_start(self):
        if not self.cpu_btn.isChecked() and not self.mem_btn.isChecked() and not self.net_btn.isChecked():
            return
        set_startup_registered(self.startup_toggle.isChecked())
        _save_last_setup(self.get_settings())
        self.accept()

    def _apply_last_setup(self, saved: dict) -> None:
        """Apply saved settings to controls after _setup_ui is done."""
        if not saved:
            return
        if "cpu_enabled" in saved:
            self.cpu_btn.setChecked(bool(saved["cpu_enabled"]))
        if "memory_enabled" in saved:
            self.mem_btn.setChecked(bool(saved["memory_enabled"]))
        if "network_enabled" in saved:
            self.net_btn.setChecked(bool(saved["network_enabled"]))
        self._update_mode_buttons()
        if "current_rows" in saved:
            self.current_spin.setValue(int(saved["current_rows"]))
        if "history_rows" in saved:
            self.history_spin.setValue(int(saved["history_rows"]))
        if "refresh_rate_ms" in saved:
            self.refresh_slider.setValue(int(saved["refresh_rate_ms"]) // 500)
        if "retention_minutes" in saved:
            self.retention_slider.setValue(int(saved["retention_minutes"]) // 10)
        if "memory_unit" in saved:
            self.unit_combo.setCurrentText(saved["memory_unit"])
        if "network_unit" in saved:
            self.net_unit_combo.setCurrentText(saved["network_unit"])
        if "network_sort_mode" in saved:
            self.net_sort_combo.setCurrentText(saved["network_sort_mode"])
        if "network_max_download_mbps" in saved:
            self.net_dl_spin.setValue(int(saved["network_max_download_mbps"]))
        if "network_max_upload_mbps" in saved:
            self.net_ul_spin.setValue(int(saved["network_max_upload_mbps"]))
        if "font_size" in saved:
            self.font_slider.setValue(int(saved["font_size"]))

    def get_settings(self) -> InitialSettings:
        return InitialSettings(
            cpu_enabled=self.cpu_btn.isChecked(),
            memory_enabled=self.mem_btn.isChecked(),
            network_enabled=self.net_btn.isChecked(),
            current_rows=self.current_spin.value(),
            history_rows=self.history_spin.value(),
            refresh_rate_ms=self.refresh_slider.value() * 500,
            retention_minutes=self.retention_slider.value() * 10,
            memory_unit=self.unit_combo.currentText(),
            network_unit=self.net_unit_combo.currentText(),
            network_sort_mode=self.net_sort_combo.currentText(),
            network_max_download_mbps=self.net_dl_spin.value(),
            network_max_upload_mbps=self.net_ul_spin.value(),
            font_size=self.font_slider.value(),
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
    font_size: int = Defaults.FONT_SIZE


@dataclass
class MemorySettings:
    """Settings for Memory window only."""
    current_rows: int = Defaults.CURRENT_ROWS
    history_rows: int = Defaults.HISTORY_ROWS
    refresh_rate_ms: int = Defaults.REFRESH_RATE_MS
    retention_minutes: int = Defaults.RETENTION_MINUTES
    memory_unit: str = Defaults.MEMORY_UNIT
    font_size: int = Defaults.FONT_SIZE


# ---------------------------------------------------------------------------
# CPUSettingsDialog
# ---------------------------------------------------------------------------

class CPUSettingsDialog(QDialog):
    """Settings dialog for CPU window (no mode selection, no memory unit)."""

    def __init__(self, parent: Optional[QWidget] = None, settings: Optional[CPUSettings] = None):
        super().__init__(parent)
        self.settings = settings or CPUSettings()
        self.setWindowTitle("CPU Monitor - Settings")
        self.resize(400, 600)

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
        self.current_spin = _make_spinbox(Defaults.CURRENT_ROWS)
        row1.addWidget(self.current_spin)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(self._make_label("History records:", 11, color="#aaaaaa"))
        row2.addStretch()
        self.history_spin = _make_spinbox(Defaults.HISTORY_ROWS)
        row2.addWidget(self.history_spin)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(self._make_label("Refresh rate:", 11, color="#aaaaaa"))
        row3.addStretch()
        self.refresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.refresh_slider.setRange(1, 10)
        self.refresh_slider.setValue(Defaults.REFRESH_RATE_MS // 500)
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
        self.refresh_slider.valueChanged.connect(lambda v: self.refresh_label.setText(f"{v * 500} ms"))
        row3.addWidget(self.refresh_label)
        layout.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(self._make_label("History retention:", 11, color="#aaaaaa"))
        row4.addStretch()
        self.retention_slider = QSlider(Qt.Orientation.Horizontal)
        self.retention_slider.setRange(1, 36)
        self.retention_slider.setValue(Defaults.RETENTION_MINUTES // 10)
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
        self.retention_slider.valueChanged.connect(lambda v: self.retention_label.setText(f"{v * 10} min"))
        row4.addWidget(self.retention_label)
        layout.addLayout(row4)

        # Font size
        row_font = QHBoxLayout()
        row_font.addWidget(self._make_label("Font size:", 11, color="#aaaaaa"))
        row_font.addStretch()
        self.font_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_slider.setRange(8, 18)
        self.font_slider.setValue(Defaults.FONT_SIZE)
        self.font_slider.setFixedWidth(140)
        self.font_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3a3a4e; border-radius: 3px; }
            QSlider::handle:horizontal { background: #e94560; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::sub-page:horizontal { background: #e94560; border-radius: 3px; }
        """)
        row_font.addWidget(self.font_slider)
        self.font_label = self._make_label(f"{Defaults.FONT_SIZE} pt", 11)
        self.font_label.setFixedWidth(65)
        self.font_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.font_slider.valueChanged.connect(lambda v: self.font_label.setText(f"{v} pt"))
        row_font.addWidget(self.font_label)
        layout.addLayout(row_font)

        # Color Settings — all sections in one compact container (4px spacing)
        color_container = QWidget()
        color_container.setStyleSheet("background: transparent;")
        cc_layout = QVBoxLayout(color_container)
        cc_layout.setContentsMargins(0, 0, 0, 0)
        cc_layout.setSpacing(4)

        cpu_threads = psutil.cpu_count()
        self._color_scale = _build_color_section(
            cc_layout, self._make_label, mode="cpu",
            max_info=f"{cpu_threads * 100}%",
            show_legend=False,
            scale_max=50,
        )
        self._color_scale_all = _build_color_section(
            cc_layout, self._make_label, mode="cpu_all",
            title="All Usage Color Settings",
            max_info=f"{cpu_threads * 100}%",
        )
        self._color_scale_all._legend_btn.clicked.connect(self._show_legend)
        layout.addWidget(color_container)

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
        ProcessColorManager().update_value_thresholds(self._color_scale.thresholds, "cpu")
        ProcessColorManager().update_value_thresholds(self._color_scale_all.thresholds, "cpu_all")
        super().accept()

    def _load_settings(self):
        self.current_spin.setValue(self.settings.current_rows)
        self.history_spin.setValue(self.settings.history_rows)
        self.refresh_slider.setValue(self.settings.refresh_rate_ms // 500)
        self.retention_slider.setValue(self.settings.retention_minutes // 10)
        self.font_slider.setValue(self.settings.font_size)

    def get_settings(self) -> CPUSettings:
        return CPUSettings(
            current_rows=self.current_spin.value(),
            history_rows=self.history_spin.value(),
            refresh_rate_ms=self.refresh_slider.value() * 500,
            retention_minutes=self.retention_slider.value() * 10,
            font_size=self.font_slider.value(),
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
        self.resize(400, 900)

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
        self.current_spin = _make_spinbox(Defaults.CURRENT_ROWS)
        row1.addWidget(self.current_spin)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(self._make_label("History records:", 11, color="#aaaaaa"))
        row2.addStretch()
        self.history_spin = _make_spinbox(Defaults.HISTORY_ROWS)
        row2.addWidget(self.history_spin)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(self._make_label("Refresh rate:", 11, color="#aaaaaa"))
        row3.addStretch()
        self.refresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.refresh_slider.setRange(1, 10)
        self.refresh_slider.setValue(Defaults.REFRESH_RATE_MS // 500)
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
        self.refresh_slider.valueChanged.connect(lambda v: self.refresh_label.setText(f"{v * 500} ms"))
        row3.addWidget(self.refresh_label)
        layout.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(self._make_label("History retention:", 11, color="#aaaaaa"))
        row4.addStretch()
        self.retention_slider = QSlider(Qt.Orientation.Horizontal)
        self.retention_slider.setRange(1, 36)
        self.retention_slider.setValue(Defaults.RETENTION_MINUTES // 10)
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
        self.retention_slider.valueChanged.connect(lambda v: self.retention_label.setText(f"{v * 10} min"))
        row4.addWidget(self.retention_label)
        layout.addLayout(row4)

        # Font size
        row_font = QHBoxLayout()
        row_font.addWidget(self._make_label("Font size:", 11, color="#aaaaaa"))
        row_font.addStretch()
        self.font_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_slider.setRange(8, 18)
        self.font_slider.setValue(Defaults.FONT_SIZE)
        self.font_slider.setFixedWidth(140)
        self.font_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3a3a4e; border-radius: 3px; }
            QSlider::handle:horizontal { background: #e94560; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::sub-page:horizontal { background: #e94560; border-radius: 3px; }
        """)
        row_font.addWidget(self.font_slider)
        self.font_label = self._make_label(f"{Defaults.FONT_SIZE} pt", 11)
        self.font_label.setFixedWidth(65)
        self.font_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.font_slider.valueChanged.connect(lambda v: self.font_label.setText(f"{v} pt"))
        row_font.addWidget(self.font_label)
        layout.addLayout(row_font)

        layout.addWidget(self._make_label("Memory Settings", 12, bold=True))
        row5 = QHBoxLayout()
        row5.addWidget(self._make_label("Display unit:", 11, color="#aaaaaa"))
        row5.addStretch()
        self.unit_combo = self._make_combo(["KB", "MB", "GB"], "MB")
        row5.addWidget(self.unit_combo)
        layout.addLayout(row5)

        # Color Settings — all sections in one compact container (4px spacing)
        color_container = QWidget()
        color_container.setStyleSheet("background: transparent;")
        cc_layout = QVBoxLayout(color_container)
        cc_layout.setContentsMargins(0, 0, 0, 0)
        cc_layout.setSpacing(4)

        unit = self.settings.memory_unit
        ram_bytes = psutil.virtual_memory().total
        from .monitor import get_commit_limit_bytes
        commit_limit_bytes = get_commit_limit_bytes()

        self._color_scale_usage = _build_color_section(
            cc_layout, self._make_label, mode="memory", show_legend=False,
            title="Usage Color Settings", max_info=_format_bytes_in_unit(ram_bytes, unit),
            scale_max=50,
        )
        self._color_scale_total = _build_color_section(
            cc_layout, self._make_label, mode="memory_total", show_legend=False,
            title="Commit Color Settings", max_info=_format_bytes_in_unit(commit_limit_bytes, unit),
            scale_max=50,
        )
        self._color_scale_all_usage = _build_color_section(
            cc_layout, self._make_label, mode="memory_all", show_legend=False,
            title="All Usage Color Settings", max_info=_format_bytes_in_unit(ram_bytes, unit),
        )
        self._color_scale_all_total = _build_color_section(
            cc_layout, self._make_label, mode="memory_all_total", show_legend=False,
            title="All Commit Color Settings", max_info=_format_bytes_in_unit(commit_limit_bytes, unit),
        )

        legend_row = QHBoxLayout()
        legend_row.addStretch()
        legend_btn = _make_legend_btn()
        legend_btn.clicked.connect(self._show_legend)
        legend_row.addWidget(legend_btn)
        cc_layout.addLayout(legend_row)
        layout.addWidget(color_container)

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
        ProcessColorManager().update_value_thresholds(self._color_scale_usage.thresholds, "memory")
        ProcessColorManager().update_value_thresholds(self._color_scale_total.thresholds, "memory_total")
        ProcessColorManager().update_value_thresholds(self._color_scale_all_usage.thresholds, "memory_all")
        ProcessColorManager().update_value_thresholds(self._color_scale_all_total.thresholds, "memory_all_total")
        super().accept()

    def _load_settings(self):
        self.current_spin.setValue(self.settings.current_rows)
        self.history_spin.setValue(self.settings.history_rows)
        self.refresh_slider.setValue(self.settings.refresh_rate_ms // 500)
        self.retention_slider.setValue(self.settings.retention_minutes // 10)
        self.unit_combo.setCurrentText(self.settings.memory_unit)
        self.font_slider.setValue(self.settings.font_size)

    def get_settings(self) -> MemorySettings:
        return MemorySettings(
            current_rows=self.current_spin.value(),
            history_rows=self.history_spin.value(),
            refresh_rate_ms=self.refresh_slider.value() * 500,
            retention_minutes=self.retention_slider.value() * 10,
            memory_unit=self.unit_combo.currentText(),
            font_size=self.font_slider.value(),
        )


# ---------------------------------------------------------------------------
# NetworkSettings / NetworkSettingsDialog
# ---------------------------------------------------------------------------

@dataclass
class NetworkSettings:
    """Settings for Network window only."""
    current_rows: int = Defaults.CURRENT_ROWS
    history_rows: int = Defaults.HISTORY_ROWS
    refresh_rate_ms: int = Defaults.REFRESH_RATE_MS
    retention_minutes: int = Defaults.RETENTION_MINUTES
    network_unit: str = Defaults.NETWORK_UNIT
    sort_mode: str = Defaults.NETWORK_SORT_MODE
    max_download_mbps: int = Defaults.NETWORK_MAX_DOWNLOAD_MBPS
    max_upload_mbps: int = Defaults.NETWORK_MAX_UPLOAD_MBPS
    font_size: int = Defaults.FONT_SIZE


class NetworkSettingsDialog(QDialog):
    """Settings dialog for Network window."""

    def __init__(self, parent: Optional[QWidget] = None, settings: Optional[NetworkSettings] = None):
        super().__init__(parent)
        self.settings = settings or NetworkSettings()
        self.setWindowTitle("Network Monitor - Settings")
        self.resize(400, 700)

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

        title = self._make_label("Network Monitor Settings", 16, bold=True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(12)

        # Display settings
        row1 = QHBoxLayout()
        row1.addWidget(self._make_label("Current processes:", 11, color="#aaaaaa"))
        row1.addStretch()
        self.current_spin = _make_spinbox(Defaults.CURRENT_ROWS)
        row1.addWidget(self.current_spin)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(self._make_label("History records:", 11, color="#aaaaaa"))
        row2.addStretch()
        self.history_spin = _make_spinbox(Defaults.HISTORY_ROWS)
        row2.addWidget(self.history_spin)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(self._make_label("Refresh rate:", 11, color="#aaaaaa"))
        row3.addStretch()
        self.refresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.refresh_slider.setRange(1, 10)
        self.refresh_slider.setValue(Defaults.REFRESH_RATE_MS // 500)
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
        self.refresh_slider.valueChanged.connect(lambda v: self.refresh_label.setText(f"{v * 500} ms"))
        row3.addWidget(self.refresh_label)
        layout.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(self._make_label("History retention:", 11, color="#aaaaaa"))
        row4.addStretch()
        self.retention_slider = QSlider(Qt.Orientation.Horizontal)
        self.retention_slider.setRange(1, 36)
        self.retention_slider.setValue(Defaults.RETENTION_MINUTES // 10)
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
        self.retention_slider.valueChanged.connect(lambda v: self.retention_label.setText(f"{v * 10} min"))
        row4.addWidget(self.retention_label)
        layout.addLayout(row4)

        # Font size
        row_font = QHBoxLayout()
        row_font.addWidget(self._make_label("Font size:", 11, color="#aaaaaa"))
        row_font.addStretch()
        self.font_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_slider.setRange(8, 18)
        self.font_slider.setValue(Defaults.FONT_SIZE)
        self.font_slider.setFixedWidth(140)
        self.font_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #3a3a4e; border-radius: 3px; }
            QSlider::handle:horizontal { background: #e94560; width: 16px; margin: -5px 0; border-radius: 8px; }
            QSlider::sub-page:horizontal { background: #e94560; border-radius: 3px; }
        """)
        row_font.addWidget(self.font_slider)
        self.font_label = self._make_label(f"{Defaults.FONT_SIZE} pt", 11)
        self.font_label.setFixedWidth(65)
        self.font_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.font_slider.valueChanged.connect(lambda v: self.font_label.setText(f"{v} pt"))
        row_font.addWidget(self.font_label)
        layout.addLayout(row_font)

        # Network-specific settings
        layout.addWidget(self._make_label("Network Settings", 12, bold=True))

        row_unit = QHBoxLayout()
        row_unit.addWidget(self._make_label("Speed unit:", 11, color="#aaaaaa"))
        row_unit.addStretch()
        self.unit_combo = self._make_combo(["KB/s", "MB/s"], Defaults.NETWORK_UNIT)
        row_unit.addWidget(self.unit_combo)
        layout.addLayout(row_unit)

        row_sort = QHBoxLayout()
        row_sort.addWidget(self._make_label("Sort by:", 11, color="#aaaaaa"))
        row_sort.addStretch()
        self.sort_combo = self._make_combo(["total", "download", "upload"], Defaults.NETWORK_SORT_MODE)
        row_sort.addWidget(self.sort_combo)
        layout.addLayout(row_sort)

        row_dl = QHBoxLayout()
        row_dl.addWidget(self._make_label("Max download (Mbps):", 11, color="#aaaaaa"))
        row_dl.addStretch()
        self.dl_spin = QSpinBox()
        self.dl_spin.setRange(0, 100000)
        self.dl_spin.setSpecialValueText("auto")
        self.dl_spin.setFont(QFont("Segoe UI", 11))
        self.dl_spin.setFixedHeight(32)
        self.dl_spin.setFixedWidth(100)
        self.dl_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dl_spin.setStyleSheet(_SPINBOX_STYLE)
        row_dl.addWidget(self.dl_spin)
        layout.addLayout(row_dl)

        row_ul = QHBoxLayout()
        row_ul.addWidget(self._make_label("Max upload (Mbps):", 11, color="#aaaaaa"))
        row_ul.addStretch()
        self.ul_spin = QSpinBox()
        self.ul_spin.setRange(0, 100000)
        self.ul_spin.setSpecialValueText("auto")
        self.ul_spin.setFont(QFont("Segoe UI", 11))
        self.ul_spin.setFixedHeight(32)
        self.ul_spin.setFixedWidth(100)
        self.ul_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ul_spin.setStyleSheet(_SPINBOX_STYLE)
        row_ul.addWidget(self.ul_spin)
        layout.addLayout(row_ul)

        speed_hint = self._make_label(
            "0 = auto-detect from link speed. Test yours at speedtest.net", 9, color="#666666"
        )
        layout.addWidget(speed_hint)

        # Color Settings
        color_container = QWidget()
        color_container.setStyleSheet("background: transparent;")
        cc_layout = QVBoxLayout(color_container)
        cc_layout.setContentsMargins(0, 0, 0, 0)
        cc_layout.setSpacing(4)

        self._color_scale_dl = _build_color_section(
            cc_layout, self._make_label, mode="net_dl", show_legend=False,
            title="Download Color Settings",
        )
        self._color_scale_ul = _build_color_section(
            cc_layout, self._make_label, mode="net_ul", show_legend=False,
            title="Upload Color Settings",
        )

        legend_row = QHBoxLayout()
        legend_row.addStretch()
        legend_btn = _make_legend_btn()
        legend_btn.clicked.connect(self._show_legend)
        legend_row.addWidget(legend_btn)
        cc_layout.addLayout(legend_row)
        layout.addWidget(color_container)

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
        ProcessColorManager().update_value_thresholds(self._color_scale_dl.thresholds, "net_dl")
        ProcessColorManager().update_value_thresholds(self._color_scale_ul.thresholds, "net_ul")
        super().accept()

    def _load_settings(self):
        self.current_spin.setValue(self.settings.current_rows)
        self.history_spin.setValue(self.settings.history_rows)
        self.refresh_slider.setValue(self.settings.refresh_rate_ms // 500)
        self.retention_slider.setValue(self.settings.retention_minutes // 10)
        self.font_slider.setValue(self.settings.font_size)
        self.unit_combo.setCurrentText(self.settings.network_unit)
        self.sort_combo.setCurrentText(self.settings.sort_mode)
        self.dl_spin.setValue(self.settings.max_download_mbps)
        self.ul_spin.setValue(self.settings.max_upload_mbps)

    def get_settings(self) -> NetworkSettings:
        return NetworkSettings(
            current_rows=self.current_spin.value(),
            history_rows=self.history_spin.value(),
            refresh_rate_ms=self.refresh_slider.value() * 500,
            retention_minutes=self.retention_slider.value() * 10,
            network_unit=self.unit_combo.currentText(),
            sort_mode=self.sort_combo.currentText(),
            max_download_mbps=self.dl_spin.value(),
            max_upload_mbps=self.ul_spin.value(),
            font_size=self.font_slider.value(),
        )
