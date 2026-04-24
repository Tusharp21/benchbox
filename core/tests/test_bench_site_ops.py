from __future__ import annotations

from pathlib import Path

import pytest

from benchbox_core.bench import (
    BenchSiteOperationError,
    backup_site,
    migrate_site,
    restore_site,
)
from benchbox_core.installer._run import CommandResult, CommandRunner


class CapturingRunner(CommandRunner):
    def __init__(self, *, returncode: int = 0) -> None:
        super().__init__(dry_run=False)
        self._returncode = returncode
        self.calls: list[tuple[tuple[str, ...], str | None]] = []

    def run(
        self,
        command: list[str] | tuple[str, ...],
        *,
        input: str | None = None,
        cwd: str | Path | None = None,
        check: bool = False,
        timeout: float | None = None,
    ) -> CommandResult:
        argv = tuple(command)
        self.calls.append((argv, str(cwd) if cwd is not None else None))
        stderr = "" if self._returncode == 0 else "boom"
        return CommandResult(argv, self._returncode, "", stderr, True)


# --- migrate -------------------------------------------------------


def test_migrate_site_argv_and_cwd(tmp_path: Path) -> None:
    runner = CapturingRunner()
    migrate_site(tmp_path / "bench", "site1.local", runner=runner)
    argv, cwd = runner.calls[0]
    assert argv == ("bench", "--site", "site1.local", "migrate")
    assert cwd == str(tmp_path / "bench")


def test_migrate_site_raises_on_failure(tmp_path: Path) -> None:
    runner = CapturingRunner(returncode=1)
    with pytest.raises(BenchSiteOperationError) as excinfo:
        migrate_site(tmp_path / "bench", "s.local", runner=runner)
    assert excinfo.value.operation == "migrate"


# --- backup --------------------------------------------------------


def test_backup_site_argv_shape(tmp_path: Path) -> None:
    runner = CapturingRunner()
    backup_site(tmp_path / "bench", "s.local", runner=runner)
    argv = runner.calls[0][0]
    assert argv == ("bench", "--site", "s.local", "backup")
    assert "--with-files" not in argv


def test_backup_site_with_files_flag(tmp_path: Path) -> None:
    runner = CapturingRunner()
    backup_site(tmp_path / "bench", "s.local", with_files=True, runner=runner)
    argv = runner.calls[0][0]
    assert "--with-files" in argv


def test_backup_site_raises_on_failure(tmp_path: Path) -> None:
    runner = CapturingRunner(returncode=1)
    with pytest.raises(BenchSiteOperationError) as excinfo:
        backup_site(tmp_path / "bench", "s.local", runner=runner)
    assert excinfo.value.operation == "backup"


# --- restore -------------------------------------------------------


def test_restore_site_argv_includes_sql_path_and_pw(tmp_path: Path) -> None:
    sql = tmp_path / "dump.sql"
    runner = CapturingRunner()
    restore_site(
        tmp_path / "bench",
        "s.local",
        sql_path=sql,
        db_root_password="root-pw",
        runner=runner,
    )
    argv = runner.calls[0][0]
    assert argv[:4] == ("bench", "--site", "s.local", "restore")
    assert argv[4] == str(sql)
    assert "--db-root-password" in argv
    assert argv[argv.index("--db-root-password") + 1] == "root-pw"


def test_restore_site_raises_on_failure(tmp_path: Path) -> None:
    runner = CapturingRunner(returncode=1)
    with pytest.raises(BenchSiteOperationError) as excinfo:
        restore_site(
            tmp_path / "bench",
            "s.local",
            sql_path=tmp_path / "d.sql",
            db_root_password="pw",
            runner=runner,
        )
    assert excinfo.value.operation == "restore"


def test_migrate_dry_run_reports_without_executing(tmp_path: Path) -> None:
    dry = CommandRunner(dry_run=True)
    result = migrate_site(tmp_path / "bench", "s.local", runner=dry)
    assert result.executed is False
