from __future__ import annotations

from pathlib import Path

import pytest
from benchbox_core import credentials as core_credentials
from benchbox_core import database as core_database
from benchbox_core.database import DatabaseInfo
from pytestqt.qtbot import QtBot

from benchbox_gui.views.databases import DatabasesView


@pytest.fixture
def saved_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core_credentials, "get_mariadb_root_password", lambda: "root-pw")


def _make_rows() -> list[DatabaseInfo]:
    return [
        DatabaseInfo(
            name="_shop",
            size_bytes=12345,
            site_name="shop.local",
            bench_path=Path("/home/u/bench-a"),
        ),
        DatabaseInfo(name="_lost", size_bytes=4096, site_name=None, bench_path=None),
        DatabaseInfo(name="_archive", size_bytes=0, site_name=None, bench_path=None),
    ]


def test_view_renders_one_row_per_database(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, saved_password: None
) -> None:
    rows = _make_rows()
    monkeypatch.setattr(core_database, "list_databases", lambda **_kw: list(rows))

    view = DatabasesView()
    qtbot.addWidget(view)

    assert view.row_count == 3


def test_view_filters_by_status(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, saved_password: None
) -> None:
    rows = _make_rows()
    monkeypatch.setattr(core_database, "list_databases", lambda **_kw: list(rows))

    view = DatabasesView()
    qtbot.addWidget(view)

    # Pick "Orphan only"
    idx = view._status_combo.findData("orphan")  # noqa: SLF001
    assert idx > 0
    view._status_combo.setCurrentIndex(idx)  # noqa: SLF001
    assert view.row_count == 2

    # And "Allocated only"
    idx = view._status_combo.findData("allocated")  # noqa: SLF001
    view._status_combo.setCurrentIndex(idx)  # noqa: SLF001
    assert view.row_count == 1


def test_view_text_filter_matches_name_site_or_bench(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, saved_password: None
) -> None:
    rows = _make_rows()
    monkeypatch.setattr(core_database, "list_databases", lambda **_kw: list(rows))

    view = DatabasesView()
    qtbot.addWidget(view)

    view._search.setText("shop")  # noqa: SLF001
    assert view.row_count == 1

    view._search.setText("bench-a")  # noqa: SLF001
    assert view.row_count == 1

    view._search.setText("nope")  # noqa: SLF001
    assert view.row_count == 0


def test_view_drop_button_disabled_for_allocated(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, saved_password: None
) -> None:
    from PySide6.QtWidgets import QPushButton

    rows = _make_rows()
    monkeypatch.setattr(core_database, "list_databases", lambda **_kw: list(rows))

    view = DatabasesView()
    qtbot.addWidget(view)

    drop_states: dict[str, bool] = {}
    for r in range(view.row_count):
        name = view._table.item(r, 0).text()  # noqa: SLF001
        cell = view._table.cellWidget(r, 5)  # noqa: SLF001
        btn = cell.findChild(QPushButton)
        drop_states[name] = btn.isEnabled()
    assert drop_states == {"_shop": False, "_lost": True, "_archive": True}


def test_view_shows_notice_when_password_missing(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core_credentials, "get_mariadb_root_password", lambda: None)
    monkeypatch.setattr(
        core_database,
        "list_databases",
        lambda **_kw: pytest.fail("must not query without a password"),
    )

    view = DatabasesView()
    qtbot.addWidget(view)

    assert view.row_count == 0
    assert view._notice.isHidden() is False  # noqa: SLF001
    assert "password" in view._notice.text().lower()  # noqa: SLF001


def test_view_shows_notice_on_query_failure(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, saved_password: None
) -> None:
    def raise_error(**_kw: object) -> list[DatabaseInfo]:
        raise core_database.DatabaseError("Access denied")

    monkeypatch.setattr(core_database, "list_databases", raise_error)
    view = DatabasesView()
    qtbot.addWidget(view)

    assert view.row_count == 0
    assert view._notice.isHidden() is False  # noqa: SLF001
    assert "Access denied" in view._notice.text()  # noqa: SLF001
