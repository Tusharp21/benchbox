"""One tab in the bench detail view, scoped to a single site.

Three sections, top → bottom:

1. **Site info** — a compact 2-column key/value table (db, apps).
2. **Maintenance** — Migrate, Clear cache, Clear website cache, Backup.
   Each click pre-fills the embedded :class:`BenchCommandRunner` with
   a ``bench --site …`` command; the user reviews and presses Enter.
3. **Run any command** — embedded :class:`BenchCommandRunner` (default
   chips suppressed: the buttons above already cover those actions).

Open in browser and Drop site live on the bench-detail page's bottom
:class:`BenchProcessDock` rather than in this tab. The dock listens
for tab changes and re-targets those buttons to whichever site tab
the user is on, so the actions are always one mouse-move away
without each site tab having to repaint them.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from benchbox_core import introspect
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.widgets.command_runner import BenchCommandRunner

_SECTION_SPACING_TOP: int = 4
_SECTION_SPACING_BELOW: int = 2


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
    """Per-site working area embedded inside the bench detail's QTabWidget."""

    def __init__(
        self,
        bench_path: Path,
        site: introspect.SiteInfo,
        *,
        webserver_port: int = 8000,
        bench_apps: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bench_path = bench_path
        self._site = site
        self._url = f"http://{site.name}:{webserver_port}"
        # Bench-wide apps list, used as a fallback when introspect
        # couldn't determine which apps are installed on *this* site
        # (modern Frappe stores that in the DB rather than apps.txt).
        # At least we can show what's *available* in the bench so the
        # user isn't staring at "(none)".
        self._bench_apps: list[str] = list(bench_apps or [])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 1. ---- site info -----------------------------------------
        layout.addWidget(_section_header("Site info"))
        layout.addLayout(self._build_info_table())
        layout.addSpacing(6)

        # 2. ---- maintenance ---------------------------------------
        layout.addWidget(_section_header("Maintenance"))
        layout.addLayout(self._build_maintenance_grid())
        layout.addSpacing(6)

        # 3. ---- run any command ----------------------------------
        layout.addWidget(_section_header("Run any command"))
        # show_chips=False so the embedded runner doesn't repeat the
        # Migrate / Clear cache buttons rendered in the Maintenance
        # section above.
        self._runner = BenchCommandRunner(locked_site=site.name, show_chips=False)
        self._runner.set_bench(bench_path, [site.name])
        self._runner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._runner, 1)

    # --- public API ---------------------------------------------------

    @property
    def site_name(self) -> str:
        return self._site.name

    @property
    def bench_path(self) -> Path:
        return self._bench_path

    @property
    def url(self) -> str:
        return self._url

    @property
    def runner(self) -> BenchCommandRunner:
        """The embedded runner — exposed so the parent can dispatch
        commands (e.g. drop-site after a typed confirm) into the same
        terminal the user is already looking at."""
        return self._runner

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
        real_cmd = (
            f"bench drop-site {shlex.quote(site)} "
            f"--root-password {shlex.quote(root_password)} --no-backup"
        )
        display_cmd = f"bench drop-site {site} --root-password ******** --no-backup"
        return self._runner.run_command(real_cmd, display=display_cmd)

    # --- section builders -------------------------------------------

    def _build_info_table(self) -> QGridLayout:
        """Compact 2-column key/value table.

        QGridLayout with a fixed-width key column on the left and a
        wrap-friendly value column on the right reads like a metadata
        table without bringing the QTableWidget chrome (selection
        backgrounds, header bar, sort arrows) we don't want here.
        """
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)
        # Value column expands; the key column stays compact at its
        # text's natural width.
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

        rows: list[tuple[str, str, bool]] = [
            ("db", self._site.db_name or "—", False),
            ("apps", self._format_apps_value(), True),
        ]

        for row_idx, (key, value, rich) in enumerate(rows):
            key_label = QLabel(key)
            key_label.setProperty("role", "dim")
            key_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

            value_label = QLabel(value)
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if rich:
                value_label.setTextFormat(Qt.TextFormat.RichText)
            grid.addWidget(key_label, row_idx, 0)
            grid.addWidget(value_label, row_idx, 1)
        return grid

    def _format_apps_value(self) -> str:
        """Apps line — site-specific list first, bench-wide fallback otherwise."""
        if self._site.installed_apps:
            return ", ".join(self._site.installed_apps)
        if self._bench_apps:
            joined = ", ".join(self._bench_apps)
            return (
                f"{joined} "
                f'<span style="opacity:0.65;">(from bench — run '
                f"<code>bench --site {self._site.name} list-apps</code> to verify)</span>"
            )
        return "(none)"

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

    # --- helpers ------------------------------------------------------

    def _mk_button(self, label: str, *, role: str | None = None) -> QPushButton:
        btn = QPushButton(label)
        if role is not None:
            btn.setProperty("role", role)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(34)
        return btn


__all__ = ["SiteTab"]
