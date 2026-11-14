"""M182: build a tubular reference library from a licensed file - draft set, provenance, preview, confirm, publish.

Flow: choose or create a DRAFT set -> choose an XLSX / CSV / JSON file -> state the provenance of the file ->
Preview (every row classified, nothing written) -> give a reason and Confirm import (one transaction with an
audit record) -> Publish the draft when it is complete (it becomes immutable). Every failure says NOT IMPORTED
or NOT PUBLISHED and leaves the library unchanged.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from core.engineering import tubular_import as ti
from core.engineering import tubular_reference as tr


class TubularImportDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.preview: Optional[ti.ImportPreview] = None
        self.last_result: Optional[dict] = None
        self.setWindowTitle("Import tubular reference data")
        layout = QVBoxLayout(self)

        set_row = QHBoxLayout()
        self.set_combo = QComboBox()
        self.new_set_btn = QPushButton("New draft set…")
        self.publish_btn = QPushButton("Publish draft…")
        set_row.addWidget(QLabel("Draft set:"))
        set_row.addWidget(self.set_combo, 1)
        set_row.addWidget(self.new_set_btn)
        set_row.addWidget(self.publish_btn)
        layout.addLayout(set_row)

        file_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("XLSX, CSV or JSON file with canonical headers, e.g. 'Nominal OD (in)'")
        self.browse_btn = QPushButton("Choose file…")
        self.sheet_edit = QLineEdit()
        self.sheet_edit.setPlaceholderText("Sheet (XLSX with several sheets)")
        file_row.addWidget(self.path_edit, 1)
        file_row.addWidget(self.browse_btn)
        file_row.addWidget(self.sheet_edit)
        layout.addLayout(file_row)

        form = QFormLayout()
        self.origin_combo = QComboBox()
        for origin in ("user", "manufacturer"):         # "user" first: manufacturer data needs a stated licence
            self.origin_combo.addItem(origin, origin)
        self.manufacturer_edit, self.document_edit, self.url_edit = QLineEdit(), QLineEdit(), QLineEdit()
        self.revision_edit, self.licence_edit, self.notes_edit = QLineEdit(), QLineEdit(), QLineEdit()
        self.licence_edit.setPlaceholderText("Licence / terms that allow storing these values (required for "
                                             "manufacturer data; a public PDF is not a licence)")
        form.addRow("Origin", self.origin_combo)
        form.addRow("Manufacturer", self.manufacturer_edit)
        form.addRow("Document", self.document_edit)
        form.addRow("URL", self.url_edit)
        form.addRow("Revision", self.revision_edit)
        form.addRow("Licence", self.licence_edit)
        form.addRow("Notes", self.notes_edit)
        layout.addLayout(form)

        self.preview_btn = QPushButton("Preview (nothing is written)")
        layout.addWidget(self.preview_btn)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Row", "Status", "Designation", "Issues"])
        layout.addWidget(self.table)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        confirm_row = QHBoxLayout()
        self.partial_check = QCheckBox("Import the NEW rows although some rows are invalid or conflicting")
        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText("Reason (required)")
        self.import_btn = QPushButton("Confirm import")
        self.import_btn.setEnabled(False)
        confirm_row.addWidget(self.partial_check)
        confirm_row.addWidget(self.reason_edit, 1)
        confirm_row.addWidget(self.import_btn)
        layout.addLayout(confirm_row)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.new_set_btn.clicked.connect(self._new_set_clicked)
        self.publish_btn.clicked.connect(self._publish_clicked)
        self.browse_btn.clicked.connect(self._browse_clicked)
        self.preview_btn.clicked.connect(self._preview_clicked)
        self.import_btn.clicked.connect(self._import_clicked)
        for edit in (self.path_edit, self.sheet_edit, self.manufacturer_edit, self.document_edit, self.url_edit,
                     self.revision_edit, self.licence_edit, self.notes_edit):
            edit.textChanged.connect(self._invalidate)
        self.origin_combo.currentIndexChanged.connect(self._invalidate)
        self.set_combo.currentIndexChanged.connect(self._invalidate)
        self.refresh_sets()

    # ------------------------------------------------------------------------------------------ sets
    def refresh_sets(self, select_id: Optional[int] = None) -> None:
        current = select_id if select_id is not None else self.set_combo.currentData()
        self.set_combo.blockSignals(True)
        self.set_combo.clear()
        for row in tr.list_sets(self.db):
            if row["status"] == tr.DRAFT:
                self.set_combo.addItem(f"{row['name']} v{row['version']} ({row['items']} item(s))", row["id"])
        index = self.set_combo.findData(current)
        self.set_combo.setCurrentIndex(index if index >= 0 else (0 if self.set_combo.count() else -1))
        self.set_combo.blockSignals(False)
        if not self.set_combo.count():
            self.status.setText("No draft set. Create one with 'New draft set…' (a new name, or a revision of a "
                                "published set).")
        self._invalidate()

    def create_draft(self, name: str) -> Optional[dict]:
        try:
            row = tr.create_set(self.db, name.strip())
        except tr.TubularReferenceError as exc:
            self._refuse("New draft set", f"NOT CREATED — {exc}")
            return None
        self.refresh_sets(row["id"])
        self.status.setText(f"Draft {row['name']} v{row['version']} created.")
        return row

    def publish_current(self) -> Optional[dict]:
        set_id = self.set_combo.currentData()
        if set_id is None:
            self._refuse("Publish", "NOT PUBLISHED — no draft set is selected.")
            return None
        try:
            row = tr.publish_set(self.db, set_id)
        except tr.TubularReferenceError as exc:
            self._refuse("Publish", f"NOT PUBLISHED — {exc}")
            return None
        self.refresh_sets()
        self.status.setText(f"Published {row['name']} v{row['version']} (fingerprint {row['fingerprint'][:12]}…); "
                            f"it is now immutable.")
        return row

    # --------------------------------------------------------------------------------------- import
    def provenance(self) -> tr.Provenance:
        def text(edit):
            return edit.text().strip() or None
        return tr.Provenance(origin=self.origin_combo.currentData(), manufacturer=text(self.manufacturer_edit),
                             document=text(self.document_edit), url=text(self.url_edit),
                             revision=text(self.revision_edit), licence=text(self.licence_edit),
                             notes=text(self.notes_edit))

    def run_preview(self) -> Optional[ti.ImportPreview]:
        self.preview = None
        self.import_btn.setEnabled(False)
        set_id, path = self.set_combo.currentData(), self.path_edit.text().strip()
        if set_id is None or not path:
            self.summary.setText("Choose a draft set and a file first.")
            return None
        try:
            preview = ti.preview_file(self.db, set_id, path, self.provenance(),
                                      sheet=self.sheet_edit.text().strip() or None)
        except (ti.TubularImportError, OSError, ValueError) as exc:
            self.table.setRowCount(0)
            self.summary.setText(f"NOT PREVIEWED — {exc}")
            return None
        self.preview = preview
        self.table.setRowCount(len(preview.rows))
        for r, row in enumerate(preview.rows):
            for c, text in enumerate((str(row.row_number), row.status, row.spec.designation if row.spec else "",
                                      "; ".join(row.issues))):
                self.table.setItem(r, c, QTableWidgetItem(text))
        extra = f" Ignored columns: {', '.join(preview.ignored_columns)}." if preview.ignored_columns else ""
        self.summary.setText(f"{preview.summary()} — target {preview.set_label}; file SHA-256 "
                             f"{preview.sha256[:16]}….{extra}")
        self.import_btn.setEnabled(preview.importable)
        return preview

    def confirm_import(self) -> Optional[dict]:
        if self.preview is None:
            self._refuse("Import", "NOT IMPORTED — preview the file first.")
            return None
        try:
            result = ti.apply_import(self.db, self.preview, confirmed=True, reason=self.reason_edit.text(),
                                     accept_partial=self.partial_check.isChecked())
        except ti.TubularImportError as exc:
            self._refuse("Import", f"NOT IMPORTED — {exc}")
            return None
        self.last_result = result
        self.preview = None
        self.import_btn.setEnabled(False)
        self.refresh_sets(result["set_id"])
        self.status.setText(f"Imported {result['imported']} row(s) into draft {result['set']}. Publish the draft "
                            f"to make it citable.")
        return result

    # -------------------------------------------------------------------------------------- helpers
    def _invalidate(self, *_):
        if self.preview is not None:
            self.preview = None
            self.summary.setText("Inputs changed — preview again before importing.")
        self.import_btn.setEnabled(False)

    def _refuse(self, title: str, message: str) -> None:
        self.status.setText(message)
        QMessageBox.warning(self, title, message)

    def _new_set_clicked(self, _checked=False):
        name, ok = QInputDialog.getText(self, "New draft set", "Library name (an existing name starts a revision):")
        if ok and name.strip():
            self.create_draft(name)
        else:
            self.status.setText("Cancelled — NOT CREATED.")

    def _publish_clicked(self, _checked=False):
        answer = QMessageBox.question(self, "Publish draft", "Publish the selected draft? A published set can "
                                      "never change; corrections need a new revision.")
        if answer == QMessageBox.Yes:
            self.publish_current()
        else:
            self.status.setText("Cancelled — NOT PUBLISHED.")

    def _browse_clicked(self, _checked=False):
        path, _filter = QFileDialog.getOpenFileName(self, "Tubular reference file", "",
                                                    "Reference data (*.xlsx *.xlsm *.csv *.json)")
        if path:
            self.path_edit.setText(path)

    def _preview_clicked(self, _checked=False):
        self.run_preview()

    def _import_clicked(self, _checked=False):
        self.confirm_import()
