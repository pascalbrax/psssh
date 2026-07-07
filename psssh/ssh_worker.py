"""Background SSH session: connect, authenticate, shuttle PTY data, keepalive."""
from __future__ import annotations

import socket
import threading
from dataclasses import dataclass, field
from typing import Optional

import paramiko
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .connection import ConnectionSpec
from .host_keys import HostKeyGate, TrustOnFirstUsePolicy, known_hosts_path, verify_and_connect
from .settings import AppSettings


@dataclass
class PasswordRequest:
    prompt: str
    password: Optional[str] = None
    _event: threading.Event = field(default_factory=threading.Event)

    def wait(self) -> Optional[str]:
        self._event.wait()
        return self.password

    def resolve(self, password: Optional[str]) -> None:
        self.password = password
        self._event.set()


class AuthGate(QObject):
    """Lives on the GUI thread; prompts for a password when key/agent auth fails."""

    password_requested = pyqtSignal(object)  # PasswordRequest

    def ask_password(self, prompt: str) -> Optional[str]:
        req = PasswordRequest(prompt=prompt)
        self.password_requested.emit(req)
        return req.wait()


class SSHWorker(QThread):
    data_received = pyqtSignal(bytes)
    connected = pyqtSignal()
    status_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    session_closed = pyqtSignal(str)

    def __init__(self, spec: ConnectionSpec, host_key_gate: HostKeyGate, auth_gate: AuthGate,
                 settings: AppSettings, parent=None, initial_password: Optional[str] = None) -> None:
        super().__init__(parent)
        self.spec = spec
        self._host_key_gate = host_key_gate
        self._auth_gate = auth_gate
        self._settings = settings
        self._initial_password = initial_password
        self._client: Optional[paramiko.SSHClient] = None
        self._channel: Optional[paramiko.Channel] = None
        self._stop_flag = threading.Event()
        self._cols = 80
        self._rows = 24
        self.used_password: Optional[str] = None

    def run(self) -> None:
        client = paramiko.SSHClient()
        client.load_host_keys(str(known_hosts_path()))
        client.set_missing_host_key_policy(TrustOnFirstUsePolicy(self._host_key_gate))
        self._client = client

        connect_kwargs = dict(
            hostname=self.spec.host, port=self.spec.port, username=self.spec.user,
            key_filename=self.spec.key_file or None,
            look_for_keys=True, allow_agent=True, timeout=15,
        )

        try:
            self.status_changed.emit(f"Connecting to {self.spec.host}:{self.spec.port}...")
            try:
                if self._initial_password:
                    connect_kwargs.update(password=self._initial_password,
                                           look_for_keys=False, allow_agent=False)
                verify_and_connect(client, self._host_key_gate, **connect_kwargs)
                if self._initial_password:
                    self.used_password = self._initial_password
            except paramiko.BadHostKeyException:
                raise
            except (paramiko.AuthenticationException, paramiko.SSHException):
                # No usable key/agent/saved-password auth worked (paramiko raises
                # the bare SSHException "No authentication methods available" when
                # there's nothing to even try, not AuthenticationException) - fall
                # back to an interactive password prompt.
                password = self._auth_gate.ask_password(
                    f"Password for {self.spec.user}@{self.spec.host}:"
                )
                if not password:
                    raise
                connect_kwargs.update(password=password, look_for_keys=False, allow_agent=False)
                verify_and_connect(client, self._host_key_gate, **connect_kwargs)
                self.used_password = password

            transport = client.get_transport()
            if self._settings.keepalive_enabled:
                transport.set_keepalive(self._settings.keepalive_interval)

            self.status_changed.emit("Opening shell...")
            channel = client.invoke_shell(term="xterm-256color", width=self._cols, height=self._rows)
            channel.settimeout(0.5)
            self._channel = channel
            self.connected.emit()

            while not self._stop_flag.is_set():
                try:
                    chunk = channel.recv(65536)
                except socket.timeout:
                    continue
                except (EOFError, OSError):
                    break
                if not chunk:
                    break
                self.data_received.emit(chunk)

            # _stop_flag is only ever set by stop() (tab closed, app exiting),
            # so if the loop exited without it, the remote end went away on
            # its own - a dropped connection, not a requested disconnect.
            if self._stop_flag.is_set():
                self.session_closed.emit("Disconnected")
            else:
                self.session_closed.emit("Connection lost")
        except paramiko.AuthenticationException:
            self.error_occurred.emit("Authentication failed")
        except Exception as exc:  # noqa: BLE001 - surface any connection failure to the GUI
            self.error_occurred.emit(str(exc))
        finally:
            try:
                client.close()
            except Exception:
                pass

    @property
    def transport(self) -> Optional[paramiko.Transport]:
        return self._client.get_transport() if self._client is not None else None

    def send(self, data: bytes) -> None:
        if self._channel is not None:
            try:
                self._channel.send(data)
            except Exception:
                pass

    def resize(self, cols: int, rows: int) -> None:
        self._cols, self._rows = cols, rows
        if self._channel is not None:
            try:
                self._channel.resize_pty(width=cols, height=rows)
            except Exception:
                pass

    def stop(self) -> None:
        self._stop_flag.set()
        if self._channel is not None:
            try:
                self._channel.close()
            except Exception:
                pass
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
