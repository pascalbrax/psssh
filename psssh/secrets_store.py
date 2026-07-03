"""Secure storage for bookmark passwords, via the OS credential store (keyring)."""
from __future__ import annotations

import sys
from typing import Optional

import keyring

if getattr(sys, "frozen", False):
    # keyring normally picks its backend by scanning installed-package entry
    # points, which don't exist inside a PyInstaller bundle - set it explicitly
    # instead of relying on that discovery.
    from keyring.backends import Windows
    keyring.set_keyring(Windows.WinVaultKeyring())

_SERVICE = "psssh"


def set_password(bookmark_id: str, password: str) -> None:
    keyring.set_password(_SERVICE, bookmark_id, password)


def get_password(bookmark_id: str) -> Optional[str]:
    try:
        return keyring.get_password(_SERVICE, bookmark_id)
    except Exception:
        return None


def delete_password(bookmark_id: str) -> None:
    try:
        keyring.delete_password(_SERVICE, bookmark_id)
    except Exception:
        pass
