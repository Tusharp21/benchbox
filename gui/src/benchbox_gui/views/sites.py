"""Sites tab — cross-bench site cards with typed-name drop confirmation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from benchbox_core import credentials, discovery, introspect
from benchbox_core import site as core_site
from PySide6.QtCore import Qt
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

from benchbox_gui.widgets.card_grid import CardGrid
from benchbox_gui.widgets.dialogs import (
    InstallAppDialog,
    NewSiteDialog,
    TypedNameConfirmDialog,
)
from benchbox_gui.widgets.site_card import SiteCard
from benchbox_gui.workers import OperationWorker


@dataclass(frozen=True)
class _Row:
    bench_path: Path
    site: introspect.SiteInfo


class SitesView(QWidget):
    """Lists every site across every discovered bench as cards."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: OperationWorker | None = None
        self._progress: QProgressDialog | None = None
        self._rows: list[_Row] = []
        self._bench_cache: dict[Path, introspect.BenchInfo] = {}

        title = QLabel("Sites")
        title.setProperty("role", "h1")
        subtitle = QLabel("Sites across every bench on this machine")
        subtitle.setProperty("role", "dim")

        refresh = QPushButton("Refresh")
        refresh.setProperty("role", "ghost")
        refresh.clicked.connect(self.refresh)

        new_site = QPushButton("+ New site")
        new_site.setProperty("role", "primary")
        new_site.clicked.connect(self._on_new_site)

        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        header = QHBoxLayout()
        header.addLayout(header_text, 1)
        header.addWidget(refresh, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(new_site, 0, Qt.AlignmentFlag.AlignTop)

        self._grid = CardGrid()
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self._grid)
        self._scroll.setFrameShape(self._scroll.Shape.NoFrame)

        self._empty = QLabel(
            "<p>No sites yet.</p>"
            "<p style='color:#a9a9c4;'>Create one with <b>+ New site</b> after "
            "you have a bench.</p>"
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

    # --- data --------------------------------------------------------

    @property
    def card_count(self) -> int:
        return self._grid.card_count()

    def _load_rows(self) -> list[_Row]:
        self._bench_cache = {p: introspect.introspect(p) for p in discovery.discover_benches()}
        return [
            _Row(bench_path=info.path, site=site)
            for info in self._bench_cache.values()
            for site in info.sites
        ]

    def refresh(self) -> None:
        self._rows = self._load_rows()
        cards: list[QWidget] = []
        for row in self._rows:
            card = SiteCard(row.bench_path, row.site)
            card.install_app_requested.connect(self._on_install_app_on_site)
            card.drop_requested.connect(self._on_drop_site)
            cards.append(card)
        self._grid.set_cards(cards)

        has_rows = bool(self._rows)
        self._scroll.setVisible(has_rows)
        self._empty.setVisible(not has_rows)

    # --- actions -----------------------------------------------------

    def _ensure_password(self) -> str | None:
        pw = credentials.get_mariadb_root_password()
        if pw is None:
            QMessageBox.warning(
                self,
                "MariaDB password missing",
                "Run the installer once from the sidebar to set the MariaDB root password.",
            )
        return pw

    def _on_new_site(self) -> None:
        if not self._bench_cache:
            self._bench_cache = {p: introspect.introspect(p) for p in discovery.discover_benches()}
        benches = list(self._bench_cache.keys())
        if not benches:
            QMessageBox.information(self, "No benches", "Create a bench first.")
            return
        pw = self._ensure_password()
        if pw is None:
            return
        # NewSiteDialog is a LiveLogDialog: it owns the worker and log,
        # so we just refresh on Accepted.
        dialog = NewSiteDialog(
            benches,
            db_root_password=pw,
            parent=self,
            apps_by_bench={p: [a.name for a in i.apps] for p, i in self._bench_cache.items()},
        )
        if dialog.exec() == dialog.DialogCode.Accepted:
            # Force re-introspection — the new site won't be in the cache.
            self._bench_cache.clear()
            self.refresh()

    def _on_install_app_on_site(self, bench_path: Path, site_name: str) -> None:
        """Per-card '+ Install app' on SiteCard — preselect this site + bench."""
        if not self._bench_cache:
            self._bench_cache = {p: introspect.introspect(p) for p in discovery.discover_benches()}
        bench_sites = {p: [s.name for s in i.sites] for p, i in self._bench_cache.items()}
        bench_apps = {p: [a.name for a in i.apps] for p, i in self._bench_cache.items()}
        dialog = InstallAppDialog(
            bench_sites,
            bench_apps,
            preselect_bench=bench_path,
            preselect_site=site_name,
            parent=self,
        )
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._bench_cache.clear()
            self.refresh()

    def _on_drop_site(self, bench_path: Path, site_name: str) -> None:
        """Triggered from a SiteCard's Drop button — typed-name confirm."""
        dialog = TypedNameConfirmDialog(
            site_name,
            title="Drop site",
            message=(
                f"This permanently deletes <b>{site_name}</b> on "
                f"<code>{bench_path}</code>, including its MariaDB database. "
                "This can't be undone."
            ),
            action_label="Drop site",
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        pw = self._ensure_password()
        if pw is None:
            return
        self._start_drop(bench_path, site_name, pw)

    def _start_drop(self, bench_path: Path, site_name: str, db_root: str) -> None:
        self._open_progress(f"Dropping {site_name}…")

        def op() -> core_site.SiteDropResult:
            return core_site.drop_site(bench_path, site_name, db_root_password=db_root)

        self._spawn(op, success_msg=f"Site {site_name!r} dropped.")

    # --- worker plumbing --------------------------------------------

    def _open_progress(self, message: str) -> None:
        self._progress = QProgressDialog(self)
        self._progress.setLabelText(message)
        self._progress.setWindowTitle("Working…")
        self._progress.setMinimum(0)
        self._progress.setMaximum(0)
        self._progress.setMinimumDuration(0)
        self._progress.setCancelButton(None)
        self._progress.show()

    def _close_progress(self) -> None:
        if self._progress is not None:
            self._progress.close()
            self._progress = None

    def _spawn(self, op: object, *, success_msg: str) -> None:
        self._worker = OperationWorker(op)  # type: ignore[arg-type]
        self._worker.succeeded.connect(lambda _r, msg=success_msg: self._on_success(msg))
        self._worker.failed.connect(self._on_failure)
        self._worker.start()

    def _on_success(self, message: str) -> None:
        self._close_progress()
        self.refresh()
        QMessageBox.information(self, "Done", message)

    def _on_failure(self, exc: object) -> None:
        self._close_progress()
        QMessageBox.critical(self, "Operation failed", f"{exc}")
