"""KPI convergence regressions — Mission 21.

W12 previously computed several KPIs with independent SQL that could silently
disagree with the canonical ``OperationsIntelligenceService`` — most concretely
``current_depth`` (W12 used latest-by-date, the canonical service uses the
well's MAX recorded depth). These diverge whenever a later report records a
shallower depth (correction / section change).

These tests lock W12's shared KPIs to the canonical source (semantic parity,
not formatting) and preserve the no-fabrication contract (unknown != 0).

Qt-free: ``calculate_kpis`` is exercised as an unbound method against a tiny
stand-in holding only ``current_well_id``, ``db`` and ``intelligence_service``.
"""
from datetime import date, time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base, DatabaseManager, Company, Project, Well, DailyReport,
    DrillingParameters, TimeLog24H,
)
from core.operations_intelligence import OperationsIntelligenceService
from tabs.w12_Analysis import AnalysisWidget


def memory_manager():
    m = DatabaseManager()
    m.engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    return m


class _Stub:
    """Minimal stand-in exposing exactly what calculate_kpis touches."""
    def __init__(self, db, well_id):
        self.db = db
        self.current_well_id = well_id
        self.intelligence_service = OperationsIntelligenceService(db)


def seed_well(m, depths_rops, npt=True):
    s = m.create_session()
    try:
        c = Company(name="X", code="X"); s.add(c); s.flush()
        p = Project(name="P", code="P", company_id=c.id); s.add(p); s.flush()
        w = Well(name="W", code="W", project_id=p.id); s.add(w); s.flush()
        wid = w.id
        for d, depth, rop in depths_rops:
            r = DailyReport(well_id=wid, report_date=d, depth_2400=depth)
            s.add(r); s.flush()
            if rop is not None:
                s.add(DrillingParameters(well_id=wid, report_date=d, avg_rop=rop))
            if npt:
                s.add(TimeLog24H(report_id=r.id, time_from=time(0, 0),
                                 time_to=time(20, 0), duration=20.0, is_npt=False))
                s.add(TimeLog24H(report_id=r.id, time_from=time(20, 0),
                                 time_to=time(0, 0), duration=4.0, is_npt=True))
        s.commit()
        return wid
    finally:
        s.close()


def w12_kpis(m, wid):
    session = m.create_session()
    try:
        return AnalysisWidget.calculate_kpis.__get__(_Stub(m, wid))(session)
    finally:
        session.close()


@pytest.fixture
def m():
    mgr = memory_manager()
    yield mgr
    mgr.close()


class TestParity:
    def test_current_depth_is_max_not_latest(self, m):
        # Last report (1/3) is SHALLOWER than 1/2 -> latest-by-date != max.
        wid = seed_well(m, [
            (date(2026, 1, 1), 1000, 10.0),
            (date(2026, 1, 2), 1500, 20.0),
            (date(2026, 1, 3), 1400, 30.0),
        ])
        canonical = OperationsIntelligenceService(m).analyze_well(wid)["kpis"]
        w12 = w12_kpis(m, wid)
        assert canonical["current_depth"] == 1500.0
        assert w12["current_depth"] == canonical["current_depth"]

    def test_shared_metrics_match_canonical(self, m):
        wid = seed_well(m, [
            (date(2026, 1, 1), 1000, 10.0),
            (date(2026, 1, 2), 1500, 20.0),
            (date(2026, 1, 3), 2000, 30.0),
        ])
        canonical = OperationsIntelligenceService(m).analyze_well(wid)["kpis"]
        w12 = w12_kpis(m, wid)
        assert w12["avg_rop"] == canonical["average_rop"]
        assert w12["npt_percentage"] == canonical["npt_percent"]
        assert w12["total_npt"] == canonical["npt_hours"]
        assert w12["total_days"] == canonical["rig_days"]

    def test_no_parameters_gives_unknown_rop_not_zero(self, m):
        wid = seed_well(m, [(date(2026, 1, 1), 1000, None)], npt=False)
        w12 = w12_kpis(m, wid)
        assert w12["avg_rop"] is None       # unknown, not 0.0
        assert w12["npt_percentage"] is None  # no time recorded -> unknown
        assert w12["efficiency"] is None

    def test_zero_npt_with_hours_is_real_zero(self, m):
        wid = seed_well(m, [(date(2026, 1, 1), 1000, 10.0)], npt=False)
        # Add only productive time (no NPT rows) -> npt% is a real 0, not None.
        s = m.create_session()
        try:
            rid = s.query(DailyReport).filter_by(well_id=wid).first().id
            s.add(TimeLog24H(report_id=rid, time_from=time(0, 0),
                             time_to=time(0, 0), duration=24.0, is_npt=False))
            s.commit()
        finally:
            s.close()
        canonical = OperationsIntelligenceService(m).analyze_well(wid)["kpis"]
        w12 = w12_kpis(m, wid)
        assert canonical["npt_percent"] == 0.0
        assert w12["npt_percentage"] == 0.0
        assert w12["efficiency"] == 100.0

    def test_empty_well_all_none(self, m):
        s = m.create_session()
        try:
            c = Company(name="Y", code="Y"); s.add(c); s.flush()
            p = Project(name="P", code="P", company_id=c.id); s.add(p); s.flush()
            w = Well(name="Empty", code="E", project_id=p.id); s.add(w); s.commit()
            wid = w.id
        finally:
            s.close()
        w12 = w12_kpis(m, wid)
        assert w12["avg_rop"] is None
        assert w12["current_depth"] in (None, 0.0)
        assert w12["npt_percentage"] is None
