"""M302: read-only lineage of one imported DDR value (``core.import_value_lineage``).

Shows the identity, the check outcome with its reason, the expected value and where it comes from, the value
stored now, the five stages (source -> parsed -> normalized -> correction -> accepted), every correction and
every later typed change. Read-only by construction: the dialog receives an already-built lineage dictionary,
has no input widget, no edit trigger and no save action, and never touches the database.

Entry points: the Import review dialog ("🧬 Lineage…", one selected review item) and the W2 value-states dialog
("🧬 Lineage…", the selected header field of an imported report).
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

CHECK_TEXT = {
    "MATCH": "MATCH: the stored value is still the accepted value",
    "CHANGED_SINCE": "CHANGED SINCE ACCEPTANCE: the stored value differs from the accepted value",
    "NOT_CHECKED": "NOT CHECKED",
    "UNREADABLE": "UNREADABLE",
    "NOT_APPLICABLE": "NOT APPLICABLE: no value was accepted",
}


def _show(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    return str(value)


def _table(name: str, headers, rows) -> QTableWidget:
    table = QTableWidget(len(rows), len(headers))
    table.setObjectName(name)
    table.setHorizontalHeaderLabels(list(headers))
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.horizontalHeader().setStretchLastSection(True)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem(_show(value))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)          # never editable
            table.setItem(r, c, item)
    return table


class ValueLineageDialog(QDialog):
    def __init__(self, lineage: Dict[str, Any], parent=None, *, title: str = ""):
        super().__init__(parent)
        self.lineage = lineage
        self.setObjectName("value_lineage_dialog")
        self.setWindowTitle(title or f"Value lineage – {lineage.get('target_field') or ''}")
        self.resize(900, 560)
        layout = QVBoxLayout(self)
        check = str(lineage.get("check") or "")
        reason = lineage.get("reason") or ""
        self.check_label = QLabel(f"<b>{CHECK_TEXT.get(check, check)}</b>" + (f" – {reason}" if reason else ""))
        self.check_label.setObjectName("value_lineage_check")
        self.check_label.setWordWrap(True)
        layout.addWidget(self.check_label)
        summary = [("Field", lineage.get("target_field")), ("Identity", lineage.get("identity")),
                   ("Expected value", lineage.get("expected")), ("Expected from", lineage.get("expected_basis")),
                   ("Stored now", lineage.get("stored_now"))]
        if lineage.get("review_item_id"):
            summary.append(("Review item", lineage["review_item_id"]))
        self.summary = _table("value_lineage_summary", ["", "Value"], summary)
        layout.addWidget(self.summary)
        stages = lineage.get("stages") or []
        self.stages = _table("value_lineage_stages", ["Stage", "Status", "Detail"],
                             [(s.get("stage"), s.get("status"), s.get("detail")) for s in stages])
        layout.addWidget(QLabel("Stages (source → parsed → normalized → correction → accepted)"))
        layout.addWidget(self.stages, 1)
        corrections = []
        for stage in stages:
            if stage.get("stage") == "CORRECTION":
                corrections = (stage.get("detail") or {}).get("corrections") or []
        self.corrections = _table("value_lineage_corrections", ["Old", "New", "Unit", "Reason", "By", "At"],
                                  [(c.get("old"), c.get("new"), c.get("unit"), c.get("reason"), c.get("by"),
                                    c.get("at")) for c in corrections])
        layout.addWidget(QLabel(f"Corrections ({len(corrections)})"))
        layout.addWidget(self.corrections)
        later = lineage.get("later_changes") or []
        self.later = _table("value_lineage_later", ["At", "By", "Details"],
                            [(c.get("at"), c.get("by"), c.get("details")) for c in later])
        layout.addWidget(QLabel(f"Later typed changes ({len(later)})"))
        layout.addWidget(self.later)
        note = QLabel("Read-only: nothing here changes stored data. Corrections are made in the Import review queue.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def for_review_item(db, item_id: int, well_id: int, parent=None) -> ValueLineageDialog:
    from core import import_value_lineage as ivl
    return ValueLineageDialog(ivl.value_lineage(db, item_id, well_id), parent)


def for_imported_value(db, report_id: int, field: str, parent=None) -> ValueLineageDialog:
    from core import import_value_lineage as ivl
    return ValueLineageDialog(ivl.imported_value_lineage(db, report_id, field), parent)


def open_non_blocking(dialog: Optional[ValueLineageDialog]) -> Optional[ValueLineageDialog]:
    """Show ``dialog`` window-modal without blocking the caller (the caller keeps the reference)."""
    if dialog is not None:
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.open()
    return dialog
