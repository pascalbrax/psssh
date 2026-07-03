"""JSON-backed bookmark storage for saved connections."""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from . import secrets_store


def _config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    path = Path(base) / "psssh"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Bookmark:
    name: str
    host: str
    user: str
    port: int = 22
    key_file: str = ""
    save_password: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def display(self) -> str:
        suffix = "" if self.port == 22 else f":{self.port}"
        return f"{self.name}  ({self.user}@{self.host}{suffix})"


class BookmarkManager:
    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or (_config_dir() / "bookmarks.json")
        self._bookmarks: List[Bookmark] = []
        self.load()

    @property
    def bookmarks(self) -> List[Bookmark]:
        return list(self._bookmarks)

    def load(self) -> None:
        if not self._path.exists():
            self._bookmarks = []
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._bookmarks = []
            return
        self._bookmarks = [Bookmark(**item) for item in raw]

    def save(self) -> None:
        data = [asdict(b) for b in self._bookmarks]
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, bookmark: Bookmark) -> None:
        self._bookmarks.append(bookmark)
        self.save()

    def update(self, bookmark: Bookmark) -> None:
        for i, b in enumerate(self._bookmarks):
            if b.id == bookmark.id:
                if b.save_password and not bookmark.save_password:
                    secrets_store.delete_password(b.id)
                self._bookmarks[i] = bookmark
                self.save()
                return
        raise KeyError(f"No bookmark with id {bookmark.id}")

    def remove(self, bookmark_id: str) -> None:
        secrets_store.delete_password(bookmark_id)
        self._bookmarks = [b for b in self._bookmarks if b.id != bookmark_id]
        self.save()
