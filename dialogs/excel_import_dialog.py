# dialogs/excel_import_dialog.py
"""
Excel Import Dialog v2.1 - Professional Intelligence Platform

P0 Requirements:
- Import Transaction واقعی: Begin Transaction ... Commit / Rollback All
- Import Preview قبل از ذخیره: File, Sheet/Page, Detected Table, Source Cell, Original Value, Normalized Value, Unit, Target Field, Confidence, Decision
  Buttons: Accept All High Confidence, Review Medium, Reject Low Confidence, Edit Mapping, Edit Value, Edit Unit, Ignore Column, Confirm Import, Cancel Import
  No data before Confirm Import
- Universal Import برای همه شرکت‌ها: no dependency on OEOC/DDR Remark names, universal aliases
- Batch: فایل‌های موفق و ناموفق جدا گزارش

Architecture:
Excel → structural analysis → merged-cell detection → region detection → header detection → parameter candidate extraction → deterministic rules → confidence scoring → AI only for ambiguous → validation → normalized engineering data → Preview → User Confirmation → Database (atomic)
"""

import os
import re
import json
import logging
from datetime import date as dt_date, time as dt_time, datetime as dt_datetime
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QFileDialog, QComboBox, QLineEdit, QMessageBox,
    QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QWidget, QSplitter, QProgressBar, QApplication,
    QInputDialog, QDialogButtonBox,
)
from PySide6.QtCore import Signal, Qt, QTimer, QDir
from PySide6.QtGui import QColor

from core.text_utils import wrap_text
from core.import_quality import ImportValidator, find_duplicates, TimeLogValidator, decision_for_confidence
from core.import_diagnostics import (
    PersistenceIssue, PersistenceError, ImportStatus, determine_import_status,
)
from core.import_quality import ReviewItem
from core.ai_import_mapper import AIImportMapper, model_catalog, get_selected_model, set_selected_model
from core.async_workers import FunctionWorker
from core.import_router import route_file
from core.mineru_engine import (
    DocumentNormalizer,
    MinerUAdapter,
    MinerUError,
    MinerUNormalizationError,
    MinerUParseResult,
    parse_pdf_native_fallback,
)
from core.unit_manager import UnitManager
from dialogs.smart_template_dialog import ValueNormalizer, FIELD_LABELS

from core.ddr_import_service import DDRImportService, _canonical_review_row, _enrich_record_reviews

logger = logging.getLogger(__name__)

ALL_EXPECTED_FIELDS = list(FIELD_LABELS.keys())


def has_meaningful_canonical_data(extracted: dict) -> bool:
    """Return true only for semantic canonical values, not provenance metadata."""
    ignored = {"metadata", "provenance", "review_matrix", "raw_document"}

    def business_key(key: object) -> bool:
        key = str(key or "")
        return not (
            key.startswith("_")
            or key.endswith("_source")
            or key in {"source_row", "source_cells", "report_date_source"}
        )

    def meaningful(value, *, key: object = ""):
        if not business_key(key):
            return False
        if value is None or value is False:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (int, float)):
            return True
        if isinstance(value, dict):
            return any(
                meaningful(item, key=item_key)
                for item_key, item in value.items()
                if item_key not in ignored
            )
        if isinstance(value, (list, tuple, set)):
            return any(meaningful(item) for item in value)
        return True

    return isinstance(extracted, dict) and any(
        meaningful(value, key=key)
        for key, value in extracted.items()
        if key not in ignored
    )





# Universal aliases as per spec
UNIVERSAL_ALIASES = {
    "well_info.name": ["well", "well name", "well number", "well id", "نام چاه", "well designation", "well_name"],
    "well_info.report_date": ["report date", "date", "report_date"],
    "daily_report.depth_2400": ["md", "measured depth", "bit depth", "current depth", "depth", "depth @ 24:00", "td"],
    "drilling_params.wob_max": ["wob", "wt. on bit", "bit load", "weight on bit", "w.o.b"],
    "drilling_params.rpm_max": ["rotary", "rotary speed", "surface rpm", "rpm", "rotary speed"],
    "mud_report.mw": ["mud weight", "mw", "mud wt", "density", "1.50 sg", "sg"],
}


class ImportPreviewDialog(QDialog):
    """Professional Import Preview before saving - as per spec.

    Columns: File, Sheet/Page, Detected Table, Source Cell, Original Value, Normalized Value, Unit, Target Field, Confidence, Decision
    Buttons: Accept All High Confidence, Review Medium, Reject Low Confidence, Edit Mapping, Edit Value, Edit Unit, Ignore Column, Confirm Import, Cancel Import
    """

    def __init__(self, file_path: str, extracted: dict, import_report: dict, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.extracted = extracted
        self.import_report = import_report
        self.confirmed = False
        self.setWindowTitle(f"Import Preview - {Path(file_path).name}")
        self.setMinimumSize(1100, 650)
        self.setModal(True)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel(f"📋 Import Preview: {Path(self.file_path).name} - No data saved yet")
        header.setStyleSheet("font-size: 13px; font-weight: bold; color: #2c3e50; padding: 8px; background: #ecf0f1; border-radius: 4px;")
        layout.addWidget(header)

        # Summary
        report = self.import_report or {}
        source_summary = ""
        if report.get("source_engine") == "MinerU":
            source_summary = (
                f" | Source: MinerU | Backend: {report.get('backend', '')}"
                f" | Method: {report.get('method', '')} | Pages: {report.get('pages', 0)}"
                f" | Tables: {report.get('tables', 0)} | Fields: {report.get('fields_extracted', 0)}"
            )
        summary = QLabel(
            f"Total: {report.get('total',0)} | Errors: {report.get('errors',0)} | Warnings: {report.get('warnings',0)} | "
            f"Review items: {len(report.get('review',[]))} | "
            f"TimeLogs: {len(self.extracted.get('time_logs_24h',[]))} | Surveys: {len(self.extracted.get('surveys',[]))}"
            f"{source_summary}"
        )
        summary.setStyleSheet("color: #555; padding: 4px;")
        layout.addWidget(summary)

        # Table
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(
            ["File", "Sheet/Page", "Detected Table", "Source Cell", "Original Value", "Normalized Value", "Unit", "Target Field", "Confidence", "Decision"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)

        # Keep the serialized rows tied to their UI rows so edits and
        # decisions reach the canonical payload, not just the visual table.
        self._row_payloads = []
        for item in report.get("review", []):
            row = self.table.rowCount()
            self.table.insertRow(row)
            file_name = Path(self.file_path).name
            values = [
                file_name,
                item.get("sheet", item.get("file", "")),
                item.get("detected_table", item.get("record_type", "")),
                item.get("source_cell", f"{item.get('column','')}{item.get('row','')}"),
                str(item.get("original_value", item.get("source_value", "")))[:100],
                str(item.get("normalized_value", item.get("value", "")))[:100],
                item.get("unit", ""),
                item.get("target_field", item.get("canonical_field", "")),
                f"{float(item.get('confidence',0)):.0%}" if item.get("confidence") not in (None, "") else "",
                item.get("decision", "REVIEW"),
            ]
            for col, val in enumerate(values):
                it = QTableWidgetItem(str(val))
                # Color by confidence
                conf = item.get("confidence", 0)
                try:
                    conf_f = float(conf)
                    if conf_f >= 0.95:
                        it.setBackground(QColor("#d5f5e3"))
                    elif conf_f >= 0.70:
                        it.setBackground(QColor("#fef9e7"))
                    else:
                        it.setBackground(QColor("#fadbd8"))
                except Exception:
                    pass
                self.table.setItem(row, col, it)
            if self.table.item(row, 0) is not None:
                self.table.item(row, 0).setData(Qt.UserRole, item)
            self._row_payloads.append(item)

        # Add issues as rows too
        for issue in report.get("issues", [])[:30]:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                Path(self.file_path).name,
                issue.get("sheet", ""),
                "Validation",
                f"Row {issue.get('row','')}",
                str(issue.get("value", ""))[:80],
                "",
                "",
                issue.get("field", ""),
                "",
                issue.get("level", "error").upper(),
            ]
            for col, val in enumerate(values):
                it = QTableWidgetItem(str(val))
                it.setBackground(QColor("#fadbd8"))
                self.table.setItem(row, col, it)
            self._row_payloads.append(None)

        self.table.resizeColumnsToContents()
        layout.addWidget(self.table, 1)

        # Action buttons as per spec
        btn_layout = QHBoxLayout()

        accept_high_btn = QPushButton("✅ Accept All High Confidence")
        accept_high_btn.setToolTip("Accept all items with confidence >=95%")
        accept_high_btn.clicked.connect(self._accept_high)
        btn_layout.addWidget(accept_high_btn)

        review_medium_btn = QPushButton("🟡 Review Medium")
        review_medium_btn.setToolTip("Focus on medium confidence 70-95%")
        review_medium_btn.clicked.connect(self._filter_medium)
        btn_layout.addWidget(review_medium_btn)

        reject_low_btn = QPushButton("🔴 Reject Low Confidence")
        reject_low_btn.setToolTip("Reject all items with confidence <70%")
        reject_low_btn.clicked.connect(self._reject_low)
        btn_layout.addWidget(reject_low_btn)

        edit_mapping_btn = QPushButton("✏️ Edit Mapping")
        edit_mapping_btn.clicked.connect(self._edit_mapping)
        btn_layout.addWidget(edit_mapping_btn)

        edit_value_btn = QPushButton("✏️ Edit Value")
        edit_value_btn.clicked.connect(self._edit_value)
        btn_layout.addWidget(edit_value_btn)

        edit_unit_btn = QPushButton("📏 Edit Unit")
        edit_unit_btn.clicked.connect(self._edit_unit)
        btn_layout.addWidget(edit_unit_btn)

        ignore_col_btn = QPushButton("🚫 Ignore Column")
        ignore_col_btn.clicked.connect(self._ignore_column)
        btn_layout.addWidget(ignore_col_btn)

        layout.addLayout(btn_layout)

        # Confirm / Cancel
        confirm_layout = QHBoxLayout()
        confirm_layout.addStretch()

        cancel_btn = QPushButton("❌ Cancel Import")
        cancel_btn.setStyleSheet("background: #e74c3c; color: white; padding: 8px 16px; font-weight: bold; border-radius: 4px;")
        cancel_btn.clicked.connect(self.reject)
        confirm_layout.addWidget(cancel_btn)

        self.confirm_btn = QPushButton("✅ Confirm Import")
        self.confirm_btn.setStyleSheet("background: #27ae60; color: white; padding: 10px 20px; font-weight: bold; border-radius: 4px; font-size: 13px;")
        self.confirm_btn.clicked.connect(self._confirm)
        confirm_layout.addWidget(self.confirm_btn)

        layout.addLayout(confirm_layout)

    def _accept_high(self):
        for row in range(self.table.rowCount()):
            conf_item = self.table.item(row, 8)
            if not conf_item:
                continue
            try:
                conf_str = conf_item.text().replace("%", "")
                conf = float(conf_str) / 100 if conf_str else 0
                if conf >= 0.95:
                    self._set_decision(row, "ACCEPT")
            except Exception:
                pass

    def _payload_for_row(self, row: int):
        item = self.table.item(row, 0)
        payload = item.data(Qt.UserRole) if item is not None else None
        if isinstance(payload, dict):
            return payload
        return self._row_payloads[row] if 0 <= row < len(self._row_payloads) else None

    def _set_decision(self, row: int, decision: str) -> None:
        self.table.setItem(row, 9, QTableWidgetItem(decision))
        payload = self._payload_for_row(row)
        if payload is not None:

            payload["decision"] = decision
            payload["review_state"] = (
                "accepted" if decision in {"ACCEPT", "CONFIRMED"}
                else "rejected" if decision in {"REJECT", "IGNORED"}
                else "unreviewed"
            )

    def _filter_medium(self):
        for row in range(self.table.rowCount()):
            conf_item = self.table.item(row, 8)
            if not conf_item:
                continue
            try:
                conf_str = conf_item.text().replace("%", "")
                conf = float(conf_str) / 100 if conf_str else 0
                show = 0.70 <= conf < 0.95
                self.table.setRowHidden(row, not show)
            except Exception:
                self.table.setRowHidden(row, True)

    def _reject_low(self):
        for row in range(self.table.rowCount()):
            conf_item = self.table.item(row, 8)
            if not conf_item:
                continue
            try:
                conf_str = conf_item.text().replace("%", "")
                conf = float(conf_str) / 100 if conf_str else 0
                if conf < 0.70:
                    self._set_decision(row, "REJECT")
            except Exception:
                pass

    def _edit_mapping(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No selection", "Select a row first")
            return
        current = self.table.item(row, 7).text() if self.table.item(row, 7) else ""
        new_field, ok = QInputDialog.getText(self, "Edit Mapping", f"Target field (current: {current}):", text=current)
        if ok and new_field:
            self.table.setItem(row, 7, QTableWidgetItem(new_field))
            payload = self._payload_for_row(row)
            if payload is not None:
                payload["target_field"] = new_field
                payload["canonical_field"] = new_field
            self._set_decision(row, "CONFIRMED")

    def _edit_value(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No selection", "Select a row first")
            return
        current = self.table.item(row, 5).text() if self.table.item(row, 5) else ""
        new_val, ok = QInputDialog.getText(self, "Edit Value", "Normalized value:", text=current)
        if ok:
            self.table.setItem(row, 5, QTableWidgetItem(new_val))
            payload = self._payload_for_row(row)
            if payload is not None:
                payload["normalized_value"] = new_val
                payload["value"] = new_val
                payload["proposed_value"] = new_val
            self._set_decision(row, "CONFIRMED")

    def _edit_unit(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No selection", "Select a row first")
            return
        current = self.table.item(row, 6).text() if self.table.item(row, 6) else ""
        new_unit, ok = QInputDialog.getText(self, "Edit Unit", "Unit:", text=current)
        if ok:
            self.table.setItem(row, 6, QTableWidgetItem(new_unit))
            payload = self._payload_for_row(row)
            if payload is not None:
                payload["unit"] = new_unit
            self._set_decision(row, "CONFIRMED")
            # Try to re-normalize with UnitManager
            try:
                orig_item = self.table.item(row, 4)
                orig_val = orig_item.text() if orig_item else ""
                target_field = self.table.item(row, 7).text() if self.table.item(row, 7) else ""
                # Detect quantity from field
                quantity = "text"
                if "depth" in target_field or "md" in target_field:
                    quantity = "depth"
                elif "mw" in target_field or "density" in target_field:
                    quantity = "density"
                elif "pressure" in target_field:
                    quantity = "pressure"
                # Attempt conversion
                num_val, src_unit = UnitManager.detect_unit(orig_val)
                if num_val is None:
                    try:
                        num_val = float(orig_val)
                        src_unit = current
                    except Exception:
                        num_val = None
                if num_val is not None:
                    converted = UnitManager.convert(num_val, quantity, src_unit or current, new_unit)
                    if converted is not None:
                        self.table.setItem(row, 5, QTableWidgetItem(str(converted)))
                        payload = self._payload_for_row(row)
                        if payload is not None:
                            payload["normalized_value"] = converted
                            payload["value"] = converted
                            payload["proposed_value"] = converted
            except Exception as exc:
                logger.debug(f"Unit re-normalize failed: {exc}")

    def _ignore_column(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No selection", "Select a row first")
            return
        self._set_decision(row, "IGNORED")

    def _confirm(self):
        # Check if any critical errors remain
        report = self.import_report or {}
        if report.get("errors", 0) > 0:
            reply = QMessageBox.warning(
                self,
                "Validation Errors",
                f"There are {report.get('errors')} errors. Confirm anyway?\n\nNo partial report will be kept if later steps fail (atomic rollback).",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        self.confirmed = True
        self.accept()

    def get_decisions(self) -> Dict[int, str]:
        """Return decisions and synchronize every edited ReviewItem row."""
        decisions = {}
        for row in range(self.table.rowCount()):
            dec_item = self.table.item(row, 9)
            decision = dec_item.text() if dec_item else "REVIEW"
            decisions[row] = decision
            payload = self._payload_for_row(row)
            if payload is None:
                continue
            payload["decision"] = decision
            payload["target_field"] = self.table.item(row, 7).text() if self.table.item(row, 7) else payload.get("target_field", "")
            payload["canonical_field"] = payload.get("target_field", payload.get("canonical_field", ""))
            payload["unit"] = self.table.item(row, 6).text() if self.table.item(row, 6) else payload.get("unit", "")
            normalized = self.table.item(row, 5).text() if self.table.item(row, 5) else ""
            payload["normalized_value"] = normalized
            payload["value"] = normalized
            payload["proposed_value"] = normalized
            payload["review_state"] = (
                "accepted" if decision in {"ACCEPT", "CONFIRMED"}
                else "rejected" if decision in {"REJECT", "IGNORED"}
                else "unreviewed"
            )
        return decisions

    def apply_review_changes(self, extracted: dict) -> dict:
        """Apply confirmed scalar edits/rejections to the canonical payload.

        Row-oriented edits remain in the review export for manual handling;
        scalar canonical fields can be safely applied by their dotted path.
        """
        self.get_decisions()
        for payload in self._row_payloads:
            if not payload:
                continue
            field_path = payload.get("target_field") or payload.get("canonical_field") or ""
            if "." not in field_path:
                continue
            section, key = field_path.split(".", 1)
            section_data = extracted.setdefault(section, {})
            decision = str(payload.get("decision", "REVIEW")).upper()
            if decision in {"REJECT", "IGNORED"}:
                section_data.pop(key, None)
                section_data.pop(f"{key}_source", None)
                continue
            if decision not in {"ACCEPT", "CONFIRMED"}:
                continue
            normalized = payload.get("normalized_value", payload.get("value"))
            # Empty UI text is not a value.  Keep the original canonical state
            # rather than inventing an empty string.
            if normalized not in (None, ""):
                section_data[key] = normalized
        return extracted


class ExcelImportDialog(QDialog, DDRImportService):
    """
    Main entry point for Excel Import - Professional version
    """

    import_completed = Signal(list)

    def __init__(self, db_manager, well_id: int, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.well_id = well_id
        self._mineru_worker = None
        self._pending_import_files = []
        self._mineru_results = {}
        self.setWindowTitle("📊 Universal Import - Intelligence Platform")
        self.setMinimumSize(600, 500)
        self.setModal(True)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        header = QLabel("📊 Universal Import - Excel Intelligence + MinerU")
        header.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #2c3e50; "
            "padding: 10px; background: #ecf0f1; border-radius: 5px;"
        )
        layout.addWidget(header)

        import_group = QGroupBox("🚀 Universal Import - All Companies")
        il = QVBoxLayout(import_group)
        il.addWidget(QLabel(
            "Select one or more Excel/PDF/CSV reports. System will:\n"
            "• Scan workbook structure (sheets, merged ranges, hidden rows, formulas, table count)\n"
            "• Classify sheets (Daily Report, Mud, BHA, Bit, Survey, Safety, Logistics, etc.)\n"
            "• Detect tables with Row/Column Density, Blank Row/Column, Header Pattern, Data Type Consistency\n"
            "• Use deterministic rules + confidence scoring, AI only for ambiguous cases\n"
            "• Show professional preview (File, Sheet, Table, Cell, Original, Normalized, Unit, Target, Confidence, Decision)\n"
            "• Atomic transaction: Begin → Well/Project/Section/Report/Mud/Drilling/TimeLogs/Bit/BHA/Survey/Equipment/Logistics/Safety/Services/Cost → Commit/Rollback\n"
            "• No data saved before Confirm Import"
        ))
        ai_row = QHBoxLayout()
        ai_row.addWidget(QLabel("AI model:"))
        self.ai_model_combo = QComboBox()
        installed = set(AIImportMapper().installed_models())
        entries = list(model_catalog())
        known = {entry.get("model", entry.get("name", "")) for entry in entries}
        entries.extend({"model": model, "label": model, "description": "Installed Ollama model"} for model in installed if model not in known)
        for entry in entries:
            model = entry.get("model", entry.get("name", ""))
            mark = "✓" if model in installed else "—"
            self.ai_model_combo.addItem(f"{mark} {entry.get('label', model)}", model)
        selected = os.getenv("DRILLMASTER_AI_MODEL", "") or get_selected_model() or (sorted(installed)[0] if installed else "")
        selected_index = self.ai_model_combo.findData(selected)
        if selected_index >= 0:
            self.ai_model_combo.setCurrentIndex(selected_index)
            set_selected_model(selected)
            os.environ["DRILLMASTER_AI_MODEL"] = selected
        self.ai_model_combo.currentIndexChanged.connect(self._select_ai_model)
        ai_row.addWidget(self.ai_model_combo, 1)
        il.addLayout(ai_row)

        import_btn = QPushButton("📥 Import Report(s) - With Preview")
        import_btn.setStyleSheet(
            "background: #27ae60; color: white; padding: 14px; "
            "font-weight: bold; border-radius: 5px; font-size: 14px;"
        )
        import_btn.clicked.connect(self._unified_import)
        il.addWidget(import_btn)

        self.import_status = QLabel("No file selected - Preview before save enabled (P0)")
        self.import_status.setStyleSheet("color: #2c3e50; font-weight: bold;")
        il.addWidget(self.import_status)

        self.batch_summary = QTextEdit()
        self.batch_summary.setReadOnly(True)
        self.batch_summary.setMaximumHeight(120)
        self.batch_summary.setPlaceholderText("Batch results will appear here: successful vs failed files")
        il.addWidget(self.batch_summary)

        layout.addWidget(import_group)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

    def _select_ai_model(self, index):
        model = self.ai_model_combo.itemData(index) if hasattr(self, "ai_model_combo") else None
        if model:
            os.environ["DRILLMASTER_AI_MODEL"] = model
            os.environ["DRILLMASTER_AI_IMPORT"] = "1"
            set_selected_model(model)

    def _unified_import(self):
        """Route imports without running MinerU in the Qt UI thread."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Report(s)",
            "",
            "Reports (*.xlsx *.xls *.xlsm *.csv *.pdf *.docx *.pptx *.png *.jpg *.jpeg *.webp *.tif *.tiff)",
        )
        if not files:
            return

        self._pending_import_files = list(files)
        self._mineru_results = {}
        mineru_sources = []
        for source in files:
            route = route_file(source, template_matcher=self._auto_match_template)
            if route.engine == "mineru":
                mineru_sources.append(source)

        if mineru_sources:
            self.import_status.setText(
                f"Detecting document engine... Using MinerU for {len(mineru_sources)} file(s): "
                "parsing layout, text, and tables..."
            )
            QApplication.processEvents()
            self._mineru_worker = FunctionWorker(
                self._parse_mineru_batch,
                mineru_sources,
                parent=self,
            )
            self._mineru_worker.result_ready.connect(self._on_mineru_batch_ready)
            self._mineru_worker.failed.connect(self._on_mineru_batch_failed)
            self._mineru_worker.start()
            return

        self._run_import_pipeline(files, {})

    @staticmethod
    def _parse_mineru_batch(sources):
        """Worker entry point; no Qt or database objects are used here."""
        return MinerUAdapter().parse_batch(sources)

    @staticmethod
    def _result_key(source):
        try:
            return str(Path(source).expanduser().resolve())
        except OSError:
            return str(source)

    def _on_mineru_batch_ready(self, parse_results):
        self._mineru_results = {
            self._result_key(result.source_file): result
            for result in parse_results
            if isinstance(result, MinerUParseResult)
        }
        if self._mineru_worker is not None:
            self._mineru_worker.deleteLater()
            self._mineru_worker = None
        self._run_import_pipeline(self._pending_import_files, self._mineru_results)

    def _on_mineru_batch_failed(self, error):
        logger.error("MinerU worker failed: %s", error)
        if self._mineru_worker is not None:
            self._mineru_worker.deleteLater()
            self._mineru_worker = None
        # PDF still has the existing explicit fallback. XLSX still has the
        # existing smart/template path. Other MinerU-only formats receive an
        # actionable per-file failure in _run_import_pipeline.
        self._run_import_pipeline(self._pending_import_files, {})

    def _mineru_extracted(self, source, parse_result, *, source_label="MinerU", fallback_diagnostics=None):
        """Return canonical data and review metadata for a successful parse."""
        if not parse_result or not parse_result.success or parse_result.document is None:
            raise MinerUError(parse_result.error if parse_result else "MinerU produced no result")
        normalized = DocumentNormalizer().normalize(parse_result.document)
        if not normalized.validation.valid:
            raise MinerUNormalizationError(
                "MinerU output failed canonical schema validation: "
                + "; ".join(item.get("message", "invalid value") for item in normalized.validation.errors)
            )
        extracted = dict(normalized.canonical_data)
        review_rows = []
        for warning in normalized.warnings:
            source_details = warning.get("source") if isinstance(warning.get("source"), dict) else {}
            location = " ".join(
                part for part in (
                    f"page {source_details.get('source_page')}" if source_details.get("source_page") is not None else "",
                    f"row {source_details.get('source_row')}" if source_details.get("source_row") is not None else "",
                    f"column {source_details.get('source_column')}" if source_details.get("source_column") is not None else "",
                ) if part
            )
            review_rows.append(
                {
                    "file": Path(source).name,
                    "sheet": source_details.get("source_sheet", ""),
                    "page": source_details.get("source_page"),
                    "row": source_details.get("source_row", 0) or 0,
                    "column": source_details.get("source_column", ""),
                    "detected_table": "MinerU document",
                    "source_table": source_details.get("source_table", ""),
                    "source_cell": location,
                    "coordinates": source_details.get("bounding_box"),
                    "extraction_method": source_details.get("extraction_method", ""),
                    "original_value": warning.get("value", ""),
                    "normalized_value": warning.get("normalized_value"),
                    "value": warning.get("normalized_value"),
                    "target_field": warning.get("field", ""),
                    "canonical_field": warning.get("field", ""),
                    "expected_type": warning.get("expected_type", ""),
                    "confidence": source_details.get("confidence"),
                    "decision": "REVIEW",
                    "status": "REVIEW_REQUIRED",
                    "validation_state": "needs_review",
                    "review_state": "unreviewed",
                    "reason": warning.get("message", "Review required"),
                    "mapping_method": "MinerU document normalization",
                }
            )
        review_rows = [_canonical_review_row(item) for item in review_rows]
        extracted["metadata"] = {
            "source": source_label,
            "source_engine": source_label,
            "backend": parse_result.document.backend,
            "method": parse_result.document.method,
            "pages": parse_result.document.page_count,
            "tables": parse_result.document.table_count,
            "fields_extracted": normalized.fields_extracted,
            "warnings": normalized.warnings,
            "review_matrix": review_rows,
            "mineru_provenance": normalized.provenance,
            "raw_ir": normalized.raw_document.to_dict(include_cells=True) if normalized.raw_document is not None else None,
            "output_dir": parse_result.document.output_dir,
            "output_files": parse_result.document.raw_files,
            "assets": list(parse_result.document.images),
            "diagnostics": dict(
                getattr(parse_result, "diagnostics", {})
                or parse_result.document.metadata.get("diagnostics", {})
                or {}
            ),
            "fallback_diagnostics": fallback_diagnostics or {},
        }
        logger.info(
            "MinerU normalized: file=%s pages=%d tables=%d fields=%d warnings=%d",
            Path(source).name,
            parse_result.document.page_count,
            parse_result.document.table_count,
            normalized.fields_extracted,
            len(normalized.warnings),
        )
        return extracted

    def _run_import_pipeline(self, files, mineru_results):
        """Run the existing preview/atomic DB path after optional MinerU work."""
        results = []
        successful_files = []
        failed_files = []

        for number, source in enumerate(files, 1):
            self.import_status.setText(
                f"Processing {number}/{len(files)}: {os.path.basename(source)} - Scanning..."
            )
            QApplication.processEvents()
            dialog = None
            parse_result = None
            error_status = ImportStatus.PERSISTENCE_ERROR.value
            pipeline_stage = "route"
            try:
                route = route_file(source, template_matcher=self._auto_match_template)
                parse_result = mineru_results.get(self._result_key(source))
                path = source
                extracted = None
                pipeline_stage = "open"

                if route.engine == "mineru" and parse_result and parse_result.success:
                    self.import_status.setText(
                        f"{os.path.basename(source)} - Normalizing MinerU document and validating schema..."
                    )
                    QApplication.processEvents()
                    extracted = self._mineru_extracted(source, parse_result)
                elif route.engine == "mineru" and route.fallback_engine == "pdf_fallback":
                    # PDF fallback remains PDF-native and is adapted directly
                    # into the same common document IR.  It must never create
                    # or parse an intermediate workbook.
                    primary_reason = parse_result.error if parse_result else "MinerU was unavailable"
                    logger.warning("MinerU PDF fallback: file=%s reason=%s", Path(source).name, primary_reason)
                    self.import_status.setText(
                        f"{os.path.basename(source)} - MinerU unavailable; using PDF-native fallback..."
                    )
                    try:
                        fallback_document = parse_pdf_native_fallback(source)
                        fallback_result = MinerUParseResult(
                            source_file=str(source),
                            success=True,
                            document=fallback_document,
                        )
                        extracted = self._mineru_extracted(
                            source,
                            fallback_result,
                            source_label="PDF native fallback",
                            fallback_diagnostics={
                                "primary": {
                                    "error_type": parse_result.error_type if parse_result else "not-run",
                                    "error": primary_reason,
                                },
                                "fallback": {
                                    "engine": fallback_document.method,
                                    "pages": fallback_document.page_count,
                                    "tables": fallback_document.table_count,
                                },
                            },
                        )
                    except Exception as fallback_exc:
                        raise MinerUError(
                            "PDF_IMPORT_FAILED: MinerU cause: "
                            f"{primary_reason}; PDF fallback cause: {fallback_exc}"
                        ) from fallback_exc
                elif route.engine == "mineru" and route.fallback_engine == "excel_intelligence":
                    # Unknown XLSX can still use the established smart importer
                    # if MinerU is unavailable or fails.
                    reason = parse_result.error if parse_result else "MinerU was unavailable"
                    logger.warning("MinerU XLSX fallback to existing importer: file=%s reason=%s", Path(source).name, reason)
                elif route.engine == "mineru":
                    reason = parse_result.error if parse_result else "MinerU worker did not return a result"
                    raise MinerUError(
                        f"MinerU could not parse {Path(source).name}: {reason}. "
                        "Configure MINERU_EXECUTABLE or MINERU_PYTHON in Settings/environment."
                    )

                # Known structured workbooks have exactly one canonical path:
                # openpyxl -> ExcelIntelligence -> canonical JSON.  The legacy
                # SmartTemplate dialog is not run first and cannot overwrite
                # or compete with this result.
                if extracted is None and route.engine == "excel_intelligence":
                    pipeline_stage = "mapping"
                    rep, extracted = self.extract_file(path)

                if extracted is None:
                    if route.engine == "csv":
                        from core.document_import import csv_to_xlsx
                        clean = Path(os.path.join(QDir.tempPath(), Path(source).stem + "_csv_import.xlsx"))
                        csv_to_xlsx(source, clean)
                        path = str(clean)
                    elif route.engine == "unsupported":
                        raise ValueError(route.reason)
                    elif path.lower().endswith(".xls"):
                        raise ValueError("Legacy .xls requires conversion to .xlsx before import")

                    # A converter or a MinerU failure is not permission to
                    # enter the retired heuristic/profile importer.  Without
                    # a canonical template there is no safe mapping contract.
                    if route.engine in {"csv", "mineru"}:
                        raise ValueError(
                            "No canonical template was available after the "
                            f"{route.engine} fallback; import stopped before persistence"
                        )

                    # No heuristic/profile importer is reachable from the
                    # universal route.  Every successful branch above has
                    # already produced the canonical payload.

                # Existing quality and time-log validation remains the source
                # of truth for the database import boundary.
                pipeline_stage = "validation"
                report_data = extracted.get("daily_report", {})
                quality = ImportValidator.validate_rows([report_data], "daily_report", "Daily Report")
                time_logs = extracted.get("time_logs_24h", []) or []
                time_report = TimeLogValidator.validate_logs(time_logs, sheet="Time Logs 24H")
                quality.total += time_report.total
                quality.issues.extend(time_report.issues)
                for item in time_report.review.items:
                    quality.review.items.append(item)

                duplicate_indexes = set(find_duplicates(time_logs, "time_log"))
                if duplicate_indexes:
                    quality.warning("Time Logs", 0, f"Skipped {len(duplicate_indexes)} duplicate time-log rows")

                review_with_file = []
                for item in quality.review.as_rows():
                    item["file"] = os.path.basename(source)
                    item.setdefault("detected_table", item.get("record_type", ""))
                    item.setdefault("source_cell", f"{item.get('column','')}{item.get('row','')}")
                    item.setdefault("original_value", item.get("source_value"))
                    item.setdefault("normalized_value", item.get("value"))
                    item.setdefault("unit", item.get("unit", ""))
                    item.setdefault("target_field", item.get("canonical_field", ""))
                    review_with_file.append(item)
                quality.review.items = []
                for item in review_with_file:
                    quality.review.add(**item)

                metadata = extracted.get("metadata") or {}
                for item in metadata.get("review_matrix", []):
                    item["file"] = os.path.basename(source)
                    quality.review.add(**item)

                import_report_dict = quality.as_dict()
                if metadata.get("source") in {"MinerU", "PDF native fallback"}:
                    import_report_dict.update(
                        {
                            "source_engine": "MinerU",
                            "backend": metadata.get("backend", ""),
                            "method": metadata.get("method", ""),
                            "pages": metadata.get("pages", 0),
                            "tables": metadata.get("tables", 0),
                            "fields_extracted": metadata.get("fields_extracted", 0),
                            "warnings": len(metadata.get("warnings", [])),
                        }
                    )

                if not has_meaningful_canonical_data(extracted):
                    error_status = ImportStatus.VALIDATION_ERROR.value
                    pipeline_stage = "meaningful_data"
                    raise ValueError("No meaningful canonical report data was detected")

                pipeline_stage = "ui_preview"
                self.import_status.setText(
                    f"Preview for {os.path.basename(source)} - Waiting for user confirmation..."
                )
                preview = ImportPreviewDialog(source, extracted, import_report_dict, self)
                preview_result = preview.exec()

                if not preview.confirmed or preview_result != QDialog.Accepted:
                    results.append(
                        {
                            "file": source,
                            "skipped": 1,
                            "imported": 0,
                            "failed": 0,
                            "details": [f"⏭️ {os.path.basename(source)}: Cancelled by user in preview"],
                        }
                    )
                    failed_files.append(f"{os.path.basename(source)}: Cancelled")
                    if dialog is not None:
                        dialog.deleteLater()
                    continue

                preview.apply_review_changes(extracted)
                # Decisions and edits are now part of the audit payload and
                # the exact canonical object sent to the atomic save boundary.
                pipeline_stage = "persistence"
                self.import_status.setText(f"Importing {os.path.basename(source)} - Atomic transaction...")
                result = self._do_import(extracted, refresh_ui=False)
                result["file"] = source
                result["import_report"] = import_report_dict
                results.append(result)

                result_status = result.get("status", ImportStatus.PERSISTENCE_ERROR.value)
                if result_status in {ImportStatus.ACCEPT.value, ImportStatus.REVIEW_REQUIRED.value}:
                    successful_files.append(
                        f"{os.path.basename(source)} [{result_status}]"
                    )
                else:
                    failed_files.append(
                        f"{os.path.basename(source)} [{result_status}]: "
                        f"{result.get('details', [])[-1] if result.get('details') else 'Failed'}"
                    )
                if dialog is not None:
                    dialog.deleteLater()

            except Exception as exc:
                logger.error("Universal import failed for %s at %s: %s", source, pipeline_stage, exc, exc_info=True)
                # A source/open/mapping/validation failure is not a database
                # failure.  Preserve the four public statuses, but identify
                # the first failed stage explicitly so an empty workbook,
                # corrupt ZIP, mapping error, preview/UI error, and DB error
                # cannot collapse into one generic "routing" diagnostic.
                diagnostic_stage = {
                    "route": "import.routing",
                    "open": "import.open",
                    "mapping": "import.mapping",
                    "validation": "import.validation",
                    "meaningful_data": "validation.meaningful_data",
                    "ui_preview": "ui.preview",
                    "persistence": "import.persistence",
                }.get(pipeline_stage, "import.unknown")
                if pipeline_stage != "persistence" and pipeline_stage != "ui_preview":
                    error_status = ImportStatus.VALIDATION_ERROR.value
                diagnostic_status = error_status
                err_result = {
                    "file": source,
                    "failed": 1,
                    "imported": 0,
                    "status": diagnostic_status,
                    "diagnostics": [PersistenceIssue.from_exception(
                        exc, stage=diagnostic_stage, entity="source_document",
                        operation=("open_workbook" if pipeline_stage == "open" else pipeline_stage),
                        status=diagnostic_status,
                    ).to_dict()],
                    "details": [f"❌ {os.path.basename(source)}: {exc}"],
                    "error": str(exc),
                }
                results.append(err_result)
                failed_files.append(f"{os.path.basename(source)}: {exc}")
                if dialog is not None:
                    dialog.deleteLater()
            finally:
                # The adapter keeps the stable result directory alive through
                # normalization and review.  Once this file's consumer has
                # finished, release only the isolated temporary result.
                if parse_result is not None and parse_result.success:
                    parse_result.cleanup()

        summary_text = (
            f"Batch completed: {len(files)} files\n"
            f"✅ Successful: {len(successful_files)} - {', '.join(successful_files[:5])}\n"
            f"❌ Failed: {len(failed_files)} - {'; '.join(failed_files[:5])}"
        )
        self.batch_summary.setPlainText(summary_text)
        self.import_status.setText(
            f"Batch done: {len(successful_files)} success, {len(failed_files)} failed - See preview summary"
        )
        self.import_completed.emit(results)
        if failed_files and not successful_files:
            QMessageBox.warning(self, "Batch Import", summary_text)
        else:
            self.accept()
