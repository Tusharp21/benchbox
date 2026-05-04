"""Collapsible sticky panel for the bench-start log.

Sits at the bottom of the bench detail view so server status is always
one glance away — even when the user is deep in a site tab. Subscribes
to :class:`BenchProcessManager`; never owns its own QProcess.

Default state: collapsed when the bench is stopped, expanded when it's
running. The user can toggle either way; the choice persists for the
lifetime of the dock instance (a fresh detail view starts at default).
"""

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

# status-dot palette — same colours used by BenchProcessPanel so the dock
# and any other indicator stay visually consistent.
_STATUS_COLOURS: dict[str, str] = {
    "running": "#1a7f37",
    "starting": "#d29922",
    "stopping…": "#d29922",
    "stopped": "#6e7781",
}

# When the log gets very chatty we cap the visible scrollback so the dock
# doesn't balloon into hundreds of MB over a long-running session. Same
# upper bound as :class:`BenchProcessPanel`.
_MAX_LOG_BLOCKS: int = 5000


class _StatusDot(QFrame):
    """Tiny coloured pill that mirrors the bench-process status."""

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
    """Sticky bottom dock — Start/Stop + status + collapsible bench-start log.

    Signals:
        start_requested(): user clicked Start; the page should call
            ``BenchProcessManager.start`` for the current bench.
        stop_requested(): same, for Stop.
    """

    start_requested = Signal()
    stop_requested = Signal()

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

        # ---- header bar (always visible) ----------------------------
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
        header.addWidget(self._toggle_btn)

        # ---- log panel (collapsible) --------------------------------
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

        # Subscribe to the manager once. We filter by current bench in
        # each slot so other benches' output doesn't leak into the panel.
        manager.output_appended.connect(self._on_output_appended)
        manager.status_changed.connect(self._on_status_changed)
        manager.process_started.connect(self._on_process_started)
        manager.process_stopped.connect(self._on_process_stopped)

    # --- public API ---------------------------------------------------

    def set_bench(self, path: Path, *, webserver_port: int = 8000) -> None:
        """Switch which bench this dock reflects. Does NOT kill anything."""
        self._bench_path = path.resolve()
        self._url = f"http://localhost:{webserver_port}"
        self._url_link.setText(
            f'<a href="{self._url}" style="color:#8250df;text-decoration:none;">↗ {self._url}</a>'
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

        # Auto-expand when running, collapse when stopped — but only if
        # the user hasn't manually overridden, otherwise we'd keep
        # snapping their preference back on every status change.
        if not self._user_overrode_collapse:
            self._set_expanded(running)

    def expanded(self) -> bool:
        return self._expanded

    # --- toggle -------------------------------------------------------

    def _on_toggle_clicked(self) -> None:
        self._user_overrode_collapse = True
        self._set_expanded(not self._expanded)

    def _set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self._log.setVisible(expanded)
        self._toggle_btn.setText("Hide logs" if expanded else "Show logs")

    # --- manager handlers --------------------------------------------

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
        if not self._user_overrode_collapse:
            self._set_expanded(True)

    def _on_process_stopped(self, path: Path, _exit_code: int) -> None:
        if not self._matches_current(path):
            return
        self._url_link.setVisible(False)
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._apply_status("stopped")

    def _apply_status(self, status: str) -> None:
        self._dot.set_status(status)
        self._status.setText(status)


__all__ = ["BenchProcessDock"]
