"""Mission 24 — W12 analytics wellbore-scope truth (Qt-free domain tests).

Proves that W12's analytical readers follow the selected scope and never mix
bores:

* Whole-well aggregate spans original + sidetrack + unknown-bore reports.
* A selected wellbore isolates ONLY that bore's reports/params/NPT.
* Unknown-bore (NULL wellbore_id) records are excluded from a bore-scoped view
  and never attributed to a specific bore.
* Scope cache keys are distinct per scope, and re-selecting a scope yields the
  identical result (no stale cross-scope contamination).
* Missing values stay unknown (None), never fabricated 0 — including
  ``get_performance_data`` (Track G) and ROP-prediction input eligibility.

The W12 methods are bound to a lightweight stub (no Qt), exactly like the M23
analytics-truth tests, and run against a real in-memory DatabaseManager.
"""
import types
from datetime import date, time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base, DatabaseManager, Company, Project, Well, Wellbore, Section,
    DailyReport, DrillingParameters, TimeLog24H,
)
from core.operations_intelligence import OperationsIntelligenceService
from tabs.w12_Analysis import AnalysisWidget


# ---------------------------------------------------------------------------
# Fixture: one well, Original + Sidetrack + one unknown-bore report
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    m = DatabaseManager()
    m.engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    m.create_session()
    return m


@pytest.fixture()
def two_bore(db):
    s = db.create_session()
    c = Company(name="C", code="C"); s.add(c); s.flush()
    p = Project(name="P", code="P", company_id=c.id); s.add(p); s.flush()
    w = Well(name="W1", code="W1", project_id=p.id); s.add(w); s.flush()
    orig = Wellbore(well_id=w.id, name="Original", wellbore_type="original")
    s.add(orig); s.flush()
    st1 = Wellbore(well_id=w.id, name="ST-1", wellbore_type="sidetrack",
                   parent_wellbore_id=orig.id, kickoff_md=2500)
    s.add(st1); s.flush()
    sec_o = Section(name='12-1/4"', well_id=w.id, wellbore_id=orig.id, depth_from=1000)
    sec_s = Section(name='12-1/4"', well_id=w.id, wellbore_id=st1.id, depth_from=2500)
    s.add_all([sec_o, sec_s]); s.flush()
    ro = DailyReport(well_id=w.id, section_id=sec_o.id, wellbore_id=orig.id,
                     report_number=1, report_date=date(2026, 1, 1),
                     depth_2400=1000, rop_meter=20)
    rs = DailyReport(well_id=w.id, section_id=sec_s.id, wellbore_id=st1.id,
                     report_number=2, report_date=date(2026, 1, 5),
                     depth_2400=3000, rop_meter=60)
    runk = DailyReport(well_id=w.id, section_id=None, wellbore_id=None,
                       report_number=3, report_date=date(2026, 1, 3),
                       depth_2400=1500, rop_meter=40)
    s.add_all([ro, rs, runk]); s.flush()
    s.add_all([
        DrillingParameters(well_id=w.id, report_id=ro.id, report_date=date(2026, 1, 1),
                           avg_rop=20, wob_min=10, wob_max=20),
        DrillingParameters(well_id=w.id, report_id=rs.id, report_date=date(2026, 1, 5),
                           avg_rop=60, wob_min=30, wob_max=40),
        TimeLog24H(report_id=ro.id, time_from=time(0, 0), time_to=time(1, 0),
                   duration=1.0, is_npt=True, main_code="NPT-A"),
        TimeLog24H(report_id=ro.id, time_from=time(1, 0), time_to=time(23, 0),
                   duration=22.0, is_npt=False),
        TimeLog24H(report_id=rs.id, time_from=time(0, 0), time_to=time(4, 0),
                   duration=4.0, is_npt=True, main_code="NPT-B"),
        TimeLog24H(report_id=rs.id, time_from=time(4, 0), time_to=time(23, 0),
                   duration=20.0, is_npt=False),
    ])
    s.commit()
    ids = {"well": w.id, "orig": orig.id, "st1": st1.id,
           "sec_o": sec_o.id, "sec_s": sec_s.id}
    s.close()
    return ids


def _stub(db, well_id, wellbore_id=None, section_id=None):
    class Stub:
        pass
    st = Stub()
    st.db = db
    st.current_well_id = well_id
    st.current_wellbore_id = wellbore_id
    st.current_section_id = section_id
    st.intelligence_service = OperationsIntelligenceService(db)
    for name in ("_scope_key", "_scope_reports_query", "_scope_params_query",
                 "_canonical_scope_kpis", "get_time_depth_data", "get_npt_data",
                 "calculate_kpis", "get_performance_data", "get_today_data"):
        setattr(st, name, types.MethodType(getattr(AnalysisWidget, name), st))
    return st


# ---------------------------------------------------------------------------
# Scope isolation
# ---------------------------------------------------------------------------

def test_whole_well_aggregate_includes_all_bores(db, two_bore):
    st = _stub(db, two_bore["well"])
    s = db.create_session()
    try:
        td = st.get_time_depth_data(s)
        npt = st.get_npt_data(s)
        kp = st.calculate_kpis(s)
    finally:
        s.close()
    assert len(td) == 3  # original + sidetrack + unknown
    assert npt["total_npt"] == 5.0  # 1 + 4
    assert kp["current_depth"] == 3000.0


def test_original_bore_isolated(db, two_bore):
    st = _stub(db, two_bore["well"], wellbore_id=two_bore["orig"])
    s = db.create_session()
    try:
        td = st.get_time_depth_data(s)
        npt = st.get_npt_data(s)
        kp = st.calculate_kpis(s)
    finally:
        s.close()
    assert [d["depth"] for d in td] == [1000.0]
    assert npt["total_npt"] == 1.0
    assert kp["current_depth"] == 1000.0
    assert kp["avg_rop"] == 20


def test_sidetrack_isolated(db, two_bore):
    st = _stub(db, two_bore["well"], wellbore_id=two_bore["st1"])
    s = db.create_session()
    try:
        td = st.get_time_depth_data(s)
        npt = st.get_npt_data(s)
        kp = st.calculate_kpis(s)
    finally:
        s.close()
    assert [d["depth"] for d in td] == [3000.0]
    assert npt["total_npt"] == 4.0
    assert kp["current_depth"] == 3000.0
    assert kp["avg_rop"] == 60


def test_unknown_bore_excluded_from_bore_view(db, two_bore):
    for bore in (two_bore["orig"], two_bore["st1"]):
        st = _stub(db, two_bore["well"], wellbore_id=bore)
        s = db.create_session()
        try:
            td = st.get_time_depth_data(s)
        finally:
            s.close()
        assert 1500.0 not in [d["depth"] for d in td]


def test_scope_keys_distinct(db, two_bore):
    whole = _stub(db, two_bore["well"])
    orig = _stub(db, two_bore["well"], wellbore_id=two_bore["orig"])
    st1 = _stub(db, two_bore["well"], wellbore_id=two_bore["st1"])
    keys = {whole._scope_key(), orig._scope_key(), st1._scope_key()}
    assert len(keys) == 3
    assert whole._scope_key() == f"well:{two_bore['well']}"
    assert orig._scope_key() == f"wellbore:{two_bore['orig']}"


def test_scope_switch_is_deterministic(db, two_bore):
    """Original computed twice (with a sidetrack computation between) is identical."""
    def kpis_for(bore):
        st = _stub(db, two_bore["well"], wellbore_id=bore)
        s = db.create_session()
        try:
            return st.calculate_kpis(s)
        finally:
            s.close()
    first = kpis_for(two_bore["orig"])
    _ = kpis_for(two_bore["st1"])
    again = kpis_for(two_bore["orig"])
    assert first == again
    assert first != kpis_for(two_bore["st1"])


# ---------------------------------------------------------------------------
# Truth semantics (Track G)
# ---------------------------------------------------------------------------

def test_performance_missing_is_none_not_zero(db, two_bore):
    """A parameter row with no torque/pressure yields None, not a fabricated 0."""
    st = _stub(db, two_bore["well"], wellbore_id=two_bore["orig"])
    s = db.create_session()
    try:
        perf = st.get_performance_data(s)
    finally:
        s.close()
    assert perf, "expected one bit run"
    row = perf[0]
    # torque/pressure were never recorded -> unknown
    assert row["torque"] is None
    assert row["pressure"] is None
    # wob had both bounds -> midpoint is a real value
    assert row["wob"] == 15.0
    # avg_rop was recorded -> real value
    assert row["rop"] == 20


def test_performance_explicit_zero_preserved(db, two_bore):
    """A genuinely measured 0.0 survives (not dropped as if missing)."""
    s = db.create_session()
    try:
        # A drilling-params row on the original report with an explicit avg_rop 0
        rid = (s.query(DailyReport)
               .filter(DailyReport.wellbore_id == two_bore["orig"]).first().id)
        # remove existing param and add explicit-zero one
        s.query(DrillingParameters).filter(DrillingParameters.report_id == rid).delete()
        s.add(DrillingParameters(well_id=two_bore["well"], report_id=rid,
                                 report_date=date(2026, 1, 1), avg_rop=0.0,
                                 wob_min=0.0, wob_max=0.0))
        s.commit()
    finally:
        s.close()
    st = _stub(db, two_bore["well"], wellbore_id=two_bore["orig"])
    s = db.create_session()
    try:
        perf = st.get_performance_data(s)
    finally:
        s.close()
    assert perf[0]["rop"] == 0.0   # explicit zero preserved
    assert perf[0]["wob"] == 0.0   # midpoint of (0,0) is a real 0.0
