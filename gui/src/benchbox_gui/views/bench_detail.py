"""Detail view for a single bench — single home for every mutating action.

Top of the view: bench metadata + an action row (Start / Stop / Open
folder / + New site / + Get app / + New app / Restore).

Below: a process-log panel, then two side-by-side card grids — Apps and
Sites — using the same :class:`AppCard` / :class:`SiteCard` widgets as
the read-only Apps / Sites tabs. Every per-card action (Install on
site, Uninstall, Remove, Drop) is wired through the bench-detail
handlers here, so the global tabs can stay informational and this page
becomes the single place to act on a bench.
"""

from __future__ import annotations

from pathlib import Path

from benchbox_core import app as core_app
from benchbox_core import credentials, discovery, introspect
from benchbox_core import site as core_site
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.services.bench_processes import BenchProcessManager
from benchbox_gui.widgets.app_card import AppCard
from benchbox_gui.widgets.bench_actions import (
    BenchActionRow,
    BenchProcessPanel,
    open_in_file_manager,
)
from benchbox_gui.widgets.card_grid import CardGrid
from benchbox_gui.widgets.dialogs import (
    GetAppDialog,
    InstallAppDialog,
    NewAppDialog,
    NewSiteDialog,
    RestoreSiteDialog,
    TypedNameConfirmDialog,
)
from benchbox_gui.widgets.site_card import SiteCard
from benchbox_gui.workers import OperationWorker


class BenchDetailView(QWidget):
    """Single home for every per-bench mutation."""

    back_requested = Signal()

    def __init__(
        self,
        process_manager: BenchProcessManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._current_path: Path | None = None
        self._info: introspect.BenchInfo | None = None
        # short-op spinner for fast mutations (drop / uninstall / remove);
        # long-running ones use the live-log dialogs and don't touch this.
        self._worker: OperationWorker | None = None
        self._progress: QProgressDialog | None = None

        back = QPushButton("← back to benches")
        back.setProperty("role", "ghost")
        back.clicked.connect(self.back_requested.emit)
        header_row = QHBoxLayout()
        header_row.addWidget(back)
        header_row.addStretch(1)

        self._title = QLabel()
        self._title.setProperty("role", "h1")
        self._meta = QLabel()
        self._meta.setTextFormat(self._meta.textFormat().RichText)

        self._actions = BenchActionRow()
        self._actions.start_requested.connect(self._on_start)
        self._actions.stop_requested.connect(self._on_stop)
        self._actions.open_folder_requested.connect(self._on_open_folder)
        self._actions.new_site_requested.connect(self._on_new_site)
        self._actions.get_app_requested.connect(self._on_get_app)
        self._actions.new_app_requested.connect(self._on_new_app)
        self._actions.restore_site_requested.connect(self._on_restore_site)

        self._process = BenchProcessPanel(process_manager)
        self._process.started.connect(lambda: self._actions.set_running(True))
        self._process.stopped.connect(lambda: self._actions.set_running(False))

        # Card grids for apps and sites — same widgets the read-only tabs
        # use, but mutating actions stay enabled here.
        self._apps_grid = CardGrid()
        self._sites_grid = CardGrid()

        apps_box = QGroupBox("Apps")
        apps_layout = QVBoxLayout(apps_box)
        apps_layout.setContentsMargins(8, 8, 8, 8)
        apps_layout.addWidget(self._apps_grid)
        apps_box.setMinimumHeight(340)

        sites_box = QGroupBox("Sites")
        sites_layout = QVBoxLayout(sites_box)
        sites_layout.setContentsMargins(8, 8, 8, 8)
        sites_layout.addWidget(self._sites_grid)
        sites_box.setMinimumHeight(340)

        apps_sites_row = QHBoxLayout()
        apps_sites_row.setSpacing(12)
        apps_sites_row.addWidget(apps_box, 1)
        apps_sites_row.addWidget(sites_box, 1)

        process_box = QGroupBox("Bench process")
        process_layout = QVBoxLayout(process_box)
        process_layout.setContentsMargins(8, 8, 8, 8)
        process_layout.addWidget(self._process)
        process_box.setMinimumHeight(360)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 16, 20, 16)
        content_layout.setSpacing(12)
        content_layout.addLayout(header_row)
        content_layout.addWidget(self._title)
        content_layout.addWidget(self._meta)
        content_layout.addWidget(self._actions)
        content_layout.addWidget(process_box)
        content_layout.addLayout(apps_sites_row)
        content_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(scroll)

    # --- loading ------------------------------------------------------

    def load(self, path: Path) -> None:
        self._current_path = path
        self._info = introspect.introspect(path)
        info = self._info
        self._process.set_bench(path, webserver_port=info.webserver_port)
        self._title.setText(str(info.path))
        self._meta.setText(
            "<table cellpadding='2'>"
            f"<tr><td><b>frappe</b></td><td>{info.frappe_version or '-'}</td></tr>"
            f"<tr><td><b>python</b></td><td>{info.python_version or '-'}</td></tr>"
            f"<tr><td><b>branch</b></td><td>{info.git_branch or '-'}</td></tr>"
            "</table>"
        )

        # Populate apps grid with action-enabled cards.
        app_cards: list[QWidget] = []
        for app in info.apps:
            card = AppCard(path, app)
            card.install_requested.connect(self._on_install_from_app_card)
            card.uninstall_requested.connect(self._on_uninstall_requested)
            card.remove_requested.connect(self._on_remove_requested)
            app_cards.append(card)
        self._apps_grid.set_cards(app_cards)

        # Populate sites grid with action-enabled cards.
        site_cards: list[QWidget] = []
        for site in info.sites:
            card = SiteCard(path, site)
            card.install_app_requested.connect(self._on_install_app_on_site)
            card.drop_requested.connect(self._on_drop_site)
            site_cards.append(card)
        self._sites_grid.set_cards(site_cards)

    # --- bench-process actions ---------------------------------------

    def _on_start(self) -> None:
        self._process.start()

    def _on_stop(self) -> None:
        self._process.stop()

    def _on_open_folder(self) -> None:
        if self._current_path is not None:
            open_in_file_manager(self._current_path)

    # --- shared helpers ----------------------------------------------

    def _ensure_mariadb_password(self) -> str | None:
        saved = credentials.get_mariadb_root_password()
        if saved is not None:
            return saved
        QMessageBox.warning(
            self,
            "MariaDB password missing",
            "No MariaDB root password is saved yet. Run the installer "
            "from the sidebar once to set it.",
        )
        return None

    def _refresh_after_op(self) -> None:
        if self._current_path is not None:
            self.load(self._current_path)

    # --- top action-row handlers (long ops via LiveLogDialog) --------

    def _on_new_site(self) -> None:
        if self._current_path is None:
            return
        db_root = self._ensure_mariadb_password()
        if db_root is None:
            return
        dialog = NewSiteDialog(
            [self._current_path],
            db_root_password=db_root,
            preselect=self._current_path,
            parent=self,
        )
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._refresh_after_op()

    def _on_get_app(self) -> None:
        if self._current_path is None:
            return
        dialog = GetAppDialog([self._current_path], preselect=self._current_path, parent=self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._refresh_after_op()

    def _on_new_app(self) -> None:
        if self._current_path is None:
            return
        dialog = NewAppDialog([self._current_path], preselect=self._current_path, parent=self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._refresh_after_op()

    def _on_restore_site(self) -> None:
        if self._current_path is None or self._info is None:
            return
        sites = [s.name for s in self._info.sites]
        if not sites:
            QMessageBox.information(
                self,
                "No sites",
                "This bench has no sites to restore into. Create a site first.",
            )
            return
        db_root = self._ensure_mariadb_password()
        if db_root is None:
            return
        dialog = RestoreSiteDialog(
            {self._current_path: sites},
            db_root_password=db_root,
            parent=self,
            preselect_bench=self._current_path,
        )
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._refresh_after_op()

    # --- per-card actions: install (long) ---------------------------

    def _on_install_from_app_card(self, bench_path: Path, app_name: str) -> None:
        self._open_install_dialog(preselect_bench=bench_path, preselect_app=app_name)

    def _on_install_app_on_site(self, bench_path: Path, site_name: str) -> None:
        self._open_install_dialog(preselect_bench=bench_path, preselect_site=site_name)

    def _open_install_dialog(
        self,
        *,
        preselect_bench: Path | None = None,
        preselect_site: str | None = None,
        preselect_app: str | None = None,
    ) -> None:
        if self._current_path is None or self._info is None:
            return
        bench_sites = {self._current_path: [s.name for s in self._info.sites]}
        bench_apps = {self._current_path: [a.name for a in self._info.apps]}
        dialog = InstallAppDialog(
            bench_sites,
            bench_apps,
            preselect_bench=preselect_bench or self._current_path,
            preselect_site=preselect_site,
            preselect_app=preselect_app,
            parent=self,
        )
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._refresh_after_op()

    # --- per-card actions: uninstall / remove / drop (fast → spinner)

    def _on_uninstall_requested(self, bench_path: Path, app_name: str) -> None:
        if self._info is None:
            return
        site_names = [s.name for s in self._info.sites]
        if not site_names:
            QMessageBox.information(
                self,
                "No sites",
                f"{bench_path} has no sites to uninstall {app_name} from.",
            )
            return
        site, ok = QInputDialog.getItem(
            self,
            "Uninstall app",
            f"Uninstall <b>{app_name}</b> from which site?",
            site_names,
            0,
            False,
        )
        if not ok or not site:
            return
        confirm_target = f"{app_name}@{site}"
        confirm = TypedNameConfirmDialog(
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
        if confirm.exec() != confirm.DialogCode.Accepted:
            return
        self._open_progress(f"Uninstalling {app_name} from {site}…")
        self._spawn(
            lambda: core_app.uninstall_app(bench_path, site, app_name),
            success_msg=f"Uninstalled {app_name} from {site}.",
        )

    def _on_remove_requested(self, bench_path: Path, app_name: str) -> None:
        confirm = TypedNameConfirmDialog(
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
        if confirm.exec() != confirm.DialogCode.Accepted:
            return
        self._open_progress(f"Removing {app_name} from bench…")
        self._spawn(
            lambda: core_app.remove_app(bench_path, app_name),
            success_msg=f"Removed {app_name} from bench.",
        )

    def _on_drop_site(self, bench_path: Path, site_name: str) -> None:
        confirm = TypedNameConfirmDialog(
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
        if confirm.exec() != confirm.DialogCode.Accepted:
            return
        db_root = self._ensure_mariadb_password()
        if db_root is None:
            return
        self._open_progress(f"Dropping {site_name}…")
        self._spawn(
            lambda: core_site.drop_site(bench_path, site_name, db_root_password=db_root),
            success_msg=f"Site {site_name!r} dropped.",
        )

    # --- spinner plumbing for fast mutations -------------------------

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
        self._worker.succeeded.connect(lambda _r, msg=success_msg: self._on_short_op_success(msg))
        self._worker.failed.connect(self._on_short_op_failure)
        self._worker.start()

    def _on_short_op_success(self, message: str) -> None:
        self._close_progress()
        self._refresh_after_op()
        QMessageBox.information(self, "Done", message)

    def _on_short_op_failure(self, exc: object) -> None:
        self._close_progress()
        QMessageBox.critical(self, "Operation failed", f"{exc}")


# Re-export discovery for any caller that previously imported it from
# this module by accident; keeps refactor surface small.
__all__ = ["BenchDetailView", "discovery"]
