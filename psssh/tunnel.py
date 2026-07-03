"""Local (`ssh -L`) and remote (`ssh -R`) SSH port forwarding over paramiko."""
from __future__ import annotations

import select
import socket
import socketserver
import threading
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

import paramiko


@dataclass
class TunnelSpec:
    kind: str  # "local" or "remote"
    bind_host: str
    bind_port: int
    dest_host: str
    dest_port: int
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def description(self) -> str:
        if self.kind == "local":
            return (f"Local  {self.bind_host}:{self.bind_port}  ->  "
                    f"{self.dest_host}:{self.dest_port} (on remote host)")
        return (f"Remote  {self.bind_host}:{self.bind_port} (on remote host)  ->  "
                f"{self.dest_host}:{self.dest_port} (local)")


def _relay(chan: paramiko.Channel, sock: socket.socket) -> None:
    try:
        while True:
            r, _, _ = select.select([sock, chan], [], [])
            if sock in r:
                data = sock.recv(4096)
                if not data:
                    break
                chan.send(data)
            if chan in r:
                data = chan.recv(4096)
                if not data:
                    break
                sock.send(data)
    except (OSError, EOFError):
        pass
    finally:
        try:
            chan.close()
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass


class _ForwardServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


class _LocalForwardHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server = self.server
        try:
            peer = self.request.getpeername()
        except OSError:
            peer = ("127.0.0.1", 0)
        try:
            chan = server.transport.open_channel(
                "direct-tcpip", (server.dest_host, server.dest_port), peer, timeout=10)
        except Exception:
            chan = None
        if chan is None:
            return
        _relay(chan, self.request)


class LocalForwarder:
    """Listens locally and forwards each connection over the SSH transport."""

    def __init__(self, transport: paramiko.Transport, spec: TunnelSpec) -> None:
        self.spec = spec
        self._server = _ForwardServer((spec.bind_host, spec.bind_port), _LocalForwardHandler)
        self._server.transport = transport
        self._server.dest_host = spec.dest_host
        self._server.dest_port = spec.dest_port
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


class TunnelManager:
    """
    Owns every tunnel (local + remote) for a single SSH transport.

    Remote forwarding needs special care: paramiko keeps exactly one dispatch
    handler per Transport for *all* forwarded-tcpip connections, no matter how
    many remote ports were requested. So instead of one handler per tunnel, we
    install a single dispatcher keyed by allocated port and route incoming
    channels to the right local destination ourselves.
    """

    def __init__(self, transport_provider) -> None:
        self._transport_provider = transport_provider
        self._locals: Dict[str, LocalForwarder] = {}
        self._remotes: Dict[str, TunnelSpec] = {}
        self._remote_by_port: Dict[int, TunnelSpec] = {}

    def active_specs(self):
        specs = [f.spec for f in self._locals.values()]
        specs.extend(self._remotes.values())
        return specs

    def add(self, spec: TunnelSpec) -> None:
        transport = self._transport_provider()
        if transport is None:
            raise RuntimeError("Not connected")
        if spec.kind == "local":
            forwarder = LocalForwarder(transport, spec)
            forwarder.start()
            self._locals[spec.id] = forwarder
        else:
            transport.request_port_forward(spec.bind_host, spec.bind_port,
                                            handler=self._dispatch_remote)
            self._remotes[spec.id] = spec
            self._remote_by_port[spec.bind_port] = spec

    def _dispatch_remote(self, channel: paramiko.Channel, origin_addr_port, server_addr_port) -> None:
        _server_addr, server_port = server_addr_port
        spec = self._remote_by_port.get(server_port)
        if spec is None:
            channel.close()
            return
        try:
            sock = socket.create_connection((spec.dest_host, spec.dest_port), timeout=10)
        except OSError:
            channel.close()
            return
        threading.Thread(target=_relay, args=(channel, sock), daemon=True).start()

    def remove(self, spec_id: str) -> None:
        if spec_id in self._locals:
            self._locals.pop(spec_id).stop()
            return
        spec = self._remotes.pop(spec_id, None)
        if spec is None:
            return
        self._remote_by_port.pop(spec.bind_port, None)
        transport = self._transport_provider()
        if transport is not None:
            try:
                transport.cancel_port_forward(spec.bind_host, spec.bind_port)
            except Exception:
                pass
            # cancel_port_forward() unconditionally clears the transport's single
            # (shared, per-transport) dispatch handler slot; if other remote
            # tunnels are still active on this transport, put it back rather than
            # sending another "tcpip-forward" request (which would open a new port).
            if self._remotes:
                transport._tcp_handler = self._dispatch_remote

    def stop_all(self) -> None:
        for forwarder in list(self._locals.values()):
            forwarder.stop()
        self._locals.clear()
        transport = self._transport_provider()
        for spec in list(self._remotes.values()):
            if transport is not None:
                try:
                    transport.cancel_port_forward(spec.bind_host, spec.bind_port)
                except Exception:
                    pass
        self._remotes.clear()
        self._remote_by_port.clear()
