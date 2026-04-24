"""Small rounded pill used in the top stats banner."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


class StatPill(QFrame):
    """A single stat: ``label`` on the left, ``value`` on the right.

    ``set_value`` + ``set_accent`` are the only methods the banner needs;
    everything else is cosmetic.
    """

    def __init__(
        self,
        label: str,
        *,
        value: str = "—",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("StatPill")
        self._label = QLabel(label)
        self._label.setProperty("role", "dim")

        self._value = QLabel(value)
        self._value.setProperty("role", "h2")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(10)
        layout.addWidget(self._label)
        layout.addWidget(self._value, alignment=Qt.AlignmentFlag.AlignRight)

    def set_value(self, value: str) -> None:
        self._value.setText(value)

    def set_accent(self, color: str | None) -> None:
        if color is None:
            self._value.setStyleSheet("")
            return
        self._value.setStyleSheet(f"color: {color};")
