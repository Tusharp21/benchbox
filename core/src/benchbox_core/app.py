"""App lifecycle operations — get, install, uninstall.

Thin wrappers around three ``bench`` subcommands:
- ``bench get-app <git-url>`` — clones and pip-installs an app into the
  bench's virtualenv; does NOT install it onto any site.
- ``bench --site <name> install-app <app> [<app>...]`` — installs one or
  more already-downloaded apps onto a specific site. ``--site`` is a
  *global* bench flag (before the subcommand), not a flag on install-app.
- ``bench --site <name> uninstall-app <app>`` — removes an app from a
  site. Single-app only; callers needing to drop several should loop.

All three subcommands resolve their bench_path from ``os.getcwd()``, so we
always pass ``cwd=bench_path`` on the runner.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from benchbox_core.installer._run import CommandResult, CommandRunner
from benchbox_core.introspect import AppInfo, read_apps


class AppOperationError(RuntimeError):
    """Raised when a wrapped ``bench`` app command exits non-zero."""

    def __init__(self, operation: str, result: CommandResult) -> None:
        super().__init__(
            f"`bench {operation}` failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip() or 'no output'}"
        )
        self.operation = operation
        self.result = result


@dataclass(frozen=True)
class GetAppResult:
    """Outcome of ``get_app``. ``app`` is None on dry-run or when the app
    can't be located in ``apps/`` after success (unusual — usually means
    the git URL gave an app whose folder name differs from its click name)."""

    command: CommandResult
    apps: tuple[AppInfo, ...]  # full apps list after the get


@dataclass(frozen=True)
class InstallAppResult:
    command: CommandResult


@dataclass(frozen=True)
class UninstallAppResult:
    command: CommandResult


@dataclass(frozen=True)
class RemoveAppResult:
    command: CommandResult


def get_app(
    bench_path: Path,
    git_url: str,
    *,
    branch: str | None = None,
    overwrite: bool = False,
    skip_assets: bool = False,
    resolve_deps: bool = False,
    runner: CommandRunner | None = None,
) -> GetAppResult:
    """Run ``bench get-app`` inside ``bench_path``.

    Downloads the app and pip-installs it into the bench's venv. Use
    ``install_app`` afterwards to install the app on a specific site.
    """
    argv: list[str] = ["bench", "get-app", git_url]
    if branch is not None:
        argv.extend(["--branch", branch])
    if overwrite:
        argv.append("--overwrite")
    if skip_assets:
        argv.append("--skip-assets")
    if resolve_deps:
        argv.append("--resolve-deps")

    active = runner if runner is not None else CommandRunner()
    result = active.run(argv, cwd=bench_path)

    if not result.executed:
        return GetAppResult(command=result, apps=())

    if result.returncode != 0:
        raise AppOperationError("get-app", result)

    return GetAppResult(command=result, apps=tuple(read_apps(bench_path)))


def install_app(
    bench_path: Path,
    site_name: str,
    apps: Sequence[str],
    *,
    force: bool = False,
    runner: CommandRunner | None = None,
) -> InstallAppResult:
    """Install one or more apps onto ``site_name`` via ``bench install-app``.

    ``--site`` is a *global* bench option (before the subcommand), so the
    argv is ``bench --site <name> install-app <app> [<app>...]`` — not a
    flag on install-app itself.
    """
    if not apps:
        raise ValueError("install_app requires at least one app name")

    argv: list[str] = ["bench", "--site", site_name, "install-app", *apps]
    if force:
        argv.append("--force")

    active = runner if runner is not None else CommandRunner()
    result = active.run(argv, cwd=bench_path)

    if result.executed and result.returncode != 0:
        raise AppOperationError("install-app", result)

    return InstallAppResult(command=result)


def uninstall_app(
    bench_path: Path,
    site_name: str,
    app: str,
    *,
    yes: bool = True,
    no_backup: bool = False,
    force: bool = False,
    runner: CommandRunner | None = None,
) -> UninstallAppResult:
    """Remove ``app`` from ``site_name`` via ``bench uninstall-app``.

    ``yes`` defaults to True because the interactive prompt would hang a
    non-TTY subprocess. Set ``no_backup=True`` to skip the default pre-drop
    backup when you know you don't need it.
    """
    argv: list[str] = ["bench", "--site", site_name, "uninstall-app", app]
    if yes:
        argv.append("--yes")
    if no_backup:
        argv.append("--no-backup")
    if force:
        argv.append("--force")

    active = runner if runner is not None else CommandRunner()
    result = active.run(argv, cwd=bench_path)

    if result.executed and result.returncode != 0:
        raise AppOperationError("uninstall-app", result)

    return UninstallAppResult(command=result)


def remove_app(
    bench_path: Path,
    app: str,
    *,
    no_backup: bool = False,
    force: bool = False,
    runner: CommandRunner | None = None,
) -> RemoveAppResult:
    """Remove ``app`` from a bench's ``apps/`` directory via ``bench remove-app``.

    Distinct from :func:`uninstall_app` — that only detaches an app from a
    specific site's DB. ``remove_app`` yanks the whole app out of the bench
    so ``bench get-app`` is what gets it back. ``bench remove-app`` will
    refuse to run while any site still has the app installed unless
    ``force=True``.
    """
    argv: list[str] = ["bench", "remove-app", app]
    if no_backup:
        argv.append("--no-backup")
    if force:
        argv.append("--force")

    active = runner if runner is not None else CommandRunner()
    result = active.run(argv, cwd=bench_path)

    if result.executed and result.returncode != 0:
        raise AppOperationError("remove-app", result)

    return RemoveAppResult(command=result)
