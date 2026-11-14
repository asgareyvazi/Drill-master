"""M176: DDR import route parity: one synthetic time log through every route, with full provenance.

Routes: XLSX profile (golden fixture), generic Excel (label/value proposals), smart template, native PDF
fallback (PyMuPDF-drawn synthetic PDF), and MinerU (a synthetic MinerU document; the external engine is NOT
installed, so the real engine is NOT RUN). Real-document acceptance is NOT RUN (no owner-authorized file).
"""
from __future__ import annotations

import hashlib
import shutil
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import ddr_import_pipeline as pipe
from core.ddr_continuation import analyse_time_rows
from core.mineru_engine import PROFILE_RULES_VERSION, DocumentTable, MinerUDocument, Provenance

fitz = pytest.importorskip("fitz")

FIXTURES = Path(__file__).parent / "fixtures"
HEADERS = ["From", "To", "Hrs", "Code", "Activity Description"]
ROWS = [["00:00", "06:00", "6", "DRL", "Drill ahead"], ["", "", "", "", "with full returns"],
        ["06:00", "08:00", "2", "TRIP", "POOH"]]
COLS = [50, 110, 170, 220, 290]


@pytest.fixture(scope="module")
def service():
    from PySide6.QtWidgets import QApplication
    from core.ddr_import_service import DDRImportService
    QApplication.instance() or QApplication([])
    return DDRImportService()


def _prepare(service, path):
    from core.import_router import route_file
    from dialogs.excel_import_dialog import has_meaningful_canonical_data
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = pipe.prepare_import(str(path), route=route_file, template_matcher=service._auto_match_template,
                                  extract_file=service.extract_file, meaningful=has_meaningful_canonical_data)
    assert out.error is None, out.error
    return out


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _mineru(tables):
    document = MinerUDocument(source_file="synthetic.pdf", backend="mineru", method="auto", tables=tables)
    return pipe.mineru_extracted("synthetic.pdf", SimpleNamespace(document=document, success=True,
                                                                   diagnostics={}, error=None))


def _pdf(path, pages):
    doc = fitz.open()
    for lines in pages:
        page = doc.new_page()
        page.insert_text((50, 40), "SYNTHETIC DRILLING REPORT - TEST ONLY", fontsize=8)
        page.insert_text((50, 55), "24 hrs time log", fontsize=9)
        y = 80
        for cells in lines:
            for x, text in zip(COLS, cells):
                if text:
                    page.insert_text((x, y), text, fontsize=9)
            y += 14
    doc.save(path)


def _layout_notes(review):
    return [r for r in review if "PDF layout" in str(r.get("reason"))]


def _check_provenance(provenance, path, route):
    assert provenance["contract"] == pipe.SOURCE_PROVENANCE_CONTRACT and provenance["route"] == route
    assert provenance["sha256"] == _sha(path) and provenance["size_bytes"] == Path(path).stat().st_size
    assert provenance["file_name"] == Path(path).name
    assert provenance["pipeline_version"] == pipe.PIPELINE_VERSION
    assert provenance["profile_rules_version"] == PROFILE_RULES_VERSION and provenance["header_rules_version"] == 1


# ---- route by route --------------------------------------------------------------------------------------
def test_mineru_route_keeps_the_continuation_for_review_with_page_cell_provenance():
    extracted = _mineru([DocumentTable(HEADERS, ROWS, Provenance("synthetic.pdf", source_page=2),
                                       name="24 hrs time log")])
    rows = extracted["time_logs_24h"]
    assert [r.get("activity_description") for r in rows] == ["Drill ahead", "with full returns", "POOH"]
    assert rows[2]["_source_cells"]["time_log.activity_description"] == {"page": 2, "row": 3, "column": 5}
    [continuation] = [a for a in analyse_time_rows(rows) if a.kind == "continuation"]
    assert continuation.eligible and continuation.parent_index == 0        # proposed, never merged silently


def test_native_pdf_route_reports_its_wrapped_line_join_and_records_the_file(service, tmp_path):
    path = tmp_path / "synthetic_ddr.pdf"
    _pdf(path, [[HEADERS] + ROWS])
    out = _prepare(service, path)
    rows = out.extracted["time_logs_24h"]
    assert [(str(r["time_from"]), r["activity_description"]) for r in rows] == \
        [("00:00:00", "Drill ahead with full returns"), ("06:00:00", "POOH")]
    [note] = _layout_notes(out.import_report["review"])                  # the join is visible, not silent
    assert (note["page"], note["row"], note["column"], note["original_value"]) == (1, 1, 5, "with full returns")
    assert note["decision"] == "REVIEW"
    _check_provenance(out.extracted["metadata"]["source_provenance"], path, "mineru")
    assert out.extracted["metadata"]["source_provenance"]["fallback_engine"] == "pdf_fallback"
    assert out.extracted["metadata"]["source_provenance"]["backend"] == "pdf-native-fallback"
    assert rows[1]["_source_cells"]["time_log.time_from"] == {"page": 1, "row": 2, "column": 1}


def test_native_pdf_multi_page_table_keeps_row_pages_and_join_positions(service, tmp_path):
    path = tmp_path / "multi_page.pdf"
    _pdf(path, [[HEADERS, ROWS[0], ["06:00", "08:00", "2", "TRIP", "POOH"]],
                [HEADERS, ["08:00", "12:00", "4", "DRL", "Drill to TD"], ["", "", "", "", "no losses"]]])
    out = _prepare(service, path)
    rows = out.extracted["time_logs_24h"]
    assert [r["activity_description"] for r in rows] == ["Drill ahead", "POOH", "Drill to TD no losses"]
    pages = [r["_source_cells"]["time_log.time_from"]["page"] for r in rows]
    assert pages == [1, 1, 2]                                             # per-row page of a joined table
    [note] = _layout_notes(out.import_report["review"])
    assert note["original_value"] == "no losses" and note["page"] == 2 and note["row"] == 3


def test_smart_template_route_keeps_source_rows_and_file_provenance(tmp_path):
    from dialogs.smart_template_dialog import SmartTemplateDialog
    cells = {(5, 1): "00:00", (5, 2): "06:00", (5, 3): 6, (5, 4): "Drill ahead", (6, 4): "with full returns",
             (7, 1): "06:00", (7, 2): "08:00", (7, 3): 2, (7, 4): "POOH"}
    logs = SmartTemplateDialog._parse_time_table(object(), cells, 4, 7, {"from": 1, "to": 2, "hrs": 3, "desc": 4})
    assert [log.get("_source_row") for log in logs] == [5, 6, 7]
    [continuation] = [a for a in analyse_time_rows(logs) if a.kind == "continuation"]
    assert continuation.eligible and continuation.parent_index == 0
    source = tmp_path / "smart.xlsx"
    shutil.copyfile(FIXTURES / "normal_ddr.xlsx", source)
    provenance = pipe.source_provenance(source, route="smart_template", extracted={"metadata": {}})
    _check_provenance(provenance, source, "smart_template")


def test_xlsx_profile_route_golden_fixture_provenance(service, tmp_path):
    path = tmp_path / "golden.xlsx"
    shutil.copyfile(FIXTURES / "synthetic_ddr_golden_a.xlsx", path)
    before = _sha(path)
    out = _prepare(service, path)
    _check_provenance(out.extracted["metadata"]["source_provenance"], path, "excel_intelligence")
    assert out.import_report["source_provenance"] == out.extracted["metadata"]["source_provenance"]
    review = out.import_report["review"]
    assert all(r.get("sheet") for r in review if r.get("review_type") != "continuation")
    assert _sha(path) == before                                           # the source is never modified


def test_generic_excel_route_is_label_value_only_and_reports_the_rest(service, tmp_path):
    import openpyxl
    path = tmp_path / "generic.xlsx"
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "DDR"
    sheet["A1"], sheet["B1"] = "Well Name", "SYN-176"
    sheet["A5"] = "24 HRS TIME LOG"
    for column, header in enumerate(HEADERS, 1):
        sheet.cell(6, column, header)
    for row, values in enumerate(ROWS, 7):
        for column, value in enumerate(values, 1):
            if value:
                sheet.cell(row, column, value)
    book.save(path)
    out = _prepare(service, path)
    # LIMITATION (documented in the parity matrix): only the first data row is proposed, as a label/value
    # proposal that needs confirmation; the rest of the table is reported, never silently dropped.
    assert len(out.extracted["time_logs_24h"]) == 1
    proposals = [r for r in out.import_report["review"] if str(r.get("canonical_field", "")).startswith("time_log")]
    assert proposals and all(r["decision"] == "REVIEW" for r in proposals)
    regions = out.extracted["metadata"]["unmapped_content"]["sheets"][0]["regions"]
    assert any(region["kind"] == "table-like" and region["range"] == "A5:E9" for region in regions)
    _check_provenance(out.extracted["metadata"]["source_provenance"], path, "excel_intelligence")


# ---- scenarios -------------------------------------------------------------------------------------------
def test_morning_heading_binds_the_morning_section_and_24h_stays_24h():
    rows = [["00:00", "06:00", "6", "Drill ahead"], ["06:00", "08:00", "2", "POOH"]]
    morning = _mineru([DocumentTable(["From", "To", "Hrs", "Activity"], rows, Provenance("s.pdf", source_page=1),
                                     name="morning time log")])
    assert [r["activity_description"] for r in morning["time_logs_morning"]] == ["Drill ahead", "POOH"]
    assert not morning.get("time_logs_24h") and not morning.get("document_tables")
    binding = morning["metadata"]["header_aliases"][0]
    assert binding["state"] == "SECTION_FROM_HEADING" and binding["section"] == "time_log_morning"
    day = _mineru([DocumentTable(["From", "To", "Hrs", "Activity"], rows, Provenance("s.pdf", source_page=1),
                                 name="24 hrs time log")])
    assert len(day["time_logs_24h"]) == 2 and not day.get("time_logs_morning")


def test_multi_table_document_maps_each_table_to_its_section():
    extracted = _mineru([
        DocumentTable(HEADERS, [ROWS[0], ROWS[2]], Provenance("s.pdf", source_page=1), name="24 hrs time log"),
        DocumentTable(["MW (ppg)"], [["10.2"]], Provenance("s.pdf", source_page=2), name="mud properties")])
    assert len(extracted["time_logs_24h"]) == 2
    assert extracted["mud_report"]["_source_cells"]["mud_report.mw"] == {"page": 2, "row": 1, "column": 1}


def test_mixed_headers_give_the_same_records():
    explicit = _mineru([DocumentTable(["From", "To", "Hrs", "Rig Activity"], [ROWS[0][:3] + ["Drill ahead"]],
                                      Provenance("s.pdf", source_page=1), name="24 hrs time log")])
    generic = _mineru([DocumentTable(["From", "To", "Hrs", "Activity"], [ROWS[0][:3] + ["Drill ahead"]],
                                     Provenance("s.pdf", source_page=1), name="24 hrs time log")])
    strip = lambda rows: [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]  # noqa: E731
    assert strip(explicit["time_logs_24h"]) == strip(generic["time_logs_24h"])


def test_missing_time_anchors_invent_no_times_and_mixed_tables_are_never_silent():
    extracted = _mineru([DocumentTable(["Hrs", "Activity"], [["6", "Drill"], ["2", "POOH"]],
                                       Provenance("s.pdf", source_page=1), name="24 hrs time log")])
    rows = extracted["time_logs_24h"]
    assert all(r.get("time_from") is None and r.get("time_to") is None for r in rows)    # no 00:00, no guess
    assert all("activity_description" not in r for r in rows)          # no anchor -> generic header not used
    mixed = _mineru([DocumentTable(["Bit No", "MW (ppg)", "From"], [["1", "10", "00:00"]],
                                   Provenance("s.pdf", source_page=1), name="stuff")])
    [notice] = [w for w in mixed["metadata"]["warnings"] if w.get("rule") == "document-table-not-stored-v1"]
    assert "NOT stored" in notice["message"] and "1 row(s)" in notice["message"]


def test_file_provenance_is_not_part_of_the_payload_fingerprint(tmp_path):
    from core.ddr_import_service import _source_fingerprint
    payload = {"daily_report": {"report_number": 1}, "metadata": {"source": "x"}}
    first = dict(payload, metadata=dict(payload["metadata"], source_provenance={"file_name": "a.xlsx"}))
    renamed = dict(payload, metadata=dict(payload["metadata"], source_provenance={"file_name": "b.xlsx"}))
    assert _source_fingerprint(first) == _source_fingerprint(renamed) == _source_fingerprint(payload)


def test_provenance_names_a_profile_only_when_the_route_applied_it(tmp_path):
    from core.ddr_report_profiles import ReportProfile
    profile = ReportProfile(key="syn-m176", version=4, name="Synthetic", report_format="pdf", aliases={}, units={},
                            date_formats=(), table_rules={})
    document = MinerUDocument(source_file="s.pdf", backend="mineru", method="auto", tables=[
        DocumentTable(HEADERS, [ROWS[0]], Provenance("s.pdf", source_page=1), name="24 hrs time log")])
    applied = pipe.mineru_extracted("s.pdf", SimpleNamespace(document=document, success=True, diagnostics={},
                                                              error=None), profile=profile)
    source = tmp_path / "s.pdf"
    source.write_bytes(b"%PDF-1.4 synthetic")
    assert pipe.source_provenance(source, route="mineru", extracted=applied)["profile"] == \
        {"key": "syn-m176", "version": 4}
    assert pipe.source_provenance(source, route="excel_intelligence", extracted={"metadata": {}})["profile"] is None


def test_unreadable_size_is_unknown_not_zero(tmp_path):
    provenance = pipe.source_provenance(tmp_path / "missing.pdf", route="mineru")
    assert provenance["size_bytes"] is None and provenance["sha256"] is None
