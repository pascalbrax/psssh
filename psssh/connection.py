"""Parsing of free-form host strings typed into the address bar."""
from __future__ import annotations

import getpass
import re
from dataclasses import dataclass, field
from typing import Optional

# user@host:port, ssh://user@host:port, [ipv6]:port, bare host, etc.
_HOST_RE = re.compile(
    r"^\s*(?:ssh://)?"
    r"(?:(?P<user>[^@\s]+)@)?"
    r"(?P<host>\[[0-9A-Fa-f:]+\]|[^:\s/]+)"
    r"(?::(?P<port>\d{1,5}))?"
    r"/?\s*$"
)

DEFAULT_PORT = 22


@dataclass
class ConnectionSpec:
    host: str
    user: str
    port: int = DEFAULT_PORT
    key_file: Optional[str] = None
    raw: str = field(default="")

    @property
    def label(self) -> str:
        suffix = "" if self.port == DEFAULT_PORT else f":{self.port}"
        return f"{self.user}@{self.host}{suffix}"

    @classmethod
    def parse(cls, text: str, default_user: Optional[str] = None) -> "ConnectionSpec":
        match = _HOST_RE.match(text or "")
        if not match:
            raise ValueError(f"Could not parse host: {text!r}")

        host = match.group("host")
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]
        if not host:
            raise ValueError("Empty host")

        user = match.group("user") or default_user or getpass.getuser()
        port = int(match.group("port")) if match.group("port") else DEFAULT_PORT

        return cls(host=host, user=user, port=port, raw=text.strip())
