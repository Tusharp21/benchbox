"""App-level registry of running ``bench start`` processes.

The older design had ``BenchProcessPanel`` own its own :class:`QProcess`,
which meant:

- switching to a different bench → the previous bench got killed
  (``set_bench`` called ``stop``);
- going "back" from the detail view → same, because ``set_bench`` runs
  again when the user re-opens the bench;
- multiple concurrent benches → impossible, only one panel existed.

We lift process ownership into this module-level manager. Views subscribe
to its signals and ask it to start/stop by path. The manager's ``QProcess``
objects live as long as the app does (or until the user stops them),
so running benches survive any view navigation and several can run at once.

Thread-safety: everything here is main-thread only. QProcess itself is
thread-affine, so this must never be touched from a worker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal

# Max log lines to keep in memory per bench. Bench's honcho output is
# chatty; an unbounded buffer is a memory leak over a long-running
# session. 5000 lines ≈ 500 KB at 100 chars/line.
MAX_LOG_LINES: int = 5000

# Source nvm before exec'ing bench so Frappe's watch.1 finds Node 18;
# see the comment in bench_actions.py for the full story.
_NVM_BOOTSTRAP_SCRIPT: str = (
    'if [ -s "$HOME/.nvm/nvm.sh" ]; then '
    'export NVM_DIR="$HOME/.nvm"; '
    '. "$NVM_DIR/nvm.sh"; '
    "fi; "
    "exec bench start"
)


@dataclass
class _Entry:
    """Per-bench state held by the manager."""

    bench_path: Path
    process: QProcess
    status: str = "starting"
    log_lines: list[str] = field(default_factory=list)


class BenchProcessManager(QObject):
    """Owns every running bench's :class:`QProcess`.

    Signals fire on the main thread.

    ``process_started(Path)`` — a fresh process was spawned.
    ``process_stopped(Path, int)`` — process exited (exit code). The entry
    is already removed before the signal fires.
    ``output_appended(Path, str)`` — new stdout/stderr chunk.
    ``status_changed(Path, str)`` — human-readable status string.
    """

    process_started = Signal(Path)
    process_stopped = Signal(Path, int)
    output_appended = Signal(Path, str)
    status_changed = Signal(Path, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._entries: dict[Path, _Entry] = {}

    # --- public API ---------------------------------------------------

    def start(self, bench_path: Path) -> None:
        """Spawn ``bench start`` inside ``bench_path``. No-op if already running."""
        resolved = bench_path.resolve()
        if resolved in self._entries:
            return

        process = QProcess(self)
        process.setWorkingDirectory(str(resolved))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

        entry = _Entry(bench_path=resolved, process=process)
        self._entries[resolved] = entry

        # Capture `resolved` in the lambda so late-binding doesn't hand
        # the last loop iteration's path to every process's handler.
        process.readyReadStandardOutput.connect(lambda p=resolved: self._drain_output(p))
        process.finished.connect(lambda code, _status, p=resolved: self._on_finished(p, code))
        process.errorOccurred.connect(lambda _err, p=resolved: self._on_error(p))

        process.start("bash", ["-c", _NVM_BOOTSTRAP_SCRIPT])

        self.process_started.emit(resolved)
        self._set_status(resolved, "starting")

    def stop(self, bench_path: Path) -> None:
        """Ask a running bench to exit cleanly, then kill if it refuses."""
        resolved = bench_path.resolve()
        entry = self._entries.get(resolved)
        if entry is None:
            return
        self._set_status(resolved, "stopping…")
        entry.process.terminate()
        if not entry.process.waitForFinished(3000):
            entry.process.kill()
            entry.process.waitForFinished(1000)

    def is_running(self, bench_path: Path) -> bool:
        resolved = bench_path.resolve()
        entry = self._entries.get(resolved)
        if entry is None:
            return False
        return entry.process.state() != QProcess.ProcessState.NotRunning

    def running_paths(self) -> list[Path]:
        """Snapshot of every bench currently running, in dict-insertion order."""
        return [
            p
            for p, e in self._entries.items()
            if e.process.state() != QProcess.ProcessState.NotRunning
        ]

    def log_of(self, bench_path: Path) -> str:
        """Accumulated log, oldest lines first. Empty string if unknown."""
        resolved = bench_path.resolve()
        entry = self._entries.get(resolved)
        if entry is None:
            return ""
        return "\n".join(entry.log_lines)

    def status_of(self, bench_path: Path) -> str:
        resolved = bench_path.resolve()
        entry = self._entries.get(resolved)
        return entry.status if entry is not None else "stopped"

    def stop_all(self) -> None:
        """Best-effort stop every running bench — used during app shutdown."""
        for path in list(self._entries):
            self.stop(path)

    # --- QProcess handlers -------------------------------------------

    def _drain_output(self, bench_path: Path) -> None:
        entry = self._entries.get(bench_path)
        if entry is None:
            return
        raw = bytes(entry.process.readAllStandardOutput().data())
        if not raw:
            return
        text = raw.decode(errors="replace").rstrip("\n")
        if not text:
            return
        entry.log_lines.append(text)
        # Trim from the front when the buffer overflows. cheap because
        # Python lists are arrays — O(n) but only on overflow events.
        if len(entry.log_lines) > MAX_LOG_LINES:
            overflow = len(entry.log_lines) - MAX_LOG_LINES
            entry.log_lines = entry.log_lines[overflow:]
        self.output_appended.emit(bench_path, text)
        if entry.status != "running":
            self._set_status(bench_path, "running")

    def _on_finished(self, bench_path: Path, exit_code: int) -> None:
        entry = self._entries.pop(bench_path, None)
        if entry is None:
            return
        self.process_stopped.emit(bench_path, exit_code)
        # No _set_status here — the entry is gone; ``status_of`` returns
        # "stopped" for unknown paths.

    def _on_error(self, bench_path: Path) -> None:
        # Bench binary missing on PATH is the usual cause.
        entry = self._entries.pop(bench_path, None)
        if entry is None:
            return
        self.process_stopped.emit(bench_path, -1)

    def _set_status(self, bench_path: Path, status: str) -> None:
        entry = self._entries.get(bench_path)
        if entry is None:
            return
        entry.status = status
        self.status_changed.emit(bench_path, status)


__all__ = [
    "MAX_LOG_LINES",
    "BenchProcessManager",
]
