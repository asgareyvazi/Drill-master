"""Secure first-run bootstrap for a new desktop installation."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)


class BootstrapDialog(QDialog):
    """Collect production bootstrap passwords without persisting plaintext."""

    _ROLES = (
        ("admin", "Administrator password"),
        ("engineer", "Engineer password (optional)"),
        ("viewer", "Viewer password (optional)"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DrillMaster - Secure First Run")
        self.setMinimumWidth(560)
        self.setModal(True)
        self._passwords: dict[str, str] = {}
        self._fields: dict[str, tuple[QLineEdit, QLineEdit]] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        intro = QLabel(
            "This is the first run of DrillMaster. Create an administrator account. "
            "Engineer and viewer accounts are optional; leave both fields blank to omit them. Passwords are used only to create "
            "salted database hashes and are never written to the application "
            "directory or executable."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        for role, label in self._ROLES:
            password = QLineEdit()
            password.setEchoMode(QLineEdit.Password)
            password.setPlaceholderText("Use a unique password")
            confirm = QLineEdit()
            confirm.setEchoMode(QLineEdit.Password)
            confirm.setPlaceholderText("Repeat password")
            self._fields[role] = (password, confirm)
            form.addRow(label + ":", password)
            form.addRow("Confirm:", confirm)
        layout.addLayout(form)

        note = QLabel(
            "Use at least 12 characters for each password. After setup, "
            "manage users from the authenticated application."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            orientation=Qt.Horizontal,
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self) -> None:
        passwords: dict[str, str] = {}
        for role, label in self._ROLES:
            password, confirm = self._fields[role]
            value = password.text()
            if role != "admin" and not value and not confirm.text():
                continue
            from core.credential_policy import validate_production_password, CredentialLifecycleError
            try:
                validate_production_password(value)
            except CredentialLifecycleError as exc:
                QMessageBox.warning(self, "Incomplete setup", str(exc))
                password.setFocus()
                return
            if value != confirm.text():
                QMessageBox.warning(self, "Incomplete setup", f"{label} entries do not match.")
                confirm.clear()
                confirm.setFocus()
                return
            passwords[role] = value
        self._passwords = passwords
        self.accept()

    def passwords(self) -> dict[str, str]:
        """Return passwords only to the caller during this process."""
        return dict(self._passwords)
