"""Action strip + process panel under the bench detail view.

``BenchActionRow`` — five buttons: Start, Stop, Open folder, New site,
Get app. Emits signals rather than doing I/O itself, so BenchDetailView
stays in charge of sequencing the dialogs and workers.

``BenchProcessPanel`` — wraps a ``QProcess`` running ``bench start`` with
its working directory set to ``bench_path``. Captures stdout+stderr into
a read-only log area. Kills the process cleanly on parent close.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class BenchActionRow(QWidget):
    """Row of action buttons for a single bench."""

    start_requested = Signal()
    stop_requested = Signal()
    open_folder_requested = Signal()
    new_site_requested = Signal()
    get_app_requested = Signal()

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

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._start)
        layout.addWidget(self._stop)
        layout.addSpacing(16)
        layout.addWidget(open_folder)
        layout.addWidget(new_site)
        layout.addWidget(get_app)
        layout.addStretch(1)

    def set_running(self, running: bool) -> None:
        """Toggle which of Start/Stop is the primary action."""
        self._start.setEnabled(not running)
        self._stop.setEnabled(running)


class BenchProcessPanel(QWidget):
    """``bench start`` wrapper: process + log viewer + status label.

    ``bench start`` runs indefinitely; we own the subprocess lifecycle here
    so the process dies when the widget is closed / swapped out.
    """

    started = Signal()
    stopped = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._bench_path: Path | None = None
        self._process: QProcess | None = None

        self._status = QLabel("stopped")
        self._status.setProperty("role", "dim")

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        mono = QFont("JetBrains Mono, Fira Code, Courier New", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._log.setFont(mono)
        self._log.setPlaceholderText("Bench output will appear here when you click Start bench.")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._status)
        layout.addWidget(self._log, 1)

    # ---- public API --------------------------------------------------

    def set_bench(self, path: Path) -> None:
        """Change the bench this panel controls. Stops any running process."""
        if self._process is not None:
            self.stop()
        self._bench_path = path
        self._log.clear()
        self._status.setText("stopped")

    def is_running(self) -> bool:
        return (
            self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning
        )

    def start(self) -> None:
        if self._bench_path is None or self.is_running():
            return
        self._log.clear()
        self._status.setText(f"starting in {self._bench_path}…")

        process = QProcess(self)
        process.setWorkingDirectory(str(self._bench_path))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._drain_output)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)
        self._process = process
        # Source nvm first so watch.1 picks up Node 18 (nvm-installed)
        # instead of the system Node 12 that ships with Ubuntu 22.04.
        # Without this, Frappe's frontend watcher exits immediately and
        # honcho kills every sibling process — the whole bench appears
        # to "start then stop instantly".
        script = (
            'if [ -s "$HOME/.nvm/nvm.sh" ]; then '
            'export NVM_DIR="$HOME/.nvm"; '
            '. "$NVM_DIR/nvm.sh"; '
            "fi; "
            "exec bench start"
        )
        process.start("bash", ["-c", script])
        self.started.emit()

    def stop(self) -> None:
        if self._process is None:
            return
        self._status.setText("stopping…")
        self._process.terminate()
        if not self._process.waitForFinished(3000):
            self._process.kill()
            self._process.waitForFinished(1000)

    # ---- QProcess signal handlers -----------------------------------

    def _drain_output(self) -> None:
        if self._process is None:
            return
        # QByteArray → bytes via .data(); wrapped in bytes() to satisfy stubs
        # that declare the union as bytes|bytearray|memoryview.
        raw = bytes(self._process.readAllStandardOutput().data())
        chunk = raw.decode(errors="replace")
        if chunk:
            self._log.appendPlainText(chunk.rstrip("\n"))
            self._status.setText("running")

    def _on_finished(self, exit_code: int, status: QProcess.ExitStatus) -> None:
        del status  # unused
        self._status.setText(f"stopped (exit {exit_code})")
        self._process = None
        self.stopped.emit()

    def _on_error(self, _err: QProcess.ProcessError) -> None:
        if self._process is None:
            return
        self._status.setText("error — bench binary not found on PATH?")
        self._process = None
        self.stopped.emit()

    # ---- teardown ---------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 — Qt override
        if self.is_running():
            self.stop()
        super().closeEvent(event)


def open_in_file_manager(path: Path) -> bool:
    """Open ``path`` in the system file manager via xdg-open / QDesktopServices."""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
