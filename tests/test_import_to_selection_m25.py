"""Mission 25 — Track L: Import → Wellbore → Selection chain (Qt-free parts).

Two guarantees are locked here without constructing MainWindow:

* The read helpers that build the post-import selection payload preserve the
  wellbore (bore) dimension: get_daily_report_by_id, get_sections_by_well and
  get_daily_reports_by_section all expose ``wellbore_id`` so a bore-tagged
  report can carry its scope into the selection.
* The effective-bore resolution rule used by _targeted_refresh (report's own
  wellbore_id wins, else the section's, else None=Whole-Well, never inferred to
  Original) is exercised as pure logic.

The SelectionManager signal-order / propagation guarantee is covered by the
subprocess Qt test ``test_import_to_selection_ui_smoke_m25.py``.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base, DatabaseManager, Company, Project, Well, Wellbore, Section,
    DailyReport,
)


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
def fixture(db):
    s = db.create_session()
    c = Company(name="C", code="C"); s.add(c); s.flush()
    p = Project(name="P", code="P", company_id=c.id); s.add(p); s.flush()
    w = Well(name="W1", code="W1", project_id=p.id); s.add(w); s.flush()
    orig = Wellbore(well_id=w.id, name="Original", wellbore_type="original")
    s.add(orig); s.flush()
    st1 = Wellbore(well_id=w.id, name="ST-1", wellbore_type="sidetrack",
                   parent_wellbore_id=orig.id, kickoff_md=2500)
    s.add(st1); s.flush()
    sec = Section(name='12-1/4"', well_id=w.id, wellbore_id=st1.id,
                  depth_from=2500)
    s.add(sec); s.flush()
    rpt = DailyReport(well_id=w.id, section_id=sec.id, wellbore_id=st1.id,
                      report_number=100, report_date=date(2026, 3, 1),
                      depth_2400=3000)
    s.add(rpt); s.flush()
    ids = {"well": w.id, "orig": orig.id, "st1": st1.id,
           "sec": sec.id, "rpt": rpt.id}
    s.commit(); s.close()
    return ids


# ---------------------------------------------------------------------------
# Read helpers preserve the bore dimension (§18, §45)
# ---------------------------------------------------------------------------

def test_get_daily_report_by_id_exposes_wellbore(db, fixture):
    row = db.get_daily_report_by_id(fixture["rpt"])
    assert row["wellbore_id"] == fixture["st1"]


def test_get_sections_by_well_exposes_wellbore(db, fixture):
    secs = db.get_sections_by_well(fixture["well"])
    sec = next(s for s in secs if s["id"] == fixture["sec"])
    assert sec["wellbore_id"] == fixture["st1"]


def test_get_daily_reports_by_section_exposes_wellbore(db, fixture):
    reports = db.get_daily_reports_by_section(fixture["sec"])
    assert reports and reports[0]["wellbore_id"] == fixture["st1"]


# ---------------------------------------------------------------------------
# Effective-bore resolution rule (mirror of _targeted_refresh logic)
# ---------------------------------------------------------------------------

def _resolve_effective_bore(report_data, section_data):
    """The exact rule _targeted_refresh applies."""
    wellbore_id = report_data.get("wellbore_id")
    if wellbore_id is None:
        wellbore_id = section_data.get("wellbore_id")
    return wellbore_id


def test_report_bore_wins(db, fixture):
    report_data = db.get_daily_report_by_id(fixture["rpt"])
    secs = db.get_sections_by_well(fixture["well"])
    section_data = next(s for s in secs if s["id"] == fixture["sec"])
    assert _resolve_effective_bore(report_data, section_data) == fixture["st1"]


def test_section_bore_used_when_report_bore_missing(db, fixture):
    section_data = {"wellbore_id": fixture["orig"]}
    report_data = {"wellbore_id": None}
    assert _resolve_effective_bore(report_data, section_data) == fixture["orig"]


def test_unknown_bore_stays_none_never_original(db, fixture):
    # Neither report nor section knows the bore -> None (Whole-Well). It must
    # NOT be inferred to be the Original bore.
    assert _resolve_effective_bore({"wellbore_id": None},
                                   {"wellbore_id": None}) is None
