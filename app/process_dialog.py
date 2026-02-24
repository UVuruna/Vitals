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

from .process_actions import PRIORITY_CLASSES
from .styles import Fonts


class _ProcessDialogBase(QDialog):
    """Modal dialog with a dark theme and process name header."""

    BG_COLOR = "#1e1e2e"
    CARD_COLOR = "#2a2a3e"
    HEADER_COLOR = "#3a3a4e"
    ACCENT = "#e94560"
    TEXT = "#ffffff"
    TEXT_MUTED = "#aaaaaa"

    def __init__(
        self,
        parent,
        process_name: str,
        title: str,
        proc_color: Optional[QColor] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(360)
        self._build_base(process_name, proc_color)

    def _build_base(self, process_name: str, proc_color: Optional[QColor]):
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {self.BG_COLOR};
            }}
            QLabel {{
                background: transparent;
                color: {self.TEXT};
            }}
            QPushButton {{
                background-color: {self.HEADER_COLOR};
                color: {self.TEXT};
                border: none;
                border-radius: 6px;
                padding: 6px 20px;
                font-family: {Fonts.FAMILY};
                font-size: {Fonts.SIZE_BODY}px;
            }}
            QPushButton:hover {{
                background-color: #4a4a5e;
            }}
            QRadioButton {{
                color: {self.TEXT};
                background: transparent;
                font-family: {Fonts.FAMILY};
                font-size: {Fonts.SIZE_BODY}px;
                spacing: 8px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header — process name
        header = QFrame()
        header.setStyleSheet(f"background-color: {self.CARD_COLOR};")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 16, 20, 16)

        name_label = QLabel(process_name)
        name_label.setFont(QFont(Fonts.FAMILY, Fonts.SIZE_HEADER, QFont.Weight.Bold))
        name_color = proc_color.name() if proc_color else self.TEXT
        name_label.setStyleSheet(f"color: {name_color}; background: transparent;")
        header_layout.addWidget(name_label)

        root.addWidget(header)

        # Content area
        content = QFrame()
        content.setStyleSheet(f"background-color: {self.BG_COLOR};")
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
        proc_color: Optional[QColor] = None,
    ):
        super().__init__(parent, process_name, "Kill Process", proc_color)

        count_str = f"{count} instance{'s' if count != 1 else ''}"
        msg = QLabel(f"Kill all {count_str} of this process?\nThis cannot be undone.")
        msg.setFont(QFont(Fonts.FAMILY, Fonts.SIZE_BODY))
        msg.setStyleSheet(f"color: {self.TEXT_MUTED}; background: transparent;")
        self._content.addWidget(msg)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        kill_btn = QPushButton("Kill")
        kill_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.ACCENT};
                color: {self.TEXT};
                border: none;
                border-radius: 6px;
                padding: 6px 20px;
                font-family: {Fonts.FAMILY};
                font-size: {Fonts.SIZE_BODY}px;
            }}
            QPushButton:hover {{
                background-color: #ff6080;
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
        proc_color: Optional[QColor] = None,
    ):
        super().__init__(parent, process_name, "Set Priority", proc_color)

        desc = QLabel("Set priority for all instances:")
        desc.setFont(QFont(Fonts.FAMILY, Fonts.SIZE_SMALL))
        desc.setStyleSheet(f"color: {self.TEXT_MUTED}; background: transparent;")
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
                background-color: #3a6a3a;
                color: {self.TEXT};
                border: none;
                border-radius: 6px;
                padding: 6px 20px;
                font-family: {Fonts.FAMILY};
                font-size: {Fonts.SIZE_BODY}px;
            }}
            QPushButton:hover {{
                background-color: #4a8a4a;
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
