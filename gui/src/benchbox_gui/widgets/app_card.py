"""One card per (bench, app) in the Apps tab."""

from __future__ import annotations

from pathlib import Path

from benchbox_core.introspect import AppInfo
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
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
    """Renders an :class:`AppInfo` + its bench path with per-app actions.

    Three actions:
    - **Install on site** — ``install_requested(bench, app)`` — caller opens
      a site picker (preselected to this app + bench) and spawns
      ``core.app.install_app``.
    - **Uninstall from site** — ``uninstall_requested(bench, app)`` — caller
      opens a site picker before spawning ``core.app.uninstall_app``.
    - **Remove from bench** — ``remove_requested(bench, app)`` — caller gates
      on a typed-name confirm, then spawns ``core.app.remove_app``.

    ``frappe`` is treated as non-removable: uninstall + remove become
    disabled with a tooltip explaining why. Install stays enabled because
    Frappe is always implicitly installed when the site is created — the
    dialog will skip it if it's already there.
    """

    install_requested = Signal(Path, str)
    uninstall_requested = Signal(Path, str)
    remove_requested = Signal(Path, str)

    def __init__(
        self,
        bench_path: Path,
        app: AppInfo,
        parent: QWidget | None = None,
        *,
        read_only: bool = False,
    ) -> None:
        super().__init__(parent)
        self._bench_path = bench_path
        self._app_name = app.name
        self.setObjectName("AppCard")
        self.setFrameShape(QFrame.Shape.NoFrame)

        name = QLabel(app.name)
        name.setProperty("role", "h2")

        bench_path_label = QLabel(str(bench_path))
        bench_path_label.setProperty("role", "dim")
        bench_path_label.setWordWrap(True)

        install_btn = QPushButton("Install on site…")
        install_btn.setProperty("role", "primary")
        install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        install_btn.clicked.connect(
            lambda: self.install_requested.emit(self._bench_path, self._app_name)
        )

        uninstall_btn = QPushButton("Uninstall from site…")
        uninstall_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        uninstall_btn.clicked.connect(
            lambda: self.uninstall_requested.emit(self._bench_path, self._app_name)
        )

        remove_btn = QPushButton("Remove from bench")
        remove_btn.setProperty("role", "danger")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.clicked.connect(
            lambda: self.remove_requested.emit(self._bench_path, self._app_name)
        )

        if app.name == FRAPPE_APP_NAME:
            # Required by every bench — we don't let the user shoot
            # themselves in the foot even with the typed-confirm.
            uninstall_btn.setEnabled(False)
            uninstall_btn.setToolTip("frappe is required by every bench")
            remove_btn.setEnabled(False)
            remove_btn.setToolTip("frappe cannot be removed — it's the bench itself")

        actions = QHBoxLayout()
        actions.setSpacing(6)
        actions.addWidget(install_btn)
        actions.addWidget(uninstall_btn)
        actions.addWidget(remove_btn)

        if read_only:
            install_btn.setVisible(False)
            uninstall_btn.setVisible(False)
            remove_btn.setVisible(False)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addWidget(name)
        title_col.addWidget(bench_path_label)

        title_row = QHBoxLayout()
        title_row.addLayout(title_col, 1)
        title_row.addLayout(actions)

        badges = QHBoxLayout()
        badges.setSpacing(6)
        if app.version:
            badges.addWidget(_Badge(f"v{app.version}", accent=True))
        if app.git_branch:
            badges.addWidget(_Badge(app.git_branch))
        badges.addStretch(1)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        root.addLayout(title_row)
        root.addLayout(badges)
