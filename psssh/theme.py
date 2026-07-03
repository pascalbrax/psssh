"""App-wide theme switching (native "system" look vs. a flat gray palette)."""
from __future__ import annotations

from typing import Optional

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


def _gray_palette() -> QPalette:
    palette = QPalette()
    window = QColor(53, 53, 53)
    base = QColor(42, 42, 42)
    alt_base = QColor(66, 66, 66)
    text = QColor(220, 220, 220)
    disabled_text = QColor(127, 127, 127)
    highlight = QColor(90, 140, 210)

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, alt_base)
    palette.setColor(QPalette.ColorRole.ToolTipBase, text)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, window)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 90, 90))
    palette.setColor(QPalette.ColorRole.Link, highlight)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(20, 20, 20))

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text)
    return palette


def apply_theme(app: QApplication, theme: str) -> None:
    capture_defaults(app)
    if theme == "gray":
        app.setStyle(QStyleFactory.create("Fusion"))
        app.setPalette(_gray_palette())
    else:
        if _default_style_name:
            style = QStyleFactory.create(_default_style_name)
            if style is not None:
                app.setStyle(style)
        if _default_palette is not None:
            app.setPalette(_default_palette)
