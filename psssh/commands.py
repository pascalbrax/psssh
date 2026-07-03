"""JSON-backed storage for user-defined command snippets sent to the active session."""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional


def _config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    path = Path(base) / "psssh"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class SavedCommand:
    name: str
    text: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)


class CommandManager:
    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or (_config_dir() / "commands.json")
        self._commands: List[SavedCommand] = []
        self.load()

    @property
    def commands(self) -> List[SavedCommand]:
        return list(self._commands)

    def load(self) -> None:
        if not self._path.exists():
            self._commands = []
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._commands = []
            return
        self._commands = [SavedCommand(**item) for item in raw]

    def save(self) -> None:
        data = [asdict(c) for c in self._commands]
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, command: SavedCommand) -> None:
        self._commands.append(command)
        self.save()

    def update(self, command: SavedCommand) -> None:
        for i, c in enumerate(self._commands):
            if c.id == command.id:
                self._commands[i] = command
                self.save()
                return
        raise KeyError(f"No command with id {command.id}")

    def remove(self, command_id: str) -> None:
        self._commands = [c for c in self._commands if c.id != command_id]
        self.save()
