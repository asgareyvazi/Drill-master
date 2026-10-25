"""Related-documents panel for the Well Info and Daily Report pages (M45).

Read-only list of the library documents a user has linked to the shown well
(or daily report).  "Open" asks the main window to show the document in the
Documents tab at the link's anchor page; links themselves are created,
changed and removed in the Documents tab (permission ``can_import``).
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from core.document_links import SCOPE_REPORT, SCOPE_WELL, DocumentLinkService

logger = logging.getLogger(__name__)


def link_target_text(link: dict) -> str:
    """'Well SYN-A (code)' or 'Report #3 · 2026-01-02' for one link row."""
    if link.get("report_id"):
        date = link["report_date"].isoformat() if link.get("report_date") else "no date"
        number = link["report_number"] if link.get("report_number") is not None else "?"
        return f"Report #{number} · {date}"
    code = f" ({link['well_code']})" if link.get("well_code") else ""
    return f"Whole well {link['well_name']}{code}"


class RelatedDocumentsPanel(QGroupBox):
    """Documents linked to one well (scope 'well') or one report (scope 'report')."""

    open_requested = Signal(int, object)          # document_id, anchor page_no or None

    def __init__(self, db_manager, scope: str = SCOPE_WELL, parent=None):
        super().__init__("📎 Related documents", parent)
        if scope not in (SCOPE_WELL, SCOPE_REPORT):
            raise ValueError(scope)
        self.setObjectName(f"related_documents_{scope}")
        self.scope = scope
        self.service = DocumentLinkService(db_manager) if db_manager is not None else None
        self.target_id: Optional[int] = None
        self.links: list = []
        layout = QVBoxLayout(self)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("Document", "Linked to", "Anchor page", "Linked by"))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMaximumHeight(170)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.cellDoubleClicked.connect(lambda row, _col: self.open_row(row))
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        self.open_button = QPushButton("Open document")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(lambda: self.open_row(self.table.currentRow()))
        actions.addWidget(self.open_button)
        actions.addStretch()
        hint = QLabel("Links are added and changed in the 📄 Documents tab.")
        hint.setStyleSheet("color: #667085;")
        actions.addWidget(hint)
        layout.addLayout(actions)
        self._show_empty()

    # ------------------------------------------------------------------ data
    def set_well(self, well_id: Optional[int]):
        if self.scope == SCOPE_WELL:
            self.target_id = well_id or None
            self.refresh()

    def set_report(self, report_id: Optional[int]):
        if self.scope == SCOPE_REPORT:
            self.target_id = report_id or None
            self.refresh()

    def refresh(self):
        self.table.setRowCount(0)
        self.links = []
        if self.target_id is None or self.service is None:
            self._show_empty()
            return
        try:
            self.links = (self.service.links_for_well(self.target_id) if self.scope == SCOPE_WELL
                          else self.service.links_for_report(self.target_id))
        except Exception as exc:
            logger.warning("Related documents could not be read: %s", type(exc).__name__)
            self.status_label.setText(f"Linked documents could not be read ({type(exc).__name__}).")
            self.open_button.setEnabled(False)
            return
        self.table.setRowCount(len(self.links))
        for row, link in enumerate(self.links):
            values = (link["file_name"], link_target_text(link),
                      f"page {link['page_no']}" if link["page_no"] else "—", link["linked_by"] or "—")
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, link["id"])
                self.table.setItem(row, column, item)
        noun = "well" if self.scope == SCOPE_WELL else "report"
        if self.links:
            documents = len({link["document_id"] for link in self.links})
            self.status_label.setText(f"{documents} document(s) linked to this {noun} "
                                      f"({len(self.links)} link(s)). Double-click or Open to view the stored text.")
        else:
            self.status_label.setText(f"No documents are linked to this {noun}.")
        self._selection_changed()

    def _show_empty(self):
        noun = "well" if self.scope == SCOPE_WELL else "daily report"
        self.status_label.setText(f"Select a {noun} to see its linked documents.")
        self.open_button.setEnabled(False)

    # ---------------------------------------------------------------- actions
    def _selection_changed(self):
        self.open_button.setEnabled(0 <= self.table.currentRow() < len(self.links))

    def open_row(self, row: int):
        if 0 <= row < len(self.links):
            link = self.links[row]
            self.open_requested.emit(int(link["document_id"]), link["page_no"])
