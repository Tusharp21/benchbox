from __future__ import annotations

from unittest.mock import patch

from benchbox_core import credentials
from pytestqt.qtbot import QtBot

from benchbox_gui.views.install import InstallerView


def test_prompt_returns_stored_password_without_dialog(qtbot: QtBot) -> None:
    credentials.set_mariadb_root_password("already-stored")
    view = InstallerView()
    qtbot.addWidget(view)

    # If the code reaches for QInputDialog the test would hang; a stored
    # password must short-circuit before that.
    with patch(
        "benchbox_gui.views.install.QInputDialog.getText",
        side_effect=AssertionError("should not prompt when password is stored"),
    ):
        assert view._ensure_password() == "already-stored"  # noqa: SLF001


def test_prompt_persists_new_password(qtbot: QtBot) -> None:
    view = InstallerView()
    qtbot.addWidget(view)

    with patch(
        "benchbox_gui.views.install.QInputDialog.getText",
        return_value=("fresh-pw", True),
    ):
        result = view._ensure_password()  # noqa: SLF001

    assert result == "fresh-pw"
    assert credentials.get_mariadb_root_password() == "fresh-pw"
