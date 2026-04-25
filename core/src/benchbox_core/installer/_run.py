"""Subprocess helper used by every installer component.

Wraps :mod:`subprocess` with:
- structured logging (every command + its output lands in the session log)
- a dry-run switch that records what *would* run without executing
- capture of stdout/stderr for later inspection

Components never call ``subprocess`` directly — they go through ``CommandRunner``
so the GUI/CLI can surface the same stream of events.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from benchbox_core.logs import get_logger

_log = get_logger(__name__)


def _nvm_node_bin() -> str | None:
    """Return the nvm-managed Node bin dir, or None if nvm isn't set up.

    Frappe's ``bench init`` calls yarn → node; if the inherited PATH only
    contains the apt-installed Node (12.22.9 on Ubuntu 22.04), bench bails
    with "engine node incompatible: expected >=18". We prepend the
    nvm-managed Node bin dir so every subprocess we spawn finds Node 18+
    regardless of whether the user sourced nvm in their shell.

    Prefers v18 (Frappe v15's required major). Falls back to the highest
    available major if no v18 is present.
    """
    nvm_versions = Path.home() / ".nvm" / "versions" / "node"
    if not nvm_versions.is_dir():
        return None
    v18 = sorted(nvm_versions.glob("v18.*"), reverse=True)
    candidates = v18 or sorted(nvm_versions.iterdir(), reverse=True)
    for candidate in candidates:
        node_bin = candidate / "bin"
        if (node_bin / "node").is_file():
            return str(node_bin)
    return None


def _build_subprocess_env() -> dict[str, str]:
    """Return an os.environ copy with nvm's Node prepended to PATH."""
    env = os.environ.copy()
    nvm_bin = _nvm_node_bin()
    if nvm_bin:
        path = env.get("PATH", "")
        if nvm_bin not in path.split(":"):
            env["PATH"] = f"{nvm_bin}:{path}" if path else nvm_bin
    return env


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

    ``quiet=True`` demotes the per-command "$ cmd / -> exit N" lines from
    INFO to DEBUG so they only land in the session log file, not on the
    console. Probe runners (dpkg-query, systemctl is-active, etc.) use this
    so the terminal shows mutations only and stays readable.
    """

    dry_run: bool = False
    quiet: bool = False
    _history: list[CommandResult] = field(default_factory=list, init=False, repr=False)

    @property
    def history(self) -> tuple[CommandResult, ...]:
        return tuple(self._history)

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
        pretty = shlex.join(argv)
        emit = _log.debug if self.quiet else _log.info

        if self.dry_run:
            stdin_suffix = " (with stdin)" if input is not None else ""
            cwd_suffix = f" [cwd={cwd}]" if cwd is not None else ""
            emit("[dry-run] %s%s%s", pretty, stdin_suffix, cwd_suffix)
            result = CommandResult(argv, 0, "", "", executed=False)
            self._history.append(result)
            return result

        cwd_suffix = f" [cwd={cwd}]" if cwd is not None else ""
        emit("$ %s%s", pretty, cwd_suffix)
        try:
            proc = subprocess.run(  # noqa: S603  # argv list, never shell=True
                argv,
                input=input,
                cwd=cwd,
                env=_build_subprocess_env(),
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

        # Surface the exit code at INFO so the session log always has at
        # least one post-command line per run; on failure, also mirror
        # stdout/stderr at INFO so users can see why without flipping to
        # DEBUG.
        if proc.returncode == 0:
            emit("  -> exit 0")
        else:
            # On a quiet (probe) runner, a non-zero exit is usually
            # informational (package not installed yet) — keep it at the
            # same level as the rest of the probe output. Loud runners log
            # failures at INFO and mirror stdout/stderr so users can see
            # why something broke without flipping to DEBUG.
            emit("  -> exit %d", proc.returncode)
            if not self.quiet:
                if proc.stdout:
                    _log.info("stdout: %s", proc.stdout.rstrip())
                if proc.stderr:
                    _log.info("stderr: %s", proc.stderr.rstrip())

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
