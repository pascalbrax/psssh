"""A VT100/xterm-256/truecolor terminal emulator widget backed by pyte."""
from __future__ import annotations

from typing import Optional

import pyte
from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import (QClipboard, QColor, QFont, QFontMetrics, QGuiApplication,
                          QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QResizeEvent,
                          QWheelEvent)
from PyQt6.QtWidgets import QMenu, QWidget

from . import colors
from .settings import AppSettings


class _Screen(pyte.HistoryScreen):
    """
    pyte's parser forwards a ``private=True`` flag to whichever CSI handler
    matches the trailing character whenever the sequence starts with ``?``,
    but only set_mode/reset_mode were written to accept it. Some full-screen
    apps (e.g. Midnight Commander / S-Lang) send ``CSI ?1001r`` - "restore DEC
    private mode values" - which happens to share its trailing 'r' with
    DECSTBM (set_margins), so pyte calls ``set_margins(private=True)`` and
    raises TypeError, crashing the whole app. pyte doesn't implement private
    mode save/restore at all, so the correct behavior is just to ignore it.
    """

    def set_margins(self, *args, private: bool = False, **kwargs) -> None:
        if private:
            return
        super().set_margins(*args, **kwargs)


# xterm function-key escape sequences (normal, non-application mode).
_FUNCTION_KEYS = {
    Qt.Key.Key_F1: b"\x1bOP", Qt.Key.Key_F2: b"\x1bOQ",
    Qt.Key.Key_F3: b"\x1bOR", Qt.Key.Key_F4: b"\x1bOS",
    Qt.Key.Key_F5: b"\x1b[15~", Qt.Key.Key_F6: b"\x1b[17~",
    Qt.Key.Key_F7: b"\x1b[18~", Qt.Key.Key_F8: b"\x1b[19~",
    Qt.Key.Key_F9: b"\x1b[20~", Qt.Key.Key_F10: b"\x1b[21~",
    Qt.Key.Key_F11: b"\x1b[23~", Qt.Key.Key_F12: b"\x1b[24~",
}

# Cursor keys switch between CSI ("normal") and SS3 ("application") encoding
# depending on DECCKM (CSI ?1h / ?1l) - full-screen apps like mc/vim/htop rely
# on this switch, so hardcoding one form makes them misread arrow/home/end.
_CURSOR_KEYS_NORMAL = {
    Qt.Key.Key_Up: b"\x1b[A", Qt.Key.Key_Down: b"\x1b[B",
    Qt.Key.Key_Right: b"\x1b[C", Qt.Key.Key_Left: b"\x1b[D",
    Qt.Key.Key_Home: b"\x1b[H", Qt.Key.Key_End: b"\x1b[F",
}
_CURSOR_KEYS_APPLICATION = {
    Qt.Key.Key_Up: b"\x1bOA", Qt.Key.Key_Down: b"\x1bOB",
    Qt.Key.Key_Right: b"\x1bOC", Qt.Key.Key_Left: b"\x1bOD",
    Qt.Key.Key_Home: b"\x1bOH", Qt.Key.Key_End: b"\x1bOF",
}

_SIMPLE_KEYS = {
    Qt.Key.Key_Insert: b"\x1b[2~", Qt.Key.Key_Delete: b"\x1b[3~",
    Qt.Key.Key_PageUp: b"\x1b[5~", Qt.Key.Key_PageDown: b"\x1b[6~",
    Qt.Key.Key_Backtab: b"\x1b[Z",
    Qt.Key.Key_Return: b"\r", Qt.Key.Key_Enter: b"\r",
    Qt.Key.Key_Backspace: b"\x7f", Qt.Key.Key_Tab: b"\t",
    Qt.Key.Key_Escape: b"\x1b",
}

# DEC private mode numbers, as tracked in pyte's Screen.mode (shifted << 5 by
# pyte itself to distinguish private modes from ANSI ones - see Screen.set_mode).
_MODE_DECCKM = 1 << 5              # application cursor keys
_MODE_MOUSE_X10 = 1000 << 5        # report button press+release only
_MODE_MOUSE_BTN_EVENT = 1002 << 5  # also report motion while a button is held
_MODE_MOUSE_ANY_EVENT = 1003 << 5  # report all motion, button held or not
_MODE_MOUSE_SGR = 1006 << 5        # SGR extended coordinate encoding
_MOUSE_REPORTING_MODES = {_MODE_MOUSE_X10, _MODE_MOUSE_BTN_EVENT, _MODE_MOUSE_ANY_EVENT}

_MOUSE_BUTTON_CODES = {
    Qt.MouseButton.LeftButton: 0,
    Qt.MouseButton.MiddleButton: 1,
    Qt.MouseButton.RightButton: 2,
}


class TerminalWidget(QWidget):
    data_to_send = pyqtSignal(bytes)
    size_changed = pyqtSignal(int, int)  # cols, rows
    title_changed = pyqtSignal(str)

    def __init__(self, settings: AppSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setMouseTracking(True)  # so any-event mouse reporting (mode 1003) gets motion too

        self.screen = _Screen(80, 24, history=settings.scrollback_lines, ratio=0.12)
        self.stream = pyte.ByteStream(self.screen)
        self._title = ""

        self._font = QFont(settings.font_family, settings.font_size)
        self._font.setFixedPitch(True)
        self._font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(self._font)
        self._metrics = QFontMetrics(self._font)
        self._cell_w = max(1, self._metrics.horizontalAdvance("M"))
        self._cell_h = max(1, self._metrics.height())

        self._selecting = False
        self._sel_start: Optional[QPoint] = None
        self._sel_end: Optional[QPoint] = None

        self.setMinimumSize(self._cell_w * 10, self._cell_h * 4)

    def focusNextPrevChild(self, next: bool) -> bool:
        # Without this, Qt's focus-chain traversal steals Tab/Shift+Tab before
        # they ever reach keyPressEvent, so shell command completion breaks.
        return False

    # -- incoming data ---------------------------------------------------
    def feed(self, data: bytes) -> None:
        try:
            self.stream.feed(data)
        except Exception:
            # A malformed/unsupported escape sequence should never take down
            # the whole app - worst case this redraw glitches, the session
            # and app stay alive. (An unhandled exception here would otherwise
            # propagate out of a Qt signal handler and abort the process.)
            import traceback
            traceback.print_exc()
        if self.screen.title != self._title:
            self._title = self.screen.title
            self.title_changed.emit(self._title)
        self.update()

    def clear_scrollback(self) -> None:
        self.screen.history.top.clear()
        self.screen.history.bottom.clear()
        self.update()

    # -- geometry ----------------------------------------------------------
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        cols = max(1, self.width() // self._cell_w)
        rows = max(1, self.height() // self._cell_h)
        if (cols, rows) != (self.screen.columns, self.screen.lines):
            self.screen.resize(lines=rows, columns=cols)
            self.size_changed.emit(cols, rows)

    def sizeHint(self):
        from PyQt6.QtCore import QSize
        return QSize(self._cell_w * 80, self._cell_h * 24)

    # -- painting ------------------------------------------------------
    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(f"#{colors.DEFAULT_BG}"))
        painter.setFont(self._font)

        sel_range = self._normalized_selection()

        for y in range(self.screen.lines):
            row = self.screen.buffer[y]
            x = 0
            columns = self.screen.columns
            while x < columns:
                char = row[x]
                fg, bg, bold, underscore, italics, strike, reverse = (
                    char.fg, char.bg, char.bold, char.underscore,
                    char.italics, char.strikethrough, char.reverse,
                )
                run_text = [char.data or " "]
                run_start = x
                x += 1
                while x < columns:
                    nxt = row[x]
                    if (nxt.fg, nxt.bg, nxt.bold, nxt.underscore, nxt.italics,
                            nxt.strikethrough, nxt.reverse) != (fg, bg, bold, underscore,
                                                                  italics, strike, reverse):
                        break
                    run_text.append(nxt.data or " ")
                    x += 1

                fg_color = colors.resolve(fg, colors.DEFAULT_FG)
                bg_color = colors.resolve(bg, colors.DEFAULT_BG)
                if reverse:
                    fg_color, bg_color = bg_color, fg_color

                run_len = x - run_start
                cell_rect_x = run_start * self._cell_w
                cell_rect_y = y * self._cell_h
                rect_w = run_len * self._cell_w

                if self._in_selection(sel_range, y, run_start, x - 1):
                    bg_color = QColor("#3a6ea5")

                painter.fillRect(cell_rect_x, cell_rect_y, rect_w, self._cell_h, bg_color)

                font = QFont(self._font)
                font.setBold(bool(bold))
                font.setItalic(bool(italics))
                font.setUnderline(bool(underscore))
                font.setStrikeOut(bool(strike))
                painter.setFont(font)
                painter.setPen(fg_color)
                painter.drawText(cell_rect_x, cell_rect_y + self._metrics.ascent(),
                                  "".join(run_text))

        if not self.screen.cursor.hidden and self.hasFocus():
            cx, cy = self.screen.cursor.x, self.screen.cursor.y
            painter.fillRect(cx * self._cell_w, cy * self._cell_h,
                              self._cell_w, self._cell_h, QColor(255, 255, 255, 120))

    # -- keyboard --------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent) -> None:
        mods = event.modifiers()
        key = event.key()

        if mods & Qt.KeyboardModifier.ControlModifier and mods & Qt.KeyboardModifier.ShiftModifier:
            if key == Qt.Key.Key_C:
                self._copy_selection()
                return
            if key == Qt.Key.Key_V:
                self._paste_clipboard()
                return

        if key == Qt.Key.Key_Insert and mods & Qt.KeyboardModifier.ShiftModifier:
            self._paste_clipboard()
            return

        if mods & Qt.KeyboardModifier.ShiftModifier and key in (Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            if key == Qt.Key.Key_PageUp:
                self.screen.prev_page()
            else:
                self.screen.next_page()
            self.update()
            return

        if key in _FUNCTION_KEYS:
            self.data_to_send.emit(_FUNCTION_KEYS[key])
            return

        if key in _CURSOR_KEYS_NORMAL:
            cursor_keys = (_CURSOR_KEYS_APPLICATION if _MODE_DECCKM in self.screen.mode
                           else _CURSOR_KEYS_NORMAL)
            self.data_to_send.emit(cursor_keys[key])
            return

        if key in _SIMPLE_KEYS:
            self.data_to_send.emit(_SIMPLE_KEYS[key])
            return

        if mods & Qt.KeyboardModifier.ControlModifier and Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            self.data_to_send.emit(bytes([key - Qt.Key.Key_A + 1]))
            return

        text = event.text()
        if text:
            self.data_to_send.emit(text.encode("utf-8"))
            return

        super().keyPressEvent(event)

    # -- mouse: xterm mouse reporting, selection & scrollback -------------
    def _cell_at(self, pos: QPoint) -> QPoint:
        col = max(0, min(self.screen.columns - 1, pos.x() // self._cell_w))
        row = max(0, min(self.screen.lines - 1, pos.y() // self._cell_h))
        return QPoint(col, row)

    def _mouse_reporting_enabled(self) -> bool:
        return bool(self.screen.mode & _MOUSE_REPORTING_MODES)

    def _send_mouse_report(self, pos: QPoint, button_code: int, pressed: bool,
                            event: Optional[QMouseEvent] = None) -> None:
        cell = self._cell_at(pos)
        col, row = cell.x() + 1, cell.y() + 1
        code = button_code
        if event is not None:
            mods = event.modifiers()
            if mods & Qt.KeyboardModifier.ShiftModifier:
                code |= 4
            if mods & Qt.KeyboardModifier.AltModifier:
                code |= 8
            if mods & Qt.KeyboardModifier.ControlModifier:
                code |= 16
        if _MODE_MOUSE_SGR in self.screen.mode:
            suffix = "M" if pressed else "m"
            seq = f"\x1b[<{code};{col};{row}{suffix}".encode("ascii")
        else:
            # Legacy X10-style encoding: releases are always reported as code 3
            # (there's no per-button release code), and coordinates are single
            # bytes offset by 32, so they saturate rather than wrap past 223.
            b = code if pressed else 3
            seq = bytes([0x1B, 0x5B, 0x4D, 32 + (b & 0xFF), 32 + min(col, 223), 32 + min(row, 223)])
        self.data_to_send.emit(seq)

    @staticmethod
    def _primary_button(buttons: Qt.MouseButton) -> Optional[Qt.MouseButton]:
        for btn in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            if buttons & btn:
                return btn
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.setFocus()
        # Shift+click always forces local selection, matching xterm convention,
        # so the terminal's own copy/paste stays reachable even in apps (mc,
        # vim, htop, ...) that have grabbed mouse reporting for themselves.
        if self._mouse_reporting_enabled() and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            code = _MOUSE_BUTTON_CODES.get(event.button())
            if code is not None:
                self._send_mouse_report(event.position().toPoint(), code, pressed=True, event=event)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._selecting = True
            self._sel_start = self._cell_at(event.position().toPoint())
            self._sel_end = self._sel_start
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._mouse_reporting_enabled() and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            buttons = event.buttons()
            primary = self._primary_button(buttons)
            if primary is not None and _MODE_MOUSE_BTN_EVENT in self.screen.mode:
                code = _MOUSE_BUTTON_CODES.get(primary, 0) | 32
                self._send_mouse_report(event.position().toPoint(), code, pressed=True, event=event)
            elif primary is None and _MODE_MOUSE_ANY_EVENT in self.screen.mode:
                self._send_mouse_report(event.position().toPoint(), 3 | 32, pressed=True, event=event)
            return
        if self._selecting:
            self._sel_end = self._cell_at(event.position().toPoint())
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._mouse_reporting_enabled() and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            code = _MOUSE_BUTTON_CODES.get(event.button())
            if code is not None:
                self._send_mouse_report(event.position().toPoint(), code, pressed=False, event=event)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._selecting = False

    def wheelEvent(self, event: QWheelEvent) -> None:
        notches = event.angleDelta().y() // 120
        if self._mouse_reporting_enabled() and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            code = 64 if notches > 0 else 65  # wheel up / wheel down
            for _ in range(abs(notches)):
                self._send_mouse_report(event.position().toPoint(), code, pressed=True, event=event)
            return
        for _ in range(abs(notches)):
            if notches > 0:
                self.screen.prev_page()
            else:
                self.screen.next_page()
        self.update()

    def _normalized_selection(self):
        if not self._sel_start or not self._sel_end:
            return None
        a, b = self._sel_start, self._sel_end
        if (a.y(), a.x()) <= (b.y(), b.x()):
            return (a.y(), a.x(), b.y(), b.x())
        return (b.y(), b.x(), a.y(), a.x())

    @staticmethod
    def _in_selection(sel_range, row, col_start, col_end) -> bool:
        if not sel_range:
            return False
        y0, x0, y1, x1 = sel_range
        if row < y0 or row > y1:
            return False
        if y0 == y1:
            return not (col_end < x0 or col_start > x1)
        if row == y0:
            return col_end >= x0
        if row == y1:
            return col_start <= x1
        return True

    def _selected_text(self) -> str:
        sel_range = self._normalized_selection()
        if not sel_range:
            return ""
        y0, x0, y1, x1 = sel_range
        lines = []
        for y in range(y0, y1 + 1):
            row = self.screen.buffer[y]
            start = x0 if y == y0 else 0
            end = x1 if y == y1 else self.screen.columns - 1
            text = "".join((row[x].data or " ") for x in range(start, end + 1))
            lines.append(text.rstrip())
        return "\n".join(lines)

    def _copy_selection(self) -> None:
        text = self._selected_text()
        if text:
            QGuiApplication.clipboard().setText(text, QClipboard.Mode.Clipboard)

    def _paste_clipboard(self) -> None:
        text = QGuiApplication.clipboard().text(QClipboard.Mode.Clipboard)
        if text:
            self.data_to_send.emit(text.encode("utf-8"))

    def screenshot_to_clipboard(self) -> None:
        """Render just this widget (no SFTP panel) to the clipboard as an image."""
        pixmap = self.grab()
        QGuiApplication.clipboard().setPixmap(pixmap, QClipboard.Mode.Clipboard)

    def _show_context_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        copy_action = menu.addAction("Copy")
        copy_action.setEnabled(bool(self._selected_text()))
        paste_action = menu.addAction("Paste")
        menu.addSeparator()
        screenshot_action = menu.addAction("Copy Screenshot")
        menu.addSeparator()
        clear_action = menu.addAction("Clear Scrollback")
        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen == copy_action:
            self._copy_selection()
        elif chosen == paste_action:
            self._paste_clipboard()
        elif chosen == screenshot_action:
            self.screenshot_to_clipboard()
        elif chosen == clear_action:
            self.clear_scrollback()

    def apply_font(self, family: str, size: int) -> None:
        self._font = QFont(family, size)
        self._font.setFixedPitch(True)
        self._font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(self._font)
        self._metrics = QFontMetrics(self._font)
        self._cell_w = max(1, self._metrics.horizontalAdvance("M"))
        self._cell_h = max(1, self._metrics.height())
        self.resizeEvent(QResizeEvent(self.size(), self.size()))
        self.update()
