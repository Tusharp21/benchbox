"""App lifecycle (get, new, install, uninstall, remove)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from benchbox_core.installer._run import CommandResult, CommandRunner
from benchbox_core.introspect import AppInfo, read_apps


class AppOperationError(RuntimeError):
    def __init__(self, operation: str, result: CommandResult) -> None:
        super().__init__(
            f"`bench {operation}` failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip() or 'no output'}"
        )
        self.operation = operation
        self.result = result


@dataclass(frozen=True)
class GetAppResult:
    command: CommandResult
    apps: tuple[AppInfo, ...]


@dataclass(frozen=True)
class NewAppResult:
    command: CommandResult
    apps: tuple[AppInfo, ...]


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
    line_callback: Callable[[str], None] | None = None,
) -> GetAppResult:
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
    result = active.run(argv, cwd=bench_path, line_callback=line_callback)

    if not result.executed:
        return GetAppResult(command=result, apps=())

    if result.returncode != 0:
        raise AppOperationError("get-app", result)

    return GetAppResult(command=result, apps=tuple(read_apps(bench_path)))


# bench new-app prompts for: title, description, publisher, email, license.
_NEW_APP_LICENSE_DEFAULT: str = "MIT"


def new_app(
    bench_path: Path,
    app_name: str,
    *,
    title: str | None = None,
    description: str = "A new Frappe app",
    publisher: str = "benchbox",
    email: str = "dev@example.com",
    app_license: str = _NEW_APP_LICENSE_DEFAULT,
    runner: CommandRunner | None = None,
    line_callback: Callable[[str], None] | None = None,
) -> NewAppResult:
    if not app_name or not app_name.isidentifier() or not app_name.islower():
        raise ValueError(
            f"invalid app name {app_name!r}: must be lowercase, "
            "start with a letter, contain only letters/digits/underscores"
        )

    resolved_title = title or app_name.replace("_", " ").title()
    stdin_input = (
        f"{resolved_title}\n"
        f"{description}\n"
        f"{publisher}\n"
        f"{email}\n"
        f"{app_license}\n"
    )

    active = runner if runner is not None else CommandRunner()
    result = active.run(
        ["bench", "new-app", app_name],
        cwd=bench_path,
        input=stdin_input,
        line_callback=line_callback,
    )

    if not result.executed:
        return NewAppResult(command=result, apps=())

    if result.returncode != 0:
        raise AppOperationError("new-app", result)

    return NewAppResult(command=result, apps=tuple(read_apps(bench_path)))


def install_app(
    bench_path: Path,
    site_name: str,
    apps: Sequence[str],
    *,
    force: bool = False,
    runner: CommandRunner | None = None,
    line_callback: Callable[[str], None] | None = None,
) -> InstallAppResult:
    if not apps:
        raise ValueError("install_app requires at least one app name")

    argv: list[str] = ["bench", "--site", site_name, "install-app", *apps]
    if force:
        argv.append("--force")

    active = runner if runner is not None else CommandRunner()
    result = active.run(argv, cwd=bench_path, line_callback=line_callback)

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
