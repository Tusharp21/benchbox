"""Per-bench dev-command runner — the second pane of the bench terminal.

A QPlainTextEdit on top shows merged stdout/stderr from whatever command
is in flight; a row of quick-chip buttons + a free-form input line let the
user fire ``bench`` commands inside the bench's working directory. Each
command runs through :class:`PySide6.QtCore.QProcess` with the same
nvm-bootstrap shell used for ``bench start``, so Frappe sees Node 18 even
when the system PATH only has Node 12.

Owns at most one in-flight :class:`QProcess` at a time; ``set_bench``
swaps the working directory and clears the buffer but never kills a
running command. ``shutdown`` is the cleanup hook the main window calls
on quit so a half-finished ``bench migrate`` doesn't outlive the GUI.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Same nvm bootstrap as the long-running bench-start path. We exec the
# user's command through bash so PATH is set up identically; otherwise
# yarn (and bench's pip-resolver) would pick up Node 12 from /usr/bin.
_NVM_BOOTSTRAP_PREFIX: str = (
    'if [ -s "$HOME/.nvm/nvm.sh" ]; then '
    'export NVM_DIR="$HOME/.nvm"; '
    '. "$NVM_DIR/nvm.sh"; '
    "fi; "
    "exec "
)

# Quick-action buttons: (label, command-builder). The builder gets the
# selected site name (may be ``""`` when no site is selected) and returns
# the bench command to drop into the input field. We pre-fill rather than
# fire-and-forget so the user can review/edit the command first — bench
# mutations are heavy and unwinding a wrong one is annoying.
QuickAction = tuple[str, Callable[[str], str]]

DEFAULT_QUICK_ACTIONS: tuple[QuickAction, ...] = (
    ("Update bench", lambda _site: "bench update"),
    (
        "Migrate",
        lambda site: f"bench --site {site} migrate" if site else "bench migrate",
    ),
    ("Restart", lambda _site: "bench restart"),
    (
        "Clear cache",
        lambda site: (
            f"bench --site {site} clear-cache" if site else "bench clear-cache"
        ),
    ),
    (
        "Clear website cache",
        lambda site: (
            f"bench --site {site} clear-website-cache"
            if site
            else "bench clear-website-cache"
        ),
    ),
    ("Help", lambda _site: "bench --help"),
)

# Cap the runner's history; long pip resolves can spew thousands of lines.
MAX_LOG_BLOCKS: int = 5000


class BenchCommandRunner(QWidget):
    """Editable command line + log pane scoped to one bench directory.

    Signals:
        command_started(str): emitted with the literal command line just
            before the process spawns. Useful for tests.
        command_finished(int): emitted with the exit code after the
            process exits. -1 indicates the process failed to spawn.
    """

    command_started = Signal(str)
    command_finished = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        locked_site: str | None = None,
        show_chips: bool = True,
    ) -> None:
        super().__init__(parent)
        self._bench_path: Path | None = None
        self._site_names: list[str] = []
        # When set, the dropdown is hidden and every chip-builder receives
        # this site as its argument. The tab's label already tells the user
        # which site they're acting on, so a redundant dropdown would just
        # be noise. Free-form input still runs verbatim.
        self._locked_site: str | None = locked_site
        # SiteTab has its own action grid (Migrate / Clear cache / etc.)
        # — chips would duplicate those buttons, so callers that already
        # render those actions elsewhere set ``show_chips=False`` to keep
        # the runner focused on free-form input.
        self._show_chips: bool = show_chips
        # Lazy-import keeps the widget testable without importing QtCore
        # at module load when only the pure-Python helpers are used.
        from PySide6.QtCore import QProcess

        self._process_cls = QProcess
        self._process: QProcess | None = None

        # ----- top row: site selector + status text ------------------
        site_label = QLabel("site:")
        site_label.setProperty("role", "dim")
        self._site_label = site_label
        self._site_select = QComboBox()
        self._site_select.setMinimumWidth(180)
        self._site_select.addItem("(no site selected)", "")
        if locked_site is not None:
            self._site_label.setVisible(False)
            self._site_select.setVisible(False)

        self._status = QLabel("idle")
        self._status.setProperty("role", "dim")

        site_row = QHBoxLayout()
        site_row.setContentsMargins(0, 0, 0, 0)
        site_row.setSpacing(8)
        site_row.addWidget(site_label)
        site_row.addWidget(self._site_select)
        site_row.addStretch(1)
        site_row.addWidget(self._status)

        # ----- quick chip row ----------------------------------------
        # Skipped entirely (rather than just hidden) when ``show_chips``
        # is False so the row doesn't even reserve vertical space — the
        # SiteTab embedding wants the runner as compact as possible.
        self._chip_row = QHBoxLayout()
        self._chip_row.setContentsMargins(0, 0, 0, 0)
        self._chip_row.setSpacing(6)
        if show_chips:
            for label, builder in DEFAULT_QUICK_ACTIONS:
                btn = QPushButton(label)
                btn.setProperty("role", "ghost")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _checked=False, b=builder: self._fill_from_chip(b))
                self._chip_row.addWidget(btn)
            self._chip_row.addStretch(1)

        # ----- input + run/stop --------------------------------------
        self._input = QLineEdit()
        self._input.setPlaceholderText("bench …  (Enter to run)")
        self._input.returnPressed.connect(self._on_run_clicked)

        self._run_btn = QPushButton("Run")
        self._run_btn.setProperty("role", "primary")
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.clicked.connect(self._on_run_clicked)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setProperty("role", "danger")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        self._cancel_btn.setEnabled(False)

        clear_btn = QPushButton("Clear")
        clear_btn.setProperty("role", "ghost")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self._clear_log)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(6)
        input_row.addWidget(self._input, 1)
        input_row.addWidget(self._run_btn)
        input_row.addWidget(self._cancel_btn)
        input_row.addWidget(clear_btn)

        # ----- output pane -------------------------------------------
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(MAX_LOG_BLOCKS)
        mono = QFont("JetBrains Mono, Fira Code, Courier New", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._log.setFont(mono)
        self._log.setPlaceholderText(
            "Run a quick-chip command above, or type any bench command and press Enter."
        )
        self._log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # ----- assembly ----------------------------------------------
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(site_row)
        if show_chips:
            layout.addLayout(self._chip_row)
        layout.addLayout(input_row)
        layout.addWidget(self._log, 1)

        # Start disabled — set_bench(path) re-enables once we know which
        # working directory to spawn into.
        self._set_enabled_for_bench(False)

    # --- public API ---------------------------------------------------

    def set_bench(self, path: Path | None, site_names: list[str] | None = None) -> None:
        """Switch which bench this runner targets.

        Does *not* kill an in-flight process; the user can navigate away
        from a bench while ``bench update`` is running and come back later
        to see the result. Buffer is cleared per-bench to keep the runner
        scoped to whichever bench the user is actively looking at.
        """
        new_path = path.resolve() if path is not None else None
        bench_changed = new_path != self._bench_path
        self._bench_path = new_path
        self._site_names = list(site_names or [])

        self._site_select.blockSignals(True)
        self._site_select.clear()
        self._site_select.addItem("(no site selected)", "")
        for name in self._site_names:
            self._site_select.addItem(name, name)
        self._site_select.blockSignals(False)

        if bench_changed:
            self._log.clear()
            self._input.clear()

        self._set_enabled_for_bench(new_path is not None)

    def _set_enabled_for_bench(self, has_bench: bool) -> None:
        idle = self._process is None
        self._input.setEnabled(has_bench and idle)
        self._run_btn.setEnabled(has_bench and idle)
        for i in range(self._chip_row.count()):
            item = self._chip_row.itemAt(i)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setEnabled(has_bench)

    def shutdown(self) -> None:
        """Kill any in-flight command — called by the main window on quit."""
        if self._process is None:
            return
        self._process.terminate()
        if not self._process.waitForFinished(2000):
            self._process.kill()
            self._process.waitForFinished(1000)
        self._process = None

    def is_busy(self) -> bool:
        return self._process is not None

    # --- chip / input plumbing ---------------------------------------

    def _selected_site(self) -> str:
        if self._locked_site is not None:
            return self._locked_site
        return str(self._site_select.currentData() or "")

    def _fill_from_chip(self, builder: Callable[[str], str]) -> None:
        if self._bench_path is None:
            return
        self._input.setText(builder(self._selected_site()))
        self._input.setFocus()

    def _on_run_clicked(self) -> None:
        if self._bench_path is None or self._process is not None:
            return
        command = self._input.text().strip()
        if not command:
            return
        self._spawn(command)

    def _on_cancel_clicked(self) -> None:
        if self._process is None:
            return
        self._append("\n^C  (cancelling…)\n")
        self._process.terminate()

    def _clear_log(self) -> None:
        self._log.clear()

    # --- subprocess management ---------------------------------------

    def _spawn(self, command: str) -> None:
        assert self._bench_path is not None
        process = self._process_cls(self)
        process.setWorkingDirectory(str(self._bench_path))
        process.setProcessChannelMode(self._process_cls.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._drain_output)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)

        self._process = process
        self._set_busy_ui(True)
        self._append(f"$ {command}\n")
        self.command_started.emit(command)
        # bash -c so the nvm bootstrap runs before bench, and so the user
        # can pipe / chain commands naturally.
        process.start("bash", ["-c", _NVM_BOOTSTRAP_PREFIX + command])

    def _drain_output(self) -> None:
        if self._process is None:
            return
        raw = bytes(self._process.readAllStandardOutput().data())
        if not raw:
            return
        text = raw.decode(errors="replace")
        self._append(text)

    def _on_finished(self, exit_code: int, _exit_status: object) -> None:
        # _exit_status is a QProcess.ExitStatus; we report exit_code only.
        self._append(f"\n[exited with code {exit_code}]\n")
        self._process = None
        self._set_busy_ui(False)
        self.command_finished.emit(exit_code)

    def _on_error(self, _err: object) -> None:
        # readyRead+finished still fire on most errors, but a missing
        # binary races ahead — make sure we always re-enable the UI.
        if self._process is None:
            return
        self._append("\n[failed to launch command]\n")
        self._process = None
        self._set_busy_ui(False)
        self.command_finished.emit(-1)

    def _set_busy_ui(self, busy: bool) -> None:
        self._run_btn.setEnabled(not busy and self._bench_path is not None)
        self._cancel_btn.setEnabled(busy)
        self._input.setEnabled(not busy and self._bench_path is not None)
        self._status.setText("running…" if busy else "idle")

    def _append(self, text: str) -> None:
        # appendPlainText auto-adds a newline; insertPlainText doesn't.
        # Process output already carries its own newlines, so insert.
        cursor = self._log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self._log.setTextCursor(cursor)
        self._log.ensureCursorVisible()


__all__ = ["BenchCommandRunner", "DEFAULT_QUICK_ACTIONS", "MAX_LOG_BLOCKS"]
