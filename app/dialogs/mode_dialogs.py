"""The three per-monitor settings dialogs.

CPU, Memory and Network each open their own dialog from the gear button in
their window header. All three are the same shape — the shared rows from
`BaseSettingsDialog`, then the color scales that mode owns, then Apply — so
they live together: reading one means reading the family.

What differs is exactly the per-mode part: which color scales exist, what
"100%" means on each of them, and which extra controls the mode needs
(Memory's display unit, Network's unit/sort/max-speed block).

Each dialog is constructed with the THEME SCOPE of the window that opened it,
so the CPU dialog can be dark while the Memory one is light. They are modal
and cannot see a flip, which is why they style once instead of registering
for `changed`.
"""

from typing import Optional

import psutil
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ..color_management import ProcessColorManager
from ..settings import CPUSettings, MemorySettings, NetworkSettings
from ..styles import MEMORY_UNITS
from ..theme import ThemeScope
from .base_dialog import BaseSettingsDialog
from .dialog_styles import apply_button_style


# ═══════════════════════════════ HELPERS ═══════════════════════════════

def _format_bytes_in_unit(total_bytes: int, unit: str) -> str:
    """Format a byte count in the user's selected memory unit (KB/MB/GB)."""
    divisor = MEMORY_UNITS[unit]
    value = total_bytes / divisor
    if unit == "GB":
        return f"{value:.1f} GB"
    return f"{round(value):,} {unit}"


# ════════════════════════════ CPU SETTINGS ════════════════════════════

class CPUSettingsDialog(BaseSettingsDialog):
    """Settings dialog for CPU window (no mode selection, no memory unit)."""

    def __init__(
        self,
        scope: ThemeScope,
        parent: Optional[QWidget] = None,
        settings: Optional[CPUSettings] = None,
    ):
        super().__init__(scope, parent)
        self.settings = settings or CPUSettings()
        self.setWindowTitle("CPU - Settings")
        self.resize(400, 600)

        self._apply_theme()

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 24, 32, 24)

        title = self._make_label("CPU Settings", 16, bold=True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(12)

        (
            self.current_spin, self.history_spin, self.refresh_slider, self.refresh_label,
            self.retention_slider, self.retention_label, self.font_slider, self.font_label,
        ) = self._build_common_settings_rows(layout)

        # Color Settings — all sections in one compact container (4px spacing)
        color_container = QWidget()
        color_container.setStyleSheet("background: transparent;")
        cc_layout = QVBoxLayout(color_container)
        cc_layout.setContentsMargins(0, 0, 0, 0)
        cc_layout.setSpacing(4)

        cpu_threads = psutil.cpu_count()
        self._color_scale = self._build_color_section(
            cc_layout, mode="cpu",
            max_info=f"{cpu_threads * 100}%",
            show_legend=False,
            scale_max=50,
        )
        self._color_scale_all = self._build_color_section(
            cc_layout, mode="cpu_all",
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
        self._themed_sheet(self.apply_btn, apply_button_style)
        self.apply_btn.clicked.connect(self.accept)
        layout.addWidget(self.apply_btn)

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


# ══════════════════════════ MEMORY SETTINGS ══════════════════════════

class MemorySettingsDialog(BaseSettingsDialog):
    """Settings dialog for Memory window (no mode selection, has memory unit)."""

    def __init__(
        self,
        scope: ThemeScope,
        parent: Optional[QWidget] = None,
        settings: Optional[MemorySettings] = None,
    ):
        super().__init__(scope, parent)
        self.settings = settings or MemorySettings()
        self.setWindowTitle("Memory - Settings")
        self.resize(400, 900)

        self._apply_theme()

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 24, 32, 24)

        title = self._make_label("Memory Settings", 16, bold=True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(12)

        (
            self.current_spin, self.history_spin, self.refresh_slider, self.refresh_label,
            self.retention_slider, self.retention_label, self.font_slider, self.font_label,
        ) = self._build_common_settings_rows(layout)

        layout.addWidget(self._make_label("Memory Settings", 12, bold=True))
        row5 = QHBoxLayout()
        row5.addWidget(self._make_label("Display unit:", 11, color="TEXT_MUTED"))
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
        from ..collect.system_query import get_commit_limit_bytes
        commit_limit_bytes = get_commit_limit_bytes()

        self._color_scale_usage = self._build_color_section(
            cc_layout, mode="memory", show_legend=False,
            title="Usage Color Settings", max_info=_format_bytes_in_unit(ram_bytes, unit),
            scale_max=50,
        )
        self._color_scale_total = self._build_color_section(
            cc_layout, mode="memory_total", show_legend=False,
            title="Commit Color Settings", max_info=_format_bytes_in_unit(commit_limit_bytes, unit),
            scale_max=50,
        )
        self._color_scale_all_usage = self._build_color_section(
            cc_layout, mode="memory_all", show_legend=False,
            title="All Usage Color Settings", max_info=_format_bytes_in_unit(ram_bytes, unit),
        )
        self._color_scale_all_total = self._build_color_section(
            cc_layout, mode="memory_all_total", show_legend=False,
            title="All Commit Color Settings", max_info=_format_bytes_in_unit(commit_limit_bytes, unit),
        )

        legend_row = QHBoxLayout()
        legend_row.addStretch()
        legend_btn = self._make_legend_btn()
        legend_btn.clicked.connect(self._show_legend)
        legend_row.addWidget(legend_btn)
        cc_layout.addLayout(legend_row)
        layout.addWidget(color_container)

        layout.addStretch()

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.apply_btn.setFixedHeight(44)
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._themed_sheet(self.apply_btn, apply_button_style)
        self.apply_btn.clicked.connect(self.accept)
        layout.addWidget(self.apply_btn)

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


# ══════════════════════════ NETWORK SETTINGS ══════════════════════════

class NetworkSettingsDialog(BaseSettingsDialog):
    """Settings dialog for Network window."""

    def __init__(
        self,
        scope: ThemeScope,
        parent: Optional[QWidget] = None,
        settings: Optional[NetworkSettings] = None,
    ):
        super().__init__(scope, parent)
        self.settings = settings or NetworkSettings()
        self.setWindowTitle("Network - Settings")
        self.resize(400, 700)

        self._apply_theme()

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(32, 24, 32, 24)

        title = self._make_label("Network Settings", 16, bold=True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(12)

        # Display settings
        (
            self.current_spin, self.history_spin, self.refresh_slider, self.refresh_label,
            self.retention_slider, self.retention_label, self.font_slider, self.font_label,
        ) = self._build_common_settings_rows(layout)

        # Network-specific settings
        (
            self.unit_combo, self.sort_combo, self.dl_spin, self.ul_spin,
        ) = self._build_network_settings_rows(layout)

        # Color Settings
        color_container = QWidget()
        color_container.setStyleSheet("background: transparent;")
        cc_layout = QVBoxLayout(color_container)
        cc_layout.setContentsMargins(0, 0, 0, 0)
        cc_layout.setSpacing(4)

        self._color_scale_dl = self._build_color_section(
            cc_layout, mode="net_dl", show_legend=False,
            title="Download Color Settings",
        )
        self._color_scale_ul = self._build_color_section(
            cc_layout, mode="net_ul", show_legend=False,
            title="Upload Color Settings",
        )

        legend_row = QHBoxLayout()
        legend_row.addStretch()
        legend_btn = self._make_legend_btn()
        legend_btn.clicked.connect(self._show_legend)
        legend_row.addWidget(legend_btn)
        cc_layout.addLayout(legend_row)
        layout.addWidget(color_container)

        layout.addStretch()

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.apply_btn.setFixedHeight(44)
        self.apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._themed_sheet(self.apply_btn, apply_button_style)
        self.apply_btn.clicked.connect(self.accept)
        layout.addWidget(self.apply_btn)

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
