"""Dialog to link a library document to a well and, optionally, a report (M45).

The dialog only collects a choice; it never writes.  The Documents tab saves
the link through ``DocumentLinkService`` after the user presses "Link".

* Wells are listed with code, field, project, company, rig, spud date and
  report count, and same-name wells are flagged, so two wells called the
  same can be told apart.
* "Suggestions" lists wells whose name/code appears in the stored text, with
  the page it was found on.  Clicking a suggestion only selects that well in
  the table; nothing is pre-selected and nothing is linked without "Link".
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from core.document_links import DocumentLinkService

logger = logging.getLogger(__name__)

WELL_COLUMNS = ("Well name", "Code", "Field", "Project", "Company", "Rig", "Spud date", "Reports", "ID")
REPORT_COLUMNS = ("Report", "Date", "Section", "Depth @24:00 (m)", "Status", "ID")


def _text(value) -> str:
    if value is None or value == "":
        return "—"
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


class LinkDocumentDialog(QDialog):
    """Pick well → (optional) report → (optional) anchor page."""

    def __init__(self, db_manager, document: dict, pages: list, *, suggestions=(), current: Optional[dict] = None,
                 anchor_page: Optional[int] = None, parent=None):
        super().__init__(parent)
        self.service = DocumentLinkService(db_manager)
        self.document = document
        self.pages = pages
        self.suggestions = list(suggestions)
        self.current = current
        self.wells: list = []
        self.reports: list = []
        self.setWindowTitle("Change document link" if current else "Link document to a well / report")
        self.resize(1040, 680)
        self._build()
        self.reload_wells()
        if current:
            self.select_well(current["well_id"])
            self.select_report(current.get("report_id"))
            self.set_anchor_page(current.get("page_no"))
        elif anchor_page is not None:
            self.set_anchor_page(anchor_page)
        self._update_state()

    # ------------------------------------------------------------------ UI
    def _build(self):
        layout = QVBoxLayout(self)
        title = QLabel(f"<b>{self.document['file_name']}</b>"
                       + (f" — currently linked to well <b>{self.current['well_name']}</b>" if self.current else ""))
        title.setWordWrap(True)
        layout.addWidget(title)

        suggestion_title = QLabel("Suggestions from the stored text (a well name or code found in the document). "
                                  "They are hints only — nothing is linked until you press “Link”.")
        suggestion_title.setWordWrap(True)
        suggestion_title.setStyleSheet("color: #475467;")
        layout.addWidget(suggestion_title)
        self.suggestion_list = QListWidget()
        self.suggestion_list.setMaximumHeight(90)
        for suggestion in self.suggestions:
            code = f", code {suggestion.well_code}" if suggestion.well_code else ""
            item = QListWidgetItem(f"{suggestion.well_name} (id {suggestion.well_id}{code}) — {suggestion.matched} "
                                   f"found on {suggestion.location}, {suggestion.occurrences}×")
            item.setData(Qt.UserRole, suggestion.well_id)
            self.suggestion_list.addItem(item)
        if not self.suggestions:
            placeholder = QListWidgetItem("No well name or code from the database appears in this document.")
            placeholder.setFlags(Qt.NoItemFlags)
            self.suggestion_list.addItem(placeholder)
        self.suggestion_list.itemClicked.connect(self._suggestion_clicked)
        layout.addWidget(self.suggestion_list)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Find well:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Name, code, field, project, company or rig")
        self.filter_edit.textChanged.connect(lambda _t: self.reload_wells())
        filter_row.addWidget(self.filter_edit, 1)
        layout.addLayout(filter_row)

        self.well_table = self._table(WELL_COLUMNS)
        self.well_table.itemSelectionChanged.connect(self._well_selected)
        layout.addWidget(self.well_table, 3)

        layout.addWidget(QLabel("Daily report (optional — leave “Whole well” to link the well only):"))
        self.report_table = self._table(REPORT_COLUMNS)
        self.report_table.itemSelectionChanged.connect(self._update_state)
        layout.addWidget(self.report_table, 2)

        form = QFormLayout()
        self.page_combo = QComboBox()
        self.page_combo.addItem("No anchor page (open at the first stored page)", None)
        for page in self.pages:
            self.page_combo.addItem(page["location"], page["page_no"])
        form.addRow("Anchor page:", self.page_combo)
        layout.addLayout(form)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Save change" if self.current else "Link")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    @staticmethod
    def _table(columns):
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    # ---------------------------------------------------------------- data
    def reload_wells(self):
        selected = self.selected_well_id()
        try:
            self.wells = self.service.well_choices(self.filter_edit.text())
        except Exception as exc:
            logger.warning("Well list could not be read: %s", type(exc).__name__)
            self.wells = []
            self.summary.setText(f"Wells could not be read ({type(exc).__name__}).")
        self.well_table.blockSignals(True)
        self.well_table.setRowCount(len(self.wells))
        for row, well in enumerate(self.wells):
            values = (well["name"] + ("  ⚠ same name as another well" if well["ambiguous_name"] else ""),
                      well["code"], well["field"], well["project"], well["company"], well["rig"],
                      well["spud_date"], well["reports"], well["id"])
            for column, value in enumerate(values):
                item = QTableWidgetItem(_text(value))
                item.setData(Qt.UserRole, well["id"])
                if well["ambiguous_name"] and column == 0:
                    item.setForeground(QColor("#9a5b00"))
                self.well_table.setItem(row, column, item)
        self.well_table.blockSignals(False)
        if selected is not None:
            self.select_well(selected)
        else:
            self._well_selected()

    def _well_selected(self):
        well_id = self.selected_well_id()
        self.reports = []
        if well_id is not None:
            try:
                self.reports = self.service.report_choices(well_id)
            except Exception as exc:
                logger.warning("Report list could not be read: %s", type(exc).__name__)
        self.report_table.blockSignals(True)
        self.report_table.setRowCount(len(self.reports) + 1)
        whole = QTableWidgetItem("Whole well (no specific report)")
        whole.setData(Qt.UserRole, None)
        self.report_table.setItem(0, 0, whole)
        for column in range(1, len(REPORT_COLUMNS)):
            self.report_table.setItem(0, column, QTableWidgetItem(""))
        for row, report in enumerate(self.reports, start=1):
            number = report["report_number"] if report["report_number"] is not None else "?"
            values = (f"#{number}", report["report_date"], report["section"], report["depth"], report["status"],
                      report["id"])
            for column, value in enumerate(values):
                item = QTableWidgetItem(_text(value))
                item.setData(Qt.UserRole, report["id"])
                self.report_table.setItem(row, column, item)
        self.report_table.selectRow(0)
        self.report_table.blockSignals(False)
        self._update_state()

    def _suggestion_clicked(self, item):
        well_id = item.data(Qt.UserRole)
        if well_id is not None:
            self.filter_edit.clear()
            self.select_well(well_id)

    def _update_state(self):
        well_id = self.selected_well_id()
        ok = self.buttons.button(QDialogButtonBox.Ok)
        ok.setEnabled(well_id is not None)
        if well_id is None:
            self.summary.setText("Select a well to link this document.")
            return
        well = next((w for w in self.wells if w["id"] == well_id), None)
        report_id = self.selected_report_id()
        report = next((r for r in self.reports if r["id"] == report_id), None)
        target = f"well <b>{well['name']}</b> (id {well['id']}, code {_text(well['code'])})" if well else "well"
        if report:
            target += f", report #{_text(report['report_number'])} of {_text(report['report_date'])}"
        self.summary.setText(f"Will link to {target}.")

    # ------------------------------------------------------------- test API
    def selected_well_id(self) -> Optional[int]:
        row = self.well_table.currentRow()
        if row < 0 or not self.well_table.selectionModel().isRowSelected(row, self.well_table.rootIndex()):
            return None
        item = self.well_table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def selected_report_id(self) -> Optional[int]:
        row = self.report_table.currentRow()
        item = self.report_table.item(row, 0) if row >= 0 else None
        return item.data(Qt.UserRole) if item else None

    def select_well(self, well_id) -> bool:
        for row in range(self.well_table.rowCount()):
            if self.well_table.item(row, 0).data(Qt.UserRole) == well_id:
                self.well_table.selectRow(row)
                return True
        return False

    def select_report(self, report_id) -> bool:
        for row in range(self.report_table.rowCount()):
            if self.report_table.item(row, 0).data(Qt.UserRole) == report_id:
                self.report_table.selectRow(row)
                return True
        return False

    def set_anchor_page(self, page_no) -> None:
        index = self.page_combo.findData(page_no)
        self.page_combo.setCurrentIndex(index if index >= 0 else 0)

    def selection(self) -> dict:
        return {"well_id": self.selected_well_id(), "report_id": self.selected_report_id(),
                "page_no": self.page_combo.currentData()}
