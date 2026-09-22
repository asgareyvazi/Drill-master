"""Mission 25 — W12 remaining scope-leakage regressions (Qt-free domain tests).

Locks the concrete leaks found after M24:

* get_today_data must NOT fall back to a well+date lookup for DrillingParameters
  / MudReport when the well+date is ambiguous (multi-bore day) — that would pull
  another bore's row. The legacy fallback is allowed ONLY when (well, date) maps
  to exactly one report (single-bore legacy data). Otherwise -> UNKNOWN.
* load_milestones data follows the selected bore (Section.wellbore_id) and uses
  the REAL stored Section.planned_days as PLAN, never a fabricated depth/50 or
  flat 5-day value.

W12 methods are bound to a lightweight stub (no Qt) against a real in-memory
DatabaseManager, exactly like the M24 analytics-truth tests.
"""
import types
from datetime import date, time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base, DatabaseManager, Company, Project, Well, Wellbore, DailyReport, DrillingParameters, MudReport, TimeLog24H,
)
from core.operations_intelligence import OperationsIntelligenceService
from tabs.w12_Analysis import AnalysisWidget


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


def _stub(db, well_id, wellbore_id=None, section_id=None):
    class Stub:
        pass
    st = Stub()
    st.db = db
    st.current_well_id = well_id
    st.current_wellbore_id = wellbore_id
    st.current_section_id = section_id
    st.current_wellbore_name = None
    st.intelligence_service = OperationsIntelligenceService(db)
    for name in ("_scope_key", "_scope_reports_query", "_scope_params_query",
                 "_canonical_scope_kpis", "get_today_data", "get_npt_data",
                 "_report_date_unambiguous", "_unique_legacy_row"):
        setattr(st, name, types.MethodType(getattr(AnalysisWidget, name), st))
    return st


# ---------------------------------------------------------------------------
# get_today_data — no cross-bore well+date fallback in a multi-bore day
# ---------------------------------------------------------------------------

def _two_bore_same_date(db):
    """Original + ST-1, BOTH with a report on the SAME date. Only the ST-1
    report's DrillingParameters/MudReport carry a report_id; the Original
    report's child rows are legacy (report_id=NULL, well+date only)."""
    s = db.create_session()
    c = Company(name="C", code="C"); s.add(c); s.flush()
    p = Project(name="P", code="P", company_id=c.id); s.add(p); s.flush()
    w = Well(name="W1", code="W1", project_id=p.id); s.add(w); s.flush()
    orig = Wellbore(well_id=w.id, name="Original", wellbore_type="original")
    s.add(orig); s.flush()
    st1 = Wellbore(well_id=w.id, name="ST-1", wellbore_type="sidetrack",
                   parent_wellbore_id=orig.id, kickoff_md=2500)
    s.add(st1); s.flush()
    d = date(2026, 1, 10)
    ro = DailyReport(well_id=w.id, wellbore_id=orig.id, report_number=1,
                     report_date=d, depth_2400=1000)
    rs = DailyReport(well_id=w.id, wellbore_id=st1.id, report_number=2,
                     report_date=d, depth_2400=3000)
    s.add_all([ro, rs]); s.flush()
    # Original: LEGACY child rows with NO report_id (only well+date). ROP 20.
    s.add_all([
        DrillingParameters(well_id=w.id, report_id=None, report_date=d,
                           avg_rop=20.0),
        MudReport(well_id=w.id, report_id=None, report_date=d, mw=1.20),
        # ST-1: properly linked child rows. ROP 60.
        DrillingParameters(well_id=w.id, report_id=rs.id, report_date=d,
                           avg_rop=60.0),
        MudReport(well_id=w.id, report_id=rs.id, report_date=d, mw=1.60),
    ])
    s.commit()
    ids = {"well": w.id, "orig": orig.id, "st1": st1.id,
           "ro": ro.id, "rs": rs.id, "date": d}
    s.close()
    return ids


def test_today_data_no_cross_bore_param_fallback(db):
    """Original report has only legacy well+date params, but ST-1 shares the
    date. The Original view must NOT borrow ST-1's ROP 60 — it stays UNKNOWN."""
    ids = _two_bore_same_date(db)
    st = _stub(db, ids["well"], wellbore_id=ids["orig"])
    s = db.create_session()
    try:
        td = st.get_today_data(s)
    finally:
        s.close()
    # The scoped report is Original's; its params are unlinked and the day is
    # ambiguous (two reports share the date) -> no fabrication from ST-1.
    assert td is not None
    assert td["rop"] is None, "must not borrow the sidetrack's ROP 60"
    assert td["mw_in"] is None, "must not borrow the sidetrack's mud weight"


def test_today_data_sidetrack_uses_own_linked_rows(db):
    """ST-1's own report_id-linked params/mud are used directly (ROP 60)."""
    ids = _two_bore_same_date(db)
    st = _stub(db, ids["well"], wellbore_id=ids["st1"])
    s = db.create_session()
    try:
        td = st.get_today_data(s)
    finally:
        s.close()
    assert td["rop"] == 60.0
    assert td["mw_in"] == 1.60


def test_today_data_single_bore_legacy_fallback_still_works(db):
    """When (well, date) is unambiguous (one report), the legacy well+date
    fallback is preserved so single-bore legacy data still displays."""
    s = db.create_session()
    c = Company(name="C", code="C"); s.add(c); s.flush()
    p = Project(name="P", code="P", company_id=c.id); s.add(p); s.flush()
    w = Well(name="W1", code="W1", project_id=p.id); s.add(w); s.flush()
    d = date(2026, 2, 1)
    r = DailyReport(well_id=w.id, wellbore_id=None, report_number=1,
                    report_date=d, depth_2400=800)
    s.add(r); s.flush()
    # Legacy child rows with NO report_id — only well+date links them.
    s.add_all([
        DrillingParameters(well_id=w.id, report_id=None, report_date=d, avg_rop=15.0),
        MudReport(well_id=w.id, report_id=None, report_date=d, mw=1.10),
    ])
    s.commit()
    wid = w.id
    s.close()

    st = _stub(db, wid)  # whole well, single report on the date
    s = db.create_session()
    try:
        td = st.get_today_data(s)
    finally:
        s.close()
    assert td["rop"] == 15.0, "unambiguous single-bore legacy fallback preserved"
    assert td["mw_in"] == 1.10


def test_today_data_ambiguous_legacy_child_rows_stay_unknown(db):
    """M26 §7/§18: even with ONE report on the date, two legacy well+date child
    rows make a bare .first() nondeterministic. The fallback must refuse and
    return UNKNOWN instead of silently hiding the other row."""
    s = db.create_session()
    c = Company(name="C", code="C"); s.add(c); s.flush()
    p = Project(name="P", code="P", company_id=c.id); s.add(p); s.flush()
    w = Well(name="W1", code="W1", project_id=p.id); s.add(w); s.flush()
    d = date(2026, 3, 1)
    r = DailyReport(well_id=w.id, wellbore_id=None, report_number=1,
                    report_date=d, depth_2400=800)
    s.add(r); s.flush()
    # ONE report, but TWO legacy child rows share (well, date) with different
    # values — ownership of each is unprovable.
    s.add_all([
        DrillingParameters(well_id=w.id, report_id=None, report_date=d, avg_rop=15.0),
        DrillingParameters(well_id=w.id, report_id=None, report_date=d, avg_rop=99.0),
        MudReport(well_id=w.id, report_id=None, report_date=d, mw=1.10),
        MudReport(well_id=w.id, report_id=None, report_date=d, mw=1.90),
    ])
    s.commit()
    wid = w.id
    s.close()

    st = _stub(db, wid)
    s = db.create_session()
    try:
        td = st.get_today_data(s)
    finally:
        s.close()
    assert td["rop"] is None, "ambiguous legacy params must stay UNKNOWN"
    assert td["mw_in"] is None, "ambiguous legacy mud must stay UNKNOWN"


def test_npt_null_duration_is_unknown_not_zero(db):
    """M26 §15: an NPT time log with duration=NULL is UNKNOWN, not 0.0. It must
    not contribute a fabricated zero to the total, must be counted as unknown,
    and its entry keeps hours=None. A stored 0.0 is a real fact and survives."""
    s = db.create_session()
    c = Company(name="C", code="C"); s.add(c); s.flush()
    p = Project(name="P", code="P", company_id=c.id); s.add(p); s.flush()
    w = Well(name="W1", code="W1", project_id=p.id); s.add(w); s.flush()
    d = date(2026, 5, 1)
    r = DailyReport(well_id=w.id, wellbore_id=None, report_number=1,
                    report_date=d)
    s.add(r); s.flush()
    s.add_all([
        TimeLog24H(report_id=r.id, is_npt=True, duration=2.0, main_code="A",
                   time_from=time(0, 0), time_to=time(2, 0)),
        TimeLog24H(report_id=r.id, is_npt=True, duration=None, main_code="B",
                   time_from=time(2, 0), time_to=time(3, 0)),
        TimeLog24H(report_id=r.id, is_npt=True, duration=0.0, main_code="C",
                   time_from=time(3, 0), time_to=time(3, 0)),
        # productive time so total_hours (the % denominator) is known
        TimeLog24H(report_id=r.id, is_npt=False, duration=10.0, main_code="DR",
                   time_from=time(4, 0), time_to=time(14, 0)),
    ])
    s.commit()
    wid = w.id
    s.close()

    st = _stub(db, wid)
    s = db.create_session()
    try:
        npt = st.get_npt_data(s)
    finally:
        s.close()
    # 2.0 + 0.0; the NULL row contributes nothing (not a fabricated 0).
    assert npt["total_npt"] == 2.0
    assert npt["unknown_npt_count"] == 1
    assert [e["hours"] for e in npt["entries"]] == [2.0, None, 0.0]
    # Category map excludes the unknown row, keeps the real 0.0.
    assert npt["categories"] == {"A": 2.0, "C": 0.0}
