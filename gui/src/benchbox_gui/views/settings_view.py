"""Settings tab — credentials, paths, about.

Three cards, consistent spacing:
  - Credentials: status chip + selectable path + change-password + reset
  - Paths: credentials file, logs dir, venv install — each with Open folder
  - About: version info for all three packages + repo link

No long-running state; everything here is pure filesystem + credentials
store access, so no worker threads needed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from benchbox_core import __version__ as core_version
from benchbox_core import credentials, logs
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
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

from benchbox_gui import __version__ as gui_version
from benchbox_gui.widgets.card import Card
from benchbox_gui.widgets.dialogs import confirm

_GREEN = "#50fa7b"
_RED = "#ff5555"


def _chip(text: str, color: str) -> QLabel:
    """A small coloured status pill. Pure-label, no interaction."""
    label = QLabel(text)
    label.setStyleSheet(
        f"background-color: {color}; color: #282a36; "
        f"border-radius: 8px; padding: 2px 10px; font-weight: 600; font-size: 9pt;"
    )
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def _path_row(label: str, path: Path, *, exists: bool | None = None) -> QWidget:
    """A row: label + selectable path + Open folder button.

    ``exists`` is shown as a trailing dim hint when supplied.
    """
    row_widget = QWidget()
    row = QHBoxLayout(row_widget)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)

    title = QLabel(label)
    title.setProperty("role", "dim")
    title.setMinimumWidth(110)

    path_label = QLabel(f"<code>{path}</code>")
    path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    path_label.setWordWrap(True)
    if exists is False:
        path_label.setText(f"<code>{path}</code> <span style='color:#a9a9c4;'>(missing)</span>")

    open_btn = QPushButton("Open")
    open_btn.setProperty("role", "ghost")
    open_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def _open_it() -> None:
        # Directory targets open in file manager; files open their containing
        # dir because xdg-open on a .json just launches a text editor.
        target = path if path.is_dir() else path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    open_btn.clicked.connect(_open_it)

    row.addWidget(title)
    row.addWidget(path_label, 1)
    row.addWidget(open_btn)
    return row_widget


def _venv_prefix() -> Path:
    """The venv benchbox is running out of, via ``sys.prefix``.

    Always points at ``~/.local/share/benchbox/venv`` for a
    user-installed app via install.sh.
    """
    return Path(sys.prefix)


class SettingsView(QWidget):
    """Credentials + paths + about, in three cards."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        title = QLabel("Settings")
        title.setProperty("role", "h1")
        subtitle = QLabel("Local credentials, paths, and benchbox version info")
        subtitle.setProperty("role", "dim")

        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        cred_card = self._build_credentials_card()
        paths_card = self._build_paths_card()
        about_card = self._build_about_card()

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)
        root.addLayout(header_text)
        root.addWidget(cred_card)
        root.addWidget(paths_card)
        root.addWidget(about_card)
        root.addStretch(1)

    # --- credentials --------------------------------------------------

    def _build_credentials_card(self) -> Card:
        card = Card()
        heading = QLabel("Credentials")
        heading.setProperty("role", "h2")
        card.addWidget(heading)

        self._status_row = QHBoxLayout()
        self._status_row.setSpacing(8)
        self._status_chip_holder = QHBoxLayout()
        self._status_chip_holder.setContentsMargins(0, 0, 0, 0)
        self._status_caption = QLabel()
        self._status_caption.setProperty("role", "dim")
        self._status_row.addLayout(self._status_chip_holder)
        self._status_row.addWidget(self._status_caption, 1)

        status_widget = QWidget()
        status_widget.setLayout(self._status_row)
        card.addWidget(status_widget)

        change_pw = QPushButton("Change MariaDB root password")
        change_pw.clicked.connect(self._on_change_password)
        reset = QPushButton("Reset all saved credentials")
        reset.setProperty("role", "danger")
        reset.clicked.connect(self._on_reset_credentials)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(change_pw)
        actions.addWidget(reset)
        actions.addStretch(1)
        actions_widget = QWidget()
        actions_widget.setLayout(actions)
        card.addWidget(actions_widget)

        self._refresh_status()
        return card

    def _refresh_status(self) -> None:
        # Clear the chip holder, then re-populate with the current state chip.
        while self._status_chip_holder.count() > 0:
            item = self._status_chip_holder.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        pw_set = credentials.get_mariadb_root_password() is not None
        chip_text = "MariaDB password saved" if pw_set else "MariaDB password not set"
        chip_color = _GREEN if pw_set else _RED
        self._status_chip_holder.addWidget(_chip(chip_text, chip_color))

        path = credentials.credentials_path()
        exists = path.is_file()
        self._status_caption.setText(
            f"<code>{path}</code> · "
            f"<span style='color:#a9a9c4;'>{'present' if exists else 'not yet created'}</span>"
        )

    def _on_change_password(self) -> None:
        new_pw, ok = QInputDialog.getText(
            self,
            "Change MariaDB root password",
            "Enter the new password. Stored at "
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
        self._refresh_status()
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
        self._refresh_status()
        QMessageBox.information(self, "Done", "Credentials cleared.")

    # --- paths --------------------------------------------------------

    def _build_paths_card(self) -> Card:
        card = Card()
        heading = QLabel("Paths")
        heading.setProperty("role", "h2")
        card.addWidget(heading)

        # Credentials file
        cred_path = credentials.credentials_path()
        card.addWidget(_path_row("Credentials", cred_path, exists=cred_path.is_file()))

        # Log directory
        session = logs.current_session_dir()
        log_dir = session.parent if session is not None else Path.home() / ".benchbox" / "logs"
        card.addWidget(_path_row("Logs", log_dir, exists=log_dir.is_dir()))

        # Venv benchbox runs from
        venv = _venv_prefix()
        card.addWidget(_path_row("Install", venv, exists=venv.is_dir()))

        # Config dir (the parent of the credentials file)
        config_dir_env = os.environ.get("BENCHBOX_CONFIG_DIR")
        config_dir = Path(config_dir_env) if config_dir_env else Path.home() / ".benchbox"
        card.addWidget(_path_row("Config", config_dir, exists=config_dir.is_dir()))
        return card

    # --- about --------------------------------------------------------

    def _build_about_card(self) -> Card:
        card = Card()
        heading = QLabel("About")
        heading.setProperty("role", "h2")
        card.addWidget(heading)

        # Versions — all three packages. The CLI version would also be
        # useful, but it adds an import path we don't need.
        versions = QLabel(
            "<table cellpadding='2'>"
            f"<tr><td><b>benchbox-gui</b></td><td><code>{gui_version}</code></td></tr>"
            f"<tr><td><b>benchbox-core</b></td><td><code>{core_version}</code></td></tr>"
            "</table>"
        )
        versions.setTextFormat(Qt.TextFormat.RichText)
        card.addWidget(versions)

        link = QLabel(
            "<span style='color:#a9a9c4;'>Source: "
            "<a href='https://github.com/Tusharp21/benchbox'>"
            "github.com/Tusharp21/benchbox</a> · "
            "Apache-2.0 licensed</span>"
        )
        link.setTextFormat(Qt.TextFormat.RichText)
        link.setOpenExternalLinks(True)
        card.addWidget(link)
        return card
