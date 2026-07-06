"""A VT100/xterm-256/truecolor terminal emulator widget backed by pyte."""
from __future__ import annotations

from typing import Optional

import pyte
from PyQt6.QtCore import QPoint, QTimer, Qt, pyqtSignal
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
_MODE_BRACKETED_PASTE = 2004 << 5  # wrap pasted text in ESC[200~ ... ESC[201~
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
    screenshot_taken = pyqtSignal()

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
        self._palette = colors.palette_for(settings.theme)

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

        self._autoscroll_timer = QTimer(self)
        self._autoscroll_timer.setInterval(80)
        self._autoscroll_timer.timeout.connect(self._autoscroll_tick)
        self._autoscroll_dir = 0  # -1 = scrolling up, +1 = scrolling down, 0 = idle
        self._autoscroll_col = 0

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
        painter.fillRect(self.rect(), QColor(f"#{self._palette.default_bg}"))
        painter.setFont(self._font)

        sel_range = self._normalized_selection()
        columns = self.screen.columns

        for y in range(self.screen.lines):
            row = self.screen.buffer[y]
            sel_cols = self._selection_cols_for_row(sel_range, y, columns)
            x = 0
            while x < columns:
                char = row[x]
                fg, bg, bold, underscore, italics, strike, reverse = (
                    char.fg, char.bg, char.bold, char.underscore,
                    char.italics, char.strikethrough, char.reverse,
                )
                run_chars = [char.data or " "]
                run_start = x
                x += 1
                while x < columns:
                    nxt = row[x]
                    if (nxt.fg, nxt.bg, nxt.bold, nxt.underscore, nxt.italics,
                            nxt.strikethrough, nxt.reverse) != (fg, bg, bold, underscore,
                                                                  italics, strike, reverse):
                        break
                    run_chars.append(nxt.data or " ")
                    x += 1
                run_end = x - 1

                fg_color = colors.resolve(fg, self._palette.default_fg, self._palette.named)
                bg_color = colors.resolve(bg, self._palette.default_bg, self._palette.named)
                if reverse:
                    fg_color, bg_color = bg_color, fg_color

                # Selection boundaries rarely align with attribute-run boundaries
                # (e.g. a whole blank line is usually one run) - split the run so
                # only the actually-selected cells get highlighted.
                for seg_start, seg_end, selected in self._split_run_by_selection(
                        run_start, run_end, sel_cols):
                    seg_text = "".join(run_chars[seg_start - run_start:seg_end - run_start + 1])
                    seg_bg = QColor("#3a6ea5") if selected else bg_color

                    cell_rect_x = seg_start * self._cell_w
                    cell_rect_y = y * self._cell_h
                    rect_w = (seg_end - seg_start + 1) * self._cell_w

                    painter.fillRect(cell_rect_x, cell_rect_y, rect_w, self._cell_h, seg_bg)

                    font = QFont(self._font)
                    font.setBold(bool(bold))
                    font.setItalic(bool(italics))
                    font.setUnderline(bool(underscore))
                    font.setStrikeOut(bool(strike))
                    painter.setFont(font)
                    painter.setPen(fg_color)
                    painter.drawText(cell_rect_x, cell_rect_y + self._metrics.ascent(), seg_text)

        if not self.screen.cursor.hidden and self.hasFocus():
            cx, cy = self.screen.cursor.x, self.screen.cursor.y
            cursor_color = QColor(f"#{self._palette.cursor_hex}")
            cursor_color.setAlpha(120)
            painter.fillRect(cx * self._cell_w, cy * self._cell_h,
                              self._cell_w, self._cell_h, cursor_color)

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
            self._scroll_view(prev=key == Qt.Key.Key_PageUp)
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

    def _scroll_view(self, prev: bool) -> None:
        """
        Page the scrollback via pyte, keeping any selection anchored to the
        same lines. pyte's HistoryScreen doesn't grow a taller buffer when you
        scroll - it swaps which content occupies the existing row indices, so
        a selection recorded as "row 2" would silently start pointing at
        different text after scrolling unless we shift it by exactly how far
        the view moved.
        """
        before = self.screen.history.position
        if prev:
            self.screen.prev_page()
        else:
            self.screen.next_page()
        delta = self.screen.history.position - before
        if delta:
            if self._sel_start is not None:
                self._sel_start = QPoint(self._sel_start.x(), self._sel_start.y() - delta)
            if self._sel_end is not None:
                self._sel_end = QPoint(self._sel_end.x(), self._sel_end.y() - delta)

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
            pos = event.position()
            self._sel_end = self._cell_at(pos.toPoint())
            self._update_autoscroll(pos.y())
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._stop_autoscroll()
        if self._mouse_reporting_enabled() and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            code = _MOUSE_BUTTON_CODES.get(event.button())
            if code is not None:
                self._send_mouse_report(event.position().toPoint(), code, pressed=False, event=event)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._selecting = False

    def _update_autoscroll(self, y: float) -> None:
        """Start/stop continuous scrolling while a drag-selection is held past
        the terminal's top/bottom edge, so a selection can span more content
        than fits on one screen without needing the mouse wheel."""
        if y < 0:
            direction = -1
        elif y >= self.height():
            direction = 1
        else:
            direction = 0
        if direction == self._autoscroll_dir:
            return
        self._autoscroll_dir = direction
        if direction == 0:
            self._autoscroll_timer.stop()
        else:
            self._autoscroll_col = self._sel_end.x() if self._sel_end else 0
            self._autoscroll_timer.start()

    def _stop_autoscroll(self) -> None:
        self._autoscroll_dir = 0
        self._autoscroll_timer.stop()

    def _autoscroll_tick(self) -> None:
        if not self._selecting or self._autoscroll_dir == 0:
            self._stop_autoscroll()
            return
        self._scroll_view(prev=self._autoscroll_dir < 0)
        edge_row = 0 if self._autoscroll_dir < 0 else self.screen.lines - 1
        self._sel_end = QPoint(self._autoscroll_col, edge_row)
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        notches = event.angleDelta().y() // 120
        if self._mouse_reporting_enabled() and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            code = 64 if notches > 0 else 65  # wheel up / wheel down
            for _ in range(abs(notches)):
                self._send_mouse_report(event.position().toPoint(), code, pressed=True, event=event)
            return
        for _ in range(abs(notches)):
            self._scroll_view(prev=notches > 0)
        self.update()

    def _normalized_selection(self):
        if not self._sel_start or not self._sel_end:
            return None
        if self._sel_start == self._sel_end:
            # A plain click (no drag) shouldn't paint a selection at all - real
            # terminals only start highlighting once the mouse actually moves
            # to a different cell.
            return None
        a, b = self._sel_start, self._sel_end
        if (a.y(), a.x()) <= (b.y(), b.x()):
            return (a.y(), a.x(), b.y(), b.x())
        return (b.y(), b.x(), a.y(), a.x())

    @staticmethod
    def _selection_cols_for_row(sel_range, row: int, columns: int) -> Optional[tuple]:
        """Inclusive (start, end) column range selected on this row, or None."""
        if not sel_range:
            return None
        y0, x0, y1, x1 = sel_range
        if row < y0 or row > y1:
            return None
        start = x0 if row == y0 else 0
        end = x1 if row == y1 else columns - 1
        return (start, end)

    @staticmethod
    def _split_run_by_selection(run_start: int, run_end: int, sel_cols: Optional[tuple]):
        """Split [run_start, run_end] into (seg_start, seg_end, selected) pieces."""
        if not sel_cols:
            yield (run_start, run_end, False)
            return
        sx0, sx1 = sel_cols
        if sx1 < run_start or sx0 > run_end:
            yield (run_start, run_end, False)
            return
        if run_start < sx0:
            yield (run_start, sx0 - 1, False)
        yield (max(run_start, sx0), min(run_end, sx1), True)
        if run_end > sx1:
            yield (sx1 + 1, run_end, False)

    def _row_at(self, virtual_y: int):
        """
        Look up a row by viewport-relative index, which - once a selection has
        survived a scroll via _scroll_view() - may be negative (above the
        current top of screen) or >= lines (below it, only reachable while
        paged up). screen.buffer only ever holds the current viewport, so rows
        outside it have to come from pyte's own history deques instead;
        falls back to None if that content isn't retained anymore.
        """
        if 0 <= virtual_y < self.screen.lines:
            return self.screen.buffer[virtual_y]
        if virtual_y < 0:
            top = self.screen.history.top
            idx = len(top) + virtual_y
            return top[idx] if 0 <= idx < len(top) else None
        bottom = self.screen.history.bottom
        idx = virtual_y - self.screen.lines
        return bottom[idx] if 0 <= idx < len(bottom) else None

    def _selected_text(self) -> str:
        sel_range = self._normalized_selection()
        if not sel_range:
            return ""
        y0, x0, y1, x1 = sel_range
        lines = []
        for y in range(y0, y1 + 1):
            row = self._row_at(y)
            if row is None:
                lines.append("")
                continue
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
        if not text:
            return
        # A real Enter keypress sends a bare CR (see _SIMPLE_KEYS), and line
        # editors (nano, vim, bash) expect pasted newlines to match that; left
        # as \n they can be ignored or misapplied, garbling multi-line pastes.
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r")
        data = normalized.encode("utf-8")
        if _MODE_BRACKETED_PASTE in self.screen.mode:
            # Tell the remote app this text was pasted, not typed, so it skips
            # per-keystroke behavior like auto-indent on it (mode 2004).
            data = b"\x1b[200~" + data + b"\x1b[201~"
        self.data_to_send.emit(data)

    def screenshot_to_clipboard(self) -> None:
        """Render just this widget (no SFTP panel) to the clipboard as an image."""
        pixmap = self.grab()
        QGuiApplication.clipboard().setPixmap(pixmap, QClipboard.Mode.Clipboard)
        self.screenshot_taken.emit()

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

    def apply_palette(self, theme: str) -> None:
        self._palette = colors.palette_for(theme)
        self.update()
