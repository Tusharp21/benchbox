"""Databases tab — every MariaDB schema, with site-allocation status and a drop button."""

from __future__ import annotations

from collections.abc import Callable

from benchbox_core import credentials, database
from benchbox_core.database import DatabaseError, DatabaseInfo, summarize
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.widgets.dialogs import TypedNameConfirmDialog
from benchbox_gui.workers import OperationWorker

_STATUS_ALL: str = "all"
_STATUS_ALLOCATED: str = "allocated"
_STATUS_ORPHAN: str = "orphan"


def _format_size(n: int) -> str:
    if n <= 0:
        return "—"
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(n)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{n} B"


class _NumericItem(QTableWidgetItem):
    """Sortable cell that ranks by an underlying number, not by formatted text."""

    def __init__(self, display: str, value: float) -> None:
        super().__init__(display)
        self._value = value
        self.setData(Qt.ItemDataRole.UserRole, value)
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other: object) -> bool:
        if isinstance(other, _NumericItem):
            return self._value < other._value
        return super().__lt__(other)  # type: ignore[arg-type]


class _StatusItem(QTableWidgetItem):
    """Sort by orphan-vs-allocated regardless of label text."""

    def __init__(self, *, is_orphan: bool) -> None:
        # Empty text — the actual badge is rendered as a cell widget.
        super().__init__("")
        self._sort_key = 1 if is_orphan else 0
        self.setData(Qt.ItemDataRole.UserRole, self._sort_key)

    def __lt__(self, other: object) -> bool:
        if isinstance(other, _StatusItem):
            return self._sort_key < other._sort_key
        return super().__lt__(other)  # type: ignore[arg-type]


class DatabasesView(QWidget):
    """List every database, group/filter by allocation, drop orphans."""

    refreshed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._databases: list[DatabaseInfo] = []
        self._filter: str = ""
        self._status_filter: str = _STATUS_ALL
        self._worker: OperationWorker | None = None
        self._progress: QProgressDialog | None = None

        title = QLabel("Databases")
        title.setProperty("role", "h1")
        subtitle = QLabel(
            "Every MariaDB schema on this machine. Orphan databases are no "
            "longer referenced by any site — drop them to reclaim disk."
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

        # Filter toolbar.
        filter_label = QLabel("Filter:")
        filter_label.setProperty("role", "dim")

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search by database, site, or bench…")
        self._search.setClearButtonEnabled(True)
        self._search.setMinimumWidth(260)
        self._search.textChanged.connect(self._on_filter_changed)

        status_label = QLabel("Status:")
        status_label.setProperty("role", "dim")

        self._status_combo = QComboBox()
        self._status_combo.setMinimumWidth(160)
        self._status_combo.addItem("All databases", _STATUS_ALL)
        self._status_combo.addItem("Allocated to a site", _STATUS_ALLOCATED)
        self._status_combo.addItem("Orphan (no site)", _STATUS_ORPHAN)
        self._status_combo.currentIndexChanged.connect(self._on_status_changed)

        self._summary = QLabel()
        self._summary.setProperty("role", "dim")

        self._filter_bar = QFrame()
        self._filter_bar.setObjectName("FilterBar")
        filter_layout = QHBoxLayout(self._filter_bar)
        filter_layout.setContentsMargins(14, 10, 14, 10)
        filter_layout.setSpacing(12)
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self._search, 1)
        filter_layout.addWidget(status_label)
        filter_layout.addWidget(self._status_combo)
        filter_layout.addWidget(self._summary)

        # Table — modeled like a datatable with sortable columns + accent
        # selection bar.
        self._table = QTableWidget(0, 6)
        self._table.setObjectName("DatabasesTable")
        self._table.setHorizontalHeaderLabels(
            ["Database", "Status", "Size", "Site", "Bench", ""]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(False)
        self._table.setShowGrid(False)
        self._table.setSortingEnabled(True)

        h = self._table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        h.setHighlightSections(False)
        h.setSortIndicatorShown(True)
        h.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._table.verticalHeader().setDefaultSectionSize(48)
        # Default sort: by Database name ascending. Users can click any
        # header to re-sort.
        self._table.sortByColumn(0, Qt.SortOrder.AscendingOrder)

        # Footer — summary line under the table, like a datatable footer.
        self._footer = QLabel("")
        self._footer.setProperty("role", "dim")
        self._footer.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # Empty / error state — full-width overlay shown when the table is hidden.
        self._notice = QLabel()
        self._notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._notice.setWordWrap(True)
        self._notice.setVisible(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)
        root.addLayout(header)
        root.addWidget(self._filter_bar)
        root.addWidget(self._table, 1)
        root.addWidget(self._footer)
        root.addWidget(self._notice)

        self.refresh()

    # --- public API --------------------------------------------------

    @property
    def row_count(self) -> int:
        return self._table.rowCount()

    def refresh(self) -> None:
        password = credentials.get_mariadb_root_password()
        if password is None:
            self._databases = []
            self._render()
            self._show_notice(
                "<p>No MariaDB root password is saved.</p>"
                "<p style='color:#a9a9c4;'>Run the installer or set the password "
                "in <b>Settings</b> to view databases.</p>"
            )
            return
        try:
            self._databases = database.list_databases(db_root_password=password)
        except DatabaseError as exc:
            self._databases = []
            self._render()
            self._show_notice(
                f"<p>Could not query MariaDB.</p>"
                f"<p style='color:#a9a9c4;'>{exc}</p>"
            )
            return
        self._hide_notice()
        self._render()
        self.refreshed.emit()

    # --- filter handlers --------------------------------------------

    def _on_filter_changed(self, text: str) -> None:
        self._filter = text.strip().lower()
        self._render()

    def _on_status_changed(self, _index: int) -> None:
        self._status_filter = self._status_combo.currentData() or _STATUS_ALL
        self._render()

    # --- rendering ---------------------------------------------------

    def _matches(self, db: DatabaseInfo) -> bool:
        if self._status_filter == _STATUS_ALLOCATED and db.is_orphan:
            return False
        if self._status_filter == _STATUS_ORPHAN and not db.is_orphan:
            return False
        if not self._filter:
            return True
        haystack = f"{db.name}\n{db.site_name or ''}\n{db.bench_path or ''}".lower()
        return all(token in haystack for token in self._filter.split())

    def _render(self) -> None:
        visible = [db for db in self._databases if self._matches(db)]
        # Disable sort while we replace the rows — otherwise items would
        # be re-sorted after every setItem and the indices we wrote to
        # would no longer match.
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(visible))
        for row, db in enumerate(visible):
            self._populate_row(row, db)
        self._table.setSortingEnabled(True)
        self._refresh_summary(len(visible))
        if self._databases and not visible:
            self._show_notice(
                "<p>No databases match the current filters.</p>"
                "<p style='color:#a9a9c4;'>Try a different search term or "
                "switch to <b>All databases</b>.</p>"
            )
        elif not self._databases:
            # refresh() already populated the notice on hard error; if we got
            # here with an empty list and no error notice, MariaDB just has
            # nothing to show — keep the table visible (empty).
            if not self._notice.isVisible():
                self._show_notice(
                    "<p>No user databases on this server.</p>"
                    "<p style='color:#a9a9c4;'>Create a site to allocate one.</p>"
                )
        else:
            self._hide_notice()

    def _populate_row(self, row: int, db: DatabaseInfo) -> None:
        name_item = QTableWidgetItem(db.name)
        name_item.setData(Qt.ItemDataRole.UserRole, db.name)
        name_item.setToolTip(db.name)
        self._table.setItem(row, 0, name_item)

        # Status: a badge cell. Sortable item underneath provides ordering.
        self._table.setItem(row, 1, _StatusItem(is_orphan=db.is_orphan))
        status_label = QLabel("orphan" if db.is_orphan else "allocated")
        status_label.setProperty(
            "role", "badge-warn" if db.is_orphan else "badge-accent"
        )
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_label.setMinimumWidth(86)
        cell = QWidget()
        cell.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        cell_layout = QHBoxLayout(cell)
        cell_layout.setContentsMargins(8, 4, 8, 4)
        cell_layout.addWidget(status_label, 0, Qt.AlignmentFlag.AlignVCenter)
        cell_layout.addStretch(1)
        self._table.setCellWidget(row, 1, cell)

        # Size: numeric sort, right-aligned.
        size_item = _NumericItem(_format_size(db.size_bytes), float(db.size_bytes))
        self._table.setItem(row, 2, size_item)

        # Site / Bench: dim rendering when missing.
        site_item = QTableWidgetItem(db.site_name or "—")
        if not db.site_name:
            site_item.setForeground(Qt.GlobalColor.gray)
        self._table.setItem(row, 3, site_item)

        if db.bench_path:
            bench_item = QTableWidgetItem(db.bench_path.name)
            bench_item.setToolTip(str(db.bench_path))
        else:
            bench_item = QTableWidgetItem("—")
            bench_item.setForeground(Qt.GlobalColor.gray)
        self._table.setItem(row, 4, bench_item)

        # Action cell — Drop only enabled for orphans.
        drop_btn = QPushButton("Drop")
        drop_btn.setProperty("role", "danger")
        drop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        drop_btn.setEnabled(db.is_orphan)
        drop_btn.setMinimumHeight(28)
        if not db.is_orphan:
            drop_btn.setToolTip(
                "This database is allocated to a site. Use the bench's "
                "Drop site action instead."
            )
        else:
            drop_btn.setToolTip("Drop this orphan database")
        drop_btn.clicked.connect(self._make_drop_handler(db.name))
        action_cell = QWidget()
        action_cell.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        action_layout = QHBoxLayout(action_cell)
        action_layout.setContentsMargins(8, 2, 12, 2)
        action_layout.addStretch(1)
        action_layout.addWidget(drop_btn)
        self._table.setCellWidget(row, 5, action_cell)

    def _refresh_summary(self, visible_count: int | None = None) -> None:
        s = summarize(self._databases)
        if s.total == 0:
            self._summary.setText("")
            self._footer.setText("")
            return

        # Compact chip in the filter bar — just totals.
        self._summary.setText(
            f"{s.allocated} allocated · {s.orphan} orphan · "
            f"{_format_size(s.total_bytes)}"
        )

        # Footer line under the table — shows what's currently visible.
        shown = visible_count if visible_count is not None else s.total
        if shown == s.total:
            self._footer.setText(f"Showing all {s.total} databases")
        else:
            self._footer.setText(f"Showing {shown} of {s.total} databases")

    def _show_notice(self, text: str) -> None:
        self._notice.setText(text)
        self._notice.setVisible(True)
        self._table.setVisible(False)
        self._footer.setVisible(False)

    def _hide_notice(self) -> None:
        self._notice.setVisible(False)
        self._table.setVisible(True)
        self._footer.setVisible(True)

    # --- drop flow ---------------------------------------------------

    def _make_drop_handler(self, name: str) -> Callable[[], None]:
        return lambda: self._on_drop_clicked(name)

    def _on_drop_clicked(self, name: str) -> None:
        password = credentials.get_mariadb_root_password()
        if password is None:
            QMessageBox.warning(
                self,
                "MariaDB password missing",
                "No MariaDB root password is saved. Set it in Settings first.",
            )
            return
        dialog = TypedNameConfirmDialog(
            name,
            title="Drop database",
            message=(
                f"This will permanently drop the database <b>{name}</b>. "
                "This cannot be undone."
            ),
            action_label="Drop database",
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._spawn_drop(name, password)

    def _spawn_drop(self, name: str, password: str) -> None:
        self._show_progress(f"Dropping database {name}…")

        def op() -> str:
            database.drop_database(name, db_root_password=password)
            return name

        self._worker = OperationWorker(op)
        self._worker.succeeded.connect(self._on_drop_succeeded)
        self._worker.failed.connect(self._on_drop_failed)
        self._worker.start()

    def _on_drop_succeeded(self, result: object) -> None:
        self._close_progress()
        QMessageBox.information(self, "Done", f"Dropped database {result}.")
        self.refresh()

    def _on_drop_failed(self, exc: object) -> None:
        self._close_progress()
        QMessageBox.critical(self, "Drop failed", f"{exc}")

    # --- progress ----------------------------------------------------

    def _show_progress(self, message: str) -> None:
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
