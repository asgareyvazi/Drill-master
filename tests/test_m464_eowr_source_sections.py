"""M464-M466: the EOWR renders bit records, BHA components, 24-hour and morning time logs, material requests and
equipment logs from the stored rows of the selected well (SYNTHETIC data only).

Checked: well isolation, chronology, sources (table + id + daily report), units as stored, missing values as "—",
HTML escaping of stored text, unknown payload keys kept, empty payloads NOT_RECORDED, malformed payloads
NOT_RENDERED with their ids, a failed table QUERY_FAILED (the report still renders), period scoping with undated
records excluded and counted, and the same rows in HTML, Excel and CSV.
"""
from __future__ import annotations

import csv
import json
import os
from datetime import date, time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core import eowr_sections as es  # noqa: E402
from core import report_engine as engines  # noqa: E402
from core import report_sections as rs  # noqa: E402
from core.database import (BHAReport, BitReport, DailyReport, EquipmentLog, MaterialRequest,  # noqa: E402
                           TimeLog24H, TimeLogMorning)
from tests.test_m70_integrity import _open, _seed  # noqa: E402

BIT_UI = {"Bit No": "SYN-3", "Size (in)": "12.25", "Manufacture": "SYN-MFR", "Type": "PDC", "IADC Code": "M223",
          "Depth In (m)": "1200", "Depth Out (m)": "1850", "Metres Drilled": "650", "Hours": "",
          "ROP (m/hr)": "21.7", "Dull Grade": "1-2-WT-A-X-I-NO-TD", "Reason Pulled": "TD",
          "Remarks": "<script>alert(1)</script>"}
BIT_IMPORTED = {"bit_no": "SYN-4", "bit_size": 8.5, "depth_in": 1850.0, "nozzles_custom": "3x16"}


@pytest.fixture
def world(tmp_path, monkeypatch):
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    manager = _open(tmp_path / "m464.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    well, _bore = ids["A"]
    other, _ = ids["B"]
    with manager.session_scope() as s:
        r1 = DailyReport(well_id=well, report_date=date(2026, 1, 2), report_number=7)
        r2 = DailyReport(well_id=well, report_date=date(2026, 1, 5), report_number=8)
        rb = DailyReport(well_id=other, report_date=date(2026, 1, 2), report_number=1)
        s.add_all([r1, r2, rb])
        s.flush()
        # inserted out of chronological order on purpose
        s.add(BitReport(well_id=well, report_id=r2.id, report_date=date(2026, 1, 5), report_name="SYN later",
                        bit_records_json=json.dumps([BIT_IMPORTED])))
        s.add(BitReport(well_id=well, report_id=r1.id, report_date=date(2026, 1, 2), report_name="SYN first",
                        bit_records_json=json.dumps([BIT_UI])))
        s.add(BHAReport(well_id=well, report_id=r1.id, bha_name="SYN BHA 1", bha_data_json=[
            {"Component Name": "SYN bit sub", "Tool Type": "Bit Sub", "OD (in)": "8.0", "Length (m)": "0.9"},
            {"Component Name": "SYN collar", "Tool Type": "Drill Collar", "OD (in)": "8.0", "ID (in)": "2.8",
             "Length (m)": "9.1"}]))
        s.add(BHAReport(well_id=well, report_id=r2.id, bha_name="SYN legacy",
                        bha_data_json={"Run A": [{"Component Name": "SYN motor", "Length (m)": "7.5"}]}))
        s.add(TimeLog24H(report_id=r2.id, time_from=time(0, 0), time_to=time(6, 0), duration=6.0,
                         main_phase="SYN-DRL", activity_description="SYN drill day 2"))
        s.add(TimeLog24H(report_id=r1.id, time_from=time(12, 0), time_to=time(18, 0), duration=6.0,
                         activity_description="SYN afternoon day 1", is_npt=True, npt_category="SYN-WAIT"))
        s.add(TimeLog24H(report_id=r1.id, time_from=time(6, 0), time_to=time(12, 0), duration=None,
                         activity_description="SYN morning day 1"))
        s.add(TimeLogMorning(report_id=r2.id, time_from=time(0, 0), time_to=time(3, 0), duration=3.0,
                             activity_description="SYN tour day 2"))
        s.add(MaterialRequest(well_id=well, report_id=r2.id, request_date=date(2026, 1, 5),
                              requested_items="SYN barite", requested_quantity=40.0, requested_unit="sx",
                              outstanding_quantity=10.0, status="Pending"))
        s.add(MaterialRequest(well_id=well, request_date=date(2026, 1, 1), requested_items="SYN bentonite",
                              requested_quantity=5.0, requested_unit="sx"))
        s.add(EquipmentLog(well_id=well, equipment_name="SYN shaker", equipment_type="Solids control",
                           service_date=date(2026, 1, 3), hours_worked=22.5, status="Operational"))
        s.add(EquipmentLog(well_id=well, equipment_name="SYN undated pump", service_date=None))
        # well B: must never appear in well A's report
        s.add(BitReport(well_id=other, report_id=rb.id, report_date=date(2026, 1, 2), report_name="LEAK",
                        bit_records_json=json.dumps([{"Bit No": "SYN-LEAK-B"}])))
        s.add(TimeLog24H(report_id=rb.id, time_from=time(0, 0), time_to=time(1, 0), duration=1.0,
                         activity_description="SYN-LEAK-B log"))
        s.add(EquipmentLog(well_id=other, equipment_name="SYN-LEAK-B equipment"))
        s.add(MaterialRequest(well_id=other, request_date=date(2026, 1, 2), requested_items="SYN-LEAK-B item"))
        s.flush()
        refs = {"well": well, "other": other, "r1": r1.id, "r2": r2.id}
    yield manager, refs
    manager.close()


def _sections(engine):
    return {e["section"]: e for e in engine.last_provenance["sections"]}


def _html(manager, well, tmp_path, name="eowr.html", period=None):
    engine = engines.EOWRReportEngine(manager)
    path = tmp_path / name
    assert engine.generate(well, str(path), "html", period=period)
    return engine, path.read_text(encoding="utf-8")


def test_all_six_sections_render_with_sources_and_well_isolation(world, tmp_path):
    manager, refs = world
    engine, text = _html(manager, refs["well"], tmp_path)
    sections = _sections(engine)
    expected = {"12. Bit records": 2, "13. BHA components": 3, "14. 24-hour time logs": 3,
                "15. Morning tour time logs": 1, "16. Material requests": 2, "17. Equipment logs": 2}
    for title, rows in expected.items():
        assert sections[title]["status"] == rs.INCLUDED, (title, sections[title])
        assert sections[title]["rows"] == rows, title
    assert "SYN-LEAK-B" not in text
    for source in ("bit_reports id", "bha_reports id", "time_logs_24h id", "time_logs_morning id",
                   "material_requests id", "equipment_logs id"):
        assert source in text, source
    assert f"DDR id {refs['r1']} #7 2026-01-02" in text
    assert "no daily report" in text                       # the request without a DDR says so
    assert "Not recorded" not in text.split("12. Bit records")[1]


def test_chronology_units_missing_values_and_escaping(world, tmp_path):
    manager, refs = world
    _engine, text = _html(manager, refs["well"], tmp_path)
    body = text.split("<h1>14. 24-hour time logs</h1>")[1].split("<h1>15.")[0]
    order = [body.index(s) for s in ("SYN morning day 1", "SYN afternoon day 1", "SYN drill day 2")]
    assert order == sorted(order)                          # date, then start time; not insertion order
    bits = text.split("<h1>12. Bit records</h1>")[1].split("<h1>13.")[0]
    assert bits.index("SYN-3") < bits.index("SYN-4")       # report date order
    assert "<th>Depth In (m)</th>" in bits and "<th>ROP (m/hr)</th>" in bits
    assert "<td>1200</td>" in bits and "<td>8.5</td>" in bits and "<td>1850.0</td>" in bits
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in bits and "<script>alert(1)" not in text
    assert "nozzles_custom=3x16" in bits                   # unknown payload key kept, not dropped
    hours_col = bits.split("SYN-3")[1].split("</tr>")[0]
    assert "<td>—</td>" in hours_col and "<td>0</td>" not in hours_col
    logs = text.split("<h1>14. 24-hour time logs</h1>")[1].split("<h1>15.")[0]
    assert "<td>06:00</td><td>12:00</td><td>—</td>" in logs   # missing duration is unknown, not 0
    assert "<td>Yes</td><td>SYN-WAIT</td>" in logs
    bha = text.split("<h1>13. BHA components</h1>")[1].split("<h1>14.")[0]
    assert "SYN legacy / Run A (legacy configuration)" in bha
    assert bha.index("SYN bit sub") < bha.index("SYN collar") < bha.index("SYN motor")
    req = text.split("<h1>16. Material requests</h1>")[1].split("<h1>17.")[0]
    assert req.index("SYN bentonite") < req.index("SYN barite")
    assert "<td>40.0</td><td>sx</td>" in req
    eq = text.split("<h1>17. Equipment logs</h1>")[1]
    assert eq.index("SYN shaker") < eq.index("SYN undated pump")   # undated last
    assert "<td>22.5</td>" in eq


def test_empty_well_states_not_recorded_for_each_section(world, tmp_path):
    manager, refs = world
    with manager.session_scope() as s:
        for model in (BitReport, BHAReport, MaterialRequest, EquipmentLog):
            s.query(model).filter(model.well_id == refs["other"]).delete()
        s.query(TimeLog24H).delete()
        s.query(TimeLogMorning).delete()
        s.add(BitReport(well_id=refs["other"], report_date=date(2026, 1, 2), report_name="SYN empty",
                        bit_records_json="[]"))
    engine, text_ = _html(manager, refs["other"], tmp_path)
    for _key, title, _sheet in es.SECTION_SPECS:
        entry = _sections(engine)[title]
        assert entry["status"] == rs.NOT_RECORDED and entry["rows"] == 0, title
        assert "not a reported zero" in entry["detail"]
    assert text_.count("Not recorded: none recorded for this scope") == 5
    # a stored bit report with an empty payload is named, never INCLUDED and never a zero-row "table"
    assert "1 stored record(s) with no rows (bit_reports id" in _sections(engine)["12. Bit records"]["detail"]


def test_malformed_payload_is_not_rendered_and_named(world, tmp_path):
    manager, refs = world
    with manager.session_scope() as s:
        bad = BitReport(well_id=refs["well"], report_id=refs["r1"], report_date=date(2026, 1, 3),
                        report_name="SYN bad", bit_records_json="[{\"Bit No\": ")
        s.add(bad)
        s.flush()
        bad_id = bad.id
    engine, text_ = _html(manager, refs["well"], tmp_path)
    entry = _sections(engine)["12. Bit records"]
    assert entry["status"] == rs.NOT_RENDERED and entry["rows"] == 2
    assert f"bit_reports id {bad_id}" in entry["detail"] and "malformed JSON" in entry["detail"]
    assert "Unreadable stored records (not rendered)" in text_ and "SYN-3" in text_


def test_failed_table_is_query_failed_and_the_report_still_renders(world, tmp_path):
    manager, refs = world
    with manager.session_scope() as s:
        s.execute(text("DROP TABLE equipment_logs"))
    engine, text_ = _html(manager, refs["well"], tmp_path)
    sections = _sections(engine)
    assert sections["17. Equipment logs"]["status"] == rs.QUERY_FAILED
    assert sections["17. Equipment logs"]["rows"] is None
    assert "query failed" in sections["17. Equipment logs"]["detail"]
    assert "the equipment_logs query failed" in text_ and "Not recorded: none recorded" not in text_.split("17.")[-1]
    assert sections["12. Bit records"]["status"] == rs.INCLUDED     # the other sections are unaffected
    assert sections["16. Material requests"]["status"] == rs.INCLUDED


def test_period_keeps_dated_records_inside_it_and_counts_undated(world, tmp_path):
    manager, refs = world
    engine, text_ = _html(manager, refs["well"], tmp_path, period=("2026-01-02", "2026-01-03"))
    sections = _sections(engine)
    assert sections["14. 24-hour time logs"]["rows"] == 2          # only DDR #7 (2026-01-02)
    assert sections["15. Morning tour time logs"]["status"] == rs.NOT_RECORDED
    assert sections["12. Bit records"]["rows"] == 1 and "SYN-4" not in text_
    assert sections["13. BHA components"]["rows"] == 2 and "SYN motor" not in text_
    assert sections["16. Material requests"]["status"] == rs.NOT_RECORDED   # 01-01 and 01-05 are outside
    eq = sections["17. Equipment logs"]
    assert eq["rows"] == 1 and "1 undated record(s) excluded from the period" in eq["detail"]
    assert "SYN undated pump" not in text_ and "SYN shaker" in text_
    assert sections["Scope"]["detail"].startswith("Period 2026-01-02 to 2026-01-03")
    assert "equipment_logs 1" in sections["Scope"]["detail"]
    assert "Period 2026-01-02 to 2026-01-03" in text_
    assert engine.last_provenance["scope"]["period"].startswith("2026-01-02 – 2026-01-03 (requested period; 1 daily")
    whole, whole_text = _html(manager, refs["well"], tmp_path, name="whole.html")
    assert _sections(whole)["Scope"]["detail"] == "Whole-Well Aggregate" and "SYN undated pump" in whole_text


@pytest.mark.parametrize("period", [("2026-01-05", "2026-01-01"), ("2026-01-01",), "2026-01-01", (1, 2)])
def test_invalid_period_fails_instead_of_reporting_the_whole_well(world, tmp_path, period):
    manager, refs = world
    engine = engines.EOWRReportEngine(manager)
    out = tmp_path / "bad.html"
    assert engine.generate(refs["well"], str(out), "html", period=period) is False
    assert not out.exists()
    with pytest.raises(ValueError):
        es.parse_period(period)


def test_excel_and_csv_carry_the_same_rows(world, tmp_path):
    manager, refs = world
    from openpyxl import load_workbook
    engine = engines.EOWRReportEngine(manager)
    xlsx = tmp_path / "eowr.xlsx"
    assert engine.generate(refs["well"], str(xlsx), "excel")
    wb = load_workbook(xlsx, read_only=True)
    for _key, _title, sheet in es.SECTION_SPECS:
        assert sheet in wb.sheetnames, sheet
    rows = list(wb["TimeLog24H"].iter_rows(values_only=True))
    assert rows[0][0] == "Date" and len(rows) == 4
    assert [r[11] for r in rows[1:]] == ["SYN morning day 1", "SYN afternoon day 1", "SYN drill day 2"]
    wb.close()
    out = tmp_path / "eowr.csv"
    assert engine.generate(refs["well"], str(out), "csv")
    with open(tmp_path / "eowr_EquipmentLogs.csv", encoding="utf-8-sig") as handle:
        values = [row for row in csv.reader(handle) if row and not row[0].startswith("#")]
    assert values[0][0] == "Service date" and values[1][2] == "SYN shaker"


def test_empty_section_sheet_has_an_explicit_status_row():
    res = es.SectionResult("requests", "16. Material requests", rs.NOT_RECORDED, detail="none recorded")
    assert es.sheet_records(res) == [{"Status": rs.NOT_RECORDED, "Detail": "none recorded"}]


def test_payload_reader_and_column_mapping():
    assert es._payload_records(None) == ([], "")
    assert es._payload_records("null") == ([], "")
    assert es._payload_records("[1, 2]")[0] is None
    assert es._payload_records("{oops")[0] is None
    assert es._payload_records({"A": [{"x": 1}]}) == ([("A", {"x": 1})], "")
    assert es._payload_records(42)[1] == "unexpected payload type int"
    mapped = es._map_columns({"bit_no": "7", "IADC_CODE": "117", "extra": None, "x": 0}, es.BIT_COLUMNS)
    assert mapped["Bit No"] == "7" and mapped["IADC"] == "117" and mapped["Hours"] == "—"
    assert mapped["Other fields"] == "x=0"                  # a stored 0 is kept; an empty value is not invented
    assert es._text(0) == "0" and es._text("") == "—" and es._text(None) == "—" and es._text(False) == "No"


def test_pdf_output_renders_the_source_sections(world, tmp_path):
    manager, refs = world
    engine = engines.EOWRReportEngine(manager)
    out = tmp_path / "eowr.pdf"
    assert engine.generate(refs["well"], str(out), "pdf")
    assert out.stat().st_size > 1000 and out.read_bytes()[:5] == b"%PDF-"
    assert _sections(engine)["14. 24-hour time logs"]["rows"] == 3


def test_scale_benchmark_counts_are_independent_of_the_engine():
    """M468: the benchmark's expected row counts come from its generator parameters, not from the engine."""
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "tools" / "quality" / "benchmark_m468_eowr.py"
    spec = importlib.util.spec_from_file_location("benchmark_m468_eowr", path)
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    result = bench.run(days=3, logs=4, bits=2, components=3)
    assert result["expected_rows"]["14. 24-hour time logs"] == 12 and result["expected_rows"]["12. Bit records"] == 6
    assert result["passed"], result["checks"]
