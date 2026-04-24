from __future__ import annotations

import subprocess
from typing import Any

import pytest

from benchbox_core.installer._run import CommandResult, CommandRunner


def test_dry_run_does_not_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    def boom(*a: Any, **kw: Any) -> None:
        calls.append((a, kw))
        raise AssertionError("subprocess.run must not be called in dry-run mode")

    monkeypatch.setattr("benchbox_core.installer._run.subprocess.run", boom)

    runner = CommandRunner(dry_run=True)
    result = runner.run(["echo", "hi"])

    assert result.executed is False
    assert result.returncode == 0
    assert result.command == ("echo", "hi")
    assert calls == []


def test_run_captures_stdout_and_returncode() -> None:
    runner = CommandRunner(dry_run=False)
    result = runner.run(["printf", "hello"])

    assert result.executed is True
    assert result.returncode == 0
    assert result.stdout == "hello"
    assert result.ok is True


def test_run_records_history() -> None:
    runner = CommandRunner(dry_run=False)
    runner.run(["true"])
    runner.run(["true"])

    assert len(runner.history) == 2
    assert all(r.executed for r in runner.history)


def test_run_propagates_nonzero_exit_without_check() -> None:
    runner = CommandRunner(dry_run=False)
    result = runner.run(["sh", "-c", "exit 3"])

    assert result.executed is True
    assert result.returncode == 3
    assert result.ok is False


def test_run_with_check_raises_on_failure() -> None:
    runner = CommandRunner(dry_run=False)
    with pytest.raises(subprocess.CalledProcessError):
        runner.run(["sh", "-c", "exit 1"], check=True)


def test_run_handles_missing_binary() -> None:
    runner = CommandRunner(dry_run=False)
    result = runner.run(["benchbox-nonexistent-binary-xyz"])

    assert result.returncode == 127
    assert result.executed is True
    assert "benchbox-nonexistent-binary-xyz" in result.stderr


def test_command_result_ok_requires_executed() -> None:
    dry = CommandResult(("true",), 0, "", "", executed=False)
    real = CommandResult(("true",), 0, "", "", executed=True)
    assert dry.ok is False
    assert real.ok is True
