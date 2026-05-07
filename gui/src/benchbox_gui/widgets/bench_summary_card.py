"""Per-bench dashboard card with a list of compact item rows."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from benchbox_core.introspect import AppInfo, SiteInfo
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class _Badge(QLabel):
    def __init__(self, text: str, *, accent: bool = False) -> None:
        super().__init__(text)
        self.setProperty("role", "badge-accent" if accent else "badge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class _ItemRow(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ItemRow")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _layout(self) -> QHBoxLayout:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        return layout


class SiteRow(_ItemRow):
    def __init__(self, site: SiteInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = self._layout()

        name = QLabel(site.name)
        name.setProperty("role", "row-title")

        meta_bits: list[str] = []
        if site.db_name:
            meta_bits.append(f"db: {site.db_name}")
        meta_bits.append(f"{len(site.installed_apps)} apps")
        meta = QLabel(" · ".join(meta_bits))
        meta.setProperty("role", "dim")

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.addWidget(name)
        text_col.addWidget(meta)

        layout.addLayout(text_col, 1)

        if site.maintenance_mode:
            layout.addWidget(_Badge("maintenance", accent=False))
        if site.scheduler_paused:
            layout.addWidget(_Badge("scheduler paused"))


class AppRow(_ItemRow):
    def __init__(self, app: AppInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = self._layout()

        name = QLabel(app.name)
        name.setProperty("role", "row-title")
        layout.addWidget(name, 1)

        if app.version:
            layout.addWidget(_Badge(f"v{app.version}", accent=True))
        if app.git_branch:
            layout.addWidget(_Badge(app.git_branch))


class BenchSummaryCard(QFrame):
    """A bench rendered as a single card, with item rows inside."""

    def __init__(
        self,
        bench_path: Path,
        *,
        item_label: str,
        accent_color: str = "#bd93f9",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bench_path = bench_path
        self._item_label = item_label
        self.setObjectName("BenchSummaryCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        title = QLabel(bench_path.name or str(bench_path))
        title.setProperty("role", "h2")

        path_label = QLabel(str(bench_path))
        path_label.setProperty("role", "dim")
        path_label.setWordWrap(True)
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.addWidget(title)
        title_col.addWidget(path_label)

        self._count_value = QLabel("0")
        self._count_value.setProperty("role", "kpi-value")
        self._count_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._count_label = QLabel(item_label.upper())
        self._count_label.setProperty("role", "kpi-label")
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._count_value.setStyleSheet(f"color: {accent_color};")

        count_col = QVBoxLayout()
        count_col.setSpacing(2)
        count_col.setContentsMargins(0, 0, 0, 0)
        count_col.addWidget(self._count_value)
        count_col.addWidget(self._count_label)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(12)
        header_row.addLayout(title_col, 1)
        header_row.addLayout(count_col)

        self._header = QFrame()
        self._header.setObjectName("BenchSummaryHeader")
        self._header.setStyleSheet(f"#BenchSummaryHeader {{ border-left: 3px solid {accent_color}; }}")
        header_layout = QVBoxLayout(self._header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(0)
        header_layout.addLayout(header_row)

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)
        self._body_layout.addStretch(1)

        self._empty_hint = QLabel("Nothing to show.")
        self._empty_hint.setProperty("role", "dim")
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_hint.setVisible(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header)
        root.addWidget(self._body)
        root.addWidget(self._empty_hint)

    @property
    def bench_path(self) -> Path:
        return self._bench_path

    def row_count(self) -> int:
        # All items minus the trailing stretch.
        n = self._body_layout.count() - 1
        return max(0, n)

    def set_rows(self, rows: Sequence[QWidget]) -> None:
        # Drain everything — widgets *and* spacer items — so the trailing
        # stretch doesn't pile up across renders.
        while self._body_layout.count() > 0:
            item = self._body_layout.takeAt(0)
            if item is None:
                break
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        for row in rows:
            row.setParent(self._body)
            self._body_layout.addWidget(row)
        self._body_layout.addStretch(1)

        n = len(rows)
        suffix = self._item_label if n == 1 else f"{self._item_label}s"
        self._count_value.setText(str(n))
        self._count_label.setText(suffix.upper())
        self._empty_hint.setVisible(n == 0)


__all__ = ["AppRow", "BenchSummaryCard", "SiteRow"]
