"""M306: read-only side-by-side view of a cloned calculation case and its source.

A clone is a copy of stored inputs and stored results, not a rerun. The view shows the clone's provenance (M304),
then every input and result field of the clone next to the same field of the source with SAME / DIFFERENT /
ONLY IN CLONE / ONLY IN SOURCE. Nothing is recalculated and nothing is written.
"""
from __future__ import annotations

import json
from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from core import calculation_clone_contract as ccc


def _show(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    return str(value)


def _fill(table: QTableWidget, rows) -> None:
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem(_show(value))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            table.setItem(r, c, item)


class CloneComparisonDialog(QDialog):
    def __init__(self, comparison: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.comparison = comparison
        self.setObjectName("clone_comparison_dialog")
        self.setWindowTitle("Clone vs source (copy, not a rerun)")
        self.resize(960, 600)
        layout = QVBoxLayout(self)
        provenance = comparison["provenance"]
        self.provenance_label = QLabel(ccc.provenance_line(provenance))
        self.provenance_label.setWordWrap(True)
        layout.addWidget(self.provenance_label)
        self.status_label = QLabel(f"<b>{comparison.get('status', '')}</b> – {comparison['statement']}")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.meta = QTableWidget(0, 3)
        self.meta.setHorizontalHeaderLabels(["", "Clone", "Source"])
        _fill(self.meta, comparison.get("meta") or [])
        self.fields = QTableWidget(0, 5)
        self.fields.setHorizontalHeaderLabels(["Section", "Field", "Clone", "Source", "Status"])
        _fill(self.fields, [(r["section"], r["key"], r["clone"], r["source"], r["status"])
                            for r in comparison.get("rows") or []])
        for table in (self.meta, self.fields):
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.meta)
        layout.addWidget(self.fields, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
