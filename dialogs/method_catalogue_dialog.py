"""Help › Method Catalogue (M92): read-only view of ``core.method_catalogue``.

Filter by text, family and status; the details pane shows every field of the selected method and how many
stored W13 cases in the open database (and for the selected well) were produced with it. There is no
approve, edit or delete action: approval comes only from the owner's record in the source.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
                               QTextBrowser, QVBoxLayout)

from sqlalchemy.exc import SQLAlchemyError

from core import method_catalogue as mc

logger = logging.getLogger(__name__)

SHOWN = ("Method ID", "Title", "Family", "Status", "Label", "Version", "Approval")
ALL = "All"


class MethodCatalogueDialog(QDialog):
    def __init__(self, db=None, well_id: Optional[int] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Method Catalogue")
        self.setLayoutDirection(Qt.LeftToRight)
        self.resize(1100, 640)
        self.db, self.well_id = db, well_id
        self.entries: List[mc.CatalogueEntry] = mc.catalogue()
        self.shown: List[mc.CatalogueEntry] = []
        self.counts_db, self.counts_well = {}, {}
        if db is not None:
            try:
                self.counts_db = mc.usage(db)
                self.counts_well = mc.usage(db, well_id) if well_id else {}
            except SQLAlchemyError as exc:  # usage is informative; the catalogue stays usable without it
                logger.warning("method catalogue usage unavailable: %s", exc)
                self.counts_db = None

        layout = QVBoxLayout(self)
        intro = QLabel(f"{len(self.entries)} methods from the engine, contract, specialist and workflow registries "
                       f"({mc.CATALOGUE_VERSION}). Approval comes only from the owner's record in the source; this "
                       "window cannot approve a method. UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search id, title, reference, limits…")
        self.family = QComboBox()
        self.family.addItems([ALL] + sorted({e.family for e in self.entries}))
        self.status = QComboBox()
        self.status.addItems([ALL] + [s for s in mc.STATUSES if any(e.status == s for e in self.entries)])
        self.export_btn = QPushButton("Export CSV…")
        self.export_btn.clicked.connect(self._export_clicked)
        for widget in (QLabel("Search:"), self.search, QLabel("Family:"), self.family, QLabel("Status:"),
                       self.status, self.export_btn):
            filters.addWidget(widget)
        layout.addLayout(filters)
        splitter = QSplitter(Qt.Vertical)
        self.table = QTableWidget(0, len(SHOWN))
        self.table.setHorizontalHeaderLabels(list(SHOWN))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemSelectionChanged.connect(self._show_details)
        self.details = QTextBrowser()
        splitter.addWidget(self.table)
        splitter.addWidget(self.details)
        layout.addWidget(splitter, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.search.textChanged.connect(lambda _t: self.apply_filter())
        self.family.currentTextChanged.connect(lambda _t: self.apply_filter())
        self.status.currentTextChanged.connect(lambda _t: self.apply_filter())
        self.apply_filter()

    def apply_filter(self) -> int:
        text = self.search.text().strip().lower()
        family, status = self.family.currentText(), self.status.currentText()
        self.shown = [e for e in self.entries
                      if (family == ALL or e.family == family) and (status == ALL or e.status == status)
                      and (not text or text in " ".join(e.row()).lower())]
        self.table.setRowCount(len(self.shown))
        index = {name: i for i, name in enumerate(mc.COLUMNS)}
        for r, entry in enumerate(self.shown):
            row = entry.row()
            for c, name in enumerate(SHOWN):
                self.table.setItem(r, c, QTableWidgetItem(row[index[name]]))
        self.details.setPlainText(f"{len(self.shown)} of {len(self.entries)} methods shown.")
        return len(self.shown)

    def selected(self) -> Optional[mc.CatalogueEntry]:
        rows = self.table.selectionModel().selectedRows()
        return self.shown[rows[0].row()] if rows else None

    def usage_text(self, entry: mc.CatalogueEntry) -> str:
        if self.counts_db is None:
            return "unavailable (database could not be read)"
        if self.db is None:
            return "no database open"
        total = mc.usage_for(entry, self.counts_db)
        if total is None:
            return "not a W13 case method (see Calc History for engine runs)"
        text = f"{total} stored case(s) in this database"
        if self.well_id:
            text += f", {mc.usage_for(entry, self.counts_well)} for the selected well"
        return text

    def _show_details(self) -> None:
        entry = self.selected()
        if entry is None:
            return
        lines = [f"{name}: {value}" for name, value in zip(mc.COLUMNS, entry.row())]
        lines.append(f"Stored use: {self.usage_text(entry)}")
        self.details.setPlainText("\n".join(lines))

    def export(self, path: str) -> int:
        return mc.export_csv(path, self.shown)

    def _export_clicked(self, _checked=False):
        path, _ = QFileDialog.getSaveFileName(self, "Export method catalogue", "method_catalogue.csv", "CSV (*.csv)")
        if path:
            self.details.setPlainText(f"Exported {self.export(path)} method(s) to {path}")
