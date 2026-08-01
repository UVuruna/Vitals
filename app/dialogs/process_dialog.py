"""
Process Action Dialogs

Kill confirmation and priority selection dialogs.
Both show the process name prominently in a header at the top.
"""

from typing import Optional

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from ..process_actions import PRIORITY_CLASSES
from ..styles import Fonts
from ..theme import Palette


class _ProcessDialogBase(QDialog):
    """Modal dialog in the calling window's theme, with a process name header.

    These dialogs used to carry their OWN copy of the palette hexes — a
    duplicate that could not follow a theme flip. They now take the palette
    of the window that opened them (root Rules #4 and #5), which matters more
    than ever since the three monitors can be on different themes. Being
    modal, reading it once at construction is enough.
    """

    def __init__(
        self,
        parent,
        process_name: str,
        title: str,
        palette: Palette,
        proc_color: Optional[QColor] = None,
    ):
        super().__init__(parent)
        self._palette = palette
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(360)
        self._build_base(process_name, proc_color)

    def _build_base(self, process_name: str, proc_color: Optional[QColor]):
        palette = self._palette
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {palette.BACKGROUND};
            }}
            QLabel {{
                background: transparent;
                color: {palette.TEXT};
            }}
            QPushButton {{
                background-color: {palette.HEADER};
                color: {palette.TEXT};
                border: none;
                border-radius: 6px;
                padding: 6px 20px;
                font-family: {Fonts.FAMILY};
                font-size: {Fonts.SIZE_BODY}px;
            }}
            QPushButton:hover {{
                background-color: {palette.BORDER};
            }}
            QRadioButton {{
                color: {palette.TEXT};
                background: transparent;
                font-family: {Fonts.FAMILY};
                font-size: {Fonts.SIZE_BODY}px;
                spacing: 8px;
            }}
            QRadioButton::indicator {{
                width: 13px;
                height: 13px;
                border-radius: 8px;
                border: 2px solid {palette.BORDER};
                background-color: {palette.CARD};
            }}
            QRadioButton::indicator:checked {{
                border: 2px solid {palette.ACCENT};
                background-color: {palette.ACCENT};
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header — process name
        header = QFrame()
        header.setStyleSheet(f"background-color: {palette.CARD};")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 16)

        name_label = QLabel(process_name)
        name_label.setFont(QFont(Fonts.FAMILY, Fonts.SIZE_HEADER, QFont.Weight.Bold))
        name_color = proc_color.name() if proc_color else palette.TEXT
        name_label.setStyleSheet(f"color: {name_color}; background: transparent;")
        header_layout.addWidget(name_label)

        root.addWidget(header)

        # Content area
        content = QFrame()
        content.setStyleSheet(f"background-color: {palette.BACKGROUND};")
        self._content = QVBoxLayout(content)
        self._content.setContentsMargins(20, 16, 20, 20)
        self._content.setSpacing(12)

        root.addWidget(content)


class KillConfirmDialog(_ProcessDialogBase):
    """Confirmation before killing all instances of a process."""

    def __init__(
        self,
        parent,
        process_name: str,
        count: int,
        palette: Palette,
        proc_color: Optional[QColor] = None,
    ):
        super().__init__(parent, process_name, "Kill Process", palette, proc_color)

        count_str = f"{count} instance{'s' if count != 1 else ''}"
        msg = QLabel(f"Kill all {count_str} of this process?\nThis cannot be undone.")
        msg.setFont(QFont(Fonts.FAMILY, Fonts.SIZE_BODY))
        msg.setStyleSheet(f"color: {palette.TEXT_MUTED}; background: transparent;")
        self._content.addWidget(msg)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        kill_btn = QPushButton("Kill")
        kill_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {palette.ACCENT};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 20px;
                font-family: {Fonts.FAMILY};
                font-size: {Fonts.SIZE_BODY}px;
            }}
            QPushButton:hover {{
                background-color: {palette.ACCENT_HOVER};
            }}
        """)
        kill_btn.clicked.connect(self.accept)
        btn_row.addWidget(kill_btn)

        self._content.addLayout(btn_row)


class PriorityDialog(_ProcessDialogBase):
    """Priority class selection for all instances of a process."""

    def __init__(
        self,
        parent,
        process_name: str,
        current_priority: Optional[int],
        palette: Palette,
        proc_color: Optional[QColor] = None,
    ):
        super().__init__(parent, process_name, "Set Priority", palette, proc_color)

        desc = QLabel("Set priority for all instances:")
        desc.setFont(QFont(Fonts.FAMILY, Fonts.SIZE_SMALL))
        desc.setStyleSheet(f"color: {palette.TEXT_MUTED}; background: transparent;")
        self._content.addWidget(desc)

        self._group = QButtonGroup(self)
        for label, value in PRIORITY_CLASSES:
            radio = QRadioButton(label)
            if value == current_priority:
                radio.setChecked(True)
            radio.setProperty("priority_value", value)
            self._group.addButton(radio)
            self._content.addWidget(radio)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        apply_btn = QPushButton("Apply")
        apply_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {palette.CONFIRM};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 20px;
                font-family: {Fonts.FAMILY};
                font-size: {Fonts.SIZE_BODY}px;
            }}
            QPushButton:hover {{
                background-color: {palette.CONFIRM_HOVER};
            }}
        """)
        apply_btn.clicked.connect(self.accept)
        btn_row.addWidget(apply_btn)

        self._content.addLayout(btn_row)

    def get_selected_priority(self) -> Optional[int]:
        """Return the selected Windows priority class constant."""
        checked = self._group.checkedButton()
        if checked:
            return checked.property("priority_value")
        return None
