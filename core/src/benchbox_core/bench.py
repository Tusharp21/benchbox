"""Bench lifecycle and per-site bench commands."""

from __future__ import annotations

import shlex
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from benchbox_core.discovery import is_bench
from benchbox_core.installer._run import CommandResult, CommandRunner
from benchbox_core.introspect import BenchInfo, introspect

DEFAULT_FRAPPE_BRANCH: str = "version-15"
DEFAULT_PYTHON_BIN: str = "python3"
# Match ``installer.node.NodeComponent.nvm_dir`` so the wrapper script
# sources the same nvm install that benchbox provisioned.
DEFAULT_NVM_DIR: Path = Path.home() / ".nvm"


def _bench_init_via_nvm(
    path: Path,
    frappe_branch: str,
    python_bin: str,
    node_major: str,
    nvm_dir: Path,
) -> tuple[str, ...]:
    """Build a ``bash -lc`` invocation that sources nvm and runs ``bench init``.

    Wrapping is needed when the GUI's parent shell doesn't have the right
    Node major active — e.g. user installed Node 24 for Frappe v16 but
    launched benchbox from a terminal where ``nvm use 18`` was last
    called. ``bash -lc`` runs a login shell so ``~/.profile`` (where nvm
    and pipx put their PATH entries) is sourced.
    """
    script = (
        f"export NVM_DIR={shlex.quote(str(nvm_dir))}"
        f' && . "$NVM_DIR/nvm.sh"'
        f" && nvm use {shlex.quote(node_major)}"
        f" && bench init {shlex.quote(str(path))}"
        f" --frappe-branch {shlex.quote(frappe_branch)}"
        f" --python {shlex.quote(python_bin)}"
    )
    return ("bash", "-lc", script)


class BenchAlreadyExistsError(RuntimeError):
    pass


class BenchCreationError(RuntimeError):
    def __init__(self, result: CommandResult) -> None:
        super().__init__(
            f"`bench init` failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip() or 'no output'}"
        )
        self.result = result


@dataclass(frozen=True)
class BenchCreateResult:
    command: CommandResult
    info: BenchInfo | None


def create_bench(
    path: Path,
    *,
    frappe_branch: str = DEFAULT_FRAPPE_BRANCH,
    python_bin: str = DEFAULT_PYTHON_BIN,
    node_major: str | None = None,
    nvm_dir: Path | None = None,
    runner: CommandRunner | None = None,
    line_callback: Callable[[str], None] | None = None,
) -> BenchCreateResult:
    # bench init refuses to populate an existing directory but exits 0 with
    # an error message on stdout, so we gate this ourselves.
    if path.exists():
        if is_bench(path):
            raise BenchAlreadyExistsError(f"{path} already contains a Frappe bench")
        raise BenchAlreadyExistsError(
            f"{path} already exists; bench init refuses to populate an "
            f"existing directory. Pick a path that doesn't exist yet."
        )

    active = runner if runner is not None else CommandRunner()

    if node_major:
        command: tuple[str, ...] | list[str] = _bench_init_via_nvm(
            path=path,
            frappe_branch=frappe_branch,
            python_bin=python_bin,
            node_major=node_major,
            nvm_dir=nvm_dir or DEFAULT_NVM_DIR,
        )
    else:
        command = [
            "bench",
            "init",
            str(path),
            "--frappe-branch",
            frappe_branch,
            "--python",
            python_bin,
        ]

    result = active.run(command, line_callback=line_callback)

    if not result.executed:
        return BenchCreateResult(command=result, info=None)

    if result.returncode != 0:
        raise BenchCreationError(result)

    # bench sometimes reports exit 0 with an error on stdout; verify.
    if not is_bench(path):
        raise BenchCreationError(result)

    return BenchCreateResult(command=result, info=introspect(path))


# --- per-site ops (migrate / backup / restore) --------------------------


class BenchSiteOperationError(RuntimeError):
    def __init__(self, operation: str, result: CommandResult) -> None:
        super().__init__(
            f"`bench {operation}` failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip() or 'no output'}"
        )
        self.operation = operation
        self.result = result


def migrate_site(
    bench_path: Path,
    site_name: str,
    *,
    runner: CommandRunner | None = None,
) -> CommandResult:
    active = runner if runner is not None else CommandRunner()
    result = active.run(
        ["bench", "--site", site_name, "migrate"],
        cwd=bench_path,
    )
    if result.executed and result.returncode != 0:
        raise BenchSiteOperationError("migrate", result)
    return result


def backup_site(
    bench_path: Path,
    site_name: str,
    *,
    with_files: bool = False,
    runner: CommandRunner | None = None,
) -> CommandResult:
    active = runner if runner is not None else CommandRunner()
    argv: list[str] = ["bench", "--site", site_name, "backup"]
    if with_files:
        argv.append("--with-files")
    result = active.run(argv, cwd=bench_path)
    if result.executed and result.returncode != 0:
        raise BenchSiteOperationError("backup", result)
    return result


def restore_site(
    bench_path: Path,
    site_name: str,
    *,
    sql_path: Path,
    db_root_password: str,
    runner: CommandRunner | None = None,
) -> CommandResult:
    active = runner if runner is not None else CommandRunner()
    argv: list[str] = [
        "bench",
        "--site",
        site_name,
        "restore",
        str(sql_path),
        "--db-root-password",
        db_root_password,
    ]
    result = active.run(argv, cwd=bench_path)
    if result.executed and result.returncode != 0:
        raise BenchSiteOperationError("restore", result)
    return result
