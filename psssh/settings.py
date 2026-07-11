"""Application preferences, persisted via QSettings (registry-backed on Windows)."""
from __future__ import annotations

from PyQt6.QtCore import QByteArray, QSettings

ORG_NAME = "psssh"
APP_NAME = "psssh"


class AppSettings:
    """Thin typed wrapper around QSettings for the preferences we expose."""

    def __init__(self) -> None:
        self._qs = QSettings(ORG_NAME, APP_NAME)

    # -- appearance ------------------------------------------------------
    @property
    def theme(self) -> str:
        return self._qs.value("ui/theme", "system", type=str)

    @theme.setter
    def theme(self, value: str) -> None:
        self._qs.setValue("ui/theme", value)

    @property
    def window_geometry(self) -> QByteArray:
        return self._qs.value("ui/window_geometry", QByteArray(), type=QByteArray)

    @window_geometry.setter
    def window_geometry(self, value: QByteArray) -> None:
        self._qs.setValue("ui/window_geometry", value)

    # -- keepalive -----------------------------------------------------
    @property
    def keepalive_enabled(self) -> bool:
        return self._qs.value("ssh/keepalive_enabled", True, type=bool)

    @keepalive_enabled.setter
    def keepalive_enabled(self, value: bool) -> None:
        self._qs.setValue("ssh/keepalive_enabled", value)

    @property
    def keepalive_interval(self) -> int:
        """Seconds between SSH-level keepalive packets."""
        return self._qs.value("ssh/keepalive_interval", 30, type=int)

    @keepalive_interval.setter
    def keepalive_interval(self, value: int) -> None:
        self._qs.setValue("ssh/keepalive_interval", value)

    # -- terminal appearance --------------------------------------------
    @property
    def font_family(self) -> str:
        return self._qs.value("terminal/font_family", "Cascadia Mono", type=str)

    @font_family.setter
    def font_family(self, value: str) -> None:
        self._qs.setValue("terminal/font_family", value)

    @property
    def font_size(self) -> int:
        return self._qs.value("terminal/font_size", 11, type=int)

    @font_size.setter
    def font_size(self, value: int) -> None:
        self._qs.setValue("terminal/font_size", value)

    @property
    def scrollback_lines(self) -> int:
        return self._qs.value("terminal/scrollback_lines", 5000, type=int)

    @scrollback_lines.setter
    def scrollback_lines(self, value: int) -> None:
        self._qs.setValue("terminal/scrollback_lines", value)

    # -- connection defaults ---------------------------------------------
    @property
    def default_user(self) -> str:
        return self._qs.value("connection/default_user", "", type=str)

    @default_user.setter
    def default_user(self, value: str) -> None:
        self._qs.setValue("connection/default_user", value)

    @property
    def show_sftp_panel(self) -> bool:
        return self._qs.value("ui/show_sftp_panel", True, type=bool)

    @show_sftp_panel.setter
    def show_sftp_panel(self, value: bool) -> None:
        self._qs.setValue("ui/show_sftp_panel", value)

    # -- external editor (SFTP "Edit" action) -----------------------------
    @property
    def editor_command(self) -> str:
        return self._qs.value("editor/command", "", type=str)

    @editor_command.setter
    def editor_command(self, value: str) -> None:
        self._qs.setValue("editor/command", value)

    # -- recent connections (address bar dropdown) ------------------------
    MAX_RECENT = 20

    @property
    def recent_connections(self) -> list:
        value = self._qs.value("connection/recent", [], type=list)
        return list(value) if value else []

    def add_recent_connection(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        recent = [t for t in self.recent_connections if t != text]
        recent.insert(0, text)
        self._qs.setValue("connection/recent", recent[: self.MAX_RECENT])

    def sync(self) -> None:
        self._qs.sync()
