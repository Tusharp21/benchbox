"""Per-site card."""

from __future__ import annotations

from pathlib import Path

from benchbox_core.introspect import SiteInfo
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _Badge(QLabel):
    def __init__(self, text: str, *, accent: bool = False) -> None:
        super().__init__(text)
        self.setProperty("role", "badge-accent" if accent else "badge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class SiteCard(QFrame):
    install_app_requested = Signal(Path, str)
    drop_requested = Signal(Path, str)

    def __init__(
        self,
        bench_path: Path,
        site: SiteInfo,
        parent: QWidget | None = None,
        *,
        read_only: bool = False,
    ) -> None:
        super().__init__(parent)
        self._bench_path = bench_path
        self._site_name = site.name
        self.setObjectName("SiteCard")
        self.setFrameShape(QFrame.Shape.NoFrame)

        name = QLabel(site.name)
        name.setProperty("role", "h2")

        bench_path_label = QLabel(str(bench_path))
        bench_path_label.setProperty("role", "dim")
        bench_path_label.setWordWrap(True)

        install_btn = QPushButton("Install app")
        install_btn.setProperty("role", "primary")
        install_btn.setMinimumWidth(120)
        install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        install_btn.clicked.connect(
            lambda: self.install_app_requested.emit(self._bench_path, self._site_name)
        )

        drop_btn = QPushButton("Drop")
        drop_btn.setProperty("role", "danger")
        drop_btn.setMinimumWidth(84)
        drop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        drop_btn.clicked.connect(self._emit_drop)

        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        title_col.addWidget(name)
        title_col.addWidget(bench_path_label)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(install_btn)
        actions.addWidget(drop_btn)

        if read_only:
            install_btn.setVisible(False)
            drop_btn.setVisible(False)

        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title_row.addLayout(title_col, 1)
        title_row.addLayout(actions)

        badges = QHBoxLayout()
        badges.setSpacing(8)
        if site.db_name:
            badges.addWidget(_Badge(f"db: {site.db_name}", accent=True))
        badges.addWidget(_Badge(f"{len(site.installed_apps)} apps"))
        visible = list(site.installed_apps[:3])
        hidden = max(0, len(site.installed_apps) - len(visible))
        for app in visible:
            badges.addWidget(_Badge(app))
        if hidden > 0:
            badges.addWidget(_Badge(f"+{hidden}"))
        badges.addStretch(1)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)
        root.addLayout(title_row)
        root.addLayout(badges)

    def _emit_drop(self) -> None:
        self.drop_requested.emit(self._bench_path, self._site_name)
