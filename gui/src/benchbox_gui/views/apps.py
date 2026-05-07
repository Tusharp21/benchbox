"""Apps tab — read-only list of every (bench, app) on the host, grouped by bench."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from benchbox_core import discovery, introspect
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.widgets.app_card import AppCard
from benchbox_gui.widgets.bench_section import BenchSection

ALL_BENCHES = "__all__"


@dataclass(frozen=True)
class _Row:
    bench_path: Path
    app: introspect.AppInfo


class AppsView(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[_Row] = []
        self._bench_paths: list[Path] = []
        self._filter: str = ""
        self._bench_filter: str = ALL_BENCHES

        title = QLabel("Apps")
        title.setProperty("role", "h1")
        subtitle = QLabel(
            "Apps grouped by bench. "
            "Open a bench from the Benches tab to install or remove apps."
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

        # Filter toolbar — search box + bench dropdown.
        filter_label = QLabel("Filter:")
        filter_label.setProperty("role", "dim")

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search by app name or bench path…")
        self._search.setClearButtonEnabled(True)
        self._search.setMinimumWidth(260)
        self._search.textChanged.connect(self._on_filter_changed)

        bench_label = QLabel("Bench:")
        bench_label.setProperty("role", "dim")

        self._bench_combo = QComboBox()
        self._bench_combo.setMinimumWidth(220)
        self._bench_combo.currentIndexChanged.connect(self._on_bench_filter_changed)

        self._filter_bar = QFrame()
        self._filter_bar.setObjectName("FilterBar")
        filter_layout = QHBoxLayout(self._filter_bar)
        filter_layout.setContentsMargins(14, 10, 14, 10)
        filter_layout.setSpacing(12)
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self._search, 1)
        filter_layout.addWidget(bench_label)
        filter_layout.addWidget(self._bench_combo)

        # Body — vertical stack of BenchSection widgets inside a scroll area.
        self._sections_host = QWidget()
        self._sections_layout = QVBoxLayout(self._sections_host)
        self._sections_layout.setContentsMargins(0, 0, 0, 0)
        self._sections_layout.setSpacing(14)
        self._sections_layout.addStretch(1)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self._sections_host)
        self._scroll.setFrameShape(self._scroll.Shape.NoFrame)

        self._empty = QLabel()
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)
        root.addLayout(header)
        root.addWidget(self._filter_bar)
        root.addWidget(self._scroll, 1)
        root.addWidget(self._empty)

        self.refresh()

    @property
    def card_count(self) -> int:
        return sum(s.card_count() for s in self._sections())

    def refresh(self) -> None:
        bench_cache = {p: introspect.introspect(p) for p in discovery.discover_benches()}
        self._bench_paths = sorted(bench_cache.keys(), key=lambda p: str(p).lower())
        self._rows = [
            _Row(bench_path=info.path, app=app)
            for info in bench_cache.values()
            for app in info.apps
        ]
        self._refresh_bench_combo()
        self._render()

    def _refresh_bench_combo(self) -> None:
        current = self._bench_filter
        self._bench_combo.blockSignals(True)
        self._bench_combo.clear()
        self._bench_combo.addItem("All benches", ALL_BENCHES)
        for path in self._bench_paths:
            self._bench_combo.addItem(str(path), str(path))
        idx = self._bench_combo.findData(current)
        self._bench_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._bench_filter = self._bench_combo.currentData() or ALL_BENCHES
        self._bench_combo.blockSignals(False)

    def _on_filter_changed(self, text: str) -> None:
        self._filter = text.strip().lower()
        self._render()

    def _on_bench_filter_changed(self, _index: int) -> None:
        self._bench_filter = self._bench_combo.currentData() or ALL_BENCHES
        self._render()

    def _sections(self) -> list[BenchSection]:
        out: list[BenchSection] = []
        for i in range(self._sections_layout.count()):
            item = self._sections_layout.itemAt(i)
            if item is None:
                continue
            w = item.widget()
            if isinstance(w, BenchSection):
                out.append(w)
        return out

    def _clear_sections(self) -> None:
        for i in reversed(range(self._sections_layout.count())):
            item = self._sections_layout.itemAt(i)
            if item is None:
                continue
            w = item.widget()
            if isinstance(w, BenchSection):
                self._sections_layout.takeAt(i)
                w.setParent(None)
                w.deleteLater()

    def _render(self) -> None:
        self._clear_sections()

        rows_by_bench: dict[Path, list[_Row]] = {p: [] for p in self._bench_paths}
        for row in self._rows:
            if not self._matches(row):
                continue
            if self._bench_filter != ALL_BENCHES and str(row.bench_path) != self._bench_filter:
                continue
            rows_by_bench.setdefault(row.bench_path, []).append(row)

        insert_at = max(0, self._sections_layout.count() - 1)
        total_visible = 0
        for bench_path in self._bench_paths:
            if self._bench_filter != ALL_BENCHES and str(bench_path) != self._bench_filter:
                continue
            rows = rows_by_bench.get(bench_path, [])
            if not rows and self._filter:
                continue
            section = BenchSection(bench_path, item_label="app")
            cards: list[QWidget] = [
                AppCard(r.bench_path, r.app, read_only=True, show_bench_path=False) for r in rows
            ]
            section.set_cards(cards)
            self._sections_layout.insertWidget(insert_at, section)
            insert_at += 1
            total_visible += len(rows)

        has_any = bool(self._rows)
        has_match = total_visible > 0
        self._scroll.setVisible(has_match)
        self._empty.setVisible(not has_match)
        if not has_any:
            self._empty.setText(
                "<p>No apps registered yet.</p>"
                "<p style='color:#a9a9c4;'>"
                "Open a bench from the Benches tab and use "
                "<b>+ Get app</b> or <b>+ New app</b> to add one."
                "</p>"
            )
        elif not has_match:
            criteria = self._filter or "your filters"
            self._empty.setText(
                f"<p>No apps match <b>{criteria}</b>.</p>"
                "<p style='color:#a9a9c4;'>Try a different search term, switch bench, "
                "or clear the filters.</p>"
            )

    def _matches(self, row: _Row) -> bool:
        if not self._filter:
            return True
        haystack = f"{row.app.name}\n{row.bench_path}".lower()
        return all(token in haystack for token in self._filter.split())
