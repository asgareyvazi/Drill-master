"""W12 analytics truth-boundary regressions — Mission 23 Track C.

Locks the unknown-vs-zero contract for the W12 secondary analytical readers
(the shared KPI cards are already canonical via OperationsIntelligenceService):

  * DailyReport depth columns keep the trichotomy: a MISSING depth stays NULL,
    an explicit reported 0 stays 0.0. The client-side default=0.0 that collapsed
    missing into fabricated zero has been removed (§22).
  * get_time_depth_data never fabricates a depth or a gain from a missing depth;
    the gain is measured against the last KNOWN depth, so a gap does not create a
    false plunge-and-recovery (§22, Class C calculation contamination).
  * get_today_data returns None (rendered "—") for unknown physical measurements
    rather than a fabricated 0 (§20, Class B presentation fabrication), while a
    genuine reported 0 survives.

Qt-free: the widget's data methods are called as unbound functions against a
lightweight stub holding ``current_well_id`` and a real in-memory session.
"""
from datetime import date, time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base, DatabaseManager, Company, Project, Well, DailyReport,
    DrillingParameters, TimeLog24H,
)
from tabs.w12_Analysis import AnalysisWidget


import types


class _Stub:
    """Minimal carrier so we can call the widget's data methods Qt-free.

    These readers became scope-aware in Mission 24 (Track B): they resolve the
    active scope through ``_scope_reports_query`` / ``_scope_params_query``. The
    stub carries the whole-well scope (no bore/section selected) and binds those
    helpers off the real class, so the unknown-vs-zero contract asserted here is
    exercised against exactly the production filtering code.
    """
    def __init__(self, well_id):
        self.current_well_id = well_id
        self.current_wellbore_id = None
        self.current_section_id = None
        for name in ("_scope_key", "_scope_reports_query",
                     "_scope_params_query", "_canonical_scope_kpis",
                     "_report_date_unambiguous", "_unique_legacy_row"):
            setattr(self, name,
                    types.MethodType(getattr(AnalysisWidget, name), self))


def _mgr():
    m = DatabaseManager()
    m.engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    return m


def _well(m):
    s = m.create_session()
    try:
        c = Company(name="OP", code="OP"); s.add(c); s.flush()
        p = Project(name="PR", code="PR", company_id=c.id); s.add(p); s.flush()
        w = Well(name="W1", code="W1", project_id=p.id); s.add(w); s.flush()
        s.commit()
        return w.id
    finally:
        s.close()


# ---------------------------------------------------------------------------
# DB trichotomy for depth
# ---------------------------------------------------------------------------

class TestDepthTrichotomy:
    def test_missing_depth_stays_null(self):
        m = _mgr(); wid = _well(m)
        s = m.create_session()
        try:
            r = DailyReport(well_id=wid, report_date=date(2026, 1, 1), depth_2400=None)
            s.add(r); s.commit()
            assert r.depth_2400 is None  # no fabricated 0
        finally:
            s.close()

    def test_explicit_zero_depth_preserved(self):
        m = _mgr(); wid = _well(m)
        s = m.create_session()
        try:
            r = DailyReport(well_id=wid, report_date=date(2026, 1, 1), depth_2400=0.0)
            s.add(r); s.commit()
            assert r.depth_2400 == 0.0
        finally:
            s.close()


# ---------------------------------------------------------------------------
# get_time_depth_data
# ---------------------------------------------------------------------------

class TestTimeDepth:
    def _seed(self, m, wid, depths):
        s = m.create_session()
        try:
            for i, depth in enumerate(depths):
                s.add(DailyReport(well_id=wid, report_date=date(2026, 1, i + 1),
                                  depth_2400=depth))
            s.commit()
        finally:
            s.close()

    def _run(self, m, wid):
        s = m.create_session()
        try:
            return AnalysisWidget.get_time_depth_data(_Stub(wid), s)
        finally:
            s.close()

    def test_missing_middle_depth_does_not_fabricate_gain(self):
        m = _mgr(); wid = _well(m)
        self._seed(m, wid, [1000.0, None, 1200.0])
        res = self._run(m, wid)
        assert res[0]["depth"] == 1000.0 and res[0]["gain"] is None
        assert res[1]["depth"] is None and res[1]["gain"] is None
        assert res[1]["status"] == "Unknown"
        # Gain measured against last KNOWN depth (1000), not the fabricated 0.
        assert res[2]["depth"] == 1200.0 and res[2]["gain"] == 200.0

    def test_leading_missing_depth(self):
        m = _mgr(); wid = _well(m)
        self._seed(m, wid, [None, 1000.0])
        res = self._run(m, wid)
        assert res[0]["depth"] is None and res[0]["gain"] is None
        # First KNOWN depth has no prior reference -> gain unknown, not depth.
        assert res[1]["depth"] == 1000.0 and res[1]["gain"] is None

    def test_normal_progression_gain(self):
        m = _mgr(); wid = _well(m)
        self._seed(m, wid, [1000.0, 1100.0, 1250.0])
        res = self._run(m, wid)
        assert res[1]["gain"] == 100.0 and res[1]["status"] == "Normal"
        assert res[2]["gain"] == 150.0

    def test_explicit_zero_depth_is_a_fact_not_gap(self):
        m = _mgr(); wid = _well(m)
        self._seed(m, wid, [0.0, 500.0])
        res = self._run(m, wid)
        # Day 1 explicit 0 depth is known; day 2 gain is 500 - 0.
        assert res[0]["depth"] == 0.0 and res[0]["gain"] is None
        assert res[1]["gain"] == 500.0


# ---------------------------------------------------------------------------
# get_today_data
# ---------------------------------------------------------------------------

class TestTodayData:
    def _run(self, m, wid):
        s = m.create_session()
        try:
            return AnalysisWidget.get_today_data(_Stub(wid), s)
        finally:
            s.close()

    def test_unknown_measurements_are_none(self):
        m = _mgr(); wid = _well(m)
        s = m.create_session()
        try:
            # A report with no depth, no drilling params, no mud, no time logs.
            s.add(DailyReport(well_id=wid, report_date=date(2026, 1, 1),
                              depth_2400=None, rig_day=None))
            s.commit()
        finally:
            s.close()
        today = self._run(m, wid)
        assert today["depth"] is None
        assert today["rop"] is None
        assert today["wob"] is None
        assert today["rpm"] is None
        assert today["torque"] is None
        assert today["pressure"] is None
        assert today["mw_in"] is None and today["mw_out"] is None
        # No time logs at all -> hours/npt unknown, not fabricated 0.
        assert today["hours"] is None
        assert today["npt_hours"] is None

    def test_recorded_time_with_no_npt_is_real_zero(self):
        m = _mgr(); wid = _well(m)
        s = m.create_session()
        try:
            r = DailyReport(well_id=wid, report_date=date(2026, 1, 1), depth_2400=1500.0)
            s.add(r); s.flush()
            # A recorded (non-NPT) time log exists.
            s.add(TimeLog24H(report_id=r.id, time_from=time(0, 0), time_to=time(12, 0),
                             duration=12.0, is_npt=False))
            s.commit()
        finally:
            s.close()
        today = self._run(m, wid)
        assert today["depth"] == 1500.0
        assert today["hours"] == 12.0
        assert today["npt_hours"] == 0.0  # real zero NPT, time was recorded

    def test_midpoint_requires_both_bounds(self):
        m = _mgr(); wid = _well(m)
        s = m.create_session()
        try:
            r = DailyReport(well_id=wid, report_date=date(2026, 1, 1), depth_2400=100.0)
            s.add(r); s.flush()
            # WOB has both bounds; RPM only a min -> RPM midpoint unknown.
            s.add(DrillingParameters(well_id=wid, report_date=date(2026, 1, 1),
                                     wob_min=10.0, wob_max=20.0, rpm_min=100.0))
            s.commit()
        finally:
            s.close()
        today = self._run(m, wid)
        assert today["wob"] == 15.0
        assert today["rpm"] is None  # single bound is not a midpoint
