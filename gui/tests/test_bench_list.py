from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from benchbox_gui.services.bench_processes import BenchProcessManager
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


@pytest.fixture
def manager() -> BenchProcessManager:
    # Fresh per-test — avoids state bleed between tests.
    return BenchProcessManager()


def test_bench_list_renders_discovered_benches(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manager: BenchProcessManager,
) -> None:
    _make_bench(tmp_path / "bench-a")
    _make_bench(tmp_path / "bench-b")

    def fake_discover(**kw: object) -> list[Path]:
        return sorted((tmp_path / "bench-a", tmp_path / "bench-b"))

    monkeypatch.setattr("benchbox_gui.views.bench_list.discovery.discover_benches", fake_discover)

    view = BenchListView(manager)
    qtbot.addWidget(view)

    assert view.card_count == 2
    cards = view.findChildren(BenchCard)
    assert len(cards) == 2


def test_bench_list_empty_state(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, manager: BenchProcessManager
) -> None:
    monkeypatch.setattr("benchbox_gui.views.bench_list.discovery.discover_benches", lambda **kw: [])
    view = BenchListView(manager)
    qtbot.addWidget(view)

    assert view._scroll.isHidden() is True  # noqa: SLF001
    assert view._empty.isHidden() is False  # noqa: SLF001
    assert view.card_count == 0


def test_bench_card_emits_opened_with_path(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manager: BenchProcessManager,
) -> None:
    bench = tmp_path / "click-me"
    _make_bench(bench)
    monkeypatch.setattr(
        "benchbox_gui.views.bench_list.discovery.discover_benches",
        lambda **kw: [bench.resolve()],
    )

    view = BenchListView(manager)
    qtbot.addWidget(view)

    card = view.findChild(BenchCard)
    assert card is not None

    received: list[Path] = []
    view.bench_selected.connect(received.append)
    card._emit_opened()  # noqa: SLF001

    assert received == [bench.resolve()]


def test_bench_list_search_filters_visible_cards(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manager: BenchProcessManager,
) -> None:
    paths = [tmp_path / "alpha-bench", tmp_path / "beta-bench", tmp_path / "gamma-bench"]
    for p in paths:
        _make_bench(p)

    monkeypatch.setattr(
        "benchbox_gui.views.bench_list.discovery.discover_benches",
        lambda **kw: sorted(paths),
    )

    view = BenchListView(manager)
    qtbot.addWidget(view)
    view.show()  # isHidden() needs real visibility state

    # No filter → all visible.
    cards = view.findChildren(BenchCard)
    assert len(cards) == 3
    for c in cards:
        assert c.isHidden() is False

    # Partial match filters out the ones that don't contain "alpha".
    view._search.setText("alpha")  # noqa: SLF001
    alpha_cards = [c for c in cards if "alpha" in c.bench_path.name]
    other_cards = [c for c in cards if "alpha" not in c.bench_path.name]
    for c in alpha_cards:
        assert c.isHidden() is False
    for c in other_cards:
        assert c.isHidden() is True


def test_bench_list_card_flips_running_chip_on_manager_signals(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manager: BenchProcessManager,
) -> None:
    bench = tmp_path / "busy"
    _make_bench(bench)
    resolved = bench.resolve()
    monkeypatch.setattr(
        "benchbox_gui.views.bench_list.discovery.discover_benches",
        lambda **kw: [resolved],
    )

    view = BenchListView(manager)
    qtbot.addWidget(view)
    card = view.findChild(BenchCard)
    assert card is not None
    assert card._running_chip.isVisible() is False  # noqa: SLF001

    # Simulate the manager reporting a new start.
    manager.process_started.emit(resolved)
    assert card._running_chip.isHidden() is False  # noqa: SLF001

    # And a stop — chip goes away again.
    manager.process_stopped.emit(resolved, 0)
    assert card._running_chip.isHidden() is True  # noqa: SLF001


def test_bench_card_url_link_appears_when_running(qtbot: QtBot, tmp_path: Path) -> None:
    from benchbox_core.introspect import BenchInfo

    info = BenchInfo(
        path=tmp_path / "a-bench",
        frappe_version="15.0.0",
        python_version="3.10.12",
        git_branch="version-15",
        apps=[],
        sites=[],
        webserver_port=8080,
    )
    card = BenchCard(info)
    qtbot.addWidget(card)

    assert card._url_link.isHidden() is True  # noqa: SLF001
    card.set_running(True)
    assert card._url_link.isHidden() is False  # noqa: SLF001
    assert "localhost:8080" in card.url
    assert "localhost:8080" in card._url_link.text()  # noqa: SLF001
    card.set_running(False)
    assert card._url_link.isHidden() is True  # noqa: SLF001


def test_bench_list_running_only_filter_hides_stopped(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manager: BenchProcessManager,
) -> None:
    running_bench = tmp_path / "hot"
    stopped_bench = tmp_path / "cold"
    _make_bench(running_bench)
    _make_bench(stopped_bench)

    # Fake discover + manager.is_running so we can drive state without
    # spawning real QProcesses.
    monkeypatch.setattr(
        "benchbox_gui.views.bench_list.discovery.discover_benches",
        lambda **kw: [running_bench.resolve(), stopped_bench.resolve()],
    )
    monkeypatch.setattr(
        manager,
        "is_running",
        lambda path: path.resolve() == running_bench.resolve(),
    )

    view = BenchListView(manager)
    qtbot.addWidget(view)

    cards = {c.bench_path: c for c in view.findChildren(BenchCard)}
    assert len(cards) == 2
    for c in cards.values():
        assert c.isHidden() is False

    # Toggle running-only: stopped bench should disappear.
    view._running_only_toggle.setChecked(True)  # noqa: SLF001
    assert cards[running_bench.resolve()].isHidden() is False
    assert cards[stopped_bench.resolve()].isHidden() is True

    # Untoggle restores both.
    view._running_only_toggle.setChecked(False)  # noqa: SLF001
    for c in cards.values():
        assert c.isHidden() is False
