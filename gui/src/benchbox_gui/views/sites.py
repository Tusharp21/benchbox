"""Sites tab — dashboard view: KPIs + per-bench summary cards."""

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

from benchbox_gui.widgets.bench_summary_card import BenchSummaryCard, SiteRow
from benchbox_gui.widgets.busy_label import BusyLabel
from benchbox_gui.widgets.card_grid import CardGrid
from benchbox_gui.widgets.kpi_card import KpiCard
from benchbox_gui.workers import OperationWorker

ALL_BENCHES = "__all__"


@dataclass(frozen=True)
class _Row:
    bench_path: Path
    site: introspect.SiteInfo


class SitesView(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[_Row] = []
        self._bench_paths: list[Path] = []
        self._filter: str = ""
        self._bench_filter: str = ALL_BENCHES
        self._load_worker: OperationWorker | None = None

        title = QLabel("Sites")
        title.setProperty("role", "h1")
        subtitle = QLabel(
            "All sites grouped by bench. Open a bench from the Benches tab "
            "to create, drop, or restore a site."
        )
        subtitle.setProperty("role", "dim")
        subtitle.setWordWrap(True)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setProperty("role", "ghost")
        self._refresh_btn.clicked.connect(self.refresh)

        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        header = QHBoxLayout()
        header.addLayout(header_text, 1)
        header.addWidget(self._refresh_btn, 0, Qt.AlignmentFlag.AlignTop)

        self._kpi_benches = KpiCard("Benches", value="0", accent="#bd93f9")
        self._kpi_sites = KpiCard("Sites", value="0", accent="#8be9fd")
        self._kpi_paused = KpiCard("Scheduler paused", value="0", accent="#f1fa8c")
        self._kpi_maint = KpiCard("Maintenance on", value="0", accent="#ff5555")

        kpi_strip = QHBoxLayout()
        kpi_strip.setSpacing(12)
        kpi_strip.addWidget(self._kpi_benches, 1)
        kpi_strip.addWidget(self._kpi_sites, 1)
        kpi_strip.addWidget(self._kpi_paused, 1)
        kpi_strip.addWidget(self._kpi_maint, 1)

        filter_label = QLabel("Filter:")
        filter_label.setProperty("role", "dim")

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search by site name or bench path…")
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

        self._grid = CardGrid()
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self._grid)
        self._scroll.setFrameShape(self._scroll.Shape.NoFrame)

        self._empty = QLabel()
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)

        # Async "Loading sites…" indicator. The introspect loop walks every
        # bench's apps + sites trees, which can take seconds on a slow disk
        # — we don't want the GUI thread blocked while it does.
        self._loading = BusyLabel()
        self._loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading.setProperty("role", "dim")
        self._loading.setVisible(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)
        root.addLayout(header)
        root.addLayout(kpi_strip)
        root.addWidget(self._filter_bar)
        root.addWidget(self._scroll, 1)
        root.addWidget(self._empty)
        root.addWidget(self._loading)

        self.refresh()

    @property
    def card_count(self) -> int:
        return sum(c.row_count() for c in self._summary_cards())

    def refresh(self) -> None:
        if self._load_worker is not None and self._load_worker.isRunning():
            return

        self._show_loading()

        def op() -> dict[Path, introspect.BenchInfo]:
            return {p: introspect.introspect(p) for p in discovery.discover_benches()}

        self._load_worker = OperationWorker(op)
        self._load_worker.succeeded.connect(self._on_load_succeeded)
        self._load_worker.failed.connect(self._on_load_failed)
        self._load_worker.start()

    def _show_loading(self) -> None:
        self._refresh_btn.setEnabled(False)
        self._scroll.setVisible(False)
        self._empty.setVisible(False)
        self._loading.setVisible(True)
        self._loading.set_busy("Loading sites")

    def _hide_loading(self) -> None:
        self._loading.set_idle("")
        self._loading.setVisible(False)
        self._refresh_btn.setEnabled(True)

    def _on_load_succeeded(self, result: object) -> None:
        self._hide_loading()
        bench_cache = result if isinstance(result, dict) else {}
        self._bench_paths = sorted(bench_cache.keys(), key=lambda p: str(p).lower())
        self._rows = [
            _Row(bench_path=info.path, site=site)
            for info in bench_cache.values()
            for site in info.sites
        ]
        self._refresh_kpis()
        self._refresh_bench_combo()
        self._render()

    def _on_load_failed(self, exc: object) -> None:
        self._hide_loading()
        self._bench_paths = []
        self._rows = []
        self._refresh_kpis()
        self._refresh_bench_combo()
        self._render()
        self._empty.setText(
            f"<p>Could not load sites.</p>"
            f"<p style='color:#a9a9c4;'>{exc}</p>"
        )
        self._empty.setVisible(True)
        self._scroll.setVisible(False)

    def shutdown(self) -> None:
        if self._load_worker is not None and self._load_worker.isRunning():
            self._load_worker.quit()
            self._load_worker.wait(2000)

    def _summary_cards(self) -> list[BenchSummaryCard]:
        return self._grid.findChildren(BenchSummaryCard)

    def _refresh_kpis(self) -> None:
        self._kpi_benches.set_value(len(self._bench_paths))
        self._kpi_sites.set_value(len(self._rows))
        self._kpi_paused.set_value(sum(1 for r in self._rows if r.site.scheduler_paused))
        self._kpi_maint.set_value(sum(1 for r in self._rows if r.site.maintenance_mode))

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

    def _matches(self, row: _Row) -> bool:
        if not self._filter:
            return True
        haystack = f"{row.site.name}\n{row.bench_path}".lower()
        return all(token in haystack for token in self._filter.split())

    def _render(self) -> None:
        rows_by_bench: dict[Path, list[_Row]] = {p: [] for p in self._bench_paths}
        for row in self._rows:
            if not self._matches(row):
                continue
            if self._bench_filter != ALL_BENCHES and str(row.bench_path) != self._bench_filter:
                continue
            rows_by_bench.setdefault(row.bench_path, []).append(row)

        cards: list[QWidget] = []
        total_visible = 0
        for bench_path in self._bench_paths:
            if self._bench_filter != ALL_BENCHES and str(bench_path) != self._bench_filter:
                continue
            site_rows = rows_by_bench.get(bench_path, [])
            if not site_rows and self._filter:
                continue
            card = BenchSummaryCard(bench_path, item_label="site")
            card.set_rows([SiteRow(r.site) for r in site_rows])
            cards.append(card)
            total_visible += len(site_rows)

        self._grid.set_cards(cards)

        has_any = bool(self._rows)
        has_match = total_visible > 0
        self._scroll.setVisible(has_match)
        self._empty.setVisible(not has_match)
        if not has_any:
            self._empty.setText(
                "<p>No sites yet.</p>"
                "<p style='color:#a9a9c4;'>"
                "Open a bench from the Benches tab and use "
                "<b>+ New site</b> to create one."
                "</p>"
            )
        elif not has_match:
            criteria = self._filter or "your filters"
            self._empty.setText(
                f"<p>No sites match <b>{criteria}</b>.</p>"
                "<p style='color:#a9a9c4;'>Try a different search term, switch bench, "
                "or clear the filters.</p>"
            )
