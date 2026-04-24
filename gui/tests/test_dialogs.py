from __future__ import annotations

from pathlib import Path

from benchbox_core.bench import DEFAULT_FRAPPE_BRANCH, DEFAULT_PYTHON_BIN
from pytestqt.qtbot import QtBot

from benchbox_gui.widgets.dialogs import (
    GetAppDialog,
    NewBenchDialog,
    NewSiteDialog,
)


def test_new_bench_dialog_values_use_placeholder_when_blank(qtbot: QtBot) -> None:
    dialog = NewBenchDialog()
    qtbot.addWidget(dialog)
    values = dialog.values()
    # Placeholder is `~/frappe-bench`, resolved via expanduser.
    assert values.path == (Path.home() / "frappe-bench")
    assert values.frappe_branch == DEFAULT_FRAPPE_BRANCH
    assert values.python_bin == DEFAULT_PYTHON_BIN


def test_new_bench_dialog_roundtrips_custom_values(qtbot: QtBot, tmp_path: Path) -> None:
    dialog = NewBenchDialog()
    qtbot.addWidget(dialog)
    dialog._path.setText(str(tmp_path / "mybench"))  # noqa: SLF001
    dialog._branch.setText("develop")  # noqa: SLF001
    dialog._python.setText("python3.12")  # noqa: SLF001

    values = dialog.values()
    assert values.path == tmp_path / "mybench"
    assert values.frappe_branch == "develop"
    assert values.python_bin == "python3.12"


def test_new_site_dialog_parses_install_apps(qtbot: QtBot, tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    dialog = NewSiteDialog([bench], preselect=bench)
    qtbot.addWidget(dialog)
    dialog._name.setText("site1.local")  # noqa: SLF001
    dialog._admin.setText("admin-pw")  # noqa: SLF001
    dialog._apps.setText("erpnext, hrms,  crm")  # noqa: SLF001
    dialog._set_default.setChecked(True)  # noqa: SLF001

    values = dialog.values()
    assert values.bench_path == bench
    assert values.site_name == "site1.local"
    assert values.admin_password == "admin-pw"
    assert values.install_apps == ("erpnext", "hrms", "crm")
    assert values.set_default is True


def test_get_app_dialog_empty_branch_returns_none(qtbot: QtBot, tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    dialog = GetAppDialog([bench], preselect=bench)
    qtbot.addWidget(dialog)
    dialog._url.setText("https://github.com/frappe/erpnext")  # noqa: SLF001

    values = dialog.values()
    assert values.git_url == "https://github.com/frappe/erpnext"
    assert values.branch is None  # blank field → None


def test_get_app_dialog_preserves_custom_branch(qtbot: QtBot, tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    dialog = GetAppDialog([bench], preselect=bench)
    qtbot.addWidget(dialog)
    dialog._url.setText("https://github.com/frappe/erpnext")  # noqa: SLF001
    dialog._branch.setText("version-15")  # noqa: SLF001

    assert dialog.values().branch == "version-15"
