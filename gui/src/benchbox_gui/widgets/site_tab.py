"""Per-site tab inside the bench detail view.

Each tab carries the site's own start/stop controls, URL link, drop
button, and a live log panel. The log mirrors the bench-level
``bench start`` process — Frappe runs one dev server per bench that
serves every site, so the same output stream appears on each site tab.
"""

from __future__ import annotations

from pathlib import Path

from benchbox_core import introspect
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.services.bench_processes import BenchProcessManager

_STATUS_COLOURS: dict[str, str] = {
    "running": "#1a7f37",
    "starting": "#d29922",
    "stopping…": "#d29922",
    "stopped": "#6e7781",
}

_MAX_LOG_BLOCKS: int = 5000


class _StatusDot(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self.set_status("stopped")

    def set_status(self, status: str) -> None:
        colour = _STATUS_COLOURS.get(status, "#6e7781")
        self.setStyleSheet(
            f"background-color: {colour}; border-radius: 6px; border: none;"
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
    """Per-site view: info + start/stop + URL + drop + live log."""

    start_requested = Signal()
    stop_requested = Signal()
    open_browser_requested = Signal(str)  # full http URL
    drop_site_requested = Signal(str)  # site name

    def __init__(
        self,
        bench_path: Path,
        site: introspect.SiteInfo,
        process_manager: BenchProcessManager,
        *,
        webserver_port: int = 8000,
        bench_apps: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bench_path = bench_path.resolve()
        self._site = site
        self._url = f"http://{site.name}:{webserver_port}"
        self._bench_apps: list[str] = list(bench_apps or [])
        self._manager = process_manager

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(_section_header("Site info"))
        layout.addLayout(self._build_info_table())
        layout.addSpacing(6)

        layout.addWidget(_section_header("Server"))
        layout.addLayout(self._build_server_row())
        layout.addSpacing(4)

        layout.addWidget(_section_header("Live log"))
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(_MAX_LOG_BLOCKS)
        mono = QFont("JetBrains Mono, Fira Code, Courier New", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._log.setFont(mono)
        self._log.setPlaceholderText(
            f"Click Start bench to launch the dev server. "
            f"This view follows the shared {self._bench_path.name} log "
            f"(one process serves every site in the bench)."
        )
        self._log.setMinimumHeight(180)
        self._log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._log, 1)

        hint = QLabel(
            "The Free terminal tab is for ad-hoc <code>bench --site {site} ...</code> "
            "commands like migrate, backup, clear-cache, or maintenance toggles."
            .format(site=site.name)
        )
        hint.setProperty("role", "dim")
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(hint)

        # Wire to manager.
        self._manager.output_appended.connect(self._on_output_appended)
        self._manager.status_changed.connect(self._on_status_changed)
        self._manager.process_started.connect(self._on_process_started)
        self._manager.process_stopped.connect(self._on_process_stopped)

        # Initial sync — replay any log already buffered for this bench
        # so a tab opened mid-run isn't blank.
        existing = self._manager.log_of(self._bench_path)
        if existing:
            self._log.appendPlainText(existing)
        self._apply_status(self._manager.status_of(self._bench_path))
        self._refresh_running_ui(self._manager.is_running(self._bench_path))

    # --- public API --------------------------------------------------

    @property
    def site_name(self) -> str:
        return self._site.name

    @property
    def bench_path(self) -> Path:
        return self._bench_path

    @property
    def url(self) -> str:
        return self._url

    def shutdown(self) -> None:
        # Manager outlives the tab; disconnecting prevents stray callbacks
        # after the widget is torn down on bench reload.
        try:
            self._manager.output_appended.disconnect(self._on_output_appended)
            self._manager.status_changed.disconnect(self._on_status_changed)
            self._manager.process_started.disconnect(self._on_process_started)
            self._manager.process_stopped.disconnect(self._on_process_stopped)
        except (RuntimeError, TypeError):
            pass

    # --- info table --------------------------------------------------

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

    # --- server row --------------------------------------------------

    def _build_server_row(self) -> QHBoxLayout:
        self._dot = _StatusDot()
        self._status_label = QLabel("stopped")
        self._status_label.setProperty("role", "dim")

        self._url_link = QLabel(
            f'<a href="{self._url}" style="color:#8250df;text-decoration:none;">{self._url}</a>'
        )
        self._url_link.setOpenExternalLinks(False)
        self._url_link.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self._url_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self._url_link.setVisible(False)
        self._url_link.linkActivated.connect(
            lambda *_args: self.open_browser_requested.emit(self._url)
        )

        self._start_btn = QPushButton("Start bench")
        self._start_btn.setProperty("role", "primary")
        self._start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_btn.clicked.connect(self.start_requested.emit)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        self._stop_btn.setEnabled(False)

        self._open_browser_btn = QPushButton("Open in browser")
        self._open_browser_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_browser_btn.clicked.connect(
            lambda: self.open_browser_requested.emit(self._url)
        )
        self._open_browser_btn.setVisible(False)

        self._drop_site_btn = QPushButton("Drop site")
        self._drop_site_btn.setProperty("role", "danger")
        self._drop_site_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._drop_site_btn.clicked.connect(
            lambda: self.drop_site_requested.emit(self._site.name)
        )

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self._dot)
        row.addWidget(self._status_label)
        row.addSpacing(6)
        row.addWidget(self._url_link)
        row.addStretch(1)
        row.addWidget(self._start_btn)
        row.addWidget(self._stop_btn)
        row.addSpacing(6)
        row.addWidget(self._open_browser_btn)
        row.addWidget(self._drop_site_btn)
        return row

    # --- manager event handlers --------------------------------------

    def _matches_bench(self, path: Path) -> bool:
        return path == self._bench_path

    def _on_output_appended(self, path: Path, chunk: str) -> None:
        if not self._matches_bench(path):
            return
        self._log.appendPlainText(chunk)

    def _on_status_changed(self, path: Path, status: str) -> None:
        if not self._matches_bench(path):
            return
        self._apply_status(status)

    def _on_process_started(self, path: Path) -> None:
        if not self._matches_bench(path):
            return
        self._log.clear()
        self._refresh_running_ui(True)

    def _on_process_stopped(self, path: Path, _exit_code: int) -> None:
        if not self._matches_bench(path):
            return
        self._refresh_running_ui(False)
        self._apply_status("stopped")

    def _apply_status(self, status: str) -> None:
        self._dot.set_status(status)
        self._status_label.setText(status)

    def _refresh_running_ui(self, running: bool) -> None:
        self._url_link.setVisible(running)
        self._open_browser_btn.setVisible(running)
        self._start_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)


__all__ = ["SiteTab"]
