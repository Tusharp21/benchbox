"""One card per site in the Sites tab."""

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
    """Renders a ``SiteInfo`` + its bench path, with a destructive Drop action.

    Emits ``drop_requested(bench_path, site_name)``. Cards are static —
    there's no site-detail view to open — so only the Drop button fires.
    """

    drop_requested = Signal(Path, str)

    def __init__(
        self,
        bench_path: Path,
        site: SiteInfo,
        parent: QWidget | None = None,
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

        drop_btn = QPushButton("Drop")
        drop_btn.setProperty("role", "danger")
        drop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        drop_btn.clicked.connect(self._emit_drop)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addWidget(name)
        title_col.addWidget(bench_path_label)

        title_row = QHBoxLayout()
        title_row.addLayout(title_col, 1)
        title_row.addWidget(drop_btn, 0, Qt.AlignmentFlag.AlignTop)

        # Badges: db name + apps. Cap at 4 visible to keep card height
        # bounded; overflow becomes a "+N" chip.
        badges = QHBoxLayout()
        badges.setSpacing(6)
        if site.db_name:
            badges.addWidget(_Badge(f"db: {site.db_name}", accent=True))
        badges.addWidget(_Badge(f"{len(site.installed_apps)} apps"))
        visible = list(site.installed_apps[:4])
        hidden = max(0, len(site.installed_apps) - len(visible))
        for app in visible:
            badges.addWidget(_Badge(app))
        if hidden > 0:
            badges.addWidget(_Badge(f"+{hidden}"))
        badges.addStretch(1)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        root.addLayout(title_row)
        root.addLayout(badges)

    def _emit_drop(self) -> None:
        self.drop_requested.emit(self._bench_path, self._site_name)
