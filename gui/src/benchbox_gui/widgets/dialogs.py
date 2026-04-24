"""Form dialogs for mutating core operations.

Each dialog exposes a ``values()`` method that returns a small dataclass
the caller passes straight into the matching core call — keeps the GUI
free of argument-marshalling boilerplate and makes dialogs easy to unit
test (just pop the form, dial in values, read ``values()``).

All dialogs inherit the global Dracula-inspired QSS; the only per-dialog
styling is spacing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from benchbox_core.bench import DEFAULT_FRAPPE_BRANCH, DEFAULT_PYTHON_BIN
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# --- NewBenchDialog ----------------------------------------------------

# Preloaded into the Frappe branch combo. First entry is the default
# (matches ``benchbox_core.bench.DEFAULT_FRAPPE_BRANCH``). Users on
# develop or older sites can pick from the drop-down; arbitrary
# branches/tags can still be typed in.
COMMON_FRAPPE_REFS: tuple[str, ...] = (
    "version-15",
    "version-16",
    "version-14",
    "version-13",
    "develop",
)


@dataclass(frozen=True)
class NewBenchValues:
    path: Path
    frappe_branch: str
    python_bin: str


class NewBenchDialog(QDialog):
    """Gathers the args for ``core.bench.create_bench``."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New bench")
        self.setMinimumWidth(520)

        self._path = QLineEdit()
        self._path.setPlaceholderText(str(Path.home() / "frappe-bench"))
        browse = QPushButton("Browse…")
        browse.setProperty("role", "ghost")
        browse.clicked.connect(self._on_browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self._path, 1)
        path_row.addWidget(browse)

        # Editable combo so the user can pick a well-known branch/tag with
        # one click or type an arbitrary ref (bugfix branches, specific
        # tags like ``v15.50.0``, forks, etc.).
        self._branch = QComboBox()
        self._branch.setEditable(True)
        for ref in COMMON_FRAPPE_REFS:
            self._branch.addItem(ref)
        self._branch.setCurrentText(DEFAULT_FRAPPE_BRANCH)

        self._python = QLineEdit(DEFAULT_PYTHON_BIN)

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("Bench path", path_row)
        form.addRow("Frappe branch", self._branch)
        form.addRow("Python", self._python)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok is not None:
            ok.setText("Create bench")
            ok.setProperty("role", "primary")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(16)
        root.addLayout(form)
        root.addWidget(buttons)

    def _on_browse(self) -> None:
        picked = QFileDialog.getExistingDirectory(self, "Choose parent directory", str(Path.home()))
        if picked:
            default_name = "frappe-bench"
            self._path.setText(str(Path(picked) / default_name))

    def _try_accept(self) -> None:
        text = self._path.text().strip() or self._path.placeholderText()
        if not text:
            QMessageBox.warning(self, "Missing path", "Choose where to create the bench.")
            return
        self.accept()

    def values(self) -> NewBenchValues:
        text = self._path.text().strip() or self._path.placeholderText()
        branch = self._branch.currentText().strip() or DEFAULT_FRAPPE_BRANCH
        return NewBenchValues(
            path=Path(text).expanduser(),
            frappe_branch=branch,
            python_bin=self._python.text().strip() or DEFAULT_PYTHON_BIN,
        )


# --- NewSiteDialog -----------------------------------------------------


@dataclass(frozen=True)
class NewSiteValues:
    bench_path: Path
    site_name: str
    admin_password: str
    install_apps: tuple[str, ...]
    set_default: bool


class NewSiteDialog(QDialog):
    """Gathers the args for ``core.site.create_site``.

    ``apps_by_bench`` (optional) maps each bench path to the apps available
    *in that bench*. When provided, the dialog shows a checkable list of
    apps so the user picks by clicking rather than typing a
    comma-separated string; ``frappe`` is hidden (always installed).

    Does NOT prompt for the MariaDB root password — that's loaded from the
    credentials store by the caller (installer.py has the same pattern).
    """

    def __init__(
        self,
        bench_paths: list[Path],
        *,
        parent: QWidget | None = None,
        preselect: Path | None = None,
        apps_by_bench: dict[Path, list[str]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("New site")
        self.setMinimumWidth(520)
        self._apps_by_bench = apps_by_bench or {}

        self._bench = QComboBox()
        for path in bench_paths:
            self._bench.addItem(str(path), userData=path)
        if preselect is not None:
            idx = self._bench.findData(preselect)
            if idx >= 0:
                self._bench.setCurrentIndex(idx)
        self._bench.currentIndexChanged.connect(self._reload_app_choices)

        self._name = QLineEdit()
        self._name.setPlaceholderText("site1.local")

        self._admin = QLineEdit()
        self._admin.setEchoMode(QLineEdit.EchoMode.Password)
        self._admin.setPlaceholderText("Administrator password for the new site")

        self._apps_list = QListWidget()
        self._apps_list.setMinimumHeight(120)

        self._set_default = QCheckBox("Set as default site")

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("Bench", self._bench)
        form.addRow("Site name", self._name)
        form.addRow("Admin password", self._admin)
        form.addRow("Install apps", self._apps_list)
        form.addRow("", self._set_default)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok is not None:
            ok.setText("Create site")
            ok.setProperty("role", "primary")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(16)
        root.addLayout(form)
        root.addWidget(buttons)

        if not bench_paths:
            self._bench.setEnabled(False)
            self._bench.addItem("(no benches found — create one first)")

        self._reload_app_choices()

    def _reload_app_choices(self) -> None:
        self._apps_list.clear()
        bench = self._bench.currentData()
        if bench is None:
            return
        # frappe is implicit on every site; hide it from the install list.
        apps = [a for a in self._apps_by_bench.get(bench, []) if a != "frappe"]
        for app in apps:
            item = QListWidgetItem(app)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._apps_list.addItem(item)

    def _try_accept(self) -> None:
        if not self._name.text().strip():
            QMessageBox.warning(self, "Missing name", "Site name is required.")
            return
        if not self._admin.text():
            QMessageBox.warning(self, "Missing password", "Administrator password is required.")
            return
        if self._bench.currentData() is None:
            QMessageBox.warning(self, "No bench", "Create a bench first, then come back.")
            return
        self.accept()

    def values(self) -> NewSiteValues:
        checked: list[str] = []
        for row in range(self._apps_list.count()):
            item = self._apps_list.item(row)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                checked.append(item.text())
        return NewSiteValues(
            bench_path=self._bench.currentData(),
            site_name=self._name.text().strip(),
            admin_password=self._admin.text(),
            install_apps=tuple(checked),
            set_default=self._set_default.isChecked(),
        )


# --- GetAppDialog ------------------------------------------------------


@dataclass(frozen=True)
class GetAppValues:
    bench_path: Path
    git_url: str
    branch: str | None


class GetAppDialog(QDialog):
    def __init__(
        self,
        bench_paths: list[Path],
        *,
        parent: QWidget | None = None,
        preselect: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Get app")
        self.setMinimumWidth(560)

        self._bench = QComboBox()
        for path in bench_paths:
            self._bench.addItem(str(path), userData=path)
        if preselect is not None:
            idx = self._bench.findData(preselect)
            if idx >= 0:
                self._bench.setCurrentIndex(idx)

        self._url = QLineEdit()
        self._url.setPlaceholderText("https://github.com/frappe/erpnext")

        self._branch = QLineEdit()
        self._branch.setPlaceholderText("(optional) e.g. version-15 — leave blank for default")

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("Bench", self._bench)
        form.addRow("Git URL", self._url)
        form.addRow("Branch", self._branch)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok is not None:
            ok.setText("Get app")
            ok.setProperty("role", "primary")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(16)
        root.addLayout(form)
        root.addWidget(buttons)

    def _try_accept(self) -> None:
        if not self._url.text().strip():
            QMessageBox.warning(self, "Missing URL", "Git URL is required.")
            return
        if self._bench.currentData() is None:
            QMessageBox.warning(self, "No bench", "No bench available; create one first.")
            return
        self.accept()

    def values(self) -> GetAppValues:
        branch = self._branch.text().strip() or None
        return GetAppValues(
            bench_path=self._bench.currentData(),
            git_url=self._url.text().strip(),
            branch=branch,
        )


# --- InstallAppDialog --------------------------------------------------


@dataclass(frozen=True)
class InstallAppValues:
    bench_path: Path
    site_name: str
    apps: tuple[str, ...]
    force: bool = False


class InstallAppDialog(QDialog):
    """Picks a site on a bench and an app (from that bench's apps) to install."""

    def __init__(
        self,
        bench_sites: dict[Path, list[str]],
        bench_apps: dict[Path, list[str]],
        *,
        parent: QWidget | None = None,
        preselect_bench: Path | None = None,
        preselect_app: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Install app")
        self.setMinimumWidth(520)
        self._bench_sites = bench_sites
        self._bench_apps = bench_apps

        self._bench = QComboBox()
        for path in bench_sites:
            self._bench.addItem(str(path), userData=path)
        if preselect_bench is not None:
            idx = self._bench.findData(preselect_bench)
            if idx >= 0:
                self._bench.setCurrentIndex(idx)
        self._bench.currentIndexChanged.connect(self._reload_site_and_app_choices)

        self._site = QComboBox()
        self._app = QComboBox()
        self._reload_site_and_app_choices()
        if preselect_app is not None:
            idx = self._app.findText(preselect_app)
            if idx >= 0:
                self._app.setCurrentIndex(idx)

        self._force = QCheckBox("Force (pass --force)")

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("Bench", self._bench)
        form.addRow("Site", self._site)
        form.addRow("App", self._app)
        form.addRow("", self._force)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok is not None:
            ok.setText("Install app")
            ok.setProperty("role", "primary")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(16)
        root.addLayout(form)
        root.addWidget(buttons)

    def _reload_site_and_app_choices(self) -> None:
        bench = self._bench.currentData()
        self._site.clear()
        self._app.clear()
        if bench is None:
            return
        for site in self._bench_sites.get(bench, []):
            self._site.addItem(site)
        for app in self._bench_apps.get(bench, []):
            if app != "frappe":  # frappe is always installed on every site
                self._app.addItem(app)

    def _try_accept(self) -> None:
        if self._bench.currentData() is None:
            QMessageBox.warning(self, "No bench", "No bench selected.")
            return
        if not self._site.currentText():
            QMessageBox.warning(self, "No site", "This bench has no sites yet.")
            return
        if not self._app.currentText():
            QMessageBox.warning(self, "No app", "This bench has no other apps installed.")
            return
        self.accept()

    def values(self) -> InstallAppValues:
        return InstallAppValues(
            bench_path=self._bench.currentData(),
            site_name=self._site.currentText(),
            apps=(self._app.currentText(),),
            force=self._force.isChecked(),
        )


# --- ConfirmDialog -----------------------------------------------------


def confirm(parent: QWidget, title: str, message: str, *, destructive: bool = False) -> bool:
    """Yes/No prompt. ``destructive=True`` makes Yes red and defaults to No."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning if destructive else QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(message)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(
        QMessageBox.StandardButton.No if destructive else QMessageBox.StandardButton.Yes
    )
    return box.exec() == QMessageBox.StandardButton.Yes


# Kept for convenience — some modules import from here.
__all__ = [
    "GetAppDialog",
    "GetAppValues",
    "InstallAppDialog",
    "InstallAppValues",
    "NewBenchDialog",
    "NewBenchValues",
    "NewSiteDialog",
    "NewSiteValues",
    "confirm",
]
