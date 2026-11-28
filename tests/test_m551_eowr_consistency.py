"""M551-M554 (U5): EOWR data-consistency analyzer — every rule and status on SYNTHETIC rows, non-destructive,
lineage, and the report / Excel / provenance-manifest wiring through the real EOWR engine."""
from __future__ import annotations

import copy
import json
from datetime import date, time
from types import SimpleNamespace as NS

import pytest

from core import eowr_consistency as ec
from tests.test_m464_eowr_source_sections import world  # noqa: F401  (SYNTHETIC EOWR fixture)


def _dr(i, d, n, d0, d24, bore=None):
    return NS(id=i, report_date=d, report_number=n, depth_0000=d0, depth_2400=d24, wellbore_id=bore)


def _tl(i, rid, t0, t1, dur, npt=False):
    return NS(id=i, report_id=rid, time_from=t0, time_to=t1, duration=dur, is_npt=npt)


def _base(**over):
    data = {
        "daily_reports": [_dr(1, date(2026, 1, 1), 1, 0.0, 100.0), _dr(2, date(2026, 1, 2), 2, 100.0, 250.0)],
        "time_logs_24h": [_tl(11, 1, time(0), time(12), 12.0), _tl(12, 1, time(12), time(0), 12.0, True),
                          _tl(13, 2, time(0), time(6), 6.0)],
        "bit_reports": [NS(id=21, bit_records_json=json.dumps([{"Bit No": "SYN-1", "Depth In (m)": "0",
                                                                "Depth Out (m)": "250", "Metres Drilled": "250"}]))],
        "surveys": [{"id": 31, "md": 240.0}],
        "summary": {"total_npt": 12.0},
        "source_query_status": {"time_logs_24h": "available", "bit_reports": "available"},
        "period": None,
    }
    data.update(over)
    return data


def test_consistent_synthetic_well_is_consistent_everywhere():
    analysis = ec.analyze(_base())
    assert ec.statuses(analysis) == {key: ec.CONSISTENT for key in ec.RULE_KEYS}
    assert analysis["counts"][ec.CONSISTENT] == len(ec.RULE_KEYS) and analysis["version"] == ec.ANALYZER_VERSION


def test_analyzer_never_modifies_its_input():
    data = _base(daily_reports=[_dr(1, date(2026, 1, 1), 1, 0.0, 100.0), _dr(2, date(2026, 1, 2), 2, 90.0, 80.0)])
    before = copy.deepcopy(data)
    ec.analyze(data)
    assert repr(data) == repr(before)


@pytest.mark.parametrize("rule,over,needle", [
    ("depth_continuity", {"daily_reports": [_dr(1, date(2026, 1, 1), 1, 0.0, 100.0),
                                            _dr(2, date(2026, 1, 2), 2, 120.0, 250.0)]}, "starts at 120"),
    ("depth_within_day", {"daily_reports": [_dr(1, date(2026, 1, 1), 1, 0.0, 100.0),
                                            _dr(2, date(2026, 1, 2), 2, 100.0, 80.0)]}, "plug-back"),
    ("time_log_day_total", {"time_logs_24h": [_tl(11, 1, time(0), time(12), 12.0),
                                              _tl(12, 1, time(12), time(0), 13.0)],
                            "summary": {"total_npt": 0.0}}, "25 h"),
    ("time_log_interval", {"time_logs_24h": [_tl(11, 1, time(6), time(12), 5.0)], "summary": {"total_npt": 0.0}},
     "06:00:00-12:00:00 is 6 h"),
    ("npt_summary", {"summary": {"total_npt": 10.0}}, "rows give 12"),
    ("report_identity", {"daily_reports": [_dr(1, date(2026, 1, 1), 1, 0.0, 100.0),
                                           _dr(2, date(2026, 1, 1), 1, 100.0, 250.0)]}, "are both"),
    ("bit_run_depths", {"bit_reports": [NS(id=21, bit_records_json=[{"Depth In (m)": "300",
                                                                      "Depth Out (m)": "250"}])]}, "above depth in"),
    ("bit_run_depths", {"bit_reports": [NS(id=21, bit_records_json=[{"Depth In (m)": "0", "Depth Out (m)": "250",
                                                                      "Metres Drilled": "240"}])]}, "metres drilled"),
    ("survey_within_depth", {"surveys": [{"id": 31, "md": 300.0}]}, "deeper than any reported depth"),
])
def test_each_rule_reports_its_contradiction_with_lineage(rule, over, needle):
    result = next(r for r in ec.analyze(_base(**over))["results"] if r["rule"] == rule)
    assert result["status"] == ec.INCONSISTENT, result
    assert any(needle in f["message"] for f in result["findings"]), result["findings"]
    assert all(f["sources"] and all({"table", "id", "field", "value"} <= set(s) for s in f["sources"])
               for f in result["findings"])


def test_failed_queries_are_not_assessed_not_consistent():
    data = _base(time_logs_24h=None, bit_reports=None,
                 source_query_status={"time_logs_24h": "query-failed", "bit_reports": "query-failed"})
    st = ec.statuses(ec.analyze(data))
    for rule in ("time_log_day_total", "time_log_interval", "npt_summary", "bit_run_depths"):
        assert st[rule] == ec.NOT_ASSESSED


def test_missing_values_are_insufficient_data_never_zero():
    data = _base(daily_reports=[_dr(1, None, 1, None, None), _dr(2, date(2026, 1, 2), None, None, None)],
                 time_logs_24h=[_tl(11, 1, None, None, None, None)], bit_reports=[NS(id=21, bit_records_json=None)],
                 surveys=[], summary={"total_npt": None})
    st = ec.statuses(ec.analyze(data))
    assert st == {"depth_continuity": ec.INSUFFICIENT_DATA, "depth_within_day": ec.INSUFFICIENT_DATA,
                  "time_log_day_total": ec.INSUFFICIENT_DATA, "time_log_interval": ec.INSUFFICIENT_DATA,
                  "npt_summary": ec.INSUFFICIENT_DATA, "report_identity": ec.INSUFFICIENT_DATA,
                  "bit_run_depths": ec.INSUFFICIENT_DATA, "survey_within_depth": ec.INSUFFICIENT_DATA}


def test_summary_npt_from_incomplete_rows_is_inconsistent():
    data = _base(time_logs_24h=[_tl(11, 1, time(0), time(6), 6.0, None)], summary={"total_npt": 0.0})
    assert ec.statuses(ec.analyze(data))["npt_summary"] == ec.INCONSISTENT


def test_period_report_makes_the_survey_rule_not_applicable():
    data = _base(period=(date(2026, 1, 2), date(2026, 1, 2)), surveys=[{"id": 31, "md": 999.0}])
    assert ec.statuses(ec.analyze(data))["survey_within_depth"] == ec.NOT_APPLICABLE


def test_wellbores_are_checked_separately():
    data = _base(daily_reports=[_dr(1, date(2026, 1, 1), 1, 0.0, 100.0, bore=1),
                                _dr(2, date(2026, 1, 2), 1, 50.0, 80.0, bore=2),
                                _dr(3, date(2026, 1, 3), 2, 100.0, 150.0, bore=1)])
    st = ec.statuses(ec.analyze(data))
    assert st["depth_continuity"] == ec.CONSISTENT and st["report_identity"] == ec.CONSISTENT


def test_empty_collection_is_not_assessed():
    assert set(ec.statuses(ec.analyze({})).values()) == {ec.NOT_ASSESSED}


def test_html_escapes_stored_text_and_lists_sources():
    data = _base(bit_reports=[NS(id=21, bit_records_json=[{"Depth In (m)": "300", "Depth Out (m)": "250"}])])
    html = ec.html_section(ec.analyze(data))
    assert "bit_reports id 21" in html and "<script" not in html and "Data consistency review" in html
    rows = ec.manifest_rows(ec.analyze(data))
    assert ["consistency.version", ec.ANALYZER_VERSION] in rows
    assert any(r[0] == "consistency.bit_run_depths" and r[1].startswith(ec.INCONSISTENT) for r in rows)


# ---- through the real EOWR engine (SYNTHETIC database of tests/test_m464) ----------------------------------------------
def test_engine_html_excel_and_manifest_carry_the_review(world, tmp_path):  # noqa: F811
    import openpyxl

    from core.database import TimeLog24H
    from core.report_engine import EOWRReportEngine

    manager, refs = world
    with manager.session_scope() as s:
        s.add(TimeLog24H(report_id=refs["r2"], time_from=time(6, 0), time_to=time(12, 0), duration=5.0,
                         activity_description="SYN-M551 mismatched log"))
    with manager.session_scope() as s:
        before = sorted((r.id, r.duration, r.time_from) for r in s.query(TimeLog24H).all())
    engine = EOWRReportEngine(manager)
    html_path = tmp_path / "eowr.html"
    assert engine.generate(refs["well"], str(html_path), "html")
    text = html_path.read_text(encoding="utf-8")
    assert "Data consistency review" in text and "stored duration is 5 h" in text
    assert "consistency.time_log_interval" in text
    assert engine.last_provenance["consistency"]["version"] == ec.ANALYZER_VERSION
    st = ec.statuses(engine.last_provenance["consistency"])
    assert st["time_log_interval"] == ec.INCONSISTENT
    assert st["npt_summary"] == ec.CONSISTENT                 # 6 h NPT (the undated-duration row is not NPT)
    assert st["bit_run_depths"] == ec.CONSISTENT              # 1200 -> 1850 m, 650 m drilled
    assert "SYN-LEAK-B" not in text
    xlsx = tmp_path / "eowr.xlsx"
    assert engine.generate(refs["well"], str(xlsx), "excel")
    assert "Data Consistency" in openpyxl.load_workbook(xlsx).sheetnames
    with manager.session_scope() as s:
        assert sorted((r.id, r.duration, r.time_from) for r in s.query(TimeLog24H).all()) == before
