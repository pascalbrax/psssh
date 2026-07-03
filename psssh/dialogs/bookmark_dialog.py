"""Add/edit/manage saved connections."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                              QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                              QPushButton, QSpinBox, QVBoxLayout, QWidget)

from .. import secrets_store
from ..bookmarks import Bookmark, BookmarkManager


class BookmarkEditDialog(QDialog):
    def __init__(self, bookmark: Optional[Bookmark], parent: QWidget = None,
                 captured_password: Optional[str] = None) -> None:
        super().__init__(parent)
        self._bookmark = bookmark
        self.setWindowTitle("Edit Bookmark" if bookmark else "Add Bookmark")

        form = QFormLayout()
        self.name_edit = QLineEdit(bookmark.name if bookmark else "")
        self.host_edit = QLineEdit(bookmark.host if bookmark else "")
        self.user_edit = QLineEdit(bookmark.user if bookmark else "")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(bookmark.port if bookmark else 22)
        self.keyfile_edit = QLineEdit(bookmark.key_file if bookmark else "")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_key)

        key_row = QHBoxLayout()
        key_row.addWidget(self.keyfile_edit)
        key_row.addWidget(browse_btn)
        key_widget = QWidget()
        key_widget.setLayout(key_row)

        self.password_edit = QLineEdit(captured_password or "")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        if bookmark and bookmark.save_password and not captured_password:
            self.password_edit.setPlaceholderText("(leave blank to keep the saved password)")

        self.save_password_checkbox = QCheckBox("Save password securely (Windows Credential Manager)")
        self.save_password_checkbox.setChecked(bool(captured_password) or (bookmark.save_password if bookmark else False))

        form.addRow("Name:", self.name_edit)
        form.addRow("Host:", self.host_edit)
        form.addRow("User:", self.user_edit)
        form.addRow("Port:", self.port_spin)
        form.addRow("Private key (optional):", key_widget)
        form.addRow("Password (optional):", self.password_edit)
        form.addRow(self.save_password_checkbox)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _browse_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select private key")
        if path:
            self.keyfile_edit.setText(path)

    def _on_accept(self) -> None:
        if not self.name_edit.text().strip() or not self.host_edit.text().strip():
            QMessageBox.warning(self, "Missing information", "Name and host are required.")
            return
        self.accept()

    def result_bookmark(self) -> Bookmark:
        kwargs = dict(
            name=self.name_edit.text().strip(),
            host=self.host_edit.text().strip(),
            user=self.user_edit.text().strip(),
            port=self.port_spin.value(),
            key_file=self.keyfile_edit.text().strip(),
            save_password=self.save_password_checkbox.isChecked(),
        )
        if self._bookmark:
            kwargs["id"] = self._bookmark.id
        return Bookmark(**kwargs)

    def entered_password(self) -> Optional[str]:
        text = self.password_edit.text()
        return text if text else None

    def apply_password(self, bookmark: Bookmark) -> None:
        """Persist (or clear) the keyring secret to match the dialog's choices."""
        if bookmark.save_password:
            password = self.entered_password()
            if password:
                secrets_store.set_password(bookmark.id, password)
        else:
            secrets_store.delete_password(bookmark.id)


class BookmarkManagerDialog(QDialog):
    def __init__(self, manager: BookmarkManager, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Manage Bookmarks")
        self.resize(420, 320)

        self.list_widget = QListWidget()
        self._reload()

        add_btn = QPushButton("Add...")
        edit_btn = QPushButton("Edit...")
        remove_btn = QPushButton("Remove")
        close_btn = QPushButton("Close")

        add_btn.clicked.connect(self._add)
        edit_btn.clicked.connect(self._edit)
        remove_btn.clicked.connect(self._remove)
        close_btn.clicked.connect(self.accept)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._edit())

        btn_row = QHBoxLayout()
        for b in (add_btn, edit_btn, remove_btn):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list_widget)
        layout.addLayout(btn_row)

    def _reload(self) -> None:
        self.list_widget.clear()
        for bm in self.manager.bookmarks:
            item = QListWidgetItem(bm.display)
            item.setData(Qt.ItemDataRole.UserRole, bm.id)
            self.list_widget.addItem(item)

    def _selected_bookmark(self) -> Optional[Bookmark]:
        item = self.list_widget.currentItem()
        if not item:
            return None
        bid = item.data(Qt.ItemDataRole.UserRole)
        for bm in self.manager.bookmarks:
            if bm.id == bid:
                return bm
        return None

    def _add(self) -> None:
        dialog = BookmarkEditDialog(None, self)
        if dialog.exec():
            bm = dialog.result_bookmark()
            self.manager.add(bm)
            dialog.apply_password(bm)
            self._reload()

    def _edit(self) -> None:
        bm = self._selected_bookmark()
        if not bm:
            return
        dialog = BookmarkEditDialog(bm, self)
        if dialog.exec():
            updated = dialog.result_bookmark()
            self.manager.update(updated)
            dialog.apply_password(updated)
            self._reload()

    def _remove(self) -> None:
        bm = self._selected_bookmark()
        if not bm:
            return
        reply = QMessageBox.question(self, "Remove Bookmark", f"Remove bookmark '{bm.name}'?")
        if reply == QMessageBox.StandardButton.Yes:
            self.manager.remove(bm.id)
            self._reload()
