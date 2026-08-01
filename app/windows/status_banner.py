"""StatusBanner — the one surface allowed to shout.

Hidden until something is actually wrong. It sits between the header and the
data because a failure that only whispers from a corner label reads as "no
traffic", not "broken" (root Rule #1): the owner reported the Network window
as "showing nothing" when it was in fact refusing to trace and saying so in
10pt muted grey.

The banner shows a `TraceFailure`'s two lines and ONE remedy button. Which
remedy is decided by the failure's CODE, not by matching its text: relaunching
elevated cannot fix "another instance", and retrying in-process can never gain
Administrator.
"""

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..collect.network_trace import NEEDS_ADMIN
from ..styles import FontScale, scaled_font
from ..theme import ThemeScope


# ═══════════════════════════ THE STATUS BANNER ═══════════════════════════

class StatusBanner(QWidget):
    """A hidden-by-default failure notice with one remedy button.

    Args:
        scope: the owning window's theme scope — the banner follows it.
        font_base: the window's base font size in points.
        on_action: called when the remedy button is pressed.
    """

    def __init__(self, scope: ThemeScope, font_base: int, on_action: Callable[[], None]):
        super().__init__()
        self._theme = scope
        self._code: str = ""
        self.setVisible(False)

        banner_layout = QVBoxLayout(self)
        banner_layout.setContentsMargins(14, 10, 14, 12)
        banner_layout.setSpacing(4)

        self.reason = QLabel("")
        self.reason.setFont(scaled_font(font_base, FontScale.SUBTITLE, bold=True))
        self.reason.setWordWrap(True)
        banner_layout.addWidget(self.reason)

        self.action = QLabel("")
        self.action.setFont(scaled_font(font_base, FontScale.SMALL))
        self.action.setWordWrap(True)
        banner_layout.addWidget(self.action)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 4, 0, 0)
        button_row.addStretch()
        self.button = QPushButton("")
        self.button.setFont(scaled_font(font_base, FontScale.BODY, bold=True))
        self.button.setFixedHeight(30)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.clicked.connect(on_action)
        button_row.addWidget(self.button)
        banner_layout.addLayout(button_row)

    @property
    def code(self) -> str:
        """The failure code currently on display ('' when hidden)."""
        return self._code

    def show_failure(self, failure) -> None:
        """Display a TraceFailure and offer the remedy its code calls for."""
        self.reason.setText(failure.reason)
        self.action.setText(failure.action)
        # Relaunching cannot fix "another instance", and retrying in-process
        # can never gain Administrator — so the remedy follows the code.
        self._code = failure.code
        self.button.setText(
            "Restart as administrator" if failure.code == NEEDS_ADMIN else "Retry"
        )
        self.setVisible(True)

    def apply_theme(self) -> None:
        """Restyle from the owning window's palette (called on every flip).

        It borrows the existing TEMP_CRITICAL token rather than introducing a
        colour, so it follows the theme like everything else.
        """
        palette = self._theme.palette
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {palette.CARD};
                border: 1px solid {palette.TEMP_CRITICAL};
                border-radius: 8px;
            }}
        """)
        self.reason.setStyleSheet(
            f"color: {palette.TEMP_CRITICAL}; background: transparent; border: none;"
        )
        self.action.setStyleSheet(
            f"color: {palette.TEXT_MUTED}; background: transparent; border: none;"
        )
        self.button.setStyleSheet(f"""
            QPushButton {{
                background-color: {palette.ACCENT}; color: #ffffff;
                border: none; border-radius: 6px; padding: 4px 16px;
            }}
            QPushButton:hover {{ background-color: {palette.ACCENT_HOVER}; }}
        """)
