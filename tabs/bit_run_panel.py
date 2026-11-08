"""M130: Bit run workbench (W12 Analysis › Bit runs).

Runs come from the DDR drilling parameters of the selected well (or of the explicitly selected wellbore) through
``core.bit_runs``; every run is listed, incomplete runs with what is missing. The DDR rows of the selected run
are shown and open the report. The cost scenario has no default value: currency, bit cost, rig rate and trip
time must all be typed (empty = not entered). Only complete runs are costed and ranked, and only against runs
of the same bit size. A scenario is saved as an immutable case (History re-runs it); the tables export to CSV
with their provenance.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QDoubleValidator
from PySide6.QtWidgets import (QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from core import bit_runs as br
from core.authorization import AuthorizationError
from core.context_jobs import CANCELLED, ERROR, STALE, ContextJobRunner, check_cancel
from tabs.job_retry import REFRESH_HINT, retry_button, scope_row, show_retry

logger = logging.getLogger(__name__)

COMPARE_COLUMNS = ("Run", "Size (in)", "Footage (m)", "Hours", "ROP (m/h)", "Lifecycle", "Data", "Cost status",
                   "Cost per m", "Currency", "Lowest cost / m (same size)", "Highest ROP (same size)", "Reasons")
DETAIL_COLUMNS = ("Date", "Report", "Depth in (m)", "Depth out (m)", "Drilled (m)", "Hours on bottom", "Source")
INCOMPLETE_COLOUR = "#e67e22"


def _text(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def _number(edit: QLineEdit) -> Optional[float]:
    text = edit.text().strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:  # silent-ok: an unparseable entry is "not entered" and is named in the reasons
        return None


def _load_runs_job(db, params, cancel_event):
    """Worker side: plain ids in, frozen ``BitRun`` DTOs out."""
    check_cancel(cancel_event)
    return br.load_runs(db, params["well"], params["wellbore"])


class BitRunWorkbench(QWidget):
    def __init__(self, db=None, owner=None, parent=None):
        super().__init__(parent)
        self.db, self.owner = db, owner
        self.well_id: Optional[int] = None
        self.wellbore_id: Optional[int] = None
        self.runs: List[br.BitRun] = []
        self.outcomes: Dict[str, br.CostOutcome] = {}
        self.comparison: List[Dict[str, Any]] = []
        self.jobs = ContextJobRunner(None, "bit runs", refresh_hint=REFRESH_HINT, parent=self)       # M103 runner (M51: no GUI-thread SQL)
        self.jobs.result_ready.connect(self._show_runs)
        self.jobs.state_changed.connect(self._job_state)

        layout = QVBoxLayout(self)
        self.scope_label = QLabel("NOT ASSESSED: select a well")
        self.retry_btn = retry_button(self._retry)
        layout.addLayout(scope_row(self.scope_label, self.retry_btn))
        self.runs_table = QTableWidget(0, len(br.RUN_COLUMNS))
        self.runs_table.setHorizontalHeaderLabels(br.RUN_COLUMNS)
        self.runs_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.runs_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.runs_table.itemSelectionChanged.connect(self._show_details)
        layout.addWidget(self.runs_table)

        self.detail_table = QTableWidget(0, len(DETAIL_COLUMNS))
        self.detail_table.setHorizontalHeaderLabels(DETAIL_COLUMNS)
        self.detail_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.detail_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.detail_table.itemSelectionChanged.connect(self._update_actions)
        self.open_btn = QPushButton("Open DDR")
        self.open_btn.clicked.connect(self.open_selected_report)
        details = QGroupBox("DDR rows of the selected run")
        details_layout = QVBoxLayout(details)
        details_layout.addWidget(self.detail_table)
        details_layout.addWidget(self.open_btn)
        layout.addWidget(details)

        scenario = QGroupBox("Cost per metre — " + br.COST_LABEL)
        grid = QGridLayout(scenario)
        self.currency_edit = QLineEdit()
        self.currency_edit.setPlaceholderText("Not entered (3-letter code, e.g. USD)")
        self.currency_edit.setMaxLength(3)
        self.bit_cost_edit, self.rig_rate_edit, self.trip_edit = QLineEdit(), QLineEdit(), QLineEdit()
        for edit in (self.bit_cost_edit, self.rig_rate_edit, self.trip_edit):
            edit.setPlaceholderText("Not entered")
            edit.setValidator(QDoubleValidator(0.0, 1e12, 4, edit))
        for column, (label, edit) in enumerate((("Currency", self.currency_edit), ("Bit cost", self.bit_cost_edit),
                                                ("Rig rate per day", self.rig_rate_edit),
                                                ("Trip time (h)", self.trip_edit))):
            grid.addWidget(QLabel(label), 0, column)
            grid.addWidget(edit, 1, column)
        note = QLabel("All four values are typed by you in one currency; nothing is converted and nothing here is "
                      "recorded cost. Incomplete runs are never costed or ranked; runs are ranked only against runs "
                      "of the same bit size.")
        note.setWordWrap(True)
        grid.addWidget(note, 2, 0, 1, 4)
        layout.addWidget(scenario)

        buttons = QHBoxLayout()
        self.compare_btn = QPushButton("Compare runs")
        self.compare_btn.clicked.connect(self.compare)
        self.save_btn = QPushButton("Save scenario for the selected run")
        self.save_btn.clicked.connect(self.save_selected)
        self.export_btn = QPushButton("Export CSV…")
        self.export_btn.clicked.connect(self._export_dialog)
        for button in (self.compare_btn, self.save_btn, self.export_btn):
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.compare_table = QTableWidget(0, len(COMPARE_COLUMNS))
        self.compare_table.setHorizontalHeaderLabels(COMPARE_COLUMNS)
        self.compare_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.compare_table)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self._update_actions()

    # -- scope ------------------------------------------------------------------------------------------------
    def set_scope(self, well_id: Optional[int], wellbore_id: Optional[int] = None) -> None:
        if (well_id, wellbore_id) != (self.well_id, self.wellbore_id):
            self.outcomes, self.comparison = {}, []
            self.compare_table.setRowCount(0)
            self.status.setText("")
        self.well_id, self.wellbore_id = well_id, wellbore_id
        self.reload()

    def scope_text(self) -> str:
        if self.well_id is None:
            return "NOT ASSESSED: select a well"
        if self.wellbore_id:
            return f"Well #{self.well_id}, wellbore #{self.wellbore_id} only (DDRs of that wellbore)"
        return f"Well #{self.well_id}, whole well (all wellbores; legacy duplicate rows excluded)"

    def reload(self) -> Optional[int]:
        """Read the runs of the current scope in a background job (M103 runner: worker session on a file
        database, stale and superseded results rejected); returns the job id, None when nothing runs."""
        self.runs = []
        if self.well_id is None or self.db is None:
            self.jobs.invalidate()
            self.scope_label.setText(self.scope_text())
            self._fill_runs()
            return None
        self.scope_label.setText(self.scope_text() + " — loading bit runs…")
        self._fill_runs()
        self.jobs.db_manager = self.db
        return self.jobs.start(_load_runs_job, {"well": self.well_id, "wellbore": self.wellbore_id})

    def _retry(self, _checked: bool = False) -> Optional[int]:
        """M138: Retry re-reads the current scope (a failed, stale or cancelled read showed nothing)."""
        return self.reload()

    def wait(self, timeout_ms: int = 30000) -> bool:
        return self.jobs.wait(timeout_ms)

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        return self.jobs.shutdown(timeout_ms)

    def _job_state(self, state: str, message: str) -> None:
        show_retry(self.retry_btn, state)
        if state in (ERROR, STALE, CANCELLED):
            self.runs = []
            self._fill_runs()
            self.scope_label.setText(message)          # the runner's message names the state / error type

    def _show_runs(self, _job_id: int, result) -> None:
        self.runs = list(result or [])
        incomplete = sum(1 for run in self.runs if not run.complete)
        text = self.scope_text() + f" — {len(self.runs)} run(s), {incomplete} incomplete. {br.RUN_METHOD}."
        if not self.runs:
            text += " No DDR row records a bit number."
        self.scope_label.setText(text)
        self._fill_runs()

    def _fill_runs(self) -> None:
        self.runs_table.setRowCount(len(self.runs))
        for i, run in enumerate(self.runs):
            for j, value in enumerate(run.table_row()):
                item = QTableWidgetItem(_text(value))
                if not run.complete:
                    item.setForeground(QColor(INCOMPLETE_COLOUR))
                    item.setToolTip("INCOMPLETE: " + "; ".join(run.missing))
                self.runs_table.setItem(i, j, item)
        self.detail_table.setRowCount(0)
        self._update_actions()

    # -- DDR linkage -----------------------------------------------------------------------------------------
    def selected_run(self) -> Optional[br.BitRun]:
        rows = self.runs_table.selectionModel().selectedRows() if self.runs_table.selectionModel() else []
        if not rows or rows[0].row() >= len(self.runs):
            return None
        return self.runs[rows[0].row()]

    def _show_details(self) -> None:
        run = self.selected_run()
        details = list(run.details) if run else []
        self.detail_table.setRowCount(len(details))
        for i, d in enumerate(details):
            for j, value in enumerate((d["date"], d["report"], d["in"], d["out"], d["drilled"], d["hours"],
                                       f"drilling_parameters #{d['row']}")):
                self.detail_table.setItem(i, j, QTableWidgetItem(_text(value)))
        self._update_actions()

    def selected_report_id(self) -> Optional[int]:
        run = self.selected_run()
        rows = self.detail_table.selectionModel().selectedRows() if self.detail_table.selectionModel() else []
        if run is None or not rows or rows[0].row() >= len(run.details):
            return None
        return run.details[rows[0].row()]["report"]

    def open_selected_report(self) -> bool:
        report_id = self.selected_report_id()
        if report_id is None or self.owner is None:
            return False
        return bool(self.owner.open_report_by_id(report_id))

    # -- scenario ------------------------------------------------------------------------------------------------
    def scenario(self) -> Dict[str, Any]:
        return {"currency": self.currency_edit.text().strip().upper(), "bit_cost": _number(self.bit_cost_edit),
                "rig_rate_per_day": _number(self.rig_rate_edit), "trip_hours": _number(self.trip_edit)}

    def compare(self) -> List[Dict[str, Any]]:
        scenario = self.scenario()
        self.outcomes = {run.key: br.cost_per_length(run.figures(), missing=run.missing, **scenario)
                         for run in self.runs}
        self.comparison = br.compare(self.runs, self.outcomes)
        self.compare_table.setRowCount(len(self.comparison))
        for i, row in enumerate(self.comparison):
            values = (row["run"], row["size_in"], row["footage_m"], row["hours"], row["rop_m_h"], row["lifecycle"],
                      row["data"], row["cost_status"], row["cost_per_m"], row["currency"],
                      "yes" if row["best_cost"] else "", "yes" if row["best_rop"] else "",
                      "; ".join(row["cost_reasons"]))
            for j, value in enumerate(values):
                item = QTableWidgetItem(_text(value))
                if row["data"] != br.COMPLETE:
                    item.setForeground(QColor(INCOMPLETE_COLOUR))
                if j in (8,):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.compare_table.setItem(i, j, item)
        assessed = sum(1 for r in self.comparison if r["cost_status"] == br.ASSESSED)
        problems = br.scenario_problems(**scenario)
        self.status.setText(f"{assessed} of {len(self.comparison)} run(s) costed. {br.COST_LABEL}."
                            + (" NOT ASSESSED: " + "; ".join(problems) + "." if problems else ""))
        self._update_actions()
        return self.comparison

    def save_selected(self) -> Optional[Dict[str, Any]]:
        run = self.selected_run()
        if run is None:
            self.status.setText("Select a run first.")
            return None
        outcome = br.cost_per_length(run.figures(), missing=run.missing, **self.scenario())
        if outcome.status != br.ASSESSED:
            self.status.setText("Not saved: NOT ASSESSED — " + "; ".join(outcome.reasons))
            return None
        try:
            case = br.save_scenario(self.db, run, outcome, well_id=self.well_id, wellbore_id=self.wellbore_id)
        except (ValueError, AuthorizationError) as exc:
            self.status.setText(f"Not saved: {exc}")
            return None
        self.status.setText(f"Scenario saved as calculation case #{case['id']} ({outcome.cost_per_m:,.2f} "
                            f"{outcome.currency}/m for bit {run.key}). {br.COST_LABEL}.")
        return case

    # -- export ------------------------------------------------------------------------------------------------
    def export_to(self, path: str) -> int:
        return br.export_csv(path, self.runs, self.comparison or br.compare(self.runs, {}),
                             well_label=f"well #{self.well_id}", scope_label=self.scope_text(),
                             scenario=self.scenario() if self.comparison else None)

    def _export_dialog(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(self, "Export bit runs", "bit_runs.csv", "CSV (*.csv)")
        if path:
            written = self.export_to(path)
            self.status.setText(f"Exported {written} run(s) to {path}.")

    def _update_actions(self) -> None:
        has_runs = bool(self.runs)
        self.compare_btn.setEnabled(has_runs)
        self.export_btn.setEnabled(has_runs)
        self.save_btn.setEnabled(self.selected_run() is not None and self.db is not None)
        self.open_btn.setEnabled(self.selected_report_id() is not None and self.owner is not None)
