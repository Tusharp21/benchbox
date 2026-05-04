"""Logs tab — live tail of a benchbox session log."""

from __future__ import annotations

import os
from pathlib import Path

from benchbox_core import logs
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

DEFAULT_TAIL_MS: int = 1000


def _log_root() -> Path:
    override = os.environ.get(logs.ENV_LOG_DIR)
    return Path(override) if override else logs.DEFAULT_LOG_ROOT


def _discover_sessions() -> list[Path]:
    root = _log_root()
    if not root.is_dir():
        return []
    sessions = [p for p in root.iterdir() if p.is_dir() and (p / "session.log").is_file()]
    sessions.sort(key=lambda p: p.name, reverse=True)
    return sessions


class LogsView(QWidget):
    def __init__(self, parent: QWidget | None = None, *, tail_ms: int = DEFAULT_TAIL_MS) -> None:
        super().__init__(parent)
        self._log_path: Path | None = None
        self._offset: int = 0

        title = QLabel("Logs")
        title.setProperty("role", "h1")
        subtitle = QLabel("Live tail of the current benchbox session log")
        subtitle.setProperty("role", "dim")

        # Session picker — current session on top, then older ones. Useful
        # because the current session.log is empty until something logs.
        session_label = QLabel("Session:")
        session_label.setProperty("role", "dim")

        self._session_picker = QComboBox()
        self._session_picker.setMinimumWidth(320)
        self._session_picker.currentIndexChanged.connect(self._on_session_changed)

        refresh_sessions = QPushButton("↻")
        refresh_sessions.setProperty("role", "ghost")
        refresh_sessions.setToolTip("Rescan log directory for new sessions")
        refresh_sessions.setFixedWidth(36)
        refresh_sessions.clicked.connect(self._reload_sessions)

        session_row = QHBoxLayout()
        session_row.setSpacing(8)
        session_row.addWidget(session_label)
        session_row.addWidget(self._session_picker, 1)
        session_row.addWidget(refresh_sessions)

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
        mono = QFont("JetBrains Mono, Fira Code, Courier New", 10)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._view.setFont(mono)
        self._view.setPlaceholderText(
            "This session has not logged anything yet.\n"
            "benchbox writes a line every time it runs a command — try "
            "creating a bench, getting an app, or creating a site from the "
            "sidebar, then come back here.\n"
            "Older sessions that DO have content are reachable from the "
            "Session dropdown above."
        )

        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)
        root.addLayout(header_text)
        root.addLayout(session_row)
        root.addWidget(self._session_path)
        root.addLayout(toolbar)
        root.addWidget(self._view, 1)

        # Populate the session picker — this also sets the log path via
        # the _on_session_changed slot.
        self._reload_sessions()

        self._timer = QTimer(self)
        self._timer.setInterval(tail_ms)
        self._timer.timeout.connect(self._poll_tail)
        self._timer.start()
        self._poll_tail()  # initial read so there's something on first show

    # --- helpers ------------------------------------------------------

    def _reload_sessions(self) -> None:
        current = logs.current_session_dir()
        if current is None:
            current = logs.init_session()

        sessions = _discover_sessions()
        # Pin the current session at the top of the picker.
        if current in sessions:
            sessions.remove(current)
        sessions.insert(0, current)

        # Block signals so repopulation doesn't fire a cascade of changes.
        self._session_picker.blockSignals(True)
        self._session_picker.clear()
        for idx, path in enumerate(sessions):
            label = f"{path.name} (current)" if idx == 0 else path.name
            self._session_picker.addItem(label, userData=path)
        self._session_picker.setCurrentIndex(0)
        self._session_picker.blockSignals(False)
        self._switch_to_session(sessions[0])

    def _on_session_changed(self, _row: int) -> None:
        path = self._session_picker.currentData()
        if isinstance(path, Path):
            self._switch_to_session(path)

    def _switch_to_session(self, session_dir: Path) -> None:
        self._log_path = session_dir / "session.log"
        self._session_path.setText(f"<code>{self._log_path}</code>")
        self._offset = 0
        self._view.clear()
        self._poll_tail()

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
