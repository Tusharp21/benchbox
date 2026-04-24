from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from benchbox_gui.views.bench_list import BenchListView


def _make_bench(path: Path) -> None:
    (path / "apps" / "frappe" / "frappe").mkdir(parents=True, exist_ok=True)
    (path / "apps" / "frappe" / "frappe" / "__init__.py").write_text(
        '__version__ = "15.0.0"\n', encoding="utf-8"
    )
    (path / "sites").mkdir(parents=True, exist_ok=True)
    (path / "sites" / "apps.txt").write_text("frappe\n", encoding="utf-8")
    (path / "sites" / "common_site_config.json").write_text(json.dumps({}), encoding="utf-8")


def test_bench_list_renders_discovered_benches(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_bench(tmp_path / "bench-a")
    _make_bench(tmp_path / "bench-b")

    def fake_discover(**kw: object) -> list[Path]:
        return sorted((tmp_path / "bench-a", tmp_path / "bench-b"))

    monkeypatch.setattr("benchbox_gui.views.bench_list.discovery.discover_benches", fake_discover)

    view = BenchListView()
    qtbot.addWidget(view)

    table = view._table  # noqa: SLF001 — direct access is the test's point
    assert table.rowCount() == 2
    # Column 1 is "frappe" — both rows should show 15.0.0.
    row0 = table.item(0, 1)
    row1 = table.item(1, 1)
    assert row0 is not None and row0.text() == "15.0.0"
    assert row1 is not None and row1.text() == "15.0.0"


def test_bench_list_empty_state(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("benchbox_gui.views.bench_list.discovery.discover_benches", lambda **kw: [])
    view = BenchListView()
    qtbot.addWidget(view)

    # ``isVisible()`` walks the parent chain; unshown widgets report False.
    # ``isHidden()`` reports the stored state from setVisible, which is what
    # the widget itself controls and what we actually want to verify.
    assert view._table.isHidden() is True  # noqa: SLF001
    assert view._empty.isHidden() is False  # noqa: SLF001
    assert view._table.rowCount() == 0  # noqa: SLF001
