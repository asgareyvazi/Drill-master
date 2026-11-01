"""M54: editor for versioned DDR report profiles.

Every save creates a new immutable version; nothing is overwritten. Aliases
can only target canonical fields, and a header preview shows exactly how a
header row would map (profile alias, canonical alias, or unmapped/review).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.ddr_report_profiles import (
    FORMATS,
    KNOWN_SOURCE_UNITS,
    ReportProfile,
    list_latest_profiles,
    map_headers,
    profile_history,
    save_profile_version,
    validate_profile,
)
from core.permissions import require_permission

logger = logging.getLogger(__name__)


def _split(text: str, sep: str) -> list[str]:
    return [part.strip() for part in str(text or "").split(sep) if part.strip()]


class ReportProfileDialog(QDialog):
    def __init__(self, db_manager, parent=None, user_id=None):
        super().__init__(parent)
        self.db = db_manager
        self.user_id = user_id
        self.setWindowTitle("DDR report profiles")
        self.setMinimumSize(980, 620)
        self._current_key = None
        from core.canonical_schema import FIELD_SPECS
        self._fields = sorted(FIELD_SPECS)

        root = QHBoxLayout(self)
        left = QVBoxLayout()
        left.addWidget(QLabel("Profiles (latest version)"))
        self.profile_list = QListWidget()
        self.profile_list.currentItemChanged.connect(self._profile_selected)
        left.addWidget(self.profile_list, 1)
        self.new_btn = QPushButton("New profile")
        self.new_btn.clicked.connect(self.new_profile)
        left.addWidget(self.new_btn)
        self.history_label = QLabel("")
        self.history_label.setWordWrap(True)
        left.addWidget(self.history_label)
        root.addLayout(left, 1)

        right = QVBoxLayout()
        form = QFormLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("unique key, e.g. operator-a-pdf")
        self.name_edit = QLineEdit()
        self.operator_edit = QLineEdit()
        self.format_combo = QComboBox()
        self.format_combo.addItems(list(FORMATS))
        self.date_formats_edit = QLineEdit("%Y-%m-%d")
        self.date_formats_edit.setToolTip("Comma-separated strftime patterns, tried in order, e.g. %d/%m/%Y, %Y-%m-%d")
        self.confidence_spin = QDoubleSpinBox()
        self.confidence_spin.setRange(0.0, 1.0)
        self.confidence_spin.setSingleStep(0.05)
        self.confidence_spin.setValue(0.8)
        self.continuation_check = QCheckBox("Join tables continued on the next page")
        self.continuation_check.setChecked(True)
        self.stop_markers_edit = QLineEdit()
        self.stop_markers_edit.setToolTip("Semicolon-separated text that ends a table (e.g. Total; Remarks)")
        self.skip_rows_edit = QLineEdit()
        self.skip_rows_edit.setToolTip("Semicolon-separated text; matching rows are ignored and listed for review")
        self.skip_tables_edit = QLineEdit()
        self.skip_tables_edit.setToolTip("Semicolon-separated text; tables whose name/headers match are ignored and listed")
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("What changed in this version")
        for label, widget in (("Key", self.key_edit), ("Name", self.name_edit), ("Operator", self.operator_edit),
                              ("Format", self.format_combo), ("Date formats", self.date_formats_edit),
                              ("Review below confidence", self.confidence_spin), ("Continuation", self.continuation_check),
                              ("Table stop markers", self.stop_markers_edit),
                              ("Skip rows containing", self.skip_rows_edit),
                              ("Skip tables containing", self.skip_tables_edit), ("Version note", self.note_edit)):
            form.addRow(label, widget)
        right.addLayout(form)

        right.addWidget(QLabel("Header aliases (source label → canonical field)"))
        self.alias_table = self._table(["Source label", "Canonical field"])
        right.addWidget(self.alias_table)
        alias_buttons = QHBoxLayout()
        self.add_alias_btn = QPushButton("Add alias")
        self.add_alias_btn.clicked.connect(lambda: self.add_alias_row())
        self.remove_alias_btn = QPushButton("Remove alias")
        self.remove_alias_btn.clicked.connect(lambda: self._remove_row(self.alias_table))
        alias_buttons.addWidget(self.add_alias_btn)
        alias_buttons.addWidget(self.remove_alias_btn)
        alias_buttons.addStretch(1)
        right.addLayout(alias_buttons)

        right.addWidget(QLabel("Source units (canonical field → unit used by this report)"))
        self.unit_table = self._table(["Canonical field", "Source unit"])
        self.unit_table.setMaximumHeight(110)
        right.addWidget(self.unit_table)
        unit_buttons = QHBoxLayout()
        self.add_unit_btn = QPushButton("Add unit rule")
        self.add_unit_btn.clicked.connect(lambda: self.add_unit_row())
        self.remove_unit_btn = QPushButton("Remove unit rule")
        self.remove_unit_btn.clicked.connect(lambda: self._remove_row(self.unit_table))
        unit_buttons.addWidget(self.add_unit_btn)
        unit_buttons.addWidget(self.remove_unit_btn)
        unit_buttons.addStretch(1)
        right.addLayout(unit_buttons)

        preview_row = QHBoxLayout()
        self.headers_edit = QLineEdit()
        self.headers_edit.setPlaceholderText("Test a header row: From | To | Hrs | Code | Activity")
        self.preview_btn = QPushButton("Preview mapping")
        self.preview_btn.clicked.connect(self.preview_mapping)
        preview_row.addWidget(self.headers_edit, 1)
        preview_row.addWidget(self.preview_btn)
        right.addLayout(preview_row)
        self.preview_table = self._table(["Header", "Canonical field", "Mapped by", "Source unit"])
        self.preview_table.setMaximumHeight(130)
        right.addWidget(self.preview_table)

        self.message_label = QLabel("")
        self.message_label.setWordWrap(True)
        right.addWidget(self.message_label)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.save_btn = QPushButton("Save as new version")
        self.save_btn.clicked.connect(self.save_version)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(self.save_btn)
        bottom.addWidget(close_btn)
        right.addLayout(bottom)
        root.addLayout(right, 3)
        self.refresh_profiles()

    def show_warning(self, text):
        """Used by ``require_permission`` when the save is not allowed."""
        self.message_label.setText(f"Not saved: {text}")

    # -- helpers ---------------------------------------------------------------
    @staticmethod
    def _table(headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        return table

    @staticmethod
    def _remove_row(table):
        row = table.currentRow()
        if row >= 0:
            table.removeRow(row)

    def _field_combo(self, value=""):
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(self._fields)
        combo.setCurrentText(value)
        return combo

    def add_alias_row(self, source="", target=""):
        row = self.alias_table.rowCount()
        self.alias_table.insertRow(row)
        self.alias_table.setItem(row, 0, QTableWidgetItem(source))
        self.alias_table.setCellWidget(row, 1, self._field_combo(target))

    def add_unit_row(self, target="", unit=""):
        row = self.unit_table.rowCount()
        self.unit_table.insertRow(row)
        self.unit_table.setCellWidget(row, 0, self._field_combo(target))
        combo = QComboBox()
        combo.addItems(list(KNOWN_SOURCE_UNITS))
        if unit:
            combo.setCurrentText(unit)
        self.unit_table.setCellWidget(row, 1, combo)

    # -- data ------------------------------------------------------------------
    def refresh_profiles(self, select_key=None):
        self.profile_list.clear()
        try:
            profiles = list_latest_profiles(self.db)
        except Exception as exc:
            logger.error("Report profiles could not be listed: %s", exc)
            self.message_label.setText("Report profiles could not be loaded — see the log.")
            return
        for profile in profiles:
            item = QListWidgetItem(f"{profile.label()} — {profile.operator or 'no operator'}")
            item.setData(Qt.UserRole, profile)
            self.profile_list.addItem(item)
            if profile.key == select_key:
                self.profile_list.setCurrentItem(item)
        if not profiles:
            self.message_label.setText("No report profiles yet. Create one with New profile.")

    def _profile_selected(self, item, _previous=None):
        profile = item.data(Qt.UserRole) if item is not None else None
        if profile is not None:
            self.load_profile(profile)

    def new_profile(self):
        self.load_profile(None)

    def load_profile(self, profile):
        self._current_key = profile.key if profile else None
        self.key_edit.setReadOnly(profile is not None)
        self.key_edit.setText(profile.key if profile else "")
        self.name_edit.setText(profile.name if profile else "")
        self.operator_edit.setText(profile.operator if profile else "")
        self.format_combo.setCurrentText(profile.report_format if profile else "any")
        self.date_formats_edit.setText(", ".join(profile.date_formats) if profile else "%Y-%m-%d")
        self.confidence_spin.setValue(profile.confidence_threshold if profile else 0.8)
        self.continuation_check.setChecked(profile.continuation if profile else True)
        rules = profile.table_rules if profile else {}
        self.stop_markers_edit.setText("; ".join(rules.get("stop_markers", [])))
        self.skip_rows_edit.setText("; ".join(rules.get("skip_rows_containing", [])))
        self.skip_tables_edit.setText("; ".join(rules.get("skip_tables_containing", [])))
        self.note_edit.clear()
        self.alias_table.setRowCount(0)
        self.unit_table.setRowCount(0)
        for source, target in (profile.aliases if profile else {}).items():
            self.add_alias_row(source, target)
        for target, unit in (profile.units if profile else {}).items():
            self.add_unit_row(target, unit)
        if profile is not None:
            history = profile_history(self.db, profile.key)
            self.history_label.setText(
                "Versions: " + ", ".join(f"v{h['version']}" + (f" ({h['note']})" if h["note"] else "") for h in history)
            )
        else:
            self.history_label.setText("New profile — the first save creates version 1.")
        self.message_label.clear()

    def collect_profile(self) -> ReportProfile:
        aliases = {}
        for row in range(self.alias_table.rowCount()):
            item = self.alias_table.item(row, 0)
            combo = self.alias_table.cellWidget(row, 1)
            source = item.text().strip() if item else ""
            if source or (combo and combo.currentText().strip()):
                aliases[source] = combo.currentText().strip() if combo else ""
        units = {}
        for row in range(self.unit_table.rowCount()):
            field_combo, unit_combo = self.unit_table.cellWidget(row, 0), self.unit_table.cellWidget(row, 1)
            if field_combo and field_combo.currentText().strip():
                units[field_combo.currentText().strip()] = unit_combo.currentText() if unit_combo else ""
        return ReportProfile(
            key=self.key_edit.text().strip(), version=0, name=self.name_edit.text().strip(),
            operator=self.operator_edit.text().strip(), report_format=self.format_combo.currentText(),
            aliases=aliases, units=units, date_formats=tuple(_split(self.date_formats_edit.text(), ",")),
            table_rules={
                name: values for name, values in (
                    ("stop_markers", _split(self.stop_markers_edit.text(), ";")),
                    ("skip_rows_containing", _split(self.skip_rows_edit.text(), ";")),
                    ("skip_tables_containing", _split(self.skip_tables_edit.text(), ";")),
                ) if values or name == "stop_markers"
            },
            continuation=self.continuation_check.isChecked(),
            confidence_threshold=float(self.confidence_spin.value()), note=self.note_edit.text().strip(),
        )

    def preview_mapping(self):
        headers = _split(self.headers_edit.text(), "|")
        rows = map_headers(self.collect_profile(), headers)
        self.preview_table.setRowCount(0)
        for result in rows:
            row = self.preview_table.rowCount()
            self.preview_table.insertRow(row)
            for col, key in enumerate(("header", "field", "method", "unit")):
                self.preview_table.setItem(row, col, QTableWidgetItem(str(result[key] or "—")))
        return rows

    @require_permission("can_import")
    def save_version(self):
        profile = self.collect_profile()
        errors = validate_profile(profile)
        if errors:
            self.message_label.setText("Not saved:\n• " + "\n• ".join(errors))
            return None
        try:
            stored = save_profile_version(self.db, profile, user_id=self.user_id, note=profile.note)
        except Exception as exc:
            logger.error("Report profile save failed: %s", exc)
            self.message_label.setText(f"Not saved: {exc}")
            return None
        self.message_label.setText(f"Saved {stored.label()}. Earlier versions are kept unchanged.")
        self.refresh_profiles(select_key=stored.key)
        return stored
