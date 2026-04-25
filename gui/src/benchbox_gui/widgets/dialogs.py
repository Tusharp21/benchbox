"""Form dialogs for mutating core operations.

Each dialog exposes a ``values()`` method that returns a small dataclass
the caller passes straight into the matching core call — keeps the GUI
free of argument-marshalling boilerplate and makes dialogs easy to unit
test (just pop the form, dial in values, read ``values()``).

All dialogs inherit the global Dracula-inspired QSS; the only per-dialog
styling is spacing.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from benchbox_core.bench import DEFAULT_FRAPPE_BRANCH, DEFAULT_PYTHON_BIN
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.workers import StreamingOpWorker

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
    """Form → live log → done, all in one window.

    The dialog hosts the form, the streaming log panel, and the worker
    itself; the parent view just opens it and refreshes when ``exec()``
    returns ``Accepted`` (op finished cleanly). Form is hidden once the
    worker starts so the log gets the full window height.
    """

    def __init__(
        self,
        bench_paths: list[Path],
        *,
        parent: QWidget | None = None,
        preselect: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Get app")
        self.setMinimumSize(760, 560)

        self._worker: StreamingOpWorker | None = None
        self._values: GetAppValues | None = None

        # --- form (top, hidden once worker starts) ------------------
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

        self._token = QLineEdit()
        self._token.setEchoMode(QLineEdit.EchoMode.Password)
        self._token.setPlaceholderText(
            "(optional) GitHub/GitLab personal access token for private repos"
        )

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("Bench", self._bench)
        form.addRow("Git URL", self._url)
        form.addRow("Branch", self._branch)
        form.addRow("Token", self._token)

        self._form_holder = QWidget()
        self._form_holder.setLayout(form)

        # --- live log panel (bottom, hidden until worker starts) ----
        self._status = QLabel()
        self._status.setProperty("role", "dim")
        self._status.setVisible(False)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(10_000)
        mono = QFont("JetBrains Mono, Fira Code, Courier New", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._log.setFont(mono)
        self._log.setPlaceholderText(
            "Live `bench get-app` output will appear here once you click Get app."
        )
        self._log.setVisible(False)

        # --- buttons -----------------------------------------------
        self._primary = QPushButton("Get app")
        self._primary.setProperty("role", "primary")
        self._primary.setCursor(Qt.CursorShape.PointingHandCursor)
        self._primary.clicked.connect(self._on_primary)

        self._cancel = QPushButton("Cancel")
        self._cancel.setProperty("role", "ghost")
        self._cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel.clicked.connect(self.reject)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch(1)
        buttons_row.addWidget(self._cancel)
        buttons_row.addWidget(self._primary)

        # --- assemble -----------------------------------------------
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(14)
        root.addWidget(self._form_holder)
        root.addWidget(self._status)
        root.addWidget(self._log, 1)
        root.addLayout(buttons_row)

    # --- public API -------------------------------------------------

    def values(self) -> GetAppValues:
        """The values used to launch the operation (set after primary click)."""
        if self._values is None:
            raise RuntimeError("values() called before the operation started")
        return self._values

    # --- phase transitions -----------------------------------------

    def _on_primary(self) -> None:
        # Two roles: "Get app" (start) and "Close" (finish-and-accept).
        if self._worker is None:
            self._start_op()
        else:
            self.accept()

    def _start_op(self) -> None:
        url = self._url.text().strip()
        if not url:
            QMessageBox.warning(self, "Missing URL", "Git URL is required.")
            return
        bench_path = self._bench.currentData()
        if bench_path is None:
            QMessageBox.warning(self, "No bench", "No bench available; create one first.")
            return

        branch = self._branch.text().strip() or None
        token = self._token.text().strip()
        if token:
            url = _inject_token(url, token)
        self._values = GetAppValues(bench_path=bench_path, git_url=url, branch=branch)

        # Lock the form, reveal the log panel, swap button text.
        self._form_holder.setEnabled(False)
        self._log.setVisible(True)
        self._status.setVisible(True)
        self._status.setText(f"Fetching {url} into {bench_path}…")
        self._primary.setEnabled(False)
        self._primary.setText("Working…")
        self._cancel.setEnabled(False)

        # Defer the import to avoid a hard module-load cost when the dialog
        # is just being constructed in tests.
        from benchbox_core import app as core_app

        def op(line_cb: Callable[[str], None]) -> Any:
            return core_app.get_app(
                self._values.bench_path,  # type: ignore[union-attr]
                self._values.git_url,  # type: ignore[union-attr]
                branch=self._values.branch,  # type: ignore[union-attr]
                line_callback=line_cb,
            )

        self._worker = StreamingOpWorker(op)
        self._worker.line_received.connect(self._append_log)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _append_log(self, line: str) -> None:
        # appendPlainText adds a trailing newline; we strip ours so we
        # don't get blank lines between entries.
        self._log.appendPlainText(line.rstrip("\n"))

    def _on_succeeded(self, _result: object) -> None:
        self._status.setText("✓ App fetched successfully.")
        self._primary.setText("Close")
        self._primary.setEnabled(True)
        self._primary.setProperty("role", "primary")
        self._cancel.setVisible(False)

    def _on_failed(self, exc: object) -> None:
        self._status.setText(f"✗ Failed: {exc}")
        self._primary.setText("Close")
        self._primary.setEnabled(True)
        # Closing after a failure should not mean "accepted" — caller
        # uses the Rejected code to skip its post-success refresh.
        self._primary.clicked.disconnect()
        self._primary.clicked.connect(self.reject)
        self._cancel.setVisible(False)


def _inject_token(git_url: str, token: str) -> str:
    """Rewrite an https git URL so it carries a PAT in the userinfo.

    GitHub/GitLab accept ``https://<token>@host/...`` as basic-auth (the
    token is treated as the username, password empty). SSH URLs (``git@``)
    and anything non-https are returned unchanged — a token isn't useful
    there anyway.
    """
    split = urlsplit(git_url)
    if split.scheme != "https" or not split.hostname:
        return git_url
    # Drop any existing userinfo (rare, but don't compound).
    host = split.hostname
    netloc = f"{token}@{host}"
    if split.port:
        netloc = f"{netloc}:{split.port}"
    return urlunsplit((split.scheme, netloc, split.path, split.query, split.fragment))


# --- NewAppDialog ------------------------------------------------------

# Frappe app name validation: starts with a lowercase letter, then
# lowercase letters / digits / underscores only. Matches the rule
# ``bench new-app`` enforces internally.
_APP_NAME_RE: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class NewAppValues:
    bench_path: Path
    app_name: str
    title: str
    publisher: str
    email: str


class NewAppDialog(QDialog):
    """Scaffold a fresh Frappe app via ``bench new-app`` with a live log.

    Same form → log → done flow as :class:`GetAppDialog`. Title /
    publisher / email default to sensible values so the user usually only
    needs to type the app name.
    """

    def __init__(
        self,
        bench_paths: list[Path],
        *,
        parent: QWidget | None = None,
        preselect: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("New app")
        self.setMinimumSize(720, 540)

        self._worker: StreamingOpWorker | None = None
        self._values: NewAppValues | None = None

        self._bench = QComboBox()
        for path in bench_paths:
            self._bench.addItem(str(path), userData=path)
        if preselect is not None:
            idx = self._bench.findData(preselect)
            if idx >= 0:
                self._bench.setCurrentIndex(idx)

        self._app_name = QLineEdit()
        self._app_name.setPlaceholderText("e.g. my_custom_app  (lowercase, letters/digits/underscores)")

        self._title = QLineEdit()
        self._title.setPlaceholderText("(optional) human-readable title — auto-generated from app name")

        self._publisher = QLineEdit("benchbox")
        self._email = QLineEdit("dev@example.com")

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("Bench", self._bench)
        form.addRow("App name", self._app_name)
        form.addRow("Title", self._title)
        form.addRow("Publisher", self._publisher)
        form.addRow("Email", self._email)

        self._form_holder = QWidget()
        self._form_holder.setLayout(form)

        self._status = QLabel()
        self._status.setProperty("role", "dim")
        self._status.setVisible(False)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(10_000)
        mono = QFont("JetBrains Mono, Fira Code, Courier New", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._log.setFont(mono)
        self._log.setPlaceholderText(
            "Live `bench new-app` output will appear here once you click Create."
        )
        self._log.setVisible(False)

        self._primary = QPushButton("Create app")
        self._primary.setProperty("role", "primary")
        self._primary.setCursor(Qt.CursorShape.PointingHandCursor)
        self._primary.clicked.connect(self._on_primary)

        self._cancel = QPushButton("Cancel")
        self._cancel.setProperty("role", "ghost")
        self._cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel.clicked.connect(self.reject)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch(1)
        buttons_row.addWidget(self._cancel)
        buttons_row.addWidget(self._primary)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(14)
        root.addWidget(self._form_holder)
        root.addWidget(self._status)
        root.addWidget(self._log, 1)
        root.addLayout(buttons_row)

    def values(self) -> NewAppValues:
        if self._values is None:
            raise RuntimeError("values() called before the operation started")
        return self._values

    def _on_primary(self) -> None:
        if self._worker is None:
            self._start_op()
        else:
            self.accept()

    def _start_op(self) -> None:
        bench_path = self._bench.currentData()
        if bench_path is None:
            QMessageBox.warning(self, "No bench", "No bench available; create one first.")
            return
        app_name = self._app_name.text().strip()
        if not _APP_NAME_RE.match(app_name):
            QMessageBox.warning(
                self,
                "Invalid app name",
                "App name must start with a lowercase letter and contain only "
                "lowercase letters, digits, and underscores.",
            )
            return
        if app_name == "frappe":
            QMessageBox.warning(self, "Reserved name", "'frappe' is reserved — pick another name.")
            return

        title = self._title.text().strip() or app_name.replace("_", " ").title()
        publisher = self._publisher.text().strip() or "benchbox"
        email = self._email.text().strip() or "dev@example.com"

        self._values = NewAppValues(
            bench_path=bench_path,
            app_name=app_name,
            title=title,
            publisher=publisher,
            email=email,
        )

        self._form_holder.setEnabled(False)
        self._log.setVisible(True)
        self._status.setVisible(True)
        self._status.setText(f"Scaffolding {app_name} in {bench_path}…")
        self._primary.setEnabled(False)
        self._primary.setText("Working…")
        self._cancel.setEnabled(False)

        from benchbox_core import app as core_app

        def op(line_cb: Callable[[str], None]) -> Any:
            return core_app.new_app(
                self._values.bench_path,  # type: ignore[union-attr]
                self._values.app_name,  # type: ignore[union-attr]
                title=self._values.title,  # type: ignore[union-attr]
                publisher=self._values.publisher,  # type: ignore[union-attr]
                email=self._values.email,  # type: ignore[union-attr]
                line_callback=line_cb,
            )

        self._worker = StreamingOpWorker(op)
        self._worker.line_received.connect(self._append_log)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _append_log(self, line: str) -> None:
        self._log.appendPlainText(line.rstrip("\n"))

    def _on_succeeded(self, _result: object) -> None:
        self._status.setText("✓ App scaffolded successfully.")
        self._primary.setText("Close")
        self._primary.setEnabled(True)
        self._cancel.setVisible(False)

    def _on_failed(self, exc: object) -> None:
        self._status.setText(f"✗ Failed: {exc}")
        self._primary.setText("Close")
        self._primary.setEnabled(True)
        self._primary.clicked.disconnect()
        self._primary.clicked.connect(self.reject)
        self._cancel.setVisible(False)


# --- RestoreSiteDialog -------------------------------------------------


@dataclass(frozen=True)
class RestoreSiteValues:
    bench_path: Path
    site_name: str
    sql_path: Path
    admin_password: str | None
    with_public_files: Path | None
    with_private_files: Path | None
    force: bool


class RestoreSiteDialog(QDialog):
    """Picks an existing site + a SQL backup (optionally public/private file
    tarballs) to restore onto that site.

    The MariaDB root password isn't prompted for here — the caller loads
    it from the credentials store (same pattern as NewSiteDialog).
    """

    def __init__(
        self,
        bench_sites: dict[Path, list[str]],
        *,
        parent: QWidget | None = None,
        preselect_bench: Path | None = None,
        preselect_site: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Restore site")
        self.setMinimumWidth(580)
        self._bench_sites = bench_sites

        self._bench = QComboBox()
        for path in bench_sites:
            self._bench.addItem(str(path), userData=path)
        if preselect_bench is not None:
            idx = self._bench.findData(preselect_bench)
            if idx >= 0:
                self._bench.setCurrentIndex(idx)
        self._bench.currentIndexChanged.connect(self._reload_sites)

        self._site = QComboBox()
        self._reload_sites()
        if preselect_site is not None:
            idx = self._site.findText(preselect_site)
            if idx >= 0:
                self._site.setCurrentIndex(idx)

        self._sql = QLineEdit()
        self._sql.setPlaceholderText("Path to SQL or .sql.gz backup")
        sql_browse = QPushButton("Browse…")
        sql_browse.setProperty("role", "ghost")
        sql_browse.clicked.connect(lambda: self._pick_file(self._sql, "SQL backup"))
        sql_row = QHBoxLayout()
        sql_row.addWidget(self._sql, 1)
        sql_row.addWidget(sql_browse)

        self._public = QLineEdit()
        self._public.setPlaceholderText("(optional) files.tar archive with public files")
        public_browse = QPushButton("Browse…")
        public_browse.setProperty("role", "ghost")
        public_browse.clicked.connect(lambda: self._pick_file(self._public, "Public files"))
        public_row = QHBoxLayout()
        public_row.addWidget(self._public, 1)
        public_row.addWidget(public_browse)

        self._private = QLineEdit()
        self._private.setPlaceholderText("(optional) private-files.tar archive")
        private_browse = QPushButton("Browse…")
        private_browse.setProperty("role", "ghost")
        private_browse.clicked.connect(lambda: self._pick_file(self._private, "Private files"))
        private_row = QHBoxLayout()
        private_row.addWidget(self._private, 1)
        private_row.addWidget(private_browse)

        self._admin = QLineEdit()
        self._admin.setEchoMode(QLineEdit.EchoMode.Password)
        self._admin.setPlaceholderText("(optional) reset Administrator password to this value")

        self._force = QCheckBox("Force (overwrite existing DB)")
        self._force.setChecked(True)

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("Bench", self._bench)
        form.addRow("Site", self._site)
        form.addRow("SQL backup", sql_row)
        form.addRow("Public files", public_row)
        form.addRow("Private files", private_row)
        form.addRow("Admin password", self._admin)
        form.addRow("", self._force)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok is not None:
            ok.setText("Restore site")
            ok.setProperty("role", "primary")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(16)
        root.addLayout(form)
        root.addWidget(buttons)

    def _pick_file(self, target: QLineEdit, label: str) -> None:
        picked, _ = QFileDialog.getOpenFileName(self, f"Select {label}", str(Path.home()))
        if picked:
            target.setText(picked)

    def _reload_sites(self) -> None:
        self._site.clear()
        bench = self._bench.currentData()
        if bench is None:
            return
        for site in self._bench_sites.get(bench, []):
            self._site.addItem(site)

    def _try_accept(self) -> None:
        if self._bench.currentData() is None:
            QMessageBox.warning(self, "No bench", "No bench selected.")
            return
        if not self._site.currentText():
            QMessageBox.warning(self, "No site", "This bench has no sites to restore into.")
            return
        sql = self._sql.text().strip()
        if not sql:
            QMessageBox.warning(self, "Missing backup", "Pick a SQL backup file.")
            return
        if not Path(sql).expanduser().is_file():
            QMessageBox.warning(
                self, "Backup not found", f"SQL backup does not exist:\n{sql}"
            )
            return
        self.accept()

    def values(self) -> RestoreSiteValues:
        def _opt_path(text: str) -> Path | None:
            t = text.strip()
            return Path(t).expanduser() if t else None

        return RestoreSiteValues(
            bench_path=self._bench.currentData(),
            site_name=self._site.currentText(),
            sql_path=Path(self._sql.text().strip()).expanduser(),
            admin_password=self._admin.text() or None,
            with_public_files=_opt_path(self._public.text()),
            with_private_files=_opt_path(self._private.text()),
            force=self._force.isChecked(),
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


# --- TypedNameConfirmDialog --------------------------------------------


class TypedNameConfirmDialog(QDialog):
    """GitHub-style destructive-action confirm.

    Shows a warning message, asks the user to type the exact ``name`` of
    the thing they're about to destroy, and keeps the destructive button
    disabled until the input matches. Forces a real moment of "yes I mean
    this one" instead of a muscle-memory Yes click.
    """

    def __init__(
        self,
        name: str,
        *,
        title: str,
        message: str,
        action_label: str = "Delete",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self._name = name

        body = QLabel(message)
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)

        prompt = QLabel(f"Type <b>{name}</b> to confirm.")
        prompt.setWordWrap(True)
        prompt.setTextFormat(Qt.TextFormat.RichText)

        self._input = QLineEdit()
        self._input.setPlaceholderText(name)
        self._input.textChanged.connect(self._on_input_changed)

        self._action_btn = QPushButton(action_label)
        self._action_btn.setProperty("role", "danger")
        self._action_btn.setEnabled(False)
        self._action_btn.clicked.connect(self.accept)

        cancel = QPushButton("Cancel")
        cancel.setProperty("role", "ghost")
        cancel.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(self._action_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(12)
        root.addWidget(body)
        root.addWidget(prompt)
        root.addWidget(self._input)
        root.addLayout(buttons)

    def _on_input_changed(self, text: str) -> None:
        self._action_btn.setEnabled(text == self._name)


# Kept for convenience — some modules import from here.
__all__ = [
    "COMMON_FRAPPE_REFS",
    "GetAppDialog",
    "GetAppValues",
    "InstallAppDialog",
    "InstallAppValues",
    "NewAppDialog",
    "NewAppValues",
    "NewBenchDialog",
    "NewBenchValues",
    "NewSiteDialog",
    "NewSiteValues",
    "RestoreSiteDialog",
    "RestoreSiteValues",
    "TypedNameConfirmDialog",
    "confirm",
]
