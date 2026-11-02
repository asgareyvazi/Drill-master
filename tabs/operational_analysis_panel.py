"""W12 "Operational Analysis" page (M91).

Shows ``core.operational_analysis`` for the analysis page's current scope
(well, optionally a wellbore) and an optional report-date range: summary,
daily footage / ROP, activities, NPT timeline with sources, bit runs, MSE
points, cost per currency and plan vs actual. A row with a source daily report
opens it (drill-down through the owner's SelectionManager path); export writes
CSV or XLSX with the scope, method and UNSIGNED label. Missing values show as
"—", never as 0. Reads run on the GUI thread on demand (Refresh) and are
discarded when the selection changes.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDateEdit, QFileDialog, QHBoxLayout, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from core import operational_analysis as oa

logger = logging.getLogger(__name__)

TITLES = {"daily": "Daily footage / ROP", "activities": "Activities", "npt": "NPT timeline", "bit_runs": "Bit runs",
          "mse": "MSE points", "cost": "Cost (per currency)", "plan_vs_actual": "Plan vs actual"}


def _cell(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


class OperationalAnalysisPanel(QWidget):
    def __init__(self, owner, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.owner = owner
        self.result: Optional[oa.OperationalAnalysis] = None
        self._scope_pair = None                 # (well, wellbore) the shown result belongs to
        self.setLayoutDirection(Qt.LeftToRight)
        layout = QVBoxLayout(self)
        intro = QLabel("Operational analysis from the stored daily reports, time logs, drilling parameters, NPT "
                       "register, MSE calculations and cost records. Missing data stays '—' (never 0). "
                       + oa.LABEL)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        row = QHBoxLayout()
        self.limit_dates = QCheckBox("Limit report dates")
        self.from_date, self.to_date = QDateEdit(), QDateEdit()
        for edit in (self.from_date, self.to_date):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
            edit.setDate(QDate.currentDate())
            edit.setEnabled(False)
        self.limit_dates.toggled.connect(self.from_date.setEnabled)
        self.limit_dates.toggled.connect(self.to_date.setEnabled)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(lambda _c=False: self.refresh())
        self.open_btn = QPushButton("Open source report")
        self.open_btn.clicked.connect(lambda _c=False: self.open_selected())
        self.export_btn = QPushButton("Export…")
        self.export_btn.clicked.connect(self._export_clicked)
        for widget in (self.limit_dates, QLabel("From:"), self.from_date, QLabel("To:"), self.to_date,
                       self.refresh_btn, self.open_btn, self.export_btn):
            row.addWidget(widget)
        row.addStretch(1)
        layout.addLayout(row)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.summary)
        self.tabs = QTabWidget()
        self.tables = {}
        for key, title in TITLES.items():
            table = QTableWidget(0, len(oa.COLUMNS[key]))
            table.setHorizontalHeaderLabels(list(oa.COLUMNS[key]))
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setSelectionMode(QAbstractItemView.SingleSelection)
            table.itemSelectionChanged.connect(self._update_actions)
            table.cellDoubleClicked.connect(lambda _r, _c: self.open_selected())
            self.tables[key] = table
            self.tabs.addTab(table, title)
        self.tabs.currentChanged.connect(lambda _i: self._update_actions())
        layout.addWidget(self.tabs, 1)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.invalidate()

    # -- state ----------------------------------------------------------------
    def _owner_pair(self):
        return (getattr(self.owner, "current_well_id", None) or None,
                getattr(self.owner, "current_wellbore_id", None) or None)

    def selection_changed(self) -> None:
        """Keep the result only while the well and wellbore are unchanged (e.g. after a drill-down)."""
        if self.result is None or self._owner_pair() != self._scope_pair or self._scope_pair[0] is None:
            self.invalidate("Select a well first." if self._owner_pair()[0] is None
                            else "Press Refresh to analyse the selected scope.")

    def invalidate(self, message: str = "Press Refresh to analyse the selected scope.") -> None:
        """The selection changed: nothing of the previous scope stays on screen."""
        self.result = None
        self._scope_pair = None
        for table in self.tables.values():
            table.setRowCount(0)
        self.summary.setText("")
        self.status.setText(message)
        self._update_actions()

    def _range(self):
        if not self.limit_dates.isChecked():
            return None, None
        return self.from_date.date().toPython(), self.to_date.date().toPython()

    def refresh(self) -> Optional[oa.OperationalAnalysis]:
        db = getattr(self.owner, "db", None)
        if db is None or not getattr(self.owner, "current_well_id", None):
            self.invalidate("Select a well first.")
            return None
        start, end = self._range()
        try:
            result = oa.analyze(db, self.owner._analysis_scope(), start=start, end=end)
        except ValueError as exc:
            self.invalidate(str(exc))
            return None
        self.result = result
        self._scope_pair = self._owner_pair()
        for key, table in self.tables.items():
            _columns, rows = result.tables[key]
            table.setRowCount(len(rows))
            for r, values in enumerate(rows):
                for c, value in enumerate(values):
                    table.setItem(r, c, QTableWidgetItem(_cell(value)))
        s = result.summary
        money = (f"{s['cost_currency']} {s['cost_actual']:,.2f} actual" if s["cost_actual"] is not None
                 else f"cost total not assessed ({s['cost_status']})")
        self.summary.setText(
            f"<b>{result.scope_label}</b> — {s['reports']} report(s). Footage {_cell(s['footage_m'])} m "
            f"(known on {s['footage_days']} days, known sum {_cell(s['footage_known_m'])} m); drilling "
            f"{_cell(s['drilling_hours'])} h; time-weighted ROP {_cell(s['weighted_rop_m_h'])} m/h "
            f"({s['weighted_rop_days']} days); logged {_cell(s['logged_hours'])} h; NPT {_cell(s['npt_hours'])} h "
            f"({_cell(s['npt_percent'])} %) from time logs, NPT register {_cell(s['npt_register_hours'])} h "
            f"(separate source); {s['bit_runs']} bit run(s); {s['mse_points']} MSE point(s); {money}.")
        self.status.setText("Notes: " + ("; ".join(result.notes) if result.notes else "none") + f". {oa.OA_VERSION}.")
        self._update_actions()
        return result

    def current_key(self) -> str:
        return list(TITLES)[self.tabs.currentIndex()]

    def selected_report_id(self) -> Optional[int]:
        if self.result is None:
            return None
        key = self.current_key()
        rows = self.tables[key].selectionModel().selectedRows()
        if not rows:
            return None
        ids = self.result.report_ids.get(key, [])
        index = rows[0].row()
        return ids[index] if index < len(ids) else None

    def _update_actions(self) -> None:
        self.export_btn.setEnabled(self.result is not None)
        self.open_btn.setEnabled(self.selected_report_id() is not None)

    # -- actions --------------------------------------------------------------
    def open_selected(self) -> bool:
        report_id = self.selected_report_id()
        if report_id is None:
            return False
        return bool(self.owner.open_report_by_id(report_id))

    def export(self, path: str) -> list:
        if self.result is None:
            return []
        written = oa.export(self.result, path)
        self.status.setText(f"Exported {len(written)} file(s): {', '.join(written)}")
        return written

    def _export_clicked(self, _checked=False):
        path, _ = QFileDialog.getSaveFileName(self, "Export operational analysis", "operational_analysis.xlsx",
                                              "Excel (*.xlsx);;CSV (*.csv)")
        if path:
            self.export(path)
