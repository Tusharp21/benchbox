"""Action strip + bench-process log panel under the bench detail view.

``BenchActionRow`` — Start / Stop / Open folder / + New site / + Get app.
Emits signals rather than doing I/O itself, so BenchDetailView sequences
the dialogs and workers.

``BenchProcessPanel`` — live view over a single bench's log stream. Does
NOT own the ``QProcess``; it subscribes to
:class:`BenchProcessManager` so switching benches (or going back to the
list) doesn't kill anything. Multiple benches can run concurrently; each
detail view just displays whichever bench the user is looking at.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.services.bench_processes import BenchProcessManager

# status-dot palette — keyed by the strings the manager emits via
# ``status_changed``. anything not listed falls back to a neutral grey.
_STATUS_COLOURS: dict[str, str] = {
    "running": "#1a7f37",
    "starting": "#d29922",
    "stopping…": "#d29922",
    "stopped": "#6e7781",
}


class _StatusDot(QFrame):
    """Tiny coloured circle that visualises a bench process's state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self.set_status("stopped")

    def set_status(self, status: str) -> None:
        colour = _STATUS_COLOURS.get(status, "#6e7781")
        # Inline stylesheet so the dot ignores theme rules — it's the same
        # colour in dark and light, on purpose.
        self.setStyleSheet(
            f"background-color: {colour}; border-radius: 6px; border: none;"
        )


class BenchActionRow(QWidget):
    """Row of action buttons for a single bench."""

    start_requested = Signal()
    stop_requested = Signal()
    open_folder_requested = Signal()
    new_site_requested = Signal()
    get_app_requested = Signal()
    new_app_requested = Signal()
    restore_site_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._start = QPushButton("▶ Start bench")
        self._start.setProperty("role", "primary")
        self._start.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start.clicked.connect(self.start_requested.emit)

        self._stop = QPushButton("■ Stop")
        self._stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop.clicked.connect(self.stop_requested.emit)
        self._stop.setEnabled(False)

        open_folder = QPushButton("Open folder")
        open_folder.setProperty("role", "ghost")
        open_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        open_folder.clicked.connect(self.open_folder_requested.emit)

        new_site = QPushButton("+ New site")
        new_site.setCursor(Qt.CursorShape.PointingHandCursor)
        new_site.clicked.connect(self.new_site_requested.emit)

        get_app = QPushButton("+ Get app")
        get_app.setCursor(Qt.CursorShape.PointingHandCursor)
        get_app.clicked.connect(self.get_app_requested.emit)

        new_app = QPushButton("+ New app")
        new_app.setCursor(Qt.CursorShape.PointingHandCursor)
        new_app.clicked.connect(self.new_app_requested.emit)

        restore = QPushButton("⟲ Restore site")
        restore.setCursor(Qt.CursorShape.PointingHandCursor)
        restore.clicked.connect(self.restore_site_requested.emit)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._start)
        layout.addWidget(self._stop)
        layout.addSpacing(16)
        layout.addWidget(open_folder)
        layout.addWidget(new_site)
        layout.addWidget(get_app)
        layout.addWidget(new_app)
        layout.addWidget(restore)
        layout.addStretch(1)

    def set_running(self, running: bool) -> None:
        """Toggle which of Start/Stop is the primary action."""
        self._start.setEnabled(not running)
        self._stop.setEnabled(running)


class BenchProcessPanel(QWidget):
    """Live view over a bench's ``bench start`` stream.

    Re-subscribes on :meth:`set_bench`; no process lifecycle is owned
    here. Ask the manager to start/stop; manager tells us when output
    arrives, status changes, or the process exits.
    """

    # Kept for API compatibility so the detail view can still flip its
    # action buttons off the panel's signals.
    started = Signal()
    stopped = Signal()

    def __init__(
        self,
        manager: BenchProcessManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._bench_path: Path | None = None
        self._url: str = ""

        self._dot = _StatusDot()
        self._status = QLabel("stopped")
        self._status.setProperty("role", "dim")

        # Live URL — shown only while the bench is running. Clickable.
        self._url_link = QLabel()
        self._url_link.setOpenExternalLinks(True)
        self._url_link.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self._url_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self._url_link.setVisible(False)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(5000)
        mono = QFont("JetBrains Mono, Fira Code, Courier New", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._log.setFont(mono)
        self._log.setPlaceholderText("Bench output will appear here when you click Start bench.")

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(8)
        status_row.addWidget(self._dot)
        status_row.addWidget(self._status)
        status_row.addStretch(1)
        status_row.addWidget(self._url_link)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(status_row)
        layout.addWidget(self._log, 1)

        # Subscribe once to the manager. We filter in each slot by the
        # currently-displayed bench; signals for other benches are ignored.
        manager.output_appended.connect(self._on_output_appended)
        manager.status_changed.connect(self._on_status_changed)
        manager.process_started.connect(self._on_process_started)
        manager.process_stopped.connect(self._on_process_stopped)

    # ---- public API --------------------------------------------------

    def set_bench(self, path: Path, *, webserver_port: int = 8000) -> None:
        """Switch which bench this panel reflects. Does NOT kill anything.

        ``webserver_port`` populates the clickable URL shown when the
        bench is running; pass ``info.webserver_port`` from the caller.
        """
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
        self._status.setText(current_status)
        self._dot.set_status(current_status)

        running = self._manager.is_running(self._bench_path)
        self._url_link.setVisible(running)
        # Sync the external "running?" signal so the action row updates.
        if running:
            self.started.emit()
        else:
            self.stopped.emit()

    def is_running(self) -> bool:
        if self._bench_path is None:
            return False
        return self._manager.is_running(self._bench_path)

    def start(self) -> None:
        if self._bench_path is None:
            return
        self._manager.start(self._bench_path)

    def stop(self) -> None:
        if self._bench_path is None:
            return
        self._manager.stop(self._bench_path)

    # ---- manager signal handlers ------------------------------------

    def _matches_current(self, path: Path) -> bool:
        return self._bench_path is not None and path == self._bench_path

    def _on_output_appended(self, path: Path, chunk: str) -> None:
        if not self._matches_current(path):
            return
        self._log.appendPlainText(chunk)

    def _on_status_changed(self, path: Path, status: str) -> None:
        if not self._matches_current(path):
            return
        self._status.setText(status)
        self._dot.set_status(status)

    def _on_process_started(self, path: Path) -> None:
        if not self._matches_current(path):
            return
        # Clear whatever stale log we had showing from the previous owner.
        self._log.clear()
        self._url_link.setVisible(True)
        self.started.emit()

    def _on_process_stopped(self, path: Path, _exit_code: int) -> None:
        if not self._matches_current(path):
            return
        self._url_link.setVisible(False)
        self._dot.set_status("stopped")
        self._status.setText("stopped")
        self.stopped.emit()


def open_in_file_manager(path: Path) -> bool:
    """Open ``path`` in the system file manager via xdg-open / QDesktopServices."""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
