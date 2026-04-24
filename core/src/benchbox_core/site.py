"""Site lifecycle operations — create, drop.

Wraps ``bench new-site`` and ``bench drop-site``. Both of those resolve the
bench they operate on from ``os.getcwd()``, so every call here sets
``cwd=bench_path`` explicitly rather than forcing the caller to ``chdir``.

Passwords (MariaDB root, new Administrator) are accepted as arguments and
passed on the ``bench`` argv. This does mean they land in ``ps aux`` for
the lifetime of the subprocess; for fully secret-safe behaviour a caller
can alternatively pre-write ``sites/common_site_config.json`` with a
``mariadb_root_password`` key and omit the flag (bench reads it from
there). For benchbox's local-dev scope the argv path is the simpler
default.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from benchbox_core.installer._run import CommandResult, CommandRunner
from benchbox_core.introspect import SiteInfo, read_sites


class SiteAlreadyExistsError(RuntimeError):
    """Raised when ``create_site`` would collide with an existing site dir."""


class SiteNotFoundError(RuntimeError):
    """Raised when ``drop_site`` targets a site that isn't present."""


class SiteOperationError(RuntimeError):
    """Raised when the wrapped ``bench`` command exits non-zero."""

    def __init__(self, operation: str, result: CommandResult) -> None:
        super().__init__(
            f"`bench {operation}` failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip() or 'no output'}"
        )
        self.operation = operation
        self.result = result


@dataclass(frozen=True)
class SiteCreateResult:
    """Outcome of ``create_site``. ``info`` is ``None`` on dry-run."""

    command: CommandResult
    info: SiteInfo | None


@dataclass(frozen=True)
class SiteDropResult:
    """Outcome of ``drop_site``."""

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
) -> SiteCreateResult:
    """Run ``bench new-site`` inside ``bench_path`` and return a SiteInfo.

    ``force`` maps to bench's ``--force`` (overwrite an existing site). When
    False, we guard up front with ``SiteAlreadyExistsError`` so callers get
    a clear error before the subprocess is even spawned.
    """
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
    result = active.run(argv, cwd=bench_path)

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
    """Run ``bench drop-site`` inside ``bench_path``.

    Raises ``SiteNotFoundError`` if the site dir doesn't exist when not in
    dry-run mode, so callers don't waste a subprocess on a typo.
    """
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
