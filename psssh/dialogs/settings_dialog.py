"""Preferences dialog: keepalive, terminal appearance, connection defaults."""
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                              QFileDialog, QFontComboBox, QFormLayout, QHBoxLayout, QLineEdit,
                              QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ..settings import AppSettings
from ..theme import apply_theme


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Preferences")

        form = QFormLayout()

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("System", "system")
        self.theme_combo.addItem("Gray", "gray")
        self.theme_combo.addItem("Solarized", "solarized")
        self.theme_combo.addItem("Solarized Dark", "solarized_dark")
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(settings.theme))
        form.addRow("Theme:", self.theme_combo)

        self.keepalive_checkbox = QCheckBox("Send SSH keepalive packets")
        self.keepalive_checkbox.setChecked(settings.keepalive_enabled)
        form.addRow(self.keepalive_checkbox)

        self.keepalive_spin = QSpinBox()
        self.keepalive_spin.setRange(1, 3600)
        self.keepalive_spin.setSuffix(" s")
        self.keepalive_spin.setValue(settings.keepalive_interval)
        form.addRow("Keepalive interval:", self.keepalive_spin)

        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(settings.font_family))
        form.addRow("Terminal font:", self.font_combo)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 48)
        self.font_size_spin.setValue(settings.font_size)
        form.addRow("Font size:", self.font_size_spin)

        self.scrollback_spin = QSpinBox()
        self.scrollback_spin.setRange(0, 100000)
        self.scrollback_spin.setValue(settings.scrollback_lines)
        form.addRow("Scrollback lines:", self.scrollback_spin)

        self.default_user_edit = QLineEdit(settings.default_user)
        form.addRow("Default username:", self.default_user_edit)

        self.show_sftp_checkbox = QCheckBox("Show SFTP panel for new connections")
        self.show_sftp_checkbox.setChecked(settings.show_sftp_panel)
        form.addRow(self.show_sftp_checkbox)

        self.editor_edit = QLineEdit(settings.editor_command)
        self.editor_edit.setPlaceholderText("(blank = open with the system default application)")
        editor_browse_btn = QPushButton("Browse...")
        editor_browse_btn.clicked.connect(self._browse_editor)
        editor_row = QHBoxLayout()
        editor_row.addWidget(self.editor_edit)
        editor_row.addWidget(editor_browse_btn)
        editor_widget = QWidget()
        editor_widget.setLayout(editor_row)
        form.addRow("SFTP file editor:", editor_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _browse_editor(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select editor executable")
        if path:
            self.editor_edit.setText(path)

    def _on_accept(self) -> None:
        s = self.settings
        s.theme = self.theme_combo.currentData()
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, s.theme)
        s.keepalive_enabled = self.keepalive_checkbox.isChecked()
        s.keepalive_interval = self.keepalive_spin.value()
        s.font_family = self.font_combo.currentFont().family()
        s.font_size = self.font_size_spin.value()
        s.scrollback_lines = self.scrollback_spin.value()
        s.default_user = self.default_user_edit.text().strip()
        s.show_sftp_panel = self.show_sftp_checkbox.isChecked()
        s.editor_command = self.editor_edit.text().strip()
        s.sync()
        self.accept()
