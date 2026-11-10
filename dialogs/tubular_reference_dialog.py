"""M159: search and filter the tubular reference library; return an immutable snapshot of the chosen item.

Missing values are shown as "unavailable" - never 0. Provenance (origin, manufacturer, document, revision,
page, units, licence, file fingerprint) is shown for the selected row. ``selected_snapshot`` is set only for an
item of a PUBLISHED set version (a draft can still change, so it cannot be cited by a calculation).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from core.engineering import tubular_reference as tr

COLUMNS = [("component_type", "Type"), ("designation", "Designation"), ("nominal_od_in", "OD (in)"),
           ("id_in", "ID (in)"), ("weight_ppf", "Weight (lb/ft)"), ("grade", "Grade"), ("connection", "Connection"),
           ("origin", "Origin"), ("set", "Library version")]


class TubularReferenceDialog(QDialog):
    def __init__(self, db, parent=None, *, component_type: Optional[str] = None):
        super().__init__(parent)
        self.db = db
        self.rows: List[Dict[str, Any]] = []
        self.selected_snapshot: Optional[Dict[str, Any]] = None
        self.setWindowTitle("Tubular reference library")
        layout = QVBoxLayout(self)

        filters = QHBoxLayout()
        self.type_combo = QComboBox()
        self.type_combo.addItem("All types", None)
        for code in tr.COMPONENT_TYPES:
            self.type_combo.addItem(tr.COMPONENT_LABELS[code], code)
        if component_type in tr.COMPONENT_TYPES:
            self.type_combo.setCurrentIndex(tr.COMPONENT_TYPES.index(component_type) + 1)
        self.origin_combo = QComboBox()
        self.origin_combo.addItem("All origins", None)
        for origin in tr.ORIGINS:
            self.origin_combo.addItem(origin, origin)
        self.od_edit = QLineEdit()
        self.od_edit.setPlaceholderText("OD (in)")
        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText("Designation, grade, connection, manufacturer...")
        self.drafts_check = QCheckBox("Include drafts")
        for widget in (QLabel("Type"), self.type_combo, QLabel("Origin"), self.origin_combo, self.od_edit,
                       self.text_edit, self.drafts_check):
            filters.addWidget(widget)
        layout.addLayout(filters)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([label for _, label in COLUMNS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(170)
        layout.addWidget(self.detail)
        self.status = QLabel()
        layout.addWidget(self.status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Use selected item")
        self.buttons.accepted.connect(self._use_selected)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        for signal in (self.type_combo.currentIndexChanged, self.origin_combo.currentIndexChanged,
                       self.drafts_check.toggled):
            signal.connect(self.reload)
        self.od_edit.editingFinished.connect(self.reload)
        self.text_edit.textChanged.connect(self.reload)
        self.table.itemSelectionChanged.connect(self._show_detail)
        self.reload()

    def _od_filter(self) -> Optional[float]:
        text = self.od_edit.text().strip().replace(",", ".")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            self.status.setText(f"OD filter {text!r} is not a number; ignored")
            return None

    def reload(self, *_):
        self.rows = tr.search(self.db, component_type=self.type_combo.currentData(), text=self.text_edit.text(),
                              od_in=self._od_filter(), origin=self.origin_combo.currentData(),
                              published_only=not self.drafts_check.isChecked())
        self.table.setRowCount(len(self.rows))
        for r, row in enumerate(self.rows):
            spec = row["spec"]
            for c, (key, _label) in enumerate(COLUMNS):
                if key == "origin":
                    text = spec.provenance.origin
                elif key == "set":
                    text = f"{row['set_name']} v{row['set_version']} ({row['set_status']})"
                elif key in tr.ENGINEERING_FIELDS:
                    text = spec.display_value(key)
                else:
                    value = getattr(spec, key)
                    text = tr.UNAVAILABLE if value in (None, "") else str(value)
                self.table.setItem(r, c, QTableWidgetItem(text))
        if not self.rows:
            self.status.setText("No reference items match. The application ships no pipe data; build a library "
                                "from documents you are licensed to use.")
        else:
            self.status.setText(f"{len(self.rows)} item(s)")
        self.detail.clear()

    def _current(self) -> Optional[Dict[str, Any]]:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        return self.rows[rows[0].row()] if rows else None

    def _show_detail(self):
        row = self._current()
        if row is None:
            self.detail.clear()
            return
        spec = row["spec"]
        prov = spec.provenance
        lines = [f"{tr.COMPONENT_LABELS.get(spec.component_type, spec.component_type)}: {spec.designation}"]
        for name, (label, unit) in tr.ENGINEERING_FIELDS.items():
            lines.append(f"  {label}: {spec.display_value(name)}" + ("" if getattr(spec, name) is None else f" {unit}"))
        lines.append("Provenance:")
        for name in ("origin", "manufacturer", "document", "url", "revision", "page", "units", "licence",
                     "file_fingerprint", "derived_from", "entered_by", "notes"):
            value = getattr(prov, name)
            lines.append(f"  {name}: {tr.UNAVAILABLE if value in (None, '') else value}")
        lines.append(f"Item fingerprint: {row['fingerprint']}")
        self.detail.setPlainText("\n".join(lines))

    def _use_selected(self):
        row = self._current()
        if row is None:
            self.status.setText("Select an item first")
            return
        try:
            self.selected_snapshot = tr.reference_snapshot(row)
        except tr.TubularReferenceError as exc:
            self.status.setText(str(exc))
            return
        self.accept()
