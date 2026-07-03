"""
Host key verification against the user's OpenSSH known_hosts file
(~/.ssh/known_hosts), with GUI confirmation for trust-on-first-use and a
hard warning when a previously trusted key changes (possible MITM).

paramiko's SSHClient.connect() only calls the MissingHostKeyPolicy for hosts
it has never seen before; a *changed* key raises BadHostKeyException directly,
so that case is handled separately by verify_and_connect().
"""
from __future__ import annotations

import base64
import hashlib
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import paramiko
from PyQt6.QtCore import QObject, pyqtSignal


def known_hosts_path() -> Path:
    path = Path.home() / ".ssh" / "known_hosts"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def fingerprint(key: paramiko.PKey) -> str:
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


@dataclass
class HostKeyRequest:
    hostname: str
    key_type: str
    new_fingerprint: str
    old_fingerprint: Optional[str] = None  # set only for a changed-key warning
    approved: bool = False
    _event: threading.Event = field(default_factory=threading.Event)

    def wait(self) -> bool:
        self._event.wait()
        return self.approved

    def resolve(self, approved: bool) -> None:
        self.approved = approved
        self._event.set()


class HostKeyGate(QObject):
    """Lives on the GUI thread; bridges worker-thread requests to modal dialogs."""

    unknown_host_key = pyqtSignal(object)  # HostKeyRequest
    changed_host_key = pyqtSignal(object)  # HostKeyRequest

    def ask_unknown(self, hostname: str, key: paramiko.PKey) -> bool:
        req = HostKeyRequest(hostname=hostname, key_type=key.get_name(),
                              new_fingerprint=fingerprint(key))
        self.unknown_host_key.emit(req)
        return req.wait()

    def ask_changed(self, hostname: str, key_type: str, old_key: paramiko.PKey,
                     new_key: paramiko.PKey) -> bool:
        req = HostKeyRequest(hostname=hostname, key_type=key_type,
                              new_fingerprint=fingerprint(new_key),
                              old_fingerprint=fingerprint(old_key))
        self.changed_host_key.emit(req)
        return req.wait()


class TrustOnFirstUsePolicy(paramiko.MissingHostKeyPolicy):
    """Prompts the user (via the GUI thread) before trusting a brand-new host."""

    def __init__(self, gate: HostKeyGate) -> None:
        self._gate = gate

    def missing_host_key(self, client: paramiko.SSHClient, hostname: str,
                          key: paramiko.PKey) -> None:
        if self._gate.ask_unknown(hostname, key):
            client.get_host_keys().add(hostname, key.get_name(), key)
            client.save_host_keys(str(known_hosts_path()))
        else:
            raise paramiko.SSHException(f"Host key for {hostname} rejected by user")


def verify_and_connect(client: paramiko.SSHClient, gate: HostKeyGate, **connect_kwargs) -> None:
    """
    connect() a paramiko SSHClient that has already had load_host_keys() and
    set_missing_host_key_policy(TrustOnFirstUsePolicy(gate)) applied, handling
    the changed-key (BadHostKeyException) case with a GUI warning + retry.
    """
    try:
        client.connect(**connect_kwargs)
    except paramiko.BadHostKeyException as exc:
        if not gate.ask_changed(exc.hostname, exc.key.get_name(), exc.expected_key, exc.key):
            raise
        client.get_host_keys().add(exc.hostname, exc.key.get_name(), exc.key)
        client.save_host_keys(str(known_hosts_path()))
        client.connect(**connect_kwargs)
