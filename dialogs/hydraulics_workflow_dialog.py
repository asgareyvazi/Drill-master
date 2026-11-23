"""M366 — W13 Hydraulics › "Budget & sensitivity…" dialog.

UI → ``core.hydraulics_workflow`` (service) → ``core.hydraulics_engine`` (engine) → validation in the engine →
``core.calculation_cases`` (persistence, SHA-256 of the frozen inputs as provenance) → Calculation History replay
(``core.history_replay`` adapter ``m366.hydraulics_workflow``).

The dialog freezes the page values when it opens; later edits on the page do not change what this dialog computes
or saves. Observed standpipe pressure and tolerance are optional free-text fields: empty means NOT ENTERED, never 0.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

from PySide6.QtWidgets import (QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout)

from core import hydraulics_workflow as hw


def _cell(value: Any, digits: int = 1) -> QTableWidgetItem:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return QTableWidgetItem(f"{value:.{digits}f}")
    return QTableWidgetItem("—" if value in (None, "") else str(value))


def _optional_number(text: str, label: str) -> Optional[float]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError as exc:
        raise hw.WorkflowError(f"{label} {text!r} is not a number") from exc
    if not math.isfinite(value):
        raise hw.WorkflowError(f"{label} must be finite")
    return value


class HydraulicsWorkflowDialog(QDialog):
    FLOW_COLUMNS = ("Flow gpm", "Status", "SPP psi", "Bit ΔP psi", "Annular psi", "ECD bit ppg", "HSI hp/in²",
                    "% bit HP", "Min AV ft/min", "Critical flow", "Pumps")
    NOZZLE_COLUMNS = ("Nozzles", "Status", "TFA in²", "Bit ΔP psi", "HSI hp/in²", "Jet ft/s", "Impact lbf",
                      "SPP psi", "% bit HP", "Pumps")

    def __init__(self, values: Dict[str, Any], *, db=None, well_id: Optional[int] = None, user_id=None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hydraulics — pressure budget & sensitivity (SCREENING)")
        self.resize(980, 640)
        self.values = hw.freeze(values)
        self.db, self.well_id, self.user_id = db, well_id, user_id
        self.result: Optional[Dict[str, Any]] = None
        self.saved_case: Optional[Dict[str, Any]] = None

        lay = QVBoxLayout(self)
        banner = QLabel(f"{hw.LABEL}. Inputs frozen from the Hydraulics page (SHA-256 "
                        f"{hw.values_sha256(self.values)[:16]}…). Empty optional fields are NOT ENTERED.")
        banner.setWordWrap(True)
        lay.addWidget(banner)

        box = QGroupBox("Declared options")
        form = QFormLayout(box)
        self.flow_edit = QLineEdit()
        self.flow_edit.setPlaceholderText("e.g. 350, 400, 450 (gpm)")
        self.nozzle_edit = QLineEdit()
        self.nozzle_edit.setPlaceholderText("e.g. 3x12; 3x13; 2x12+1x14 (quantity x size in 32nds)")
        self.observed_edit = QLineEdit()
        self.observed_edit.setPlaceholderText("observed standpipe pressure, psi (optional)")
        self.tolerance_edit = QLineEdit()
        self.tolerance_edit.setPlaceholderText("declared ± tolerance, psi (optional; no default)")
        form.addRow("Flow rates:", self.flow_edit)
        form.addRow("Nozzle sets:", self.nozzle_edit)
        form.addRow("Observed SPP:", self.observed_edit)
        form.addRow("Tolerance:", self.tolerance_edit)
        lay.addWidget(box)

        buttons = QHBoxLayout()
        self.run_btn = QPushButton("Run workflow")
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
        lay.addWidget(self.summary)

        self.tabs = QTabWidget()
        self.budget_table = QTableWidget(0, 3)
        self.budget_table.setHorizontalHeaderLabels(["Component", "Loss psi", "Share of SPP %"])
        self.pump_table = QTableWidget(0, 7)
        self.pump_table.setHorizontalHeaderLabels(["Pump", "Flow gpm", "Max psi (entered)", "Pressure",
                                                   "Required HHP", "Rated HP (entered)", "Horsepower"])
        self.flow_table = QTableWidget(0, len(self.FLOW_COLUMNS))
        self.flow_table.setHorizontalHeaderLabels(list(self.FLOW_COLUMNS))
        self.nozzle_table = QTableWidget(0, len(self.NOZZLE_COLUMNS))
        self.nozzle_table.setHorizontalHeaderLabels(list(self.NOZZLE_COLUMNS))
        self.tabs.addTab(self.budget_table, "Pressure budget")
        self.tabs.addTab(self.pump_table, "Pump limits")
        self.tabs.addTab(self.flow_table, "Flow sensitivity")
        self.tabs.addTab(self.nozzle_table, "Nozzle sensitivity")
        lay.addWidget(self.tabs, 1)

    # ---- actions ---------------------------------------------------------------------------------------
    def run(self) -> Optional[Dict[str, Any]]:
        self.save_btn.setEnabled(False)
        self.result = None
        for table in (self.budget_table, self.pump_table, self.flow_table, self.nozzle_table):
            table.setRowCount(0)
        try:
            rates = hw.parse_flow_rates(self.flow_edit.text())
            sets = hw.parse_nozzle_sets(self.nozzle_edit.text())
            observed = _optional_number(self.observed_edit.text(), "observed SPP")
            tolerance = _optional_number(self.tolerance_edit.text(), "tolerance")
            result = hw.evaluate(self.values, flow_rates=rates, nozzle_sets=sets, observed_spp_psi=observed,
                                 spp_tolerance_psi=tolerance)
        except hw.WorkflowError as exc:
            self.summary.setText(f"Not run: {exc}")
            return None
        self.result = result
        self.summary.setText("\n".join(hw.summary_lines(result)))
        if result["status"] == "COMPUTED":
            self._fill(result)
            self.save_btn.setEnabled(self.db is not None)
        return result

    def _fill(self, result: Dict[str, Any]) -> None:
        base = result["base"]
        rows = base["budget"]["rows"] + [{"label": "Predicted standpipe pressure (engine total)",
                                          "loss_psi": base["spp_psi"], "share_pct": 100.0}]
        self.budget_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate((row["label"], row["loss_psi"], row["share_pct"])):
                self.budget_table.setItem(r, c, _cell(value))
        self.pump_table.setRowCount(len(base["pumps"]))
        for r, pump in enumerate(base["pumps"]):
            for c, value in enumerate((pump["pump"], pump["flow_gpm"], pump["max_pressure_psi"],
                                       pump["pressure_status"], pump["required_hhp"], pump["rated_hp"],
                                       pump["hp_status"])):
                self.pump_table.setItem(r, c, _cell(value))
        self.flow_table.setRowCount(len(result["flow_sweep"]))
        for r, p in enumerate(result["flow_sweep"]):
            ok = p["status"] == "OK"
            cells = (p["flow_gpm"], p["status"] if ok else f"NOT ASSESSED: {p['reason']}",
                     p.get("spp_psi"), p.get("bit_loss_psi"), p.get("annular_loss_psi"), p.get("ecd_at_bit_ppg"),
                     p.get("hsi"), p.get("percent_bit_hp"), p.get("min_annular_velocity_ft_min"),
                     p.get("critical_flow_gpm"), p.get("pump_status"))
            for c, value in enumerate(cells):
                self.flow_table.setItem(r, c, _cell(value, 3 if c == 5 else 1))
        self.nozzle_table.setRowCount(len(result["nozzle_sweep"]))
        for r, p in enumerate(result["nozzle_sweep"]):
            ok = p["status"] == "OK"
            cells = (hw.nozzle_set_label(p["nozzles"] or []), p["status"] if ok else f"NOT ASSESSED: {p['reason']}",
                     p.get("tfa_in2"), p.get("bit_loss_psi"), p.get("hsi"), p.get("jet_velocity_fps"),
                     p.get("impact_force_lbf"), p.get("spp_psi"), p.get("percent_bit_hp"), p.get("pump_status"))
            for c, value in enumerate(cells):
                self.nozzle_table.setItem(r, c, _cell(value, 3 if c == 2 else 1))

    def save(self) -> Optional[Dict[str, Any]]:
        from core.authorization import AuthorizationError

        if self.result is None or self.db is None:
            return None
        try:
            case = hw.save_case(self.db, self.result, well_id=self.well_id, user_id=self.user_id)
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
