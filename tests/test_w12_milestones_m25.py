"""Mission 25 — W12 Milestones scope + plan-truth regressions (Qt-free).

* Milestones follow the selected bore: a bore selection narrows to the sections
  that bore owns (Section.wellbore_id); whole-well shows every section.
* PLAN uses the REAL stored Section.planned_days — never a fabricated
  depth/50 or flat 5-day value. A section with no stored plan contributes 0
  (nothing planned), not an invented duration.

``load_milestones_data`` normally renders a matplotlib chart; we capture its
inputs by binding it to a stub whose ``_draw_milestones_chart`` records the
series, so the selection/plan logic is exercised without Qt.
"""
import types
from datetime import date, time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base, DatabaseManager, Company, Project, Well, Wellbore, Section,
    DailyReport, TimeLog24H,
)
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


@pytest.fixture()
def two_bore_sections(db):
    s = db.create_session()
    c = Company(name="C", code="C"); s.add(c); s.flush()
    p = Project(name="P", code="P", company_id=c.id); s.add(p); s.flush()
    w = Well(name="W1", code="W1", project_id=p.id); s.add(w); s.flush()
    orig = Wellbore(well_id=w.id, name="Original", wellbore_type="original")
    s.add(orig); s.flush()
    st1 = Wellbore(well_id=w.id, name="ST-1", wellbore_type="sidetrack",
                   parent_wellbore_id=orig.id, kickoff_md=2500)
    s.add(st1); s.flush()
    # Original section: real stored plan of 8 days.
    sec_o = Section(name='12-1/4"', well_id=w.id, wellbore_id=orig.id,
                    depth_from=1000, depth_to=2000, planned_days=8.0)
    # Sidetrack section: real stored plan of 3 days.
    sec_s = Section(name='8-1/2"', well_id=w.id, wellbore_id=st1.id,
                    depth_from=2500, depth_to=3000, planned_days=3.0)
    # A section with NO stored plan (planned_days left at default 0).
    sec_np = Section(name='17-1/2"', well_id=w.id, wellbore_id=orig.id,
                     depth_from=0, depth_to=1000, planned_days=0.0)
    s.add_all([sec_o, sec_s, sec_np]); s.flush()
    ro = DailyReport(well_id=w.id, section_id=sec_o.id, wellbore_id=orig.id,
                     report_number=1, report_date=date(2026, 1, 1))
    rs = DailyReport(well_id=w.id, section_id=sec_s.id, wellbore_id=st1.id,
                     report_number=2, report_date=date(2026, 1, 5))
    s.add_all([ro, rs]); s.flush()
    s.add_all([
        TimeLog24H(report_id=ro.id, time_from=time(0, 0), time_to=time(23, 0),
                   duration=24.0, is_npt=False),   # 1 day fact on Original sec
        TimeLog24H(report_id=rs.id, time_from=time(0, 0), time_to=time(23, 0),
                   duration=48.0, is_npt=False),   # 2 days fact on ST section
    ])
    s.commit()
    ids = {"well": w.id, "orig": orig.id, "st1": st1.id,
           "sec_o": sec_o.id, "sec_s": sec_s.id, "sec_np": sec_np.id}
    s.close()
    return ids


def _milestone_stub(db, well_id, wellbore_id=None):
    class Stub:
        pass
    st = Stub()
    st.db = db
    st.current_well_id = well_id
    st.current_wellbore_id = wellbore_id
    st.current_wellbore_name = None
    st.captured = None
    st.milestones_scope_label = types.SimpleNamespace(
        _text="", setText=lambda t: setattr(st.milestones_scope_label, "_text", t))
    st._draw_milestones_chart = lambda names, fact, plan: setattr(
        st, "captured", (list(names), list(fact), list(plan)))
    for name in ("load_milestones_data", "_update_milestones_scope_label",
                 "_load_milestones_from_reports"):
        setattr(st, name, types.MethodType(getattr(AnalysisWidget, name), st))
    return st


def test_milestones_whole_well_spans_all_sections(db, two_bore_sections):
    st = _milestone_stub(db, two_bore_sections["well"])
    st.load_milestones_data()
    names, fact, plan = st.captured
    # All three sections (both bores) present.
    assert set(names) == {'12-1/4"', '8-1/2"', '17-1/2"'}
    assert st.milestones_scope_label._text == "Scope: Whole Well"


def test_milestones_bore_scoped_to_selected_wellbore(db, two_bore_sections):
    st = _milestone_stub(db, two_bore_sections["well"],
                         wellbore_id=two_bore_sections["st1"])
    st.current_wellbore_name = "ST-1"
    st.load_milestones_data()
    names, fact, plan = st.captured
    # Only the sidetrack's section — Original's sections are excluded.
    assert names == ['8-1/2"']
    assert plan == [3.0]           # real stored plan, not fabricated
    assert fact == [2.0]           # 48h / 24
    assert "ST-1" in st.milestones_scope_label._text


def test_milestones_uses_real_stored_plan_not_fabricated(db, two_bore_sections):
    st = _milestone_stub(db, two_bore_sections["well"],
                         wellbore_id=two_bore_sections["orig"])
    st.load_milestones_data()
    names, fact, plan = st.captured
    # Original bore owns the 12-1/4" (plan 8) and 17-1/2" (no plan -> 0).
    by_name = dict(zip(names, plan))
    assert by_name['12-1/4"'] == 8.0          # real stored plan
    # No stored plan -> 0 (nothing planned), never depth/50 (=20) or flat 5.
    assert by_name['17-1/2"'] == 0.0
    # depth/50 would have produced (1000-0)/50 = 20; prove that did NOT happen.
    assert by_name['17-1/2"'] != 20.0


def test_milestones_no_sections_bore_scope_is_empty(db):
    """A bore with no sections yields an empty bore-scoped milestones chart
    (never the whole-well report fallback, which is not bore-scoped)."""
    s = db.create_session()
    c = Company(name="C", code="C"); s.add(c); s.flush()
    p = Project(name="P", code="P", company_id=c.id); s.add(p); s.flush()
    w = Well(name="W1", code="W1", project_id=p.id); s.add(w); s.flush()
    orig = Wellbore(well_id=w.id, name="Original", wellbore_type="original")
    s.add(orig); s.flush()
    # A report but NO sections for this bore.
    s.add(DailyReport(well_id=w.id, wellbore_id=orig.id, report_number=1,
                      report_date=date(2026, 1, 1), depth_2400=500))
    s.commit()
    wid, oid = w.id, orig.id
    s.close()
    st = _milestone_stub(db, wid, wellbore_id=oid)
    st.load_milestones_data()
    names, fact, plan = st.captured
    assert names == [] and fact == [] and plan == []
