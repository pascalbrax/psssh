"""App icon lookup."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QIcon

_ICON_PATH = Path(__file__).parent / "assets" / "icon.ico"


def app_icon() -> QIcon:
    return QIcon(str(_ICON_PATH))
