"""QSS builders for the settings dialogs.

Every builder is a FUNCTION taking the palette to render in — never a
module-level f-string. A dialog is themed by the window that opened it, and
two open dialogs can be on different themes, so nothing here may look up a
theme of its own. A module-level constant would freeze whichever palette
happened to be active at import time (the exact bug the ThemeScope design
exists to prevent).

`BaseSettingsDialog._themed_sheet()` registers these as restylers, which is
what lets the setup screen follow a live theme flip.
"""

from ..theme import Palette


# ═══════════════════════════════ INPUT WIDGETS ═══════════════════════════════

def spinbox_style(palette: Palette) -> str:
    """QSS for a numeric input."""
    return f"""
    QSpinBox {{
        background-color: {palette.HEADER}; color: {palette.TEXT};
        border: 1px solid {palette.BORDER}; border-radius: 4px;
        padding: 4px 8px;
    }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 0px; }}
"""


def slider_style(palette: Palette) -> str:
    """QSS for a settings slider."""
    return f"""
    QSlider::groove:horizontal {{ height: 6px; background: {palette.HEADER}; border-radius: 3px; }}
    QSlider::handle:horizontal {{ background: {palette.ACCENT}; width: 16px; margin: -5px 0; border-radius: 8px; }}
    QSlider::sub-page:horizontal {{ background: {palette.ACCENT}; border-radius: 3px; }}
"""


def combo_style(palette: Palette) -> str:
    """QSS for a dropdown."""
    return f"""
    QComboBox {{
        background-color: {palette.HEADER}; color: {palette.TEXT};
        border: 1px solid {palette.BORDER}; border-radius: 4px; padding: 4px 8px;
    }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox::down-arrow {{
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 5px solid {palette.TEXT};
    }}
    QComboBox QAbstractItemView {{
        background-color: {palette.HEADER}; color: {palette.TEXT};
        selection-background-color: {palette.ACCENT};
    }}
"""


# ═══════════════════════════════════ BUTTONS ═══════════════════════════════════

def start_button_style(palette: Palette) -> str:
    """QSS for the setup screen's primary action button."""
    return f"""
    QPushButton {{
        background-color: {palette.ACCENT}; color: #ffffff;
        border: none; border-radius: 8px;
    }}
    QPushButton:hover {{ background-color: {palette.ACCENT_HOVER}; }}
    QPushButton:disabled {{
        background-color: {palette.TEXT_DISABLED}; color: {palette.TEXT_DIM};
    }}
"""


def mode_button_style(palette: Palette, active: bool) -> str:
    """QSS for a selectable mode/toggle button."""
    if active:
        return f"""
        QPushButton {{
            background-color: {palette.ACCENT}; color: #ffffff;
            border: none; border-radius: 6px;
        }}
        QPushButton:hover {{ background-color: {palette.ACCENT_HOVER}; }}
    """
    return f"""
    QPushButton {{
        background-color: {palette.HEADER}; color: {palette.TEXT_DIM};
        border: none; border-radius: 6px;
    }}
    QPushButton:hover {{ background-color: {palette.BORDER}; }}
"""


def apply_button_style(palette: Palette) -> str:
    """QSS for a per-mode dialog's Apply button (one builder for all three)."""
    return f"""
    QPushButton {{
        background-color: {palette.ACCENT}; color: #ffffff;
        border: none; border-radius: 8px;
    }}
    QPushButton:hover {{ background-color: {palette.ACCENT_HOVER}; }}
"""
