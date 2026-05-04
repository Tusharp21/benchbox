"""Sticky bottom dock with bench start/stop and per-site action buttons."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
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


class BenchProcessDock(QWidget):
    start_requested = Signal()
    stop_requested = Signal()
    open_browser_requested = Signal(str)
    drop_site_requested = Signal(str)

    def __init__(
        self,
        manager: BenchProcessManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("BenchProcessDock")
        self._manager = manager
        self._bench_path: Path | None = None
        self._url: str = ""
        self._user_overrode_collapse: bool = False
        self._expanded: bool = False
        self._current_site: str | None = None
        self._current_site_url: str = ""

        self._dot = _StatusDot()
        self._status = QLabel("stopped")
        self._status.setProperty("role", "dim")

        self._url_link = QLabel()
        self._url_link.setOpenExternalLinks(True)
        self._url_link.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self._url_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self._url_link.setVisible(False)

        self._start_btn = QPushButton("Start bench")
        self._start_btn.setProperty("role", "primary")
        self._start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_btn.clicked.connect(self.start_requested.emit)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        self._stop_btn.setEnabled(False)

        self._toggle_btn = QPushButton("Show logs")
        self._toggle_btn.setProperty("role", "ghost")
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._on_toggle_clicked)

        self._open_browser_btn = QPushButton("Open in browser")
        self._open_browser_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_browser_btn.clicked.connect(self._on_open_browser_clicked)
        self._open_browser_btn.setVisible(False)

        self._drop_site_btn = QPushButton("Drop site")
        self._drop_site_btn.setProperty("role", "danger")
        self._drop_site_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._drop_site_btn.clicked.connect(self._on_drop_site_clicked)
        self._drop_site_btn.setVisible(False)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(self._dot)
        header.addWidget(self._status)
        header.addSpacing(6)
        header.addWidget(self._url_link)
        header.addStretch(1)
        header.addWidget(self._start_btn)
        header.addWidget(self._stop_btn)
        header.addSpacing(6)
        header.addWidget(self._open_browser_btn)
        header.addWidget(self._drop_site_btn)
        header.addSpacing(6)
        header.addWidget(self._toggle_btn)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(_MAX_LOG_BLOCKS)
        mono = QFont("JetBrains Mono, Fira Code, Courier New", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._log.setFont(mono)
        self._log.setPlaceholderText("Bench output appears here when you click Start bench.")
        self._log.setMinimumHeight(180)
        self._log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._log.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self._log)

        manager.output_appended.connect(self._on_output_appended)
        manager.status_changed.connect(self._on_status_changed)
        manager.process_started.connect(self._on_process_started)
        manager.process_stopped.connect(self._on_process_stopped)

    def set_bench(self, path: Path, *, webserver_port: int = 8000) -> None:
        self._bench_path = path.resolve()
        self._url = f"http://localhost:{webserver_port}"
        self._url_link.setText(
            f'<a href="{self._url}" style="color:#8250df;text-decoration:none;">{self._url}</a>'
        )

        self._log.clear()
        existing = self._manager.log_of(self._bench_path)
        if existing:
            self._log.appendPlainText(existing)

        current_status = self._manager.status_of(self._bench_path)
        self._apply_status(current_status)

        running = self._manager.is_running(self._bench_path)
        self._url_link.setVisible(running)
        self._start_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)

        if not self._user_overrode_collapse:
            self._set_expanded(running)

    def expanded(self) -> bool:
        return self._expanded

    def set_current_site(self, site_name: str | None, url: str | None = None) -> None:
        self._current_site = site_name
        self._current_site_url = url or ""
        self._refresh_site_button_visibility()

    def _on_toggle_clicked(self) -> None:
        self._user_overrode_collapse = True
        self._set_expanded(not self._expanded)

    def _on_open_browser_clicked(self) -> None:
        if self._current_site_url:
            self.open_browser_requested.emit(self._current_site_url)

    def _on_drop_site_clicked(self) -> None:
        if self._current_site is not None:
            self.drop_site_requested.emit(self._current_site)

    def _refresh_site_button_visibility(self) -> None:
        has_site = self._current_site is not None
        bench_running = (
            self._bench_path is not None and self._manager.is_running(self._bench_path)
        )
        self._drop_site_btn.setVisible(has_site)
        self._open_browser_btn.setVisible(has_site and bench_running)

    def _set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self._log.setVisible(expanded)
        self._toggle_btn.setText("Hide logs" if expanded else "Show logs")

    def _matches_current(self, path: Path) -> bool:
        return self._bench_path is not None and path == self._bench_path

    def _on_output_appended(self, path: Path, chunk: str) -> None:
        if not self._matches_current(path):
            return
        self._log.appendPlainText(chunk)

    def _on_status_changed(self, path: Path, status: str) -> None:
        if not self._matches_current(path):
            return
        self._apply_status(status)

    def _on_process_started(self, path: Path) -> None:
        if not self._matches_current(path):
            return
        self._log.clear()
        self._url_link.setVisible(True)
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._refresh_site_button_visibility()
        if not self._user_overrode_collapse:
            self._set_expanded(True)

    def _on_process_stopped(self, path: Path, _exit_code: int) -> None:
        if not self._matches_current(path):
            return
        self._url_link.setVisible(False)
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._refresh_site_button_visibility()
        self._apply_status("stopped")

    def _apply_status(self, status: str) -> None:
        self._dot.set_status(status)
        self._status.setText(status)


__all__ = ["BenchProcessDock"]
