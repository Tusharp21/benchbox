"""Bench list view — main area of the Benches sidebar entry."""

from __future__ import annotations

from pathlib import Path

from benchbox_core import discovery, introspect
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class BenchListView(QWidget):
    """Discovers benches under the user's home dir and renders a table.

    Emits ``bench_selected(Path)`` when the user double-clicks a row so the
    main window can swap in the detail view.
    """

    bench_selected = Signal(Path)
    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        header = QHBoxLayout()
        title = QLabel("<h2>Benches on this machine</h2>")
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(refresh)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["path", "frappe", "python", "sites", "apps"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.doubleClicked.connect(self._on_activated)

        self._empty = QLabel("<p><i>No benches found. Use 'Install' to create one.</i></p>")
        self._empty.setVisible(False)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self._table, 1)
        layout.addWidget(self._empty)

        self.refresh()

    def refresh(self) -> None:
        paths = discovery.discover_benches()
        self._table.setRowCount(0)
        for path in paths:
            info = introspect.introspect(path)
            row = self._table.rowCount()
            self._table.insertRow(row)
            path_item = QTableWidgetItem(str(info.path))
            path_item.setData(Qt.ItemDataRole.UserRole, info.path)
            self._table.setItem(row, 0, path_item)
            self._table.setItem(row, 1, QTableWidgetItem(info.frappe_version or "-"))
            self._table.setItem(row, 2, QTableWidgetItem(info.python_version or "-"))
            self._table.setItem(row, 3, QTableWidgetItem(str(len(info.sites))))
            self._table.setItem(row, 4, QTableWidgetItem(str(len(info.apps))))

        self._table.setVisible(bool(paths))
        self._empty.setVisible(not paths)
        self.refresh_requested.emit()

    def _on_activated(self) -> None:
        items = self._table.selectedItems()
        if not items:
            return
        row = items[0].row()
        cell = self._table.item(row, 0)
        if cell is None:
            return
        path = cell.data(Qt.ItemDataRole.UserRole)
        if isinstance(path, Path):
            self.bench_selected.emit(path)
