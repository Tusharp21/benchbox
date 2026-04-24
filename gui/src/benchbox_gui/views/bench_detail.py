"""Detail view for a single bench — shown when user picks a bench."""

from __future__ import annotations

from pathlib import Path

from benchbox_core import introspect
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class BenchDetailView(QWidget):
    """Reads metadata via introspect + renders apps/sites tables."""

    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        header_row = QHBoxLayout()
        self._title = QLabel()
        back = QPushButton("← back to benches")
        back.clicked.connect(self.back_requested.emit)
        header_row.addWidget(back)
        header_row.addStretch(1)

        self._meta = QLabel()
        self._meta.setTextFormat(self._meta.textFormat().RichText)

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
        apps_layout.addWidget(self._apps)

        sites_box = QGroupBox("Sites")
        sites_layout = QVBoxLayout(sites_box)
        sites_layout.addWidget(self._sites)

        layout = QVBoxLayout(self)
        layout.addLayout(header_row)
        layout.addWidget(self._title)
        layout.addWidget(self._meta)
        layout.addWidget(apps_box, 1)
        layout.addWidget(sites_box, 1)

    def load(self, path: Path) -> None:
        info = introspect.introspect(path)
        self._title.setText(f"<h2>{info.path}</h2>")
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
