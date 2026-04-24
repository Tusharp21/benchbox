"""One card per bench in the list view."""

from __future__ import annotations

from pathlib import Path

from benchbox_core.introspect import BenchInfo
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
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


class BenchCard(QFrame):
    """Renders a ``BenchInfo`` as a clickable card.

    Emits ``opened(Path)`` when the user clicks the 'Open' button or
    anywhere on the card body (not the URL link — those open the
    browser via ``QDesktopServices``).

    When running, shows:
    - a green "● running" chip in the title row, and
    - a clickable ``http://localhost:<port>`` link below the subtitle.
    """

    opened = Signal(Path)

    def __init__(
        self,
        info: BenchInfo,
        *,
        running: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._info = info
        self.setObjectName("BenchCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        title = QLabel(info.path.name)
        title.setProperty("role", "h2")

        # Running indicator — hidden by default; flipped by ``set_running``.
        self._running_chip = QLabel("● running")
        self._running_chip.setStyleSheet(
            "background-color: #1a7f37; color: #ffffff; "
            "border-radius: 10px; padding: 2px 10px; font-size: 9pt; font-weight: 600;"
        )
        self._running_chip.setVisible(running)

        subtitle = QLabel(str(info.path))
        subtitle.setProperty("role", "dim")
        subtitle.setWordWrap(True)

        # Live URL — visible only while the bench is running. Uses an
        # anchor so Qt opens it in the default browser.
        self._port = info.webserver_port
        self._url = f"http://localhost:{self._port}"
        self._url_link = QLabel(
            f'<a href="{self._url}" style="color:#8250df;text-decoration:none;">↗ {self._url}</a>'
        )
        self._url_link.setOpenExternalLinks(True)
        # Stop the card-wide click handler from stealing clicks on the link.
        self._url_link.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self._url_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self._url_link.setVisible(running)

        open_btn = QPushButton("Open")
        open_btn.setProperty("role", "primary")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setMinimumWidth(84)
        open_btn.clicked.connect(self._emit_opened)

        title_line = QHBoxLayout()
        title_line.setSpacing(8)
        title_line.addWidget(title)
        title_line.addWidget(self._running_chip)
        title_line.addStretch(1)

        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        title_col.addLayout(title_line)
        title_col.addWidget(subtitle)
        title_col.addWidget(self._url_link)

        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title_row.addLayout(title_col, 1)
        title_row.addWidget(open_btn, 0, Qt.AlignmentFlag.AlignTop)

        # Badges row: frappe version, python, branch, site/app counts
        badges = QHBoxLayout()
        badges.setSpacing(8)
        if info.frappe_version:
            badges.addWidget(_Badge(f"frappe {info.frappe_version}", accent=True))
        if info.python_version:
            badges.addWidget(_Badge(f"py {info.python_version}"))
        if info.git_branch:
            badges.addWidget(_Badge(info.git_branch))
        sites_n = len(info.sites)
        apps_n = len(info.apps)
        badges.addWidget(_Badge(f"{sites_n} site{'' if sites_n == 1 else 's'}"))
        badges.addWidget(_Badge(f"{apps_n} app{'' if apps_n == 1 else 's'}"))
        badges.addStretch(1)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)
        root.addLayout(title_row)
        root.addLayout(badges)

    # Make the whole card clickable, not just the button.
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._emit_opened()
        super().mousePressEvent(event)

    def _emit_opened(self) -> None:
        self.opened.emit(self._info.path)

    # --- running indicator --------------------------------------------

    @property
    def bench_path(self) -> Path:
        return self._info.path

    @property
    def url(self) -> str:
        return self._url

    def set_running(self, running: bool) -> None:
        self._running_chip.setVisible(running)
        self._url_link.setVisible(running)
