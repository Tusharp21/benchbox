"""Installer view — runs the full component pipeline off the UI thread."""

from __future__ import annotations

import platform

from benchbox_core import credentials, detect, preflight
from benchbox_core.installer import (
    AptComponent,
    BenchCliComponent,
    Component,
    MariaDBComponent,
    NodeComponent,
    RedisComponent,
    WkhtmltopdfComponent,
)
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.workers import InstallWorker


class InstallerView(QWidget):
    """Preflight + component progress + run button.

    Keeps all long work in ``InstallWorker`` (a QThread) so the UI thread
    stays responsive during ``apt-get install`` / ``pipx install`` / etc.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._title = QLabel("<h2>Install</h2>")
        self._os = QLabel()
        self._preflight = QTableWidget(0, 3)
        self._preflight.setHorizontalHeaderLabels(["check", "state", "details"])
        self._preflight.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._preflight.verticalHeader().setVisible(False)
        self._preflight.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self._components = QTableWidget(0, 2)
        self._components.setHorizontalHeaderLabels(["component", "state"])
        self._components.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._components.verticalHeader().setVisible(False)
        self._components.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate until first component
        self._progress.setVisible(False)

        controls = QHBoxLayout()
        self._dry_run = QCheckBox("Dry run (preview only)")
        self._run = QPushButton("Run install")
        self._run.clicked.connect(self._on_run_clicked)
        controls.addWidget(self._dry_run)
        controls.addStretch(1)
        controls.addWidget(self._run)

        layout = QVBoxLayout(self)
        layout.addWidget(self._title)
        layout.addWidget(self._os)
        layout.addWidget(QLabel("<b>Preflight</b>"))
        layout.addWidget(self._preflight, 1)
        layout.addWidget(QLabel("<b>Components</b>"))
        layout.addWidget(self._components, 1)
        layout.addWidget(self._progress)
        layout.addLayout(controls)

        self._worker: InstallWorker | None = None
        self._populate_preflight()

    # ------------------------------------------------------------------

    def _populate_preflight(self) -> None:
        try:
            info = detect.detect_os()
        except detect.UnsupportedOSError as err:
            self._os.setText(f"<span style='color:red'>unsupported host: {err}</span>")
            self._run.setEnabled(False)
            return

        try:
            detect.require_supported(info)
        except detect.UnsupportedOSError as err:
            self._os.setText(f"<span style='color:red'>{err}</span>")
            self._run.setEnabled(False)
            return

        self._os.setText(f"<b>Host:</b> {info.pretty_name} ({info.arch})")
        report = preflight.run_preflight()
        self._preflight.setRowCount(0)
        for check in report.checks:
            row = self._preflight.rowCount()
            self._preflight.insertRow(row)
            self._preflight.setItem(row, 0, QTableWidgetItem(check.name))
            state_item = QTableWidgetItem("✓ pass" if check.passed else "✗ fail")
            self._preflight.setItem(row, 1, state_item)
            self._preflight.setItem(row, 2, QTableWidgetItem(check.message))

    def _ensure_password(self) -> str | None:
        saved = credentials.get_mariadb_root_password()
        if saved is not None:
            return saved

        pw, ok = QInputDialog.getText(
            self,
            "MariaDB root password",
            "benchbox will set this password on a new MariaDB install, or use\n"
            "it to talk to your existing MariaDB.\n\n"
            "Saved locally at ~/.benchbox/credentials.json (0600).",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not pw:
            return None
        credentials.set_mariadb_root_password(pw)
        return pw

    def _build_components(self, password: str) -> list[Component]:
        info = detect.detect_os()
        return [
            AptComponent(),
            MariaDBComponent(root_password=password),
            RedisComponent(),
            NodeComponent(),
            WkhtmltopdfComponent(ubuntu_version=info.version_id, machine_arch=platform.machine()),
            BenchCliComponent(),
        ]

    # ------------------------------------------------------------------

    def _on_run_clicked(self) -> None:
        password = self._ensure_password()
        if password is None:
            return

        components = self._build_components(password)
        self._components.setRowCount(0)
        for component in components:
            row = self._components.rowCount()
            self._components.insertRow(row)
            self._components.setItem(row, 0, QTableWidgetItem(component.name))
            self._components.setItem(row, 1, QTableWidgetItem("queued"))

        self._run.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, len(components))
        self._progress.setValue(0)

        self._worker = InstallWorker(components, dry_run=self._dry_run.isChecked())
        self._worker.component_started.connect(self._on_component_started)
        self._worker.component_finished.connect(self._on_component_finished)
        self._worker.install_finished.connect(self._on_install_finished)
        self._worker.start()

    def _row_for(self, component_name: str) -> int:
        for row in range(self._components.rowCount()):
            cell = self._components.item(row, 0)
            if cell is not None and cell.text() == component_name:
                return row
        return -1

    def _set_state(self, component_name: str, state: str, *, color: str = "") -> None:
        row = self._row_for(component_name)
        if row < 0:
            return
        item = QTableWidgetItem(state)
        if color:
            item.setForeground(Qt.GlobalColor.darkGreen if color == "green" else Qt.GlobalColor.red)
        self._components.setItem(row, 1, item)

    def _on_component_started(self, name: str, index: int, _total: int) -> None:
        self._set_state(name, "running…")
        self._progress.setValue(index)

    def _on_component_finished(self, name: str, ok: bool) -> None:
        self._set_state(name, "done" if ok else "failed", color="green" if ok else "red")

    def _on_install_finished(self, result: object) -> None:
        self._progress.setVisible(False)
        self._run.setEnabled(True)
        from benchbox_core.installer import InstallResult

        if isinstance(result, InstallResult):
            if result.ok:
                QMessageBox.information(self, "Install complete", "All components succeeded.")
            else:
                failed = result.failed_component.component if result.failed_component else "?"
                QMessageBox.warning(
                    self,
                    "Install failed",
                    f"Stopped at component {failed!r}. Check session logs for details.",
                )
