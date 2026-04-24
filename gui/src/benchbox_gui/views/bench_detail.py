"""Detail view for a single bench — metadata, apps, sites, actions."""

from __future__ import annotations

from pathlib import Path

from benchbox_core import app as core_app
from benchbox_core import credentials, introspect
from benchbox_core import site as core_site
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.widgets.bench_actions import (
    BenchActionRow,
    BenchProcessPanel,
    open_in_file_manager,
)
from benchbox_gui.widgets.dialogs import (
    GetAppDialog,
    GetAppValues,
    NewSiteDialog,
    NewSiteValues,
)
from benchbox_gui.workers import OperationWorker


class BenchDetailView(QWidget):
    """Reads metadata via introspect + renders apps/sites tables + actions."""

    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_path: Path | None = None
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

        self._process = BenchProcessPanel()
        self._process.started.connect(lambda: self._actions.set_running(True))
        self._process.stopped.connect(lambda: self._actions.set_running(False))

        self._apps = QTableWidget(0, 3)
        self._apps.setHorizontalHeaderLabels(["name", "version", "branch"])
        self._apps.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._apps.verticalHeader().setVisible(False)
        self._apps.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self._sites = QTableWidget(0, 3)
        self._sites.setHorizontalHeaderLabels(["site", "db name", "apps"])
        self._sites.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._sites.verticalHeader().setVisible(False)
        self._sites.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        apps_box = QGroupBox("Apps")
        apps_layout = QVBoxLayout(apps_box)
        apps_layout.setContentsMargins(8, 8, 8, 8)
        apps_layout.addWidget(self._apps)

        sites_box = QGroupBox("Sites")
        sites_layout = QVBoxLayout(sites_box)
        sites_layout.setContentsMargins(8, 8, 8, 8)
        sites_layout.addWidget(self._sites)

        process_box = QGroupBox("Bench process")
        process_layout = QVBoxLayout(process_box)
        process_layout.setContentsMargins(8, 8, 8, 8)
        process_layout.addWidget(self._process)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addLayout(header_row)
        layout.addWidget(self._title)
        layout.addWidget(self._meta)
        layout.addWidget(self._actions)
        layout.addWidget(process_box, 1)
        layout.addWidget(apps_box, 1)
        layout.addWidget(sites_box, 1)

    # --- loading ------------------------------------------------------

    def load(self, path: Path) -> None:
        self._current_path = path
        self._process.set_bench(path)
        info = introspect.introspect(path)
        self._title.setText(str(info.path))
        self._meta.setText(
            "<table cellpadding='2'>"
            f"<tr><td><b>frappe</b></td><td>{info.frappe_version or '-'}</td></tr>"
            f"<tr><td><b>python</b></td><td>{info.python_version or '-'}</td></tr>"
            f"<tr><td><b>branch</b></td><td>{info.git_branch or '-'}</td></tr>"
            "</table>"
        )

        self._apps.setRowCount(0)
        for app in info.apps:
            row = self._apps.rowCount()
            self._apps.insertRow(row)
            self._apps.setItem(row, 0, QTableWidgetItem(app.name))
            self._apps.setItem(row, 1, QTableWidgetItem(app.version or "-"))
            self._apps.setItem(row, 2, QTableWidgetItem(app.git_branch or "-"))

        self._sites.setRowCount(0)
        for site in info.sites:
            row = self._sites.rowCount()
            self._sites.insertRow(row)
            self._sites.setItem(row, 0, QTableWidgetItem(site.name))
            self._sites.setItem(row, 1, QTableWidgetItem(site.db_name or "-"))
            self._sites.setItem(row, 2, QTableWidgetItem(", ".join(site.installed_apps) or "-"))

    # --- action handlers ---------------------------------------------

    def _on_start(self) -> None:
        self._process.start()

    def _on_stop(self) -> None:
        self._process.stop()

    def _on_open_folder(self) -> None:
        if self._current_path is not None:
            open_in_file_manager(self._current_path)

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

    def _on_new_site(self) -> None:
        if self._current_path is None:
            return
        dialog = NewSiteDialog([self._current_path], preselect=self._current_path, parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        values = dialog.values()
        db_root = self._ensure_mariadb_password()
        if db_root is None:
            return
        self._start_new_site(values, db_root)

    def _start_new_site(self, values: NewSiteValues, db_root: str) -> None:
        self._open_progress(f"Creating site {values.site_name}…")

        def op() -> core_site.SiteCreateResult:
            return core_site.create_site(
                values.bench_path,
                values.site_name,
                db_root_password=db_root,
                admin_password=values.admin_password,
                install_apps=values.install_apps,
                set_default=values.set_default,
            )

        self._spawn_worker(
            op,
            on_success=lambda _r: self._on_mutation_success(f"Site {values.site_name!r} created."),
            on_failure=lambda e: self._on_mutation_failed("Site creation failed", e),
        )

    def _on_get_app(self) -> None:
        if self._current_path is None:
            return
        dialog = GetAppDialog([self._current_path], preselect=self._current_path, parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self._start_get_app(values)

    def _start_get_app(self, values: GetAppValues) -> None:
        self._open_progress("Fetching app (this can take a few minutes)…")

        def op() -> core_app.GetAppResult:
            return core_app.get_app(values.bench_path, values.git_url, branch=values.branch)

        self._spawn_worker(
            op,
            on_success=lambda _r: self._on_mutation_success("App fetched."),
            on_failure=lambda e: self._on_mutation_failed("Fetching app failed", e),
        )

    # --- worker plumbing ---------------------------------------------

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

    def _spawn_worker(
        self,
        op: object,
        *,
        on_success: object,
        on_failure: object,
    ) -> None:
        self._worker = OperationWorker(op)  # type: ignore[arg-type]
        self._worker.succeeded.connect(on_success)
        self._worker.failed.connect(on_failure)
        self._worker.start()

    def _on_mutation_success(self, message: str) -> None:
        self._close_progress()
        if self._current_path is not None:
            self.load(self._current_path)
        QMessageBox.information(self, "Done", message)

    def _on_mutation_failed(self, title: str, exc: object) -> None:
        self._close_progress()
        QMessageBox.critical(self, title, f"{exc}")
