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

    Raises ``BenchAlreadyExistsError`` if ``path`` already looks like a bench
    directory, and ``BenchCreationError`` if the CLI call itself fails. On
    a dry-run runner we skip the pre/post-condition work and return
    ``info=None`` — the caller can still read the command shape off
    ``result.command``.
    """
    if is_bench(path):
        raise BenchAlreadyExistsError(f"{path} already contains a Frappe bench")

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

    return BenchCreateResult(command=result, info=introspect(path))
