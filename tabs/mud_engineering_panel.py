"""M133: Mud evaluation workbench (W12 Analysis › Mud evaluation).

The DDR mud reports of the selected well (or of the explicitly selected wellbore) are listed; the selected one
is evaluated by ``core.mud_engineering``: every value with its class (LAB / ASSUMED / DERIVED / UNKNOWN) and
its source or formula. Fann readings are optional and must be tagged LAB (with the lab reference) or ASSUMED.
Herschel-Bulkley is shown as NOT ASSESSED. "Open DDR" opens the mud report's daily report; an evaluation is
saved as an immutable case that History re-runs.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from PySide6.QtGui import QColor, QDoubleValidator
from PySide6.QtWidgets import (QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from core import mud_engineering as me
from core.authorization import AuthorizationError
from core.context_jobs import CANCELLED, ERROR, STALE, ContextJobRunner, check_cancel
from tabs.job_retry import REFRESH_HINT, retry_button, scope_row, show_retry

logger = logging.getLogger(__name__)

CLASS_COLOUR = {me.LAB: "#1e7d32", me.ASSUMED: "#b26a00", me.DERIVED: "#1f6fb2", me.DERIVED_ASSUMED: "#b26a00",
                me.UNKNOWN: "#7f8c8d"}
NOT_TAGGED = "— class —"


def _text(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.4g}" if abs(value) < 1e4 else f"{value:,.1f}"
    return str(value)


def _load_samples_job(db, params, cancel_event):
    """Worker side: plain ids in, frozen ``MudSample`` DTOs out."""
    check_cancel(cancel_event)
    return me.load_samples(db, params["well"], params["wellbore"])


class MudEvaluationPanel(QWidget):
    def __init__(self, db=None, owner=None, parent=None):
        super().__init__(parent)
        self.db, self.owner = db, owner
        self.well_id: Optional[int] = None
        self.wellbore_id: Optional[int] = None
        self.samples: List[me.MudSample] = []
        self.evaluation: Optional[me.Evaluation] = None
        self.jobs = ContextJobRunner(None, "mud reports", refresh_hint=REFRESH_HINT, parent=self)     # M103 runner (M51: no GUI-thread SQL)
        self.jobs.result_ready.connect(self._show_samples)
        self.jobs.state_changed.connect(self._job_state)

        layout = QVBoxLayout(self)
        self.scope_label = QLabel("NOT ASSESSED: select a well")
        self.scope_label.setWordWrap(True)
        self.retry_btn = retry_button(self._retry)
        layout.addLayout(scope_row(self.scope_label, self.retry_btn))
        self.samples_table = QTableWidget(0, len(me.LIST_COLUMNS))
        self.samples_table.setHorizontalHeaderLabels(me.LIST_COLUMNS)
        self.samples_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.samples_table.setSelectionMode(QTableWidget.SingleSelection)
        self.samples_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.samples_table.itemSelectionChanged.connect(self.evaluate_selected)
        layout.addWidget(self.samples_table)

        readings = QGroupBox("Fann readings (optional; the DDR mud report has none) — each must be LAB with its "
                             "lab reference, or ASSUMED")
        grid = QGridLayout(readings)
        self.reading_edits: Dict[str, QLineEdit] = {}
        self.class_combos: Dict[str, QComboBox] = {}
        self.reference_edits: Dict[str, QLineEdit] = {}
        for column, (key, label) in enumerate(me.READINGS):
            edit = QLineEdit()
            edit.setPlaceholderText("Not entered")
            edit.setValidator(QDoubleValidator(0.0, 1000.0, 2, edit))
            combo = QComboBox()
            combo.addItem(NOT_TAGGED, None)
            combo.addItem("LAB (measured)", me.LAB)
            combo.addItem("ASSUMED", me.ASSUMED)
            reference = QLineEdit()
            reference.setPlaceholderText("Lab reference")
            grid.addWidget(QLabel(label), 0, column)
            grid.addWidget(edit, 1, column)
            grid.addWidget(combo, 2, column)
            grid.addWidget(reference, 3, column)
            self.reading_edits[key], self.class_combos[key], self.reference_edits[key] = edit, combo, reference
        layout.addWidget(readings)

        buttons = QHBoxLayout()
        self.evaluate_btn = QPushButton("Evaluate")
        self.evaluate_btn.clicked.connect(self.evaluate_selected)
        self.open_btn = QPushButton("Open DDR")
        self.open_btn.clicked.connect(self.open_selected_report)
        self.save_btn = QPushButton("Save evaluation")
        self.save_btn.clicked.connect(self.save_selected)
        for button in (self.evaluate_btn, self.open_btn, self.save_btn):
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.properties_table = QTableWidget(0, len(me.COLUMNS))
        self.properties_table.setHorizontalHeaderLabels(me.COLUMNS)
        self.properties_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.properties_table)
        self.hb_label = QLabel("Herschel-Bulkley: " + me.HB_STATUS)
        self.hb_label.setWordWrap(True)
        layout.addWidget(self.hb_label)
        self.status = QLabel(me.MUD_LABEL)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self._update_actions()

    # -- scope ------------------------------------------------------------------------------------------------
    def set_scope(self, well_id: Optional[int], wellbore_id: Optional[int] = None) -> None:
        self.well_id, self.wellbore_id = well_id, wellbore_id
        self.reload()

    def scope_text(self) -> str:
        if self.well_id is None:
            return "NOT ASSESSED: select a well"
        if self.wellbore_id:
            return (f"Well #{self.well_id}, wellbore #{self.wellbore_id} only (mud reports of that wellbore's DDRs; "
                    "unlinked legacy rows excluded)")
        return f"Well #{self.well_id}, whole well (all mud reports, including legacy rows without a DDR link)"

    def reload(self) -> Optional[int]:
        self.samples, self.evaluation = [], None
        self._fill_samples()
        if self.well_id is None or self.db is None:
            self.jobs.invalidate()
            self.scope_label.setText(self.scope_text())
            return None
        self.scope_label.setText(self.scope_text() + " — loading mud reports…")
        self.jobs.db_manager = self.db
        return self.jobs.start(_load_samples_job, {"well": self.well_id, "wellbore": self.wellbore_id})

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
            self.samples, self.evaluation = [], None
            self._fill_samples()
            self.scope_label.setText(message)          # the runner's message names the state / error type

    def _show_samples(self, _job_id: int, result) -> None:
        self.samples = list(result or [])
        unlinked = sum(1 for s in self.samples if not s.report_id)
        text = self.scope_text() + f" — {len(self.samples)} mud report(s)"
        text += f", {unlinked} without a DDR link." if unlinked else "."
        if not self.samples:
            text += " No mud report is recorded in this scope."
        self.scope_label.setText(text)
        self._fill_samples()

    def _fill_samples(self) -> None:
        self.samples_table.setRowCount(len(self.samples))
        for i, sample in enumerate(self.samples):
            for j, value in enumerate(sample.table_row()):
                item = QTableWidgetItem(_text(value))
                if not sample.report_id:
                    item.setToolTip("Legacy mud row without a DDR link: shown for the whole well only.")
                self.samples_table.setItem(i, j, item)
        self.properties_table.setRowCount(0)
        self._update_actions()

    # -- evaluation -------------------------------------------------------------------------------------------
    def selected_sample(self) -> Optional[me.MudSample]:
        model = self.samples_table.selectionModel()
        rows = model.selectedRows() if model else []
        if not rows or rows[0].row() >= len(self.samples):
            return None
        return self.samples[rows[0].row()]

    def select(self, index: int) -> None:
        self.samples_table.selectRow(index)

    def readings(self) -> Dict[str, Dict[str, Any]]:
        out = {}
        for key, edit in self.reading_edits.items():
            text = edit.text().strip().replace(",", "")
            if text:
                out[key] = {"value": text, "class": self.class_combos[key].currentData(),
                            "reference": self.reference_edits[key].text().strip()}
        return out

    def set_reading(self, key: str, value: str, cls: Optional[str], reference: str = "") -> None:
        self.reading_edits[key].setText(value)
        self.class_combos[key].setCurrentIndex(max(0, self.class_combos[key].findData(cls)))
        self.reference_edits[key].setText(reference)

    def evaluate_selected(self) -> Optional[me.Evaluation]:
        sample = self.selected_sample()
        self.evaluation = None
        self.properties_table.setRowCount(0)
        if sample is None:
            self._update_actions()
            return None
        try:
            self.evaluation = me.evaluate(sample.frozen(), self.readings())
        except me.MudEvaluationError as exc:
            self.status.setText(f"NOT ASSESSED: {exc}")
            self._update_actions()
            return None
        rows = self.evaluation.rows
        self.properties_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate((row.label, row.value, row.unit, row.cls, row.source)):
                item = QTableWidgetItem(_text(value))
                if j == 3:
                    item.setForeground(QColor(CLASS_COLOUR.get(row.cls, "#000000")))
                self.properties_table.setItem(i, j, item)
        self.status.setText(" ".join(self.evaluation.notes) + f" {me.MUD_LABEL}.")
        self._update_actions()
        return self.evaluation

    # -- navigation and saving ----------------------------------------------------------------------------------
    def open_selected_report(self) -> bool:
        sample = self.selected_sample()
        if sample is None or not sample.report_id or self.owner is None:
            return False
        return bool(self.owner.open_report_by_id(sample.report_id))

    def save_selected(self) -> Optional[Dict[str, Any]]:
        sample = self.selected_sample()
        if sample is None:
            self.status.setText("Select a mud report first.")
            return None
        try:
            case = me.save_evaluation(self.db, sample, self.readings(), well_id=self.well_id,
                                      wellbore_id=self.wellbore_id)
        except (me.MudEvaluationError, AuthorizationError) as exc:
            self.status.setText(f"Not saved: {exc}")
            return None
        self.status.setText(f"Evaluation saved as calculation case #{case['id']} (mud report #{sample.id}). "
                            f"{me.MUD_LABEL}.")
        return case

    def _update_actions(self) -> None:
        sample = self.selected_sample()
        self.evaluate_btn.setEnabled(sample is not None)
        self.save_btn.setEnabled(sample is not None and self.db is not None and self.well_id is not None)
        self.open_btn.setEnabled(sample is not None and bool(sample.report_id) and self.owner is not None)
