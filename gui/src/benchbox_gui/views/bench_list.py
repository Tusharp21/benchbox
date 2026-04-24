"""Bench list — scrollable column of cards, one per discovered bench."""

from __future__ import annotations

from pathlib import Path

from benchbox_core import bench as core_bench
from benchbox_core import discovery, introspect
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.widgets.bench_card import BenchCard
from benchbox_gui.widgets.dialogs import NewBenchDialog, NewBenchValues
from benchbox_gui.workers import OperationWorker


class BenchListView(QWidget):
    """Discovers benches under $HOME and renders them as cards."""

    bench_selected = Signal(Path)
    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: OperationWorker | None = None
        self._progress: QProgressDialog | None = None

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
        header_text.setSpacing(2)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        header = QHBoxLayout()
        header.addLayout(header_text, 1)
        header.addWidget(refresh, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(self._new_bench, 0, Qt.AlignmentFlag.AlignTop)

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
            "<p style='color:#a9a9c4;'>Click <b>+ New bench</b> above or run the installer "
            "from the sidebar.</p>"
        )
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)
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
        while self._cards_layout.count() > 0:
            item = self._cards_layout.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._cards_layout.addStretch(1)

    def refresh(self) -> None:
        self._clear_cards()
        paths = discovery.discover_benches()
        for path in paths:
            info = introspect.introspect(path)
            card = BenchCard(info)
            card.opened.connect(self.bench_selected.emit)
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)

        has_benches = bool(paths)
        self._scroll.setVisible(has_benches)
        self._empty.setVisible(not has_benches)
        self.refresh_requested.emit()

    # --- new-bench flow -----------------------------------------------

    def _on_new_bench(self) -> None:
        dialog = NewBenchDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self._start_create_bench(values)

    def _start_create_bench(self, values: NewBenchValues) -> None:
        self._progress = QProgressDialog(self)
        self._progress.setLabelText(
            f"Creating bench at {values.path}…\nThis can take several minutes."
        )
        self._progress.setWindowTitle("Creating bench")
        self._progress.setMinimum(0)
        self._progress.setMaximum(0)
        self._progress.setMinimumDuration(0)
        self._progress.setCancelButton(None)
        self._progress.show()

        def op() -> core_bench.BenchCreateResult:
            return core_bench.create_bench(
                values.path,
                frappe_branch=values.frappe_branch,
                python_bin=values.python_bin,
            )

        self._worker = OperationWorker(op)
        self._worker.succeeded.connect(self._on_bench_created)
        self._worker.failed.connect(self._on_bench_create_failed)
        self._worker.start()

    def _close_progress(self) -> None:
        if self._progress is not None:
            self._progress.close()
            self._progress = None

    def _on_bench_created(self, _result: object) -> None:
        self._close_progress()
        self.refresh()
        QMessageBox.information(self, "Bench ready", "New bench created.")

    def _on_bench_create_failed(self, exc: object) -> None:
        self._close_progress()
        QMessageBox.critical(
            self,
            "Bench creation failed",
            f"{exc}\n\nCheck the session log for details.",
        )
