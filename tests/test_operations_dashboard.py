"""M44: operations dashboard model (core/operations_dashboard.py).

Expected numbers are derived from the documented SYNTHETIC fixture
(tests/synthetic_operations.py), not from the implementation: SYN-DEV-01 has
six reports dated end-5 .. end, each with 24 h of logged time, 3.5 h NPT on
report 3 and 2.0 h on report 5; SYN-QA-03 reports are dated end-9 and end-8.
"""
import math
from datetime import date, datetime, timedelta, timezone

import pytest

from core.operations_dashboard import KPI_DEFINITIONS, STALE_AFTER_DAYS, WINDOW_DAYS, build_snapshot
from synthetic_operations import build_synthetic_operations, make_file_database
from test_scope_attribution import _base, _mgr, _report, _well

END = date(2026, 1, 15)


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    db = make_file_database(tmp_path_factory.mktemp("dash") / "syn.db")
    ids = build_synthetic_operations(db, end_date=END)
    yield db, ids
    db.engine.dispose()


def _flags(snapshot, name):
    well = next(w for w in snapshot.wells if w.name == name)
    return {f.code: f for f in well.flags}


def test_empty_database_reports_no_data_instead_of_zero():
    snapshot = build_snapshot(_mgr(), today=END)
    assert snapshot.empty and snapshot.wells == [] and snapshot.attention == [] and snapshot.recent_reports == []
    k = snapshot.kpis
    assert k["wells_total"].value == 0 and k["reports_total"].value == 0       # real counts of nothing
    for key in ("latest_report", "npt_window", "npt_share"):
        assert k[key].value is None and k[key].state == "no_data", key


def test_every_kpi_has_its_written_definition(synthetic):
    db, _ids = synthetic
    snapshot = build_snapshot(db, today=END)
    assert set(snapshot.kpis) == set(KPI_DEFINITIONS)
    for key, kpi in snapshot.kpis.items():
        assert kpi.definition == KPI_DEFINITIONS[key] and len(kpi.definition) > 20
        assert kpi.state in ("ok", "warning", "error", "no_data")


def test_synthetic_kpis_match_the_fixture(synthetic):
    db, _ids = synthetic
    k = build_snapshot(db, today=END).kpis
    # 4 SYN wells + the Default Well that database initialization creates.
    assert k["wells_total"].value == 5
    assert k["wells_active"].value == 2          # SYN-DEV-01, SYN-QA-03 (Drilling)
    assert k["wells_planning"].value == 2        # SYN-VERT-02 + Default Well
    assert k["wells_completed"].value == 1       # SYN-DONE-04
    assert k["reports_total"].value == 6 + 2 + 1
    assert k["reports_window"].value == 6        # QA (end-9, end-8) and DONE (end-30) are outside 7 days
    assert k["latest_report"].value == END
    assert k["npt_window"].value == pytest.approx(5.5) and k["npt_window"].state == "warning"
    assert k["npt_share"].value == pytest.approx(100 * 5.5 / (6 * 24.0))
    assert k["wells_need_review"].value == 1 and k["wells_need_review"].state == "warning"
    assert k["imports_window"].value == 0


def test_flags_and_drill_down_targets_per_well(synthetic):
    db, ids = synthetic
    snapshot = build_snapshot(db, today=END)
    qa = _flags(snapshot, "SYN-QA-03")
    assert set(qa) == {"SURVEY_CONFLICT", "SURVEY_INCOMPLETE", "STALE_REPORTING", "DEPTH_NOT_REPORTED"}
    assert qa["SURVEY_CONFLICT"].severity == "error" and qa["SURVEY_CONFLICT"].target == "trajectory"
    assert "1 survey station" in qa["SURVEY_INCOMPLETE"].message    # the azimuth-less 300 m row only
    assert qa["DEPTH_NOT_REPORTED"].target == "report" and qa["DEPTH_NOT_REPORTED"].report_id == ids["qa_reports"][1]
    assert qa["STALE_REPORTING"].report_id == ids["qa_reports"][1]
    assert "8 days" in qa["STALE_REPORTING"].message and 8 > STALE_AFTER_DAYS
    assert set(_flags(snapshot, "SYN-DONE-04")) == {"NO_SURVEY"}
    assert _flags(snapshot, "SYN-VERT-02")["NO_REPORTS"].severity == "info"    # planning well
    assert _flags(snapshot, "SYN-DEV-01") == {}
    assert snapshot.attention[0].code == "SURVEY_CONFLICT"                   # errors first


def test_well_rows_carry_composed_survey_depths_and_order(synthetic):
    db, ids = synthetic
    snapshot = build_snapshot(db, today=END)
    dev = next(w for w in snapshot.wells if w.well_id == ids["dev"])
    radius = 30 / math.radians(2)
    expected_tvd = 600 + radius * math.sin(math.radians(40)) + 600 * math.cos(math.radians(40))
    assert dev.survey_status == "READY" and dev.survey_stations == 66
    assert dev.survey_md == pytest.approx(1800.0) and dev.survey_tvd == pytest.approx(expected_tvd, abs=0.05)
    assert dev.latest_report_id == ids["reports"][6] and dev.latest_depth == 1800.0 and dev.days_since_report == 0
    assert dev.npt_hours_window == pytest.approx(5.5)
    assert snapshot.wells[0].name == "SYN-QA-03"                              # worst severity first
    assert [w.worst_severity for w in snapshot.wells][-1] is None             # clean wells last
    recent = snapshot.recent_reports
    assert len(recent) == 9 and recent[0]["report_id"] == ids["reports"][6] and recent[0]["date"] == END


def test_window_is_bounded_by_today_and_future_dates_are_flagged(synthetic):
    db, _ids = synthetic
    earlier = build_snapshot(db, today=END - timedelta(days=3))       # window end-9 .. end-3
    assert earlier.kpis["reports_window"].value == 3 + 2              # DEV end-5..end-3 + both QA reports
    assert earlier.kpis["npt_window"].value == pytest.approx(3.5)     # report 3 only (end-3)
    dev = _flags(earlier, "SYN-DEV-01")
    assert dev["FUTURE_REPORT_DATE"].severity == "warning"
    later = build_snapshot(db, today=END + timedelta(days=60))
    assert later.kpis["reports_window"].value == 0
    assert later.kpis["npt_window"].value is None and later.kpis["npt_window"].state == "no_data"
    assert later.kpis["npt_share"].value is None


def test_active_well_without_reports_is_a_warning():
    db = _mgr()
    project = _base(db)
    well_id = _well(db, project, "SYN-ACTIVE")
    session = db.create_session()
    from core.database import Well
    session.get(Well, well_id).status = "Drilling"
    session.commit()
    session.close()
    flag = _flags(build_snapshot(db, today=END), "SYN-ACTIVE")["NO_REPORTS"]
    assert flag.severity == "warning" and "active" in flag.message


def test_imports_window_counts_ddr_import_audit_rows_in_window():
    db = _mgr()
    well_id = _well(db, _base(db), "SYN-IMP")
    report_id = _report(db, well_id, 1)
    db.save_import_audit(report_id, "synthetic-fingerprint", "synthetic.xlsx", {"status": "ok"})
    today = datetime.now(timezone.utc).astimezone().date()
    assert build_snapshot(db, today=today).kpis["imports_window"].value == 1
    assert build_snapshot(db, today=today - timedelta(days=WINDOW_DAYS + 1)).kpis["imports_window"].value == 0
    assert build_snapshot(db, today=today + timedelta(days=WINDOW_DAYS + 1)).kpis["imports_window"].value == 0
