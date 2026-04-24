"""Top stats banner — polls :func:`benchbox_core.stats.snapshot` on a timer."""

from __future__ import annotations

from benchbox_core import stats
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

_GB: int = 1024**3
DEFAULT_POLL_MS: int = 2000


class StatsBanner(QWidget):
    """Horizontal strip: CPU, RAM, disk, service-status dots.

    Emits ``snapshot_ready(SystemStats)`` on every tick so tests (and any
    other widget that wants the raw numbers) can hook in without reaching
    through the widget tree.
    """

    snapshot_ready = Signal(object)

    def __init__(self, parent: QWidget | None = None, *, poll_ms: int = DEFAULT_POLL_MS) -> None:
        super().__init__(parent)
        self._cpu = QLabel("cpu —")
        self._ram = QLabel("ram —")
        self._disk = QLabel("disk —")
        self._services = QLabel("services —")
        for lbl in (self._cpu, self._ram, self._disk, self._services):
            lbl.setMinimumWidth(140)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(24)
        layout.addWidget(self._cpu)
        layout.addWidget(self._ram)
        layout.addWidget(self._disk)
        layout.addWidget(self._services)
        layout.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setInterval(poll_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        # Paint once immediately so the user doesn't see dashes on launch.
        self.refresh()

    def refresh(self) -> None:
        snap = stats.snapshot(cpu_interval=None)  # non-blocking
        self._cpu.setText(f"cpu {snap.cpu_percent:5.1f}%")

        mem = snap.memory
        ram_used = mem.used_bytes / _GB
        ram_total = mem.total_bytes / _GB
        self._ram.setText(f"ram {ram_used:.1f}/{ram_total:.1f} GB")

        disk = snap.disk
        disk_total = disk.total_bytes / _GB
        disk_used = (disk.total_bytes - disk.free_bytes) / _GB
        self._disk.setText(f"disk {disk_used:.0f}/{disk_total:.0f} GB")

        pieces: list[str] = []
        for svc in snap.services:
            mark = "●" if svc.active else "○"
            pieces.append(f"{mark} {svc.name}")
        self._services.setText("  ".join(pieces) if pieces else "no services")

        self.snapshot_ready.emit(snap)
