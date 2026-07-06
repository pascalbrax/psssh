"""Top-level window: address bar, tabbed sessions, menus, status bar."""
from __future__ import annotations

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (QComboBox, QInputDialog, QLabel, QMainWindow, QMessageBox,
                              QTabWidget, QToolBar)

from . import __version__, secrets_store
from .bookmarks import Bookmark, BookmarkManager
from .commands import CommandManager
from .connection import ConnectionSpec
from .dialogs.bookmark_dialog import BookmarkEditDialog, BookmarkManagerDialog
from .dialogs.command_dialog import CommandManagerDialog
from .dialogs.settings_dialog import SettingsDialog
from .dialogs.tunnel_dialog import TunnelManagerDialog
from .icon import app_icon
from .session_widget import SessionWidget
from .settings import AppSettings


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = AppSettings()
        self.bookmarks = BookmarkManager()
        self.commands = CommandManager()

        self.setWindowTitle("Pascal Simple SSH")
        self.setWindowIcon(app_icon())
        self.resize(1000, 650)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        self._build_toolbar()
        self._build_menu()
        self.statusBar().showMessage("Ready")

    # -- toolbar / menu construction --------------------------------------
    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Connection")
        toolbar.setMovable(False)
        toolbar.addWidget(QLabel(" Host: "))

        self.address_combo = QComboBox()
        self.address_combo.setEditable(True)
        self.address_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.address_combo.lineEdit().setPlaceholderText(
            "user@host:port  (or just host, IP, etc.)")
        self.address_combo.lineEdit().returnPressed.connect(self._connect_from_address_bar)
        self.address_combo.setMinimumWidth(320)
        self.address_combo.addItems(self.settings.recent_connections)
        self.address_combo.setCurrentText("")
        toolbar.addWidget(self.address_combo)

        connect_action = QAction("Connect", self)
        connect_action.triggered.connect(self._connect_from_address_bar)
        toolbar.addAction(connect_action)

        self.addToolBar(toolbar)

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        new_conn = QAction("&New Connection...", self)
        new_conn.setShortcut(QKeySequence("Ctrl+N"))
        new_conn.triggered.connect(lambda: self.address_combo.setFocus())
        file_menu.addAction(new_conn)

        close_tab = QAction("&Close Tab", self)
        close_tab.setShortcut(QKeySequence("Ctrl+W"))
        close_tab.triggered.connect(lambda: self._close_tab(self.tabs.currentIndex()))
        file_menu.addAction(close_tab)

        file_menu.addSeparator()
        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        view_menu = menubar.addMenu("&View")
        self.toggle_sftp_action = QAction("Show SFTP Panel", self)
        self.toggle_sftp_action.setCheckable(True)
        self.toggle_sftp_action.setChecked(self.settings.show_sftp_panel)
        self.toggle_sftp_action.triggered.connect(self._toggle_sftp_panel)
        view_menu.addAction(self.toggle_sftp_action)

        view_menu.addSeparator()
        screenshot_action = QAction("Copy &Terminal Screenshot", self)
        screenshot_action.setShortcut(QKeySequence("Ctrl+Shift+G"))
        screenshot_action.triggered.connect(self._screenshot_terminal)
        view_menu.addAction(screenshot_action)

        self._bookmarks_menu = menubar.addMenu("&Bookmarks")
        add_bookmark = QAction("&Add Bookmark for Current Tab...", self)
        add_bookmark.triggered.connect(self._add_bookmark_current)
        self._bookmarks_menu.addAction(add_bookmark)

        manage_bookmarks = QAction("&Manage Bookmarks...", self)
        manage_bookmarks.triggered.connect(self._manage_bookmarks)
        self._bookmarks_menu.addAction(manage_bookmarks)

        self._bookmarks_menu.addSeparator()
        self._static_bookmark_action_count = len(self._bookmarks_menu.actions())
        self._rebuild_bookmarks_menu()

        tunnels_menu = menubar.addMenu("&Tunnels")
        manage_tunnels = QAction("&Manage Tunnels for Current Tab...", self)
        manage_tunnels.triggered.connect(self._manage_tunnels)
        tunnels_menu.addAction(manage_tunnels)

        self._commands_menu = menubar.addMenu("&Commands")
        send_command = QAction("&Send Command...", self)
        send_command.triggered.connect(self._send_adhoc_command)
        self._commands_menu.addAction(send_command)

        manage_commands = QAction("&Manage Commands...", self)
        manage_commands.triggered.connect(self._manage_commands)
        self._commands_menu.addAction(manage_commands)

        self._commands_menu.addSeparator()
        self._static_command_action_count = len(self._commands_menu.actions())
        self._rebuild_commands_menu()

        settings_menu = menubar.addMenu("&Settings")
        prefs = QAction("&Preferences...", self)
        prefs.triggered.connect(self._open_settings_dialog)
        settings_menu.addAction(prefs)

        help_menu = menubar.addMenu("&Help")
        about = QAction("&About Pascal Simple SSH", self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

    def _rebuild_bookmarks_menu(self) -> None:
        for action in self._bookmarks_menu.actions()[self._static_bookmark_action_count:]:
            self._bookmarks_menu.removeAction(action)
        for bookmark in self.bookmarks.bookmarks:
            action = QAction(bookmark.display, self)
            action.triggered.connect(lambda checked=False, b=bookmark: self._connect_bookmark(b))
            self._bookmarks_menu.addAction(action)

    def _rebuild_commands_menu(self) -> None:
        for action in self._commands_menu.actions()[self._static_command_action_count:]:
            self._commands_menu.removeAction(action)
        for command in self.commands.commands:
            action = QAction(command.name, self)
            action.setToolTip(command.text)
            action.triggered.connect(lambda checked=False, c=command: self._send_command_text(c.text))
            self._commands_menu.addAction(action)

    # -- connecting --------------------------------------------------------
    def _connect_from_address_bar(self) -> None:
        text = self.address_combo.currentText().strip()
        if not text:
            return
        try:
            spec = ConnectionSpec.parse(text, default_user=self.settings.default_user or None)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid host", str(exc))
            return
        self._remember_recent(text)
        self.address_combo.lineEdit().clear()
        self._open_session(spec)

    def _remember_recent(self, text: str) -> None:
        self.settings.add_recent_connection(text)
        self.address_combo.blockSignals(True)
        self.address_combo.clear()
        self.address_combo.addItems(self.settings.recent_connections)
        self.address_combo.setCurrentText("")
        self.address_combo.blockSignals(False)

    def _connect_bookmark(self, bookmark: Bookmark) -> None:
        spec = ConnectionSpec(host=bookmark.host, user=bookmark.user, port=bookmark.port,
                               key_file=bookmark.key_file or None)
        password = secrets_store.get_password(bookmark.id) if bookmark.save_password else None
        self._open_session(spec, initial_password=password)

    def _open_session(self, spec: ConnectionSpec, initial_password: str = None) -> None:
        session = SessionWidget(spec, self.settings, initial_password=initial_password)
        index = self.tabs.addTab(session, spec.label)
        self.tabs.setCurrentIndex(index)
        session.status_changed.connect(lambda msg, s=session: self._on_session_status(s, msg))
        session.title_changed.connect(lambda title, s=session: self._on_session_title(s, title))
        session.start()

    def _on_session_status(self, session: SessionWidget, message: str) -> None:
        if self.tabs.currentWidget() is session:
            self.statusBar().showMessage(message, 5000)

    def _on_session_title(self, session: SessionWidget, title: str) -> None:
        idx = self.tabs.indexOf(session)
        if idx >= 0 and title:
            self.tabs.setTabText(idx, title)

    def _close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is None:
            return
        widget.stop()
        self.tabs.removeTab(index)
        widget.deleteLater()

    def _on_tab_changed(self, index: int) -> None:
        session = self.tabs.widget(index)
        if isinstance(session, SessionWidget):
            self.toggle_sftp_action.setChecked(session.is_sftp_visible())

    def _toggle_sftp_panel(self) -> None:
        session = self.tabs.currentWidget()
        if isinstance(session, SessionWidget):
            session.toggle_sftp_panel()
            self.toggle_sftp_action.setChecked(session.is_sftp_visible())

    def _screenshot_terminal(self) -> None:
        session = self.tabs.currentWidget()
        if not isinstance(session, SessionWidget):
            QMessageBox.information(self, "Copy Terminal Screenshot", "Open a connection first.")
            return
        session.terminal.screenshot_to_clipboard()
        self.statusBar().showMessage("Terminal screenshot copied to clipboard", 4000)

    def _manage_tunnels(self) -> None:
        session = self.tabs.currentWidget()
        if not isinstance(session, SessionWidget):
            QMessageBox.information(self, "SSH Tunnels", "Open a connection first.")
            return
        if session.ssh_worker.transport is None:
            QMessageBox.information(self, "SSH Tunnels", "This tab isn't connected yet.")
            return
        dialog = TunnelManagerDialog(session.tunnel_manager, self)
        dialog.exec()

    def _send_command_text(self, text: str) -> None:
        session = self.tabs.currentWidget()
        if not isinstance(session, SessionWidget):
            QMessageBox.information(self, "Send Command", "Open a connection first.")
            return
        if session.ssh_worker.transport is None:
            QMessageBox.information(self, "Send Command", "This tab isn't connected yet.")
            return
        session.ssh_worker.send(text.encode("utf-8") + b"\r")

    def _send_adhoc_command(self) -> None:
        text, ok = QInputDialog.getText(self, "Send Command", "Command:")
        if ok and text:
            self._send_command_text(text)

    def _manage_commands(self) -> None:
        dialog = CommandManagerDialog(self.commands, self)
        dialog.exec()
        self._rebuild_commands_menu()

    # -- bookmarks / settings dialogs --------------------------------------
    def _add_bookmark_current(self) -> None:
        session = self.tabs.currentWidget()
        if not isinstance(session, SessionWidget):
            QMessageBox.information(self, "Add Bookmark", "Open a connection first.")
            return
        spec = session.spec
        draft = Bookmark(name=spec.label, host=spec.host, user=spec.user, port=spec.port,
                          key_file=spec.key_file or "")
        captured_password = session.ssh_worker.used_password
        dialog = BookmarkEditDialog(draft, self, captured_password=captured_password)
        dialog.setWindowTitle("Add Bookmark")
        if dialog.exec():
            bookmark = dialog.result_bookmark()
            self.bookmarks.add(bookmark)
            dialog.apply_password(bookmark)
            self._rebuild_bookmarks_menu()

    def _manage_bookmarks(self) -> None:
        dialog = BookmarkManagerDialog(self.bookmarks, self)
        dialog.exec()
        self._rebuild_bookmarks_menu()

    def _open_settings_dialog(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            for i in range(self.tabs.count()):
                widget = self.tabs.widget(i)
                if isinstance(widget, SessionWidget):
                    widget.terminal.apply_font(self.settings.font_family, self.settings.font_size)
                    widget.terminal.apply_palette(self.settings.theme)

    def _show_about(self) -> None:
        QMessageBox.about(self, "About Pascal Simple SSH",
                           f"Pascal Simple SSH v{__version__} — a powerful SSH/SFTP client\n\n"
                           "Built with PyQt6, paramiko and pyte.")

    def closeEvent(self, event) -> None:
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if isinstance(widget, SessionWidget):
                widget.stop()
        super().closeEvent(event)
