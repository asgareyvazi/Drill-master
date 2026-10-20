"""Backup/restore UI on top of core.db_maintenance (M43).

The services enforce permission, validation and recovery; this module only
selects a candidate, states the consequences, collects an explicit
confirmation and runs the operation off the GUI thread.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QHeaderView, QLabel,
    QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from core.db_maintenance import KIND_SAFETY

logger = logging.getLogger(__name__)

WARNING_TEXT = (
    "Restoring replaces ALL current data with the selected backup.\n"
    "• Changes made after that backup will no longer be in the active database.\n"
    "• A verified pre-restore copy of the current database is created first and kept; "
    "it can be restored later from this list.\n"
    "• Unsaved edits in open screens are discarded. Save your work before continuing.\n"
    "• Other users or DrillMaster windows must close the database first.\n"
    "• After a successful restore DrillMaster closes and must be started again."
)


class MaintenanceWorker(QThread):
    """Runs one service call off the GUI thread; read ``result``/``error`` on finished."""

    def __init__(self, call, parent=None):
        super().__init__(parent)
        self._call = call
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self._call()
        except Exception as exc:
            # The traceback goes to the log ("see the log" in the message box);
            # the GUI slot reports the failure to the user.
            logger.exception("Database maintenance call failed")
            self.error = exc


def _size_text(size) -> str:
    if isinstance(size, bool) or not isinstance(size, (int, float)) or size < 0:
        return "?"
    size = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return "?"


class RestoreDatabaseDialog(QDialog):
    """Choose a verified managed backup and confirm the consequences."""

    COLUMNS = ("Created (UTC)", "Type", "Schema", "Size", "App version", "SHA-256")

    def __init__(self, candidates, current_schema: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Restore Database")
        self.setModal(True)
        self.resize(820, 460)
        self._candidates = list(candidates)
        self._current_schema = int(current_schema)

        layout = QVBoxLayout(self)
        intro = QLabel("Verified backups in the backup folder (newest first). "
                       "Only files created by DrillMaster with a matching manifest are listed.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QTableWidget(0, len(self.COLUMNS), self)
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self._fill()
        layout.addWidget(self.table)

        self.note = QLabel("")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

        warning = QLabel(WARNING_TEXT)
        warning.setWordWrap(True)
        warning.setStyleSheet("QLabel { color: #8a1c1c; font-weight: bold; }")
        layout.addWidget(warning)

        self.confirm = QCheckBox("I understand that the current data will be replaced.")
        layout.addWidget(self.confirm)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel, self)
        self.restore_button = self.buttons.addButton("Restore…", QDialogButtonBox.AcceptRole)
        self.restore_button.setEnabled(False)
        self.buttons.accepted.connect(self._confirm_and_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.table.itemSelectionChanged.connect(self._update_state)
        self.confirm.toggled.connect(self._update_state)
        self._update_state()

    def _fill(self):
        for path, manifest in self._candidates:
            row = self.table.rowCount()
            self.table.insertRow(row)
            schema = manifest.get("schema_version")
            values = (
                str(manifest.get("created_utc", "?")).replace("T", " ").replace("+00:00", ""),
                "Pre-restore copy" if manifest.get("kind") == KIND_SAFETY else "Backup",
                str(schema),
                _size_text(manifest.get("size")),
                str(manifest.get("app_version") or "?"),
                str(manifest.get("sha256", ""))[:12],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(path.name)
                if not self._restorable(schema):
                    item.setFlags(item.flags() & ~Qt.ItemIsSelectable & ~Qt.ItemIsEnabled)
                    item.setToolTip("Created by a newer DrillMaster version - cannot be restored")
                self.table.setItem(row, column, item)

    def _restorable(self, schema) -> bool:
        return isinstance(schema, int) and schema <= self._current_schema

    def selected_candidate(self):
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        path, manifest = self._candidates[rows[0].row()]
        return (path, manifest) if self._restorable(manifest.get("schema_version")) else None

    def _update_state(self):
        candidate = self.selected_candidate()
        if candidate is None:
            self.note.setText("Select a backup to restore." if self._candidates
                              else "No verified backups were found in the backup folder.")
        elif candidate[1].get("schema_version") < self._current_schema:
            self.note.setText("This backup uses an older database format. A copy of it will be "
                              "upgraded and verified before it replaces the current database; "
                              "the backup file itself is not modified.")
        else:
            self.note.setText(f"Selected: {candidate[0].name}")
        self.restore_button.setEnabled(candidate is not None and self.confirm.isChecked())

    def _confirm_and_accept(self):
        candidate = self.selected_candidate()
        if candidate is None or not self.confirm.isChecked():
            return
        answer = QMessageBox.warning(
            self, "Confirm Restore",
            f"Replace the current database with the backup from "
            f"{candidate[1].get('created_utc', '?')} (UTC)?\n\nThis cannot be undone except by "
            f"restoring the pre-restore copy.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self.accept()
