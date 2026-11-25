"""M372 — W13 Bit hydraulics & MSE › "Drill-off test (founder)…" dialog.

UI → ``core.mse_drilloff`` (service; per-step MSE through ``MSEEngine``) → validation in the service →
``core.calculation_cases`` (persistence; inputs SHA-256 as provenance) → Calculation History replay
(``core.history_replay`` adapter ``m372.mse_drilloff``).

The bit size is copied from the W13 page when it is not 0; the current page WOB / RPM / torque / ROP, when all are
entered, become the first step. Every other cell is empty until typed: an empty cell is NOT ENTERED, never 0. The
slope fraction and RPM tolerance are shown with a visible starting value and are stored with the case.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from core import mse_drilloff as mdo

LABELS = {"bit_diameter_in": "Bit diameter (in)", "founder_slope_fraction": "Founder slope fraction (0-1)",
          "rpm_tolerance_rpm": "RPM tolerance between steps (rpm)", "ccs_psi": "Rock CCS (psi, optional)"}
#: visible starting values for the two method parameters (shown, editable, stored with the case)
METHOD_START = {"founder_slope_fraction": "0.5", "rpm_tolerance_rpm": "5"}
ROWS = 8


class MseDrillOffDialog(QDialog):
    def __init__(self, page_values: Dict[str, Any], *, db=None, well_id: Optional[int] = None, user_id=None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Drill-off test — founder point and MSE (SCREENING)")
        self.resize(720, 680)
        self.db, self.well_id, self.user_id = db, well_id, user_id
        self.result: Optional[Dict[str, Any]] = None
        self.saved_case: Optional[Dict[str, Any]] = None
        lay = QVBoxLayout(self)
        banner = QLabel(f"{mdo.LABEL}. Hold RPM constant, step WOB up, record stabilised ROP and torque per step. "
                        "Empty = NOT ENTERED.")
        banner.setWordWrap(True)
        lay.addWidget(banner)
        form = QFormLayout()
        self.edits: Dict[str, QLineEdit] = {}
        for key, unit, _required in mdo.FIELDS:
            edit = QLineEdit()
            edit.setObjectName(f"m372_{key}")
            value = page_values.get(key)
            if value is not None:
                edit.setText(f"{value:g}")
            elif key in METHOD_START:
                edit.setText(METHOD_START[key])
            edit.setPlaceholderText(f"{unit or 'dimensionless'}; empty = not entered")
            self.edits[key] = edit
            form.addRow(LABELS[key] + ":", edit)
        lay.addLayout(form)
        self.table = QTableWidget(ROWS, len(mdo.STEP_FIELDS))
        self.table.setObjectName("m372_steps")
        self.table.setHorizontalHeaderLabels([f"{key.split('_')[0].upper()} ({unit})"
                                              for key, unit in mdo.STEP_FIELDS])
        first = page_values.get("first_step") or {}
        if first and all(first.get(key) is not None for key, _unit in mdo.STEP_FIELDS):
            self.set_step(0, first)
        lay.addWidget(self.table)
        buttons = QHBoxLayout()
        self.run_btn = QPushButton("Evaluate")
        self.run_btn.clicked.connect(self._run_clicked)
        self.save_btn = QPushButton("Save as calculation case")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save_clicked)
        buttons.addWidget(self.run_btn)
        buttons.addWidget(self.save_btn)
        buttons.addStretch()
        lay.addLayout(buttons)
        self.summary = QLabel("Not run.")
        self.summary.setTextFormat(Qt.PlainText)     # M491: echoes typed text (error reasons), never rich text
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary, 1)

    def set_step(self, row: int, step: Dict[str, Any]) -> None:
        for col, (key, _unit) in enumerate(mdo.STEP_FIELDS):
            value = step.get(key)
            self.table.setItem(row, col, QTableWidgetItem("" if value is None else f"{value:g}"))

    def values(self) -> Dict[str, Any]:
        return {key: edit.text().strip() or None for key, edit in self.edits.items()}

    def steps(self) -> List[Dict[str, Any]]:
        rows = []
        for row in range(self.table.rowCount()):
            cells = {}
            for col, (key, _unit) in enumerate(mdo.STEP_FIELDS):
                item = self.table.item(row, col)
                cells[key] = (item.text().strip() if item is not None else "") or None
            rows.append(cells)
        return rows

    def run(self) -> Optional[Dict[str, Any]]:
        self.save_btn.setEnabled(False)
        self.result = None
        try:
            result = mdo.evaluate(self.values(), self.steps())
        except mdo.DrillOffError as exc:
            self.summary.setText(f"Not run: {exc}")
            return None
        self.result = result
        self.summary.setText("\n".join(mdo.summary_lines(result)))
        self.save_btn.setEnabled(result["status"] == mdo.COMPUTED and self.db is not None)
        return result

    def save(self) -> Optional[Dict[str, Any]]:
        from core.authorization import AuthorizationError

        if self.result is None or self.db is None:
            return None
        try:
            case = mdo.save_case(self.db, self.result, well_id=self.well_id, user_id=self.user_id)
        except (ValueError, AuthorizationError) as exc:
            self.summary.setText(self.summary.text() + f"\nNot saved: {exc}")
            return None
        self.saved_case = case
        self.save_btn.setEnabled(False)
        self.summary.setText(self.summary.text() + f"\nSaved as calculation case #{case['id']} "
                             "(replayable from Calculation History).")
        return case

    def _run_clicked(self, _checked=False):
        self.run()

    def _save_clicked(self, _checked=False):
        self.save()
