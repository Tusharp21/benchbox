from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchbox_core import bench
from benchbox_core.bench import (
    BenchAlreadyExistsError,
    BenchCreationError,
    create_bench,
)
from benchbox_core.installer._run import CommandResult, CommandRunner


def _make_bench_layout(path: Path) -> None:
    """Write the minimum files that discovery.is_bench() recognises."""
    (path / "apps" / "frappe" / "frappe").mkdir(parents=True, exist_ok=True)
    (path / "apps" / "frappe" / "frappe" / "__init__.py").write_text(
        '__version__ = "15.0.0"\n', encoding="utf-8"
    )
    (path / "sites").mkdir(parents=True, exist_ok=True)
    (path / "sites" / "apps.txt").write_text("frappe\n", encoding="utf-8")
    (path / "sites" / "common_site_config.json").write_text(json.dumps({}), encoding="utf-8")


class CapturingRunner(CommandRunner):
    def __init__(self, *, returncode: int = 0, post_run: object | None = None) -> None:
        super().__init__(dry_run=False)
        self._returncode = returncode
        self.commands: list[tuple[str, ...]] = []
        self._post_run = post_run

    def run(
        self,
        command: list[str] | tuple[str, ...],
        *,
        input: str | None = None,
        cwd: str | Path | None = None,
        check: bool = False,
        timeout: float | None = None,
        line_callback: object | None = None,
    ) -> CommandResult:
        argv = tuple(command)
        self.commands.append(argv)
        if callable(self._post_run):
            self._post_run()
        stderr = "" if self._returncode == 0 else "boom"
        return CommandResult(argv, self._returncode, "", stderr, True)


def test_create_bench_raises_if_path_already_has_bench(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    _make_bench_layout(target)

    with pytest.raises(BenchAlreadyExistsError):
        create_bench(target)


def test_create_bench_invokes_bench_init_with_defaults(tmp_path: Path) -> None:
    target = tmp_path / "new-bench"
    runner = CapturingRunner(
        returncode=0,
        post_run=lambda: _make_bench_layout(target),
    )

    result = create_bench(target, runner=runner)

    assert runner.commands == [
        (
            "bench",
            "init",
            str(target),
            "--frappe-branch",
            bench.DEFAULT_FRAPPE_BRANCH,
            "--python",
            bench.DEFAULT_PYTHON_BIN,
        )
    ]
    assert result.command.ok is True
    assert result.info is not None
    assert result.info.path == target.resolve()
    assert result.info.frappe_version == "15.0.0"


def test_create_bench_honours_custom_branch_and_python(tmp_path: Path) -> None:
    target = tmp_path / "custom"
    runner = CapturingRunner(
        returncode=0,
        post_run=lambda: _make_bench_layout(target),
    )

    create_bench(
        target,
        frappe_branch="develop",
        python_bin="python3.12",
        runner=runner,
    )

    argv = runner.commands[0]
    assert "--frappe-branch" in argv
    assert argv[argv.index("--frappe-branch") + 1] == "develop"
    assert "--python" in argv
    assert argv[argv.index("--python") + 1] == "python3.12"


def test_create_bench_raises_on_nonzero_exit(tmp_path: Path) -> None:
    target = tmp_path / "fails"
    runner = CapturingRunner(returncode=2)

    with pytest.raises(BenchCreationError) as excinfo:
        create_bench(target, runner=runner)

    assert "exit 2" in str(excinfo.value)
    assert excinfo.value.result.returncode == 2


def test_create_bench_dry_run_returns_info_none(tmp_path: Path) -> None:
    target = tmp_path / "dry"
    runner = CommandRunner(dry_run=True)

    result = create_bench(target, runner=runner)

    # dry-run: the command was logged but not executed, so we can't introspect.
    assert result.command.executed is False
    assert result.info is None
