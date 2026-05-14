"""Main window."""

from __future__ import annotations

from collections.abc import Callable
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
from benchbox_gui.views.bench_detail import BenchDetailView
from benchbox_gui.views.bench_list import BenchListView
from benchbox_gui.views.stats_banner import StatsBanner

# (label, page key, icon name)
_SIDEBAR_ENTRIES: tuple[tuple[str, str, str], ...] = (
    ("Benches", "benches", "benches"),
    ("Install", "install", "install"),
    ("Sites", "sites", "sites"),
    ("Apps", "apps", "apps"),
    ("Databases", "databases", "databases"),
    ("Logs", "logs", "logs"),
    ("Documentation", "docs", "docs"),
    ("Settings", "settings", "settings"),
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("benchbox")
        # Wider default — the bench detail page now packs a status row,
        # action buttons, URL link, and a live log into each site tab.
        self.resize(1480, 880)
        self.setMinimumSize(1100, 680)

        self._theme: preferences.Theme = preferences.get_theme()
        self._process_manager = BenchProcessManager(self)

        self._stack = QStackedWidget()
        self._pages: dict[str, int] = {}
        # Lazy page construction — the heavy views (Sites/Apps/Databases/Install/
        # docs) each spawn subprocesses or warm DB connections on first build,
        # so we only build them on first sidebar click. Cuts startup RAM/CPU.
        self._page_factories: dict[str, Callable[[], QWidget]] = {
            "install": self._build_installer,
            "sites": self._build_lazy("benchbox_gui.views.sites", "SitesView"),
            "apps": self._build_lazy("benchbox_gui.views.apps", "AppsView"),
            "databases": self._build_lazy(
                "benchbox_gui.views.databases", "DatabasesView"
            ),
            "logs": self._build_lazy("benchbox_gui.views.logs_view", "LogsView"),
            "docs": self._build_lazy(
                "benchbox_gui.views.docs_view", "DocumentationView"
            ),
            "settings": self._build_settings,
        }

        # Benches is the default landing page, so build it eagerly.
        self._bench_list = BenchListView(self._process_manager)
        self._bench_list.bench_selected.connect(self._on_bench_selected)
        self._pages["benches"] = self._stack.addWidget(self._bench_list)

        # Detail view is lazy: built on the first bench card click.
        self._bench_detail: BenchDetailView | None = None
        self._bench_detail_index: int | None = None
        # Installer is lazy: only constructed on first Install-tab click. The
        # reference is kept so shutdown can still ping it.
        self._installer = None  # type: ignore[var-annotated]

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

    def _show_page(self, key: str) -> None:
        if key not in self._pages:
            factory = self._page_factories.get(key)
            if factory is None:
                return
            widget = factory()
            self._pages[key] = self._stack.addWidget(widget)
        self._stack.setCurrentIndex(self._pages[key])

    def _on_sidebar_row_changed(self, row: int) -> None:
        if 0 <= row < len(_SIDEBAR_ENTRIES):
            self._show_page(_SIDEBAR_ENTRIES[row][1])

    def _on_bench_selected(self, path: Path) -> None:
        if self._bench_detail is None:
            self._bench_detail = BenchDetailView(self._process_manager)
            self._bench_detail.back_requested.connect(
                lambda: self._show_page("benches")
            )
            self._bench_detail_index = self._stack.addWidget(self._bench_detail)
        self._bench_detail.load(path)
        assert self._bench_detail_index is not None
        self._stack.setCurrentIndex(self._bench_detail_index)

    @staticmethod
    def _build_lazy(module: str, attr: str) -> Callable[[], QWidget]:
        """Return a factory that imports `module.attr` on first call.

        Deferring the import as well as the construction keeps PySide6 widget
        modules (and their transitive deps like psutil for the dashboard
        views) out of startup.
        """

        def factory() -> QWidget:
            mod = __import__(module, fromlist=[attr])
            cls = getattr(mod, attr)
            return cls()

        return factory

    def _build_installer(self) -> QWidget:
        from benchbox_gui.views.install import InstallerView

        self._installer = InstallerView()
        return self._installer

    def _build_settings(self) -> QWidget:
        from benchbox_gui.views.settings_view import SettingsView

        view = SettingsView()
        view.accent_changed.connect(self._on_accent_changed)
        return view

    def _on_accent_changed(self, name: str) -> None:
        if name not in {"purple", "blue", "green", "orange", "pink", "red"}:
            return
        self.apply_accent(name)  # type: ignore[arg-type]

    # --- theme -------------------------------------------------------

    def _on_theme_toggled(self, theme: str) -> None:
        if theme not in ("dark", "light"):
            return
        typed_theme: preferences.Theme = "light" if theme == "light" else "dark"
        self._theme = typed_theme

        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setStyleSheet(stylesheet(typed_theme, preferences.get_accent()))

        for row, (_, _, icon_name) in enumerate(_SIDEBAR_ENTRIES):
            item = self._sidebar.item(row)
            if item is not None:
                item.setIcon(icon(icon_name, theme=typed_theme))

        preferences.set_theme(typed_theme)

    def apply_accent(self, accent: preferences.Accent) -> None:
        """Re-skin every live widget with the new accent color."""
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setStyleSheet(stylesheet(self._theme, accent))

    # --- shutdown ----------------------------------------------------

    def shutdown_processes(self) -> None:
        self._process_manager.stop_all()
        # Walk every built widget in the stack and ping its shutdown() hook
        # if it has one. Catches DatabasesView, InstallerView, BenchDetailView,
        # plus any future page that owns a background worker.
        seen: set[int] = set()
        for i in range(self._stack.count()):
            widget = self._stack.widget(i)
            if widget is None or id(widget) in seen:
                continue
            seen.add(id(widget))
            shutdown = getattr(widget, "shutdown", None)
            if callable(shutdown):
                shutdown()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.shutdown_processes()
        super().closeEvent(event)
