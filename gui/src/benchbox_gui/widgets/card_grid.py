"""Responsive card grid (1, 2, or 3 columns based on viewport width)."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QWidget

COL_BREAKPOINTS: tuple[tuple[int, int], ...] = (
    (1100, 3),
    (640, 2),
    (0, 1),
)


def cols_for(width: int) -> int:
    for min_width, n in COL_BREAKPOINTS:
        if width >= min_width:
            return n
    return 1


class CardGrid(QWidget):
    def __init__(self, parent: QWidget | None = None, *, spacing: int = 12) -> None:
        super().__init__(parent)
        self._cards: list[QWidget] = []
        self._cols: int = 2
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(spacing)
        self._layout.setVerticalSpacing(spacing)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        # Expanding so resizeEvent sees viewport width, not single-card hint.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    # ------------------------------------------------------------------

    def set_cards(self, cards: Sequence[QWidget]) -> None:
        self._clear_layout()
        self._cards = list(cards)
        for card in self._cards:
            card.setParent(self)
        self._relayout()

    def card_count(self) -> int:
        return len(self._cards)

    # ------------------------------------------------------------------

    def _clear_layout(self) -> None:
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        while self._layout.count() > 0:
            item = self._layout.takeAt(0)
            if item is None:
                break
        self._cards = []

    def _relayout(self) -> None:
        while self._layout.count() > 0:
            item = self._layout.takeAt(0)
            if item is None:
                break

        for i, card in enumerate(self._cards):
            row = i // self._cols
            col = i % self._cols
            self._layout.addWidget(card, row, col)

        for c in range(self._cols):
            self._layout.setColumnStretch(c, 1)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 — Qt override
        super().resizeEvent(event)
        desired = cols_for(event.size().width())
        if desired != self._cols:
            self._cols = desired
            self._relayout()
