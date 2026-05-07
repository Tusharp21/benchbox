"""Collapsible per-bench section: header (path + count) above a CardGrid."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.widgets.card_grid import CardGrid


class BenchSection(QFrame):
    """A per-bench group: header bar with collapse toggle, then a card grid."""

    def __init__(
        self,
        bench_path: Path,
        item_label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bench_path = bench_path
        self._item_label = item_label
        self._collapsed = False
        self.setObjectName("BenchSection")
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._toggle = QToolButton()
        self._toggle.setText("▾")
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setProperty("role", "section-toggle")
        self._toggle.setAutoRaise(True)
        self._toggle.clicked.connect(self._on_toggle)

        self._title = QLabel(bench_path.name or str(bench_path))
        self._title.setProperty("role", "h2")

        self._path_label = QLabel(str(bench_path))
        self._path_label.setProperty("role", "dim")

        self._count = QLabel("0")
        self._count.setProperty("role", "badge")
        self._count.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addWidget(self._title)
        title_col.addWidget(self._path_label)

        header_row = QHBoxLayout()
        header_row.setSpacing(10)
        header_row.addWidget(self._toggle, 0, Qt.AlignmentFlag.AlignVCenter)
        header_row.addLayout(title_col, 1)
        header_row.addWidget(self._count, 0, Qt.AlignmentFlag.AlignVCenter)

        self._header = QFrame()
        self._header.setObjectName("BenchSectionHeader")
        header_layout = QVBoxLayout(self._header)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(0)
        header_layout.addLayout(header_row)

        self._grid = CardGrid()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.addWidget(self._header)
        root.addWidget(self._grid)

    @property
    def bench_path(self) -> Path:
        return self._bench_path

    def card_count(self) -> int:
        return self._grid.card_count()

    def set_cards(self, cards: Sequence[QWidget]) -> None:
        self._grid.set_cards(cards)
        n = len(cards)
        suffix = self._item_label if n == 1 else f"{self._item_label}s"
        self._count.setText(f"{n} {suffix}")
        self._grid.setVisible(not self._collapsed and n > 0)

    def _on_toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._toggle.setText("▸" if self._collapsed else "▾")
        self._grid.setVisible(not self._collapsed and self._grid.card_count() > 0)
