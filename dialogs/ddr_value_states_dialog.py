"""M272: the value states of the numeric header fields of one daily report (``core.ddr_value_states``).

The table shows each field's stored value and its state (recorded, or implicit when nothing was recorded). The
operator chooses a state (and, for CALCULATED, the method) and saves. A state that contradicts the stored value
is refused with the reason; the value itself is never changed here.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from core import ddr_value_states as vs

COLUMNS = ["Field", "Stored value", "State", "Method (CALCULATED)", "Recorded"]


class DdrValueStatesDialog(QDialog):
    def __init__(self, db, report_id: int, parent=None, *, user_id: Optional[int] = None):
        super().__init__(parent)
        self.db, self.report_id, self.user_id = db, report_id, user_id
        self.setWindowTitle("Value states of this report")
        self.resize(820, 420)
        layout = QVBoxLayout(self)
        note = QLabel("Say what an empty or zero field means: unknown, not applicable, not reported, a real zero, "
                      "or a calculated value (method required). Values are not changed here; carry-forward stays "
                      "under Day states….")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, len(COLUMNS), self)
        self.table.setObjectName("ddr_value_states_table")
        self.table.setHorizontalHeaderLabels(COLUMNS)
        layout.addWidget(self.table)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.save_button = QPushButton("Save states")
        self.save_button.setObjectName("ddr_value_states_save")
        self.save_button.clicked.connect(self.save)
        buttons.addButton(self.save_button, QDialogButtonBox.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.fields: List[str] = []
        self.shown: Dict[str, Dict] = {}
        self.refresh()

    def refresh(self) -> None:
        self.shown = vs.states(self.db, self.report_id)
        self.fields = list(self.shown)
        self.table.setRowCount(len(self.fields))
        for row, field in enumerate(self.fields):
            entry = self.shown[field]
            self.table.setItem(row, 0, QTableWidgetItem(entry["label"]))
            self.table.setItem(row, 1, QTableWidgetItem("—" if entry["value"] is None else f"{entry['value']:g}"))
            combo = QComboBox()
            for state in vs.STATES:
                combo.addItem(state, state)
            current = entry.get("recorded_state", entry["state"])
            combo.setCurrentIndex(vs.STATES.index(current))
            self.table.setCellWidget(row, 2, combo)
            method = QLineEdit(entry["method"] or "")
            self.table.setCellWidget(row, 3, method)
            recorded = ("INCONSISTENT: " + entry["reason"]) if not entry["consistent"] else \
                ("yes" if entry["recorded"] else "implicit")
            self.table.setItem(row, 4, QTableWidgetItem(recorded))

    def set_state(self, field: str, state: str, method: str = "") -> None:
        row = self.fields.index(field)
        combo = self.table.cellWidget(row, 2)
        combo.setCurrentIndex(vs.STATES.index(state))
        self.table.cellWidget(row, 3).setText(method)

    def pending(self) -> List[tuple]:
        """(field, state, method) for every row whose choice differs from what is recorded or implicit."""
        out = []
        for row, field in enumerate(self.fields):
            entry = self.shown[field]
            state = self.table.cellWidget(row, 2).currentData()
            method = self.table.cellWidget(row, 3).text().strip()
            before = entry.get("recorded_state", entry["state"])
            if state != before or (state == vs.CALCULATED and method != (entry["method"] or "")):
                out.append((field, state, method))
        return out

    def save(self) -> Dict[str, List]:
        saved, refused = [], []
        for field, state, method in self.pending():
            try:
                vs.record(self.db, self.report_id, field, state, method=method, user_id=self.user_id)
                saved.append(field)
            except vs.ValueStateError as exc:
                refused.append((field, str(exc)))
        self.refresh()
        message = f"Saved {len(saved)} state(s)."
        if refused:
            message += " Refused: " + "; ".join(reason for _field, reason in refused)
        self.status.setText(message)
        return {"saved": saved, "refused": refused}
