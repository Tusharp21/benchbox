"""Sticky top header for the bench detail page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class _Pill(QLabel):
    def __init__(self, label: str, value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(
            f'<span style="opacity:0.7;">{label}</span> '
            f'<span style="font-weight:600;">{value}</span>'
        )
        self.setProperty("role", "badge")
        self.setTextFormat(Qt.TextFormat.RichText)


class BenchDetailHeader(QWidget):
    back_requested = Signal()
    open_folder_requested = Signal()

    new_site_requested = Signal()
    get_app_requested = Signal()
    new_app_requested = Signal()
    restore_site_requested = Signal()

    update_requested = Signal()
    migrate_all_requested = Signal()
    restart_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("BenchDetailHeader")

        self._back = QPushButton("Back to benches")
        self._back.setProperty("role", "ghost")
        self._back.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back.clicked.connect(self.back_requested.emit)

        self._name = QLabel("—")
        self._name.setProperty("role", "h1")
        self._name.setWordWrap(True)
        self._name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # word-wrap so deep ~/projects/... paths don't push the page
        # off the right edge.
        self._path = QLabel("")
        self._path.setProperty("role", "kbd")
        self._path.setWordWrap(True)
        self._path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._path.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._frappe_pill = _Pill("frappe", "—")
        self._python_pill = _Pill("python", "—")
        self._branch_pill = _Pill("branch", "—")
        pill_row = QHBoxLayout()
        pill_row.setContentsMargins(0, 4, 0, 0)
        pill_row.setSpacing(8)
        pill_row.addWidget(self._frappe_pill)
        pill_row.addWidget(self._python_pill)
        pill_row.addWidget(self._branch_pill)
        pill_row.addStretch(1)

        add_menu = QMenu(self)
        add_menu.addAction(self._mk_action("New site", self.new_site_requested.emit))
        add_menu.addAction(self._mk_action("Get app", self.get_app_requested.emit))
        add_menu.addAction(self._mk_action("New app", self.new_app_requested.emit))
        add_menu.addSeparator()
        add_menu.addAction(self._mk_action("Restore site", self.restore_site_requested.emit))

        self._add_btn = QPushButton("Add...")
        self._add_btn.setProperty("role", "primary")
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setMenu(add_menu)

        bench_menu = QMenu(self)
        bench_menu.addAction(self._mk_action("Update bench", self.update_requested.emit))
        bench_menu.addAction(
            self._mk_action("Migrate all sites", self.migrate_all_requested.emit)
        )
        bench_menu.addAction(self._mk_action("Restart processes", self.restart_requested.emit))

        self._bench_btn = QPushButton("Bench...")
        self._bench_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bench_btn.setMenu(bench_menu)

        self._folder_btn = QPushButton("Open folder")
        self._folder_btn.setProperty("role", "ghost")
        self._folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._folder_btn.clicked.connect(self.open_folder_requested.emit)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)
        top_row.addWidget(self._back, 0, Qt.AlignmentFlag.AlignTop)
        top_row.addStretch(1)
        top_row.addWidget(self._add_btn, 0, Qt.AlignmentFlag.AlignTop)
        top_row.addWidget(self._bench_btn, 0, Qt.AlignmentFlag.AlignTop)
        top_row.addWidget(self._folder_btn, 0, Qt.AlignmentFlag.AlignTop)

        title_block = QVBoxLayout()
        title_block.setContentsMargins(0, 0, 0, 0)
        title_block.setSpacing(2)
        title_block.addWidget(self._name)
        title_block.addWidget(self._path)
        title_block.addLayout(pill_row)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 8)
        layout.setSpacing(8)
        layout.addLayout(top_row)
        layout.addLayout(title_block)

        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_bench(
        self,
        *,
        path: str,
        frappe_version: str | None,
        python_version: str | None,
        git_branch: str | None,
    ) -> None:
        bench_path = Path(path)
        self._name.setText(bench_path.name or str(bench_path))
        self._path.setText(str(bench_path))
        self._frappe_pill.setText(self._format_pill_text("frappe", frappe_version))
        self._python_pill.setText(self._format_pill_text("python", python_version))
        self._branch_pill.setText(self._format_pill_text("branch", git_branch))

    @staticmethod
    def _format_pill_text(label: str, value: str | None) -> str:
        shown = value if value else "—"
        return (
            f'<span style="opacity:0.7;">{label}</span> '
            f'<span style="font-weight:600;">{shown}</span>'
        )

    def _mk_action(self, label: str, slot) -> QAction:  # type: ignore[no-untyped-def]
        action = QAction(label, self)
        action.triggered.connect(slot)
        return action


__all__ = ["BenchDetailHeader"]
