"""Remote file browser widget backed by SftpWorker."""
from __future__ import annotations

import os
import posixpath
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime
from typing import Dict, List, Optional

from PyQt6.QtCore import QFileSystemWatcher, Qt
from PyQt6.QtWidgets import (QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                              QMenu, QMessageBox, QToolButton, QTreeWidget, QTreeWidgetItem,
                              QVBoxLayout, QWidget)

from .settings import AppSettings
from .sftp_worker import SftpEntry, SftpWorker


def _human_size(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


class SftpPanel(QWidget):
    def __init__(self, worker: SftpWorker, settings: AppSettings, initial_path: str = ".",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._worker = worker
        self._settings = settings
        self._current_path = initial_path
        self._entries: List[SftpEntry] = []

        self._edit_tmp_dir: Optional[str] = None
        self._pending_edit_downloads: Dict[str, str] = {}  # remote path -> local path
        self._edit_remote_by_local: Dict[str, str] = {}    # local path -> remote path
        self._watcher = QFileSystemWatcher()
        self._watcher.fileChanged.connect(self._on_edited_file_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        nav = QHBoxLayout()
        self._up_btn = QToolButton()
        self._up_btn.setText("Up")
        self._refresh_btn = QToolButton()
        self._refresh_btn.setText("Refresh")
        self._path_edit = QLineEdit()
        nav.addWidget(self._up_btn)
        nav.addWidget(self._refresh_btn)
        nav.addWidget(self._path_edit, 1)
        layout.addLayout(nav)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(3)
        self._tree.setHeaderLabels(["Name", "Size", "Modified"])
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.setRootIsDecorated(False)
        layout.addWidget(self._tree, 1)

        actions_row = QHBoxLayout()
        self._upload_btn = QToolButton()
        self._upload_btn.setText("Upload...")
        self._download_btn = QToolButton()
        self._download_btn.setText("Download")
        self._mkdir_btn = QToolButton()
        self._mkdir_btn.setText("New Folder")
        self._delete_btn = QToolButton()
        self._delete_btn.setText("Delete")
        for b in (self._upload_btn, self._download_btn, self._mkdir_btn, self._delete_btn):
            actions_row.addWidget(b)
        actions_row.addStretch(1)
        layout.addLayout(actions_row)

        self._status = QLabel("")
        layout.addWidget(self._status)

        self._up_btn.clicked.connect(self._go_up)
        self._refresh_btn.clicked.connect(self.refresh)
        self._path_edit.returnPressed.connect(self._go_to_typed_path)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._upload_btn.clicked.connect(self._upload_dialog)
        self._download_btn.clicked.connect(self._download_selected)
        self._mkdir_btn.clicked.connect(self._mkdir_dialog)
        self._delete_btn.clicked.connect(self._delete_selected)

        worker.listed.connect(self._on_listed)
        worker.error.connect(self._on_error)
        worker.transfer_started.connect(
            lambda name: self._status.setText(f"Transferring {posixpath.basename(name)}..."))
        worker.transfer_finished.connect(self._on_transfer_finished)
        worker.operation_done.connect(self.refresh)

    def start(self) -> None:
        self._worker.start()
        self.refresh()

    def stop(self) -> None:
        self._worker.stop()
        if self._watcher.files():
            self._watcher.removePaths(self._watcher.files())
        if self._edit_tmp_dir:
            import shutil
            shutil.rmtree(self._edit_tmp_dir, ignore_errors=True)

    def refresh(self) -> None:
        self._worker.list_dir(self._current_path)

    def _go_up(self) -> None:
        if self._current_path in ("/", ""):
            return
        self._current_path = posixpath.dirname(self._current_path.rstrip("/")) or "/"
        self.refresh()

    def _go_to_typed_path(self) -> None:
        self._current_path = self._path_edit.text().strip() or "."
        self.refresh()

    def _on_listed(self, path: str, entries: List[SftpEntry]) -> None:
        self._current_path = path
        self._path_edit.setText(path)
        self._entries = entries
        self._tree.clear()
        for e in entries:
            size_text = "" if e.is_dir else _human_size(e.size)
            mtime_text = datetime.fromtimestamp(e.mtime).strftime("%Y-%m-%d %H:%M") if e.mtime else ""
            name = e.name + ("/" if e.is_dir else "")
            item = QTreeWidgetItem([name, size_text, mtime_text])
            item.setData(0, Qt.ItemDataRole.UserRole, e)
            self._tree.addTopLevelItem(item)
        self._status.setText(f"{len(entries)} items")

    def _on_error(self, message: str) -> None:
        self._status.setText(f"Error: {message}")

    def _selected_entry(self) -> Optional[SftpEntry]:
        items = self._tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, Qt.ItemDataRole.UserRole)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        entry: SftpEntry = item.data(0, Qt.ItemDataRole.UserRole)
        if entry.is_dir:
            self._current_path = posixpath.join(self._current_path, entry.name)
            self.refresh()
        else:
            self._download_entry(entry)

    def _download_entry(self, entry: SftpEntry) -> None:
        remote = posixpath.join(self._current_path, entry.name)
        local, _ = QFileDialog.getSaveFileName(self, "Save file as", entry.name)
        if local:
            self._worker.download(remote, local)

    def _download_selected(self) -> None:
        entry = self._selected_entry()
        if entry and not entry.is_dir:
            self._download_entry(entry)

    def _upload_dialog(self) -> None:
        local, _ = QFileDialog.getOpenFileName(self, "Upload file")
        if local:
            remote = posixpath.join(self._current_path, os.path.basename(local))
            self._worker.upload(local, remote)

    def _mkdir_dialog(self) -> None:
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name:
            self._worker.mkdir(posixpath.join(self._current_path, name))

    def _delete_selected(self) -> None:
        entry = self._selected_entry()
        if not entry:
            return
        kind = "folder" if entry.is_dir else "file"
        reply = QMessageBox.question(self, "Delete", f"Delete {kind} '{entry.name}'?")
        if reply == QMessageBox.StandardButton.Yes:
            self._worker.delete(posixpath.join(self._current_path, entry.name), entry.is_dir)

    def _show_context_menu(self, pos) -> None:
        entry = self._selected_entry()
        menu = QMenu(self)
        dl = menu.addAction("Download")
        dl.setEnabled(bool(entry) and not entry.is_dir)
        edit = menu.addAction("Edit")
        edit.setEnabled(bool(entry) and not entry.is_dir)
        up = menu.addAction("Upload here...")
        menu.addSeparator()
        mkdir = menu.addAction("New Folder...")
        rename = menu.addAction("Rename...")
        rename.setEnabled(bool(entry))
        delete = menu.addAction("Delete")
        delete.setEnabled(bool(entry))
        menu.addSeparator()
        refresh = menu.addAction("Refresh")
        chosen = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if chosen == dl:
            self._download_selected()
        elif chosen == edit and entry:
            self._edit_entry(entry)
        elif chosen == up:
            self._upload_dialog()
        elif chosen == mkdir:
            self._mkdir_dialog()
        elif chosen == rename and entry:
            self._rename_entry(entry)
        elif chosen == delete:
            self._delete_selected()
        elif chosen == refresh:
            self.refresh()

    # -- edit with external editor -----------------------------------------
    def _get_edit_dir(self) -> str:
        if not self._edit_tmp_dir:
            self._edit_tmp_dir = tempfile.mkdtemp(prefix="psssh_edit_")
        return self._edit_tmp_dir

    def _edit_entry(self, entry: SftpEntry) -> None:
        remote = posixpath.join(self._current_path, entry.name)
        local = os.path.join(self._get_edit_dir(), entry.name)
        self._pending_edit_downloads[remote] = local
        self._worker.download(remote, local)

    def _on_transfer_finished(self, name: str) -> None:
        if name in self._pending_edit_downloads:
            local = self._pending_edit_downloads.pop(name)
            self._launch_editor(name, local)
        else:
            self._status.setText(f"Done: {posixpath.basename(name)}")

    def _launch_editor(self, remote: str, local: str) -> None:
        editor_command = self._settings.editor_command.strip()
        try:
            if editor_command:
                # A plain path (the common case, picked via the Browse button) may
                # contain spaces, so only shlex-split when it isn't a literal file
                # -- that lets power users still type e.g. "code -w" style commands.
                if os.path.isfile(editor_command):
                    cmd = [editor_command, local]
                else:
                    cmd = shlex.split(editor_command, posix=sys.platform != "win32") + [local]
                subprocess.Popen(cmd)
            elif sys.platform == "win32":
                os.startfile(local)  # noqa: S606 - opens with the OS-registered default app
            elif sys.platform == "darwin":
                subprocess.Popen(["open", local])
            else:
                subprocess.Popen(["xdg-open", local])
        except Exception as exc:  # noqa: BLE001
            self._status.setText(f"Could not launch editor: {exc}")
            return
        self._edit_remote_by_local[local] = remote
        self._watcher.addPath(local)
        self._status.setText(f"Editing {posixpath.basename(remote)} — changes will be uploaded on save")

    def _on_edited_file_changed(self, local: str) -> None:
        remote = self._edit_remote_by_local.get(local)
        if not remote:
            return
        if os.path.exists(local):
            self._worker.upload(local, remote)
            self._status.setText(f"Re-uploaded {posixpath.basename(remote)} after edit")
            # Some editors save by replacing the file, which drops it from the
            # watcher; re-add so further saves keep being picked up.
            if local not in self._watcher.files():
                self._watcher.addPath(local)
        else:
            self._edit_remote_by_local.pop(local, None)

    def _rename_entry(self, entry: SftpEntry) -> None:
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=entry.name)
        if ok and new_name and new_name != entry.name:
            old_path = posixpath.join(self._current_path, entry.name)
            new_path = posixpath.join(self._current_path, new_name)
            self._worker.rename(old_path, new_path)
