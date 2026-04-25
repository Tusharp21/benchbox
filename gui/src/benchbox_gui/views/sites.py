"""Sites tab — read-only list of every site across every bench.

Mutations (new-site / drop / install-app / restore) live on the bench
detail view now; this tab just shows what's present so the user can get
a global picture without clicking through each bench.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from benchbox_core import discovery, introspect
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.widgets.card_grid import CardGrid
from benchbox_gui.widgets.site_card import SiteCard


@dataclass(frozen=True)
class _Row:
    bench_path: Path
    site: introspect.SiteInfo


class SitesView(QWidget):
    """Read-only list of every site across every bench."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[_Row] = []

        title = QLabel("Sites")
        title.setProperty("role", "h1")
        subtitle = QLabel(
            "Sites across every bench on this machine. "
            "Open a bench from the Benches tab to create, drop, or restore."
        )
        subtitle.setProperty("role", "dim")
        subtitle.setWordWrap(True)

        refresh = QPushButton("Refresh")
        refresh.setProperty("role", "ghost")
        refresh.clicked.connect(self.refresh)

        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        header = QHBoxLayout()
        header.addLayout(header_text, 1)
        header.addWidget(refresh, 0, Qt.AlignmentFlag.AlignTop)

        self._grid = CardGrid()
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self._grid)
        self._scroll.setFrameShape(self._scroll.Shape.NoFrame)

        self._empty = QLabel(
            "<p>No sites yet.</p>"
            "<p style='color:#a9a9c4;'>"
            "Open a bench from the Benches tab and use "
            "<b>+ New site</b> to create one."
            "</p>"
        )
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)
        root.addLayout(header)
        root.addWidget(self._scroll, 1)
        root.addWidget(self._empty)

        self.refresh()

    @property
    def card_count(self) -> int:
        return self._grid.card_count()

    def refresh(self) -> None:
        bench_cache = {p: introspect.introspect(p) for p in discovery.discover_benches()}
        self._rows = [
            _Row(bench_path=info.path, site=site)
            for info in bench_cache.values()
            for site in info.sites
        ]

        cards: list[QWidget] = [
            SiteCard(row.bench_path, row.site, read_only=True) for row in self._rows
        ]
        self._grid.set_cards(cards)

        has_rows = bool(self._rows)
        self._scroll.setVisible(has_rows)
        self._empty.setVisible(not has_rows)
