"""M151: review workspace for the persisted DDR import review queue of one well.

Lists every queued review item (continuations, deferred field proposals, rows the import could not store) with
its state, source location, original text, proposed value and - for a continuation - the parent activity it
would join. Filters: state, type, sheet and free text. Several rows can be selected and decided at once:

* Attach continuation  - only eligible continuations whose parent still exists (checked again per row);
* Reject / Ignore      - closes the item; canonical report data are not changed;
* Keep for review      - leaves the item open (the deferred state).

* Correct value…       - M173: a deferred scalar is edited, validated against its canonical field, previewed and
                         saved only after an explicit confirmation (``core.review_scalar_correction``); no
                         re-import is needed. The original extracted text is never changed.
* Reopen…              - M173: a decided item is reopened with a reason; its decision history is kept.

Every decision is applied and audited by ``DatabaseManager.resolve_import_review_item`` or
``core.review_scalar_correction`` (corrections and reopening).
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from core.ddr_continuation import (
    ACCEPTED, DEFERRED_UNRESOLVED, IGNORED, REJECTED, REVIEW_STATES, SAFELY_ATTACHED_CONTINUATION,
    VALIDATION_ERROR,
)
from core.review_scalar_correction import CorrectionRefused, apply_correction, preview_correction, reopen_item

logger = logging.getLogger(__name__)

PENDING = "Pending (deferred + validation errors)"
ALL = "All"
COLUMNS = ("Report date", "State", "Type", "Sheet", "Row", "Original text", "Proposed value", "Parent activity",
           "Reason")


def _text(value) -> str:
    return "" if value is None else str(value)


def proposed_value(item: Dict) -> str:
    payload = item.get("payload") or {}
    value = payload.get("normalized_value", payload.get("value"))
    return "" if item.get("review_type") == "continuation" else _text(value)


def parent_text(item: Dict) -> str:
    parent = item.get("parent")
    if not parent:
        return "—" if item.get("review_type") == "continuation" else ""
    span = f"{_text(parent.get('time_from'))[:5] or '?'}-{_text(parent.get('time_to'))[:5] or '?'}"
    return f"{span} {_text(parent.get('description'))[:160]}"


def matches(item: Dict, *, state: str = PENDING, review_type: str = ALL, sheet: str = ALL, text: str = "") -> bool:
    """Filter predicate shared by the table and the tests."""
    if state == PENDING and item.get("state") not in (DEFERRED_UNRESOLVED, VALIDATION_ERROR):
        return False
    if state not in (PENDING, ALL) and item.get("state") != state:
        return False
    if review_type != ALL and item.get("review_type") != review_type:
        return False
    if sheet != ALL and _text(item.get("source_sheet")) != sheet:
        return False
    needle = text.strip().lower()
    if needle:
        haystack = " ".join(_text(item.get(k)) for k in ("original_text", "reason", "target_field", "source_file"))
        if needle not in (haystack + " " + parent_text(item)).lower():
            return False
    return True


class ImportReviewDialog(QDialog):
    """Queue of one well; ``db`` is a ``DatabaseManager``."""

    def __init__(self, db, well_id: int, parent=None, report_id: Optional[int] = None):
        super().__init__(parent)
        self.db = db
        self.well_id = well_id
        self.report_id = report_id
        self.items: List[Dict] = []
        self.visible: List[Dict] = []
        self.setWindowTitle("Import Review Queue")
        self.setMinimumSize(1100, 600)
        layout = QVBoxLayout(self)
        self.summary = QLabel()
        layout.addWidget(self.summary)

        filters = QHBoxLayout()
        self.state_filter = QComboBox()
        self.state_filter.addItems([PENDING, ALL, *REVIEW_STATES])
        self.type_filter = QComboBox()
        self.sheet_filter = QComboBox()
        self.text_filter = QLineEdit()
        self.text_filter.setPlaceholderText("Search text, reason, field or file")
        for label, widget in (("State", self.state_filter), ("Type", self.type_filter),
                              ("Sheet", self.sheet_filter), ("Search", self.text_filter)):
            filters.addWidget(QLabel(label))
            filters.addWidget(widget)
        layout.addLayout(filters)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        self.detail = QLabel("Select a row to see its source, original text and parent activity.")
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.detail)

        actions = QHBoxLayout()
        self.attach_btn = QPushButton("🔗 Attach continuation")
        self.attach_all_btn = QPushButton("🔗 Attach all eligible (shown)")
        self.reject_btn = QPushButton("✖ Reject")
        self.ignore_btn = QPushButton("🚫 Ignore")
        self.correct_btn = QPushButton("✏ Correct value…")
        self.reopen_btn = QPushButton("↺ Reopen…")
        close_btn = QPushButton("Close")
        for button in (self.attach_btn, self.attach_all_btn, self.reject_btn, self.ignore_btn, self.correct_btn,
                       self.reopen_btn):
            actions.addWidget(button)
        actions.addStretch()
        actions.addWidget(close_btn)
        layout.addLayout(actions)
        self.attach_btn.clicked.connect(lambda: self._decide_selected("ATTACH_CONTINUATION"))
        self.attach_all_btn.clicked.connect(self._attach_all_visible)
        self.reject_btn.clicked.connect(lambda: self._decide_selected("REJECT"))
        self.ignore_btn.clicked.connect(lambda: self._decide_selected("IGNORED"))
        self.correct_btn.clicked.connect(self._correct_selected)
        self.reopen_btn.clicked.connect(self._reopen_selected)
        close_btn.clicked.connect(self.accept)
        for combo in (self.state_filter, self.type_filter, self.sheet_filter):
            combo.currentIndexChanged.connect(self.populate)
        self.text_filter.textChanged.connect(self.populate)
        self.table.itemSelectionChanged.connect(self._show_detail)
        self.reload()

    # ---- data ----------------------------------------------------------------------------------------------
    def reload(self) -> None:
        self.items = self.db.get_import_review_items(self.well_id, report_id=self.report_id)
        for combo, key in ((self.type_filter, "review_type"), (self.sheet_filter, "source_sheet")):
            current = combo.currentText() or ALL
            combo.blockSignals(True)
            combo.clear()
            combo.addItems([ALL, *sorted({_text(item.get(key)) for item in self.items if item.get(key)})])
            index = combo.findText(current)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)
        self.populate()

    def populate(self, *_args) -> None:
        keep = {item["id"] for item in self.selected_items()} if self.table.rowCount() else set()
        self.visible = [item for item in self.items
                        if matches(item, state=self.state_filter.currentText(),
                                   review_type=self.type_filter.currentText() or ALL,
                                   sheet=self.sheet_filter.currentText() or ALL, text=self.text_filter.text())]
        self.table.setRowCount(0)
        for item in self.visible:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = (_text(item.get("report_date")), item.get("state"), item.get("review_type"),
                      _text(item.get("source_sheet")), _text(item.get("source_row")),
                      _text(item.get("original_text"))[:200], proposed_value(item)[:100], parent_text(item),
                      _text(item.get("reason"))[:200])
            for column, value in enumerate(values):
                cell = QTableWidgetItem(_text(value))
                cell.setData(Qt.UserRole, item["id"])
                self.table.setItem(row, column, cell)
        # The selection survives a reload (e.g. after a partly refused batch) for the rows still shown.
        model = self.table.selectionModel()
        for row, item in enumerate(self.visible):
            if item["id"] in keep:
                model.select(self.table.model().index(row, 0),
                             QItemSelectionModel.Select | QItemSelectionModel.Rows)
        pending = sum(1 for item in self.items if item.get("state") in (DEFERRED_UNRESOLVED, VALIDATION_ERROR))
        attached = sum(1 for item in self.items if item.get("state") == SAFELY_ATTACHED_CONTINUATION)
        self.summary.setText(f"{len(self.items)} queued item(s): {pending} pending, {attached} attached; "
                             f"{len(self.visible)} shown.")

    def selected_items(self) -> List[Dict]:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        return [self.visible[row] for row in rows if 0 <= row < len(self.visible)]

    def _show_detail(self) -> None:
        selected = self.selected_items()
        if len(selected) != 1:
            self.detail.setText(f"{len(selected)} rows selected." if selected else "")
            return
        item = selected[0]
        lines = [f"Source: {item.get('source_file') or '—'} / {item.get('source_sheet') or '—'}"
                 f" / page {item.get('source_page') or '—'} / row {item.get('source_row') or '—'}",
                 f"Original: {item.get('original_text') or '—'}",
                 f"Proposed (normalized): {proposed_value(item) or '—'}",
                 f"Target: {item.get('target_field') or '—'}  |  State: {item.get('state')}",
                 f"Reason: {item.get('reason') or '—'}"]
        if item.get("review_type") == "continuation":
            lines.append(f"Parent activity: {parent_text(item)}")
            lines.append("Attachable: yes" if item.get("eligible") and item.get("parent")
                         else "Attachable: no (no provable parent in the saved report)")
        if item.get("resolved_at"):
            lines.append(f"Decided {item['resolved_at']} by {item.get('resolved_by') or 'unknown'}")
        for entry in item.get("decision_history") or ():
            change = (f" {entry.get('old')!r} → {entry.get('new')!r}" if entry.get("action") == "CORRECTED" else "")
            lines.append(f"History: {entry.get('at', '?')} {entry.get('action')}{change} "
                         f"({entry.get('before_state')} → {entry.get('after_state')}) by {entry.get('by') or '?'}"
                         + (f" - {entry.get('reason') or entry.get('note')}" if entry.get('reason') or
                            entry.get('note') else ""))
        self.detail.setText("\n".join(lines))

    # ---- decisions -----------------------------------------------------------------------------------------
    def decide(self, items: List[Dict], decision: str) -> Dict[str, int]:
        """Apply ``decision`` to ``items``; returns counts of applied and refused rows (no dialog shown)."""
        applied, refused, messages = 0, 0, []
        for item in items:
            try:
                self.db.resolve_import_review_item(item["id"], self.well_id, decision)
                applied += 1
            except (ValueError, PermissionError) as exc:
                refused += 1
                messages.append(str(exc))
        self.last_messages = messages
        self.reload()
        return {"applied": applied, "refused": refused}

    def _report(self, decision: str, counts: Dict[str, int]) -> None:
        text = f"{counts['applied']} item(s) decided ({decision})."
        if counts["refused"]:
            text += f"\n{counts['refused']} item(s) unchanged: " + "; ".join(sorted(set(self.last_messages)))[:600]
        QMessageBox.information(self, "Import review", text)

    def _decide_selected(self, decision: str) -> None:
        selected = self.selected_items()
        if not selected:
            QMessageBox.information(self, "Import review", "Select one or more rows first.")
            return
        self._report(decision, self.decide(selected, decision))

    def eligible_visible(self) -> List[Dict]:
        return [item for item in self.visible
                if item.get("review_type") == "continuation" and item.get("eligible") and item.get("parent")
                and item.get("state") == DEFERRED_UNRESOLVED]

    def _attach_all_visible(self) -> None:
        eligible = self.eligible_visible()
        if not eligible:
            QMessageBox.information(self, "Import review", "No shown continuation has a provable parent.")
            return
        self._report("ATTACH_CONTINUATION", self.decide(eligible, "ATTACH_CONTINUATION"))

    # ---- M173: correct a deferred scalar / reopen a decided item -------------------------------------------
    def correctable(self, item: Dict) -> bool:
        return (item.get("review_type") != "continuation" and bool(item.get("target_field"))
                and item.get("state") in (DEFERRED_UNRESOLVED, VALIDATION_ERROR))

    def _single(self) -> Optional[Dict]:
        selected = self.selected_items()
        if len(selected) != 1:
            QMessageBox.information(self, "Import review", "Select exactly one row.")
            return None
        return selected[0]

    def _correct_selected(self) -> None:
        item = self._single()
        if item is None:
            return
        if not self.correctable(item):
            QMessageBox.information(self, "Import review", "Only a pending scalar review item can be corrected.")
            return
        dialog = ScalarCorrectionDialog(self.db, self.well_id, item, self)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()
        self.reload()

    def reopen(self, item: Dict, reason: str) -> Dict:
        result = reopen_item(self.db, item["id"], self.well_id, reason)
        self.reload()
        return result

    def _reopen_selected(self) -> None:
        item = self._single()
        if item is None:
            return
        if item.get("state") not in (ACCEPTED, REJECTED, IGNORED):
            QMessageBox.information(self, "Import review", "Only an accepted, rejected or ignored item can be "
                                    "reopened.")
            return
        reason, ok = QInputDialog.getText(self, "Reopen review item", "Reason (kept in the decision history):")
        if not ok:
            return
        try:
            self.reopen(item, reason)
        except (CorrectionRefused, ValueError) as exc:
            QMessageBox.warning(self, "Import review", f"NOT UPDATED: {exc}")


class ScalarCorrectionDialog(QDialog):
    """M173: edit -> validate/preview -> confirm -> save one deferred scalar (no re-import)."""

    def __init__(self, db, well_id: int, item: Dict, parent=None):
        super().__init__(parent)
        self.db, self.well_id, self.item = db, well_id, item
        self.preview: Optional[Dict] = None
        self.result: Optional[Dict] = None
        self.setWindowTitle("Correct review value")
        layout = QVBoxLayout(self)
        payload = item.get("payload") or {}
        info = QFormLayout()
        info.addRow("Target field:", QLabel(_text(item.get("target_field"))))
        info.addRow("Source:", QLabel(f"{_text(item.get('source_file'))} / {_text(item.get('source_sheet'))} / "
                                      f"cell {_text(payload.get('source_cell')) or '—'}"))
        info.addRow("Original extracted value:", QLabel(_text(item.get("original_text")) or "—"))
        info.addRow("Proposed normalized value:", QLabel(proposed_value(item) or "— (none)"))
        info.addRow("Source unit:", QLabel(_text(payload.get("original_unit") or payload.get("unit")) or "—"))
        layout.addLayout(info)
        edit = QFormLayout()
        self.value_edit = QLineEdit()
        self.unit_edit = QLineEdit()
        self.unit_edit.setPlaceholderText("blank = canonical unit")
        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText("required, kept in the audit")
        edit.addRow("Corrected value:", self.value_edit)
        edit.addRow("Unit of the entered value:", self.unit_edit)
        edit.addRow("Reason:", self.reason_edit)
        layout.addLayout(edit)
        self.preview_label = QLabel("Validate the value to see the change.")
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)
        self.confirm_box = QCheckBox("I confirm this changes the canonical report data")
        layout.addWidget(self.confirm_box)
        buttons = QHBoxLayout()
        self.validate_btn = QPushButton("Validate / preview")
        self.save_btn = QPushButton("Save correction")
        cancel = QPushButton("Cancel")
        for button in (self.validate_btn, self.save_btn, cancel):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.validate_btn.clicked.connect(self.validate)
        self.save_btn.clicked.connect(self.save)
        cancel.clicked.connect(self.reject)
        for widget in (self.value_edit, self.unit_edit):
            widget.textChanged.connect(self._invalidate)
        for signal in (self.reason_edit.textChanged, self.confirm_box.toggled):
            signal.connect(self._refresh)
        self._refresh()

    def _invalidate(self, *_args) -> None:
        self.preview = None
        self.confirm_box.setChecked(False)
        self.preview_label.setText("Validate the value to see the change.")
        self._refresh()

    def _refresh(self, *_args) -> None:
        ready = bool(self.preview and not self.preview.get("conflict") and self.confirm_box.isChecked()
                     and self.reason_edit.text().strip())
        self.save_btn.setEnabled(ready)
        self.confirm_box.setEnabled(bool(self.preview and not self.preview.get("conflict")))

    def validate(self) -> Optional[Dict]:
        try:
            self.preview = preview_correction(self.db, self.item["id"], self.well_id, self.value_edit.text(),
                                              self.unit_edit.text().strip() or None)
        except (CorrectionRefused, ValueError) as exc:
            self.preview = None
            self.preview_label.setText(f"Not valid - nothing will be saved: {exc}")
            self._refresh()
            return None
        p = self.preview
        target = p["target"]
        text = (f"{target['model']} #{target['record_id']} . {target['column']} ({p['quantity']}, canonical unit "
                f"{p['canonical_unit'] or '—'}): current {p['current_value']!r} → new {p['new_value']!r}")
        if p.get("factor_applied"):
            text += f" (converted from {p['entered_value']} {p['entered_unit']})"
        if p["conflict"]:
            text += (f"\nCONFLICT: the field holds {p['current_value']!r}, expected {p['expected_value']!r} "
                     f"({p['expected_basis']}); the correction cannot be saved.")
        self.preview_label.setText(text)
        self._refresh()
        return p

    def save(self) -> Optional[Dict]:
        if not self.preview:
            return None
        try:
            self.result = apply_correction(self.db, self.item["id"], self.well_id, self.value_edit.text(),
                                           reason=self.reason_edit.text(), token=self.preview["token"],
                                           confirmed=self.confirm_box.isChecked(),
                                           unit=self.unit_edit.text().strip() or None)
        except (CorrectionRefused, ValueError, PermissionError) as exc:
            self.result = None
            self.preview_label.setText(f"NOT SAVED: {exc}")
            self.preview = None
            self._refresh()
            return None
        self.preview_label.setText(f"Saved: {self.result['old']!r} → {self.result['new']!r}")
        self.accept()
        return self.result
