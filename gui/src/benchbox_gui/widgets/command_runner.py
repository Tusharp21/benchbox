"""Per-bench dev-command runner."""

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

# Source nvm before exec so Frappe sees Node 18 even when /usr/bin/node
# is the apt-shipped Node 12.
_NVM_BOOTSTRAP_PREFIX: str = (
    'if [ -s "$HOME/.nvm/nvm.sh" ]; then '
    'export NVM_DIR="$HOME/.nvm"; '
    '. "$NVM_DIR/nvm.sh"; '
    "fi; "
    "exec "
)

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

MAX_LOG_BLOCKS: int = 5000


class BenchCommandRunner(QWidget):
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
        self._locked_site: str | None = locked_site
        self._show_chips: bool = show_chips
        from PySide6.QtCore import QProcess

        self._process_cls = QProcess
        self._process: QProcess | None = None

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(site_row)
        if show_chips:
            layout.addLayout(self._chip_row)
        layout.addLayout(input_row)
        layout.addWidget(self._log, 1)

        self._set_enabled_for_bench(False)

    def set_bench(self, path: Path | None, site_names: list[str] | None = None) -> None:
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
        if self._process is None:
            return
        self._process.terminate()
        if not self._process.waitForFinished(2000):
            self._process.kill()
            self._process.waitForFinished(1000)
        self._process = None

    def is_busy(self) -> bool:
        return self._process is not None

    def prefill(self, command: str) -> None:
        self._input.setText(command)
        self._input.setFocus()

    def run_command(self, real_command: str, *, display: str | None = None) -> bool:
        if self._bench_path is None or self._process is not None:
            return False
        echoed = display if display is not None else real_command
        process = self._process_cls(self)
        process.setWorkingDirectory(str(self._bench_path))
        process.setProcessChannelMode(self._process_cls.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._drain_output)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)
        self._process = process
        self._set_busy_ui(True)
        self._append(f"$ {echoed}\n")
        self.command_started.emit(echoed)
        process.start("bash", ["-c", _NVM_BOOTSTRAP_PREFIX + real_command])
        return True

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
        self._append(f"\n[exited with code {exit_code}]\n")
        self._process = None
        self._set_busy_ui(False)
        self.command_finished.emit(exit_code)

    def _on_error(self, _err: object) -> None:
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
        cursor = self._log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self._log.setTextCursor(cursor)
        self._log.ensureCursorVisible()


__all__ = ["BenchCommandRunner", "DEFAULT_QUICK_ACTIONS", "MAX_LOG_BLOCKS"]
