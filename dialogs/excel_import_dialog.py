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
import logging
from pathlib import Path
from typing import Dict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QFileDialog, QComboBox, QMessageBox,
    QTextEdit, QTableWidget, QTableWidgetItem, QApplication,
    QInputDialog,
)
from PySide6.QtCore import QEventLoop, Signal, Qt
from PySide6.QtGui import QColor

from core.import_quality import (
    FINAL_REVIEW_DECISIONS,
    unresolved_review_items,
    apply_review_decisions,
)
from core.import_diagnostics import (
    PersistenceIssue, ImportStatus,
)
from core.ai_import_mapper import AIImportMapper, model_catalog, get_selected_model, set_selected_model
from core import async_workers as _async_workers
from core.async_workers import FunctionWorker, release_when_finished
from core.ddr_import_pipeline import (STAGES, PreparedImport, has_meaningful_canonical_data,  # noqa: F401
                                     mineru_extracted, pdf_split_info, prepare_import)
from core import ddr_import_pipeline as _pipeline
from core import import_router as _import_router
from core import isolated_parse
from core.import_router import route_file
from core.ddr_import_queue import CANCELLED, DUPLICATE, FAILED, FINAL, ImportQueue
from core.mineru_engine import (
    MinerUAdapter,
    MinerUParseResult,
)
from core.unit_manager import UnitManager
from dialogs.smart_template_dialog import FIELD_LABELS

from core.ddr_import_service import DDRImportService
from core import ddr_pdf_split

logger = logging.getLogger(__name__)

ALL_EXPECTED_FIELDS = list(FIELD_LABELS.keys())


# M111: moved to core.ddr_import_pipeline (Qt-free, importable by the isolated parser process).





# Universal aliases as per spec
UNIVERSAL_ALIASES = {
    "well_info.name": ["well", "well name", "well number", "well id", "نام چاه", "well designation", "well_name"],
    "well_info.report_date": ["report date", "date", "report_date"],
    "daily_report.depth_2400": ["md", "measured depth", "bit depth", "current depth", "depth", "depth @ 24:00", "td"],
    "drilling_params.wob_max": ["wob", "wt. on bit", "bit load", "weight on bit", "w.o.b"],
    "drilling_params.rpm_max": ["rotary", "rotary speed", "surface rpm", "rpm", "rotary speed"],
    "mud_report.mw": ["mud weight", "mw", "mud wt", "density", "1.50 sg", "sg"],
}


def review_thresholds(profile_info) -> tuple:
    """(accept, low) confidence bands; a profile threshold sets ``accept``."""
    accept, low = 0.95, 0.70
    if isinstance(profile_info, dict) and profile_info.get("confidence_threshold") is not None:
        try:
            accept = min(1.0, max(0.0, float(profile_info["confidence_threshold"])))
        except (TypeError, ValueError):  # silent-ok: malformed threshold keeps the documented default bands
            return 0.95, 0.70
        low = min(low, accept)
    return accept, low


def review_counts(review_rows, profile_info=None) -> dict:
    """Counts used by the preview header and the batch queue."""
    accept, low = review_thresholds(profile_info)
    counts = {"eligible": 0, "review": 0, "low": 0, "not_assessed": 0, "threshold": accept}
    for row in review_rows or []:
        conf = row.get("confidence") if isinstance(row, dict) else None
        if row.get("validation_state") == "needs_review" and conf in (None, ""):
            counts["review"] += 1
            continue
        try:
            value = float(conf)
        except (TypeError, ValueError):  # silent-ok: unscored items are counted as not assessed
            counts["not_assessed"] += 1
            continue
        if row.get("validation_state") == "needs_review" or low <= value < accept:
            counts["review"] += 1
        elif value >= accept:
            counts["eligible"] += 1
        else:
            counts["low"] += 1
    return counts


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
        self.deferred_count = 0                 # M150: rows explicitly kept for review by a partial import
        # M61: the report profile's confidence threshold decides acceptance
        # eligibility; without a profile the historical 95%/70% bands apply.
        self.accept_threshold, self.low_threshold = review_thresholds(
            (import_report or {}).get("profile")
            or ((extracted or {}).get("metadata") or {}).get("profile")
        )
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
        # M54: explicit scanned-page / OCR state of the PDF-native fallback.
        self.pdf_state_label = None
        note = self.pdf_extraction_note(report)
        if note:
            self.pdf_state_label = QLabel(note)
            self.pdf_state_label.setWordWrap(True)
            self.pdf_state_label.setStyleSheet(
                "color: #7a4b00; background: #fff4e0; padding: 6px; border-radius: 4px;"
            )
            layout.addWidget(self.pdf_state_label)
        profile_info = report.get("profile") or ((self.extracted or {}).get("metadata") or {}).get("profile")
        self.profile_label = QLabel(self.profile_summary(profile_info))
        self.profile_label.setStyleSheet("color: #2c3e50; padding: 2px 4px;")
        layout.addWidget(self.profile_label)
        # M71: every source column with its target; unmapped columns and the
        # explainable profile suggestion are shown, never applied silently.
        self.column_label = QLabel(self.column_summary(report, (profile_info or {}).get("key")))
        self.column_label.setWordWrap(True)
        self.column_label.setVisible(bool(self.column_label.text()))
        layout.addWidget(self.column_label)
        counts = review_counts(report.get("review") or report.get("review_matrix")
                               or ((self.extracted or {}).get("metadata") or {}).get("review_matrix"), profile_info)
        self.threshold_label = QLabel(
            f"Acceptance threshold {counts['threshold']:.0%}: {counts['eligible']} eligible, "
            f"{counts['review']} need review, {counts['low']} low, {counts['not_assessed']} not scored."
        )
        layout.addWidget(self.threshold_label)
        self._add_pdf_split_section(layout, report)

        # Table
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(
            ["File", "Sheet/Page", "Detected Table", "Source Cell", "Original Value", "Normalized Value", "Unit", "Target Field", "Confidence", "Decision"]
        )
        self.table.setAlternatingRowColors(True)
        # Sorting stays off while rows are filled: with it on, Qt re-sorts a
        # row as soon as its first cell is set, so the remaining cells (and
        # the payload link) landed in another row. Enabled after population.
        self.table.setSortingEnabled(False)
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
                    if conf_f >= self.accept_threshold:
                        it.setBackground(QColor("#d5f5e3"))
                    elif conf_f >= self.low_threshold:
                        it.setBackground(QColor("#fef9e7"))
                    else:
                        it.setBackground(QColor("#fadbd8"))
                except (TypeError, ValueError, OverflowError):  # silent-ok: non-numeric confidence gets no colour
                    pass
                self.table.setItem(row, col, it)
            # Link the row to its canonical payload by index: PySide6 stores a
            # dict under UserRole as a converted copy, so decisions written to
            # it never reached the payloads that confirm/apply read.
            self.table.item(row, 0).setData(Qt.UserRole, len(self._row_payloads))
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
            self.table.item(row, 0).setData(Qt.UserRole, len(self._row_payloads))
            self._row_payloads.append(None)

        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table, 1)
        # M54 review workspace: full provenance of the selected field.
        self.detail_label = QLabel("Select a row to see its source, mapping, confidence and warning.")
        self.detail_label.setWordWrap(True)
        self.detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_label.setStyleSheet("background: #f4f6f7; padding: 6px; border-radius: 4px;")
        layout.addWidget(self.detail_label)
        self.table.currentCellChanged.connect(self._show_field_detail)

        # Action buttons as per spec
        btn_layout = QHBoxLayout()

        accept_high_btn = QPushButton("✅ Accept All High Confidence")
        accept_high_btn.setToolTip(f"Accept all items with confidence >={self.accept_threshold:.0%} (values needing review are skipped)")
        accept_high_btn.clicked.connect(self._accept_high)
        btn_layout.addWidget(accept_high_btn)

        review_medium_btn = QPushButton("🟡 Review Medium")
        review_medium_btn.setToolTip(f"Focus on medium confidence {self.low_threshold:.0%}-{self.accept_threshold:.0%}")
        review_medium_btn.clicked.connect(self._filter_medium)
        btn_layout.addWidget(review_medium_btn)

        reject_low_btn = QPushButton("🔴 Reject Low Confidence")
        reject_low_btn.setToolTip(f"Reject all items with confidence <{self.low_threshold:.0%}")
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

        self.attach_btn = QPushButton("🔗 Attach Eligible Continuations")
        self.attach_btn.setToolTip("Attach narrative continuation rows to their parent activity - only rows whose "
                                   "parent is unambiguous (same table and page, source order kept)")
        self.attach_btn.clicked.connect(self._attach_continuations_clicked)
        btn_layout.addWidget(self.attach_btn)

        layout.addLayout(btn_layout)

        # Confirm / Cancel
        confirm_layout = QHBoxLayout()
        confirm_layout.addStretch()

        cancel_btn = QPushButton("❌ Cancel Import")
        cancel_btn.setStyleSheet("background: #e74c3c; color: white; padding: 8px 16px; font-weight: bold; border-radius: 4px;")
        cancel_btn.clicked.connect(self.reject)
        confirm_layout.addWidget(cancel_btn)

        self.confirm_btn = QPushButton("✅ Confirm Import")
        self.confirm_btn.setStyleSheet(
            "QPushButton { background: #27ae60; color: white; padding: 10px 20px; font-weight: bold; "
            "border-radius: 4px; font-size: 13px; } "
            "QPushButton:disabled { background: #bdc3c7; color: #6c7a89; }")   # a blocked import must look blocked
        self.confirm_btn.clicked.connect(self._confirm)
        confirm_layout.addWidget(self.confirm_btn)
        if self._multi_report_block():
            self.confirm_btn.setEnabled(False)
            self.confirm_btn.setToolTip(self._multi_report_block())

        layout.addLayout(confirm_layout)

    # ---- M52: PDF report split ------------------------------------------------------------------
    def _multi_report_block(self) -> str:
        split = (self.import_report or {}).get("pdf_split") or {}
        if not split.get("multi_report"):
            return ""
        ranges = ", ".join(s["page_range"] for s in split.get("segments", []))
        return (f"This PDF holds {len(split['segments'])} daily reports (pages {ranges}). Importing it as one "
                "report would mix them. Save one PDF per report and import each one.")

    @staticmethod
    def profile_summary(profile_info):
        if not profile_info:
            return "Report profile: none — canonical aliases only."
        count = len(profile_info.get("mappings") or [])
        return (f"Report profile: {profile_info.get('name')} v{profile_info.get('version')} — "
                f"{count} column/label mapping(s) came from the profile.")

    @staticmethod
    def field_detail_text(payload, profile_info=None):
        """Plain-text provenance of one review row (source → decision)."""
        if not payload:
            return "Validation issue row — see the Decision column."
        location = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        target = payload.get("target_field", payload.get("canonical_field", ""))
        method = payload.get("mapping_method") or "canonical mapper"
        for hit in (profile_info or {}).get("mappings") or []:
            if hit.get("field") == target:
                method = f"report profile {hit.get('profile')} v{hit.get('version')} (label '{hit.get('label')}')"
                break
        confidence = payload.get("confidence")
        warning = (payload.get("review_reason") or payload.get("reason") or payload.get("message")
                   or payload.get("warning") or "none")
        page = payload.get("page", location.get("page", location.get("source_page", "")))
        parts = [
            f"Source: {payload.get('sheet', payload.get('file', '')) or '—'}"
            + (f", page {page}" if page not in (None, "") else "")
            + f", cell {payload.get('source_cell', '') or '—'}",
            f"Original: {payload.get('original_value', payload.get('source_value', '')) or '—'}",
            f"Normalized: {payload.get('normalized_value', payload.get('value', '')) or '—'} {payload.get('unit', '') or ''}".rstrip(),
            f"Target field: {target or 'unmapped'}  |  Mapped by: {method}",
            "Confidence: " + (f"{float(confidence):.0%}" if confidence not in (None, "") else "not assessed"),
            f"Warning: {warning}",
            f"Decision: {payload.get('decision', 'REVIEW')}",
        ]
        if payload.get("review_type") == "continuation":
            # M151: the reviewer sees the parent the text would join and why it may or may not be attached.
            parent = payload.get("parent") if isinstance(payload.get("parent"), dict) else None
            if parent:
                span = f"{parent.get('time_from') or '?'}-{parent.get('time_to') or '?'}"
                parts.append(f"Parent activity (source row {parent.get('row') or '?'}, {span}): "
                             f"{str(parent.get('description') or '')[:200] or '—'}")
            else:
                parts.append("Parent activity: none identified")
            parts.append("Attachable: yes" if payload.get("eligible")
                         else f"Attachable: no - {payload.get('reason') or 'not eligible'}")
        return "\n".join(parts)

    def _show_field_detail(self, row, _col=0, _prev_row=0, _prev_col=0):
        item = self.table.item(row, 0) if row is not None and row >= 0 else None
        if item is None:
            return
        index = item.data(Qt.UserRole)
        payload = self._row_payloads[index] if isinstance(index, int) and index < len(self._row_payloads) else None
        self.detail_label.setText(self.field_detail_text(payload, (self.import_report or {}).get("profile")))

    @staticmethod
    def column_summary(report, current_key=None) -> str:
        """Column-mapping and profile-suggestion text for the preview, or ``""``."""
        report = report or {}
        parts = []
        mapping = report.get("column_mapping") or {}
        if mapping.get("columns"):
            text = f"Columns: {mapping['columns']} read, {mapping['mapped']} mapped"
            if mapping.get("unmapped"):
                text += ("; not mapped to a report field (review them, they are not saved as fields): "
                         + ", ".join(mapping["unmapped"]))
            parts.append(text + ".")
        for hint in report.get("profile_suggestions") or []:
            if hint["key"] == current_key:
                continue
            parts.append(f"Suggested profile: {hint['name']} v{hint['version']} - its aliases match "
                         f"{hint['matched']} of {hint['total']} headers ({', '.join(hint['matched_headers'][:6])}). "
                         "Select it and re-import to use it.")
            break
        return " ".join(parts)

    @staticmethod
    def pdf_extraction_note(report):
        """User-facing scanned-page/OCR note for a PDF fallback import, or ``None``."""
        fallback = ((report or {}).get("fallback_diagnostics") or {}).get("fallback") or {}
        scanned = list(fallback.get("scanned_pages") or [])
        if not scanned:
            return None
        pages = ", ".join(str(p) for p in scanned)
        if fallback.get("ocr") == "unavailable":
            return (f"OCR unavailable: page(s) {pages} are scanned images without a text layer and were "
                    "not read. Nothing was guessed for those pages; enter their values manually.")
        return f"Scanned page(s) {pages} detected: OCR text must be verified field by field before saving."

    def _add_pdf_split_section(self, layout, report):
        split, error = report.get("pdf_split"), report.get("pdf_split_error")
        if not split and not error:
            return
        box = QGroupBox("📑 PDF report split")
        box_layout = QVBoxLayout(box)
        if error:
            label = QLabel(f"Report split NOT ASSESSED: {error}")
            label.setStyleSheet("color: #c0392b;")
            box_layout.addWidget(label)
            layout.addWidget(box)
            return
        segments = split.get("segments", [])
        notes = list(split.get("warnings", []))
        head = (f"{split.get('page_count', 0)} pages, {len(segments)} report(s) found"
                + (f"; unassigned pages: {', '.join(map(str, split.get('unassigned_pages', [])))}"
                   if split.get("unassigned_pages") else ""))
        self.pdf_split_label = QLabel(head + ("" if not notes else " - " + "; ".join(notes)))
        self.pdf_split_label.setWordWrap(True)
        box_layout.addWidget(self.pdf_split_label)
        self.pdf_split_table = QTableWidget(len(segments), 6)
        self.pdf_split_table.setHorizontalHeaderLabels(["Pages", "Report No.", "Date", "Well", "Confidence", "Warnings"])
        self.pdf_split_table.setEditTriggers(QTableWidget.NoEditTriggers)
        for row, seg in enumerate(segments):
            date_text = seg.get("report_date") or (f"{seg['date_text']} (not read)" if seg.get("date_text") else "—")
            values = [seg["page_range"], "—" if seg.get("report_number") is None else str(seg["report_number"]),
                      date_text, seg.get("well") or "—",
                      seg["confidence"] + (f" ({', '.join(seg['reasons'])})" if seg.get("reasons") else ""),
                      "; ".join(seg.get("warnings", []))]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col in (0, 1, 2):
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.pdf_split_table.setItem(row, col, item)
        self.pdf_split_table.horizontalHeader().setStretchLastSection(True)
        self.pdf_split_table.setMaximumHeight(160)
        box_layout.addWidget(self.pdf_split_table)
        blocked = self._multi_report_block()
        if blocked:
            warn = QLabel("⛔ " + blocked)
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #c0392b; font-weight: bold;")
            box_layout.addWidget(warn)
            self.save_split_btn = QPushButton("💾 Save one PDF per report…")
            self.save_split_btn.clicked.connect(self._save_split_pdfs)
            box_layout.addWidget(self.save_split_btn)
        layout.addWidget(box)

    def choose_split_folder(self) -> str:
        return QFileDialog.getExistingDirectory(self, "Folder for the per-report PDFs", str(Path(self.file_path).parent))

    def _save_split_pdfs(self):
        folder = self.choose_split_folder()
        if not folder:
            return None
        split = self.import_report.get("pdf_split") or {}
        segments = [ddr_pdf_split.ReportSegment(pages=s["pages"], report_number=s.get("report_number"),
                                                report_date=s.get("report_date"), well=s.get("well"))
                    for s in split.get("segments", [])]
        try:
            written = ddr_pdf_split.write_segments(self.file_path, segments, folder)
        except Exception as exc:
            logger.error("Per-report PDFs could not be written: %s", type(exc).__name__)
            QMessageBox.critical(self, "Split failed", f"The per-report PDFs could not be written ({type(exc).__name__}).")
            return None
        QMessageBox.information(self, "PDFs written", f"{len(written)} PDF file(s) written to {folder}.\n"
                                "Import each file on its own; nothing was imported from this PDF.")
        return written

    def _accept_high(self):
        for row in range(self.table.rowCount()):
            conf_item = self.table.item(row, 8)
            if not conf_item:
                continue
            try:
                conf_str = conf_item.text().replace("%", "")
                conf = float(conf_str) / 100 if conf_str else 0
                payload = self._payload_for_row(row)
                if payload is not None and payload.get("validation_state") == "needs_review":
                    continue  # ambiguous/unparsed values are never bulk-accepted
                if payload is not None and payload.get("review_type") == "continuation":
                    continue  # a continuation is attached or rejected, never accepted as a value (M148)
                if conf >= self.accept_threshold:
                    self._set_decision(row, "ACCEPT")
            except (TypeError, ValueError, OverflowError):  # silent-ok: non-numeric confidence is left for manual review
                pass

    def _payload_for_row(self, row: int):
        # The payload index travels with the row's first cell, so the link
        # stays correct after the user sorts the table. Issue rows map to None.
        item = self.table.item(row, 0)
        index = item.data(Qt.UserRole) if item is not None else None
        if isinstance(index, int) and 0 <= index < len(self._row_payloads):
            return self._row_payloads[index]
        return None

    def _set_decision(self, row: int, decision: str) -> None:
        self.table.setItem(row, 9, QTableWidgetItem(decision))
        payload = self._payload_for_row(row)
        if payload is not None:

            payload["decision"] = decision
            payload["review_state"] = self._review_state(decision)

    @staticmethod
    def _review_state(decision: str) -> str:
        if decision in {"ACCEPT", "CONFIRMED", "ATTACH_CONTINUATION"}:
            return "accepted"
        if decision in {"REJECT", "IGNORED", "IGNORE"}:
            return "rejected"
        return "deferred" if decision == "DEFER" else "unreviewed"

    def attach_eligible_continuations(self) -> int:
        """M151: mark every undecided, eligible continuation row ATTACH_CONTINUATION; returns how many.

        Eligibility comes from the shared contract (unambiguous parent, same table/page, source order kept,
        allowed by the profile); ineligible rows are left for an explicit decision.
        """
        marked = 0
        for row in range(self.table.rowCount()):
            payload = self._payload_for_row(row)
            if not payload or payload.get("review_type") != "continuation" or not payload.get("eligible"):
                continue
            current = self.table.item(row, 9).text() if self.table.item(row, 9) else "REVIEW"
            if current in FINAL_REVIEW_DECISIONS:
                continue
            self._set_decision(row, "ATTACH_CONTINUATION")
            marked += 1
        return marked

    def _attach_continuations_clicked(self):
        marked = self.attach_eligible_continuations()
        QMessageBox.information(
            self, "Continuation rows",
            f"{marked} eligible continuation row(s) will be attached to their parent activity on import. "
            "Rows without a provable parent keep their review decision." if marked else
            "No undecided continuation row has a provable parent; nothing was marked.")

    def _ask_partial_import(self, pending: list) -> bool:
        """Offer the M150 partial import; True only when the user chose it explicitly."""
        examples = [str(item.get("target_field") or item.get("canonical_field") or "unmapped field")
                    for item in pending[:5] if isinstance(item, dict)]
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Review Required")
        box.setText(f"{len(pending)} review row(s) have no decision: " + ", ".join(examples)
                    + (" and more" if len(pending) > len(examples) else "") + ".")
        box.setInformativeText(
            "Import the verified records and keep the undecided rows for review? Undecided values are not "
            "saved as report data; they stay in the review queue of this report until you decide them.")
        partial = box.addButton(f"Import verified records and retain {len(pending)} unresolved item(s) for review",
                                QMessageBox.AcceptRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() is partial

    def _filter_medium(self):
        for row in range(self.table.rowCount()):
            conf_item = self.table.item(row, 8)
            if not conf_item:
                continue
            try:
                conf_str = conf_item.text().replace("%", "")
                conf = float(conf_str) / 100 if conf_str else 0
                show = self.low_threshold <= conf < self.accept_threshold
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
                if conf < self.low_threshold:
                    self._set_decision(row, "REJECT")
            except (TypeError, ValueError, OverflowError):  # silent-ok: non-numeric confidence is left for manual review
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
                    except (TypeError, ValueError, OverflowError):  # silent-ok: non-numeric value is not unit-converted
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
        blocked = self._multi_report_block()
        if blocked:
            QMessageBox.warning(self, "Several reports in one PDF", blocked)
            return
        # A proposal marked REVIEW is not an operator decision. Block the
        # transition to persistence until every row has a final decision.
        self.get_decisions()
        pending = [item for item in unresolved_review_items(self._row_payloads)
                   if str(item.get("decision") or "REVIEW").upper() != "DEFER"]
        if pending:
            # M150: never a silent acceptance - either the user cancels, or the undecided rows are explicitly
            # deferred: excluded from the report data and kept in the persisted review queue.
            if not self._ask_partial_import(pending):
                return
            pending_ids = {id(item) for item in pending}
            for row in range(self.table.rowCount()):
                payload = self._payload_for_row(row)
                if payload is not None and id(payload) in pending_ids:
                    self._set_decision(row, "DEFER")
            self.deferred_count = len(pending)
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
            payload["review_state"] = self._review_state(decision)
        return decisions

    def apply_review_changes(self, extracted: dict) -> dict:
        """Apply UI decisions through the Qt-free canonical review boundary."""
        self.get_decisions()
        return apply_review_decisions(extracted, self._row_payloads)


class ExcelImportDialog(QDialog, DDRImportService):
    """
    Main entry point for Excel Import - Professional version
    """

    @staticmethod
    def _saved_summary(result: dict) -> str:
        """What a successful import actually saved (M150: a partial import says so)."""
        if result.get("reimport"):
            return " - already imported, nothing new saved"
        queue = result.get("review_queue") or {}
        parts = []
        if result.get("report_id"):
            parts.append(f"report {result['report_id']} saved")
        if queue.get("attached"):
            parts.append(f"{queue['attached']} continuation(s) attached")
        if queue.get("pending"):
            parts.append(f"{queue['pending']} item(s) kept for review")
        return (" - " + ", ".join(parts)) if parts else ""

    import_completed = Signal(list)

    def __init__(self, db_manager, well_id: int, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.well_id = well_id
        self._mineru_worker = None
        self._prepare_worker = None
        self._import_busy = False
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

        # M54: optional versioned report profile used as mapping context.
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Report profile:"))
        self.profile_combo = QComboBox()
        self.profile_combo.setToolTip(
            "Profile aliases are tried before the canonical aliases; every profile mapping is shown in the preview."
        )
        profile_row.addWidget(self.profile_combo, 1)
        self.profiles_btn = QPushButton("Manage profiles…")
        self.profiles_btn.clicked.connect(self._open_profile_editor)
        profile_row.addWidget(self.profiles_btn)
        il.addLayout(profile_row)
        self.refresh_profile_choices()

        import_btn = QPushButton("📥 Import Report(s) - With Preview")
        import_btn.setStyleSheet(
            "background: #27ae60; color: white; padding: 14px; "
            "font-weight: bold; border-radius: 5px; font-size: 14px;"
        )
        import_btn.clicked.connect(self._unified_import)
        self._import_btn = import_btn
        il.addWidget(import_btn)

        self.import_status = QLabel("No file selected - Preview before save enabled (P0)")
        self.import_status.setStyleSheet("color: #2c3e50; font-weight: bold;")
        il.addWidget(self.import_status)

        # M61: visible batch queue with per-file status, stage, profile and
        # diagnostics; remove / retry / cancel act on core.ddr_import_queue.
        self.import_queue = ImportQueue()
        self.queue_table = QTableWidget(0, 6)
        self.queue_table.setHorizontalHeaderLabels(["File", "Status", "Stage", "Profile", "Attempts", "Diagnostics"])
        self.queue_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.queue_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.queue_table.setMaximumHeight(150)
        il.addWidget(self.queue_table)
        queue_buttons = QHBoxLayout()
        self.queue_remove_btn = QPushButton("Remove selected")
        self.queue_remove_btn.setToolTip("Remove a queued, failed, skipped, cancelled or duplicate file; saved results are kept.")
        self.queue_remove_btn.clicked.connect(self._queue_remove_selected)
        self.queue_retry_btn = QPushButton("Retry failed")
        self.queue_retry_btn.setToolTip("Re-run failed, skipped and cancelled files.")
        self.queue_retry_btn.clicked.connect(self._queue_retry)
        self.queue_cancel_btn = QPushButton("Cancel remaining")
        self.queue_cancel_btn.setToolTip("Files not yet started are cancelled; the running file stops at its next step unless it is already saving.")
        self.queue_cancel_btn.clicked.connect(self._queue_cancel)
        # M151: the persisted review queue (deferred rows, continuations) of the well just imported.
        self.review_queue_btn = QPushButton("Review queue…")
        self.review_queue_btn.setToolTip("Rows kept for review by earlier imports of this well: attach continuations, "
                                         "reject or ignore them.")
        self.review_queue_btn.clicked.connect(self.open_review_queue)
        for button in (self.queue_remove_btn, self.queue_retry_btn, self.queue_cancel_btn, self.review_queue_btn):
            queue_buttons.addWidget(button)
        il.addLayout(queue_buttons)

        self.batch_summary = QTextEdit()
        self.batch_summary.setReadOnly(True)
        self.batch_summary.setMaximumHeight(120)
        self.batch_summary.setPlaceholderText("Batch results will appear here: successful vs failed files")
        il.addWidget(self.batch_summary)

        layout.addWidget(import_group)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

    def open_review_queue(self):
        if not self.well_id:
            QMessageBox.information(self, "Review queue", "Select a well (or import a report) first.")
            return None
        from dialogs.import_review_dialog import ImportReviewDialog
        dialog = ImportReviewDialog(self.db, self.well_id, self)
        dialog.exec()
        return dialog

    def refresh_profile_choices(self, select_key=None):
        combo = getattr(self, "profile_combo", None)
        if combo is None:
            return
        current = select_key or (combo.currentData().key if combo.currentData() is not None else None)
        combo.clear()
        combo.addItem("None — canonical aliases only", None)
        try:
            from core.ddr_report_profiles import list_latest_profiles
            profiles = list_latest_profiles(self.db) if self.db is not None else []
        except Exception as exc:
            logger.error("Report profiles unavailable: %s", exc)
            profiles = []
        for profile in profiles:
            combo.addItem(profile.label(), profile)
            if profile.key == current:
                combo.setCurrentIndex(combo.count() - 1)

    def active_profile(self):
        combo = getattr(self, "profile_combo", None)
        return combo.currentData() if combo is not None else None

    def _open_profile_editor(self):
        from core.permissions import permissions as _perms
        from dialogs.ddr_profile_dialog import ReportProfileDialog
        dialog = ReportProfileDialog(self.db, self, user_id=_perms.user_id)
        dialog.exec()
        self.refresh_profile_choices()

    def _select_ai_model(self, index):
        model = self.ai_model_combo.itemData(index) if hasattr(self, "ai_model_combo") else None
        if model:
            os.environ["DRILLMASTER_AI_MODEL"] = model
            os.environ["DRILLMASTER_AI_IMPORT"] = "1"
            set_selected_model(model)

    # -- M61 batch queue ------------------------------------------------
    def _queue(self) -> ImportQueue:
        if getattr(self, "import_queue", None) is None:
            self.import_queue = ImportQueue()
        return self.import_queue

    def _refresh_queue_view(self) -> None:
        table = getattr(self, "queue_table", None)
        if table is None:
            return
        entries = self._queue().entries
        table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            values = [entry.name, entry.status, entry.stage, entry.profile, str(entry.attempts),
                      entry.diagnostics[-1] if entry.diagnostics else ""]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setToolTip(entry.path)
                if column == 5:
                    item.setToolTip("\n".join(entry.diagnostics))
                table.setItem(row, column, item)

    def _queue_stage(self, stage: str) -> str:
        entry = getattr(self, "_queue_current", None)
        if entry is not None:
            entry.stage = stage
            self._refresh_queue_view()
        return stage

    def _queue_remove_selected(self) -> None:
        table = getattr(self, "queue_table", None)
        row = table.currentRow() if table is not None else -1
        if row >= 0 and not self._queue().remove(row):
            self.import_status.setText("That file is running or already saved; it cannot be removed.")
        self._refresh_queue_view()

    def _queue_retry(self) -> None:
        if getattr(self, "_import_busy", False):
            self.import_status.setText("An import is already running - retry after it finishes.")
            return
        entries = self._queue().retry()
        self._refresh_queue_view()
        if not entries:
            self.import_status.setText("No failed, skipped or cancelled files to retry.")
            return
        self._set_import_busy(True)
        try:
            self._start_import_batch([entry.path for entry in entries])
        except Exception:
            self._set_import_busy(False)
            raise

    def _queue_cancel(self) -> None:
        queue = self._queue()
        count = queue.cancel()
        current = getattr(self, "_queue_current", None)
        if current is not None and queue.cancel_running(current):
            count += 1
        self._refresh_queue_view()
        self.import_status.setText(f"Cancel requested: {count} file(s) not started were cancelled.")

    def _set_import_busy(self, busy: bool) -> None:
        """One batch at a time: a second click while MinerU parses, or while
        processEvents() repaints during the pipeline, must not start another
        batch (it used to overwrite the pending file list and drop a batch)."""
        self._import_busy = bool(busy)
        button = getattr(self, "_import_btn", None)
        if button is not None:
            button.setEnabled(not busy)

    def _unified_import(self):
        """Route imports without running MinerU in the Qt UI thread."""
        if getattr(self, "_import_busy", False):
            self.import_status.setText("An import is already running - wait for it to finish.")
            return
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Report(s)",
            "",
            "Reports (*.xlsx *.xls *.xlsm *.csv *.pdf *.docx *.pptx *.png *.jpg *.jpeg *.webp *.tif *.tiff)",
        )
        if not files:
            return

        self._set_import_busy(True)
        try:
            self._start_import_batch(files)
        except Exception:
            self._set_import_busy(False)
            raise

    def _start_import_batch(self, files):
        queue = self._queue()
        queue.cancel_requested = False
        queue.add(files)
        self._refresh_queue_view()
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
        release_when_finished(self._mineru_worker)   # M52: emitted inside run(), finished_ok follows
        self._mineru_worker = None
        self._run_import_pipeline(self._pending_import_files, self._mineru_results)

    def _on_mineru_batch_failed(self, error):
        logger.error("MinerU worker failed: %s", error)
        release_when_finished(self._mineru_worker)   # M52: emitted inside run(), finished_ok follows
        self._mineru_worker = None
        # PDF still has the existing explicit fallback. XLSX still has the
        # existing smart/template path. Other MinerU-only formats receive an
        # actionable per-file failure in _run_import_pipeline.
        self._run_import_pipeline(self._pending_import_files, {})

    def _mineru_extracted(self, source, parse_result, *, source_label="MinerU", fallback_diagnostics=None):
        """Canonical data for a successful parse with the dialog's active profile (GUI thread)."""
        profile = self.active_profile() if hasattr(self, "active_profile") else None
        return mineru_extracted(source, parse_result, profile=profile, source_label=source_label,
                                fallback_diagnostics=fallback_diagnostics)

    def _expected_well_name(self):
        return ddr_pdf_split.expected_well_name(self.db, self.well_id)

    def _profile_choices(self) -> list:
        combo = getattr(self, "profile_combo", None)
        if combo is None:
            return []
        return [combo.itemData(i) for i in range(combo.count()) if combo.itemData(i) is not None]

    def _prepare_in_background(self, source, parse_result, profile, entry):
        """Run ``prepare_import`` in a worker thread and wait without blocking the GUI.

        The local event loop only waits: painting, the queue's cancel button and
        window moves keep working.  The DTO is written by the worker and read here
        after the thread has finished, so no Qt or database object is shared.
        """
        holder = {}
        kwargs = dict(
            parse_result=parse_result, profile=profile, profiles=self._profile_choices(),
            expected_well=self._expected_well_name(), route=route_file,
            template_matcher=self._auto_match_template, extract_file=self.extract_file,
            meaningful=has_meaningful_canonical_data,
            should_cancel=lambda: entry.status == CANCELLED,
        )

        isolated = self._parsers_can_be_isolated(kwargs, parse_result)
        self._last_parse_mode = isolated_parse.MODE if isolated else "worker thread"

        def job():
            if isolated:                   # M111: spawn child, plain data only, bounded shutdown
                holder["prepared"] = isolated_parse.prepare_isolated(
                    source, parse_result=parse_result, profile=profile, profiles=kwargs["profiles"],
                    expected_well=kwargs["expected_well"], should_cancel=kwargs["should_cancel"],
                    timeout=self.parse_timeout)
            else:
                holder["prepared"] = prepare_import(source, **kwargs)

        worker = _async_workers.FunctionWorker(job)
        self._prepare_worker = worker
        loop = QEventLoop(self)
        worker.finished.connect(loop.quit)
        worker.start()
        if not worker.isFinished():
            loop.exec()
        worker.wait()
        self._prepare_worker = None
        release_when_finished(worker)
        prepared = holder.get("prepared")
        if prepared is None:                       # the worker itself failed before returning
            prepared = PreparedImport(source=str(source), error=RuntimeError("Background preparation failed"))
        return prepared

    #: M111: seconds before an isolated parse is stopped (TIMEOUT; nothing is saved).
    parse_timeout = isolated_parse.DEFAULT_TIMEOUT
    #: M111: production parsers run in a spawn child; set False only to debug in-process.
    isolate_parsing = True

    def _parsers_can_be_isolated(self, kwargs, parse_result) -> bool:
        """True when every parser is the production one (an injected callable cannot cross processes)."""
        cls = type(self)
        return bool(
            self.isolate_parsing
            and (parse_result is None or not getattr(parse_result, "success", False))
            and kwargs["route"] is _import_router.route_file
            and kwargs["meaningful"] is _pipeline.has_meaningful_canonical_data
            and "extract_file" not in vars(self) and cls.extract_file is DDRImportService.extract_file
            and "_auto_match_template" not in vars(self)
            and cls._auto_match_template is DDRImportService._auto_match_template)

    def _workers_running(self) -> bool:
        return any(w is not None and w.isRunning() for w in (self._prepare_worker, self._mineru_worker))

    def done(self, result):
        """Never destroy the dialog under a running worker (Qt would abort the process)."""
        if self._workers_running():
            current = getattr(self, "_queue_current", None)
            queue = self._queue()
            queue.cancel()
            if current is not None:
                queue.cancel_running(current)
            self._refresh_queue_view()
            self.import_status.setText("Cancelling: the dialog can close once the current step has finished.")
            return
        super().done(result)

    def _run_import_pipeline(self, files, mineru_results):
        """Run the batch, then release the one-batch-at-a-time guard."""
        try:
            self._run_import_pipeline_steps(files, mineru_results)
        finally:
            self._set_import_busy(False)

    def _pdf_split_info(self, source) -> dict:
        """M52: report split of a PDF (several daily reports in one file), before any extraction."""
        return pdf_split_info(source, self._expected_well_name())

    @staticmethod
    def _pdf_split_details(info) -> list:
        split = (info or {}).get("pdf_split") or {}
        if not split.get("multi_report"):
            return []
        ranges = ", ".join(s["page_range"] for s in split["segments"])
        return [f"ℹ️ This PDF holds {len(split['segments'])} daily reports (pages {ranges}); "
                "split it and import each report on its own."]

    def _run_import_pipeline_steps(self, files, mineru_results):
        """Run the existing preview/atomic DB path after optional MinerU work."""
        results = []
        successful_files = []
        failed_files = []
        batch_well_id = self.well_id

        for number, source in enumerate(files, 1):
            self.import_status.setText(
                f"Processing {number}/{len(files)}: {os.path.basename(source)} - Scanning..."
            )
            QApplication.processEvents()
            queue = self._queue()
            entry = queue.find(source)
            if entry is None or (entry.status in FINAL and entry.status != DUPLICATE):
                entry = (queue.add([source]) or [queue.find(source)])[0]
            profile = self.active_profile() if hasattr(self, "active_profile") else None
            runnable = (entry.status not in FINAL and not queue.cancel_requested
                        and queue.start(entry, profile.label() if profile is not None else ""))
            if not runnable:
                if entry.status not in FINAL:
                    entry.status, entry.stage = CANCELLED, "cancelled before start"
                # M84: a parser result prepared for a file that never runs is released too.
                unused = mineru_results.get(self._result_key(source))
                if unused is not None and getattr(unused, "success", False):
                    unused.cleanup()
                results.append({
                    "file": source, "imported": 0, "failed": int(entry.status == FAILED),
                    "skipped": int(entry.status != FAILED),
                    "reimport": entry.status == DUPLICATE, "queue_status": entry.status,
                    "details": [f"⏭️ {os.path.basename(source)}: {entry.status.lower()}"
                                + (f" - {entry.diagnostics[-1]}" if entry.diagnostics else "")],
                })
                self._refresh_queue_view()
                continue
            self._queue_current = entry
            results_before = len(results)
            dialog = None
            parse_result = None
            error_status = ImportStatus.PERSISTENCE_ERROR.value
            pipeline_stage = self._queue_stage("route")
            pdf_split_info = {}
            try:
                parse_result = mineru_results.get(self._result_key(source))
                self.import_status.setText(
                    f"Processing {number}/{len(files)}: {os.path.basename(source)} - "
                    "reading and validating in the background..."
                )
                # M71: routing, extraction, normalization and validation run in
                # a worker; only plain values cross the thread boundary.
                prepared = self._prepare_in_background(source, parse_result, profile, entry)
                pdf_split_info = prepared.pdf_split_info
                for stage in STAGES[:STAGES.index(prepared.stage) + 1]:
                    pipeline_stage = self._queue_stage(stage)
                if prepared.cancelled:
                    results.append({
                        "file": source, "skipped": 1, "imported": 0, "failed": 0, "queue_status": CANCELLED,
                        "details": [f"⏭️ {os.path.basename(source)}: cancelled during {prepared.stage}; nothing saved"],
                    })
                    failed_files.append(f"{os.path.basename(source)}: Cancelled")
                    continue
                if prepared.error is not None:
                    raise prepared.error
                extracted, import_report_dict = prepared.extracted, prepared.import_report
                if self.well_id != batch_well_id:
                    raise RuntimeError("The import target well changed during preparation; nothing was saved")

                pipeline_stage = self._queue_stage("ui_preview")
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

                if entry.status == CANCELLED:
                    raise RuntimeError("Cancelled before saving")
                pipeline_stage = self._queue_stage("identity")
                identity_problem = queue.verify_identity(entry)      # M84: same bytes as previewed
                if identity_problem:
                    raise RuntimeError(identity_problem)
                preview.apply_review_changes(extracted)
                # Decisions and edits are now part of the audit payload and
                # the exact canonical object sent to the atomic save boundary.
                pipeline_stage = self._queue_stage("persistence")
                self.import_status.setText(f"Importing {os.path.basename(source)} - Atomic transaction...")
                result = self._do_import(extracted, refresh_ui=False)
                result["file"] = source
                result["import_report"] = import_report_dict
                results.append(result)

                result_status = result.get("status", ImportStatus.PERSISTENCE_ERROR.value)
                if result_status in {ImportStatus.ACCEPT.value, ImportStatus.REVIEW_REQUIRED.value}:
                    successful_files.append(
                        f"{os.path.basename(source)} [{result_status}]" + self._saved_summary(result)
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
                    "identity": "import.file_identity",
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
                    "details": [f"❌ {os.path.basename(source)}: {exc}"] + self._pdf_split_details(pdf_split_info),
                    "error": str(exc),
                }
                if pdf_split_info:
                    err_result.update(pdf_split_info)
                results.append(err_result)
                failed_files.append(f"{os.path.basename(source)}: {exc}")
                if dialog is not None:
                    dialog.deleteLater()
            finally:
                if len(results) > results_before:
                    results[-1]["queue_status"] = queue.finish(entry, results[-1])
                else:
                    entry.status, entry.stage = FAILED, "no result"
                    entry.diagnostics.append("The pipeline produced no result for this file.")
                self._queue_current = None
                self._refresh_queue_view()
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
        summary_text += "\n" + self._queue().summary_text()
        self.batch_summary.setPlainText(summary_text)
        self.import_status.setText(
            f"Batch done: {len(successful_files)} success, {len(failed_files)} failed - See preview summary"
        )
        self.import_completed.emit(results)
        if failed_files and not successful_files:
            QMessageBox.warning(self, "Batch Import", summary_text)
        else:
            self.accept()
