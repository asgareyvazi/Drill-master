"""Portable regressions for formula-backed DDR date extraction.

The fixture is a generic OEOC-style workbook, not a certification claim for
any particular report.  Real OEOC acceptance remains environment-gated.
"""

from __future__ import annotations

import json
from pathlib import Path

from openpyxl import load_workbook

from core.excel_intelligence import ExcelIntelligence
from core.import_ir import raw_document_from_workbook


REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx"
TEMPLATE = REPO / "templates" / "OEOC_DDR_v3.json"


def test_formula_and_cached_views_preserve_date_and_provenance():
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    formula_workbook = load_workbook(FIXTURE, data_only=False, read_only=False)
    cached_workbook = load_workbook(FIXTURE, data_only=True, read_only=False)
    try:
        report = ExcelIntelligence(
            formula_workbook,
            template,
            source_file=str(FIXTURE.resolve()),
            cached_workbook=cached_workbook,
        ).extract()
    finally:
        formula_workbook.close()
        cached_workbook.close()

    assert report.canonical_json["daily_report"]["report_date"] == "2024-10-22"
    provenance = report.field_provenance["daily_report.report_date"]
    assert provenance["source_file"] == str(FIXTURE.resolve())
    assert provenance["source_cell"]
    assert provenance["source_row"]
    assert provenance["source_column"]
    assert provenance["original_value"] == [2024, "Oct", 22]
    assert provenance["normalized_value"] == "2024-10-22"
    assert provenance["source_header"]
    assert "merged_cell" in provenance
    assert provenance["components"]

    formula_ir_workbook = load_workbook(FIXTURE, data_only=False, read_only=False)
    formula_ir = raw_document_from_workbook(formula_ir_workbook, cached_workbook=None)
    try:
        formula_cells = {
            cell.location.cell: cell
            for cell in formula_ir.cells
            if cell.location.sheet == "DDR Data" and cell.location.cell in {"G7", "H7", "I7"}
        }
        assert formula_cells["G7"].formula
        assert formula_cells["H7"].formula
        assert formula_cells["I7"].formula
        assert formula_cells["G7"].original_value == formula_cells["G7"].value
    finally:
        # The workbook is held by the IR adapter for the duration of this
        # assertion; close it explicitly rather than relying on GC.
        formula_ir_workbook.close()


def test_invalid_formula_duplicate_cannot_erase_valid_date_components():
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    workbook = load_workbook(FIXTURE, data_only=False, read_only=False)
    try:
        report = ExcelIntelligence(workbook, template, source_file=str(FIXTURE.resolve())).extract()
    finally:
        workbook.close()

    daily = report.canonical_json["daily_report"]
    assert daily["report_year"] == 2024
    assert daily["report_month"] == "Oct"
    assert daily["report_day"] == 22
    assert daily["report_date"] == "2024-10-22"
    assert report.field_provenance["daily_report.report_date"]["normalized_value"] == "2024-10-22"
