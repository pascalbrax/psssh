"""Add/edit/manage saved command snippets."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLineEdit,
                              QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                              QVBoxLayout, QWidget)

from ..commands import CommandManager, SavedCommand


class CommandEditDialog(QDialog):
    def __init__(self, command: Optional[SavedCommand], parent: QWidget = None) -> None:
        super().__init__(parent)
        self._command = command
        self.setWindowTitle("Edit Command" if command else "Add Command")
        self.setMinimumSize(420, 160)

        form = QFormLayout()
        self.name_edit = QLineEdit(command.name if command else "")
        self.text_edit = QLineEdit(command.text if command else "")
        form.addRow("Name:", self.name_edit)
        form.addRow("Command:", self.text_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        if not self.name_edit.text().strip() or not self.text_edit.text().strip():
            QMessageBox.warning(self, "Missing information", "Name and command are required.")
            return
        self.accept()

    def result_command(self) -> SavedCommand:
        kwargs = dict(name=self.name_edit.text().strip(), text=self.text_edit.text())
        if self._command:
            kwargs["id"] = self._command.id
        return SavedCommand(**kwargs)


class CommandManagerDialog(QDialog):
    def __init__(self, manager: CommandManager, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Manage Commands")
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
        for cmd in self.manager.commands:
            item = QListWidgetItem(f"{cmd.name}  —  {cmd.text}")
            item.setData(Qt.ItemDataRole.UserRole, cmd.id)
            self.list_widget.addItem(item)

    def _selected_command(self) -> Optional[SavedCommand]:
        item = self.list_widget.currentItem()
        if not item:
            return None
        cid = item.data(Qt.ItemDataRole.UserRole)
        for cmd in self.manager.commands:
            if cmd.id == cid:
                return cmd
        return None

    def _add(self) -> None:
        dialog = CommandEditDialog(None, self)
        if dialog.exec():
            self.manager.add(dialog.result_command())
            self._reload()

    def _edit(self) -> None:
        cmd = self._selected_command()
        if not cmd:
            return
        dialog = CommandEditDialog(cmd, self)
        if dialog.exec():
            self.manager.update(dialog.result_command())
            self._reload()

    def _remove(self) -> None:
        cmd = self._selected_command()
        if not cmd:
            return
        reply = QMessageBox.question(self, "Remove Command", f"Remove command '{cmd.name}'?")
        if reply == QMessageBox.StandardButton.Yes:
            self.manager.remove(cmd.id)
            self._reload()
