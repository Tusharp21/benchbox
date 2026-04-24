"""Subprocess helper used by every installer component.

Wraps :mod:`subprocess` with:
- structured logging (every command + its output lands in the session log)
- a dry-run switch that records what *would* run without executing
- capture of stdout/stderr for later inspection

Components never call ``subprocess`` directly — they go through ``CommandRunner``
so the GUI/CLI can surface the same stream of events.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass, field

from benchbox_core.logs import get_logger

_log = get_logger(__name__)


@dataclass(frozen=True)
class CommandResult:
    """Outcome of a single command execution."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    executed: bool  # False when the runner is in dry-run mode

    @property
    def ok(self) -> bool:
        return self.executed and self.returncode == 0


@dataclass
class CommandRunner:
    """Executes argv lists; records everything through the benchbox logger.

    Default behaviour captures stdout/stderr and returns them on the result.
    In dry-run mode, commands are logged but never spawned — the returncode
    is reported as 0 and ``executed`` is False.
    """

    dry_run: bool = False
    _history: list[CommandResult] = field(default_factory=list, init=False, repr=False)

    @property
    def history(self) -> tuple[CommandResult, ...]:
        return tuple(self._history)

    def run(
        self,
        command: list[str] | tuple[str, ...],
        *,
        check: bool = False,
        timeout: float | None = None,
    ) -> CommandResult:
        argv = tuple(command)
        pretty = shlex.join(argv)

        if self.dry_run:
            _log.info("[dry-run] %s", pretty)
            result = CommandResult(argv, 0, "", "", executed=False)
            self._history.append(result)
            return result

        _log.info("$ %s", pretty)
        try:
            proc = subprocess.run(  # noqa: S603  # argv list, never shell=True
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as err:
            result = CommandResult(argv, 127, "", str(err), executed=True)
            self._history.append(result)
            if check:
                raise
            return result
        except subprocess.TimeoutExpired as err:
            stderr = err.stderr.decode() if isinstance(err.stderr, bytes) else (err.stderr or "")
            result = CommandResult(argv, 124, "", f"timeout after {timeout}s: {stderr}", True)
            self._history.append(result)
            if check:
                raise
            return result

        if proc.stdout:
            _log.debug("stdout: %s", proc.stdout.rstrip())
        if proc.stderr:
            _log.debug("stderr: %s", proc.stderr.rstrip())

        result = CommandResult(
            command=argv,
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            executed=True,
        )
        self._history.append(result)
        if check and proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, argv, proc.stdout, proc.stderr)
        return result
