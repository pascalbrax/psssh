"""Combines the terminal and an optional SFTP panel for one SSH connection."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QSplitter, QVBoxLayout, QWidget

from .connection import ConnectionSpec
from .host_keys import HostKeyGate, HostKeyRequest
from .settings import AppSettings
from .sftp_panel import SftpPanel
from .sftp_worker import SftpWorker
from .ssh_worker import AuthGate, PasswordRequest, SSHWorker
from .terminal_widget import TerminalWidget
from .tunnel import TunnelManager


class SessionWidget(QWidget):
    status_changed = pyqtSignal(str)
    title_changed = pyqtSignal(str)
    connection_state_changed = pyqtSignal(str)

    def __init__(self, spec: ConnectionSpec, settings: AppSettings, parent: Optional[QWidget] = None,
                 initial_password: Optional[str] = None) -> None:
        super().__init__(parent)
        self.spec = spec
        self.settings = settings
        self.connection_state = "Connecting…"
        self.tunnel_manager = TunnelManager(lambda: self.ssh_worker.transport)

        self.host_key_gate = HostKeyGate()
        self.auth_gate = AuthGate()
        self.host_key_gate.unknown_host_key.connect(self._on_unknown_host_key)
        self.host_key_gate.changed_host_key.connect(self._on_changed_host_key)
        self.auth_gate.password_requested.connect(self._on_password_requested)

        self.terminal = TerminalWidget(settings)
        self.sftp_panel: Optional[SftpPanel] = None
        self.sftp_worker: Optional[SftpWorker] = None
        self._want_sftp = settings.show_sftp_panel

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.terminal)
        layout.addWidget(self.splitter)

        self.ssh_worker = SSHWorker(spec, self.host_key_gate, self.auth_gate, settings,
                                     initial_password=initial_password)
        self.ssh_worker.data_received.connect(self.terminal.feed)
        self.ssh_worker.connected.connect(self._on_connected)
        self.ssh_worker.status_changed.connect(self._on_status)
        self.ssh_worker.error_occurred.connect(self._on_error)
        self.ssh_worker.session_closed.connect(self._on_session_closed)

        self.terminal.data_to_send.connect(self.ssh_worker.send)
        self.terminal.size_changed.connect(self.ssh_worker.resize)
        self.terminal.title_changed.connect(self.title_changed)
        self.terminal.screenshot_taken.connect(
            lambda: self.status_changed.emit("Terminal screenshot copied to clipboard"))

    def start(self) -> None:
        self.ssh_worker.start()

    def _set_connection_state(self, text: str) -> None:
        self.connection_state = text
        self.connection_state_changed.emit(text)

    def _on_status(self, message: str) -> None:
        self._set_connection_state(message)
        self.status_changed.emit(message)

    def _on_connected(self) -> None:
        text = f"Connected to {self.spec.label}"
        self._set_connection_state(text)
        self.status_changed.emit(text)
        if self._want_sftp:
            self.show_sftp_panel(True)
        self.terminal.setFocus()

    def _on_error(self, message: str) -> None:
        self._set_connection_state(f"Error: {message}")
        QMessageBox.critical(self, "Connection error", message)
        self.status_changed.emit(f"Error: {message}")

    def _on_session_closed(self, message: str) -> None:
        self._set_connection_state(message)
        self.status_changed.emit(message)

    def show_sftp_panel(self, show: bool) -> None:
        if show and self.sftp_panel is None:
            self.sftp_worker = SftpWorker(lambda: self.ssh_worker.transport)
            self.sftp_panel = SftpPanel(self.sftp_worker, self.settings, initial_path=".")
            self.splitter.addWidget(self.sftp_panel)
            self.splitter.setSizes([700, 300])
            self.sftp_panel.start()
        elif not show and self.sftp_panel is not None:
            self.sftp_panel.stop()
            self.sftp_panel.setParent(None)
            self.sftp_panel.deleteLater()
            self.sftp_panel = None
            self.sftp_worker = None
        self._want_sftp = show

    def toggle_sftp_panel(self) -> None:
        self.show_sftp_panel(self.sftp_panel is None)

    def is_sftp_visible(self) -> bool:
        return self.sftp_panel is not None

    def _on_unknown_host_key(self, req: HostKeyRequest) -> None:
        text = (f"The authenticity of host '{req.hostname}' can't be established.\n"
                f"{req.key_type} key fingerprint: {req.new_fingerprint}\n\n"
                "Are you sure you want to continue connecting?")
        reply = QMessageBox.question(self, "Unknown Host", text,
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        req.resolve(reply == QMessageBox.StandardButton.Yes)

    def _on_changed_host_key(self, req: HostKeyRequest) -> None:
        text = ("WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!\n\n"
                f"The {req.key_type} host key for '{req.hostname}' has changed.\n"
                f"Old fingerprint: {req.old_fingerprint}\n"
                f"New fingerprint: {req.new_fingerprint}\n\n"
                "This could mean someone is intercepting your connection, or the host "
                "key was legitimately changed by an administrator.\n\n"
                "Only continue if you are certain this change is expected.")
        reply = QMessageBox.warning(self, "Host Key Changed", text,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        req.resolve(reply == QMessageBox.StandardButton.Yes)

    def _on_password_requested(self, req: PasswordRequest) -> None:
        password, ok = QInputDialog.getText(self, "Authentication", req.prompt,
                                             QLineEdit.EchoMode.Password)
        req.resolve(password if ok else None)

    def stop(self) -> None:
        self.tunnel_manager.stop_all()
        if self.sftp_worker is not None:
            self.sftp_worker.stop()
            self.sftp_worker.wait(2000)
        self.ssh_worker.stop()
        self.ssh_worker.wait(2000)
