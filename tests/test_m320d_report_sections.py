"""M320-D (M287): no report section is omitted silently (SYNTHETIC).

A DDR or EOWR with empty sections states "Not recorded" for each of them in the body, and every format carries
the section manifest in its provenance (HTML, PDF, Excel and CSV). Data that the EOWR collects but does not render
is named as NOT_RENDERED with its row count.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, time

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


def test_kinds_without_a_manifest_say_so():
    assert rs.manifest("memo", {"anything": 1}) is None
    assert rs.manifest("npt", None) is None
    assert "not available for report kind 'memo'" in rs.rows(None, "memo")[0][1]
    assert all(rs.manifest(kind, {}) is not None for kind in rs.MANIFEST_KINDS)


# ---- M333 (A-7): NPT, Cost and Plan reports -------------------------------------------------------------------
def _log(session, report_id, start, end, hours, npt, code="SYN-NPT", sub=""):
    session.add(TimeLog24H(report_id=report_id, time_from=time(start), time_to=time(end), duration=hours,
                           is_npt=npt, main_code=code, sub_code=sub, activity_description="SYN"))


def test_npt_report_lists_every_section_and_states_an_unknown_cost(env, tmp_path):  # noqa: F811
    manager, ids = env
    with manager.session_scope() as s:
        _log(s, ids["report"], 0, 6, 6.0, True)
        _log(s, ids["report"], 6, 12, 6.0, False, code="SYN-DRL")
    engine = engines.NPTReportEngine(manager)
    assert engine.generate(ids["well"], str(tmp_path / "npt.html"), "html")
    sections = _sections(engine.last_provenance)
    assert sections["NPT share of logged time"]["status"] == rs.INCLUDED
    assert sections["NPT by main code"] == {"section": "NPT by main code", "status": rs.INCLUDED, "rows": 1,
                                            "detail": ""}
    assert sections["NPT event details"]["rows"] == 1
    assert sections["NPT cost (allocated)"]["status"] == rs.NOT_RECORDED              # no cost lines seeded
    assert "not a zero cost" in sections["NPT cost (allocated)"]["detail"]
    row = [v for k, v in rp.rows(engine.last_provenance) if k == "section manifest"][0]
    assert row == rs.MANIFEST_VERSION


def test_npt_manifest_window_many_sub_codes_and_no_time():
    many = {f"SYN {i}": 1.0 for i in range(20)}
    data = {"from_date": "2026-01-01", "to_date": "End", "total_hours": 24.0, "npt_pct": 10.0,
            "by_main_code": {"SYN": 20.0}, "by_sub_code": many, "by_contractor": {}, "by_phase": {},
            "by_date": {}, "entries": [], "npt_cost": None}
    by = {e["section"]: e for e in rs.npt_manifest(data)}
    assert by["NPT by sub code"]["status"] == rs.SUMMARISED and "top 15 of 20" in by["NPT by sub code"]["detail"]
    assert "date window" in by["NPT cost (allocated)"]["detail"]
    assert by["NPT event details"]["detail"] == "no NPT time logs in this scope"
    empty = {e["section"]: e for e in rs.npt_manifest({"total_hours": None, "npt_pct": None})}
    assert empty["NPT share of logged time"]["status"] == rs.NOT_RECORDED
    assert "not 0 %" in empty["NPT share of logged time"]["detail"]
    assert empty["NPT by phase"]["detail"] == "no time logged in this scope"


def test_cost_report_without_rates_states_projections_not_computed(env, tmp_path):  # noqa: F811
    from core.database import CostRecord

    manager, ids = env
    with manager.session_scope() as s:
        s.add(CostRecord(well_id=ids["well"], category="SYN rig", currency="USD", planned_cost=1000.0,
                         actual_cost=1200.0))
    engine = engines.CostReportEngine(manager)
    assert engine.generate(ids["well"], str(tmp_path / "cost.html"), "html")
    sections = _sections(engine.last_provenance)
    assert sections["Total actual cost"]["status"] == rs.INCLUDED
    assert sections["Source cost lines (unaggregated)"]["rows"] == 1
    assert sections["Projection (rate × days)"]["status"] == rs.NOT_RECORDED
    assert "projections are not computed" in sections["Cumulative cost vs depth"]["detail"]
    with_rates = engines.CostReportEngine(manager)
    assert with_rates.generate(ids["well"], str(tmp_path / "cost2.html"), "html", daily_rate=100.0,
                               spread_rate=50.0, projection_currency="USD")
    projected = _sections(with_rates.last_provenance)
    assert projected["Projection (rate × days)"]["status"] == rs.INCLUDED
    assert projected["Cumulative cost vs depth"]["status"] == rs.INCLUDED


def test_cost_manifest_without_cost_lines_is_not_a_zero():
    by = {e["section"]: e for e in rs.cost_manifest({"total_cost": None, "currency_status": "no cost lines",
                                                     "categories": {}, "records": []})}
    assert by["Total actual cost"]["status"] == rs.NOT_RECORDED and "not a zero cost" in by["Total actual cost"]["detail"]
    assert by["Cost by category"]["detail"] == "no cost records: not a reported zero"


def test_plan_report_names_the_active_plan_and_unrendered_versions(env, tmp_path):  # noqa: F811
    from core.database import PlannedActivity, WellPlan

    manager, ids = env
    with manager.session_scope() as s:
        for plan in s.query(WellPlan).filter_by(well_id=ids["well"]).all():
            plan.is_active = True
            plan.plan_version = 2
            s.add(PlannedActivity(well_id=ids["well"], plan_id=plan.id, activity_name="SYN drill",
                                  planned_start=datetime(2026, 1, 2, 0, 0), planned_end=datetime(2026, 1, 2, 12, 0),
                                  planned_duration_hours=12.0, planned_depth_to=900.0, phase_code="SYN-1"))
        s.add(WellPlan(well_id=ids["well"], plan_name="SYN old plan", is_active=False))
    engine = engines.PlanReportEngine(manager)
    assert engine.generate(ids["well"], str(tmp_path / "plan.html"), "html")
    sections = _sections(engine.last_provenance)
    assert sections["Plan information"]["detail"] == "active plan SYN plan v2"
    assert sections["Activity schedule"]["rows"] == 1 and sections["Hours by phase"]["rows"] == 1
    assert sections["Planned totals (days / hours)"]["status"] == rs.INCLUDED
    assert sections["Other plan versions"]["status"] == rs.NOT_RENDERED and sections["Other plan versions"]["rows"] == 1


def test_plan_manifest_with_an_unknown_duration_is_not_partial():
    by = {e["section"]: e for e in rs.plan_manifest({"plan": None, "total_hrs": None, "all_plans": [],
                                                     "activities": [], "by_phase": {}})}
    assert by["Plan information"]["status"] == rs.NOT_RECORDED
    assert "unknown, not partial" in by["Planned totals (days / hours)"]["detail"]
    assert by["Other plan versions"]["status"] == rs.INCLUDED and by["Other plan versions"]["rows"] == 0


def test_a_record_of_only_empty_fields_is_not_recorded():
    entry = rs.ddr_manifest({"params": {"bit_size": None, "wob": "", "nozzles": []}, "mud": {"mw": 10.0}})
    by = {e["section"]: e for e in entry}
    assert by["Drilling parameters"]["status"] == rs.NOT_RECORDED and by["Drilling parameters"]["rows"] == 0
    assert by["Mud properties"]["status"] == rs.INCLUDED and by["Mud properties"]["rows"] == 1


def test_a_known_zero_is_included_and_an_empty_list_is_not_recorded():
    """M327 survivors: a computed 0 is a figure (0 % NPT, 0 cost per metre); an empty list is never INCLUDED."""
    npt = {e["section"]: e for e in rs.npt_manifest({"total_hours": 24.0, "npt_pct": 0.0, "by_main_code": {},
                                                     "by_sub_code": {}, "by_contractor": {}, "by_phase": {},
                                                     "by_date": {}, "entries": [], "npt_cost": None})}
    assert npt["NPT share of logged time"]["status"] == rs.INCLUDED and npt["NPT share of logged time"]["detail"] == ""
    for title in ("NPT by main code", "NPT by contractor", "NPT by phase", "NPT daily trend", "NPT event details"):
        assert npt[title]["status"] == rs.NOT_RECORDED and npt[title]["rows"] == 0, title
    cost = {e["section"]: e for e in rs.cost_manifest({"total_cost": 0.0, "cost_per_meter": 0.0,
                                                      "currency_status": "USD", "categories": {}, "records": []})}
    assert cost["Total actual cost"]["status"] == rs.INCLUDED
    assert cost["Cost per metre / foot"]["status"] == rs.INCLUDED
    assert cost["Cost by category"]["status"] == rs.NOT_RECORDED
    assert cost["Source cost lines (unaggregated)"]["status"] == rs.NOT_RECORDED
    plan = {e["section"]: e for e in rs.plan_manifest({"plan": None, "total_hrs": 0.0, "max_depth": 0.0,
                                                      "all_plans": [], "activities": [], "by_phase": {}})}
    assert plan["Planned final depth"]["status"] == rs.INCLUDED
    assert plan["Activity schedule"]["status"] == rs.NOT_RECORDED and plan["Hours by phase"]["status"] == rs.NOT_RECORDED
