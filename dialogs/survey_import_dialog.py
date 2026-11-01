"""M55: survey import preview (CSV / TXT / XLSX) with explicit unit and validation.

Shows the detected columns, the depth unit (from the header or chosen by the
user — never assumed), the azimuth reference as stated, every rejected row with
its reason, and the stations that will be imported (MD in metres). Nothing is
written until the user presses Import and then saves in the trajectory tab.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from core.survey_file_import import AZIMUTH_REFERENCES, import_survey_rows, read_table


class SurveyImportDialog(QDialog):
    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = str(path)
        self.setWindowTitle(f"Import surveys — {Path(path).name}")
        self.setMinimumSize(720, 520)
        self.result = None
        self._rows, self._sheet, sheets = [], None, []
        self._read_error = None
        try:
            self._rows, self._sheet, sheets = read_table(self.path)
        except (OSError, ValueError) as exc:
            self._read_error = str(exc)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.sheet_combo = QComboBox()
        self.sheet_combo.addItems(sheets or ["(single table)"])
        self.sheet_combo.setEnabled(bool(sheets))
        self.sheet_combo.currentTextChanged.connect(self._sheet_changed)
        self.unit_combo = QComboBox()
        self.unit_combo.addItem("Not stated — use the file header", None)
        self.unit_combo.addItem("Metres (m)", "m")
        self.unit_combo.addItem("Feet (ft) — converted with 0.3048 m/ft", "ft")
        self.unit_combo.currentIndexChanged.connect(self.refresh)
        self.reference_combo = QComboBox()
        self.reference_combo.addItems(list(AZIMUTH_REFERENCES))
        self.reference_combo.setCurrentText("not stated")
        self.reference_combo.currentIndexChanged.connect(self.refresh)
        form.addRow("Sheet", self.sheet_combo)
        form.addRow("MD unit", self.unit_combo)
        form.addRow("Azimuth reference (as stated, not converted)", self.reference_combo)
        layout.addLayout(form)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.station_table = QTableWidget(0, 4)
        self.station_table.setHorizontalHeaderLabels(["Source row", "MD (m)", "Inc (deg)", "Azi (deg)"])
        self.station_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.station_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.station_table, 2)
        layout.addWidget(QLabel("Rejected rows"))
        self.issue_table = QTableWidget(0, 3)
        self.issue_table.setHorizontalHeaderLabels(["Row", "Field", "Reason"])
        self.issue_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.issue_table.horizontalHeader().setStretchLastSection(True)
        self.issue_table.setMaximumHeight(130)
        layout.addWidget(self.issue_table, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.import_btn = self.buttons.button(QDialogButtonBox.Ok)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.refresh()

    def _sheet_changed(self, name):
        try:
            self._rows, self._sheet, _ = read_table(self.path, name)
        except (OSError, ValueError) as exc:
            self._read_error = str(exc)
        self.refresh()

    def refresh(self, *_args):
        self.station_table.setRowCount(0)
        self.issue_table.setRowCount(0)
        if self._read_error:
            self.result = None
            self.status_label.setText(f"File not read: {self._read_error}")
            self.import_btn.setEnabled(False)
            return
        result = import_survey_rows(self._rows, unit=self.unit_combo.currentData(),
                                    azimuth_reference=self.reference_combo.currentText(), sheet=self._sheet)
        self.result = result
        for station in result.stations:
            row = self.station_table.rowCount()
            self.station_table.insertRow(row)
            for col, value in enumerate((station["source_row"], f"{station['md']:.2f}", f"{station['inc']:.2f}",
                                         f"{station['azi']:.2f}")):
                self.station_table.setItem(row, col, QTableWidgetItem(str(value)))
        for issue in result.issues:
            row = self.issue_table.rowCount()
            self.issue_table.insertRow(row)
            for col, value in enumerate((issue.get("row") or "—", issue.get("field", ""), issue.get("reason", ""))):
                self.issue_table.setItem(row, col, QTableWidgetItem(str(value)))
        if result.error:
            self.status_label.setText(f"Not importable: {result.error}")
        else:
            columns = ", ".join(f"{k.upper()} ← '{v}'" for k, v in result.columns.items())
            self.status_label.setText(
                f"{len(result.stations)} station(s) ready; {len(result.issues)} row(s) rejected. "
                f"Columns: {columns}. MD unit {result.unit} (from {result.unit_source}). "
                f"Azimuth reference: {result.azimuth_reference}."
            )
        self.import_btn.setText(f"Import {len(result.stations)} station(s)")
        self.import_btn.setEnabled(result.ok)
