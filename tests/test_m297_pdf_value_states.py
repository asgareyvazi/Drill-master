"""M297: header value states on the supported PDF routes (SYNTHETIC documents only).

Routes: a synthetic MinerU document through ``ddr_import_pipeline.mineru_extracted`` (the external MinerU engine is
NOT installed, so the real engine is NOT RUN), and the native PDF fallback on a PyMuPDF-drawn synthetic PDF.
Contract (``core.ddr_import_value_states``): a comma or unit suffix is never interpreted; an explicit N/A becomes a
recorded state after the operator accepts it; a mapped cell read as blank is a BLANK_EXTRACTION review item and
never NOT_REPORTED automatically; a value read by OCR always goes to review (OCR gated by P4/P5); a field fed by
two different source cells is AMBIGUOUS. No real DDR or confidential PDF is used.
"""
from __future__ import annotations

import warnings
from types import SimpleNamespace

import pytest

from core import ddr_import_pipeline as pipe
from core import ddr_import_value_states as ivs
from core import ddr_value_states as vs
from core.mineru_engine import DocumentTable, MinerUDocument, Provenance

HEADERS = ["Report Date", "Depth @ 0:00", "Depth @ 6:00", "Depth @ 24:00", "MW (PCF)"]


def _mineru(row, *, method="auto", extraction_method=None, extra_tables=()):
    table = DocumentTable(HEADERS, [row], Provenance("synthetic.pdf", source_page=1,
                                                     extraction_method=extraction_method), name="report header")
    document = MinerUDocument(source_file="synthetic.pdf", backend="mineru", method=method,
                              tables=[table, *extra_tables])
    return pipe.mineru_extracted("synthetic.pdf", SimpleNamespace(document=document, success=True, diagnostics={},
                                                                   error=None))


def _decide(extracted, accept=()):
    from core.import_quality import apply_review_decisions

    rows = extracted["metadata"]["review_matrix"]
    for row in rows:
        row["decision"] = "ACCEPT" if row.get("target_field") in accept else "DEFER"
    apply_review_decisions(extracted, rows)
    return extracted


@pytest.fixture
def target(tmp_path):
    from PySide6.QtWidgets import QApplication

    from core.database import DatabaseManager, Project, Well

    QApplication.instance() or QApplication([])
    db = DatabaseManager()
    db.db_path = str(tmp_path / "m297.db")
    assert db.initialize()
    with db.session_scope() as session:
        well = Well(name="M297 selected", code="M297", project_id=session.query(Project).first().id)
        session.add(well)
        session.flush()
        well_id = well.id
    yield db, well_id
    db.close()


def _import(db, well_id, extracted):
    from core.ddr_import_service import DDRImportService
    from core.ddr_well_identity import CHOOSE_SELECTED, make_decision

    extracted.setdefault("well_info", {})
    service = DDRImportService(db, well_id)
    assessment = service.assess_well_identity(extracted["well_info"])
    if assessment.requires_decision:                       # a synthetic header without a well name needs none
        extracted["metadata"]["well_identity_decision"] = make_decision(assessment, CHOOSE_SELECTED, "M297 test")
    return service.import_records(extracted)


def _value_state_items(db, well, report):
    return {i["target_field"]: i for i in db.get_import_review_items(well, report_id=report)
            if i["review_type"] == "value_state"}


def test_pdf_route_plan_comma_unit_blank_and_token():
    extracted = _mineru(["2026-10-01", "1,500", "", "N/A", "12.5 ppg"])
    assert extracted["daily_report"]["depth_0000"] == 1500.0            # what the extractor produced (D86 gap)
    plan = ivs.prepare(_decide(extracted, accept=("daily_report.depth_2400",)))
    assert plan["route"] == "pdf"
    outcomes = {field: entry["outcome"] for field, entry in plan["fields"].items()}
    assert outcomes == {"depth_0000": ivs.AMBIGUOUS, "depth_0600": ivs.BLANK_EXTRACTION,
                        "depth_2400": ivs.TOKEN, "mw_pcf": ivs.AMBIGUOUS}
    report = extracted["daily_report"]
    assert "depth_0000" not in report and "depth_0600" not in report and "mw_pcf" not in report
    assert report["depth_2400"] is None and plan["tokens"] == ["depth_2400"]
    blank = next(r for r in extracted["metadata"]["review_decisions"] if r["target_field"] == "daily_report.depth_0600")
    assert blank["classification"] == "value-state-blank-extraction" and "NOT_REPORTED is not assumed" in blank["reason"]
    assert (blank["page"], blank["row"]) == (1, 1) and "column 3" in blank["source_cell"]


def test_pdf_ocr_values_always_go_to_review():
    for kwargs in ({"method": "ocr"}, {"extraction_method": "tesseract-ocr"}):
        extracted = _mineru(["2026-10-01", "155", "310", "225", "70"], **kwargs)
        plan = ivs.prepare(_decide(extracted))
        assert set(plan["ambiguous"]) == {"depth_0000", "depth_0600", "depth_2400", "mw_pcf"}, kwargs
        assert all("OCR" in plan["fields"][f]["reason"] for f in plan["ambiguous"])
        assert not any(f in extracted["daily_report"] for f in plan["ambiguous"])


def test_pdf_clean_numbers_are_stored_without_review():
    extracted = _mineru(["2026-10-01", "155", "310", "225", "70"])
    plan = ivs.prepare(_decide(extracted))
    assert plan["ambiguous"] == [] and plan["tokens"] == []
    assert {f: extracted["daily_report"][f] for f in ("depth_0000", "depth_0600", "depth_2400", "mw_pcf")} == \
        {"depth_0000": 155.0, "depth_0600": 310.0, "depth_2400": 225.0, "mw_pcf": 70.0}


def test_two_different_source_cells_for_one_field_are_ambiguous():
    extracted = {"daily_report": {"depth_2400": 225.0}, "metadata": {"mineru_provenance": [
        {"canonical_field": "daily_report.depth_2400", "original_value": "225", "normalized_value": 225.0,
         "source_page": 1}, {"canonical_field": "daily_report.depth_2400", "original_value": "252",
                             "normalized_value": 252.0, "source_page": 2}]}}
    plan = ivs.prepare(extracted)
    assert plan["fields"]["depth_2400"]["outcome"] == ivs.AMBIGUOUS and "depth_2400" not in extracted["daily_report"]


def test_pdf_import_persists_states_and_review_items(target):
    db, well = target
    extracted = _decide(_mineru(["2026-10-01", "1,500", "", "N/A", "12.5 ppg"]), accept=("daily_report.depth_2400",))
    result = _import(db, well, extracted)
    report = result["report_id"]
    assert report and result["status"] == "REVIEW_REQUIRED", result["details"]
    states = vs.states(db, report)
    assert (states["depth_0000"]["value"], states["depth_0000"]["pending_review"]) == (None, "1,500")
    assert (states["depth_0600"]["value"], states["depth_0600"]["pending_review"]) == (None, "")
    assert not states["depth_0600"]["recorded"]                       # a blank extraction is never asserted
    assert (states["depth_2400"]["state"], states["depth_2400"]["source"]) == (vs.NOT_APPLICABLE, "import")
    assert (states["mw_pcf"]["value"], states["mw_pcf"]["pending_review"]) == (None, "12.5 ppg")
    items = _value_state_items(db, well, report)
    assert set(items) == {"daily_report.depth_0000", "daily_report.depth_0600", "daily_report.mw_pcf"}
    assert all(item["state"] == "DEFERRED_UNRESOLVED" for item in items.values())


def test_native_pdf_fallback_route_keeps_comma_values_out(target, tmp_path):
    fitz = pytest.importorskip("fitz")
    from core.ddr_import_service import DDRImportService
    from core.import_router import route_file
    from dialogs.excel_import_dialog import has_meaningful_canonical_data

    path = tmp_path / "synthetic_header.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 40), "SYNTHETIC DRILLING REPORT - TEST ONLY", fontsize=8)
    page.insert_text((50, 55), "report header", fontsize=9)
    for y, cells in ((80, HEADERS), (94, ["2026-10-01", "1,500", "310", "225", "70"])):
        for x, text in zip((50, 140, 230, 320, 410), cells):
            page.insert_text((x, y), text, fontsize=9)
    doc.save(path)
    service = DDRImportService()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = pipe.prepare_import(str(path), route=route_file, template_matcher=service._auto_match_template,
                                  extract_file=service.extract_file, meaningful=has_meaningful_canonical_data)
    assert out.error is None, out.error
    assert out.extracted["metadata"]["source_provenance"]["backend"] == "pdf-native-fallback"
    report = out.extracted.get("daily_report") or {}
    if "depth_0000" not in report:
        pytest.fail(f"the native fallback did not map the synthetic header table: {sorted(report)}")
    plan = ivs.prepare(_decide(out.extracted))
    assert plan["route"] == "pdf" and plan["fields"]["depth_0000"]["outcome"] == ivs.AMBIGUOUS
    assert "depth_0000" not in out.extracted["daily_report"]
    assert out.extracted["daily_report"]["depth_2400"] == 225.0
