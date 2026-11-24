"""M371 — W13 Casing strength › "Axial loads & wear…" dialog.

UI → ``core.casing_axial_loads`` (service and closed forms; ratings through ``CasingEngine``) → validation in the
service → ``core.calculation_cases`` (persistence; inputs SHA-256 as provenance) → Calculation History replay
(``core.history_replay`` adapter ``m371.casing_axial_loads``).

OD, ID, yield and axial tension are copied from the casing page when the dialog opens (a page value of 0 is NOT
ENTERED). Every other field is empty until the user declares it: there are no steel defaults for Young's modulus,
the expansion coefficient or Poisson's ratio, and an empty field is never read as 0.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from core import casing_axial_loads as cal

LABELS = {
    "od_in": "OD (in)", "id_in": "ID (in)", "yield_psi": "Yield strength (psi)",
    "base_axial_load_lbf": "Base axial load, tension + (lbf)", "youngs_modulus_psi": "Young's modulus (psi)",
    "dls_deg_per_100ft": "Dogleg severity (deg/100 ft)", "expansion_per_degf": "Expansion coefficient (1/degF)",
    "delta_temperature_degf": "Temperature change after landing (degF)", "poisson_ratio": "Poisson's ratio",
    "delta_internal_psi": "Internal pressure change (psi)", "delta_external_psi": "External pressure change (psi)",
    "wear_percent": "Wall wear (%)",
}


class CasingAxialLoadsDialog(QDialog):
    def __init__(self, page_values: Dict[str, Any], *, db=None, well_id: Optional[int] = None, user_id=None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Casing — axial-load components and wear (SCREENING)")
        self.resize(640, 640)
        self.db, self.well_id, self.user_id = db, well_id, user_id
        self.result: Optional[Dict[str, Any]] = None
        self.saved_case: Optional[Dict[str, Any]] = None
        lay = QVBoxLayout(self)
        banner = QLabel(f"{cal.LABEL}. OD, ID, yield and axial tension come from the casing page; every other "
                        "value must be declared (no defaults). Empty = NOT ENTERED.")
        banner.setWordWrap(True)
        lay.addWidget(banner)
        form = QFormLayout()
        self.edits: Dict[str, QLineEdit] = {}
        for key, unit, _required in cal.FIELDS:
            edit = QLineEdit()
            edit.setObjectName(f"m371_{key}")
            value = page_values.get(key)
            if value is not None:
                edit.setText(f"{value:g}")
            edit.setPlaceholderText(f"{unit or 'dimensionless'}; empty = not entered")
            self.edits[key] = edit
            form.addRow(LABELS[key] + ":", edit)
        lay.addLayout(form)
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
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary, 1)

    def values(self) -> Dict[str, Any]:
        return {key: edit.text().strip() or None for key, edit in self.edits.items()}

    def run(self) -> Optional[Dict[str, Any]]:
        self.save_btn.setEnabled(False)
        self.result = None
        try:
            result = cal.evaluate(self.values())
        except cal.AxialLoadError as exc:
            self.summary.setText(f"Not run: {exc}")
            return None
        self.result = result
        self.summary.setText("\n".join(cal.summary_lines(result)))
        self.save_btn.setEnabled(result["status"] == cal.COMPUTED and self.db is not None)
        return result

    def save(self) -> Optional[Dict[str, Any]]:
        from core.authorization import AuthorizationError

        if self.result is None or self.db is None:
            return None
        try:
            case = cal.save_case(self.db, self.result, well_id=self.well_id, user_id=self.user_id)
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
