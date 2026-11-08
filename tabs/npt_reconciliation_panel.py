"""M134: NPT event reconciliation (W12 Analysis › NPT Analysis).

The NPT register and the DDR time-log NPT rows of the selected well (or explicitly selected wellbore) are
paired by ``core.npt_reconciliation``: every group with its status, both sources' hours, the hours counted
once and the basis. UNCERTAIN groups are never added; a user with edit rights records a decision (same event /
different events) with evidence and a reason (append-only, audited). "Open DDR" opens the group's report;
the table exports to CSV with its provenance.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from core import npt_reconciliation as nr
from core.authorization import AuthorizationError
from core.context_jobs import CANCELLED, ERROR, STALE, ContextJobRunner, check_cancel
from tabs.job_retry import REFRESH_HINT, retry_button, scope_row, show_retry

logger = logging.getLogger(__name__)

STATUS_COLOUR = {nr.MATCHED: "#1e7d32", nr.CONFIRMED_SAME: "#1e7d32", nr.CONFIRMED_DIFFERENT: "#1f6fb2",
                 nr.REGISTER_ONLY: "#5d6d7e", nr.LOG_ONLY: "#5d6d7e", nr.UNCERTAIN: "#b26a00"}


def _text(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def _reconcile_job(db, params, cancel_event):
    """Worker side: plain ids in, frozen groups out."""
    check_cancel(cancel_event)
    return nr.reconcile_scope(db, params["well"], params["wellbore"])


class DecisionDialog(QDialog):
    def __init__(self, group: nr.Group, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Decide an UNCERTAIN NPT group")
        form = QFormLayout(self)
        summary = QLabel("; ".join(r.label() for r in group.register) + " ↔ time-log rows "
                         + ", ".join(f"#{r.id} {r.start}–{r.end}" for r in group.logs))
        summary.setWordWrap(True)
        form.addRow(summary)
        self.decision = QComboBox()
        self.decision.addItem("The rows describe ONE event (count once)", nr.SAME_EVENT)
        self.decision.addItem("The rows are DIFFERENT events (count both)", nr.DIFFERENT_EVENTS)
        self.evidence = QPlainTextEdit()
        self.evidence.setPlaceholderText("Required: the report, log or document this rests on")
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Required")
        form.addRow("Decision", self.decision)
        form.addRow("Evidence", self.evidence)
        form.addRow("Reason", self.reason)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self):
        return self.decision.currentData(), self.evidence.toPlainText(), self.reason.text()


class NptReconciliationPanel(QWidget):
    def __init__(self, db=None, owner=None, parent=None):
        super().__init__(parent)
        self.db, self.owner = db, owner
        self.well_id: Optional[int] = None
        self.wellbore_id: Optional[int] = None
        self.recon: Optional[nr.Reconciliation] = None
        self.jobs = ContextJobRunner(None, "NPT reconciliation", refresh_hint=REFRESH_HINT, parent=self)   # M103 runner (M51)
        self.jobs.result_ready.connect(self._show)
        self.jobs.state_changed.connect(self._job_state)

        box = QGroupBox("NPT event reconciliation — register vs DDR time log, each event counted once")
        layout = QVBoxLayout(box)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        self.scope_label = QLabel("NOT ASSESSED: select a well")
        self.scope_label.setWordWrap(True)
        self.retry_btn = retry_button(self._retry)
        layout.addLayout(scope_row(self.scope_label, self.retry_btn))
        self.table = QTableWidget(0, len(nr.COLUMNS))
        self.table.setHorizontalHeaderLabels(nr.COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._update_actions)
        self.table.setMinimumHeight(220)
        layout.addWidget(self.table)
        self.totals_label = QLabel("")
        self.totals_label.setWordWrap(True)
        layout.addWidget(self.totals_label)
        self.excluded_label = QLabel("")
        self.excluded_label.setWordWrap(True)
        layout.addWidget(self.excluded_label)
        buttons = QHBoxLayout()
        self.open_btn = QPushButton("Open DDR")
        self.open_btn.clicked.connect(self.open_selected_report)
        self.decide_btn = QPushButton("Decide UNCERTAIN group…")
        self.decide_btn.clicked.connect(self._decide_dialog)
        self.export_btn = QPushButton("Export CSV…")
        self.export_btn.clicked.connect(self._export_dialog)
        for button in (self.open_btn, self.decide_btn, self.export_btn):
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self._update_actions()

    # -- scope ------------------------------------------------------------------------------------------------
    def set_scope(self, well_id: Optional[int], wellbore_id: Optional[int] = None) -> None:
        if (well_id, wellbore_id) != (self.well_id, self.wellbore_id):
            self.status.setText("")
        self.well_id, self.wellbore_id = well_id, wellbore_id
        self.reload()

    def scope_text(self) -> str:
        if self.well_id is None:
            return "NOT ASSESSED: select a well"
        if self.wellbore_id:
            return (f"Well #{self.well_id}, wellbore #{self.wellbore_id} only (register events and time logs of "
                    "that wellbore's reports)")
        return f"Well #{self.well_id}, whole well"

    def reload(self) -> Optional[int]:
        self.recon = None
        self._fill()
        if self.well_id is None or self.db is None:
            self.jobs.invalidate()
            self.scope_label.setText(self.scope_text())
            return None
        self.scope_label.setText(self.scope_text() + " — reconciling…")
        self.jobs.db_manager = self.db
        return self.jobs.start(_reconcile_job, {"well": self.well_id, "wellbore": self.wellbore_id})

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
            self.recon = None
            self._fill()
            self.scope_label.setText(message)

    def _show(self, _job_id: int, result) -> None:
        self.recon = result
        text = self.scope_text() + f" — {len(result.groups)} group(s)."
        if not result.groups:                     # M138: no record is not "0 h of NPT"
            text += " No NPT register event or NPT time-log row is recorded in this scope."
        self.scope_label.setText(text)
        self._fill()

    def _fill(self) -> None:
        groups = self.recon.groups if self.recon else []
        self.table.setRowCount(len(groups))
        for i, group in enumerate(groups):
            for j, value in enumerate(group.table_row()):
                item = QTableWidgetItem(_text(value))
                if j == 0:
                    item.setForeground(QColor(STATUS_COLOUR.get(group.status, "#000000")))
                self.table.setItem(i, j, item)
        self.totals_label.setText(self.recon.summary() if self.recon else "")
        excluded = self.recon.excluded if self.recon else []
        self.excluded_label.setText(("Excluded from this scope: " + "; ".join(excluded)) if excluded else "")
        self._update_actions()

    # -- drill-down, decision, export ------------------------------------------------------------------------------
    def selected_group(self) -> Optional[nr.Group]:
        model = self.table.selectionModel()
        rows = model.selectedRows() if model else []
        if not self.recon or not rows or rows[0].row() >= len(self.recon.groups):
            return None
        return self.recon.groups[rows[0].row()]

    def open_selected_report(self) -> bool:
        group = self.selected_group()
        if group is None or group.report_id is None or self.owner is None:
            return False
        return bool(self.owner.open_report_by_id(group.report_id))

    def decide_selected(self, decision: str, evidence: str, reason: str) -> Optional[int]:
        group = self.selected_group()
        if group is None or group.status != nr.UNCERTAIN:
            self.status.setText("Select an UNCERTAIN group first.")
            return None
        try:
            decision_id = nr.record_decision(self.db, self.well_id, group.register_ids, group.log_ids,
                                             decision=decision, evidence=evidence, reason=reason,
                                             wellbore_id=self.wellbore_id)
        except (nr.ReconciliationError, AuthorizationError) as exc:
            self.status.setText(f"Not recorded: {exc}")
            return None
        self.status.setText(f"Decision #{decision_id} recorded ({decision}); it is audited and cannot be changed "
                            "(a later decision for the same rows governs).")
        self.reload()
        return decision_id

    def _decide_dialog(self) -> None:
        group = self.selected_group()
        if group is None:
            return
        dialog = DecisionDialog(group, self)
        if dialog.exec() == QDialog.Accepted:
            self.decide_selected(*dialog.values())

    def export_to(self, path: str) -> int:
        return nr.export_csv(path, self.recon or nr.Reconciliation([], []), well_label=f"well #{self.well_id}",
                             scope_label=self.scope_text())

    def _export_dialog(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(self, "Export NPT reconciliation", "npt_reconciliation.csv",
                                                    "CSV (*.csv)")
        if path:
            self.status.setText(f"Exported {self.export_to(path)} group(s) to {path}.")

    def _update_actions(self) -> None:
        group = self.selected_group()
        self.open_btn.setEnabled(group is not None and group.report_id is not None and self.owner is not None)
        self.decide_btn.setEnabled(group is not None and group.status == nr.UNCERTAIN and self.db is not None)
        self.export_btn.setEnabled(bool(self.recon and self.recon.groups))
