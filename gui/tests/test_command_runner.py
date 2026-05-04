from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from benchbox_gui.widgets.command_runner import (
    DEFAULT_QUICK_ACTIONS,
    BenchCommandRunner,
)


@pytest.fixture
def runner(qtbot: QtBot) -> BenchCommandRunner:
    widget = BenchCommandRunner()
    qtbot.addWidget(widget)
    return widget


def test_runner_starts_disabled_until_bench_is_set(runner: BenchCommandRunner) -> None:
    assert runner._run_btn.isEnabled() is False
    assert runner._input.isEnabled() is False


def test_set_bench_enables_input_and_populates_sites(
    runner: BenchCommandRunner, tmp_path: Path
) -> None:
    runner.set_bench(tmp_path, ["site-a", "site-b"])
    assert runner._run_btn.isEnabled() is True
    assert runner._input.isEnabled() is True
    # First entry is always the no-site sentinel.
    assert runner._site_select.itemData(0) == ""
    assert runner._site_select.itemData(1) == "site-a"
    assert runner._site_select.itemData(2) == "site-b"


def test_set_bench_to_none_disables_run(runner: BenchCommandRunner, tmp_path: Path) -> None:
    runner.set_bench(tmp_path, ["x"])
    runner.set_bench(None, [])
    assert runner._run_btn.isEnabled() is False
    assert runner._input.isEnabled() is False


def test_chip_with_site_selected_emits_site_form(
    runner: BenchCommandRunner, tmp_path: Path
) -> None:
    runner.set_bench(tmp_path, ["acme"])
    runner._site_select.setCurrentIndex(1)  # "acme"

    # Find the migrate chip and trigger its handler.
    migrate_builder = next(b for label, b in DEFAULT_QUICK_ACTIONS if label == "Migrate")
    runner._fill_from_chip(migrate_builder)
    assert runner._input.text() == "bench --site acme migrate"


def test_chip_without_site_emits_global_form(
    runner: BenchCommandRunner, tmp_path: Path
) -> None:
    runner.set_bench(tmp_path, ["acme"])
    # Sentinel "(no site selected)" is index 0.
    runner._site_select.setCurrentIndex(0)
    migrate_builder = next(b for label, b in DEFAULT_QUICK_ACTIONS if label == "Migrate")
    runner._fill_from_chip(migrate_builder)
    assert runner._input.text() == "bench migrate"


def test_run_with_empty_input_is_a_noop(runner: BenchCommandRunner, tmp_path: Path) -> None:
    runner.set_bench(tmp_path, [])
    runner._input.setText("   ")
    runner._on_run_clicked()
    assert runner.is_busy() is False


def test_spawn_emits_command_started(qtbot: QtBot, runner: BenchCommandRunner, tmp_path: Path) -> None:
    runner.set_bench(tmp_path, [])
    runner._input.setText("true")  # /bin/true exits 0 fast

    with qtbot.waitSignal(runner.command_started, timeout=2000) as start_signal:
        runner._on_run_clicked()
    assert start_signal.args == ["true"]

    # Wait for it to finish so we don't leak the QProcess.
    with qtbot.waitSignal(runner.command_finished, timeout=5000):
        pass
    assert runner.is_busy() is False


def test_finished_re_enables_run_button(
    qtbot: QtBot, runner: BenchCommandRunner, tmp_path: Path
) -> None:
    runner.set_bench(tmp_path, [])
    runner._input.setText("true")
    with qtbot.waitSignal(runner.command_finished, timeout=5000):
        runner._on_run_clicked()
    assert runner._run_btn.isEnabled() is True
    assert runner._cancel_btn.isEnabled() is False


def test_locked_site_hides_dropdown_and_scopes_chips(qtbot: QtBot, tmp_path: Path) -> None:
    runner = BenchCommandRunner(locked_site="locked-site")
    qtbot.addWidget(runner)
    runner.set_bench(tmp_path, ["other-site"])

    # Dropdown is invisible in locked mode.
    assert runner._site_select.isVisible() is False
    assert runner._site_label.isVisible() is False

    migrate_builder = next(b for label, b in DEFAULT_QUICK_ACTIONS if label == "Migrate")
    runner._fill_from_chip(migrate_builder)
    # The chip must use the locked site — never whatever the dropdown
    # *would* have shown.
    assert runner._input.text() == "bench --site locked-site migrate"


def test_shutdown_kills_inflight(
    qtbot: QtBot, runner: BenchCommandRunner, tmp_path: Path
) -> None:
    runner.set_bench(tmp_path, [])
    # Long-running command so we can interrupt it.
    runner._input.setText("sleep 30")
    runner._on_run_clicked()
    assert runner.is_busy() is True
    runner.shutdown()
    assert runner.is_busy() is False
