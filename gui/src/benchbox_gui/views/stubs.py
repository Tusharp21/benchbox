"""Remaining placeholder views (Logs + Settings).

Sites and Apps used to stub to CLI text here; they're now fully functional
widgets in ``views/sites.py`` and ``views/apps.py``. Logs + Settings are
still minimal — a later release will expand them.
"""

from __future__ import annotations

from benchbox_core import credentials, logs
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class LogsView(QWidget):
    """Shows the current session log dir; minimal, no tail yet."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        session = logs.current_session_dir() or logs.init_session()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Logs</h2>"))
        layout.addWidget(
            QLabel(
                "<p>benchbox writes a full session log every invocation. Open this "
                "directory when filing a bug report.</p>"
            )
        )
        path_label = QLabel(f"<code>{session}</code>")
        path_label.setWordWrap(True)
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(path_label)
        layout.addStretch(1)


class SettingsView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Settings</h2>"))
        cred_path = credentials.credentials_path()
        exists = cred_path.is_file()
        layout.addWidget(
            QLabel(
                f"<p><b>Credentials file:</b> <code>{cred_path}</code> "
                f"({'present' if exists else 'not yet created'})</p>"
                "<p>Stored values: MariaDB root password (set on first install).</p>"
            )
        )
        layout.addStretch(1)
