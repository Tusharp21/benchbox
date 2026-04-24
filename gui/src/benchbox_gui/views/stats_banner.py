"""Top stats banner — polls :func:`benchbox_core.stats.snapshot` on a timer."""

from __future__ import annotations

from benchbox_core import stats
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from benchbox_gui.widgets.stat_pill import StatPill

_GB: int = 1024**3
DEFAULT_POLL_MS: int = 2000

_ACCENT_GREEN = "#50fa7b"
_ACCENT_RED = "#ff5555"


class StatsBanner(QWidget):
    """Pill-styled horizontal strip — CPU / RAM / disk / services.

    Emits ``snapshot_ready(SystemStats)`` on every tick so tests can hook in
    without reaching through the widget tree.
    """

    snapshot_ready = Signal(object)

    def __init__(self, parent: QWidget | None = None, *, poll_ms: int = DEFAULT_POLL_MS) -> None:
        super().__init__(parent)
        self.setObjectName("StatsBanner")
        self._cpu = StatPill("cpu")
        self._ram = StatPill("ram")
        self._disk = StatPill("disk")
        self._mariadb = StatPill("mariadb")
        self._redis = StatPill("redis")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(10)
        for pill in (self._cpu, self._ram, self._disk, self._mariadb, self._redis):
            layout.addWidget(pill)
        layout.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setInterval(poll_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        snap = stats.snapshot(cpu_interval=None)
        self._cpu.set_value(f"{snap.cpu_percent:.1f}%")

        mem = snap.memory
        ram_used = mem.used_bytes / _GB
        ram_total = mem.total_bytes / _GB
        self._ram.set_value(f"{ram_used:.1f} / {ram_total:.1f} GB")

        disk = snap.disk
        disk_total = disk.total_bytes / _GB
        disk_used = (disk.total_bytes - disk.free_bytes) / _GB
        self._disk.set_value(f"{disk_used:.0f} / {disk_total:.0f} GB")

        # Service pills colour-code the value.
        mariadb = next((s for s in snap.services if s.name == "mariadb"), None)
        if mariadb is not None:
            self._mariadb.set_value(mariadb.state)
            self._mariadb.set_accent(_ACCENT_GREEN if mariadb.active else _ACCENT_RED)
        redis = next((s for s in snap.services if s.name == "redis-server"), None)
        if redis is not None:
            self._redis.set_value(redis.state)
            self._redis.set_accent(_ACCENT_GREEN if redis.active else _ACCENT_RED)

        self.snapshot_ready.emit(snap)
