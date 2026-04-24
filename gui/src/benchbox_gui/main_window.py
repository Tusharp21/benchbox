"""Main window — left sidebar, top stats banner, main content via QStackedWidget."""

from __future__ import annotations

from pathlib import Path

from benchbox_core import preferences
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.resources import icon, stylesheet
from benchbox_gui.services.bench_processes import BenchProcessManager
from benchbox_gui.views.apps import AppsView
from benchbox_gui.views.bench_detail import BenchDetailView
from benchbox_gui.views.bench_list import BenchListView
from benchbox_gui.views.install import InstallerView
from benchbox_gui.views.logs_view import LogsView
from benchbox_gui.views.settings_view import SettingsView
from benchbox_gui.views.sites import SitesView
from benchbox_gui.views.stats_banner import StatsBanner

# (label, key, icon name) — icons resolved from benchbox_gui.resources.icons.
_SIDEBAR_ENTRIES: tuple[tuple[str, str, str], ...] = (
    ("Benches", "benches", "benches"),
    ("Install", "install", "install"),
    ("Sites", "sites", "sites"),
    ("Apps", "apps", "apps"),
    ("Logs", "logs", "logs"),
    ("Settings", "settings", "settings"),
)


class MainWindow(QMainWindow):
    """benchbox's top-level window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("benchbox")
        self.resize(1200, 760)
        self.setMinimumSize(960, 600)

        self._theme: preferences.Theme = preferences.get_theme()

        # App-level singleton that owns every running `bench start`
        # process. Views subscribe to it rather than owning their own
        # QProcess, so switching views never kills a bench and multiple
        # benches can run at once.
        self._process_manager = BenchProcessManager(self)

        self._stack = QStackedWidget()
        self._pages: dict[str, int] = {}

        self._bench_list = BenchListView(self._process_manager)
        self._bench_detail = BenchDetailView(self._process_manager)
        self._installer = InstallerView()

        self._bench_list.bench_selected.connect(self._on_bench_selected)
        self._bench_detail.back_requested.connect(lambda: self._show_page("benches"))

        self._register_page("benches", self._bench_list)
        self._register_page("install", self._installer)
        self._register_page("sites", SitesView())
        self._register_page("apps", AppsView())
        self._register_page("logs", LogsView())
        self._register_page("settings", SettingsView())
        # Detail view is not a sidebar entry; it's a transient page behind
        # Benches.
        self._bench_detail_index = self._stack.addWidget(self._bench_detail)

        self._sidebar = QListWidget()
        self._sidebar.setObjectName("Sidebar")
        self._sidebar.setFixedWidth(220)
        self._sidebar.setIconSize(QSize(18, 18))
        for label, _, icon_name in _SIDEBAR_ENTRIES:
            item = QListWidgetItem(label)
            item.setIcon(icon(icon_name, theme=self._theme))
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._sidebar.addItem(item)
        self._sidebar.currentRowChanged.connect(self._on_sidebar_row_changed)

        self._stats_banner = StatsBanner()
        self._stats_banner.theme_toggled.connect(self._on_theme_toggled)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addWidget(self._stats_banner)
        center_layout.addWidget(self._stack, 1)

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._sidebar)
        root_layout.addWidget(center, 1)
        self.setCentralWidget(root)

        self._sidebar.setCurrentRow(0)

    # ------------------------------------------------------------------

    def _register_page(self, key: str, widget: QWidget) -> None:
        self._pages[key] = self._stack.addWidget(widget)

    def _show_page(self, key: str) -> None:
        self._stack.setCurrentIndex(self._pages[key])

    def _on_sidebar_row_changed(self, row: int) -> None:
        if 0 <= row < len(_SIDEBAR_ENTRIES):
            self._show_page(_SIDEBAR_ENTRIES[row][1])

    def _on_bench_selected(self, path: Path) -> None:
        self._bench_detail.load(path)
        self._stack.setCurrentIndex(self._bench_detail_index)

    # --- theme -------------------------------------------------------

    def _on_theme_toggled(self, theme: str) -> None:
        """Handle a click on the stats-banner theme button.

        Swaps the application stylesheet live, re-tints sidebar icons for
        the new palette, and persists the choice so the next launch opens
        in the same theme.
        """
        if theme not in ("dark", "light"):
            return
        typed_theme: preferences.Theme = "light" if theme == "light" else "dark"
        self._theme = typed_theme

        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setStyleSheet(stylesheet(typed_theme))

        # Re-tint sidebar icons so they stay legible on the new palette.
        for row, (_, _, icon_name) in enumerate(_SIDEBAR_ENTRIES):
            item = self._sidebar.item(row)
            if item is not None:
                item.setIcon(icon(icon_name, theme=typed_theme))

        preferences.set_theme(typed_theme)

    # --- shutdown ----------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 — Qt override
        """Stop every running bench when the user closes the window."""
        self._process_manager.stop_all()
        super().closeEvent(event)
