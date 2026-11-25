"""M373 — W13 Well control › "Volumetric method (TRAINING AID)…" dialog (P11).

UI → ``core.well_control_volumetric`` (service, validation) → ``core.calculation_cases`` (persistence; inputs
SHA-256 as provenance) → Calculation History replay (``core.history_replay`` adapter ``m373.volumetric_method``).

SICP and the mud density (pcf, as on the page) are copied from the kill-sheet page when they are not 0. Everything
else is empty until declared: the annular capacity at the bubble is not inferred from the string table, and the
safety margin / working range have no defaults. TRAINING AID - NOT FOR OPERATIONAL WELL CONTROL.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from core import well_control_volumetric as wcv

LABELS = {
    "sicp_psi": "SICP (psi)", "mud_density_pcf": "Mud density in the annulus (pcf)",
    "annular_capacity_bbl_ft": "Annular capacity at the bubble (bbl/ft)", "safety_margin_psi": "Safety margin Ps (psi)",
    "working_range_psi": "Working range Pw (psi)", "cycles": "Cycles to tabulate",
    "casing_limit_psi": "Casing-pressure limit, e.g. MAASP (psi, optional)",
    "pressure_rise_psi": "Observed shut-in pressure rise (psi, optional)",
    "rise_duration_h": "Over a duration of (h, optional)",
}


class VolumetricMethodDialog(QDialog):
    def __init__(self, page_values: Dict[str, Any], *, db=None, well_id: Optional[int] = None, user_id=None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Volumetric method — TRAINING AID (not for operational well control)")
        self.resize(640, 640)
        self.db, self.well_id, self.user_id = db, well_id, user_id
        self.result: Optional[Dict[str, Any]] = None
        self.saved_case: Optional[Dict[str, Any]] = None
        lay = QVBoxLayout(self)
        banner = QLabel(f"{wcv.LABEL}. SICP and mud density come from the kill-sheet page; every other value must be "
                        "declared (no defaults). Empty = NOT ENTERED.")
        banner.setWordWrap(True)
        banner.setStyleSheet("font-weight: bold; color: #c0392b;")
        lay.addWidget(banner)
        form = QFormLayout()
        self.edits: Dict[str, QLineEdit] = {}
        for key, unit, _required in wcv.FIELDS:
            edit = QLineEdit()
            edit.setObjectName(f"m373_{key}")
            value = page_values.get(key)
            if value is not None:
                edit.setText(f"{value:g}")
            edit.setPlaceholderText(f"{unit or 'count'}; empty = not entered")
            self.edits[key] = edit
            form.addRow(LABELS[key] + ":", edit)
        lay.addLayout(form)
        buttons = QHBoxLayout()
        self.run_btn = QPushButton("Build worksheet")
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

    def values(self) -> Dict[str, Any]:
        return {key: edit.text().strip() or None for key, edit in self.edits.items()}

    def run(self) -> Optional[Dict[str, Any]]:
        self.save_btn.setEnabled(False)
        self.result = None
        try:
            result = wcv.evaluate(self.values())
        except wcv.VolumetricError as exc:
            self.summary.setText(f"Not run: {exc}")
            return None
        self.result = result
        self.summary.setText("\n".join(wcv.summary_lines(result)))
        self.save_btn.setEnabled(result["status"] == wcv.COMPUTED and self.db is not None)
        return result

    def save(self) -> Optional[Dict[str, Any]]:
        from core.authorization import AuthorizationError

        if self.result is None or self.db is None:
            return None
        try:
            case = wcv.save_case(self.db, self.result, well_id=self.well_id, user_id=self.user_id)
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
