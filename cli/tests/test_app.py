from __future__ import annotations

from pathlib import Path

import pytest
from benchbox_core.installer._run import CommandResult, CommandRunner
from typer.testing import CliRunner

from benchbox_cli.main import app


def _make_bench(path: Path) -> None:
    (path / "apps" / "frappe" / "frappe").mkdir(parents=True, exist_ok=True)
    (path / "apps" / "frappe" / "frappe" / "__init__.py").write_text(
        '__version__ = "15.0.0"\n', encoding="utf-8"
    )
    (path / "sites").mkdir(parents=True, exist_ok=True)
    (path / "sites" / "apps.txt").write_text("frappe\n", encoding="utf-8")
    (path / "sites" / "common_site_config.json").write_text("{}", encoding="utf-8")


def _add_app(bench: Path, name: str) -> None:
    app_dir = bench / "apps" / name / name
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "__init__.py").write_text('__version__ = "1.0.0"\n', encoding="utf-8")


@pytest.fixture
def bench_path(tmp_path: Path) -> Path:
    bench = tmp_path / "bench"
    _make_bench(bench)
    return bench


def test_app_get_forwards_url_and_cwd(
    cli: CliRunner, bench_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[tuple[tuple[str, ...], object]] = []

    def fake_run(
        self: CommandRunner,
        command: list[str] | tuple[str, ...],
        *,
        input: str | None = None,
        cwd: object = None,
        check: bool = False,
        timeout: float | None = None,
    ) -> CommandResult:
        captured.append((tuple(command), cwd))
        _add_app(bench_path, "erpnext")
        return CommandResult(tuple(command), 0, "", "", True)

    monkeypatch.setattr(CommandRunner, "run", fake_run)

    result = cli.invoke(app, ["app", "get", str(bench_path), "https://github.com/frappe/erpnext"])
    assert result.exit_code == 0
    argv, cwd = captured[0]
    assert argv[0] == "bench" and argv[1] == "get-app"
    assert argv[2] == "https://github.com/frappe/erpnext"
    assert str(cwd) == str(bench_path)


def _recording_runner(
    captured: list[tuple[str, ...]],
) -> object:
    def fake_run(
        self: CommandRunner,
        command: list[str] | tuple[str, ...],
        **kw: object,
    ) -> CommandResult:
        captured.append(tuple(command))
        return CommandResult(tuple(command), 0, "", "", True)

    return fake_run


def test_app_install_multiple_apps(
    cli: CliRunner, bench_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[tuple[str, ...]] = []
    monkeypatch.setattr(CommandRunner, "run", _recording_runner(captured))

    result = cli.invoke(
        app,
        ["app", "install", str(bench_path), "s.local", "erpnext", "hrms"],
    )
    assert result.exit_code == 0
    argv = captured[0]
    assert argv[:4] == ("bench", "--site", "s.local", "install-app")
    assert argv[4:] == ("erpnext", "hrms")


def test_app_uninstall_yes_on_by_default(
    cli: CliRunner, bench_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[tuple[str, ...]] = []
    monkeypatch.setattr(CommandRunner, "run", _recording_runner(captured))

    result = cli.invoke(app, ["app", "uninstall", str(bench_path), "s.local", "erpnext"])
    assert result.exit_code == 0
    assert "--yes" in captured[0]


def test_app_uninstall_failure_propagates(
    cli: CliRunner, bench_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        CommandRunner,
        "run",
        lambda self, command, **kw: CommandResult(tuple(command), 1, "", "boom", True),
    )
    result = cli.invoke(app, ["app", "uninstall", str(bench_path), "s.local", "erpnext"])
    assert result.exit_code == 1
