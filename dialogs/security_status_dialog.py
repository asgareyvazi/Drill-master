"""M136: Tools › Security status — what this build protects in this session, and what it does not."""
from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout

from core import security_posture as sp

COLOURS = {sp.PROVIDED: "#1e7d32", sp.PARTIAL: "#b26a00", sp.OFF: "#5d6d7e", sp.NOT_PROVIDED: "#b00020"}
COLUMNS = ("Area", "Status", "Detail")


class SecurityStatusDialog(QDialog):
    def __init__(self, db, parent=None, environ=None):
        super().__init__(parent)
        self.setWindowTitle("Security status")
        self.resize(900, 420)
        layout = QVBoxLayout(self)
        note = QLabel(f"{sp.POSTURE_VERSION} — read from this session; not a certification or an approval.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.rows = sp.posture(db, environ)
        self.table = QTableWidget(len(self.rows), len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setWordWrap(True)
        for i, row in enumerate(self.rows):
            for j, value in enumerate(row):
                item = QTableWidgetItem(value)
                if j == 1:
                    item.setForeground(QColor(COLOURS.get(value, "#000000")))
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
