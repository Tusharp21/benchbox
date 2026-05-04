"""One tab in the bench detail view, scoped to a single site.

Contains everything the user usually wants when they're working on a
specific site: a clickable URL, badges for installed apps, a row of
quick-action chips (migrate / clear cache / open in browser / drop) and
a :class:`BenchCommandRunner` whose chips and free-form input run
``bench --site <this-site> ...``.

Per-site quick chips emit signals so the parent page can sequence
dialogs / confirmations / refreshes — this widget itself does no I/O
beyond what the embedded command runner spawns.
"""

from __future__ import annotations

from pathlib import Path

from benchbox_core import introspect
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
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
        installed_apps_changed_hint(): emitted after a chip the page can
            reasonably expect to mutate apps (e.g. install). Currently
            unused — reserved for Phase 3 chips.
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

        # ---- top info strip ----------------------------------------
        url_label = QLabel(
            f'<a href="{self._url}" '
            f'style="color:#8250df;text-decoration:none;font-weight:600;">'
            f"{site.name} ↗</a>"
        )
        url_label.setOpenExternalLinks(True)
        url_label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        url_label.setCursor(Qt.CursorShape.PointingHandCursor)

        db_label = QLabel(f"<b>db</b> {site.db_name or '—'}")
        db_label.setProperty("role", "dim")

        info_row = QHBoxLayout()
        info_row.setContentsMargins(0, 0, 0, 0)
        info_row.setSpacing(16)
        info_row.addWidget(url_label)
        info_row.addWidget(db_label)
        info_row.addStretch(1)

        # ---- app badges --------------------------------------------
        badges_row = QHBoxLayout()
        badges_row.setContentsMargins(0, 0, 0, 0)
        badges_row.setSpacing(6)
        badges_label = QLabel("apps:")
        badges_label.setProperty("role", "dim")
        badges_row.addWidget(badges_label)
        if site.installed_apps:
            for app in site.installed_apps:
                badge = QLabel(app)
                badge.setProperty("role", "badge")
                badges_row.addWidget(badge)
        else:
            empty = QLabel("(no apps installed yet)")
            empty.setProperty("role", "dim")
            badges_row.addWidget(empty)
        badges_row.addStretch(1)

        # ---- quick action chips ------------------------------------
        chip_row = QHBoxLayout()
        chip_row.setContentsMargins(0, 0, 0, 0)
        chip_row.setSpacing(8)

        migrate = self._mk_chip("↻ Migrate", role="primary")
        migrate.clicked.connect(lambda: self._fill_runner_with(f"bench --site {site.name} migrate"))

        clear_cache = self._mk_chip("⌫ Clear cache")
        clear_cache.clicked.connect(
            lambda: self._fill_runner_with(f"bench --site {site.name} clear-cache")
        )

        clear_web = self._mk_chip("⌫ Clear website cache")
        clear_web.clicked.connect(
            lambda: self._fill_runner_with(f"bench --site {site.name} clear-website-cache")
        )

        backup = self._mk_chip("⤓ Backup")
        backup.clicked.connect(
            lambda: self._fill_runner_with(f"bench --site {site.name} backup")
        )

        open_browser = self._mk_chip("↗ Open in browser")
        open_browser.clicked.connect(lambda: _open_in_browser(self._url))

        drop = self._mk_chip("⌫ Drop site", role="danger")
        drop.clicked.connect(lambda: self.drop_requested.emit(self._bench_path, self._site.name))

        chip_row.addWidget(migrate)
        chip_row.addWidget(clear_cache)
        chip_row.addWidget(clear_web)
        chip_row.addWidget(backup)
        chip_row.addWidget(open_browser)
        chip_row.addStretch(1)
        chip_row.addWidget(drop)

        # ---- command runner (locked to this site) ------------------
        self._runner = BenchCommandRunner(locked_site=site.name)
        self._runner.set_bench(bench_path, [site.name])
        self._runner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        runner_label = QLabel(f"Run commands on <b>{site.name}</b>")
        runner_label.setProperty("role", "dim")

        # ---- assembly -----------------------------------------------
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addLayout(info_row)
        layout.addLayout(badges_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("color: #44475a;")
        layout.addWidget(sep)

        layout.addLayout(chip_row)
        layout.addSpacing(6)
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

    def _mk_chip(self, label: str, *, role: str | None = None) -> QPushButton:
        btn = QPushButton(label)
        if role is not None:
            btn.setProperty("role", role)
        else:
            btn.setProperty("role", "ghost")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _fill_runner_with(self, command: str) -> None:
        """Drop ``command`` into the runner's input field and focus it.

        We deliberately don't fire-and-forget: bench mutations are heavy
        and ``Migrate`` on the wrong site is a real foot-gun. The user
        confirms by pressing Enter.
        """
        # The runner exposes ``_input`` only as a private attr; reaching in
        # keeps the runner's public API minimal. If this becomes painful
        # we can add ``BenchCommandRunner.set_pending_command``.
        self._runner._input.setText(command)  # noqa: SLF001
        self._runner._input.setFocus()  # noqa: SLF001


__all__ = ["SiteTab"]
