"""Top stats banner with theme toggle."""

from __future__ import annotations

from benchbox_core import preferences, stats
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from benchbox_gui.resources import icon
from benchbox_gui.widgets.stat_pill import StatPill

_GB: int = 1024**3
DEFAULT_POLL_MS: int = 2000
# Node version is comparatively expensive (forks /usr/bin/node) and
# rarely changes during a session — refresh every Nth tick rather than
# every tick.
_NODE_REFRESH_EVERY: int = 15

# Service-pill accents; theme-agnostic on purpose — active-green works on
# both backgrounds.
_ACCENT_GREEN = "#1a7f37"  # slightly darker than dark-theme variant so it
_ACCENT_RED = "#cf222e"  # stays legible against the light theme too.


class StatsBanner(QWidget):
    snapshot_ready = Signal(object)
    theme_toggled = Signal(str)

    def __init__(self, parent: QWidget | None = None, *, poll_ms: int = DEFAULT_POLL_MS) -> None:
        super().__init__(parent)
        self.setObjectName("StatsBanner")
        self._cpu = StatPill("cpu")
        self._ram = StatPill("ram")
        self._disk = StatPill("disk")
        self._node = StatPill("node")
        self._mariadb = StatPill("mariadb")
        self._redis = StatPill("redis")
        self._node_tick: int = 0
        self._node_version: str | None = None

        self._theme_btn = QPushButton()
        self._theme_btn.setObjectName("ThemeToggle")
        self._theme_btn.setProperty("role", "ghost")
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.setIconSize(QSize(18, 18))
        self._theme_btn.clicked.connect(self._on_toggle_clicked)
        self._current_theme: preferences.Theme = preferences.get_theme()
        self._refresh_theme_icon()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(10)
        for pill in (self._cpu, self._ram, self._disk, self._node, self._mariadb, self._redis):
            layout.addWidget(pill)
        layout.addStretch(1)
        layout.addWidget(self._theme_btn)

        self._timer = QTimer(self)
        self._timer.setInterval(poll_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    # --- theme toggle -------------------------------------------------

    def set_theme(self, theme: preferences.Theme) -> None:
        self._current_theme = theme
        self._refresh_theme_icon()

    def _refresh_theme_icon(self) -> None:
        icon_name = "moon" if self._current_theme == "dark" else "sun"
        self._theme_btn.setIcon(icon(icon_name, theme=self._current_theme))
        other = "light" if self._current_theme == "dark" else "dark"
        self._theme_btn.setToolTip(f"Switch to {other} theme")

    def _on_toggle_clicked(self) -> None:
        new_theme: preferences.Theme = "light" if self._current_theme == "dark" else "dark"
        self._current_theme = new_theme
        self._refresh_theme_icon()
        self.theme_toggled.emit(new_theme)

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

        self._refresh_node_pill()

        self.snapshot_ready.emit(snap)

    def _refresh_node_pill(self) -> None:
        # Re-probe Node periodically; in between, repaint the cached value
        # so colour-changes from accent settings still apply.
        if self._node_tick == 0:
            self._node_version = stats.get_node_version()
        self._node_tick = (self._node_tick + 1) % _NODE_REFRESH_EVERY
        if self._node_version is None:
            self._node.set_value("missing")
            self._node.set_accent(_ACCENT_RED)
        else:
            self._node.set_value(self._node_version)
            major = self._node_version.split(".", 1)[0]
            ok = major.isdigit() and int(major) >= 18
            self._node.set_accent(_ACCENT_GREEN if ok else _ACCENT_RED)
