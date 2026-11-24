"""M368 — W6 Trajectory › 3D view › "Plan vs actual…" dialog.

UI → ``core.survey_plan_deviation`` (service: record and frame checks, frozen snapshot) →
``core.well_plan_designer.closest_on_path`` (engine: continuous minimum-curvature path) → ``core.calculation_cases``
(persistence, SHA-256 of the frozen snapshot as provenance) → Calculation History replay (``core.history_replay``
adapter ``m368.survey_plan_deviation``).

The survey revision and the plan revision are the ones chosen in the 3D layer panel when the dialog opens. The
tolerance is optional free text: empty means NOT DECLARED (no WITHIN / OUTSIDE judgement), never a default.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

from PySide6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout)

from core import survey_plan_deviation as spd


def _cell(value: Any, digits: int = 2) -> QTableWidgetItem:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return QTableWidgetItem(f"{value:.{digits}f}")
    return QTableWidgetItem("—" if value in (None, "") else str(value))


class SurveyPlanDeviationDialog(QDialog):
    STATION_COLUMNS = ("MD m", "Plan MD m", "Distance m", "High (+) m", "Right (+) m", "ΔTVD m", "Status", "Note")
    TARGET_COLUMNS = ("Target", "Status", "Centreline miss m", "Radius m", "Closest MD m", "Reason")

    def __init__(self, db, survey_id: int, plan_id: int, *, well_id: Optional[int] = None, user_id=None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plan vs actual survey — centreline deviation (SCREENING)")
        self.resize(940, 600)
        self.db, self.survey_id, self.plan_id = db, survey_id, plan_id
        self.well_id, self.user_id = well_id, user_id
        self.result: Optional[Dict[str, Any]] = None
        self.saved_case: Optional[Dict[str, Any]] = None

        lay = QVBoxLayout(self)
        banner = QLabel(f"{spd.LABEL}. Survey revision record #{survey_id} vs plan revision record #{plan_id}. "
                        "Lengths in metres.")
        banner.setWordWrap(True)
        lay.addWidget(banner)
        form = QFormLayout()
        self.tolerance_edit = QLineEdit()
        self.tolerance_edit.setPlaceholderText("declared tolerance, m (optional; no default)")
        form.addRow("Tolerance:", self.tolerance_edit)
        lay.addLayout(form)
        buttons = QHBoxLayout()
        self.run_btn = QPushButton("Compare")
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
        self.station_table = QTableWidget(0, len(self.STATION_COLUMNS))
        self.station_table.setHorizontalHeaderLabels(list(self.STATION_COLUMNS))
        self.target_table = QTableWidget(0, len(self.TARGET_COLUMNS))
        self.target_table.setHorizontalHeaderLabels(list(self.TARGET_COLUMNS))
        self.tabs.addTab(self.station_table, "Stations")
        self.tabs.addTab(self.target_table, "Targets")
        lay.addWidget(self.tabs, 1)

    def _tolerance(self) -> Optional[float]:
        text = self.tolerance_edit.text().strip()
        if not text:
            return None
        try:
            value = float(text)
        except ValueError as exc:
            raise spd.DeviationError(f"tolerance {text!r} is not a number") from exc
        if not math.isfinite(value) or value <= 0:
            raise spd.DeviationError("the tolerance must be a positive number of metres")
        return value

    def run(self) -> Optional[Dict[str, Any]]:
        self.save_btn.setEnabled(False)
        self.result = None
        self.station_table.setRowCount(0)
        self.target_table.setRowCount(0)
        try:
            tolerance = self._tolerance()
        except spd.DeviationError as exc:
            self.summary.setText(f"Not run: {exc}")
            return None
        result = spd.run(self.db, self.survey_id, self.plan_id, tolerance_m=tolerance)
        self.result = result
        self.summary.setText("\n".join(spd.summary_lines(result)))
        if result["status"] != spd.COMPUTED:
            return result
        self.station_table.setRowCount(len(result["rows"]))
        for i, row in enumerate(result["rows"]):
            values = (row["md"], row["plan_md"], row["distance_m"], row["high_m"], row["right_m"],
                      row["tvd_difference_m"], row["status"], row["position_note"] or row["frame_note"])
            for j, value in enumerate(values):
                self.station_table.setItem(i, j, _cell(value, 1 if j < 2 else 2))
        self.target_table.setRowCount(len(result["targets"]))
        for i, t in enumerate(result["targets"]):
            for j, value in enumerate((t["name"], t["status"], t["distance_m"], t["radius_m"], t["closest_md"],
                                       t["reason"])):
                self.target_table.setItem(i, j, _cell(value))
        self.save_btn.setEnabled(self.db is not None)
        return result

    def save(self) -> Optional[Dict[str, Any]]:
        from core.authorization import AuthorizationError

        if self.result is None or self.db is None:
            return None
        try:
            case = spd.save_case(self.db, self.result, well_id=self.well_id, user_id=self.user_id)
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
