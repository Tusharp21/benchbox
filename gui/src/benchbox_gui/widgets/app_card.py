"""One card per (bench, app) — used by the Apps tab and global Apps page.

Layout (top → bottom):

- Title row: app name (large) + version pill + branch pill
- Optional bench-path line (global Apps page only — on the per-bench
  detail view every card belongs to the same bench, so the path would
  just repeat itself)
- Action row: 3 equal-width buttons — Install on site, Uninstall from
  site, Remove from bench. The card no longer crams the buttons next
  to the title, so the card's natural width drops and the parent
  CardGrid lays out 2-3 cards per row at typical window sizes.

``frappe`` is treated as non-removable; uninstall + remove are disabled
with a tooltip explaining why. Install stays enabled because Frappe is
implicitly installed when the site is created — the install dialog
short-circuits if the app is already there.
"""

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
    """Renders an :class:`AppInfo` + its bench path with per-app actions.

    Three actions emitted as signals; the parent page sequences the
    confirm dialogs and operation workers.

    - ``install_requested(bench, app)``
    - ``uninstall_requested(bench, app)``
    - ``remove_requested(bench, app)``
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
        show_bench_path: bool = True,
    ) -> None:
        super().__init__(parent)
        self._bench_path = bench_path
        self._app_name = app.name
        self.setObjectName("AppCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        # Cards expand horizontally to fill the column they're placed
        # in; vertically they stay at their hint height so the grid
        # rows align cleanly.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        name = QLabel(app.name)
        name.setProperty("role", "h2")

        # Version + branch pills sit next to the name. Lighter visual
        # weight than the buttons so the eye lands on the actions, not
        # the metadata.
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addWidget(name)
        if app.version:
            title_row.addWidget(_Badge(f"v{app.version}", accent=True))
        if app.git_branch:
            title_row.addWidget(_Badge(app.git_branch))
        title_row.addStretch(1)

        # ---- action row --------------------------------------------
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

        if app.name == FRAPPE_APP_NAME:
            # Required by every bench — we don't let the user shoot
            # themselves in the foot even with the typed-confirm.
            uninstall_btn.setEnabled(False)
            uninstall_btn.setToolTip("frappe is required by every bench")
            remove_btn.setEnabled(False)
            remove_btn.setToolTip("frappe cannot be removed — it's the bench itself")

        actions = QHBoxLayout()
        actions.setSpacing(6)
        # Equal column-weight so the row reads as a button matrix and
        # the buttons align across cards in the grid.
        actions.addWidget(install_btn, 1)
        actions.addWidget(uninstall_btn, 1)
        actions.addWidget(remove_btn, 1)

        if read_only:
            install_btn.setVisible(False)
            uninstall_btn.setVisible(False)
            remove_btn.setVisible(False)

        # ---- assembly ----------------------------------------------
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
