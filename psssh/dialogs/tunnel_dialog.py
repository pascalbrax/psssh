"""Configure and manage SSH tunnels (local/remote port forwarding) for a session."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                              QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                              QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ..tunnel import TunnelManager, TunnelSpec


class TunnelConfigDialog(QDialog):
    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New SSH Tunnel")
        self.setMinimumSize(460, 260)

        form = QFormLayout()
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Local", "local")
        self.kind_combo.addItem("Remote", "remote")
        form.addRow("Type:", self.kind_combo)

        self.note_label = QLabel()
        self.note_label.setWordWrap(True)
        form.addRow(self.note_label)

        self.bind_host_edit = QLineEdit("127.0.0.1")
        self.bind_port_spin = QSpinBox()
        self.bind_port_spin.setRange(1, 65535)
        self.bind_port_spin.setValue(8080)
        self.dest_host_edit = QLineEdit("127.0.0.1")
        self.dest_port_spin = QSpinBox()
        self.dest_port_spin.setRange(1, 65535)
        self.dest_port_spin.setValue(80)

        self.bind_host_label = QLabel()
        self.dest_host_label = QLabel()
        form.addRow(self.bind_host_label, self.bind_host_edit)
        form.addRow("Bind port:", self.bind_port_spin)
        form.addRow(self.dest_host_label, self.dest_host_edit)
        form.addRow("Destination port:", self.dest_port_spin)

        self.kind_combo.currentIndexChanged.connect(self._update_labels)
        self._update_labels()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _update_labels(self) -> None:
        if self.kind_combo.currentData() == "local":
            self.note_label.setText(
                "Listen on this machine and forward each connection through the SSH "
                "server to a destination it can reach.")
            self.bind_host_label.setText("Listen address (here):")
            self.dest_host_label.setText("Destination host (from remote host):")
        else:
            self.note_label.setText(
                "Ask the SSH server to listen on its side and forward each connection "
                "back to a destination this machine can reach.")
            self.bind_host_label.setText("Listen address (on remote host):")
            self.dest_host_label.setText("Destination host (from here):")

    def result_spec(self) -> TunnelSpec:
        return TunnelSpec(
            kind=self.kind_combo.currentData(),
            bind_host=self.bind_host_edit.text().strip() or "127.0.0.1",
            bind_port=self.bind_port_spin.value(),
            dest_host=self.dest_host_edit.text().strip() or "127.0.0.1",
            dest_port=self.dest_port_spin.value(),
        )


class TunnelManagerDialog(QDialog):
    def __init__(self, manager: TunnelManager, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("SSH Tunnels")
        self.resize(480, 300)

        self.list_widget = QListWidget()
        self._reload()

        add_btn = QPushButton("Add...")
        remove_btn = QPushButton("Remove")
        close_btn = QPushButton("Close")
        add_btn.clicked.connect(self._add)
        remove_btn.clicked.connect(self._remove)
        close_btn.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list_widget)
        layout.addLayout(btn_row)

    def _reload(self) -> None:
        self.list_widget.clear()
        for spec in self.manager.active_specs():
            item = QListWidgetItem(spec.description)
            item.setData(Qt.ItemDataRole.UserRole, spec.id)
            self.list_widget.addItem(item)

    def _add(self) -> None:
        dialog = TunnelConfigDialog(self)
        if dialog.exec():
            spec = dialog.result_spec()
            try:
                self.manager.add(spec)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "Tunnel error", str(exc))
                return
            self._reload()

    def _remove(self) -> None:
        item = self.list_widget.currentItem()
        if not item:
            return
        spec_id = item.data(Qt.ItemDataRole.UserRole)
        self.manager.remove(spec_id)
        self._reload()
