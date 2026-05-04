"""Detail view for a single bench — the working canvas for one bench.

Layout (top → bottom):

- :class:`BenchDetailHeader` — sticky, holds back / title / + Add ▾ /
  Bench ▾ / Open folder.
- :class:`QTabWidget` — the working area:
    * **Apps** tab (always first) — :class:`AppCard` grid for every app
      registered in the bench, with per-card install / uninstall / remove
      actions.
    * One :class:`SiteTab` per site — clickable URL, app badges, quick
      chips, and a :class:`BenchCommandRunner` whose chips are scoped to
      that site.
    * **Free terminal** tab (always last) — bench-wide command runner
      with no site locked; used for ``bench migrate`` / ``bench update``
      etc.
- :class:`BenchProcessDock` — sticky bottom, owns Start/Stop and the
  collapsible bench-start log.

Signal flow: child widgets emit typed signals; this view sequences the
dialogs, ``QInputDialog`` confirms, and operation workers, then calls
:meth:`refresh` so the tabs re-render with fresh introspection data.
"""

from __future__ import annotations

from pathlib import Path

from benchbox_core import app as core_app
from benchbox_core import credentials, discovery, introspect
from benchbox_core import site as core_site
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QProgressDialog,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from benchbox_gui.services.bench_processes import BenchProcessManager
from benchbox_gui.widgets.app_card import AppCard
from benchbox_gui.widgets.bench_actions import open_in_file_manager
from benchbox_gui.widgets.bench_detail_header import BenchDetailHeader
from benchbox_gui.widgets.bench_process_dock import BenchProcessDock
from benchbox_gui.widgets.card_grid import CardGrid
from benchbox_gui.widgets.command_runner import BenchCommandRunner
from benchbox_gui.widgets.dialogs import (
    GetAppDialog,
    InstallAppDialog,
    NewAppDialog,
    NewSiteDialog,
    RestoreSiteDialog,
    TypedNameConfirmDialog,
)
from benchbox_gui.widgets.site_tab import SiteTab
from benchbox_gui.workers import OperationWorker

# Tab labels for the two non-site tabs. Site tabs use the site name.
_APPS_TAB_LABEL = "Apps"
_FREE_TAB_LABEL = "Free terminal"


def _v_scroll(content: QWidget) -> QScrollArea:
    """Wrap ``content`` in a vertical-only scroll area.

    Horizontal scroll is forbidden — the user wants long content to
    expand downward rather than off the right edge of the window.
    """
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setWidget(content)
    return scroll


class BenchDetailView(QWidget):
    """Single home for every per-bench mutation, organised as tabs."""

    back_requested = Signal()

    def __init__(
        self,
        process_manager: BenchProcessManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._process_manager = process_manager
        self._current_path: Path | None = None
        self._info: introspect.BenchInfo | None = None
        # Active SiteTab widgets keyed by site name. Lets us preserve
        # per-site state (log buffer, in-flight command) across refreshes
        # so the user doesn't lose `migrate` output mid-run if some
        # unrelated event triggers a reload.
        self._site_tabs: dict[str, SiteTab] = {}
        # Spinner for fast mutations (drop / uninstall / remove); long
        # ones use the live-log dialogs and don't touch this.
        self._worker: OperationWorker | None = None
        self._progress: QProgressDialog | None = None

        # ---- sticky top header -------------------------------------
        self._header = BenchDetailHeader()
        self._header.back_requested.connect(self.back_requested.emit)
        self._header.open_folder_requested.connect(self._on_open_folder)
        self._header.new_site_requested.connect(self._on_new_site)
        self._header.get_app_requested.connect(self._on_get_app)
        self._header.new_app_requested.connect(self._on_new_app)
        self._header.restore_site_requested.connect(self._on_restore_site)
        self._header.update_requested.connect(self._on_bench_update)
        self._header.migrate_all_requested.connect(self._on_migrate_all)
        self._header.restart_requested.connect(self._on_bench_restart)

        # ---- main tab strip ----------------------------------------
        self._tabs = QTabWidget()
        self._tabs.setMovable(False)
        self._tabs.setTabsClosable(False)
        self._tabs.setUsesScrollButtons(True)
        self._tabs.setDocumentMode(True)

        # Apps tab — populated in load(). Wrapped in a vertical-scroll
        # area so a many-app bench scrolls cleanly without ever forcing
        # horizontal scroll on the page.
        self._apps_grid = CardGrid()
        apps_inner = QWidget()
        apps_layout = QVBoxLayout(apps_inner)
        apps_layout.setContentsMargins(16, 16, 16, 16)
        apps_layout.addWidget(self._apps_grid, 1)
        self._tabs.addTab(_v_scroll(apps_inner), _APPS_TAB_LABEL)

        # Free terminal tab — bench-wide commands, no site lock.
        self._free_runner = BenchCommandRunner()
        free_inner = QWidget()
        free_layout = QVBoxLayout(free_inner)
        free_layout.setContentsMargins(16, 16, 16, 16)
        free_layout.addWidget(self._free_runner, 1)
        self._tabs.addTab(_v_scroll(free_inner), _FREE_TAB_LABEL)

        # ---- sticky bottom dock ------------------------------------
        self._dock = BenchProcessDock(process_manager)
        self._dock.start_requested.connect(self._on_start)
        self._dock.stop_requested.connect(self._on_stop)

        # ---- assembly ----------------------------------------------
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header)
        layout.addWidget(self._tabs, 1)
        layout.addWidget(self._dock)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # --- loading ------------------------------------------------------

    def load(self, path: Path) -> None:
        """(Re)render the entire detail view for ``path``.

        Drops every site tab and rebuilds them from fresh introspection.
        Apps tab + Free terminal tab are repopulated in place.
        """
        self._current_path = path
        self._info = introspect.introspect(path)
        info = self._info

        self._header.set_bench(
            path=str(info.path),
            frappe_version=info.frappe_version,
            python_version=info.python_version,
            git_branch=info.git_branch,
        )

        self._dock.set_bench(path, webserver_port=info.webserver_port)

        # Apps tab — rebuild card grid in place. Skip the bench-path
        # label on each card; every app here belongs to the same bench
        # so the path would just repeat itself ``len(info.apps)`` times.
        app_cards: list[QWidget] = []
        for app in info.apps:
            card = AppCard(path, app, show_bench_path=False)
            card.install_requested.connect(self._on_install_from_app_card)
            card.uninstall_requested.connect(self._on_uninstall_requested)
            card.remove_requested.connect(self._on_remove_requested)
            app_cards.append(card)
        self._apps_grid.set_cards(app_cards)

        # Free terminal — refresh bench path + site list (for chip
        # suggestions, even though no site is locked).
        self._free_runner.set_bench(path, [s.name for s in info.sites])

        # Site tabs — drop old, build fresh. Order: Apps, [site tabs],
        # Free terminal.
        self._rebuild_site_tabs(info, path)

    def _rebuild_site_tabs(self, info: introspect.BenchInfo, path: Path) -> None:
        """Replace every site tab with a fresh SiteTab per site.

        Removes existing site tabs in reverse order (so QTabWidget
        indices stay valid as we tear down). The Apps tab (index 0) and
        Free terminal tab (last) are left in place.
        """
        # Tear down in reverse so indices are stable while we iterate.
        # SiteTab lives wrapped inside a QScrollArea — call shutdown via
        # the bookkeeping dict instead of probing the wrapper.
        for tab in self._site_tabs.values():
            tab.shutdown()
        for i in range(self._tabs.count() - 2, 0, -1):
            widget = self._tabs.widget(i)
            self._tabs.removeTab(i)
            if widget is not None:
                widget.deleteLater()
        self._site_tabs.clear()

        # Insert each site tab between Apps (index 0) and Free terminal
        # (currently the last tab). SiteTab is wrapped in a vertical
        # scroll area so chip rows + a long command-runner buffer never
        # force horizontal scroll.
        free_index = self._tabs.count() - 1
        for offset, site in enumerate(info.sites):
            tab = SiteTab(path, site, webserver_port=info.webserver_port)
            tab.drop_requested.connect(self._on_drop_site)
            insert_at = 1 + offset
            self._tabs.insertTab(insert_at, _v_scroll(tab), site.name)
            self._tabs.setTabToolTip(insert_at, f"Working context: {site.name}")
            self._site_tabs[site.name] = tab
            # Keep the free-terminal index up-to-date so we never
            # accidentally insert past it.
            free_index = insert_at + 1

        # Sanity: Apps stays selected on first load; later refreshes
        # respect the user's current tab where possible.
        if self._tabs.currentIndex() < 0 or self._tabs.currentIndex() > free_index:
            self._tabs.setCurrentIndex(0)

    # --- bench-process actions ---------------------------------------

    def _on_start(self) -> None:
        if self._current_path is not None:
            self._process_manager.start(self._current_path)

    def _on_stop(self) -> None:
        if self._current_path is not None:
            self._process_manager.stop(self._current_path)

    def _on_open_folder(self) -> None:
        if self._current_path is not None:
            open_in_file_manager(self._current_path)

    # --- bench-level chores from the header dropdown -----------------

    def _on_bench_update(self) -> None:
        self._prefill_free_runner("bench update")

    def _on_migrate_all(self) -> None:
        self._prefill_free_runner("bench migrate")

    def _on_bench_restart(self) -> None:
        self._prefill_free_runner("bench restart")

    def _prefill_free_runner(self, command: str) -> None:
        """Drop ``command`` into the bench-wide runner and switch tabs.

        Bench-level chores are heavy enough that we want the user to
        review/Enter rather than fire-and-forget. The Free terminal tab
        is the natural home for non-site commands, so we open it pointed
        at the right command and let the user confirm.
        """
        # Free terminal is the last tab; switch the user there so they
        # see the prefilled command.
        free_index = self._tabs.count() - 1
        self._tabs.setCurrentIndex(free_index)
        self._free_runner._input.setText(command)  # noqa: SLF001
        self._free_runner._input.setFocus()  # noqa: SLF001

    # --- shared helpers ----------------------------------------------

    def _ensure_mariadb_password(self) -> str | None:
        saved = credentials.get_mariadb_root_password()
        if saved is not None:
            return saved
        QMessageBox.warning(
            self,
            "MariaDB password missing",
            "No MariaDB root password is saved yet. Run the installer "
            "from the sidebar once to set it.",
        )
        return None

    def _refresh_after_op(self) -> None:
        if self._current_path is not None:
            self.load(self._current_path)

    # --- header dropdown handlers (long ops via LiveLogDialog) -------

    def _on_new_site(self) -> None:
        if self._current_path is None:
            return
        db_root = self._ensure_mariadb_password()
        if db_root is None:
            return
        dialog = NewSiteDialog(
            [self._current_path],
            db_root_password=db_root,
            preselect=self._current_path,
            parent=self,
        )
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._refresh_after_op()
            # Try to switch to the newly-created site tab so the user
            # immediately sees their new working context.
            values = getattr(dialog, "_values", None)
            new_name = getattr(values, "site_name", None) if values is not None else None
            if isinstance(new_name, str) and new_name in self._site_tabs:
                # Tab widget is the scroll wrapper, not the SiteTab; walk
                # tabs by label since that's what we set when inserting.
                for i in range(self._tabs.count()):
                    if self._tabs.tabText(i) == new_name:
                        self._tabs.setCurrentIndex(i)
                        break

    def _on_get_app(self) -> None:
        if self._current_path is None:
            return
        dialog = GetAppDialog([self._current_path], preselect=self._current_path, parent=self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._refresh_after_op()

    def _on_new_app(self) -> None:
        if self._current_path is None:
            return
        dialog = NewAppDialog([self._current_path], preselect=self._current_path, parent=self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._refresh_after_op()

    def _on_restore_site(self) -> None:
        if self._current_path is None or self._info is None:
            return
        sites = [s.name for s in self._info.sites]
        if not sites:
            QMessageBox.information(
                self,
                "No sites",
                "This bench has no sites to restore into. Create a site first.",
            )
            return
        db_root = self._ensure_mariadb_password()
        if db_root is None:
            return
        dialog = RestoreSiteDialog(
            {self._current_path: sites},
            db_root_password=db_root,
            parent=self,
            preselect_bench=self._current_path,
        )
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._refresh_after_op()

    # --- per-card actions: install (long) ---------------------------

    def _on_install_from_app_card(self, bench_path: Path, app_name: str) -> None:
        self._open_install_dialog(preselect_bench=bench_path, preselect_app=app_name)

    def _open_install_dialog(
        self,
        *,
        preselect_bench: Path | None = None,
        preselect_site: str | None = None,
        preselect_app: str | None = None,
    ) -> None:
        if self._current_path is None or self._info is None:
            return
        bench_sites = {self._current_path: [s.name for s in self._info.sites]}
        bench_apps = {self._current_path: [a.name for a in self._info.apps]}
        dialog = InstallAppDialog(
            bench_sites,
            bench_apps,
            preselect_bench=preselect_bench or self._current_path,
            preselect_site=preselect_site,
            preselect_app=preselect_app,
            parent=self,
        )
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._refresh_after_op()

    # --- per-card actions: uninstall / remove / drop (fast → spinner)

    def _on_uninstall_requested(self, bench_path: Path, app_name: str) -> None:
        if self._info is None:
            return
        site_names = [s.name for s in self._info.sites]
        if not site_names:
            QMessageBox.information(
                self,
                "No sites",
                f"{bench_path} has no sites to uninstall {app_name} from.",
            )
            return
        site, ok = QInputDialog.getItem(
            self,
            "Uninstall app",
            f"Uninstall <b>{app_name}</b> from which site?",
            site_names,
            0,
            False,
        )
        if not ok or not site:
            return
        confirm_target = f"{app_name}@{site}"
        confirm = TypedNameConfirmDialog(
            confirm_target,
            title="Uninstall app",
            message=(
                f"This detaches <b>{app_name}</b> from <b>{site}</b>, including "
                "any data the app owns on that site. The app stays in the "
                "bench's <code>apps/</code> directory."
            ),
            action_label="Uninstall",
            parent=self,
        )
        if confirm.exec() != confirm.DialogCode.Accepted:
            return
        self._open_progress(f"Uninstalling {app_name} from {site}…")
        self._spawn(
            lambda: core_app.uninstall_app(bench_path, site, app_name),
            success_msg=f"Uninstalled {app_name} from {site}.",
        )

    def _on_remove_requested(self, bench_path: Path, app_name: str) -> None:
        confirm = TypedNameConfirmDialog(
            app_name,
            title="Remove app from bench",
            message=(
                f"This removes <b>{app_name}</b> entirely from <code>{bench_path}</code>. "
                "Sites that still have it installed will continue to work at runtime, "
                "but <code>bench get-app</code> is what puts it back. This can't be undone."
            ),
            action_label="Remove from bench",
            parent=self,
        )
        if confirm.exec() != confirm.DialogCode.Accepted:
            return
        self._open_progress(f"Removing {app_name} from bench…")
        self._spawn(
            lambda: core_app.remove_app(bench_path, app_name),
            success_msg=f"Removed {app_name} from bench.",
        )

    def _on_drop_site(self, bench_path: Path, site_name: str) -> None:
        confirm = TypedNameConfirmDialog(
            site_name,
            title="Drop site",
            message=(
                f"This permanently deletes <b>{site_name}</b> on "
                f"<code>{bench_path}</code>, including its MariaDB database. "
                "This can't be undone."
            ),
            action_label="Drop site",
            parent=self,
        )
        if confirm.exec() != confirm.DialogCode.Accepted:
            return
        db_root = self._ensure_mariadb_password()
        if db_root is None:
            return
        self._open_progress(f"Dropping {site_name}…")
        self._spawn(
            lambda: core_site.drop_site(bench_path, site_name, db_root_password=db_root),
            success_msg=f"Site {site_name!r} dropped.",
        )

    # --- spinner plumbing for fast mutations -------------------------

    def _open_progress(self, message: str) -> None:
        self._progress = QProgressDialog(self)
        self._progress.setLabelText(message)
        self._progress.setWindowTitle("Working…")
        self._progress.setMinimum(0)
        self._progress.setMaximum(0)
        self._progress.setMinimumDuration(0)
        self._progress.setCancelButton(None)
        self._progress.show()

    def _close_progress(self) -> None:
        if self._progress is not None:
            self._progress.close()
            self._progress = None

    def _spawn(self, op: object, *, success_msg: str) -> None:
        self._worker = OperationWorker(op)  # type: ignore[arg-type]
        self._worker.succeeded.connect(lambda _r, msg=success_msg: self._on_short_op_success(msg))
        self._worker.failed.connect(self._on_short_op_failure)
        self._worker.start()

    def _on_short_op_success(self, message: str) -> None:
        self._close_progress()
        # After a drop, prefer landing on the Apps tab so the user isn't
        # staring at a now-stale site tab.
        self._tabs.setCurrentIndex(0)
        self._refresh_after_op()
        QMessageBox.information(self, "Done", message)

    def _on_short_op_failure(self, exc: object) -> None:
        self._close_progress()
        QMessageBox.critical(self, "Operation failed", f"{exc}")

    # --- shutdown hook -----------------------------------------------

    def shutdown(self) -> None:
        """Kill any in-flight runner command in any tab.

        ``BenchProcessManager`` cleans up its own bench-start processes;
        this only covers the per-tab :class:`BenchCommandRunner`s that
        own their own QProcess outside the manager.
        """
        self._free_runner.shutdown()
        for tab in self._site_tabs.values():
            tab.shutdown()


# Re-export discovery for any caller that previously imported it from
# this module by accident; keeps refactor surface small.
__all__ = ["BenchDetailView", "discovery"]
