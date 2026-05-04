"""GUI entrypoint."""

from __future__ import annotations

import sys

from benchbox_core import logs, preferences
from PySide6.QtWidgets import QApplication

from benchbox_gui.main_window import MainWindow
from benchbox_gui.resources import stylesheet


def main() -> int:
    logs.init_session()
    app = QApplication(sys.argv)
    app.setApplicationName("benchbox")
    app.setOrganizationName("benchbox")
    app.setStyleSheet(stylesheet(preferences.get_theme()))

    window = MainWindow()
    # closeEvent covers the X button; aboutToQuit covers signals, dock-quit,
    # session logout. Either way, stop running benches before exit.
    app.aboutToQuit.connect(window.shutdown_processes)
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
