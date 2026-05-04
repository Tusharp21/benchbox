"""One tab in the bench detail view, scoped to a single site.

Layout, top → bottom:

- Compact info strip — small dim labels for ``db`` and ``apps installed``.
  No links or badges; just the facts the user needs to remember which
  site they're working on.
- A grid of action buttons — every site-level option lives here as a
  proper :class:`QPushButton`: Open in browser, Migrate, Clear cache,
  Clear website cache, Backup, Drop site (the last one styled as
  danger).
- A :class:`BenchCommandRunner` whose chips and free-form input run
  ``bench --site <this-site> ...`` so any further command targets this
  site by default.

The buttons emit either signals (Drop) or pre-fill the embedded runner
with the relevant ``bench --site …`` invocation; the user reviews the
filled command and presses Enter. We never fire-and-forget a bench
mutation from a click — that's how foot-guns happen on heavy
operations.
"""

from __future__ import annotations

from pathlib import Path

from benchbox_core import introspect
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.widgets.command_runner import BenchCommandRunner


def _open_in_browser(url: str) -> None:
    """Hand off to the system default browser via Qt."""
    QDesktopServices.openUrl(QUrl(url))


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

        # ---- compact info strip -------------------------------------
        # Dim labels only — every interactive thing lives below as a
        # button. Keeping this row visual-only stops the page reading
        # like a status panel.
        info_row = QHBoxLayout()
        info_row.setContentsMargins(0, 0, 0, 0)
        info_row.setSpacing(16)

        db_label = QLabel(f"<b>db</b> {site.db_name or '—'}")
        db_label.setProperty("role", "dim")
        info_row.addWidget(db_label)

        apps_text = ", ".join(site.installed_apps) if site.installed_apps else "(none)"
        apps_label = QLabel(f"<b>apps</b> {apps_text}")
        apps_label.setProperty("role", "dim")
        apps_label.setWordWrap(True)
        info_row.addWidget(apps_label, 1)

        # ---- action grid -------------------------------------------
        # 3-column responsive-ish grid of buttons. Every action the
        # user can take on this site is here, all uniform shape and
        # weight, so the page reads as "pick what to do" rather than
        # "skim a status panel".
        action_grid = QGridLayout()
        action_grid.setHorizontalSpacing(8)
        action_grid.setVerticalSpacing(8)
        action_grid.setContentsMargins(0, 0, 0, 0)

        open_browser = self._mk_button("Open in browser")
        open_browser.clicked.connect(lambda: _open_in_browser(self._url))

        migrate = self._mk_button("Migrate", role="primary")
        migrate.clicked.connect(
            lambda: self._fill_runner_with(f"bench --site {site.name} migrate")
        )

        clear_cache = self._mk_button("Clear cache")
        clear_cache.clicked.connect(
            lambda: self._fill_runner_with(f"bench --site {site.name} clear-cache")
        )

        clear_web = self._mk_button("Clear website cache")
        clear_web.clicked.connect(
            lambda: self._fill_runner_with(f"bench --site {site.name} clear-website-cache")
        )

        backup = self._mk_button("Backup")
        backup.clicked.connect(
            lambda: self._fill_runner_with(f"bench --site {site.name} backup")
        )

        drop = self._mk_button("Drop site", role="danger")
        drop.clicked.connect(lambda: self.drop_requested.emit(self._bench_path, self._site.name))

        # Lay out 3 buttons per row, primary action first.
        buttons = [migrate, open_browser, clear_cache, clear_web, backup, drop]
        for index, button in enumerate(buttons):
            row, col = divmod(index, 3)
            action_grid.addWidget(button, row, col)
        # Equal column stretch so each button gets the same width and
        # the row reads as a button matrix, not a left-anchored list.
        for col in range(3):
            action_grid.setColumnStretch(col, 1)

        # ---- command runner (locked to this site) ------------------
        self._runner = BenchCommandRunner(locked_site=site.name)
        self._runner.set_bench(bench_path, [site.name])
        self._runner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        runner_label = QLabel(f"Run commands on <b>{site.name}</b>")
        runner_label.setProperty("role", "dim")

        # ---- assembly -----------------------------------------------
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addLayout(info_row)
        layout.addLayout(action_grid)
        layout.addSpacing(4)
        layout.addWidget(runner_label)
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

    # --- helpers ------------------------------------------------------

    def _mk_button(self, label: str, *, role: str | None = None) -> QPushButton:
        btn = QPushButton(label)
        if role is not None:
            btn.setProperty("role", role)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Buttons in the grid stretch with the column; without a min
        # height they look anemic next to the dropdown menus in the
        # sticky header.
        btn.setMinimumHeight(34)
        return btn

    def _fill_runner_with(self, command: str) -> None:
        """Drop ``command`` into the runner's input field and focus it.

        Pre-fill rather than fire-and-forget: every option here is heavy
        enough that an accidental double-click on the wrong site is
        worth guarding against. The user confirms by pressing Enter.
        """
        self._runner._input.setText(command)  # noqa: SLF001
        self._runner._input.setFocus()  # noqa: SLF001


__all__ = ["SiteTab"]
