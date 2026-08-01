"""BaseSettingsDialog — the shared scaffolding every settings dialog is built on.

Holds what the setup screen and the three per-monitor dialogs have in common:
theme binding, the window icon, the label/combo/spinbox factories, and the
row builders for the settings blocks that would otherwise be written four
times (root rule: no duplicate code).

The restyler mechanism lives here too. Every widget these factories create
registers a closure that rebuilds its stylesheet from `self._theme.palette`;
`_apply_theme()` runs them all, so a dialog can follow a LIVE theme flip
instead of freezing at the palette that was active when it was built.
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..color_management import ProcessColorManager
from ..persistence import get_base_path
from ..styles import Defaults
from ..theme import ThemeScope
from .color_scale import ColorScaleWidget
from .company_legend import CompanyLegendDialog
from .dialog_styles import combo_style, slider_style, spinbox_style


# ═══════════════════════════ WIDGET FACTORIES ═══════════════════════════

def make_spinbox(default: int = 1) -> QSpinBox:
    """Create an unstyled numeric input (1–100) for row count settings.

    The caller registers it with `_themed_sheet`, which is what paints it —
    styling it here too would just be a duplicate that a flip overwrites.
    """
    sb = QSpinBox()
    sb.setRange(1, 100)
    sb.setValue(max(1, min(100, default)))
    sb.setFont(QFont("Segoe UI", 11))
    sb.setFixedHeight(32)
    sb.setFixedWidth(70)
    sb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return sb


# ═══════════════════════════ THE DIALOG BASE ═══════════════════════════

class BaseSettingsDialog(QDialog):
    """
    Shared base for InitialSettingsDialog, CPUSettingsDialog,
    MemorySettingsDialog, and NetworkSettingsDialog.

    Provides theme + window icon setup, label/combo factories, and builders
    for the settings rows duplicated across all four dialogs.

    Every dialog is bound to ONE `ThemeScope` at construction: a per-mode
    dialog to the window that opened it, the setup screen to the app-wide
    scope. That is what lets the CPU settings dialog be dark while the
    Memory one is light.

    Every widget these factories create registers a **restyler** — a closure
    that rebuilds its stylesheet from `self._theme.palette`. `_apply_theme()`
    runs them all, so a dialog can follow a live theme flip instead of being
    frozen at the palette that was active when it was built. The per-mode
    dialogs are modal and never see a flip; the setup screen carries its own
    Day/Night switch and does.
    """

    def __init__(self, scope: ThemeScope, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._theme = scope

    def done(self, result: int) -> None:
        """Drop the restylers before closing, breaking the dialog's ref cycle.

        Every restyler is a closure over `self`, so a dialog holds a reference
        to itself. A parentless dialog (the tray's setup screen) therefore
        survives its own close as a zombie whose `changed` connection is still
        live, until the cyclic collector happens to run — and it accumulates
        one more zombie per open. Clearing the list here makes destruction
        deterministic instead of leaving it to gc.
        """
        self._restylers_list().clear()
        super().done(result)

    def _restylers_list(self) -> list:
        """The registered restyle closures, created on first use."""
        if not hasattr(self, "_restylers"):
            self._restylers: list = []
        return self._restylers

    def _register_restyle(self, restyle) -> None:
        """Register a closure that (re)applies one widget's theme styling."""
        self._restylers_list().append(restyle)
        restyle()

    def _themed_sheet(self, widget, builder) -> None:
        """Apply `builder(palette)` as `widget`'s stylesheet now and on every flip."""
        self._register_restyle(
            lambda: widget.setStyleSheet(builder(self._theme.palette))
        )

    def _apply_theme(self) -> None:
        """Load the window icon and apply THIS dialog's theme.

        Re-runs every registered restyler, so this is both the initial styling
        pass and the theme-flip handler.
        """
        icon_path = get_base_path() / "assets" / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        colors = self._theme.palette
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(colors.BACKGROUND))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(colors.TEXT))
        palette.setColor(QPalette.ColorRole.Base, QColor(colors.CARD))
        palette.setColor(QPalette.ColorRole.Text, QColor(colors.TEXT))
        palette.setColor(QPalette.ColorRole.Button, QColor(colors.HEADER))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors.TEXT))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(colors.ACCENT))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        for restyle in self._restylers_list():
            restyle()

    def _make_label(self, text: str, size: int = 12, bold: bool = False, color: Optional[str] = None) -> QLabel:
        """Build a styled label that follows the theme.

        `color` is a Palette ATTRIBUTE NAME (e.g. `"TEXT_MUTED"`), not a hex
        string — the token is what survives a theme flip. It defaults to
        `"TEXT"`. Resolving it here rather than in the signature matters: a
        default argument is evaluated once at import, which would freeze
        whichever palette happened to be active then.
        """
        label = QLabel(text)
        weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
        label.setFont(QFont("Segoe UI", size, weight))
        token = color or "TEXT"
        self._themed_sheet(
            label,
            lambda palette: f"color: {getattr(palette, token)}; background: transparent;",
        )
        return label

    def _make_legend_btn(self) -> QPushButton:
        """Create a themed Company Legend button (shared by all three dialogs)."""
        btn = QPushButton("Company Legend")
        btn.setFont(QFont("Segoe UI", 10))
        btn.setFixedHeight(28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._themed_sheet(btn, lambda palette: f"""
            QPushButton {{
                background-color: {palette.CARD}; color: {palette.TEXT_DIM};
                border: 1px solid {palette.HEADER}; border-radius: 4px; padding: 0 12px;
            }}
            QPushButton:hover {{ background-color: {palette.HEADER}; color: {palette.TEXT}; }}
        """)
        return btn

    def _build_color_section(
        self,
        layout: QVBoxLayout,
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
            mode:        one of the ProcessColorManager mode keys.
            max_info:    If non-empty, shown right-aligned on the title row as "100% = <max_info>".
        """
        if max_info:
            title_row = QHBoxLayout()
            title_row.setContentsMargins(0, 0, 0, 0)
            title_row.addWidget(self._make_label(title, 12, bold=True))
            title_row.addStretch()
            title_row.addWidget(self._make_label(f"100% = {max_info}", 9, color="TEXT_FAINT"))
            layout.addLayout(title_row)
        else:
            layout.addWidget(self._make_label(title, 12, bold=True))

        value_ranges = ProcessColorManager().get_value_ranges(mode, self._theme.palette)
        colors = [color for _, color in value_ranges]
        thresholds = [int(t) for t, _ in value_ranges[:-1]]  # first 4; last is always 100

        scale_widget = ColorScaleWidget(
            colors, thresholds, self._theme, scale_max=scale_max
        )
        layout.addWidget(scale_widget)

        if show_legend:
            legend_row = QHBoxLayout()
            legend_row.addStretch()
            legend_btn = self._make_legend_btn()
            scale_widget._legend_btn = legend_btn  # type: ignore[attr-defined]
            legend_row.addWidget(legend_btn)
            layout.addLayout(legend_row)
        else:
            scale_widget._legend_btn = None  # type: ignore[attr-defined]

        return scale_widget

    def _show_legend(self):
        """Open the company legend in this dialog's theme."""
        CompanyLegendDialog(self._theme, self).exec()

    def _make_combo(self, items: list, default: str) -> QComboBox:
        combo = QComboBox()
        combo.addItems(items)
        combo.setCurrentText(default)
        combo.setFont(QFont("Segoe UI", 11))
        combo.setMinimumContentsLength(max(len(item) for item in items))
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setFixedHeight(32)
        self._themed_sheet(combo, combo_style)
        return combo

    def _build_common_settings_rows(
        self, layout: QVBoxLayout
    ) -> tuple[QSpinBox, QSpinBox, QSlider, QLabel, QSlider, QLabel, QSlider, QLabel]:
        """
        Build the 5 common settings rows shared by all dialogs: current
        processes, history records, refresh rate, history retention, and
        font size. Returns the widgets so the caller can attach them as
        attributes (current_spin, history_spin, refresh_slider, refresh_label,
        retention_slider, retention_label, font_slider, font_label).
        """
        row1 = QHBoxLayout()
        row1.addWidget(self._make_label("Current processes:", 11, color="TEXT_MUTED"))
        row1.addStretch()
        current_spin = make_spinbox(Defaults.CURRENT_ROWS)
        self._themed_sheet(current_spin, spinbox_style)
        row1.addWidget(current_spin)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(self._make_label("History records:", 11, color="TEXT_MUTED"))
        row2.addStretch()
        history_spin = make_spinbox(Defaults.HISTORY_ROWS)
        self._themed_sheet(history_spin, spinbox_style)
        row2.addWidget(history_spin)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(self._make_label("Refresh rate:", 11, color="TEXT_MUTED"))
        row3.addStretch()
        refresh_slider = QSlider(Qt.Orientation.Horizontal)
        refresh_slider.setRange(1, 10)
        refresh_slider.setValue(Defaults.REFRESH_RATE_MS // 500)
        refresh_slider.setFixedWidth(140)
        self._themed_sheet(refresh_slider, slider_style)
        row3.addWidget(refresh_slider)
        refresh_label = self._make_label(f"{Defaults.REFRESH_RATE_MS} ms", 11)
        refresh_label.setFixedWidth(65)
        refresh_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        refresh_slider.valueChanged.connect(lambda v: refresh_label.setText(f"{v * 500} ms"))
        row3.addWidget(refresh_label)
        layout.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(self._make_label("History retention:", 11, color="TEXT_MUTED"))
        row4.addStretch()
        retention_slider = QSlider(Qt.Orientation.Horizontal)
        retention_slider.setRange(1, 36)
        retention_slider.setValue(Defaults.RETENTION_MINUTES // 10)
        retention_slider.setFixedWidth(140)
        self._themed_sheet(retention_slider, slider_style)
        row4.addWidget(retention_slider)
        retention_label = self._make_label(f"{Defaults.RETENTION_MINUTES} min", 11)
        retention_label.setFixedWidth(65)
        retention_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        retention_slider.valueChanged.connect(lambda v: retention_label.setText(f"{v * 10} min"))
        row4.addWidget(retention_label)
        layout.addLayout(row4)

        # Font size
        row_font = QHBoxLayout()
        row_font.addWidget(self._make_label("Font size:", 11, color="TEXT_MUTED"))
        row_font.addStretch()
        font_slider = QSlider(Qt.Orientation.Horizontal)
        font_slider.setRange(8, 18)
        font_slider.setValue(Defaults.FONT_SIZE)
        font_slider.setFixedWidth(140)
        self._themed_sheet(font_slider, slider_style)
        row_font.addWidget(font_slider)
        font_label = self._make_label(f"{Defaults.FONT_SIZE} pt", 11)
        font_label.setFixedWidth(65)
        font_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        font_slider.valueChanged.connect(lambda v: font_label.setText(f"{v} pt"))
        row_font.addWidget(font_label)
        layout.addLayout(row_font)

        return (
            current_spin, history_spin, refresh_slider, refresh_label,
            retention_slider, retention_label, font_slider, font_label,
        )

    def _build_network_settings_rows(
        self, layout: QVBoxLayout, default_speed_mbps: int = 0
    ) -> tuple[QComboBox, QComboBox, QSpinBox, QSpinBox]:
        """
        Build the network settings section shared by InitialSettingsDialog and
        NetworkSettingsDialog: title, speed unit combo, sort combo, and max
        download/upload spinboxes (0 = auto-detect from link speed). Returns
        (unit_combo, sort_combo, dl_spin, ul_spin) for the caller to attach
        as attributes.
        """
        layout.addWidget(self._make_label("Network Settings", 12, bold=True))

        row_unit = QHBoxLayout()
        row_unit.addWidget(self._make_label("Speed unit:", 11, color="TEXT_MUTED"))
        row_unit.addStretch()
        unit_combo = self._make_combo(["KB/s", "MB/s"], Defaults.NETWORK_UNIT)
        row_unit.addWidget(unit_combo)
        layout.addLayout(row_unit)

        row_sort = QHBoxLayout()
        row_sort.addWidget(self._make_label("Sort by:", 11, color="TEXT_MUTED"))
        row_sort.addStretch()
        sort_combo = self._make_combo(["total", "download", "upload"], Defaults.NETWORK_SORT_MODE)
        row_sort.addWidget(sort_combo)
        layout.addLayout(row_sort)

        row_dl = QHBoxLayout()
        row_dl.addWidget(self._make_label("Max download (Mbps):", 11, color="TEXT_MUTED"))
        row_dl.addStretch()
        dl_spin = QSpinBox()
        dl_spin.setRange(0, 100000)
        dl_spin.setValue(default_speed_mbps)
        dl_spin.setSpecialValueText("auto")
        dl_spin.setFont(QFont("Segoe UI", 11))
        dl_spin.setFixedHeight(32)
        dl_spin.setFixedWidth(100)
        dl_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._themed_sheet(dl_spin, spinbox_style)
        row_dl.addWidget(dl_spin)
        layout.addLayout(row_dl)

        row_ul = QHBoxLayout()
        row_ul.addWidget(self._make_label("Max upload (Mbps):", 11, color="TEXT_MUTED"))
        row_ul.addStretch()
        ul_spin = QSpinBox()
        ul_spin.setRange(0, 100000)
        ul_spin.setValue(default_speed_mbps)
        ul_spin.setSpecialValueText("auto")
        ul_spin.setFont(QFont("Segoe UI", 11))
        ul_spin.setFixedHeight(32)
        ul_spin.setFixedWidth(100)
        ul_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._themed_sheet(ul_spin, spinbox_style)
        row_ul.addWidget(ul_spin)
        layout.addLayout(row_ul)

        speed_hint = self._make_label(
            "0 = auto-detect from link speed. Test yours at speedtest.net", 9, color="TEXT_FAINT"
        )
        layout.addWidget(speed_hint)

        return unit_combo, sort_combo, dl_spin, ul_spin
