"""KPI card: big number on top, dim label below — used in dashboard strips."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget


class KpiCard(QFrame):
    def __init__(
        self,
        label: str,
        *,
        value: str = "—",
        accent: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("KpiCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._value = QLabel(value)
        self._value.setProperty("role", "kpi-value")
        self._value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._label = QLabel(label.upper())
        self._label.setProperty("role", "kpi-label")
        self._label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(4)
        layout.addWidget(self._value)
        layout.addWidget(self._label)

        if accent is not None:
            self.set_accent(accent)

    def set_value(self, value: str | int) -> None:
        self._value.setText(str(value))

    def set_accent(self, color: str | None) -> None:
        if color is None:
            self._value.setStyleSheet("")
            return
        self._value.setStyleSheet(f"color: {color};")


__all__ = ["KpiCard"]
