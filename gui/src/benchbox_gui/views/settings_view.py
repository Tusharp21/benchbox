"""Settings tab — manage local credentials + show version info."""

from __future__ import annotations

from benchbox_core import credentials
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui import __version__
from benchbox_gui.widgets.card import Card
from benchbox_gui.widgets.dialogs import confirm


class SettingsView(QWidget):
    """Change MariaDB password, reset credentials, show version + paths."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        title = QLabel("Settings")
        title.setProperty("role", "h1")
        subtitle = QLabel("Local credentials and environment info")
        subtitle.setProperty("role", "dim")

        # ---- credentials card ----
        self._cred_status = QLabel()
        self._cred_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        change_pw = QPushButton("Change MariaDB root password")
        change_pw.clicked.connect(self._on_change_password)

        reset = QPushButton("Reset all saved credentials")
        reset.clicked.connect(self._on_reset_credentials)

        cred_actions = QHBoxLayout()
        cred_actions.setSpacing(8)
        cred_actions.addWidget(change_pw)
        cred_actions.addWidget(reset)
        cred_actions.addStretch(1)

        cred_card = Card()
        cred_heading = QLabel("Credentials")
        cred_heading.setProperty("role", "h2")
        cred_card.addWidget(cred_heading)
        cred_card.addWidget(self._cred_status)
        cred_card.addLayout(cred_actions)

        # ---- about card ----
        about_card = Card()
        about_heading = QLabel("About")
        about_heading.setProperty("role", "h2")
        about_card.addWidget(about_heading)
        about_card.addWidget(QLabel(f"<code>benchbox-gui {__version__}</code>"))
        about_card.addWidget(
            QLabel(
                "<span style='color:#a9a9c4;'>Source: "
                "<a href='https://github.com/Tusharp21/benchbox'>"
                "github.com/Tusharp21/benchbox</a></span>"
            )
        )

        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(16)
        root.addLayout(header_text)
        root.addWidget(cred_card)
        root.addWidget(about_card)
        root.addStretch(1)

        self._refresh_cred_status()

    # --- helpers ------------------------------------------------------

    def _refresh_cred_status(self) -> None:
        path = credentials.credentials_path()
        present = path.is_file()
        pw_set = credentials.get_mariadb_root_password() is not None
        self._cred_status.setText(
            f"<code>{path}</code><br>"
            f"<span style='color:#a9a9c4;'>file: "
            f"{'present' if present else 'not yet created'} · MariaDB root "
            f"password: {'saved' if pw_set else 'not set'}</span>"
        )

    # --- actions ------------------------------------------------------

    def _on_change_password(self) -> None:
        new_pw, ok = QInputDialog.getText(
            self,
            "Change MariaDB root password",
            "Enter the new password. benchbox stores it at "
            "<code>~/.benchbox/credentials.json</code> with 0600 perms.",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not new_pw:
            return
        confirm_pw, ok2 = QInputDialog.getText(
            self,
            "Confirm password",
            "Type it again:",
            QLineEdit.EchoMode.Password,
        )
        if not ok2 or confirm_pw != new_pw:
            QMessageBox.warning(self, "Mismatch", "Passwords did not match.")
            return

        credentials.set_mariadb_root_password(new_pw)
        self._refresh_cred_status()
        QMessageBox.information(self, "Saved", "MariaDB root password updated.")

    def _on_reset_credentials(self) -> None:
        if not confirm(
            self,
            "Reset credentials",
            "Delete your stored MariaDB root password and any other saved "
            "secrets? You'll be re-prompted the next time benchbox needs them.",
            destructive=True,
        ):
            return
        path = credentials.credentials_path()
        if path.is_file():
            path.unlink()
        self._refresh_cred_status()
        QMessageBox.information(self, "Done", "Credentials cleared.")
