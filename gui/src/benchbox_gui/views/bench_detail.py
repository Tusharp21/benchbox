"""Detail view for a single bench — metadata, apps, sites, actions."""

from __future__ import annotations

from pathlib import Path

from benchbox_core import credentials, introspect
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.services.bench_processes import BenchProcessManager
from benchbox_gui.widgets.bench_actions import (
    BenchActionRow,
    BenchProcessPanel,
    open_in_file_manager,
)
from benchbox_gui.widgets.dialogs import (
    GetAppDialog,
    NewAppDialog,
    NewSiteDialog,
    RestoreSiteDialog,
)


class BenchDetailView(QWidget):
    """Reads metadata via introspect + renders apps/sites tables + actions."""

    back_requested = Signal()

    def __init__(
        self,
        process_manager: BenchProcessManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._current_path: Path | None = None

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

        # Process panel is now a subscriber to the shared manager; it
        # doesn't own the QProcess, so switching benches / going back
        # doesn't kill anything.
        self._process = BenchProcessPanel(process_manager)
        self._process.started.connect(lambda: self._actions.set_running(True))
        self._process.stopped.connect(lambda: self._actions.set_running(False))

        self._apps = QTableWidget(0, 3)
        self._apps.setHorizontalHeaderLabels(["name", "version", "branch"])
        self._apps.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._apps.verticalHeader().setVisible(False)
        self._apps.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._apps.setMinimumHeight(300)

        self._sites = QTableWidget(0, 3)
        self._sites.setHorizontalHeaderLabels(["site", "db name", "apps"])
        self._sites.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._sites.verticalHeader().setVisible(False)
        self._sites.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._sites.setMinimumHeight(300)

        apps_box = QGroupBox("Apps")
        apps_layout = QVBoxLayout(apps_box)
        apps_layout.setContentsMargins(8, 8, 8, 8)
        apps_layout.addWidget(self._apps)
        apps_box.setMinimumHeight(340)

        sites_box = QGroupBox("Sites")
        sites_layout = QVBoxLayout(sites_box)
        sites_layout.setContentsMargins(8, 8, 8, 8)
        sites_layout.addWidget(self._sites)
        sites_box.setMinimumHeight(340)

        # Apps + Sites share a row so the user can see both at a glance
        # without scrolling past the process log.
        apps_sites_row = QHBoxLayout()
        apps_sites_row.setSpacing(12)
        apps_sites_row.addWidget(apps_box, 1)
        apps_sites_row.addWidget(sites_box, 1)

        process_box = QGroupBox("Bench process")
        process_layout = QVBoxLayout(process_box)
        process_layout.setContentsMargins(8, 8, 8, 8)
        process_layout.addWidget(self._process)
        # Give the log a tall minimum so it stays legible even when the
        # apps/sites row below is also fighting for vertical space.
        process_box.setMinimumHeight(360)

        # The whole detail view is scrollable: the three panes below can
        # easily overflow a short window (apps + sites tables each want
        # ~340px, and the process log wants ~360px). Wrapping in a scroll
        # area keeps tables usably large without clipping or cramming.
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

        # Let the scroll area expand to fill whatever space this view gets
        # in the main window.
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(scroll)

    # --- loading ------------------------------------------------------

    def load(self, path: Path) -> None:
        self._current_path = path
        info = introspect.introspect(path)
        # Pass the webserver port so the panel can render the right URL
        # link (one bench uses 8000, another might use 8001, etc.).
        self._process.set_bench(path, webserver_port=info.webserver_port)
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
        db_root = self._ensure_mariadb_password()
        if db_root is None:
            return
        # NewSiteDialog is a LiveLogDialog: it owns the worker, so we
        # only refresh on Accepted (op finished cleanly).
        dialog = NewSiteDialog(
            [self._current_path],
            db_root_password=db_root,
            preselect=self._current_path,
            parent=self,
        )
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.load(self._current_path)

    def _on_get_app(self) -> None:
        if self._current_path is None:
            return
        dialog = GetAppDialog([self._current_path], preselect=self._current_path, parent=self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.load(self._current_path)

    def _on_new_app(self) -> None:
        if self._current_path is None:
            return
        dialog = NewAppDialog([self._current_path], preselect=self._current_path, parent=self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.load(self._current_path)

    def _on_restore_site(self) -> None:
        if self._current_path is None:
            return
        info = introspect.introspect(self._current_path)
        sites = [s.name for s in info.sites]
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
            self.load(self._current_path)

