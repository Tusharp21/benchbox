"""Installer view."""

from __future__ import annotations

import platform
from datetime import datetime

from benchbox_core import credentials, detect, preflight
from benchbox_core.installer import (
    AptComponent,
    BenchCliComponent,
    Component,
    ComponentPlan,
    MariaDBComponent,
    NodeComponent,
    RedisComponent,
    WkhtmltopdfComponent,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.widgets.card_grid import CardGrid
from benchbox_gui.widgets.component_card import ComponentCard
from benchbox_gui.widgets.preflight_strip import PreflightStrip
from benchbox_gui.workers import InstallWorker

# One-line description per component name so the cards read as a
# task list rather than just a list of identifiers.
_COMPONENT_DESCRIPTIONS: dict[str, str] = {
    "apt": "System libraries Frappe and its build deps need (build-essential, libssl-dev, …).",
    "mariadb": "Database server. We set the root password and harden the install.",
    "redis": "Cache + scheduler queue used by Frappe. Auto-starts on boot.",
    "node": "nvm + Node 18 (Frappe v15 won't build with the apt-shipped Node 12).",
    "wkhtmltopdf": "Frappe-recommended 0.12.6.1 build for PDF / print rendering.",
    "bench": "Frappe's bench CLI installed via pipx.",
}


def _section_header(title: str) -> QWidget:
    """All-caps section title with a thin separator below it."""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 4, 0, 2)
    layout.setSpacing(4)

    label = QLabel(title.upper())
    label.setProperty("role", "dim")
    label.setStyleSheet("font-weight: 700; letter-spacing: 1.4px; font-size: 10pt;")

    line = QLabel("")
    line.setFixedHeight(1)
    line.setStyleSheet("background-color: #44475a;")

    layout.addWidget(label)
    layout.addWidget(line)
    return container


class InstallerView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._title = QLabel("Install")
        self._title.setProperty("role", "h1")
        self._os = QLabel()
        self._os.setProperty("role", "dim")

        self._preflight = PreflightStrip()

        self._cards: dict[str, ComponentCard] = {}
        self._cards_grid = CardGrid()

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(5000)
        mono = QFont("JetBrains Mono, Fira Code, Courier New", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._log.setFont(mono)
        self._log.setPlaceholderText(
            "Install events will stream here once you click Run install."
        )
        self._log.setMinimumHeight(160)
        self._log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate until first component
        self._progress.setVisible(False)

        self._dry_run = QCheckBox("Dry run (preview only)")
        self._run = QPushButton("Run install")
        self._run.setProperty("role", "primary")
        self._run.setMinimumHeight(34)
        self._run.clicked.connect(self._on_run_clicked)
        controls = QHBoxLayout()
        controls.addWidget(self._dry_run)
        controls.addStretch(1)
        controls.addWidget(self._run)

        header_text = QVBoxLayout()
        header_text.setSpacing(3)
        header_text.addWidget(self._title)
        header_text.addWidget(self._os)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addLayout(header_text)
        layout.addWidget(_section_header("Preflight"))
        layout.addWidget(self._preflight)
        layout.addSpacing(4)
        layout.addWidget(_section_header("Components"))
        layout.addWidget(self._cards_grid)
        layout.addSpacing(4)
        layout.addWidget(_section_header("Install log"))
        layout.addWidget(self._log, 1)
        layout.addWidget(self._progress)
        layout.addLayout(controls)

        self._worker: InstallWorker | None = None
        self._populate_preflight()
        self._populate_components()

    # --- preflight ----------------------------------------------------

    def _populate_preflight(self) -> None:
        try:
            info = detect.detect_os()
        except detect.UnsupportedOSError as err:
            self._os.setText(f"<span style='color:#cf222e'>unsupported host: {err}</span>")
            self._run.setEnabled(False)
            return

        try:
            detect.require_supported(info)
        except detect.UnsupportedOSError as err:
            self._os.setText(f"<span style='color:#cf222e'>{err}</span>")
            self._run.setEnabled(False)
            return

        self._os.setText(f"<b>Host</b> &nbsp; {info.pretty_name} &nbsp; · &nbsp; {info.arch}")
        report = preflight.run_preflight()
        self._preflight.set_checks(report.checks)

    # --- component cards ---------------------------------------------

    def _populate_components(self) -> None:
        try:
            password = credentials.get_mariadb_root_password() or ""
        except Exception:  # noqa: BLE001
            password = ""

        components = self._build_components(password)
        cards: list[QWidget] = []
        for component in components:
            description = _COMPONENT_DESCRIPTIONS.get(component.name, "")
            card = ComponentCard(component.name, description)
            try:
                plan: ComponentPlan = component.plan()
            except Exception:  # noqa: BLE001
                plan = ComponentPlan(component=component.name, steps=())
            card.set_state(self._initial_state_from_plan(plan))
            self._cards[component.name] = card
            cards.append(card)
        self._cards_grid.set_cards(cards)

    def _initial_state_from_plan(self, plan: ComponentPlan) -> str:
        if not plan.steps or not plan.runnable_steps:
            return "installed"
        return "not_installed"

    # --- credentials -------------------------------------------------

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

    # --- run ---------------------------------------------------------

    def _on_run_clicked(self) -> None:
        password = self._ensure_password()
        if password is None:
            return

        components = self._build_components(password)
        for component in components:
            card = self._cards.get(component.name)
            if card is not None:
                card.set_state("queued")

        self._run.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, len(components))
        self._progress.setValue(0)

        mode = "dry run" if self._dry_run.isChecked() else "live run"
        self._append_log(f"--- starting install ({mode}) ---")

        self._worker = InstallWorker(components, dry_run=self._dry_run.isChecked())
        self._worker.component_started.connect(self._on_component_started)
        self._worker.component_finished.connect(self._on_component_finished)
        self._worker.install_finished.connect(self._on_install_finished)
        self._worker.start()

    def _on_component_started(self, name: str, index: int, _total: int) -> None:
        card = self._cards.get(name)
        if card is not None:
            card.set_state("running")
        self._progress.setValue(index)
        self._append_log(f"running {name}")

    def _on_component_finished(self, name: str, ok: bool) -> None:
        card = self._cards.get(name)
        if card is not None:
            card.set_state("done" if ok else "failed")
        self._append_log(name + (" done" if ok else " failed"))

    def _on_install_finished(self, result: object) -> None:
        self._progress.setVisible(False)
        self._run.setEnabled(True)
        from benchbox_core.installer import InstallResult

        if isinstance(result, InstallResult):
            if result.ok:
                self._append_log("--- install complete ---")
                QMessageBox.information(self, "Install complete", "All components succeeded.")
            else:
                failed = result.failed_component.component if result.failed_component else "?"
                self._append_log(f"--- install stopped at {failed} ---")
                QMessageBox.warning(
                    self,
                    "Install failed",
                    f"Stopped at component {failed!r}. Check session logs for details.",
                )

    # --- log ---------------------------------------------------------

    def _append_log(self, text: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log.appendPlainText(f"[{timestamp}] {text}")
        cursor = self._log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._log.setTextCursor(cursor)
        self._log.ensureCursorVisible()
