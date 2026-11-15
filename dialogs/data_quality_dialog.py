"""M227: the read-only Data Quality workspace dialog (Tools > Data Quality Workspace).

Lists :func:`core.data_quality_workspace.collect` for the selected well and opens the source record of the selected
issue through ``navigate`` (the main window's resolver). It edits nothing.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from core import data_quality_workspace as dqw

COLUMNS = ("Severity", "Category", "Report", "Issue", "Source record")


class DataQualityDialog(QDialog):
    def __init__(self, db, well_id: int, parent=None, *, well_label: str = "",
                 navigate: Optional[Callable[[Dict[str, Any]], Any]] = None):
        super().__init__(parent)
        self.db = db
        self.well_id = well_id
        self.navigate = navigate
        self.issues: List[dqw.Issue] = []
        self.shown: List[dqw.Issue] = []
        self.setWindowTitle(f"Data Quality Workspace — {well_label or f'well {well_id}'}")
        self.resize(980, 520)
        layout = QVBoxLayout(self)
        note = QLabel("Read-only: issues are listed, not corrected. Open the source record to fix it where it is "
                      "owned (with the usual checks, audit and permissions).")
        note.setWordWrap(True)
        layout.addWidget(note)
        bar = QHBoxLayout()
        self.category_filter = QComboBox()
        self.category_filter.setObjectName("dq_category_filter")
        self.category_filter.addItem("All categories", None)
        for category in dqw.CATEGORIES:
            self.category_filter.addItem(category, category)
        self.category_filter.currentIndexChanged.connect(self._fill)
        bar.addWidget(self.category_filter)
        self.summary = QLabel()
        self.summary.setObjectName("dq_summary")
        bar.addWidget(self.summary, 1)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        bar.addWidget(self.refresh_button)
        layout.addLayout(bar)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName("dq_table")
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._update)
        self.table.cellDoubleClicked.connect(lambda *_: self.open_selected())
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.open_button = QPushButton("Open source record")
        self.open_button.setObjectName("dq_open_source")
        self.open_button.clicked.connect(self.open_selected)
        buttons.addButton(self.open_button, QDialogButtonBox.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    def refresh(self) -> None:
        self.issues = dqw.collect(self.db, self.well_id)
        self._fill()

    def _fill(self) -> None:
        wanted = self.category_filter.currentData()
        self.shown = [i for i in self.issues if wanted is None or i.category == wanted]
        self.table.setRowCount(len(self.shown))
        for row, issue in enumerate(self.shown):
            for column, text in enumerate((issue.severity, issue.category, issue.report_label, issue.message,
                                           f"{issue.source_table} #{issue.source_id}")):
                cell = QTableWidgetItem(text)
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, column, cell)
        total = dqw.counts(self.issues)
        self.summary.setText("No issues found." if not self.issues else
                             "; ".join(f"{k}: {v}" for k, v in total.items() if v))
        self._update()

    def selected_issue(self) -> Optional[dqw.Issue]:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        return self.shown[rows[0].row()] if rows and rows[0].row() < len(self.shown) else None

    def _update(self) -> None:
        self.open_button.setEnabled(self.navigate is not None and self.selected_issue() is not None)

    def open_selected(self):
        issue = self.selected_issue()
        if issue is None or self.navigate is None:
            return None
        return self.navigate(dict(issue.target))
