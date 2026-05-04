"""Site lifecycle (new-site, drop-site)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from benchbox_core.installer._run import CommandResult, CommandRunner
from benchbox_core.introspect import SiteInfo, read_sites


class SiteAlreadyExistsError(RuntimeError):
    pass


class SiteNotFoundError(RuntimeError):
    pass


class SiteOperationError(RuntimeError):
    def __init__(self, operation: str, result: CommandResult) -> None:
        super().__init__(
            f"`bench {operation}` failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip() or 'no output'}"
        )
        self.operation = operation
        self.result = result


@dataclass(frozen=True)
class SiteCreateResult:
    command: CommandResult
    info: SiteInfo | None


@dataclass(frozen=True)
class SiteDropResult:
    command: CommandResult


@dataclass(frozen=True)
class SiteRestoreResult:
    command: CommandResult


def _site_dir(bench_path: Path, site_name: str) -> Path:
    return bench_path / "sites" / site_name


def create_site(
    bench_path: Path,
    site_name: str,
    *,
    db_root_password: str,
    admin_password: str,
    install_apps: Sequence[str] = (),
    force: bool = False,
    set_default: bool = False,
    runner: CommandRunner | None = None,
    line_callback: Callable[[str], None] | None = None,
) -> SiteCreateResult:
    if not force and _site_dir(bench_path, site_name).is_dir():
        raise SiteAlreadyExistsError(f"site {site_name!r} already exists under {bench_path}")

    argv: list[str] = [
        "bench",
        "new-site",
        site_name,
        "--db-root-password",
        db_root_password,
        "--admin-password",
        admin_password,
    ]
    for app in install_apps:
        argv.extend(["--install-app", app])
    if force:
        argv.append("--force")
    if set_default:
        argv.append("--set-default")

    active = runner if runner is not None else CommandRunner()
    result = active.run(argv, cwd=bench_path, line_callback=line_callback)

    if not result.executed:
        return SiteCreateResult(command=result, info=None)

    if result.returncode != 0:
        raise SiteOperationError("new-site", result)

    info = next(
        (s for s in read_sites(bench_path) if s.name == site_name),
        None,
    )
    return SiteCreateResult(command=result, info=info)


def drop_site(
    bench_path: Path,
    site_name: str,
    *,
    db_root_password: str,
    no_backup: bool = False,
    force: bool = False,
    runner: CommandRunner | None = None,
) -> SiteDropResult:
    active = runner if runner is not None else CommandRunner()

    if not active.dry_run and not _site_dir(bench_path, site_name).is_dir():
        raise SiteNotFoundError(f"site {site_name!r} not found under {bench_path}")

    argv: list[str] = [
        "bench",
        "drop-site",
        site_name,
        "--db-root-password",
        db_root_password,
    ]
    if no_backup:
        argv.append("--no-backup")
    if force:
        argv.append("--force")

    result = active.run(argv, cwd=bench_path)

    if result.executed and result.returncode != 0:
        raise SiteOperationError("drop-site", result)

    return SiteDropResult(command=result)


def restore_site(
    bench_path: Path,
    site_name: str,
    sql_path: Path,
    *,
    db_root_password: str,
    admin_password: str | None = None,
    with_public_files: Path | None = None,
    with_private_files: Path | None = None,
    force: bool = False,
    runner: CommandRunner | None = None,
    line_callback: Callable[[str], None] | None = None,
) -> SiteRestoreResult:
    active = runner if runner is not None else CommandRunner()

    if not active.dry_run and not _site_dir(bench_path, site_name).is_dir():
        raise SiteNotFoundError(f"site {site_name!r} not found under {bench_path}")
    if not active.dry_run and not Path(sql_path).is_file():
        raise FileNotFoundError(f"backup file not found: {sql_path}")

    argv: list[str] = [
        "bench",
        "--site",
        site_name,
        "restore",
        str(sql_path),
        "--db-root-password",
        db_root_password,
    ]
    if admin_password:
        argv.extend(["--admin-password", admin_password])
    if with_public_files is not None:
        argv.extend(["--with-public-files", str(with_public_files)])
    if with_private_files is not None:
        argv.extend(["--with-private-files", str(with_private_files)])
    if force:
        argv.append("--force")

    result = active.run(argv, cwd=bench_path, line_callback=line_callback)

    if result.executed and result.returncode != 0:
        raise SiteOperationError("restore", result)

    return SiteRestoreResult(command=result)
