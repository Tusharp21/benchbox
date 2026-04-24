"""Bench list — scrollable column of cards, one per discovered bench."""

from __future__ import annotations

from pathlib import Path

from benchbox_core import discovery, introspect
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.widgets.bench_card import BenchCard


class BenchListView(QWidget):
    """Discovers benches under $HOME and renders them as cards."""

    bench_selected = Signal(Path)
    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        title = QLabel("Benches on this machine")
        title.setProperty("role", "h1")
        subtitle = QLabel("Click a card to open its detail view")
        subtitle.setProperty("role", "dim")

        refresh = QPushButton("Refresh")
        refresh.setProperty("role", "ghost")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.clicked.connect(self.refresh)

        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        header = QHBoxLayout()
        header.addLayout(header_text, 1)
        header.addWidget(refresh, 0, Qt.AlignmentFlag.AlignTop)

        # Cards go inside a scroll area so long lists don't force window growth.
        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(10)
        self._cards_layout.addStretch(1)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self._cards_container)
        self._scroll.setFrameShape(self._scroll.Shape.NoFrame)

        self._empty = QLabel(
            "<p>No benches found under your home directory.</p>"
            "<p style='color:#a9a9c4;'>Head to <b>Install</b> in the sidebar to run the "
            "installer, or use <code>benchbox bench new &lt;path&gt;</code> from the CLI.</p>"
        )
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(20)
        root.addLayout(header)
        root.addWidget(self._scroll, 1)
        root.addWidget(self._empty)

        self.refresh()

    # --------------------------------------------------------------

    @property
    def card_count(self) -> int:
        """Count of BenchCards currently in the layout (excludes the stretch)."""
        count = 0
        for i in range(self._cards_layout.count()):
            item = self._cards_layout.itemAt(i)
            if item is not None and item.widget() is not None:
                count += 1
        return count

    def _clear_cards(self) -> None:
        # Keep the trailing stretch; remove only widget items.
        while self._cards_layout.count() > 0:
            item = self._cards_layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            # If it's the stretch spacer, it's dropped by takeAt — we add a new one below.
        self._cards_layout.addStretch(1)

    def refresh(self) -> None:
        self._clear_cards()
        paths = discovery.discover_benches()
        for path in paths:
            info = introspect.introspect(path)
            card = BenchCard(info)
            card.opened.connect(self.bench_selected.emit)
            # Insert before the trailing stretch.
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)

        has_benches = bool(paths)
        self._scroll.setVisible(has_benches)
        self._empty.setVisible(not has_benches)
        self.refresh_requested.emit()
