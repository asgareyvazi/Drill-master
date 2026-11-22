"""M320-D (M287): no report section is omitted silently (SYNTHETIC).

A DDR or EOWR with empty sections states "Not recorded" for each of them in the body, and every format carries
the section manifest in its provenance (HTML, PDF, Excel and CSV). Data that the EOWR collects but does not render
is named as NOT_RENDERED with its row count.
"""
from __future__ import annotations

import csv
from datetime import date, time

import pytest

from core import report_engine as engines
from core import report_provenance as rp
from core import report_sections as rs
from core.database import BitReport, DailyReport, DrillingParameters, MudReport, TimeLog24H
from tests.test_m93_report_provenance import env  # noqa: F401  (shared SYNTHETIC world)


def _sections(prov):
    return {e["section"]: e for e in prov["sections"]}


def test_empty_ddr_states_every_missing_section(env, tmp_path):  # noqa: F811
    manager, ids = env
    engine = engines.DDRReportEngine(manager)
    path = tmp_path / "ddr.html"
    assert engine.generate(ids["report"], str(path), "html")
    text = path.read_text(encoding="utf-8")
    for field in ("drilling parameter", "mud", "24-hour operations", "morning tour", "operations summary"):
        assert f"Not recorded: no {field} data was submitted for this scope." in text
    sections = _sections(engine.last_provenance)
    assert sections["Drilling parameters"]["status"] == rs.NOT_RECORDED
    assert sections["Time analysis"]["status"] == rs.NOT_RECORDED
    assert "not 100 % productive" in sections["Time analysis"]["detail"]
    assert "section manifest" in text and "Drilling parameters: NOT_RECORDED" in text


def test_recorded_ddr_sections_are_included_with_row_counts(env, tmp_path):  # noqa: F811
    manager, ids = env
    with manager.session_scope() as s:
        report = s.get(DailyReport, ids["report"])
        report.summary = "SYN drilled ahead"
        s.add(DrillingParameters(well_id=ids["well"], report_id=ids["report"], report_date=report.report_date,
                                 bit_no="1", wob_max=20.0))
        s.add(MudReport(well_id=ids["well"], report_id=ids["report"], report_date=report.report_date, mw=70.0))
        s.add(TimeLog24H(report_id=ids["report"],
                         time_from=time(0, 0), time_to=time(6, 0), duration=6.0, activity_description="SYN drill"))
    engine = engines.DDRReportEngine(manager)
    path = tmp_path / "ddr.html"
    assert engine.generate(ids["report"], str(path), "html")
    text = path.read_text(encoding="utf-8")
    sections = _sections(engine.last_provenance)
    for name in ("Drilling parameters", "Mud properties", "24-hour operations", "Operations summary", "Time analysis"):
        assert sections[name]["status"] == rs.INCLUDED, name
    assert sections["24-hour operations"]["rows"] == 1
    assert sections["Morning tour"]["status"] == rs.NOT_RECORDED
    assert "no mud data" not in text and "Not recorded: no morning tour data" in text


def test_eowr_states_empty_sections_and_names_unrendered_data(env, tmp_path):  # noqa: F811
    manager, ids = env
    with manager.session_scope() as s:
        s.add(BitReport(well_id=ids["well"], report_id=ids["report"], report_date=date(2026, 1, 2),
                        report_name="SYN bit", bit_records_json="[]"))
    engine = engines.EOWRReportEngine(manager)
    path = tmp_path / "eowr.html"
    assert engine.generate(ids["well"], str(path), "html")
    text = path.read_text(encoding="utf-8")
    assert "Not recorded: no drilling parameter data was submitted for this scope." in text
    sections = _sections(engine.last_provenance)
    assert sections["4. Daily reports summary"]["status"] == rs.INCLUDED
    assert sections["4. Daily reports summary"]["rows"] == 2
    assert sections["5. Drilling performance"]["status"] == rs.NOT_RECORDED
    assert sections["7. Casing and cementing"]["status"] == rs.SUMMARISED
    assert sections["Bit reports"]["status"] == rs.NOT_RENDERED and sections["Bit reports"]["rows"] == 1
    assert "collected (1 row(s)) but not rendered" in sections["Bit reports"]["detail"]
    assert sections["11. Cost summary"]["status"] in (rs.NOT_RECORDED, rs.INCLUDED, rs.QUERY_FAILED)


def test_cost_query_failure_is_a_named_status():
    entries = {e["section"]: e for e in rs.eowr_manifest({"cost_records": None})}
    assert entries["11. Cost summary"]["status"] == rs.QUERY_FAILED
    entries = {e["section"]: e for e in rs.eowr_manifest({"cost_records": []})}
    assert entries["11. Cost summary"]["status"] == rs.NOT_RECORDED
    assert "not a reported zero" in entries["11. Cost summary"]["detail"]


@pytest.mark.parametrize("fmt", ["excel", "csv", "pdf"])
def test_manifest_reaches_every_format(env, tmp_path, fmt):  # noqa: F811
    manager, ids = env
    engine = engines.DDRReportEngine(manager)
    out = tmp_path / {"excel": "ddr.xlsx", "csv": "ddr.csv", "pdf": "ddr.pdf"}[fmt]
    assert engine.generate(ids["report"], str(out), fmt)
    lines = [f"{k}: {v}" for k, v in rp.rows(engine.last_provenance)]
    assert any(line.startswith("section: Mud properties: NOT_RECORDED") for line in lines)
    if fmt == "excel":
        from openpyxl import load_workbook

        values = [c.value for row in load_workbook(out)["Provenance"].iter_rows() for c in row]
        assert "section manifest" in values and any(str(v).startswith("Mud properties: NOT_RECORDED") for v in values)
    elif fmt == "csv":
        rows = list(csv.reader(open(out, encoding="utf-8-sig")))
        assert ["# section manifest", rs.MANIFEST_VERSION] in rows


def test_kinds_without_a_manifest_say_so(env, tmp_path):  # noqa: F811
    manager, ids = env
    engine = engines.NPTReportEngine(manager)
    assert engine.generate(ids["well"], str(tmp_path / "npt.html"), "html")
    assert engine.last_provenance["sections"] is None
    row = [v for k, v in rp.rows(engine.last_provenance) if k == "section manifest"][0]
    assert "not available for report kind 'npt'" in row
