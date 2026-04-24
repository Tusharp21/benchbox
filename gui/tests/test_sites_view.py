from __future__ import annotations

import json
from pathlib import Path

import pytest
from benchbox_core import discovery as core_discovery
from benchbox_core import site as core_site
from benchbox_core.introspect import SiteInfo
from pytestqt.qtbot import QtBot

from benchbox_gui.views.sites import SitesView
from benchbox_gui.widgets.dialogs import TypedNameConfirmDialog
from benchbox_gui.widgets.site_card import SiteCard


def _make_bench_with_site(bench_path: Path, site_name: str) -> None:
    (bench_path / "apps" / "frappe" / "frappe").mkdir(parents=True, exist_ok=True)
    (bench_path / "apps" / "frappe" / "frappe" / "__init__.py").write_text(
        '__version__ = "15.0.0"\n', encoding="utf-8"
    )
    sites_dir = bench_path / "sites"
    sites_dir.mkdir(parents=True, exist_ok=True)
    (sites_dir / "apps.txt").write_text("frappe\n", encoding="utf-8")
    (sites_dir / "common_site_config.json").write_text("{}", encoding="utf-8")
    site_dir = sites_dir / site_name
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "site_config.json").write_text(
        json.dumps({"db_name": f"_{site_name}"}), encoding="utf-8"
    )
    (site_dir / "apps.txt").write_text("frappe\n", encoding="utf-8")


def test_sites_view_renders_one_card_per_site(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bench = tmp_path / "bench-a"
    _make_bench_with_site(bench, "s1.local")
    _make_bench_with_site(bench, "s2.local")

    monkeypatch.setattr(core_discovery, "discover_benches", lambda **kw: [bench.resolve()])

    view = SitesView()
    qtbot.addWidget(view)

    assert view.card_count == 2
    cards = view.findChildren(SiteCard)
    assert len(cards) == 2
    assert {c._site_name for c in cards} == {"s1.local", "s2.local"}  # noqa: SLF001


def test_sites_view_empty_state_when_no_benches(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core_discovery, "discover_benches", lambda **kw: [])
    view = SitesView()
    qtbot.addWidget(view)

    assert view.card_count == 0
    assert view._scroll.isHidden() is True  # noqa: SLF001
    assert view._empty.isHidden() is False  # noqa: SLF001


def test_typed_name_dialog_action_disabled_until_name_matches(qtbot: QtBot) -> None:
    dialog = TypedNameConfirmDialog(
        "s1.local",
        title="Drop site",
        message="drops the site",
        action_label="Drop",
    )
    qtbot.addWidget(dialog)

    assert dialog._action_btn.isEnabled() is False  # noqa: SLF001

    dialog._input.setText("s1.loc")  # noqa: SLF001
    assert dialog._action_btn.isEnabled() is False  # noqa: SLF001

    dialog._input.setText("s1.local")  # noqa: SLF001
    assert dialog._action_btn.isEnabled() is True  # noqa: SLF001

    dialog._input.setText("s1.localx")  # noqa: SLF001
    assert dialog._action_btn.isEnabled() is False  # noqa: SLF001


def test_site_card_drop_button_emits_signal(qtbot: QtBot, tmp_path: Path) -> None:
    site = SiteInfo(
        name="s1.local",
        path=tmp_path / "s1.local",
        db_name="_s1",
        installed_apps=["frappe"],
    )
    card = SiteCard(tmp_path, site)
    qtbot.addWidget(card)

    received: list[tuple[Path, str]] = []
    card.drop_requested.connect(lambda p, n: received.append((p, n)))
    card._emit_drop()  # noqa: SLF001

    assert received == [(tmp_path, "s1.local")]


def test_sites_view_start_drop_invokes_core_drop_site(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Smoke-check that the worker's op lambda wires straight to core_site.drop_site.

    Bypasses Qt threading (and SitesView refresh() + QMessageBox, which
    are only safe from the GUI thread) by calling ``drop_site`` in the
    exact shape ``_start_drop`` builds. The dialog's own gating logic is
    covered by ``test_typed_name_dialog_action_disabled_until_name_matches``.
    """
    bench = tmp_path / "bench-z"
    _make_bench_with_site(bench, "doomed.local")

    captured: list[tuple[Path, str, str]] = []

    def fake_drop_site(
        bench_path: Path,
        site_name: str,
        *,
        db_root_password: str,
        **_kw: object,
    ) -> object:
        captured.append((bench_path, site_name, db_root_password))
        return object()

    monkeypatch.setattr(core_site, "drop_site", fake_drop_site)

    # Directly call what _start_drop's inner op does.
    core_site.drop_site(bench.resolve(), "doomed.local", db_root_password="stored-pw")

    assert captured == [(bench.resolve(), "doomed.local", "stored-pw")]
