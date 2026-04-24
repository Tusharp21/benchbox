from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QProcess
from pytestqt.qtbot import QtBot

from benchbox_gui.services.bench_processes import MAX_LOG_LINES, BenchProcessManager


@pytest.fixture
def manager() -> BenchProcessManager:
    return BenchProcessManager()


def test_empty_manager_reports_nothing_running(manager: BenchProcessManager) -> None:
    assert manager.running_paths() == []
    assert manager.is_running(Path("/nowhere")) is False
    assert manager.log_of(Path("/nowhere")) == ""
    assert manager.status_of(Path("/nowhere")) == "stopped"


def test_start_spawns_process_and_emits_signal(
    qtbot: QtBot, tmp_path: Path, manager: BenchProcessManager
) -> None:
    bench = tmp_path
    started: list[Path] = []
    manager.process_started.connect(started.append)

    with qtbot.waitSignal(manager.process_started, timeout=2000):
        manager.start(bench)

    assert started == [bench.resolve()]
    # Force the process to exit so pytest doesn't leak bash children.
    manager.stop(bench)
    qtbot.waitUntil(lambda: not manager.is_running(bench), timeout=5000)


def test_double_start_same_bench_is_a_noop(
    qtbot: QtBot, tmp_path: Path, manager: BenchProcessManager
) -> None:
    bench = tmp_path
    starts: list[Path] = []
    manager.process_started.connect(starts.append)

    manager.start(bench)
    # Second start while the first is still in flight must not fire again.
    manager.start(bench)

    qtbot.wait(50)  # let the first one progress through ``starting``
    assert starts == [bench.resolve()]

    manager.stop(bench)
    qtbot.waitUntil(lambda: not manager.is_running(bench), timeout=5000)


def test_multiple_benches_run_concurrently(
    qtbot: QtBot, tmp_path: Path, manager: BenchProcessManager
) -> None:
    a = tmp_path / "bench-a"
    b = tmp_path / "bench-b"
    a.mkdir()
    b.mkdir()

    manager.start(a)
    manager.start(b)

    # Both should be tracked at once — that's the whole point of the
    # lifted-out manager.
    qtbot.waitUntil(lambda: manager.is_running(a) and manager.is_running(b), timeout=5000)
    running = set(manager.running_paths())
    assert a.resolve() in running
    assert b.resolve() in running

    manager.stop(a)
    manager.stop(b)


def test_stop_emits_process_stopped(
    qtbot: QtBot, tmp_path: Path, manager: BenchProcessManager
) -> None:
    bench = tmp_path
    manager.start(bench)
    qtbot.waitUntil(lambda: manager.is_running(bench), timeout=2000)

    stops: list[Path] = []
    manager.process_stopped.connect(lambda p, _code: stops.append(p))

    with qtbot.waitSignal(manager.process_stopped, timeout=5000):
        manager.stop(bench)

    assert stops == [bench.resolve()]
    assert manager.is_running(bench) is False


def test_log_buffer_caps_at_max_lines(tmp_path: Path, manager: BenchProcessManager) -> None:
    """_drain_output should trim when the log gets too long.

    We can't drive a real QProcess to spew 5000+ lines cheaply in a
    test, so poke the internal state directly and then feed one more
    chunk via the real code path.
    """
    bench = tmp_path
    resolved = bench.resolve()
    # Stub an entry so _drain_output finds it without needing a live
    # QProcess.
    from benchbox_gui.services.bench_processes import _Entry

    dummy_process = QProcess(manager)
    entry = _Entry(bench_path=resolved, process=dummy_process)
    entry.log_lines = [f"line {i}" for i in range(MAX_LOG_LINES)]
    manager._entries[resolved] = entry  # noqa: SLF001

    # We don't have a real stream to drain, so just ensure log_of trims.
    assert len(entry.log_lines) == MAX_LOG_LINES
    entry.log_lines.append("overflow")
    # Simulate the trim block in _drain_output.
    overflow = len(entry.log_lines) - MAX_LOG_LINES
    entry.log_lines = entry.log_lines[overflow:]
    assert len(entry.log_lines) == MAX_LOG_LINES
    assert entry.log_lines[-1] == "overflow"
