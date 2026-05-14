"""Inline busy indicator — a QLabel whose trailing dots animate while active."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QWidget

_DOT_TICK_MS: int = 400
_MAX_DOTS: int = 3


class BusyLabel(QLabel):
    """A QLabel that cycles trailing dots while busy.

    ``set_busy("Installing")`` animates as ``Installing`` → ``Installing.`` →
    ``Installing..`` → ``Installing...`` and back. ``set_idle("Done.")`` stops
    the animation and shows a static final message.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base: str = ""
        self._dots: int = 0
        self._timer = QTimer(self)
        self._timer.setInterval(_DOT_TICK_MS)
        self._timer.timeout.connect(self._tick)

    def set_busy(self, text: str) -> None:
        # Strip any trailing dots/ellipsis the caller already added — we
        # animate our own, and "Foo…..." would look broken.
        self._base = text.rstrip(" ….")
        self._dots = 0
        self._render()
        if not self._timer.isActive():
            self._timer.start()

    def set_idle(self, text: str) -> None:
        if self._timer.isActive():
            self._timer.stop()
        self._base = text
        self._dots = 0
        self.setText(text)

    def is_busy(self) -> bool:
        return self._timer.isActive()

    def _tick(self) -> None:
        self._dots = (self._dots + 1) % (_MAX_DOTS + 1)
        self._render()

    def _render(self) -> None:
        self.setText(self._base + "." * self._dots)


__all__ = ["BusyLabel"]
