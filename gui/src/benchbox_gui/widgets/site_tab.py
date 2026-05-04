"""One tab in the bench detail view, scoped to a single site.

The tab is laid out as a settings-style page with explicit section
headers so the user can scan it like a checklist instead of a wall of
buttons:

1. **Site info** — small dim line with ``db`` + ``apps installed``.
2. **Maintenance** — Migrate, Clear cache, Clear website cache, Backup.
3. **Browse** — Open in browser.
4. **Danger zone** — Drop site (visually distinct via the ``danger``
   button role).
5. **Run any command** — embedded :class:`BenchCommandRunner` (with
   default chips suppressed: the buttons above already cover those
   actions, so chips would just duplicate them).

Every clickable action is a :class:`QPushButton` — no clickable links
or status pills masquerading as actions. Clicks pre-fill the runner
with the relevant ``bench --site …`` invocation; the user reviews and
presses Enter. We never fire-and-forget bench mutations because heavy
operations on the wrong site are real foot-guns.
"""

from __future__ import annotations

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

# Shared spacing so every section header looks identical.
_SECTION_SPACING_TOP: int = 4
_SECTION_SPACING_BELOW: int = 2


def _open_in_browser(url: str) -> None:
    """Hand off to the system default browser via Qt."""
    QDesktopServices.openUrl(QUrl(url))


def _section_header(title: str) -> QWidget:
    """Render an all-caps section title with a thin separator below it.

    Returned as a single widget so a layout can ``addWidget`` it without
    having to add and pad two children. The hairline separator below
    keeps each section feeling like a discrete block without resorting
    to QGroupBox borders.
    """
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, _SECTION_SPACING_TOP, 0, _SECTION_SPACING_BELOW)
    layout.setSpacing(4)

    label = QLabel(title.upper())
    label.setProperty("role", "dim")
    # Slightly tighter letter-spacing + bold so it reads as a
    # section heading rather than just dim text.
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
        drop_requested(Path, str): user clicked Drop site (bench_path, site_name).
    """

    drop_requested = Signal(Path, str)

    def __init__(
        self,
        bench_path: Path,
        site: introspect.SiteInfo,
        *,
        webserver_port: int = 8000,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bench_path = bench_path
        self._site = site
        self._url = f"http://{site.name}:{webserver_port}"

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

        # 3. ---- browse --------------------------------------------
        layout.addWidget(_section_header("Browse"))
        layout.addLayout(self._build_browse_row())
        layout.addSpacing(6)

        # 4. ---- danger zone --------------------------------------
        layout.addWidget(_section_header("Danger zone"))
        layout.addLayout(self._build_danger_row())
        layout.addSpacing(10)

        # 5. ---- run any command ----------------------------------
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

    def shutdown(self) -> None:
        """Kill any in-flight command — called on app shutdown / tab destroy."""
        self._runner.shutdown()

    # --- section builders -------------------------------------------

    def _build_info_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)

        db_label = QLabel(f"<b>db</b> {self._site.db_name or '—'}")
        db_label.setProperty("role", "dim")
        row.addWidget(db_label)

        apps_text = (
            ", ".join(self._site.installed_apps) if self._site.installed_apps else "(none)"
        )
        apps_label = QLabel(f"<b>apps</b> {apps_text}")
        apps_label.setProperty("role", "dim")
        apps_label.setWordWrap(True)
        row.addWidget(apps_label, 1)
        return row

    def _build_maintenance_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)

        migrate = self._mk_button("Migrate", role="primary")
        migrate.clicked.connect(
            lambda: self._fill_runner_with(f"bench --site {self._site.name} migrate")
        )

        clear_cache = self._mk_button("Clear cache")
        clear_cache.clicked.connect(
            lambda: self._fill_runner_with(f"bench --site {self._site.name} clear-cache")
        )

        clear_web = self._mk_button("Clear website cache")
        clear_web.clicked.connect(
            lambda: self._fill_runner_with(
                f"bench --site {self._site.name} clear-website-cache"
            )
        )

        backup = self._mk_button("Backup")
        backup.clicked.connect(
            lambda: self._fill_runner_with(f"bench --site {self._site.name} backup")
        )

        # 3 buttons per row; equal column stretch so the matrix
        # aligns regardless of label length.
        buttons = [migrate, clear_cache, clear_web, backup]
        for index, button in enumerate(buttons):
            row, col = divmod(index, 3)
            grid.addWidget(button, row, col)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        return grid

    def _build_browse_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        open_browser = self._mk_button("Open in browser")
        open_browser.clicked.connect(lambda: _open_in_browser(self._url))
        row.addWidget(open_browser)

        url_hint = QLabel(self._url)
        url_hint.setProperty("role", "dim")
        url_hint.setWordWrap(True)
        url_hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(url_hint, 1)
        return row

    def _build_danger_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        drop = self._mk_button("Drop site", role="danger")
        drop.clicked.connect(lambda: self.drop_requested.emit(self._bench_path, self._site.name))
        row.addWidget(drop)

        # Tooltip on the explanation rather than the button — the
        # button's danger styling is already loud enough.
        warning = QLabel(
            "Permanently deletes the site directory and its MariaDB database."
        )
        warning.setProperty("role", "dim")
        warning.setWordWrap(True)
        row.addWidget(warning, 1)
        return row

    # --- helpers ------------------------------------------------------

    def _mk_button(self, label: str, *, role: str | None = None) -> QPushButton:
        btn = QPushButton(label)
        if role is not None:
            btn.setProperty("role", role)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(34)
        return btn

    def _fill_runner_with(self, command: str) -> None:
        """Drop ``command`` into the runner's input field and focus it.

        Pre-fill rather than fire-and-forget; every option here is
        heavy enough that an accidental double-click on the wrong site
        is worth guarding against. The user confirms by pressing Enter.
        """
        self._runner._input.setText(command)  # noqa: SLF001
        self._runner._input.setFocus()  # noqa: SLF001


__all__ = ["SiteTab"]
