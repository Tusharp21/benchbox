from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from benchbox_gui.views.bench_list import BenchListView
from benchbox_gui.widgets.bench_card import BenchCard


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

    assert view.card_count == 2
    cards = view.findChildren(BenchCard)
    assert len(cards) == 2


def test_bench_list_empty_state(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("benchbox_gui.views.bench_list.discovery.discover_benches", lambda **kw: [])
    view = BenchListView()
    qtbot.addWidget(view)

    # ``isVisible()`` walks the parent chain; unshown widgets report False.
    # ``isHidden()`` reports the stored state from setVisible, which is what
    # the widget itself controls and what we actually want to verify.
    assert view._scroll.isHidden() is True  # noqa: SLF001
    assert view._empty.isHidden() is False  # noqa: SLF001
    assert view.card_count == 0


def test_bench_card_emits_opened_with_path(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bench = tmp_path / "click-me"
    _make_bench(bench)
    monkeypatch.setattr(
        "benchbox_gui.views.bench_list.discovery.discover_benches",
        lambda **kw: [bench.resolve()],
    )

    view = BenchListView()
    qtbot.addWidget(view)

    card = view.findChild(BenchCard)
    assert card is not None

    received: list[Path] = []
    view.bench_selected.connect(received.append)
    card._emit_opened()  # noqa: SLF001

    assert received == [bench.resolve()]
