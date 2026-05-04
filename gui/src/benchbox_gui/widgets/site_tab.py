"""Per-site tab inside the bench detail view."""

from __future__ import annotations

import shlex
from pathlib import Path

from benchbox_core import introspect
from PySide6.QtCore import Qt
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


def _section_header(title: str) -> QWidget:
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 4, 0, 2)
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
        self._bench_apps: list[str] = list(bench_apps or [])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(_section_header("Site info"))
        layout.addLayout(self._build_info_table())
        layout.addSpacing(6)

        layout.addWidget(_section_header("Maintenance"))
        layout.addLayout(self._build_maintenance_grid())
        layout.addSpacing(6)

        layout.addWidget(_section_header("Run any command"))
        self._runner = BenchCommandRunner(locked_site=site.name, show_chips=False)
        self._runner.set_bench(bench_path, [site.name])
        self._runner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._runner, 1)

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
        return self._runner

    def shutdown(self) -> None:
        self._runner.shutdown()

    def run_drop_site(self, *, root_password: str) -> bool:
        site = self._site.name
        real_cmd = (
            f"bench drop-site {shlex.quote(site)} "
            f"--root-password {shlex.quote(root_password)} --no-backup"
        )
        display_cmd = f"bench drop-site {site} --root-password ******** --no-backup"
        return self._runner.run_command(real_cmd, display=display_cmd)

    def _build_info_table(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

        scheduler_text = (
            '<span style="color:#cf222e;font-weight:600;">paused</span>'
            if self._site.scheduler_paused
            else '<span style="color:#1a7f37;font-weight:600;">running</span>'
        )
        maintenance_text = (
            '<span style="color:#cf222e;font-weight:600;">on</span>'
            if self._site.maintenance_mode
            else '<span style="color:#1a7f37;font-weight:600;">off</span>'
        )

        rows: list[tuple[str, str, bool]] = [
            ("db", self._site.db_name or "—", False),
            ("apps", self._format_apps_value(), True),
            ("scheduler", scheduler_text, True),
            ("maintenance", maintenance_text, True),
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

        site = self._site.name

        migrate = self._mk_button("Migrate", role="primary")
        migrate.clicked.connect(lambda: self._runner.prefill(f"bench --site {site} migrate"))

        clear_cache = self._mk_button("Clear cache")
        clear_cache.clicked.connect(
            lambda: self._runner.prefill(f"bench --site {site} clear-cache")
        )

        clear_web = self._mk_button("Clear website cache")
        clear_web.clicked.connect(
            lambda: self._runner.prefill(f"bench --site {site} clear-website-cache")
        )

        backup = self._mk_button("Backup")
        backup.clicked.connect(lambda: self._runner.prefill(f"bench --site {site} backup"))

        if self._site.scheduler_paused:
            scheduler = self._mk_button("Resume scheduler", role="danger")
            scheduler.clicked.connect(
                lambda: self._runner.prefill(f"bench --site {site} enable-scheduler")
            )
        else:
            scheduler = self._mk_button("Pause scheduler")
            scheduler.clicked.connect(
                lambda: self._runner.prefill(f"bench --site {site} disable-scheduler")
            )

        if self._site.maintenance_mode:
            maintenance = self._mk_button("Exit maintenance mode", role="danger")
            maintenance.clicked.connect(
                lambda: self._runner.prefill(
                    f"bench --site {site} set-maintenance-mode off"
                )
            )
        else:
            maintenance = self._mk_button("Enter maintenance mode")
            maintenance.clicked.connect(
                lambda: self._runner.prefill(
                    f"bench --site {site} set-maintenance-mode on"
                )
            )

        buttons = [migrate, clear_cache, clear_web, backup, scheduler, maintenance]
        for index, button in enumerate(buttons):
            row, col = divmod(index, 3)
            grid.addWidget(button, row, col)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        return grid

    def _mk_button(self, label: str, *, role: str | None = None) -> QPushButton:
        btn = QPushButton(label)
        if role is not None:
            btn.setProperty("role", role)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(34)
        return btn


__all__ = ["SiteTab"]
