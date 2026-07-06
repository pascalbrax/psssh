"""Resolve pyte's fg/bg color values (named / 256 / truecolor) to QColor, and
the named terminal color schemes ("themes") the user can pick between.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import pyte.graphics
from PyQt6.QtGui import QColor

_NAMES = [
    "black", "red", "green", "brown", "blue", "magenta", "cyan", "white",
    "brightblack", "brightred", "brightgreen", "brightbrown",
    "brightblue", "brightmagenta", "brightcyan", "brightwhite",
]

# The classic xterm 16-color palette, used by the "System" and "Gray" themes.
XTERM_NAMED_HEX = dict(zip(_NAMES, pyte.graphics.FG_BG_256[:16]))

# Solarized (https://ethanschoonover.com/solarized/) redefines the 16 ANSI
# colors to a single muted palette that's shared by both its light and dark
# variants - only the terminal's own default fg/bg differ between them.
SOLARIZED_NAMED_HEX = {
    "black": "073642", "red": "dc322f", "green": "859900", "brown": "b58900",
    "blue": "268bd2", "magenta": "d33682", "cyan": "2aa198", "white": "eee8d5",
    "brightblack": "002b36", "brightred": "cb4b16", "brightgreen": "586e75",
    "brightbrown": "657b83", "brightblue": "839496", "brightmagenta": "6c71c4",
    "brightcyan": "93a1a1", "brightwhite": "fdf6e3",
}


@dataclass(frozen=True)
class TerminalPalette:
    default_fg: str
    default_bg: str
    named: Dict[str, str]
    cursor_hex: str


PALETTES: Dict[str, TerminalPalette] = {
    "system": TerminalPalette(default_fg="e5e5e5", default_bg="0c0c0c",
                               named=XTERM_NAMED_HEX, cursor_hex="ffffff"),
    "gray": TerminalPalette(default_fg="e5e5e5", default_bg="0c0c0c",
                             named=XTERM_NAMED_HEX, cursor_hex="ffffff"),
    "solarized": TerminalPalette(default_fg="657b83", default_bg="fdf6e3",
                                  named=SOLARIZED_NAMED_HEX, cursor_hex="002b36"),
    "solarized_dark": TerminalPalette(default_fg="839496", default_bg="002b36",
                                       named=SOLARIZED_NAMED_HEX, cursor_hex="fdf6e3"),
}
DEFAULT_PALETTE_KEY = "system"


def palette_for(theme: str) -> TerminalPalette:
    return PALETTES.get(theme, PALETTES[DEFAULT_PALETTE_KEY])


def resolve(value: str, default_hex: str, named: Dict[str, str] = XTERM_NAMED_HEX) -> QColor:
    if not value or value == "default":
        return QColor(f"#{default_hex}")
    if value in named:
        return QColor(f"#{named[value]}")
    if len(value) == 6:
        try:
            int(value, 16)
            return QColor(f"#{value}")
        except ValueError:
            pass
    return QColor(f"#{default_hex}")
