"""Certification regressions for the real workbook ReviewItem contract.

This is deliberately a source-level golden test: it does not confirm a PDF or
Windows run.  It confirms that the real workbook still has stable extraction
counts, that deterministic template cells are not incorrectly escalated, and
that every retained ambiguity carries a complete ReviewItem lineage record.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.excel_intelligence import ExcelIntelligence
from core.import_quality import ReviewItem
from core.mineru_engine import validate_canonical_payload


ROOT = Path(__file__).resolve().parents[1]


def _real_workbook_path() -> Path:
    candidates = sorted(
        path for path in ROOT.glob("*.xlsx")
        if "DDR" in path.name.upper()
    )
    if not candidates:
        pytest.skip("Real workbook is not available")
    return candidates[0]


def _report():
    openpyxl = pytest.importorskip("openpyxl")
    workbook_path = _real_workbook_path()
    template_paths = sorted((ROOT / "templates").glob("*.json"))
    template_path = next(
        (path for path in template_paths if "v3" in path.name.lower()),
        None,
    )
    if template_path is None:
        pytest.skip("Versioned Excel template is not available")
    workbook = openpyxl.load_workbook(workbook_path, data_only=True)
    try:
        return ExcelIntelligence(
            workbook,
            json.loads(template_path.read_text(encoding="utf-8")),
            source_file=str(workbook_path.resolve()),
        ).extract()
    finally:
        workbook.close()


def _review_rows(report):
    rows = []
    for result in report.field_results:
        if not (
            result.status != "OK"
            or result.certainty == "LOW"
            or result.canonical_field in report.source_tokens
        ):
            continue
        rows.append(
            ReviewItem.from_dict(
                {
                    "file": Path(report.raw_document.source_file).name,
                    "sheet": result.sheet,
                    "row": result.row,
                    "column": result.col,
                    "source_cell": result.cell,
                    "source_location": {
                        "file": report.raw_document.source_file,
                        "sheet": result.sheet,
                        "row": result.row,
                        "column": result.col,
                        "cell": result.cell,
                    },
                    "entity": result.canonical_field.split(".", 1)[0],
                    "field": result.canonical_field,
                    "original_value": report.source_tokens.get(
                        result.canonical_field, {}
                    ).get("original_value", result.original_value),
                    "normalized_value": None if result.canonical_field in report.source_tokens else result.value,
                    "expected_type": result.data_type,
                    "confidence": result.confidence,
                    "status": result.status,
                    "reason": result.reason,
                    "mapping_method": result.source or "excel-template",
                    "classification": "mapping-conflict" if result.status == "CONFLICT" else "source-review",
                }
            )
        )
    return rows


def test_real_workbook_golden_shape_and_semantic_validation():
    report = _report()
    # Golden counts are intentionally source-shape counts, not acceptance
    # claims. An extraction explosion/disappearance must update this test with
    # an explanation and a new audit artifact.
    assert report.tables_detected == 17
    assert report.total_rows_extracted == 147
    assert report.rejected_rows == 14
    # ``ImportReport.validation_errors`` counts source-level review states;
    # canonical validation must still have no typed/bounds errors.
    assert report.validation_errors == 9
    assert report.fields_detected == 141

    validation = validate_canonical_payload(report.canonical_json)
    assert validation.valid, validation.errors


def test_real_workbook_review_items_have_complete_lineage_and_keep_ambiguity():
    report = _report()
    rows = _review_rows(report)
    assert len(rows) == 29
    assert rows
    for item in rows:
        assert item.file
        assert item.sheet
        assert item.source_cell
        assert item.source_location
        assert item.entity
        assert item.field
        assert item.reason
        assert item.mapping_method
        assert item.expected_type
        assert item.classification

    # The anchored placeholder is retained as a reviewable source token; the
    # nearby casing number must never be accepted as water depth.
    water_depth = next(item for item in rows if item.field == "well_info.water_depth")
    assert water_depth.source_cell == "AQ6"
    assert water_depth.normalized_value is None
    assert report.canonical_json["well_info"]["water_depth"] is None


def test_duplicate_scalar_values_are_explicitly_classified_not_dropped():
    report = _report()
    assert report.duplicate_mappings
    assert all(item["status"] == "DUPLICATE_CONFIRMED" for item in report.duplicate_mappings)
    assert all(item["classification"] == "duplicate-same-value" for item in report.duplicate_mappings)
    assert all(item.get("source_cell") and item.get("primary") for item in report.duplicate_mappings)
