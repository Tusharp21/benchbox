"""Apps tab — per-bench apps list + get/install/uninstall actions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from benchbox_core import app as core_app
from benchbox_core import discovery, introspect
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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

from benchbox_gui.widgets.dialogs import (
    GetAppDialog,
    GetAppValues,
    InstallAppDialog,
    InstallAppValues,
    confirm,
)
from benchbox_gui.workers import OperationWorker


@dataclass(frozen=True)
class _Row:
    bench_path: Path
    app: introspect.AppInfo


class AppsView(QWidget):
    """Lists apps per bench + get/install/uninstall actions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: OperationWorker | None = None
        self._progress: QProgressDialog | None = None
        self._rows: list[_Row] = []
        self._bench_cache: dict[Path, introspect.BenchInfo] = {}

        title = QLabel("Apps")
        title.setProperty("role", "h1")
        subtitle = QLabel("Apps registered per bench (across all benches)")
        subtitle.setProperty("role", "dim")

        refresh = QPushButton("Refresh")
        refresh.setProperty("role", "ghost")
        refresh.clicked.connect(self.refresh)

        get_app = QPushButton("+ Get app")
        get_app.setProperty("role", "primary")
        get_app.clicked.connect(self._on_get_app)

        install = QPushButton("Install on site")
        install.clicked.connect(self._on_install_app)

        uninstall = QPushButton("Uninstall from site")
        uninstall.clicked.connect(self._on_uninstall_app)

        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        header = QHBoxLayout()
        header.addLayout(header_text, 1)
        header.addWidget(refresh, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(uninstall, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(install, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(get_app, 0, Qt.AlignmentFlag.AlignTop)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["bench", "app", "version", "branch"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        self._empty = QLabel(
            "<p>No apps registered yet.</p>"
            "<p style='color:#a9a9c4;'>Use <b>+ Get app</b> to fetch one into a bench.</p>"
        )
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)
        root.addLayout(header)
        root.addWidget(self._table, 1)
        root.addWidget(self._empty)

        self.refresh()

    # --- data --------------------------------------------------------

    def refresh(self) -> None:
        self._bench_cache = {p: introspect.introspect(p) for p in discovery.discover_benches()}
        self._rows = [
            _Row(bench_path=info.path, app=app)
            for info in self._bench_cache.values()
            for app in info.apps
        ]

        self._table.setRowCount(0)
        for row in self._rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            self._table.setItem(r, 0, QTableWidgetItem(str(row.bench_path)))
            self._table.setItem(r, 1, QTableWidgetItem(row.app.name))
            self._table.setItem(r, 2, QTableWidgetItem(row.app.version or "-"))
            self._table.setItem(r, 3, QTableWidgetItem(row.app.git_branch or "-"))
        has_rows = bool(self._rows)
        self._table.setVisible(has_rows)
        self._empty.setVisible(not has_rows)

    def _benches(self) -> list[Path]:
        return list(self._bench_cache.keys())

    def _sites_by_bench(self) -> dict[Path, list[str]]:
        return {path: [s.name for s in info.sites] for path, info in self._bench_cache.items()}

    def _apps_by_bench(self) -> dict[Path, list[str]]:
        return {path: [a.name for a in info.apps] for path, info in self._bench_cache.items()}

    def _selected_row(self) -> _Row | None:
        selection = self._table.selectedItems()
        if not selection:
            return None
        idx = selection[0].row()
        if 0 <= idx < len(self._rows):
            return self._rows[idx]
        return None

    # --- actions -----------------------------------------------------

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
        sel = self._selected_row()
        dialog = InstallAppDialog(
            self._sites_by_bench(),
            self._apps_by_bench(),
            parent=self,
            preselect_bench=sel.bench_path if sel is not None else None,
            preselect_app=sel.app.name if sel is not None else None,
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

    def _on_uninstall_app(self) -> None:
        row = self._selected_row()
        if row is None:
            QMessageBox.information(self, "No selection", "Select an app row first.")
            return
        if row.app.name == "frappe":
            QMessageBox.warning(
                self, "Cannot uninstall frappe", "frappe is required on every bench."
            )
            return
        # Ask which site to uninstall from.
        bench_info = self._bench_cache.get(row.bench_path)
        if bench_info is None or not bench_info.sites:
            QMessageBox.information(self, "No sites", "This bench has no sites to uninstall from.")
            return
        from PySide6.QtWidgets import QInputDialog

        site_names = [s.name for s in bench_info.sites]
        site, ok = QInputDialog.getItem(
            self,
            "Uninstall app",
            f"Uninstall {row.app.name} from which site?",
            site_names,
            0,
            False,
        )
        if not ok or not site:
            return
        if not confirm(
            self,
            "Uninstall app",
            f"Remove <b>{row.app.name}</b> from <b>{site}</b>?",
            destructive=True,
        ):
            return

        self._open_progress(f"Uninstalling {row.app.name} from {site}…")

        def op() -> core_app.UninstallAppResult:
            return core_app.uninstall_app(row.bench_path, site, row.app.name)

        self._spawn(op, success_msg=f"Uninstalled {row.app.name} from {site}.")

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
