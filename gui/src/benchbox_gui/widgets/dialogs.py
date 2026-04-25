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

# --- LiveLogDialog (shared base for any op that wants live output) ----


class LiveLogDialog(QDialog):
    """Dialog with form → live log → close transitions and an embedded worker.

    Subclass contract:
    - In ``__init__``, build form widgets and pass them through
      :meth:`set_form_layout` along with a primary-button label.
    - Override :meth:`_collect_values` to validate the form and return a
      values dataclass (or ``None`` after showing a warning yourself).
    - Override :meth:`_build_op` to return a callable taking a
      ``line_callback`` and running the core operation.
    - Optionally override :meth:`_success_text` / :meth:`_running_text`
      for nicer status copy.

    The base owns the log panel, status row, primary/cancel buttons,
    StreamingOpWorker, and lifecycle. Subclasses stay focused on the
    form + the op factory.
    """

    def __init__(
        self,
        *,
        title: str,
        primary_text: str,
        parent: QWidget | None = None,
        min_size: tuple[int, int] = (720, 540),
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(*min_size)

        self._worker: StreamingOpWorker | None = None
        self._values: object | None = None
        self._primary_default_text: str = primary_text

        self._form_holder = QWidget()  # placeholder; subclass replaces via set_form_layout

        self._status = QLabel()
        self._status.setProperty("role", "dim")
        self._status.setVisible(False)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(10_000)
        mono = QFont("JetBrains Mono, Fira Code, Courier New", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._log.setFont(mono)
        self._log.setVisible(False)

        self._primary = QPushButton(primary_text)
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

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(20, 20, 20, 16)
        self._root.setSpacing(14)
        self._root.addWidget(self._form_holder)
        self._root.addWidget(self._status)
        self._root.addWidget(self._log, 1)
        self._root.addLayout(buttons_row)

    # --- subclass plumbing -----------------------------------------

    def set_form_layout(self, form_layout: QFormLayout) -> None:
        """Mount the subclass's form layout in place of the placeholder."""
        new_holder = QWidget()
        new_holder.setLayout(form_layout)
        self._root.replaceWidget(self._form_holder, new_holder)
        self._form_holder.deleteLater()
        self._form_holder = new_holder

    def set_log_placeholder(self, text: str) -> None:
        self._log.setPlaceholderText(text)

    # --- subclass hooks --------------------------------------------

    def _collect_values(self) -> object | None:
        """Validate form input, return a values object, or return None
        (after the subclass has shown its own QMessageBox)."""
        raise NotImplementedError

    def _build_op(self, values: object) -> Callable[[Callable[[str], None]], Any]:
        """Return a callable that runs the operation, accepting a
        line_callback to forward to the underlying CommandRunner."""
        raise NotImplementedError

    def _success_text(self) -> str:
        return "Done."

    def _running_text(self) -> str:
        return "Working…"

    # --- lifecycle --------------------------------------------------

    def values(self) -> object:
        """The values used to launch the op (set after primary click)."""
        if self._values is None:
            raise RuntimeError("values() called before the operation started")
        return self._values

    def _on_primary(self) -> None:
        # Two roles: launch the op (when no worker yet) or close-as-accepted.
        if self._worker is None:
            self._start_op()
        else:
            self.accept()

    def _start_op(self) -> None:
        values = self._collect_values()
        if values is None:
            return
        self._values = values

        self._form_holder.setEnabled(False)
        self._log.setVisible(True)
        self._status.setVisible(True)
        self._status.setText(self._running_text())
        self._primary.setEnabled(False)
        self._primary.setText("Working…")
        self._cancel.setEnabled(False)

        op = self._build_op(values)
        self._worker = StreamingOpWorker(op)
        self._worker.line_received.connect(self._append_log)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _append_log(self, line: str) -> None:
        self._log.appendPlainText(line.rstrip("\n"))

    def _on_succeeded(self, _result: object) -> None:
        self._status.setText(f"✓ {self._success_text()}")
        self._primary.setText("Close")
        self._primary.setEnabled(True)
        self._cancel.setVisible(False)

    def _on_failed(self, exc: object) -> None:
        self._status.setText(f"✗ Failed: {exc}")
        self._primary.setText("Close")
        self._primary.setEnabled(True)
        # Failure → primary acts as Reject so the caller skips its
        # "refresh on success" branch.
        self._primary.clicked.disconnect()
        self._primary.clicked.connect(self.reject)
        self._cancel.setVisible(False)


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


class NewBenchDialog(LiveLogDialog):
    """Form → live ``bench init`` log → close."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="New bench",
            primary_text="Create bench",
            parent=parent,
            min_size=(760, 580),
        )
        self.set_log_placeholder("Live `bench init` output will appear here once you click Create bench.")

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
        self.set_form_layout(form)

    def _on_browse(self) -> None:
        picked = QFileDialog.getExistingDirectory(self, "Choose parent directory", str(Path.home()))
        if picked:
            default_name = "frappe-bench"
            self._path.setText(str(Path(picked) / default_name))

    def _collect_values(self) -> NewBenchValues | None:
        text = self._path.text().strip() or self._path.placeholderText()
        if not text:
            QMessageBox.warning(self, "Missing path", "Choose where to create the bench.")
            return None
        branch = self._branch.currentText().strip() or DEFAULT_FRAPPE_BRANCH
        return NewBenchValues(
            path=Path(text).expanduser(),
            frappe_branch=branch,
            python_bin=self._python.text().strip() or DEFAULT_PYTHON_BIN,
        )

    def _build_op(self, values: object) -> Callable[[Callable[[str], None]], Any]:
        from benchbox_core import bench as core_bench

        v: NewBenchValues = values  # type: ignore[assignment]

        def op(line_cb: Callable[[str], None]) -> Any:
            return core_bench.create_bench(
                v.path,
                frappe_branch=v.frappe_branch,
                python_bin=v.python_bin,
                line_callback=line_cb,
            )

        return op

    def _success_text(self) -> str:
        v: NewBenchValues = self._values  # type: ignore[assignment]
        return f"Bench created at {v.path}"

    def _running_text(self) -> str:
        v: NewBenchValues = self._values  # type: ignore[assignment]
        return f"Initialising bench at {v.path} (clones Frappe + npm install — can take ~10 minutes)…"


# --- NewSiteDialog -----------------------------------------------------


@dataclass(frozen=True)
class NewSiteValues:
    bench_path: Path
    site_name: str
    admin_password: str
    install_apps: tuple[str, ...]
    set_default: bool


class NewSiteDialog(LiveLogDialog):
    """Form → live ``bench new-site`` log → close.

    ``apps_by_bench`` (optional) maps each bench path to the apps available
    *in that bench*. When provided, the dialog shows a checkable list of
    apps. ``db_root_password`` is required and is loaded from the
    credentials store by the caller — we don't prompt for it here.
    """

    def __init__(
        self,
        bench_paths: list[Path],
        *,
        db_root_password: str,
        parent: QWidget | None = None,
        preselect: Path | None = None,
        apps_by_bench: dict[Path, list[str]] | None = None,
    ) -> None:
        super().__init__(
            title="New site",
            primary_text="Create site",
            parent=parent,
            min_size=(720, 560),
        )
        self.set_log_placeholder("Live `bench new-site` output will appear here once you click Create site.")
        self._apps_by_bench = apps_by_bench or {}
        self._db_root_password = db_root_password

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
        self.set_form_layout(form)

        if not bench_paths:
            self._bench.setEnabled(False)
            self._bench.addItem("(no benches found — create one first)")

        self._reload_app_choices()

    def _reload_app_choices(self) -> None:
        self._apps_list.clear()
        bench = self._bench.currentData()
        if bench is None:
            return
        apps = [a for a in self._apps_by_bench.get(bench, []) if a != "frappe"]
        for app in apps:
            item = QListWidgetItem(app)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._apps_list.addItem(item)

    def _collect_values(self) -> NewSiteValues | None:
        if not self._name.text().strip():
            QMessageBox.warning(self, "Missing name", "Site name is required.")
            return None
        if not self._admin.text():
            QMessageBox.warning(self, "Missing password", "Administrator password is required.")
            return None
        if self._bench.currentData() is None:
            QMessageBox.warning(self, "No bench", "Create a bench first, then come back.")
            return None
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

    def _build_op(self, values: object) -> Callable[[Callable[[str], None]], Any]:
        from benchbox_core import site as core_site

        v: NewSiteValues = values  # type: ignore[assignment]
        db_root = self._db_root_password

        def op(line_cb: Callable[[str], None]) -> Any:
            return core_site.create_site(
                v.bench_path,
                v.site_name,
                db_root_password=db_root,
                admin_password=v.admin_password,
                install_apps=v.install_apps,
                set_default=v.set_default,
                line_callback=line_cb,
            )

        return op

    def _success_text(self) -> str:
        v: NewSiteValues = self._values  # type: ignore[assignment]
        return f"Site {v.site_name} created."

    def _running_text(self) -> str:
        v: NewSiteValues = self._values  # type: ignore[assignment]
        return f"Creating {v.site_name} (DB + migrate + asset build)…"


# --- GetAppDialog ------------------------------------------------------


@dataclass(frozen=True)
class GetAppValues:
    bench_path: Path
    git_url: str
    branch: str | None


class GetAppDialog(LiveLogDialog):
    """Form → live ``bench get-app`` log → close."""

    def __init__(
        self,
        bench_paths: list[Path],
        *,
        parent: QWidget | None = None,
        preselect: Path | None = None,
    ) -> None:
        super().__init__(
            title="Get app",
            primary_text="Get app",
            parent=parent,
            min_size=(760, 560),
        )
        self.set_log_placeholder(
            "Live `bench get-app` output will appear here once you click Get app."
        )

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
        self.set_form_layout(form)

    def _collect_values(self) -> GetAppValues | None:
        url = self._url.text().strip()
        if not url:
            QMessageBox.warning(self, "Missing URL", "Git URL is required.")
            return None
        bench_path = self._bench.currentData()
        if bench_path is None:
            QMessageBox.warning(self, "No bench", "No bench available; create one first.")
            return None
        branch = self._branch.text().strip() or None
        token = self._token.text().strip()
        if token:
            url = _inject_token(url, token)
        return GetAppValues(bench_path=bench_path, git_url=url, branch=branch)

    def _build_op(self, values: object) -> Callable[[Callable[[str], None]], Any]:
        from benchbox_core import app as core_app

        v: GetAppValues = values  # type: ignore[assignment]

        def op(line_cb: Callable[[str], None]) -> Any:
            return core_app.get_app(
                v.bench_path,
                v.git_url,
                branch=v.branch,
                line_callback=line_cb,
            )

        return op

    def _success_text(self) -> str:
        return "App fetched."

    def _running_text(self) -> str:
        v: GetAppValues = self._values  # type: ignore[assignment]
        return f"Fetching {v.git_url} into {v.bench_path}…"


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


class NewAppDialog(LiveLogDialog):
    """Form → live ``bench new-app`` log → close."""

    def __init__(
        self,
        bench_paths: list[Path],
        *,
        parent: QWidget | None = None,
        preselect: Path | None = None,
    ) -> None:
        super().__init__(
            title="New app",
            primary_text="Create app",
            parent=parent,
            min_size=(720, 540),
        )
        self.set_log_placeholder(
            "Live `bench new-app` output will appear here once you click Create."
        )

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
        self.set_form_layout(form)

    def _collect_values(self) -> NewAppValues | None:
        bench_path = self._bench.currentData()
        if bench_path is None:
            QMessageBox.warning(self, "No bench", "No bench available; create one first.")
            return None
        app_name = self._app_name.text().strip()
        if not _APP_NAME_RE.match(app_name):
            QMessageBox.warning(
                self,
                "Invalid app name",
                "App name must start with a lowercase letter and contain only "
                "lowercase letters, digits, and underscores.",
            )
            return None
        if app_name == "frappe":
            QMessageBox.warning(self, "Reserved name", "'frappe' is reserved — pick another name.")
            return None

        title = self._title.text().strip() or app_name.replace("_", " ").title()
        publisher = self._publisher.text().strip() or "benchbox"
        email = self._email.text().strip() or "dev@example.com"

        return NewAppValues(
            bench_path=bench_path,
            app_name=app_name,
            title=title,
            publisher=publisher,
            email=email,
        )

    def _build_op(self, values: object) -> Callable[[Callable[[str], None]], Any]:
        from benchbox_core import app as core_app

        v: NewAppValues = values  # type: ignore[assignment]

        def op(line_cb: Callable[[str], None]) -> Any:
            return core_app.new_app(
                v.bench_path,
                v.app_name,
                title=v.title,
                publisher=v.publisher,
                email=v.email,
                line_callback=line_cb,
            )

        return op

    def _success_text(self) -> str:
        v: NewAppValues = self._values  # type: ignore[assignment]
        return f"App {v.app_name} scaffolded."

    def _running_text(self) -> str:
        v: NewAppValues = self._values  # type: ignore[assignment]
        return f"Scaffolding {v.app_name} in {v.bench_path}…"


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


class RestoreSiteDialog(LiveLogDialog):
    """Form → live ``bench restore`` log → close."""

    def __init__(
        self,
        bench_sites: dict[Path, list[str]],
        *,
        db_root_password: str,
        parent: QWidget | None = None,
        preselect_bench: Path | None = None,
        preselect_site: str | None = None,
    ) -> None:
        super().__init__(
            title="Restore site",
            primary_text="Restore site",
            parent=parent,
            min_size=(760, 580),
        )
        self.set_log_placeholder(
            "Live `bench restore` output will appear here once you click Restore site."
        )
        self._bench_sites = bench_sites
        self._db_root_password = db_root_password

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
        self.set_form_layout(form)

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

    def _collect_values(self) -> RestoreSiteValues | None:
        if self._bench.currentData() is None:
            QMessageBox.warning(self, "No bench", "No bench selected.")
            return None
        if not self._site.currentText():
            QMessageBox.warning(self, "No site", "This bench has no sites to restore into.")
            return None
        sql = self._sql.text().strip()
        if not sql:
            QMessageBox.warning(self, "Missing backup", "Pick a SQL backup file.")
            return None
        if not Path(sql).expanduser().is_file():
            QMessageBox.warning(self, "Backup not found", f"SQL backup does not exist:\n{sql}")
            return None

        def _opt_path(text: str) -> Path | None:
            t = text.strip()
            return Path(t).expanduser() if t else None

        return RestoreSiteValues(
            bench_path=self._bench.currentData(),
            site_name=self._site.currentText(),
            sql_path=Path(sql).expanduser(),
            admin_password=self._admin.text() or None,
            with_public_files=_opt_path(self._public.text()),
            with_private_files=_opt_path(self._private.text()),
            force=self._force.isChecked(),
        )

    def _build_op(self, values: object) -> Callable[[Callable[[str], None]], Any]:
        from benchbox_core import site as core_site

        v: RestoreSiteValues = values  # type: ignore[assignment]
        db_root = self._db_root_password

        def op(line_cb: Callable[[str], None]) -> Any:
            return core_site.restore_site(
                v.bench_path,
                v.site_name,
                v.sql_path,
                db_root_password=db_root,
                admin_password=v.admin_password,
                with_public_files=v.with_public_files,
                with_private_files=v.with_private_files,
                force=v.force,
                line_callback=line_cb,
            )

        return op

    def _success_text(self) -> str:
        v: RestoreSiteValues = self._values  # type: ignore[assignment]
        return f"Site {v.site_name} restored from {v.sql_path.name}."

    def _running_text(self) -> str:
        v: RestoreSiteValues = self._values  # type: ignore[assignment]
        return f"Restoring {v.site_name} from {v.sql_path.name}…"


# --- InstallAppDialog --------------------------------------------------


@dataclass(frozen=True)
class InstallAppValues:
    bench_path: Path
    site_name: str
    apps: tuple[str, ...]
    force: bool = False


class InstallAppDialog(LiveLogDialog):
    """Form → live ``bench install-app`` log → close."""

    def __init__(
        self,
        bench_sites: dict[Path, list[str]],
        bench_apps: dict[Path, list[str]],
        *,
        parent: QWidget | None = None,
        preselect_bench: Path | None = None,
        preselect_app: str | None = None,
    ) -> None:
        super().__init__(
            title="Install app",
            primary_text="Install app",
            parent=parent,
            min_size=(720, 540),
        )
        self.set_log_placeholder(
            "Live `bench install-app` output will appear here once you click Install app."
        )
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
        self.set_form_layout(form)

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

    def _collect_values(self) -> InstallAppValues | None:
        if self._bench.currentData() is None:
            QMessageBox.warning(self, "No bench", "No bench selected.")
            return None
        if not self._site.currentText():
            QMessageBox.warning(self, "No site", "This bench has no sites yet.")
            return None
        if not self._app.currentText():
            QMessageBox.warning(self, "No app", "This bench has no other apps installed.")
            return None
        return InstallAppValues(
            bench_path=self._bench.currentData(),
            site_name=self._site.currentText(),
            apps=(self._app.currentText(),),
            force=self._force.isChecked(),
        )

    def _build_op(self, values: object) -> Callable[[Callable[[str], None]], Any]:
        from benchbox_core import app as core_app

        v: InstallAppValues = values  # type: ignore[assignment]

        def op(line_cb: Callable[[str], None]) -> Any:
            return core_app.install_app(
                v.bench_path,
                v.site_name,
                v.apps,
                force=v.force,
                line_callback=line_cb,
            )

        return op

    def _success_text(self) -> str:
        v: InstallAppValues = self._values  # type: ignore[assignment]
        return f"Installed {', '.join(v.apps)} on {v.site_name}."

    def _running_text(self) -> str:
        v: InstallAppValues = self._values  # type: ignore[assignment]
        return f"Installing {', '.join(v.apps)} on {v.site_name}…"


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
    "LiveLogDialog",
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
