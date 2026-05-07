"""Per-site tab inside the bench detail view — read-only site info."""

from __future__ import annotations

from pathlib import Path

from benchbox_core import introspect
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


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
    """Read-only site info card.

    Per-site command running and maintenance buttons used to live here;
    they were removed in favor of the bench-level Free terminal tab,
    which can drive any ``bench --site <name> ...`` command directly.
    """

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

        hint = QLabel(
            "Use the <b>Free terminal</b> tab to run "
            "<code>bench --site {site} ...</code> commands like migrate, "
            "backup, clear-cache, or maintenance toggles.".format(site=site.name)
        )
        hint.setProperty("role", "dim")
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.TextFormat.RichText)
        layout.addSpacing(8)
        layout.addWidget(hint)
        layout.addStretch(1)

    @property
    def site_name(self) -> str:
        return self._site.name

    @property
    def bench_path(self) -> Path:
        return self._bench_path

    @property
    def url(self) -> str:
        return self._url

    def shutdown(self) -> None:  # kept for API parity with the previous tab
        pass

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


__all__ = ["SiteTab"]
