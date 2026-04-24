"""Logs tab — live tail of the current benchbox session log.

Polls ``~/.benchbox/logs/<session>/session.log`` on a QTimer, appends any
new bytes to a scrolling read-only panel, and offers Open Folder + Clear
actions. Follow mode keeps the view pinned to the bottom so long-running
installer runs read cleanly.

Not part of the core loop — this is a 1-second filesystem tail, good
enough for developer-facing visibility without going full QFileSystemWatcher.
"""

from __future__ import annotations

from pathlib import Path

from benchbox_core import logs
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

DEFAULT_TAIL_MS: int = 1000


class LogsView(QWidget):
    """Live tail of the current session log."""

    def __init__(self, parent: QWidget | None = None, *, tail_ms: int = DEFAULT_TAIL_MS) -> None:
        super().__init__(parent)
        self._log_path: Path | None = None
        self._offset: int = 0

        title = QLabel("Logs")
        title.setProperty("role", "h1")
        subtitle = QLabel("Live tail of the current benchbox session log")
        subtitle.setProperty("role", "dim")

        self._session_path = QLabel()
        self._session_path.setProperty("role", "dim")
        self._session_path.setWordWrap(True)
        self._session_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        open_folder = QPushButton("Open folder")
        open_folder.setProperty("role", "ghost")
        open_folder.clicked.connect(self._open_folder)

        clear = QPushButton("Clear view")
        clear.setProperty("role", "ghost")
        clear.clicked.connect(self._clear_view)

        self._follow = QCheckBox("Follow (auto-scroll)")
        self._follow.setChecked(True)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(self._follow)
        toolbar.addStretch(1)
        toolbar.addWidget(clear)
        toolbar.addWidget(open_folder)

        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        self._view.setMaximumBlockCount(5000)  # hard cap so long sessions don't eat RAM
        mono = QFont("JetBrains Mono, Fira Code, Courier New", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._view.setFont(mono)
        self._view.setPlaceholderText(
            "No log output yet. benchbox writes to its session log as soon as "
            "it does anything — run a command from another sidebar tab to see "
            "lines appear here."
        )

        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)
        root.addLayout(header_text)
        root.addWidget(self._session_path)
        root.addLayout(toolbar)
        root.addWidget(self._view, 1)

        self._resolve_log_path()

        self._timer = QTimer(self)
        self._timer.setInterval(tail_ms)
        self._timer.timeout.connect(self._poll_tail)
        self._timer.start()
        self._poll_tail()  # initial read so there's something on first show

    # --- helpers ------------------------------------------------------

    def _resolve_log_path(self) -> None:
        session = logs.current_session_dir()
        if session is None:
            session = logs.init_session()
        self._log_path = session / "session.log"
        self._session_path.setText(f"<code>{self._log_path}</code>")
        self._offset = 0
        self._view.clear()

    def _poll_tail(self) -> None:
        path = self._log_path
        if path is None or not path.is_file():
            return
        try:
            size = path.stat().st_size
        except OSError:
            return
        if size < self._offset:
            # Log was rotated / truncated; rewind.
            self._offset = 0
            self._view.clear()
        if size == self._offset:
            return
        try:
            with path.open("rb") as fh:
                fh.seek(self._offset)
                chunk = fh.read(size - self._offset)
        except OSError:
            return
        self._offset = size

        text = chunk.decode("utf-8", errors="replace").rstrip("\n")
        if not text:
            return
        self._view.appendPlainText(text)
        if self._follow.isChecked():
            scrollbar = self._view.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    # --- actions ------------------------------------------------------

    def _open_folder(self) -> None:
        if self._log_path is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._log_path.parent)))

    def _clear_view(self) -> None:
        # Clear the on-screen view only; we don't truncate the file (callers
        # might be grepping it) — the next tick picks up from the current offset.
        self._view.clear()
