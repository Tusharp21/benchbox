from __future__ import annotations

from pathlib import Path

import pytest
from benchbox_core import credentials
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


def _recording_runner(captured: list[tuple[tuple[str, ...], object]]) -> object:
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
        return CommandResult(tuple(command), 0, "", "", True)

    return fake_run


def _failing_runner(code: int = 1) -> object:
    def fake_run(
        self: CommandRunner,
        command: list[str] | tuple[str, ...],
        **kw: object,
    ) -> CommandResult:
        return CommandResult(tuple(command), code, "", "boom", True)

    return fake_run


@pytest.fixture
def cli() -> CliRunner:
    return CliRunner()


@pytest.fixture
def bench_path(tmp_path: Path) -> Path:
    bench = tmp_path / "bench"
    _make_bench(bench)
    return bench


# --- migrate -------------------------------------------------------


def test_bench_migrate_argv(
    cli: CliRunner, bench_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[tuple[tuple[str, ...], object]] = []
    monkeypatch.setattr(CommandRunner, "run", _recording_runner(captured))
    result = cli.invoke(app, ["bench", "migrate", str(bench_path), "s.local"])
    assert result.exit_code == 0
    argv, cwd = captured[0]
    assert argv == ("bench", "--site", "s.local", "migrate")
    assert str(cwd) == str(bench_path)


def test_bench_migrate_failure(
    cli: CliRunner, bench_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(CommandRunner, "run", _failing_runner())
    result = cli.invoke(app, ["bench", "migrate", str(bench_path), "s.local"])
    assert result.exit_code == 1


# --- backup --------------------------------------------------------


def test_bench_backup_with_files_flag(
    cli: CliRunner, bench_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[tuple[tuple[str, ...], object]] = []
    monkeypatch.setattr(CommandRunner, "run", _recording_runner(captured))
    result = cli.invoke(app, ["bench", "backup", str(bench_path), "s.local", "--with-files"])
    assert result.exit_code == 0
    argv = captured[0][0]
    assert "--with-files" in argv


# --- restore -------------------------------------------------------


def test_bench_restore_requires_stored_password(
    cli: CliRunner,
    bench_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Point credentials at empty tmp dir so no password is found.
    monkeypatch.setenv("BENCHBOX_CONFIG_DIR", str(tmp_path / "config"))
    sql = tmp_path / "dump.sql"
    sql.write_text("-- empty", encoding="utf-8")
    result = cli.invoke(app, ["bench", "restore", str(bench_path), "s.local", "--sql", str(sql)])
    assert result.exit_code == 2  # bail with a clear message


def test_bench_restore_forwards_stored_password(
    cli: CliRunner,
    bench_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BENCHBOX_CONFIG_DIR", str(tmp_path / "config"))
    credentials.set_mariadb_root_password("stored-pw")
    sql = tmp_path / "dump.sql"
    sql.write_text("-- empty", encoding="utf-8")

    captured: list[tuple[tuple[str, ...], object]] = []
    monkeypatch.setattr(CommandRunner, "run", _recording_runner(captured))

    result = cli.invoke(app, ["bench", "restore", str(bench_path), "s.local", "--sql", str(sql)])
    assert result.exit_code == 0
    argv = captured[0][0]
    assert argv[:4] == ("bench", "--site", "s.local", "restore")
    assert argv[4] == str(sql)
    assert argv[argv.index("--db-root-password") + 1] == "stored-pw"


def test_upgrade_command_shows_url(cli: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_system(cmd: str) -> int:
        calls.append(cmd)
        return 0

    monkeypatch.setattr("benchbox_cli.upgrade.os.system", fake_system)

    result = cli.invoke(app, ["upgrade", "--url", "https://example.com/install.sh"])
    assert result.exit_code == 0
    # os.system was called with a bash pipeline that includes our URL.
    assert any("example.com/install.sh" in c for c in calls)
