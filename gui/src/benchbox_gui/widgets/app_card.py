"""Per-app card used by the bench-detail Apps tab and the global Apps page."""

from __future__ import annotations

from pathlib import Path

from benchbox_core.introspect import AppInfo
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

FRAPPE_APP_NAME: str = "frappe"


class _Badge(QLabel):
    def __init__(self, text: str, *, accent: bool = False) -> None:
        super().__init__(text)
        self.setProperty("role", "badge-accent" if accent else "badge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class AppCard(QFrame):
    install_requested = Signal(Path, str)
    uninstall_requested = Signal(Path, str)
    remove_requested = Signal(Path, str)
    switch_branch_requested = Signal(Path, str, str)

    def __init__(
        self,
        bench_path: Path,
        app: AppInfo,
        parent: QWidget | None = None,
        *,
        read_only: bool = False,
        show_bench_path: bool = True,
    ) -> None:
        super().__init__(parent)
        self._bench_path = bench_path
        self._app_name = app.name
        self.setObjectName("AppCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        name = QLabel(app.name)
        name.setProperty("role", "h2")

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addWidget(name)
        if app.version:
            title_row.addWidget(_Badge(f"v{app.version}", accent=True))
        if app.git_branch:
            title_row.addWidget(_Badge(app.git_branch))
        title_row.addStretch(1)

        install_btn = QPushButton("Install on site")
        install_btn.setProperty("role", "primary")
        install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        install_btn.setMinimumHeight(32)
        install_btn.clicked.connect(
            lambda: self.install_requested.emit(self._bench_path, self._app_name)
        )

        uninstall_btn = QPushButton("Uninstall from site")
        uninstall_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        uninstall_btn.setMinimumHeight(32)
        uninstall_btn.clicked.connect(
            lambda: self.uninstall_requested.emit(self._bench_path, self._app_name)
        )

        remove_btn = QPushButton("Remove from bench")
        remove_btn.setProperty("role", "danger")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setMinimumHeight(32)
        remove_btn.clicked.connect(
            lambda: self.remove_requested.emit(self._bench_path, self._app_name)
        )

        switch_btn = QPushButton("Switch branch")
        switch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        switch_btn.setMinimumHeight(32)
        current_branch = app.git_branch or ""
        switch_btn.clicked.connect(
            lambda: self.switch_branch_requested.emit(
                self._bench_path, self._app_name, current_branch
            )
        )

        if app.name == FRAPPE_APP_NAME:
            uninstall_btn.setEnabled(False)
            uninstall_btn.setToolTip("frappe is required by every bench")
            remove_btn.setEnabled(False)
            remove_btn.setToolTip("frappe cannot be removed — it's the bench itself")

        actions = QHBoxLayout()
        actions.setSpacing(6)
        actions.addWidget(install_btn, 1)
        actions.addWidget(uninstall_btn, 1)
        actions.addWidget(switch_btn, 1)
        actions.addWidget(remove_btn, 1)

        if read_only:
            install_btn.setVisible(False)
            uninstall_btn.setVisible(False)
            switch_btn.setVisible(False)
            remove_btn.setVisible(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        root.addLayout(title_row)

        if show_bench_path:
            bench_path_label = QLabel(str(bench_path))
            bench_path_label.setProperty("role", "dim")
            bench_path_label.setWordWrap(True)
            root.addWidget(bench_path_label)

        root.addLayout(actions)
