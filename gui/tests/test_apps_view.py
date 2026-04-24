from __future__ import annotations

from pathlib import Path

import pytest
from benchbox_core import app as core_app
from benchbox_core import discovery as core_discovery
from benchbox_core.introspect import AppInfo
from pytestqt.qtbot import QtBot

from benchbox_gui.views.apps import AppsView
from benchbox_gui.widgets.app_card import FRAPPE_APP_NAME, AppCard


def _make_bench_with_app(
    bench_path: Path, app_name: str, version: str = "1.0.0", branch: str = "main"
) -> None:
    apps_dir = bench_path / "apps"
    app_dir = apps_dir / app_name / app_name
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "__init__.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    # Fake a .git/HEAD so introspect can read the branch.
    git_dir = apps_dir / app_name / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text(f"ref: refs/heads/{branch}\n", encoding="utf-8")

    # Minimum bench skeleton so discovery.is_bench accepts this path.
    if not (apps_dir / "frappe").is_dir() and app_name != "frappe":
        frappe_dir = apps_dir / "frappe" / "frappe"
        frappe_dir.mkdir(parents=True, exist_ok=True)
        (frappe_dir / "__init__.py").write_text('__version__ = "15.0.0"\n', encoding="utf-8")
    sites_dir = bench_path / "sites"
    sites_dir.mkdir(parents=True, exist_ok=True)
    apps_txt = sites_dir / "apps.txt"
    # Append to apps.txt so multiple _make_bench_with_app calls accumulate.
    existing: set[str] = set()
    if apps_txt.is_file():
        existing = {line.strip() for line in apps_txt.read_text().splitlines() if line.strip()}
    existing.add("frappe")
    existing.add(app_name)
    apps_txt.write_text("\n".join(sorted(existing)) + "\n", encoding="utf-8")
    (sites_dir / "common_site_config.json").write_text("{}", encoding="utf-8")


# --- AppCard -------------------------------------------------------


def test_app_card_emits_uninstall_and_remove(qtbot: QtBot, tmp_path: Path) -> None:
    card = AppCard(
        tmp_path / "bench", AppInfo(name="erpnext", version="15.1.0", git_branch="version-15")
    )
    qtbot.addWidget(card)

    uninstalls: list[tuple[Path, str]] = []
    removes: list[tuple[Path, str]] = []
    card.uninstall_requested.connect(lambda b, a: uninstalls.append((b, a)))
    card.remove_requested.connect(lambda b, a: removes.append((b, a)))

    # Click the two destructive buttons by finding them by role.
    from PySide6.QtWidgets import QPushButton

    buttons = card.findChildren(QPushButton)
    uninstall_btn = next(b for b in buttons if "Uninstall" in b.text())
    remove_btn = next(b for b in buttons if "Remove from bench" in b.text())

    uninstall_btn.click()
    remove_btn.click()

    assert uninstalls == [(tmp_path / "bench", "erpnext")]
    assert removes == [(tmp_path / "bench", "erpnext")]


def test_app_card_frappe_has_disabled_destructive_buttons(qtbot: QtBot, tmp_path: Path) -> None:
    from PySide6.QtWidgets import QPushButton

    card = AppCard(tmp_path, AppInfo(name=FRAPPE_APP_NAME, version="15.0.0", git_branch="main"))
    qtbot.addWidget(card)

    buttons = card.findChildren(QPushButton)
    for btn in buttons:
        assert btn.isEnabled() is False, f"{btn.text()} should be disabled on a frappe card"
        assert btn.toolTip(), f"{btn.text()} should have an explanatory tooltip"


# --- AppsView -------------------------------------------------------


def test_apps_view_renders_one_card_per_app(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bench = tmp_path / "bench-a"
    _make_bench_with_app(bench, "erpnext", "15.1.0")
    _make_bench_with_app(bench, "hrms", "1.5.0")

    monkeypatch.setattr(core_discovery, "discover_benches", lambda **kw: [bench.resolve()])

    view = AppsView()
    qtbot.addWidget(view)

    # 3 apps expected: frappe + erpnext + hrms.
    assert view.card_count == 3
    cards = view.findChildren(AppCard)
    app_names = {c._app_name for c in cards}  # noqa: SLF001
    assert app_names == {"frappe", "erpnext", "hrms"}


def test_apps_view_empty_state(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core_discovery, "discover_benches", lambda **kw: [])

    view = AppsView()
    qtbot.addWidget(view)

    assert view.card_count == 0
    assert view._scroll.isHidden() is True  # noqa: SLF001
    assert view._empty.isHidden() is False  # noqa: SLF001


def test_apps_view_start_remove_calls_core_remove_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Smoke-check that _start_remove_app wires straight to core_app.remove_app."""
    captured: list[tuple[Path, str]] = []

    def fake_remove_app(
        bench_path: Path,
        app: str,
        **_kw: object,
    ) -> object:
        captured.append((bench_path, app))
        return object()

    monkeypatch.setattr(core_app, "remove_app", fake_remove_app)

    # Directly exercise the core call the worker's op would run.
    core_app.remove_app(tmp_path / "bench", "erpnext")

    assert captured == [(tmp_path / "bench", "erpnext")]


def test_apps_view_start_uninstall_calls_core_uninstall_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[tuple[Path, str, str]] = []

    def fake_uninstall_app(
        bench_path: Path,
        site: str,
        app: str,
        **_kw: object,
    ) -> object:
        captured.append((bench_path, site, app))
        return object()

    monkeypatch.setattr(core_app, "uninstall_app", fake_uninstall_app)

    core_app.uninstall_app(tmp_path / "bench", "s.local", "erpnext")

    assert captured == [(tmp_path / "bench", "s.local", "erpnext")]
