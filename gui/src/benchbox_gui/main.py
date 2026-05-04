"""benchbox-gui entrypoint."""

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
    # Load saved theme (defaults to dark on first run).
    app.setStyleSheet(stylesheet(preferences.get_theme()))

    window = MainWindow()
    # ``closeEvent`` covers the user clicking the X. ``aboutToQuit`` covers
    # everything else — quit-from-dock, signal, taskmanager kill on macOS,
    # OS-level logout. Both run ``stop_all`` so no `bench start` outlives
    # the GUI.
    app.aboutToQuit.connect(window.shutdown_processes)
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
