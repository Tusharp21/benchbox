"""Bench list view — responsive card grid over all discovered benches."""

from __future__ import annotations

from pathlib import Path

from benchbox_core import discovery, introspect
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.services.bench_processes import BenchProcessManager
from benchbox_gui.widgets.bench_card import BenchCard
from benchbox_gui.widgets.card_grid import CardGrid
from benchbox_gui.widgets.dialogs import NewBenchDialog


class BenchListView(QWidget):
    bench_selected = Signal(Path)
    refresh_requested = Signal()

    def __init__(
        self,
        process_manager: BenchProcessManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._manager = process_manager
        self._cards_by_path: dict[Path, BenchCard] = {}
        self._filter: str = ""
        self._running_only: bool = False

        title = QLabel("Benches on this machine")
        title.setProperty("role", "h1")
        subtitle = QLabel("Click a card to open its detail view")
        subtitle.setProperty("role", "dim")

        refresh = QPushButton("Refresh")
        refresh.setProperty("role", "ghost")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.clicked.connect(self.refresh)

        self._new_bench = QPushButton("+ New bench")
        self._new_bench.setProperty("role", "primary")
        self._new_bench.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_bench.clicked.connect(self._on_new_bench)

        header_text = QVBoxLayout()
        header_text.setSpacing(3)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addLayout(header_text, 1)
        header.addWidget(refresh, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(self._new_bench, 0, Qt.AlignmentFlag.AlignTop)

        # Filter toolbar — visually grouped so it reads as "controls for the
        # grid below" rather than a second header row of disconnected inputs.
        filter_label = QLabel("Filter:")
        filter_label.setProperty("role", "dim")

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search by name or path…")
        self._search.setClearButtonEnabled(True)
        self._search.setMinimumWidth(280)
        self._search.textChanged.connect(self._on_filter_changed)

        self._running_only_toggle = QCheckBox("Running only")
        self._running_only_toggle.toggled.connect(self._on_running_only_toggled)

        self._filter_bar = QFrame()
        self._filter_bar.setObjectName("FilterBar")
        filter_layout = QHBoxLayout(self._filter_bar)
        filter_layout.setContentsMargins(14, 10, 14, 10)
        filter_layout.setSpacing(12)
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self._search, 1)
        filter_layout.addWidget(self._running_only_toggle)

        self._grid = CardGrid()
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self._grid)
        self._scroll.setFrameShape(self._scroll.Shape.NoFrame)

        self._empty = QLabel(
            "<p>No benches found under your home directory.</p>"
            "<p style='color:#a9a9c4;'>Click <b>+ New bench</b> above or run the installer "
            "from the sidebar.</p>"
        )
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)

        self._no_results = QLabel()
        self._no_results.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_results.setProperty("role", "dim")
        self._no_results.setVisible(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)
        root.addLayout(header)
        root.addWidget(self._filter_bar)
        root.addWidget(self._scroll, 1)
        root.addWidget(self._no_results)
        root.addWidget(self._empty)

        # Subscribe once — running chips stay in sync across start/stop
        # regardless of whether the user is looking at the list or a
        # detail view.
        self._manager.process_started.connect(self._on_process_started)
        self._manager.process_stopped.connect(self._on_process_stopped)

        self.refresh()

    # --------------------------------------------------------------

    @property
    def card_count(self) -> int:
        return self._grid.card_count()

    def refresh(self) -> None:
        paths = discovery.discover_benches()
        self._cards_by_path = {}
        cards: list[QWidget] = []
        for path in paths:
            info = introspect.introspect(path)
            card = BenchCard(info, running=self._manager.is_running(path))
            card.opened.connect(self.bench_selected.emit)
            self._cards_by_path[info.path] = card
            cards.append(card)
        self._grid.set_cards(cards)

        has_benches = bool(paths)
        self._scroll.setVisible(has_benches)
        self._empty.setVisible(not has_benches)
        self._apply_filter()
        self.refresh_requested.emit()

    # --- filter ------------------------------------------------------

    def _on_filter_changed(self, text: str) -> None:
        self._filter = text.strip().lower()
        self._apply_filter()

    def _on_running_only_toggled(self, checked: bool) -> None:
        self._running_only = checked
        self._apply_filter()

    def _apply_filter(self) -> None:
        if not self._cards_by_path:
            self._no_results.setVisible(False)
            return

        needle = self._filter
        matched = 0
        for path, card in self._cards_by_path.items():
            text_match = True if not needle else (needle in f"{path.name} {path!s}".lower())
            running_match = True if not self._running_only else self._manager.is_running(path)
            visible = text_match and running_match
            card.setVisible(visible)
            if visible:
                matched += 1

        # "No matches" state fires only when at least one filter is actually
        # narrowing; an all-clear filter that matches everything shouldn't
        # swap the empty-state label in.
        narrowing = bool(self._filter) or self._running_only
        if narrowing and matched == 0:
            bits: list[str] = []
            if self._filter:
                bits.append(f"matching <b>{self._filter}</b>")
            if self._running_only:
                bits.append("currently running")
            criteria = " and ".join(bits)
            self._no_results.setText(f"<p>No benches {criteria}.</p>")
            self._no_results.setVisible(True)
            self._scroll.setVisible(False)
        else:
            self._no_results.setVisible(False)
            self._scroll.setVisible(bool(self._cards_by_path))

    # --- manager signals --------------------------------------------

    def _on_process_started(self, path: Path) -> None:
        card = self._cards_by_path.get(path)
        if card is not None:
            card.set_running(True)
        if self._running_only:
            # A bench just started — maybe it now satisfies the filter.
            self._apply_filter()

    def _on_process_stopped(self, path: Path, _exit_code: int) -> None:
        card = self._cards_by_path.get(path)
        if card is not None:
            card.set_running(False)
        if self._running_only:
            # And a stop might now hide it from the running-only view.
            self._apply_filter()

    # --- new-bench flow -----------------------------------------------

    def _on_new_bench(self) -> None:
        # NewBenchDialog is a LiveLogDialog: it owns the worker and the
        # log panel, so we just refresh the list when it returns Accepted.
        dialog = NewBenchDialog(self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.refresh()
