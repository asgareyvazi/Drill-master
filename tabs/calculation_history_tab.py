"""M67: Calculation history and Engineering Report Center.

One list of every stored calculation (engine snapshots, trajectory, W13
cases, directional plan revisions) through ``core.calculation_history``
adapters: filter, inspect, compare two, recalculate-and-verify with the
current method (stored separately, the original is never changed), export
the list, and render HTML/PDF reports. Reads run on the GUI thread through
short read-only sessions inside the core module; no ORM object reaches Qt.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget,
)

from core import calculation_history as ch

logger = logging.getLogger(__name__)
COLUMNS = ("Source", "Name", "Method", "Version", "Created", "Scope", "Derived from")


class CalculationHistoryTab(QWidget):
    def __init__(self, db_manager=None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.db = db_manager
        self.well_id: Optional[int] = None
        self.entries: List[ch.HistoryEntry] = []
        self.last_outcome: Optional[dict] = None
        self.setLayoutDirection(Qt.LeftToRight)
        layout = QVBoxLayout(self)

        filters = QHBoxLayout()
        self.source_combo = QComboBox()
        self.source_combo.addItem("All sources", None)
        for source in ch.SOURCES:
            self.source_combo.addItem(source, source)
        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText("Filter by name, method or input…")
        self.well_only = QCheckBox("Selected well only")
        self.well_only.setChecked(True)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._refresh_clicked)
        self.source_combo.currentIndexChanged.connect(self._refresh_clicked)
        self.text_edit.returnPressed.connect(self.refresh)
        self.well_only.toggled.connect(self._refresh_clicked)
        for widget in (QLabel("Source:"), self.source_combo, self.text_edit, self.well_only, self.refresh_btn):
            filters.addWidget(widget)
        layout.addLayout(filters)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.detail = QTextBrowser()
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.detail)
        layout.addWidget(splitter, 1)

        actions = QHBoxLayout()
        self.compare_btn = QPushButton("Compare selected (2)")
        self.compare_btn.clicked.connect(self._compare_clicked)
        self.recalc_btn = QPushButton("Recalculate && verify")
        self.recalc_btn.setToolTip("Re-run with the current method and compare with the stored result; nothing is changed.")
        self.recalc_btn.clicked.connect(self._recalc_clicked)
        self.save_recalc_btn = QPushButton("Save recalculation")
        self.save_recalc_btn.setToolTip("Store the recalculated result as a new case; the original stays as it was.")
        self.save_recalc_btn.clicked.connect(self._save_recalc_clicked)
        self.report_btn = QPushButton("Export report…")
        self.report_btn.clicked.connect(self._report_clicked)
        self.export_btn = QPushButton("Export list CSV…")
        self.export_btn.clicked.connect(self._export_clicked)
        for button in (self.compare_btn, self.recalc_btn, self.save_recalc_btn, self.report_btn, self.export_btn):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self._update_actions()

    # -- data ---------------------------------------------------------------
    def set_well(self, well_id: Optional[int], _well_data=None) -> None:
        self.well_id = well_id
        self.refresh()

    def refresh(self) -> None:
        self.entries = []
        if self.db is not None:
            well = self.well_id if self.well_only.isChecked() else None
            if self.well_only.isChecked() and well is None:
                self.status.setText("Select a well, or clear 'Selected well only'.")
            else:
                source = self.source_combo.currentData()
                self.entries = ch.load_history(self.db, well_id=well, sources=[source] if source else None,
                                               text=self.text_edit.text())
                self.status.setText(f"{len(self.entries)} calculation(s).")
        self.table.setRowCount(len(self.entries))
        for row, entry in enumerate(self.entries):
            data = entry.to_row()
            for col, key in enumerate(("source", "name", "method", "version", "created_at", "scope", "parent")):
                self.table.setItem(row, col, QTableWidgetItem(str(data[key])))
        self.detail.clear()
        self.last_outcome = None
        self._update_actions()

    def selected(self) -> List[ch.HistoryEntry]:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        return [self.entries[r] for r in rows if r < len(self.entries)]

    def select_rows(self, rows: List[int]) -> None:
        self.table.clearSelection()
        mode = self.table.selectionMode()
        self.table.setSelectionMode(QAbstractItemView.MultiSelection)
        for row in rows:
            self.table.selectRow(row)
        self.table.setSelectionMode(mode)

    def _update_actions(self) -> None:
        chosen = self.selected() if self.table.selectionModel() is not None else []
        self.compare_btn.setEnabled(len(chosen) == 2)
        self.recalc_btn.setEnabled(len(chosen) == 1)
        self.report_btn.setEnabled(len(chosen) in (1, 2))
        self.save_recalc_btn.setEnabled(bool(self.last_outcome and self.last_outcome.get("values")))
        self.export_btn.setEnabled(bool(self.entries))

    # -- actions ------------------------------------------------------------
    def report_html(self) -> str:
        chosen = self.selected()
        if len(chosen) == 1:
            return ch.render_entry_report(chosen[0])
        if len(chosen) == 2:
            return ch.render_comparison_report(chosen[0], chosen[1])
        return ""

    def compare(self) -> Optional[dict]:
        chosen = self.selected()
        if len(chosen) != 2:
            return None
        self.detail.setHtml(self.report_html())
        return ch.compare_entries(*chosen)

    def recalculate(self) -> Optional[dict]:
        chosen = self.selected()
        if len(chosen) != 1:
            return None
        outcome = ch.recalculate_entry(chosen[0])
        self.last_outcome = outcome
        method = ("same method" if outcome["method_matches"] else "METHOD CHANGED"
                  if outcome["method_matches"] is False else "method not compared")
        self.status.setText(f"Recalculation: {outcome['status']} ({method}). {outcome['detail']}".strip())
        self._update_actions()
        return outcome

    def save_recalculation(self) -> Optional[dict]:
        chosen = self.selected()
        if len(chosen) != 1 or not self.last_outcome:
            return None
        case = ch.save_recalculation(self.db, chosen[0], self.last_outcome)
        self.status.setText(f"Stored recalculation as case #{case['id']}; the original record is unchanged.")
        self.refresh()
        return case

    def export_report(self, path: str) -> bool:
        html = self.report_html()
        if not html:
            return False
        try:
            if path.lower().endswith(".pdf"):
                document = QTextDocument()
                document.setHtml(html)
                writer = QPdfWriter(path)
                writer.setPageSize(QPageSize(QPageSize.A4))
                document.print_(writer)
            else:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(html)
        except OSError as exc:
            logger.error("Report export failed: %s", exc)
            self.status.setText(f"Report export failed: {exc}")
            return False
        self.status.setText(f"Report written to {path}.")
        return True

    def _selection_changed(self):
        chosen = self.selected()
        self.last_outcome = None
        if len(chosen) == 1:
            self.detail.setHtml(ch.render_entry_report(chosen[0]))
        self._update_actions()

    def _refresh_clicked(self, *_):
        self.refresh()

    def _compare_clicked(self, _checked=False):
        self.compare()

    def _recalc_clicked(self, _checked=False):
        self.recalculate()

    def _save_recalc_clicked(self, _checked=False):
        self.save_recalculation()

    def _report_clicked(self, _checked=False):
        path, _ = QFileDialog.getSaveFileName(self, "Export report", "calculation_report.html",
                                              "HTML (*.html);;PDF (*.pdf)")
        if path:
            self.export_report(path)

    def _export_clicked(self, _checked=False):
        path, _ = QFileDialog.getSaveFileName(self, "Export history", "calculation_history.csv", "CSV (*.csv)")
        if path:
            count = ch.export_history_csv(self.entries, path)
            self.status.setText(f"Exported {count} row(s) to {path}.")
