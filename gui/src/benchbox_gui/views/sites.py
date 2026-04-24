"""Sites tab — cross-bench site list + new/drop actions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from benchbox_core import credentials, discovery, introspect
from benchbox_core import site as core_site
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

from benchbox_gui.widgets.dialogs import NewSiteDialog, NewSiteValues, confirm
from benchbox_gui.workers import OperationWorker


@dataclass(frozen=True)
class _Row:
    bench_path: Path
    site: introspect.SiteInfo


class SitesView(QWidget):
    """Lists every site across every discovered bench + mutation actions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: OperationWorker | None = None
        self._progress: QProgressDialog | None = None
        self._rows: list[_Row] = []

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

        drop_site = QPushButton("Drop selected")
        drop_site.clicked.connect(self._on_drop_site)

        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        header = QHBoxLayout()
        header.addLayout(header_text, 1)
        header.addWidget(refresh, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(drop_site, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(new_site, 0, Qt.AlignmentFlag.AlignTop)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["bench", "site", "db name", "apps"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        self._empty = QLabel(
            "<p>No sites yet.</p>"
            "<p style='color:#a9a9c4;'>Create one with <b>+ New site</b> after you have "
            "a bench.</p>"
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

    def _load_rows(self) -> list[_Row]:
        rows: list[_Row] = []
        for bench_path in discovery.discover_benches():
            info = introspect.introspect(bench_path)
            for site in info.sites:
                rows.append(_Row(bench_path=info.path, site=site))
        return rows

    def refresh(self) -> None:
        self._rows = self._load_rows()
        self._table.setRowCount(0)
        for row in self._rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            self._table.setItem(r, 0, QTableWidgetItem(str(row.bench_path)))
            self._table.setItem(r, 1, QTableWidgetItem(row.site.name))
            self._table.setItem(r, 2, QTableWidgetItem(row.site.db_name or "-"))
            self._table.setItem(
                r,
                3,
                QTableWidgetItem(", ".join(row.site.installed_apps) or "-"),
            )
        has_rows = bool(self._rows)
        self._table.setVisible(has_rows)
        self._empty.setVisible(not has_rows)

    def _discovered_bench_paths(self) -> list[Path]:
        return [
            info.path for info in (introspect.introspect(p) for p in discovery.discover_benches())
        ]

    def _selected_row(self) -> _Row | None:
        selection = self._table.selectedItems()
        if not selection:
            return None
        idx = selection[0].row()
        if 0 <= idx < len(self._rows):
            return self._rows[idx]
        return None

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
        benches = self._discovered_bench_paths()
        if not benches:
            QMessageBox.information(self, "No benches", "Create a bench first.")
            return
        dialog = NewSiteDialog(benches, parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        pw = self._ensure_password()
        if pw is None:
            return
        self._start_new_site(dialog.values(), pw)

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

        self._spawn(op, success_msg=f"Site {values.site_name!r} created.")

    def _on_drop_site(self) -> None:
        row = self._selected_row()
        if row is None:
            QMessageBox.information(self, "No selection", "Select a site first.")
            return
        if not confirm(
            self,
            "Drop site",
            f"Drop <b>{row.site.name}</b> from {row.bench_path}?<br>This deletes the site's DB.",
            destructive=True,
        ):
            return
        pw = self._ensure_password()
        if pw is None:
            return
        self._start_drop(row, pw)

    def _start_drop(self, row: _Row, db_root: str) -> None:
        self._open_progress(f"Dropping {row.site.name}…")

        def op() -> core_site.SiteDropResult:
            return core_site.drop_site(row.bench_path, row.site.name, db_root_password=db_root)

        self._spawn(op, success_msg=f"Site {row.site.name!r} dropped.")

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
