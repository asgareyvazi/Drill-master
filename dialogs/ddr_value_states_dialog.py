"""M272: the value states of the numeric header fields of one daily report (``core.ddr_value_states``).

The table shows each field's stored value and its state (recorded, or implicit when nothing was recorded). The
operator chooses a state (and, for CALCULATED, the method) and saves. A state that contradicts the stored value
is refused with the reason; a state choice never changes the value.

M295: the "Typed entry" column takes the value as written on the paper report ("12.5", "0", "N/A", "?", "NR").
It is saved through ``ddr_value_states.record_authored``: value and state are written together, and a comma, NaN,
infinity or other text is refused with the reason and nothing is written. A blank cell means "no entry", not
NOT_REPORTED (type NR for that). When the W2 form holds unsaved edits, the column is read-only, so a typed value
can never be overwritten by the form's stale inputs; the caller reloads the form after a typed value is saved
(``values_changed``).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from core import ddr_value_states as vs

COLUMNS = ["Field", "Stored value", "State", "Method (CALCULATED)", "Recorded", "Typed entry (as written)"]
TYPED_COLUMN = 5


class DdrValueStatesDialog(QDialog):
    def __init__(self, db, report_id: int, parent=None, *, user_id: Optional[int] = None,
                 allow_typed_values: bool = True):
        super().__init__(parent)
        self.db, self.report_id, self.user_id = db, report_id, user_id
        self.allow_typed_values = allow_typed_values
        self.values_changed = False
        self.setWindowTitle("Value states of this report")
        self.resize(820, 420)
        layout = QVBoxLayout(self)
        note = QLabel("Say what an empty or zero field means: unknown, not applicable, not reported, a real zero, "
                      "or a calculated value (method required). Values are not changed here; carry-forward stays "
                      "under Day states…. Type a value as written on the report (12.5, 0, N/A, ?, NR) to set the value "
                      "and its state together; commas are refused (type 1500 or 1.5).")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, len(COLUMNS), self)
        self.table.setObjectName("ddr_value_states_table")
        self.table.setHorizontalHeaderLabels(COLUMNS)
        layout.addWidget(self.table)
        if not allow_typed_values:
            locked = QLabel("Typed entries are disabled: the report form has unsaved edits. Save the report first.")
            locked.setObjectName("ddr_value_states_typed_locked")
            locked.setWordWrap(True)
            layout.addWidget(locked)
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
            typed = QLineEdit("")
            typed.setPlaceholderText("no entry")
            typed.setReadOnly(not self.allow_typed_values)
            self.table.setCellWidget(row, TYPED_COLUMN, typed)

    def set_state(self, field: str, state: str, method: str = "") -> None:
        row = self.fields.index(field)
        combo = self.table.cellWidget(row, 2)
        combo.setCurrentIndex(vs.STATES.index(state))
        self.table.cellWidget(row, 3).setText(method)

    def set_typed(self, field: str, text: str) -> None:
        self.table.cellWidget(self.fields.index(field), TYPED_COLUMN).setText(text)

    def typed_pending(self) -> List[tuple]:
        """(field, typed text, calculated method) for every row with a typed entry (typed values enabled only)."""
        if not self.allow_typed_values:
            return []
        out = []
        for row, field in enumerate(self.fields):
            typed = self.table.cellWidget(row, TYPED_COLUMN).text()
            if typed.strip():
                calculated = self.table.cellWidget(row, 2).currentData() == vs.CALCULATED
                out.append((field, typed, self.table.cellWidget(row, 3).text().strip() if calculated else ""))
        return out

    def pending(self) -> List[tuple]:
        """(field, state, method) for every row whose choice differs from what is recorded or implicit."""
        out = []
        typed = {field for field, _text, _method in self.typed_pending()}
        for row, field in enumerate(self.fields):
            if field in typed:
                continue                                   # the typed entry sets value and state together
            entry = self.shown[field]
            state = self.table.cellWidget(row, 2).currentData()
            method = self.table.cellWidget(row, 3).text().strip()
            before = entry.get("recorded_state", entry["state"])
            if state != before or (state == vs.CALCULATED and method != (entry["method"] or "")):
                out.append((field, state, method))
        return out

    def save(self) -> Dict[str, List]:
        saved, refused = [], []
        for field, typed, method in self.typed_pending():
            try:
                vs.record_authored(self.db, self.report_id, field, typed, calculated_method=method,
                                   user_id=self.user_id)
                saved.append(field)
                self.values_changed = True
            except vs.ValueStateError as exc:
                refused.append((field, str(exc)))
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
        return {"saved": saved, "refused": refused, "values_changed": self.values_changed}
