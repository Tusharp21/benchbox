"""App-level registry of running bench-start processes.

Main-thread only — QProcess is thread-affine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal

# Cap log buffer per bench to keep long-running sessions from leaking memory.
MAX_LOG_LINES: int = 5000

# Source nvm before exec so Frappe sees Node 18, not the apt-shipped Node 12.
_NVM_BOOTSTRAP_SCRIPT: str = (
    'if [ -s "$HOME/.nvm/nvm.sh" ]; then '
    'export NVM_DIR="$HOME/.nvm"; '
    '. "$NVM_DIR/nvm.sh"; '
    "fi; "
    "exec bench start"
)


@dataclass
class _Entry:
    bench_path: Path
    process: QProcess
    status: str = "starting"
    log_lines: list[str] = field(default_factory=list)


class BenchProcessManager(QObject):
    process_started = Signal(Path)
    process_stopped = Signal(Path, int)
    output_appended = Signal(Path, str)
    status_changed = Signal(Path, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._entries: dict[Path, _Entry] = {}

    # --- public API ---------------------------------------------------

    def start(self, bench_path: Path) -> None:
        resolved = bench_path.resolve()
        if resolved in self._entries:
            return

        process = QProcess(self)
        process.setWorkingDirectory(str(resolved))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

        entry = _Entry(bench_path=resolved, process=process)
        self._entries[resolved] = entry

        # Bind `resolved` per-lambda so late-binding doesn't share state.
        process.readyReadStandardOutput.connect(lambda p=resolved: self._drain_output(p))
        process.finished.connect(lambda code, _status, p=resolved: self._on_finished(p, code))
        process.errorOccurred.connect(lambda _err, p=resolved: self._on_error(p))

        process.start("bash", ["-c", _NVM_BOOTSTRAP_SCRIPT])

        self.process_started.emit(resolved)
        self._set_status(resolved, "starting")

    def stop(self, bench_path: Path) -> None:
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
        return [
            p
            for p, e in self._entries.items()
            if e.process.state() != QProcess.ProcessState.NotRunning
        ]

    def log_of(self, bench_path: Path) -> str:
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

    def _on_error(self, bench_path: Path) -> None:
        # Usually means the bench binary isn't on PATH.
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
