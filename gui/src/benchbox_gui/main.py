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
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
