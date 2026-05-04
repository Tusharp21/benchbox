"""Sticky top header for the bench detail page.

Replaces the flat 7-button :class:`BenchActionRow` with a compact two-row
header:

- top row: ``← back`` + bench path + meta (frappe / python / branch)
- action row: dropdown menus (``+ Add ▾`` for create-* mutations,
  ``Bench ▾`` for bench-level chores) and an ``Open folder`` button

``bench start`` Start/Stop is owned by :class:`BenchProcessDock`, not this
header — keeping the header free of process-state coupling so it never
needs to repaint when the bench transitions running ↔ stopped.

Every action emits a typed signal; the page sequences the dialogs and
workers. The header itself does no I/O.
"""

from __future__ import annotations

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


class BenchDetailHeader(QWidget):
    """Sticky two-row header above the tab strip."""

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

        self._back = QPushButton("← back to benches")
        self._back.setProperty("role", "ghost")
        self._back.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back.clicked.connect(self.back_requested.emit)

        self._title = QLabel()
        self._title.setProperty("role", "h1")
        self._title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._meta = QLabel()
        self._meta.setProperty("role", "dim")
        self._meta.setTextFormat(self._meta.textFormat().RichText)

        # ---- "+ Add ▾" dropdown -------------------------------------
        add_menu = QMenu(self)
        add_menu.addAction(self._mk_action("+ New site", self.new_site_requested.emit))
        add_menu.addAction(self._mk_action("+ Get app", self.get_app_requested.emit))
        add_menu.addAction(self._mk_action("+ New app", self.new_app_requested.emit))
        add_menu.addSeparator()
        add_menu.addAction(self._mk_action("⟲ Restore site", self.restore_site_requested.emit))

        self._add_btn = QPushButton("+ Add  ▾")
        self._add_btn.setProperty("role", "primary")
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setMenu(add_menu)

        # ---- "Bench ▾" dropdown -------------------------------------
        bench_menu = QMenu(self)
        bench_menu.addAction(self._mk_action("⤓ Update bench", self.update_requested.emit))
        bench_menu.addAction(self._mk_action("↻ Migrate all sites", self.migrate_all_requested.emit))
        bench_menu.addAction(self._mk_action("⟲ Restart processes", self.restart_requested.emit))

        self._bench_btn = QPushButton("Bench  ▾")
        self._bench_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bench_btn.setMenu(bench_menu)

        # ---- "Open folder" ------------------------------------------
        self._folder_btn = QPushButton("Open folder")
        self._folder_btn.setProperty("role", "ghost")
        self._folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._folder_btn.clicked.connect(self.open_folder_requested.emit)

        # ---- assembly -----------------------------------------------
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)
        top_row.addWidget(self._back)
        top_row.addStretch(1)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(12)
        title_row.addWidget(self._title, 1)
        title_row.addWidget(self._add_btn)
        title_row.addWidget(self._bench_btn)
        title_row.addWidget(self._folder_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 8)
        layout.setSpacing(4)
        layout.addLayout(top_row)
        layout.addLayout(title_row)
        layout.addWidget(self._meta)

    # --- public API ---------------------------------------------------

    def set_bench(
        self,
        *,
        path: str,
        frappe_version: str | None,
        python_version: str | None,
        git_branch: str | None,
    ) -> None:
        """Repaint the title + meta line for ``path``."""
        self._title.setText(path)
        meta_parts: list[str] = []
        if frappe_version:
            meta_parts.append(f"<b>frappe</b> {frappe_version}")
        if python_version:
            meta_parts.append(f"<b>python</b> {python_version}")
        if git_branch:
            meta_parts.append(f"<b>branch</b> {git_branch}")
        self._meta.setText("  •  ".join(meta_parts) if meta_parts else "—")

    # --- helpers ------------------------------------------------------

    def _mk_action(self, label: str, slot) -> QAction:  # type: ignore[no-untyped-def]
        action = QAction(label, self)
        action.triggered.connect(slot)
        return action


__all__ = ["BenchDetailHeader"]
