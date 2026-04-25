"""Bench lifecycle operations — create, (later) destroy.

This module wraps the upstream ``bench`` CLI's per-bench operations. It
treats an "operation" as a single ``CommandRunner`` invocation plus
pre- and post-condition checks, and returns structured results so both
the CLI and GUI can surface progress the same way.

Site creation and app operations live in :mod:`benchbox_core.site` and
:mod:`benchbox_core.app` respectively — keeping each file's scope narrow
makes it easier to grow the operation catalogue without the module
becoming a grab-bag.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from benchbox_core.discovery import is_bench
from benchbox_core.installer._run import CommandResult, CommandRunner
from benchbox_core.introspect import BenchInfo, introspect

DEFAULT_FRAPPE_BRANCH: str = "version-15"
DEFAULT_PYTHON_BIN: str = "python3"


class BenchAlreadyExistsError(RuntimeError):
    """Raised when ``create_bench`` would overwrite an existing bench."""


class BenchCreationError(RuntimeError):
    """Raised when ``bench init`` exits non-zero."""

    def __init__(self, result: CommandResult) -> None:
        super().__init__(
            f"`bench init` failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip() or 'no output'}"
        )
        self.result = result


@dataclass(frozen=True)
class BenchCreateResult:
    """Outcome of ``create_bench``. ``info`` is ``None`` on dry-run."""

    command: CommandResult
    info: BenchInfo | None


def create_bench(
    path: Path,
    *,
    frappe_branch: str = DEFAULT_FRAPPE_BRANCH,
    python_bin: str = DEFAULT_PYTHON_BIN,
    runner: CommandRunner | None = None,
) -> BenchCreateResult:
    """Run ``bench init`` at ``path`` and return an introspected BenchInfo.

    Raises ``BenchAlreadyExistsError`` if ``path`` already exists in any
    form — bench's CLI refuses to populate an existing directory but exits
    *0* with an "ERROR: Bench instance already exists" line on stdout, so
    we have to gate this ourselves rather than trust the exit code. On
    a dry-run runner we skip the pre/post-condition work and return
    ``info=None`` — the caller can still read the command shape off
    ``result.command``.
    """
    if path.exists():
        if is_bench(path):
            raise BenchAlreadyExistsError(f"{path} already contains a Frappe bench")
        raise BenchAlreadyExistsError(
            f"{path} already exists; bench init refuses to populate an "
            f"existing directory. Pick a path that doesn't exist yet."
        )

    active = runner if runner is not None else CommandRunner()

    result = active.run(
        [
            "bench",
            "init",
            str(path),
            "--frappe-branch",
            frappe_branch,
            "--python",
            python_bin,
        ],
    )

    if not result.executed:
        # Dry-run path — nothing to introspect.
        return BenchCreateResult(command=result, info=None)

    if result.returncode != 0:
        raise BenchCreationError(result)

    # bench's CLI sometimes reports success while having done nothing
    # (e.g. a stdout "ERROR: ..." that the wrapper turns into exit 0).
    # Verify the bench was actually created before claiming success.
    if not is_bench(path):
        raise BenchCreationError(result)

    return BenchCreateResult(command=result, info=introspect(path))


# --- per-site ops (migrate / backup / restore) --------------------------


class BenchSiteOperationError(RuntimeError):
    """Raised when a wrapped per-site ``bench`` command exits non-zero."""

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
    """Run ``bench --site <site> migrate``; re-applies schema changes.

    Typical after ``bench get-app`` of a new version. Raises on non-zero
    exit; returns the :class:`CommandResult` on success (or dry-run).
    """
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
    """Run ``bench --site <site> backup [--with-files]``.

    Produces a DB dump under ``<bench>/sites/<site>/private/backups/`` and
    (with ``with_files=True``) tars the site's public+private files too.
    """
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
    """Run ``bench --site <site> restore <sql_path> --db-root-password <pw>``.

    Overwrites the site's DB with the supplied dump. Admin password on the
    restored site stays whatever it was at dump time — adjust via
    ``bench set-admin-password`` after if you need a fresh one.
    """
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
