"""Environment-gated DDR acceptance tests.

These tests are intentionally not fixtures disguised as real acceptance.  CI
skips with an explicit reason unless the caller supplies the real DDR paths and
an externally managed MinerU installation:

    DRILLMASTER_TEST_DDR_XLSX=/real/DDR.xlsx
    DRILLMASTER_TEST_DDR_PDF=/real/DDR.pdf

The Excel test exercises the canonical extractor and atomic database boundary.
The PDF test exercises the external MinerU adapter, common IR, normalization,
review/provenance, and the same atomic boundary.  No path or date is invented
when a real document is unavailable.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPO / "templates" / "OEOC_DDR_v3.json"


def _env_file(name: str) -> Path:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"{name} is not set; real DDR acceptance is opt-in")
    path = Path(value).expanduser()
    if not path.is_file():
        pytest.fail(f"{name} does not point to a file: {path}")
    return path


def _db_manager():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from core.database import Base, DatabaseManager

    manager = DatabaseManager()
    manager.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(bind=manager.engine, autoflush=False, autocommit=False)
    return manager


def _seed_report(manager):
    from core.database import Company, DailyReport, Project, Section, Well

    session = manager.create_session()
    try:
        company = Company(name="Acceptance Company", code="ACCEPTANCE")
        session.add(company)
        session.flush()
        project = Project(name="Acceptance Project", code="ACCEPTANCE", company_id=company.id)
        session.add(project)
        session.flush()
        well = Well(name="Acceptance Well", code="ACCEPTANCE-WELL", project_id=project.id)
        session.add(well)
        session.flush()
        section = Section(name="Imported Section", well_id=well.id)
        session.add(section)
        session.flush()
        report = DailyReport(
            well_id=well.id,
            section_id=section.id,
            report_number=1,
            report_date=date(2024, 1, 1),
            status="Draft",
        )
        session.add(report)
        session.commit()
        return well.id, report.id
    finally:
        session.close()


def _assert_ir_details(raw_document):
    payload = raw_document.to_dict(include_cells=True)
    assert payload["ir_version"] >= 2
    assert payload["source_file"]
    assert "tables_detail" in payload
    assert "cell_values" in payload
    assert "section_title_values" in payload
    # A source may legitimately have no formal title/unit, but the contract
    # must be serializable and deserializable without losing them when present.
    from core.import_ir import RawDocument

    restored = RawDocument.from_dict(payload)
    assert restored.source_file == raw_document.source_file
    assert len(restored.cells) == len(raw_document.cells)
    assert len(restored.tables) == len(raw_document.tables)
    for cell in restored.cells[:25]:
        assert cell.location.file == raw_document.source_file
        assert cell.location.sheet
        assert cell.location.row is not None
        assert cell.location.column is not None
        assert cell.original_value == cell.value


def _assert_review_contract(rows):
    from core.import_quality import ImportReviewMatrix, ReviewItem

    matrix = ImportReviewMatrix.from_rows(rows)
    assert len(matrix.items) == len(rows)
    for item in matrix.items:
        payload = item.to_dict()
        restored = ReviewItem.from_dict(payload)
        assert restored.target_field == item.target_field
        assert restored.original_value == item.original_value
        assert restored.normalized_value == item.normalized_value
        assert restored.file == item.file
        assert restored.file and restored.source_document
        assert restored.source_location
        assert restored.decision not in {"ACCEPT", "CONFIRMED"}
        assert restored.review_state != "accepted"
        assert restored.status
        assert restored.expected_type


def _assert_canonical_provenance(report, source: Path):
    source_file = str(source.resolve())
    for canonical_field, provenance in report.field_provenance.items():
        assert provenance.get("source_file") == source_file, canonical_field
        assert provenance.get("source_sheet"), canonical_field
        assert provenance.get("source_cell"), canonical_field
        assert provenance.get("source_row") is not None, canonical_field
        assert provenance.get("source_column") is not None, canonical_field
        assert "original_value" in provenance, canonical_field
        assert "normalized_value" in provenance, canonical_field
        assert provenance.get("extraction_method"), canonical_field
        assert provenance.get("confidence") is not None, canonical_field
        assert provenance.get("validation_state"), canonical_field
        assert provenance.get("review_state") in {"accepted", "review"}, canonical_field

    for table_name, rows in report.canonical_json.items():
        if not isinstance(rows, list):
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            assert row.get("_source_file") == source_file, f"{table_name}[{index}]"
            assert row.get("_source_sheet"), f"{table_name}[{index}]"
            assert row.get("_source_row") is not None, f"{table_name}[{index}]"
            assert row.get("_source_cells"), f"{table_name}[{index}]"
            location = row.get("_source_location") or {}
            assert location.get("file") == source_file, f"{table_name}[{index}]"
            assert location.get("sheet") == row["_source_sheet"], f"{table_name}[{index}]"
            assert location.get("row") == row["_source_row"], f"{table_name}[{index}]"
            assert location.get("cells") == row["_source_cells"], f"{table_name}[{index}]"


@pytest.mark.integration
def test_real_ddr_excel_canonical_ir_review_and_atomic_db():
    source = _env_file("DRILLMASTER_TEST_DDR_XLSX")
    if not TEMPLATE_PATH.is_file():
        pytest.fail(f"Canonical OEOC template is missing: {TEMPLATE_PATH}")

    from openpyxl import load_workbook
    from core.ddr_import_service import DDRImportService
    from core.database import AuditLog, DailyReport

    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    workbook = load_workbook(source, data_only=True, read_only=False)
    try:
        expected_sheets = {
            part.replace("_", " ").lower()
            for key in template
            if key.startswith("sheet_")
            for part in [key.split("_", 2)[-1]]
        }
        actual_sheets = {sheet.title.lower() for sheet in workbook.worksheets}
        if not expected_sheets.intersection(actual_sheets):
            pytest.fail(
                "The supplied DDR workbook does not match the canonical OEOC "
                f"template; sheets={sorted(actual_sheets)}"
            )
    finally:
        workbook.close()

    manager = _db_manager()
    well_id, _seed_report_id = _seed_report(manager)
    service = DDRImportService(manager, well_id)
    report, payload = service.extract_file(str(source.resolve()), template=template)

    assert report.raw_document is not None
    _assert_ir_details(report.raw_document)
    assert report.raw_document.metadata.get("engine") == "Excel"
    assert report.canonical_json, "Real Excel produced no canonical data"
    _assert_canonical_provenance(report, source)
    _assert_review_contract(payload["metadata"]["review_matrix"])

    # The known historical crash token must never become a float conversion
    # exception. If present, preserve it as a status-bearing review token.
    for token in report.source_tokens.values():
        if token.get("status") == "SOURCE_UNIT_PENDING":
            import math
            assert math.isfinite(float(token["normalized_value"]))
            assert token["normalized_value"] == token["original_value"]
            assert token["review"] is True
        elif token.get("status") == "SOURCE_UNIT_RESOLVED":
            assert token["source_unit"]
            from core.mud_records import mud_density_pcf
            expected, _lineage = mud_density_pcf({
                "mw": token["original_value"], "mw_unit": token["source_unit"],
            })
            assert token["normalized_value"] == pytest.approx(expected["mw"])
            assert token["review"] is False
        else:
            assert token.get("normalized_value") is None

    # Exercise the same service/orchestration path used by the desktop import,
    # not just the low-level table writer. Reviews, domain rows, and source
    # snapshots must share the transaction/audit boundary.
    imported = service.import_records(payload)
    assert imported.get("failed") == 0, imported
    assert imported.get("report_id")
    assert imported.get("imported", 0) > 0
    assert imported.get("status") in {"ACCEPT", "REVIEW_REQUIRED"}

    expected_date = report.canonical_json["daily_report"]["report_date"]
    with manager.session_scope() as session:
        saved_report = session.get(DailyReport, imported["report_id"])
        assert saved_report is not None
        assert saved_report.report_date.isoformat() == expected_date
        audit_rows = session.query(AuditLog).filter_by(
            action="ddr_import",
            entity_type="daily_report",
            entity_id=imported["report_id"],
        ).all()
        assert len(audit_rows) == 1
        audit = json.loads(audit_rows[0].details)
        assert audit["source"]["metadata"]["raw_ir"]["source_file"] == str(source.resolve())
        assert audit["source"]["metadata"]["field_provenance"]
        assert audit["result"].get("review_items", []) == imported.get("review_items", [])

    mud_source = report.canonical_json.get("mud_report") or {}
    if mud_source.get("mw") is not None:
        from core.mud_records import mud_density_pcf
        expected_mud, _lineage = mud_density_pcf(dict(mud_source))
        saved_mud = manager.get_mud_report(report_id=imported["report_id"])
        assert saved_mud is not None
        assert saved_mud["mw"] == pytest.approx(expected_mud["mw"])
    manager.close()


@pytest.mark.integration
def test_real_ddr_pdf_mineru_common_ir_review_and_atomic_db():
    source = _env_file("DRILLMASTER_TEST_DDR_PDF")
    from core.mineru_engine import DocumentNormalizer, MinerUAdapter

    adapter = MinerUAdapter()
    health = adapter.health_check()
    if not health.available:
        pytest.fail("ENVIRONMENT-BLOCKED: MinerU is unavailable for the explicitly requested PDF acceptance: " + str(health.error or health.to_dict()))
    result = adapter.parse_file(source)
    assert result.success, result.error
    assert result.document is not None
    assert result.document.raw_files, "MinerU produced no inspectable markdown/JSON/assets"

    normalized = DocumentNormalizer().normalize(result.document)
    assert normalized.raw_document is not None
    _assert_ir_details(normalized.raw_document)
    assert normalized.provenance, "Real PDF produced no canonical provenance"
    assert all(item.get("source_file") == str(source.resolve()) for item in normalized.provenance)
    assert normalized.validation.valid, normalized.validation.errors

    review_rows = []
    for warning in normalized.warnings:
        source_info = warning.get("source") or {}
        review_rows.append(
            {
                "file": source.name,
                "sheet": source_info.get("source_sheet", ""),
                "page": source_info.get("source_page"),
                "detected_table": "MinerU document",
                "source_cell": (
                    f"page {source_info['source_page']}:row {source_info.get('source_row')}:column "
                    f"{source_info.get('source_column')}"
                    if source_info.get("source_page") is not None
                    else ""
                ),
                "coordinates": source_info.get("bounding_box"),
                "original_value": warning.get("value"),
                "normalized_value": warning.get("normalized_value"),
                "target_field": warning.get("field", ""),
                "confidence": source_info.get("confidence"),
                "decision": "REVIEW",
                "validation_state": "needs_review",
                "review_state": "unreviewed",
            }
        )
    _assert_review_contract(review_rows)

    # Persist the same canonical payload when the real DDR contains the
    # required report date.  Missing source dates remain a real acceptance
    # failure rather than being replaced with today's date.
    report_data = normalized.canonical_data.get("daily_report") or {}
    if not report_data.get("report_date"):
        pytest.fail("Real DDR PDF has no canonical daily_report.report_date; refusing to invent one")
    manager = _db_manager()
    well_id, report_id = _seed_report(manager)
    persisted = manager.save_imported_multi_tab_data_atomic(
        well_id, report_id, dict(normalized.canonical_data)
    )
    assert persisted.get("failed") == 0, persisted
    assert persisted.get("imported", 0) > 0, persisted

    # This is the regression guard for the old numeric conversion crash.
    for table in normalized.raw_document.tables:
        for row in table.rows:
            for cell in row:
                if str(cell.original_value).strip().lower() == "drilling data":
                    assert cell.validation_state in {"unvalidated", "needs_review", "valid"}
                    assert cell.review_state in {"unreviewed", "review", "accepted"}
