"""Background local shell session: runs the OS default shell in a pty and shuttles I/O."""
from __future__ import annotations

import os
import signal
import sys
import threading
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal


def default_shell_command() -> str:
    """The command used to launch the OS default shell."""
    if sys.platform == "win32":
        return _windows_shell_command()
    return os.environ.get("SHELL") or "/bin/sh"


def _windows_shell_command() -> str:
    import shutil
    return shutil.which("powershell.exe") or os.environ.get("COMSPEC") or "cmd.exe"


class LocalShellWorker(QThread):
    """Runs the OS default shell in a pseudo-terminal.

    Mirrors SSHWorker's data/connect/error/close signal contract so it can
    drive the same TerminalWidget.
    """

    data_received = pyqtSignal(bytes)
    connected = pyqtSignal()
    status_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    session_closed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._stop_flag = threading.Event()
        self._cols = 80
        self._rows = 24
        self._win_pty = None
        self._posix_fd: Optional[int] = None
        self._posix_pid: Optional[int] = None

    def run(self) -> None:
        try:
            self.status_changed.emit("Starting local shell...")
            if sys.platform == "win32":
                self._run_windows()
            else:
                self._run_posix()
        except Exception as exc:  # noqa: BLE001 - surface any failure to the GUI
            self.error_occurred.emit(str(exc))

    # -- Windows: ConPTY via pywinpty --------------------------------------
    def _run_windows(self) -> None:
        try:
            import winpty
        except ImportError as exc:
            raise RuntimeError(
                "Local shell support on Windows requires the 'pywinpty' package "
                "(pip install pywinpty)."
            ) from exc

        shell = default_shell_command()
        pty = winpty.PtyProcess.spawn([shell], dimensions=(self._rows, self._cols))
        self._win_pty = pty
        self.connected.emit()

        while not self._stop_flag.is_set():
            try:
                data = pty.read(4096)
            except EOFError:
                break
            except Exception:
                break
            if not data:
                break
            self.data_received.emit(data.encode("utf-8", errors="replace"))
            if not pty.isalive():
                break

        self.session_closed.emit("Disconnected" if self._stop_flag.is_set() else "Shell exited")

    # -- POSIX: stdlib pty/tty ----------------------------------------------
    def _run_posix(self) -> None:
        import pty as pty_mod
        import select

        shell = default_shell_command()
        pid, fd = pty_mod.fork()
        if pid == 0:
            os.execvp(shell, [shell])
            os._exit(1)  # pragma: no cover - only reached if execvp fails

        self._posix_pid = pid
        self._posix_fd = fd
        self._resize_posix()
        self.connected.emit()

        while not self._stop_flag.is_set():
            try:
                ready, _, _ = select.select([fd], [], [], 0.5)
            except (OSError, ValueError):
                break
            if not ready:
                continue
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            self.data_received.emit(chunk)

        self.session_closed.emit("Disconnected" if self._stop_flag.is_set() else "Shell exited")

    def _resize_posix(self) -> None:
        if self._posix_fd is None:
            return
        import fcntl
        import struct
        import termios
        winsize = struct.pack("HHHH", self._rows, self._cols, 0, 0)
        try:
            fcntl.ioctl(self._posix_fd, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass

    def send(self, data: bytes) -> None:
        if sys.platform == "win32":
            if self._win_pty is not None:
                try:
                    self._win_pty.write(data.decode("utf-8", errors="replace"))
                except Exception:
                    pass
        else:
            if self._posix_fd is not None:
                try:
                    os.write(self._posix_fd, data)
                except OSError:
                    pass

    def resize(self, cols: int, rows: int) -> None:
        self._cols, self._rows = cols, rows
        if sys.platform == "win32":
            if self._win_pty is not None:
                try:
                    self._win_pty.setwinsize(rows, cols)
                except Exception:
                    pass
        else:
            self._resize_posix()

    def stop(self) -> None:
        self._stop_flag.set()
        if sys.platform == "win32":
            if self._win_pty is not None:
                try:
                    self._win_pty.close()
                except Exception:
                    pass
        else:
            if self._posix_fd is not None:
                try:
                    os.close(self._posix_fd)
                except OSError:
                    pass
            if self._posix_pid is not None:
                try:
                    os.kill(self._posix_pid, signal.SIGHUP)
                except Exception:
                    pass
