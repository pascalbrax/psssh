"""Application bootstrap."""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from . import __version__
from .icon import app_icon
from .main_window import MainWindow
from .settings import AppSettings
from .theme import apply_theme, capture_defaults


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("psssh")
    app.setOrganizationName("psssh")
    app.setApplicationDisplayName("Pascal Simple SSH")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())
    capture_defaults(app)
    apply_theme(app, AppSettings().theme)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
