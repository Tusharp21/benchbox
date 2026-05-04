"""Installer component card."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

_STATE_LABELS: dict[str, str] = {
    "installed": "Installed",
    "not_installed": "Not installed",
    "queued": "Queued",
    "running": "Running…",
    "done": "Done",
    "failed": "Failed",
}

_STATE_COLOURS: dict[str, str | None] = {
    "installed": "#1a7f37",
    "not_installed": None,
    "queued": None,
    "running": "#d29922",
    "done": "#1a7f37",
    "failed": "#cf222e",
}


class ComponentCard(QFrame):
    def __init__(
        self,
        name: str,
        description: str,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AppCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._name = name

        title = QLabel(name)
        title.setProperty("role", "h2")

        desc = QLabel(description)
        desc.setProperty("role", "dim")
        desc.setWordWrap(True)

        self._badge = QLabel("")
        self._badge.setProperty("role", "badge")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addWidget(title, 1)
        title_row.addWidget(self._badge, 0, Qt.AlignmentFlag.AlignTop)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        layout.addLayout(title_row)
        layout.addWidget(desc)

        self.set_state("not_installed")

    @property
    def component_name(self) -> str:
        return self._name

    def set_state(self, state: str) -> None:
        label = _STATE_LABELS.get(state, state)
        colour = _STATE_COLOURS.get(state)
        self._badge.setText(label)
        if colour is None:
            self._badge.setStyleSheet("")
        else:
            self._badge.setStyleSheet(
                f"background-color: {colour}; color: white; "
                "padding: 3px 10px; border-radius: 9px; font-weight: 600; font-size: 10pt;"
            )


__all__ = ["ComponentCard"]
