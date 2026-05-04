"""One tab in the bench detail view, scoped to a single site.

Three sections, top → bottom:

1. **Site info** — small dim line with ``db`` + ``apps installed``.
2. **Maintenance** — Migrate, Clear cache, Clear website cache, Backup.
   Each click pre-fills the embedded :class:`BenchCommandRunner` with a
   ``bench --site …`` command; the user reviews and presses Enter.
3. **Run any command** — embedded :class:`BenchCommandRunner` (default
   chips suppressed: the buttons above already cover those actions, so
   chips would just duplicate them).

The "Run any command" section also hosts two extra buttons that act
on the live site rather than pre-fill the runner:

- **Open in browser** — only visible when the bench process is
  running, since the URL only resolves while ``bench start`` has the
  webserver up.
- **Delete site** — opens a typed-name confirmation popup, then runs
  ``bench drop-site …`` through the runner so the output streams to
  the same terminal log as everything else.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from benchbox_core import introspect
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.widgets.command_runner import BenchCommandRunner

_SECTION_SPACING_TOP: int = 4
_SECTION_SPACING_BELOW: int = 2


def _open_in_browser(url: str) -> None:
    """Hand off to the system default browser via Qt."""
    QDesktopServices.openUrl(QUrl(url))


def _section_header(title: str) -> QWidget:
    """Render an all-caps section title with a thin separator below it."""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, _SECTION_SPACING_TOP, 0, _SECTION_SPACING_BELOW)
    layout.setSpacing(4)

    label = QLabel(title.upper())
    label.setProperty("role", "dim")
    label.setStyleSheet("font-weight: 700; letter-spacing: 1.4px; font-size: 10pt;")

    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Plain)
    line.setStyleSheet("color: #44475a; max-height: 1px;")

    layout.addWidget(label)
    layout.addWidget(line)
    return container


class SiteTab(QWidget):
    """Per-site working area embedded inside the bench detail's QTabWidget.

    Signals:
        delete_site_requested(Path, str): user clicked Delete site;
            parent should run a typed confirm + drive the actual drop.
            The parent calls back into :meth:`run_drop_site` with the
            real command and a masked display string so the password
            doesn't end up in the runner's log.
    """

    delete_site_requested = Signal(Path, str)

    def __init__(
        self,
        bench_path: Path,
        site: introspect.SiteInfo,
        *,
        webserver_port: int = 8000,
        bench_running: bool = False,
        bench_apps: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bench_path = bench_path
        self._site = site
        self._url = f"http://{site.name}:{webserver_port}"
        # Bench-wide apps list, used as a fallback when introspect's
        # filesystem reads couldn't determine which apps are installed
        # on *this* site (modern Frappe stores that in the DB rather
        # than apps.txt). At least we can show what's *available* in
        # the bench so the user isn't staring at "(none)".
        self._bench_apps: list[str] = list(bench_apps or [])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 1. ---- site info -----------------------------------------
        layout.addWidget(_section_header("Site info"))
        layout.addLayout(self._build_info_row())
        layout.addSpacing(6)

        # 2. ---- maintenance ---------------------------------------
        layout.addWidget(_section_header("Maintenance"))
        layout.addLayout(self._build_maintenance_grid())
        layout.addSpacing(6)

        # 3. ---- run any command ----------------------------------
        layout.addWidget(_section_header("Run any command"))
        layout.addLayout(self._build_runner_actions_row())
        # show_chips=False so the embedded runner doesn't repeat the
        # Migrate / Clear cache buttons rendered in the Maintenance
        # section above.
        self._runner = BenchCommandRunner(locked_site=site.name, show_chips=False)
        self._runner.set_bench(bench_path, [site.name])
        self._runner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._runner, 1)

        # Reflect the initial bench-running state — toggles Open in
        # browser visibility immediately so the first paint is correct.
        self.set_bench_running(bench_running)

    # --- public API ---------------------------------------------------

    @property
    def site_name(self) -> str:
        return self._site.name

    @property
    def bench_path(self) -> Path:
        return self._bench_path

    @property
    def runner(self) -> BenchCommandRunner:
        """The embedded runner — exposed so the parent can dispatch
        commands (e.g. drop-site after a typed confirm) into the same
        terminal the user is already looking at."""
        return self._runner

    def set_bench_running(self, running: bool) -> None:
        """Show/hide the Open in browser button based on bench state.

        The site URL only resolves while ``bench start`` has the
        webserver up, so showing the button when the bench is stopped
        would lead to a broken-link click.
        """
        self._open_browser_btn.setVisible(running)

    def shutdown(self) -> None:
        """Kill any in-flight command — called on app shutdown / tab destroy."""
        self._runner.shutdown()

    def run_drop_site(self, *, root_password: str) -> bool:
        """Spawn ``bench drop-site`` through the runner with the password masked.

        Returns ``False`` if the runner is busy. The displayed command
        masks the password; the actual subprocess receives the real
        value via ``--root-password``. Output streams into the runner's
        log like any other command.
        """
        site = self._site.name
        # shlex.quote so a password with shell-special chars stays one
        # argv token. The display string sticks to a fixed mask; we
        # never echo the real value to the log.
        real_cmd = (
            f"bench drop-site {shlex.quote(site)} "
            f"--root-password {shlex.quote(root_password)} --no-backup"
        )
        display_cmd = f"bench drop-site {site} --root-password ******** --no-backup"
        return self._runner.run_command(real_cmd, display=display_cmd)

    # --- section builders -------------------------------------------

    def _build_info_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)

        db_label = QLabel(f"<b>db</b> {self._site.db_name or '—'}")
        db_label.setProperty("role", "dim")
        row.addWidget(db_label)

        apps_label = QLabel(self._format_apps_text())
        apps_label.setProperty("role", "dim")
        apps_label.setWordWrap(True)
        row.addWidget(apps_label, 1)
        return row

    def _format_apps_text(self) -> str:
        """Compose the ``apps …`` line.

        Order of preference:
        1. ``site.installed_apps`` from introspect — most accurate when
           ``apps.txt`` / ``site_config`` actually carries it.
        2. Bench-wide app list with a ``(from bench)`` hint — modern
           Frappe keeps the per-site list in the DB only, so this is
           the next-best signal we can read without spawning ``bench
           --site … list-apps``.
        3. ``(none)`` when even the bench has no apps registered.
        """
        if self._site.installed_apps:
            return "<b>apps</b> " + ", ".join(self._site.installed_apps)
        if self._bench_apps:
            joined = ", ".join(self._bench_apps)
            return (
                f"<b>apps</b> {joined} "
                f'<span style="opacity:0.65;">(from bench — run '
                f"<code>bench --site {self._site.name} list-apps</code> to verify)</span>"
            )
        return "<b>apps</b> (none)"

    def _build_maintenance_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)

        migrate = self._mk_button("Migrate", role="primary")
        migrate.clicked.connect(
            lambda: self._runner.prefill(f"bench --site {self._site.name} migrate")
        )

        clear_cache = self._mk_button("Clear cache")
        clear_cache.clicked.connect(
            lambda: self._runner.prefill(f"bench --site {self._site.name} clear-cache")
        )

        clear_web = self._mk_button("Clear website cache")
        clear_web.clicked.connect(
            lambda: self._runner.prefill(
                f"bench --site {self._site.name} clear-website-cache"
            )
        )

        backup = self._mk_button("Backup")
        backup.clicked.connect(
            lambda: self._runner.prefill(f"bench --site {self._site.name} backup")
        )

        buttons = [migrate, clear_cache, clear_web, backup]
        for index, button in enumerate(buttons):
            row, col = divmod(index, 3)
            grid.addWidget(button, row, col)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        return grid

    def _build_runner_actions_row(self) -> QHBoxLayout:
        """Small button row that sits above the runner's input field.

        Holds the actions that don't fit the "pre-fill the input" pattern:
        Open in browser launches an external app, Delete site needs a
        typed confirmation gate before it ever touches the runner.
        """
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._open_browser_btn = self._mk_button("Open in browser")
        self._open_browser_btn.clicked.connect(lambda: _open_in_browser(self._url))
        # Hidden by default; ``set_bench_running(True)`` flips it on.
        self._open_browser_btn.setVisible(False)
        row.addWidget(self._open_browser_btn)

        delete_btn = self._mk_button("Delete site", role="danger")
        delete_btn.clicked.connect(
            lambda: self.delete_site_requested.emit(self._bench_path, self._site.name)
        )
        row.addWidget(delete_btn)

        row.addStretch(1)
        return row

    # --- helpers ------------------------------------------------------

    def _mk_button(self, label: str, *, role: str | None = None) -> QPushButton:
        btn = QPushButton(label)
        if role is not None:
            btn.setProperty("role", role)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(34)
        return btn


__all__ = ["SiteTab"]
