"""App-wide widget-chrome theme switching (native "System" look, or a custom palette)."""
from __future__ import annotations

from typing import Callable, Dict, Optional

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QStyleFactory

_default_style_name: Optional[str] = None
_default_palette: Optional[QPalette] = None


def capture_defaults(app: QApplication) -> None:
    """Remember the native style/palette once, before any theme is ever applied."""
    global _default_style_name, _default_palette
    if _default_style_name is None:
        _default_style_name = app.style().objectName()
        _default_palette = QPalette(app.palette())


def _build_palette(*, window: str, base: str, alt_base: str, text: str, disabled_text: str,
                    placeholder_text: str, button: str, highlight: str,
                    highlighted_text: str, bright_text: str) -> QPalette:
    palette = QPalette()

    def c(hex_value: str) -> QColor:
        return QColor(f"#{hex_value}")

    palette.setColor(QPalette.ColorRole.Window, c(window))
    palette.setColor(QPalette.ColorRole.WindowText, c(text))
    palette.setColor(QPalette.ColorRole.Base, c(base))
    palette.setColor(QPalette.ColorRole.AlternateBase, c(alt_base))
    palette.setColor(QPalette.ColorRole.ToolTipBase, c(text))
    palette.setColor(QPalette.ColorRole.ToolTipText, c(text))
    palette.setColor(QPalette.ColorRole.Text, c(text))
    palette.setColor(QPalette.ColorRole.PlaceholderText, c(placeholder_text))
    palette.setColor(QPalette.ColorRole.Button, c(button))
    palette.setColor(QPalette.ColorRole.ButtonText, c(text))
    palette.setColor(QPalette.ColorRole.BrightText, c(bright_text))
    palette.setColor(QPalette.ColorRole.Link, c(highlight))
    palette.setColor(QPalette.ColorRole.Highlight, c(highlight))
    palette.setColor(QPalette.ColorRole.HighlightedText, c(highlighted_text))

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, c(disabled_text))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, c(disabled_text))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, c(disabled_text))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.PlaceholderText, c(disabled_text))
    return palette


def _gray_palette() -> QPalette:
    return _build_palette(
        window="353535", base="2a2a2a", alt_base="424242", text="dcdcdc",
        disabled_text="7f7f7f", placeholder_text="969696", button="353535",
        highlight="5a8cd2", highlighted_text="141414", bright_text="ff5a5a",
    )


# Solarized (https://ethanschoonover.com/solarized/) base colors, shared by
# both variants below - only which end of the scale is "background" flips.
_SOL_BASE03, _SOL_BASE02 = "002b36", "073642"
_SOL_BASE01, _SOL_BASE00 = "586e75", "657b83"
_SOL_BASE0, _SOL_BASE1 = "839496", "93a1a1"
_SOL_BASE2, _SOL_BASE3 = "eee8d5", "fdf6e3"
_SOL_BLUE, _SOL_RED = "268bd2", "dc322f"


def _solarized_light_palette() -> QPalette:
    return _build_palette(
        window=_SOL_BASE3, base=_SOL_BASE3, alt_base=_SOL_BASE2, text=_SOL_BASE00,
        disabled_text=_SOL_BASE1, placeholder_text=_SOL_BASE1, button=_SOL_BASE2,
        highlight=_SOL_BLUE, highlighted_text=_SOL_BASE3, bright_text=_SOL_RED,
    )


def _solarized_dark_palette() -> QPalette:
    return _build_palette(
        window=_SOL_BASE03, base=_SOL_BASE03, alt_base=_SOL_BASE02, text=_SOL_BASE0,
        disabled_text=_SOL_BASE01, placeholder_text=_SOL_BASE01, button=_SOL_BASE02,
        highlight=_SOL_BLUE, highlighted_text=_SOL_BASE3, bright_text=_SOL_RED,
    )


_PALETTE_BUILDERS: Dict[str, Callable[[], QPalette]] = {
    "gray": _gray_palette,
    "solarized": _solarized_light_palette,
    "solarized_dark": _solarized_dark_palette,
}


def apply_theme(app: QApplication, theme: str) -> None:
    capture_defaults(app)
    builder = _PALETTE_BUILDERS.get(theme)
    if builder is not None:
        app.setStyle(QStyleFactory.create("Fusion"))
        app.setPalette(builder())
    else:
        if _default_style_name:
            style = QStyleFactory.create(_default_style_name)
            if style is not None:
                app.setStyle(style)
        if _default_palette is not None:
            app.setPalette(_default_palette)
