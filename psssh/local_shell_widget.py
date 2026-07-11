"""Terminal tab running the local OS shell (no SSH)."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from .local_shell_worker import LocalShellWorker
from .settings import AppSettings
from .terminal_widget import TerminalWidget


class LocalShellWidget(QWidget):
    status_changed = pyqtSignal(str)
    connection_state_changed = pyqtSignal(str)
    connection_failed = pyqtSignal()

    def __init__(self, settings: AppSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.connection_state = "Starting…"
        self._connected = False

        self.terminal = TerminalWidget(settings)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.terminal)

        self.worker = LocalShellWorker()
        self.worker.data_received.connect(self.terminal.feed)
        self.worker.connected.connect(self._on_connected)
        self.worker.status_changed.connect(self._on_status)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.session_closed.connect(self._on_session_closed)

        self.terminal.data_to_send.connect(self.worker.send)
        self.terminal.size_changed.connect(self.worker.resize)

    def start(self) -> None:
        self.worker.start()

    def _set_connection_state(self, text: str) -> None:
        self.connection_state = text
        self.connection_state_changed.emit(text)

    def _on_status(self, message: str) -> None:
        self._set_connection_state(message)
        self.status_changed.emit(message)

    def _on_connected(self) -> None:
        self._connected = True
        self._set_connection_state("Local shell")
        self.status_changed.emit("Local shell")
        self.terminal.setFocus()

    def _on_error(self, message: str) -> None:
        self._set_connection_state(f"Error: {message}")
        QMessageBox.critical(self, "Local shell error", message)
        self.status_changed.emit(f"Error: {message}")
        if not self._connected:
            self.connection_failed.emit()

    def _on_session_closed(self, message: str) -> None:
        self._set_connection_state(message)
        self.status_changed.emit(message)

    def stop(self) -> None:
        self.worker.stop()
        self.worker.wait(2000)
