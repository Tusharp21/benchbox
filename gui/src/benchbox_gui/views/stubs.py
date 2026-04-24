"""Placeholder views for sidebar entries we haven't built out yet.

Keeping them here (vs. separate files each) because they're all the same
'here's the info + a hint to use the CLI' pattern and there's no value in
one-file-per-stub until they grow real logic.
"""

from __future__ import annotations

from benchbox_core import credentials, logs
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class SitesStub(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "<h2>Sites</h2>"
                "<p>Per-site management lands in a later release. For now, use the CLI:</p>"
                "<pre>benchbox site new &lt;bench&gt; &lt;site&gt;\n"
                "benchbox site drop &lt;bench&gt; &lt;site&gt;</pre>"
                "<p>Existing sites are listed under each bench's detail view.</p>"
            )
        )
        layout.addStretch(1)


class AppsStub(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "<h2>Apps</h2>"
                "<p>App management lands in a later release. For now, use the CLI:</p>"
                "<pre>benchbox app get &lt;bench&gt; &lt;git-url&gt;\n"
                "benchbox app install &lt;bench&gt; &lt;site&gt; &lt;app&gt;\n"
                "benchbox app uninstall &lt;bench&gt; &lt;site&gt; &lt;app&gt;</pre>"
                "<p>Apps installed per-bench are listed under each bench's detail view.</p>"
            )
        )
        layout.addStretch(1)


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
