"""InitialSettingsDialog — the setup screen.

The app's front door and its one place to configure everything: which
monitors open, rows, refresh rate, retention, units, fonts, network options
and Start-with-Windows. Shown once at launch and again from the tray's
**Settings**, so one edit reaches all three monitors.

It is also the only settings surface that carries a Day/Night switch, and
that switch is the GLOBAL one: a monitor window's header switch flips that
window alone, this one flips the app scope and forces the same theme on every
window. That is why this dialog restyles live and the per-mode ones do not.
"""

from typing import Optional

import psutil
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ..persistence import load_last_setup
from ..settings import InitialSettings, save_initial_settings
from ..startup import is_startup_registered, set_startup_registered
from ..styles import Defaults
from ..theme import app_theme
from ..theme_switch import DayNightSwitch
from ..transition import flip_app_theme
from .base_dialog import BaseSettingsDialog
from .dialog_styles import mode_button_style, start_button_style


# ═══════════════════════════ THE SETUP SCREEN ═══════════════════════════

class InitialSettingsDialog(BaseSettingsDialog):
    """The setup screen — every window's settings in one place.

    Shown once at startup, and again from the tray's **Settings** action so
    all three monitors can be configured together without hunting through
    three per-window dialogs (owner 2026-07-24).

    Unlike the per-mode dialogs this one carries a Day/Night switch, so it
    restyles live: it is the screen the user meets before any window exists,
    and the theme has to be changeable there.

    Its switch is the GLOBAL one (owner 2026-07-26). A monitor window's
    header switch flips that window alone; this one flips the app scope and
    forces the same theme on all three monitors — that is the whole reason
    the setup screen still owns a switch now that each window has its own.
    """

    def __init__(self, parent: Optional[QWidget] = None, first_run: bool = True):
        super().__init__(app_theme(), parent)
        self.setWindowTitle("Vitals - Setup")
        self.resize(480, 600)
        self._first_run = first_run

        self._apply_theme()

        self._setup_ui()
        self._theme.changed.connect(self._apply_theme)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 24, 32, 24)

        # Title row — the Day/Night switch sits beside the app name so the
        # theme can be set before any monitor window exists.
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.addStretch()
        title = self._make_label("Vitals", 20, bold=True)
        title_row.addWidget(title)
        title_row.addStretch()
        self.theme_switch = DayNightSwitch(self._theme, flip_app_theme)
        self.theme_switch.setToolTip(
            "Switch every monitor window between dark and light theme"
        )
        title_row.addWidget(self.theme_switch, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(title_row)

        subtitle = self._make_label(
            "Select monitors to open" if self._first_run
            else "Settings apply to every monitor window",
            10, color="TEXT_DIM",
        )
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

        layout.addLayout(mode_row)

        hint = self._make_label("Select one or more monitors", 9, color="TEXT_FAINT")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        layout.addSpacing(8)

        # Display Settings
        layout.addWidget(self._make_label("Display Settings", 12, bold=True))

        (
            self.current_spin, self.history_spin, self.refresh_slider, self.refresh_label,
            self.retention_slider, self.retention_label, self.font_slider, self.font_label,
        ) = self._build_common_settings_rows(layout)

        layout.addSpacing(8)

        # Memory Settings
        layout.addWidget(self._make_label("Memory Settings", 12, bold=True))

        row5 = QHBoxLayout()
        row5.addWidget(self._make_label("Display unit:", 11, color="TEXT_MUTED"))
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

        # Auto-detect link speed for default
        from ..collect.network_trace import get_link_speed_mbps
        link_speed = get_link_speed_mbps()

        (
            self.net_unit_combo, self.net_sort_combo, self.net_dl_spin, self.net_ul_spin,
        ) = self._build_network_settings_rows(net_layout, default_speed_mbps=link_speed)

        layout.addWidget(self._net_settings_container)
        self._net_settings_container.setVisible(False)

        # Start with Windows toggle
        startup_row = QHBoxLayout()
        startup_row.addWidget(self._make_label("Start with Windows:", 11, color="TEXT_MUTED"))
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

        # System info
        cpu_threads = psutil.cpu_count()
        ram_gb = round(psutil.virtual_memory().total / (1024 ** 3))
        info_label = self._make_label(
            f"Detected: {cpu_threads} CPU threads, {ram_gb} GB RAM", 10, color="TEXT_FAINT"
        )
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_label)

        layout.addStretch()

        self.start_btn = QPushButton(
            "Start Monitoring" if self._first_run else "Apply"
        )
        self.start_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.start_btn.setFixedHeight(44)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._themed_sheet(self.start_btn, start_button_style)
        self.start_btn.clicked.connect(self._on_start)
        layout.addWidget(self.start_btn)

        # Both toggles carry a checked/unchecked style, so the method that
        # repaints them on a click IS their restyler. Registered last: they
        # touch widgets built further down this method.
        self._register_restyle(self._update_mode_buttons)
        self._register_restyle(self._update_startup_toggle)

        # Restore last session settings (no-op if file doesn't exist)
        self._apply_last_setup(load_last_setup())

    def _update_mode_buttons(self):
        palette = self._theme.palette
        for btn in (self.cpu_btn, self.mem_btn, self.net_btn):
            btn.setStyleSheet(mode_button_style(palette, btn.isChecked()))
        self._net_settings_container.setVisible(self.net_btn.isChecked())
        self.start_btn.setEnabled(
            self.cpu_btn.isChecked() or self.mem_btn.isChecked() or self.net_btn.isChecked()
        )

    def _update_startup_toggle(self):
        """Refresh startup toggle button style to match its checked state."""
        checked = self.startup_toggle.isChecked()
        self.startup_toggle.setText("ON" if checked else "OFF")
        self.startup_toggle.setStyleSheet(
            mode_button_style(self._theme.palette, checked)
        )

    def _on_start(self):
        if not self.cpu_btn.isChecked() and not self.mem_btn.isChecked() and not self.net_btn.isChecked():
            return
        set_startup_registered(self.startup_toggle.isChecked())
        save_initial_settings(self.get_settings())
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
