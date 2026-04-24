from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchbox_core.installer._run import CommandResult, CommandRunner
from benchbox_core.site import (
    SiteAlreadyExistsError,
    SiteNotFoundError,
    SiteOperationError,
    create_site,
    drop_site,
    restore_site,
)


class CapturingRunner(CommandRunner):
    """Test double: records every run() call including cwd, returns canned rc."""

    def __init__(self, *, returncode: int = 0, post_run: object | None = None) -> None:
        super().__init__(dry_run=False)
        self._returncode = returncode
        self._post_run = post_run
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
        if callable(self._post_run):
            self._post_run()
        stderr = "" if self._returncode == 0 else "boom"
        return CommandResult(argv, self._returncode, "", stderr, True)


def _make_bench_skeleton(path: Path) -> None:
    (path / "apps" / "frappe" / "frappe").mkdir(parents=True, exist_ok=True)
    (path / "apps" / "frappe" / "frappe" / "__init__.py").write_text(
        '__version__ = "15.0.0"\n', encoding="utf-8"
    )
    (path / "sites").mkdir(parents=True, exist_ok=True)
    (path / "sites" / "apps.txt").write_text("frappe\n", encoding="utf-8")
    (path / "sites" / "common_site_config.json").write_text("{}", encoding="utf-8")


def _make_site_dir(bench_path: Path, site_name: str) -> Path:
    site = bench_path / "sites" / site_name
    site.mkdir(parents=True, exist_ok=True)
    (site / "site_config.json").write_text(
        json.dumps({"db_name": f"_{site_name}"}), encoding="utf-8"
    )
    (site / "apps.txt").write_text("frappe\n", encoding="utf-8")
    return site


# --- create_site ---------------------------------------------------


def test_create_site_argv_shape(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(
        returncode=0,
        post_run=lambda: _make_site_dir(bench, "site1.local"),
    )

    create_site(
        bench,
        "site1.local",
        db_root_password="root-pw",
        admin_password="admin-pw",
        runner=runner,
    )

    argv, cwd = runner.calls[0]
    assert argv[:3] == ("bench", "new-site", "site1.local")
    assert "--db-root-password" in argv
    assert argv[argv.index("--db-root-password") + 1] == "root-pw"
    assert "--admin-password" in argv
    assert argv[argv.index("--admin-password") + 1] == "admin-pw"
    # cwd MUST be bench root — bench reads its bench_path from os.getcwd()
    assert cwd == str(bench)


def test_create_site_install_apps_repeats_flag(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(
        returncode=0,
        post_run=lambda: _make_site_dir(bench, "s.local"),
    )

    create_site(
        bench,
        "s.local",
        db_root_password="r",
        admin_password="a",
        install_apps=["erpnext", "hrms"],
        runner=runner,
    )

    argv = runner.calls[0][0]
    install_flags = [i for i, a in enumerate(argv) if a == "--install-app"]
    assert len(install_flags) == 2
    assert argv[install_flags[0] + 1] == "erpnext"
    assert argv[install_flags[1] + 1] == "hrms"


def test_create_site_raises_when_site_already_exists(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    _make_site_dir(bench, "exists.local")

    with pytest.raises(SiteAlreadyExistsError):
        create_site(
            bench,
            "exists.local",
            db_root_password="r",
            admin_password="a",
            runner=CapturingRunner(),
        )


def test_create_site_force_skips_the_existence_guard_and_adds_flag(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    _make_site_dir(bench, "existing.local")
    runner = CapturingRunner(returncode=0)

    create_site(
        bench,
        "existing.local",
        db_root_password="r",
        admin_password="a",
        force=True,
        runner=runner,
    )

    assert "--force" in runner.calls[0][0]


def test_create_site_set_default_adds_flag(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(
        returncode=0,
        post_run=lambda: _make_site_dir(bench, "s.local"),
    )

    create_site(
        bench,
        "s.local",
        db_root_password="r",
        admin_password="a",
        set_default=True,
        runner=runner,
    )

    assert "--set-default" in runner.calls[0][0]


def test_create_site_returns_populated_info_on_success(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(
        returncode=0,
        post_run=lambda: _make_site_dir(bench, "s.local"),
    )

    result = create_site(bench, "s.local", db_root_password="r", admin_password="a", runner=runner)

    assert result.info is not None
    assert result.info.name == "s.local"
    assert result.info.db_name == "_s.local"


def test_create_site_raises_on_nonzero_exit(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    runner = CapturingRunner(returncode=1)

    with pytest.raises(SiteOperationError) as excinfo:
        create_site(bench, "new.local", db_root_password="r", admin_password="a", runner=runner)

    assert excinfo.value.operation == "new-site"
    assert excinfo.value.result.returncode == 1


def test_create_site_dry_run_returns_none_info(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    dry = CommandRunner(dry_run=True)

    result = create_site(bench, "s.local", db_root_password="r", admin_password="a", runner=dry)

    assert result.command.executed is False
    assert result.info is None


# --- drop_site -----------------------------------------------------


def test_drop_site_argv_shape_and_cwd(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    _make_site_dir(bench, "doomed.local")
    runner = CapturingRunner(returncode=0)

    drop_site(bench, "doomed.local", db_root_password="root-pw", runner=runner)

    argv, cwd = runner.calls[0]
    assert argv[:3] == ("bench", "drop-site", "doomed.local")
    assert "--db-root-password" in argv
    assert argv[argv.index("--db-root-password") + 1] == "root-pw"
    assert cwd == str(bench)


def test_drop_site_flags(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    _make_site_dir(bench, "doomed.local")
    runner = CapturingRunner(returncode=0)

    drop_site(
        bench,
        "doomed.local",
        db_root_password="r",
        no_backup=True,
        force=True,
        runner=runner,
    )

    argv = runner.calls[0][0]
    assert "--no-backup" in argv
    assert "--force" in argv


def test_drop_site_raises_when_site_missing(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)

    with pytest.raises(SiteNotFoundError):
        drop_site(bench, "ghost.local", db_root_password="r", runner=CapturingRunner())


def test_drop_site_raises_on_nonzero_exit(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    _make_site_dir(bench, "doomed.local")
    runner = CapturingRunner(returncode=1)

    with pytest.raises(SiteOperationError) as excinfo:
        drop_site(bench, "doomed.local", db_root_password="r", runner=runner)
    assert excinfo.value.operation == "drop-site"


def test_drop_site_dry_run_skips_existence_guard(tmp_path: Path) -> None:
    # Dry-run is useful for CLI --dry-run previews even if the site isn't
    # there yet. We deliberately don't raise SiteNotFoundError in that mode.
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    dry = CommandRunner(dry_run=True)

    result = drop_site(bench, "ghost.local", db_root_password="r", runner=dry)
    assert result.command.executed is False


# --- restore_site --------------------------------------------------


def _make_sql_file(path: Path) -> Path:
    path.write_bytes(b"-- fake sql dump\n")
    return path


def test_restore_site_argv_shape_and_cwd(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    _make_site_dir(bench, "s.local")
    sql = _make_sql_file(tmp_path / "backup.sql.gz")
    runner = CapturingRunner(returncode=0)

    restore_site(bench, "s.local", sql, db_root_password="root-pw", runner=runner)

    argv, cwd = runner.calls[0]
    assert argv[:5] == ("bench", "--site", "s.local", "restore", str(sql))
    assert "--db-root-password" in argv
    assert argv[argv.index("--db-root-password") + 1] == "root-pw"
    assert cwd == str(bench)


def test_restore_site_optional_flags(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    _make_site_dir(bench, "s.local")
    sql = _make_sql_file(tmp_path / "backup.sql.gz")
    pub = _make_sql_file(tmp_path / "files.tar")
    priv = _make_sql_file(tmp_path / "private-files.tar")
    runner = CapturingRunner(returncode=0)

    restore_site(
        bench,
        "s.local",
        sql,
        db_root_password="r",
        admin_password="new-admin",
        with_public_files=pub,
        with_private_files=priv,
        force=True,
        runner=runner,
    )

    argv = runner.calls[0][0]
    assert "--admin-password" in argv
    assert argv[argv.index("--admin-password") + 1] == "new-admin"
    assert "--with-public-files" in argv
    assert argv[argv.index("--with-public-files") + 1] == str(pub)
    assert "--with-private-files" in argv
    assert argv[argv.index("--with-private-files") + 1] == str(priv)
    assert "--force" in argv


def test_restore_site_raises_when_site_missing(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    sql = _make_sql_file(tmp_path / "backup.sql")

    with pytest.raises(SiteNotFoundError):
        restore_site(bench, "ghost.local", sql, db_root_password="r", runner=CapturingRunner())


def test_restore_site_raises_when_backup_missing(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    _make_site_dir(bench, "s.local")

    with pytest.raises(FileNotFoundError):
        restore_site(
            bench,
            "s.local",
            tmp_path / "nope.sql",
            db_root_password="r",
            runner=CapturingRunner(),
        )


def test_restore_site_raises_on_nonzero_exit(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    _make_bench_skeleton(bench)
    _make_site_dir(bench, "s.local")
    sql = _make_sql_file(tmp_path / "backup.sql")
    runner = CapturingRunner(returncode=1)

    with pytest.raises(SiteOperationError) as excinfo:
        restore_site(bench, "s.local", sql, db_root_password="r", runner=runner)
    assert excinfo.value.operation == "restore"
