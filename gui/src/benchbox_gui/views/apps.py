"""Apps tab — per-bench app cards with per-card uninstall / remove actions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from benchbox_core import app as core_app
from benchbox_core import discovery, introspect
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.widgets.app_card import AppCard
from benchbox_gui.widgets.card_grid import CardGrid
from benchbox_gui.widgets.dialogs import (
    GetAppDialog,
    GetAppValues,
    InstallAppDialog,
    InstallAppValues,
    TypedNameConfirmDialog,
)
from benchbox_gui.workers import OperationWorker


@dataclass(frozen=True)
class _Row:
    bench_path: Path
    app: introspect.AppInfo


class AppsView(QWidget):
    """Lists every (bench, app) as a card with per-card actions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: OperationWorker | None = None
        self._progress: QProgressDialog | None = None
        self._rows: list[_Row] = []
        self._bench_cache: dict[Path, introspect.BenchInfo] = {}

        title = QLabel("Apps")
        title.setProperty("role", "h1")
        subtitle = QLabel("Apps registered across every bench on this machine")
        subtitle.setProperty("role", "dim")

        refresh = QPushButton("Refresh")
        refresh.setProperty("role", "ghost")
        refresh.clicked.connect(self.refresh)

        get_app_btn = QPushButton("+ Get app")
        get_app_btn.setProperty("role", "primary")
        get_app_btn.clicked.connect(self._on_get_app)

        install_btn = QPushButton("Install on site")
        install_btn.clicked.connect(self._on_install_app)

        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        header = QHBoxLayout()
        header.addLayout(header_text, 1)
        header.addWidget(refresh, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(install_btn, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(get_app_btn, 0, Qt.AlignmentFlag.AlignTop)

        self._grid = CardGrid()
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self._grid)
        self._scroll.setFrameShape(self._scroll.Shape.NoFrame)

        self._empty = QLabel(
            "<p>No apps registered yet.</p>"
            "<p style='color:#a9a9c4;'>Use <b>+ Get app</b> to fetch one into a bench.</p>"
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

    def refresh(self) -> None:
        self._bench_cache = {p: introspect.introspect(p) for p in discovery.discover_benches()}
        self._rows = [
            _Row(bench_path=info.path, app=app)
            for info in self._bench_cache.values()
            for app in info.apps
        ]

        cards: list[QWidget] = []
        for row in self._rows:
            card = AppCard(row.bench_path, row.app)
            card.uninstall_requested.connect(self._on_uninstall_requested)
            card.remove_requested.connect(self._on_remove_requested)
            cards.append(card)
        self._grid.set_cards(cards)

        has_rows = bool(self._rows)
        self._scroll.setVisible(has_rows)
        self._empty.setVisible(not has_rows)

    def _benches(self) -> list[Path]:
        return list(self._bench_cache.keys())

    def _sites_by_bench(self) -> dict[Path, list[str]]:
        return {path: [s.name for s in info.sites] for path, info in self._bench_cache.items()}

    def _apps_by_bench(self) -> dict[Path, list[str]]:
        return {path: [a.name for a in info.apps] for path, info in self._bench_cache.items()}

    # --- actions: get / install -------------------------------------

    def _on_get_app(self) -> None:
        benches = self._benches()
        if not benches:
            QMessageBox.information(self, "No benches", "Create a bench first.")
            return
        dialog = GetAppDialog(benches, parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._start_get_app(dialog.values())

    def _start_get_app(self, values: GetAppValues) -> None:
        self._open_progress("Fetching app…")

        def op() -> core_app.GetAppResult:
            return core_app.get_app(values.bench_path, values.git_url, branch=values.branch)

        self._spawn(op, success_msg="App fetched.")

    def _on_install_app(self) -> None:
        if not self._bench_cache:
            QMessageBox.information(self, "No benches", "Create a bench first.")
            return
        dialog = InstallAppDialog(
            self._sites_by_bench(),
            self._apps_by_bench(),
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._start_install_app(dialog.values())

    def _start_install_app(self, values: InstallAppValues) -> None:
        self._open_progress(f"Installing {', '.join(values.apps)} on {values.site_name}…")

        def op() -> core_app.InstallAppResult:
            return core_app.install_app(
                values.bench_path,
                values.site_name,
                list(values.apps),
                force=values.force,
            )

        self._spawn(op, success_msg=f"Installed {', '.join(values.apps)} on {values.site_name}.")

    # --- actions: uninstall from site (per-card) --------------------

    def _on_uninstall_requested(self, bench_path: Path, app_name: str) -> None:
        bench_info = self._bench_cache.get(bench_path)
        if bench_info is None or not bench_info.sites:
            QMessageBox.information(
                self,
                "No sites",
                f"{bench_path} has no sites to uninstall {app_name} from.",
            )
            return

        site_names = [s.name for s in bench_info.sites]
        site, ok = QInputDialog.getItem(
            self,
            "Uninstall app",
            f"Uninstall <b>{app_name}</b> from which site on <code>{bench_path}</code>?",
            site_names,
            0,
            False,
        )
        if not ok or not site:
            return

        confirm_target = f"{app_name}@{site}"
        dialog = TypedNameConfirmDialog(
            confirm_target,
            title="Uninstall app",
            message=(
                f"This detaches <b>{app_name}</b> from <b>{site}</b>, including "
                "any data the app owns on that site. The app stays in the "
                "bench's <code>apps/</code> directory."
            ),
            action_label="Uninstall",
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        self._start_uninstall_app(bench_path, site, app_name)

    def _start_uninstall_app(self, bench_path: Path, site: str, app_name: str) -> None:
        self._open_progress(f"Uninstalling {app_name} from {site}…")

        def op() -> core_app.UninstallAppResult:
            return core_app.uninstall_app(bench_path, site, app_name)

        self._spawn(op, success_msg=f"Uninstalled {app_name} from {site}.")

    # --- actions: remove from bench (per-card) ----------------------

    def _on_remove_requested(self, bench_path: Path, app_name: str) -> None:
        dialog = TypedNameConfirmDialog(
            app_name,
            title="Remove app from bench",
            message=(
                f"This removes <b>{app_name}</b> entirely from <code>{bench_path}</code>. "
                "Sites that still have it installed will continue to work at runtime, "
                "but <code>bench get-app</code> is what puts it back. This can't be undone."
            ),
            action_label="Remove from bench",
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        self._start_remove_app(bench_path, app_name)

    def _start_remove_app(self, bench_path: Path, app_name: str) -> None:
        self._open_progress(f"Removing {app_name} from bench…")

        def op() -> core_app.RemoveAppResult:
            return core_app.remove_app(bench_path, app_name)

        self._spawn(op, success_msg=f"Removed {app_name} from bench.")

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
