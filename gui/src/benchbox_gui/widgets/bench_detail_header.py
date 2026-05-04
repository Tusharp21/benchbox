"""Sticky top header for the bench detail page.

Two-block design with a clear identity for the bench:

- top row: ``← back`` (left) + action buttons (right). Buttons are
  pinned to the top so a wrapped path below doesn't shove them down.
- title block: a big bench-name heading, the full path rendered in
  monospace below it (word-wrapped — no horizontal scroll), and a row
  of version pills (frappe / python / branch).

``bench start`` Start/Stop is owned by :class:`BenchProcessDock`, not
this header — keeping the header free of process-state coupling so it
never needs to repaint when the bench transitions running ↔ stopped.

Every action emits a typed signal; the page sequences the dialogs and
workers. The header itself does no I/O.
"""

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
    """Read-only badge pill with a label-prefix and value (e.g. ``frappe 15.0.0``).

    Painted via the existing ``QLabel[role="badge"]`` style rule so it
    matches site-tab and bench-card badges. Cheap; no custom paint event.
    """

    def __init__(self, label: str, value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Prefix in slightly muted weight, value bold-ish — both still
        # honour the global badge palette.
        self.setText(
            f'<span style="opacity:0.7;">{label}</span> '
            f'<span style="font-weight:600;">{value}</span>'
        )
        self.setProperty("role", "badge")
        self.setTextFormat(Qt.TextFormat.RichText)


class BenchDetailHeader(QWidget):
    """Sticky multi-block header above the tab strip."""

    back_requested = Signal()
    open_folder_requested = Signal()

    # "+ Add ▾" menu — create-style mutations.
    new_site_requested = Signal()
    get_app_requested = Signal()
    new_app_requested = Signal()
    restore_site_requested = Signal()

    # "Bench ▾" menu — bench-wide chores.
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

        # Bench name = last path segment. The big visual anchor.
        self._name = QLabel("—")
        self._name.setProperty("role", "h1")
        self._name.setWordWrap(True)
        self._name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Full path in monospace below the name; word-wraps so a deep
        # ~/projects/... path never forces horizontal scroll on the page.
        self._path = QLabel("")
        self._path.setProperty("role", "kbd")
        self._path.setWordWrap(True)
        self._path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._path.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Version pills row.
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

        # ---- Add dropdown -------------------------------------------
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

        # ---- Bench dropdown -----------------------------------------
        bench_menu = QMenu(self)
        bench_menu.addAction(self._mk_action("Update bench", self.update_requested.emit))
        bench_menu.addAction(
            self._mk_action("Migrate all sites", self.migrate_all_requested.emit)
        )
        bench_menu.addAction(self._mk_action("Restart processes", self.restart_requested.emit))

        self._bench_btn = QPushButton("Bench...")
        self._bench_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bench_btn.setMenu(bench_menu)

        # ---- "Open folder" ------------------------------------------
        self._folder_btn = QPushButton("Open folder")
        self._folder_btn.setProperty("role", "ghost")
        self._folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._folder_btn.clicked.connect(self.open_folder_requested.emit)

        # ---- assembly -----------------------------------------------
        # Top row: back-button (left) + action buttons (right). Action
        # buttons are top-aligned so a long wrapped path below doesn't
        # vertically center them awkwardly.
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

        # Default minimum width small enough that the header itself never
        # demands more than the viewport width. Layout will give each
        # element more room when available.
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    # --- public API ---------------------------------------------------

    def set_bench(
        self,
        *,
        path: str,
        frappe_version: str | None,
        python_version: str | None,
        git_branch: str | None,
    ) -> None:
        """Repaint the title / path / pills for ``path``."""
        bench_path = Path(path)
        # Last directory segment is the visual anchor; full path lives
        # below in monospace.
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

    # --- helpers ------------------------------------------------------

    def _mk_action(self, label: str, slot) -> QAction:  # type: ignore[no-untyped-def]
        action = QAction(label, self)
        action.triggered.connect(slot)
        return action


__all__ = ["BenchDetailHeader"]
