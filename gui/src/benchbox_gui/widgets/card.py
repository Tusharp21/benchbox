"""Reusable base card — QFrame with objectName='Card' so QSS can style it."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget


class Card(QFrame):
    """A panel with the shared card look. Use ``layout()`` to add children."""

    def __init__(self, parent: QWidget | None = None, *, object_name: str = "Card") -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 14)
        self._layout.setSpacing(8)

    def addWidget(self, widget: QWidget) -> None:  # noqa: N802 — match Qt casing
        self._layout.addWidget(widget)

    def addLayout(self, layout: object) -> None:  # noqa: N802
        self._layout.addLayout(layout)  # type: ignore[arg-type]

    def addSpacing(self, amount: int) -> None:  # noqa: N802
        self._layout.addSpacing(amount)

    def addStretch(self, stretch: int = 1) -> None:  # noqa: N802
        self._layout.addStretch(stretch)
