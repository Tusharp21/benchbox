from __future__ import annotations

import json
from pathlib import Path

import pytest
from benchbox_core.installer._run import CommandResult, CommandRunner
from typer.testing import CliRunner

from benchbox_cli.main import app


def _make_bench(path: Path, version: str = "15.0.0") -> None:
    (path / "apps" / "frappe" / "frappe").mkdir(parents=True, exist_ok=True)
    (path / "apps" / "frappe" / "frappe" / "__init__.py").write_text(
        f'__version__ = "{version}"\n', encoding="utf-8"
    )
    (path / "sites").mkdir(parents=True, exist_ok=True)
    (path / "sites" / "apps.txt").write_text("frappe\n", encoding="utf-8")
    (path / "sites" / "common_site_config.json").write_text(json.dumps({}), encoding="utf-8")


def test_bench_list_finds_existing_bench(cli: CliRunner, tmp_path: Path) -> None:
    _make_bench(tmp_path / "bench-a")

    result = cli.invoke(app, ["bench", "list", "--root", str(tmp_path)])
    assert result.exit_code == 0
    # Path may be Rich-truncated in the rendered table; the frappe version is
    # the reliable signal that discovery + introspect both worked.
    assert "15.0.0" in result.stdout
    assert "benches" in result.stdout  # table title


def test_bench_list_reports_empty(cli: CliRunner, tmp_path: Path) -> None:
    result = cli.invoke(app, ["bench", "list", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "no benches found" in result.stdout


def test_bench_info_refuses_non_bench_dir(cli: CliRunner, tmp_path: Path) -> None:
    not_a_bench = tmp_path / "random"
    not_a_bench.mkdir()
    result = cli.invoke(app, ["bench", "info", str(not_a_bench)])
    assert result.exit_code == 2
    assert "not a bench" in result.stderr


def test_bench_info_renders_existing_bench(cli: CliRunner, tmp_path: Path) -> None:
    _make_bench(tmp_path / "bench-a")
    result = cli.invoke(app, ["bench", "info", str(tmp_path / "bench-a")])
    assert result.exit_code == 0
    assert "frappe" in result.stdout.lower()


def test_bench_new_dry_run_reports_without_executing(
    cli: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Dry-run runner doesn't touch the system. Bench-new will ask the runner
    # to execute `bench init` — we verify only that exit is 0.
    result = cli.invoke(app, ["bench", "new", str(tmp_path / "new-bench"), "--dry-run"])
    assert result.exit_code == 0


def test_bench_new_rejects_existing_bench(cli: CliRunner, tmp_path: Path) -> None:
    existing = tmp_path / "existing"
    _make_bench(existing)
    result = cli.invoke(app, ["bench", "new", str(existing)])
    assert result.exit_code == 2


def test_bench_new_forwards_failure(
    cli: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(
        self: CommandRunner,
        command: list[str] | tuple[str, ...],
        **kw: object,
    ) -> CommandResult:
        return CommandResult(tuple(command), 2, "", "bench init broke", True)

    monkeypatch.setattr(CommandRunner, "run", fake_run)

    result = cli.invoke(app, ["bench", "new", str(tmp_path / "failing")])
    assert result.exit_code == 1
    assert "bench init" in result.stderr
