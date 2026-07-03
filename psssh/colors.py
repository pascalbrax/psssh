"""Resolve pyte's fg/bg color values (named / 256 / truecolor) to QColor."""
from __future__ import annotations

import pyte.graphics
from PyQt6.QtGui import QColor

_NAMES = [
    "black", "red", "green", "brown", "blue", "magenta", "cyan", "white",
    "brightblack", "brightred", "brightgreen", "brightbrown",
    "brightblue", "brightmagenta", "brightcyan", "brightwhite",
]
NAMED_COLOR_HEX = dict(zip(_NAMES, pyte.graphics.FG_BG_256[:16]))

DEFAULT_FG = "e5e5e5"
DEFAULT_BG = "0c0c0c"


def resolve(value: str, default_hex: str) -> QColor:
    if not value or value == "default":
        return QColor(f"#{default_hex}")
    if value in NAMED_COLOR_HEX:
        return QColor(f"#{NAMED_COLOR_HEX[value]}")
    if len(value) == 6:
        try:
            int(value, 16)
            return QColor(f"#{value}")
        except ValueError:
            pass
    return QColor(f"#{default_hex}")
