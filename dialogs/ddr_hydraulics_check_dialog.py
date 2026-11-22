"""M314 (M277): recorded vs recomputed bit hydraulics of one daily report (SCREENING).

Shows every input with its source row and status (RECORDED / DERIVED / MISSING), the recomputed bit hydraulics
at the recorded minimum and maximum pump output, and the HSI and TFA checks with their reasons. It never edits
the report. "Save as calculation case" stores an immutable case linked to the drilling-parameter row (visible
in Calculation history); it is enabled only when something was computed.

Entry point: W2 Daily Report, "💧 Hydraulics check…" (the open, saved report).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from core import ddr_hydraulics_check as hc

RESULT_KEYS = (("bit_pressure_drop_psi", "Bit ΔP", "psi"), ("bit_hhp", "Bit HHP", "hp"), ("hsi", "HSI", "hp/in²"),
               ("jet_velocity_fps", "Jet velocity", "ft/s"), ("impact_force_lbs", "Impact force", "lbf"))


def _text(value: Any) -> str:
    if value is None:
        return "—"                       # missing stays visibly missing, never 0
    return f"{value:.4g}" if isinstance(value, float) else str(value)


def _table(name, headers, rows) -> QTableWidget:
    table = QTableWidget(len(rows), len(headers))
    table.setObjectName(name)
    table.setHorizontalHeaderLabels(list(headers))
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.horizontalHeader().setStretchLastSection(True)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem(_text(value))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            table.setItem(r, c, item)
    return table


class DdrHydraulicsCheckDialog(QDialog):
    def __init__(self, db, report_id: int, parent=None, *, user_id: Optional[int] = None):
        super().__init__(parent)
        self.db, self.report_id, self.user_id = db, report_id, user_id
        self.saved_case: Optional[Dict[str, Any]] = None
        self.setObjectName("ddr_hydraulics_check_dialog")
        self.setWindowTitle(f"Hydraulics check – report #{report_id}")
        self.resize(900, 600)
        self.result = hc.check(db, report_id)
        layout = QVBoxLayout(self)
        scope = QLabel(f"<b>{hc.SCOPE}</b><br>{hc.METHOD_VERSION}")
        scope.setObjectName("hydraulics_scope")
        layout.addWidget(scope)
        inputs = self.result["inputs"]
        self.inputs_table = _table("hydraulics_inputs", ("Input", "Value", "Unit", "Status", "Source", "Note"),
                                   [(k, e["value"], e["unit"], e["status"], e["source"], e["note"])
                                    for k, e in inputs.items()])
        layout.addWidget(self.inputs_table)
        columns = list(self.result["computed"])
        self.results_table = _table("hydraulics_results", ["Result", "Unit"] + [f"at {c} pump output" for c in columns],
                                    [(label, unit, *[self.result["computed"][c][key] for c in columns])
                                     for key, label, unit in RESULT_KEYS])
        layout.addWidget(self.results_table)
        self.status = QLabel("<br>".join(hc.summary_lines(self.result)[1:]))
        self.status.setObjectName("hydraulics_status")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.save_button = QPushButton("Save as calculation case")
        self.save_button.setObjectName("hydraulics_save_case")
        self.save_button.setEnabled(self.result["status"] == "COMPUTED")
        self.save_button.clicked.connect(self.save_case)
        buttons.addButton(self.save_button, QDialogButtonBox.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save_case(self, _checked: bool = False):
        self.saved_case = hc.save_check(self.db, self.result, user_id=self.user_id)
        self.save_button.setEnabled(False)                    # one case per check; a new check is a new case
        self.status.setText(self.status.text() + f"<br>Saved as calculation case #{self.saved_case['id']}.")
        return self.saved_case
