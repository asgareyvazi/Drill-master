"""M71: background preparation of one DDR source file.

``prepare_import`` is the heavy, read-only part of the import pipeline:
routing, MinerU normalization or the PDF-native fallback, workbook
extraction, profile rules, validation, review rows, the column-mapping
report and an explainable profile suggestion.  It runs in a worker thread
and must never touch a widget, a ``QApplication`` or a database session:
everything it needs (profile objects, the expected well *name*, callables)
is resolved on the GUI thread first, and it returns a plain
``PreparedImport`` DTO.  Preview, the user's decision and the atomic save
stay on the GUI thread (``dialogs.excel_import_dialog``).

Cancellation is cooperative: ``should_cancel`` is checked between steps.
A single parse call (openpyxl, PDF text layer) cannot be interrupted midway;
a cancel request takes effect at the next step boundary, always before
persistence.
"""
from __future__ import annotations

import logging
import os
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core import ddr_pdf_split
from core.import_diagnostics import ImportStatus
from core.import_quality import ImportValidator, TimeLogValidator, build_review_manifest, find_duplicates
from core.mineru_engine import (
    PROFILE_RULES_VERSION,
    DocumentNormalizer,
    MinerUError,
    MinerUNormalizationError,
    MinerUParseResult,
    parse_pdf_native_fallback,
)

logger = logging.getLogger(__name__)

# v2 (M148): validation applies the ddr-continuation-v1 contract to 24-hour and morning rows.
PIPELINE_VERSION = 2
STAGES = ("route", "open", "mapping", "validation", "meaningful_data")


class ImportCancelled(Exception):
    """Raised between steps when the user cancelled the running file."""


@dataclass
class PreparedImport:
    """Plain result of ``prepare_import``; safe to hand from the worker to the GUI."""
    source: str
    stage: str = "route"
    extracted: Optional[Dict[str, Any]] = None
    import_report: Dict[str, Any] = field(default_factory=dict)
    pdf_split_info: Dict[str, Any] = field(default_factory=dict)
    error: Optional[BaseException] = None
    error_status: str = ImportStatus.VALIDATION_ERROR.value
    cancelled: bool = False
    worker_thread: str = ""

    @property
    def ok(self) -> bool:
        return self.error is None and not self.cancelled and self.extracted is not None


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


# ---------------------------------------------------------------------------
# Columns and profile suggestion (explainable, never applied automatically)
# ---------------------------------------------------------------------------
def document_headers(document) -> List[str]:
    """Distinct non-empty table header labels of a parsed document, in reading order."""
    seen, headers = set(), []
    for table in getattr(document, "tables", None) or []:
        for label in getattr(table, "headers", None) or []:
            text = str(label or "").strip()
            if text and text.casefold() not in seen:
                seen.add(text.casefold())
                headers.append(text)
    return headers


def column_mapping_report(profile, headers: List[str]) -> Dict[str, Any]:
    """Every source column with its target and rule; unmapped columns are listed, never dropped."""
    from core.ddr_report_profiles import map_headers

    rows = map_headers(profile, list(headers))
    unmapped = [row["header"] for row in rows if not row["field"]]
    return {"columns": len(rows), "mapped": len(rows) - len(unmapped), "unmapped": unmapped, "rows": rows}


def suggest_profiles(profiles, headers: List[str], limit: int = 3) -> List[Dict[str, Any]]:
    """Rank report profiles by how many document headers their own aliases resolve.

    Only profile aliases count (canonical aliases match for every profile and
    explain nothing).  Each suggestion carries the matched and unmatched
    headers so the user can see why; ties keep the input order.  The caller
    shows suggestions; it never switches the active profile by itself.
    """
    if not headers:
        return []
    ranked = []
    for order, profile in enumerate(profiles or []):
        if profile is None:
            continue
        matched = [h for h in headers if profile.resolve(h)]
        if not matched:
            continue
        ranked.append((-len(matched), order, {
            "key": profile.key, "version": profile.version, "name": profile.name,
            "matched": len(matched), "total": len(headers),
            "score": round(len(matched) / len(headers), 4),
            "matched_headers": matched,
            "unmatched_headers": [h for h in headers if h not in matched],
        }))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in ranked[:limit]]


# ---------------------------------------------------------------------------
# MinerU / PDF-native document -> canonical payload (moved from the dialog)
# ---------------------------------------------------------------------------
def mineru_extracted(source, parse_result, *, profile=None, source_label="MinerU", fallback_diagnostics=None):
    """Return canonical data and review metadata for a successful parse."""
    from core.ddr_import_service import _canonical_review_row

    if not parse_result or not parse_result.success or parse_result.document is None:
        raise MinerUError(parse_result.error if parse_result else "MinerU produced no result")
    normalizer = DocumentNormalizer(profile=profile)
    normalized = normalizer.normalize(parse_result.document)
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
        "review_manifest": build_review_manifest(review_rows),
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
        # M54: which report profile (if any) supplied mappings.
        "profile": (
            {"key": profile.key, "version": profile.version, "name": profile.name,
             "mappings": list(normalizer.profile_mappings),
             # M61: profile behaviour that shaped this result.
             "confidence_threshold": float(profile.confidence_threshold),
             "date_formats": list(profile.date_formats),
             "table_rules": dict(profile.table_rules),
             "continuation": bool(profile.continuation),
             "rules_version": PROFILE_RULES_VERSION}
            if profile is not None else None
        ),
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


def pdf_split_info(source, expected_well: Optional[str]) -> Dict[str, Any]:
    """M52: report split of a PDF (several daily reports in one file), before any extraction."""
    if not str(source).lower().endswith(".pdf"):
        return {}
    try:
        split = ddr_pdf_split.analyse_pdf(source, expected_well=expected_well)
    except ddr_pdf_split.PdfSplitError as exc:
        return {"pdf_split_error": str(exc)}
    return {"pdf_split": split.to_json()}


# ---------------------------------------------------------------------------
# The worker entry point
# ---------------------------------------------------------------------------
def prepare_import(
    source: str,
    *,
    parse_result=None,
    profile=None,
    profiles=(),
    expected_well: Optional[str] = None,
    route: Callable,
    template_matcher: Callable,
    extract_file: Callable,
    meaningful: Callable[[dict], bool],
    should_cancel: Callable[[], bool] = lambda: False,
) -> PreparedImport:
    """Run every read-only step for ``source``; return a DTO, never raise."""
    out = PreparedImport(source=str(source), worker_thread=threading.current_thread().name)

    def step(name):
        if should_cancel():
            raise ImportCancelled(f"cancelled before {name}")
        out.stage = name

    headers: List[str] = []
    try:
        step("route")
        out.pdf_split_info = pdf_split_info(source, expected_well)
        decision = route(source, template_matcher=template_matcher)
        path, extracted = source, None
        step("open")
        if decision.engine == "mineru" and parse_result and parse_result.success:
            headers = document_headers(parse_result.document)
            extracted = mineru_extracted(source, parse_result, profile=profile)
        elif decision.engine == "mineru" and decision.fallback_engine == "pdf_fallback":
            primary_reason = parse_result.error if parse_result else "MinerU was unavailable"
            logger.warning("MinerU PDF fallback: file=%s reason=%s", Path(source).name, primary_reason)
            try:
                fallback_document = parse_pdf_native_fallback(
                    source, continuation=(profile.continuation if profile is not None else True))
                headers = document_headers(fallback_document)
                step("open")
                extracted = mineru_extracted(
                    source,
                    MinerUParseResult(source_file=str(source), success=True, document=fallback_document),
                    profile=profile,
                    source_label="PDF native fallback",
                    fallback_diagnostics={
                        "primary": {"error_type": parse_result.error_type if parse_result else "not-run",
                                    "error": primary_reason},
                        "fallback": {
                            "engine": fallback_document.method,
                            "pages": fallback_document.page_count,
                            "tables": fallback_document.table_count,
                            # M54: explicit scanned-page / OCR state.
                            "scanned_pages": fallback_document.metadata.get("scanned_pages", []),
                            "ocr": fallback_document.metadata.get("ocr"),
                            "warning": fallback_document.metadata.get("warning"),
                        },
                    },
                )
            except ImportCancelled:
                raise
            except Exception as fallback_exc:
                raise MinerUError(
                    "PDF_IMPORT_FAILED: MinerU cause: "
                    f"{primary_reason}; PDF fallback cause: {fallback_exc}"
                ) from fallback_exc
        elif decision.engine == "mineru" and decision.fallback_engine == "excel_intelligence":
            reason = parse_result.error if parse_result else "MinerU was unavailable"
            logger.warning("MinerU XLSX fallback to existing importer: file=%s reason=%s", Path(source).name, reason)
        elif decision.engine == "mineru":
            reason = parse_result.error if parse_result else "MinerU worker did not return a result"
            raise MinerUError(
                f"MinerU could not parse {Path(source).name}: {reason}. "
                "Configure MINERU_EXECUTABLE or MINERU_PYTHON in Settings/environment."
            )

        # Known structured workbooks: openpyxl -> ExcelIntelligence -> canonical JSON.
        if extracted is None and decision.engine == "excel_intelligence":
            step("mapping")
            _rep, extracted = extract_file(path)

        if extracted is None:
            if decision.engine == "csv":
                from core.document_import import csv_to_xlsx
                clean = Path(tempfile.gettempdir()) / (Path(source).stem + "_csv_import.xlsx")
                csv_to_xlsx(source, clean)
            elif decision.engine == "unsupported":
                raise ValueError(decision.reason)
            elif str(path).lower().endswith(".xls"):
                raise ValueError("Legacy .xls requires conversion to .xlsx before import")
            if decision.engine in {"csv", "mineru"}:
                raise ValueError(
                    "No canonical template was available after the "
                    f"{decision.engine} fallback; import stopped before persistence"
                )
            raise ValueError(f"No canonical payload for engine {decision.engine!r}")

        step("validation")
        out.import_report = _validate(source, extracted)
        if headers:
            columns = column_mapping_report(profile, headers)
            out.import_report["column_mapping"] = columns
            out.import_report["profile_suggestions"] = suggest_profiles(profiles, headers)
            # Kept with the import evidence: every source column and its rule.
            if isinstance(extracted.get("metadata"), dict):
                extracted["metadata"]["column_mapping"] = columns
        out.import_report["pipeline_version"] = PIPELINE_VERSION

        if not meaningful(extracted):
            out.stage = "meaningful_data"
            raise ValueError("No meaningful canonical report data was detected")
        out.import_report.update(out.pdf_split_info)          # M52: shown in the preview
        step("validation")                                    # last cancel point before the GUI review
        out.extracted = extracted
    except ImportCancelled as exc:
        out.cancelled, out.error, out.extracted = True, exc, None
    except Exception as exc:                                   # reported per file by the dialog
        out.error, out.extracted = exc, None
        logger.info("DDR preparation stopped for %s at %s: %s", os.path.basename(str(source)), out.stage, exc)
    return out


def continuation_allowed(extracted) -> bool:
    """M148 condition 7: the report profile decides whether continuation rows may be attached at all.

    The decision is recorded in ``metadata.continuation_allowed`` so the review decisions applied later use the
    same answer as the preview.
    """
    metadata = extracted.get("metadata")
    if not isinstance(metadata, dict):
        return True                     # no metadata, no profile: the default of every later step
    if "continuation_allowed" not in metadata:
        profile = metadata.get("profile") if isinstance(metadata.get("profile"), dict) else None
        metadata["continuation_allowed"] = bool(profile.get("continuation", True)) if profile else True
    return bool(metadata["continuation_allowed"])


def _validate(source, extracted) -> Dict[str, Any]:
    """Existing quality and time-log validation; review rows tagged with the file."""
    report_data = extracted.get("daily_report", {})
    quality = ImportValidator.validate_rows([report_data], "daily_report", "Daily Report")
    time_logs = extracted.get("time_logs_24h", []) or []
    allowed = continuation_allowed(extracted)
    time_report = TimeLogValidator.validate_logs(time_logs, sheet="Time Logs 24H", continuation_allowed=allowed)
    quality.total += time_report.total
    quality.issues.extend(time_report.issues)
    for item in time_report.review.items:
        quality.review.items.append(item)
    # M152: morning rows follow the same continuation contract (they were classified only at persistence).
    from core.ddr_continuation import continuation_review_rows
    for payload in continuation_review_rows(extracted.get("time_logs_morning") or [], collection="time_logs_morning",
                                            continuation_allowed=allowed, sheet="Time Logs 06:00"):
        quality.review.add(**payload)
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

    report = quality.as_dict()
    if metadata.get("source") in {"MinerU", "PDF native fallback"}:
        report.update({
            "source_engine": "MinerU",
            "backend": metadata.get("backend", ""),
            "method": metadata.get("method", ""),
            "pages": metadata.get("pages", 0),
            "tables": metadata.get("tables", 0),
            "fields_extracted": metadata.get("fields_extracted", 0),
            "warnings": len(metadata.get("warnings", [])),
        })
        # The preview's scanned-page / OCR note reads this from the report.
        report["fallback_diagnostics"] = metadata.get("fallback_diagnostics") or {}
    return report
