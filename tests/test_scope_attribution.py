"""Deterministic scope-attribution (Well → Wellbore → Section) regression tests.

These pin the four-state attribution contract of
``core.scope_attribution.ScopeAttributionService``:

* RESOLVED only when ownership is provably unique (via the report's own section,
  or a well/wellbore with exactly one child).
* AMBIGUOUS when >1 candidate and no canonical discriminator — left NULL.
* UNRESOLVED when 0 candidates — left NULL.
* Existing valid scope is preserved (ALREADY) and never overwritten.
* Cross-well assignment is impossible (persistence invariants are the net).
* Resolution is idempotent.
* After safe resolution, Wellbore/Section KPIs gain coverage; still-NULL rows
  keep unknown (None) KPI semantics.
"""

from __future__ import annotations

from datetime import date, time as dtime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base,
    Company,
    DailyReport,
    DatabaseManager,
    DrillingParameters,
    Project,
    Section,
    TimeLog24H,
    Well,
    Wellbore,
)
from core.import_diagnostics import OwnershipIntegrityError
from core.operations_intelligence import OperationsIntelligenceService
from core.scope_attribution import (
    ALREADY,
    AMBIGUOUS,
    INVALID,
    RESOLVED,
    UNRESOLVED,
    ScopeAttributionService,
)


def _mgr():
    m = DatabaseManager()
    m.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(m.engine, "connect")
    def _fk(dbapi, _rec):  # pragma: no cover - trivial
        dbapi.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    return m


def _base(m):
    s = m.create_session()
    co = Company(name="C", code="C")
    s.add(co)
    s.flush()
    pr = Project(name="P", code="P", company_id=co.id)
    s.add(pr)
    s.flush()
    pid = pr.id
    s.commit()
    s.close()
    return pid


def _well(m, pid, name):
    s = m.create_session()
    try:
        w = Well(name=name, code=name, project_id=pid)
        s.add(w)
        s.flush()
        wid = w.id
        s.commit()
        return wid
    finally:
        s.close()


def _wellbore(m, well_id, name, wtype="original", parent=None):
    s = m.create_session()
    try:
        wb = Wellbore(well_id=well_id, name=name, wellbore_type=wtype,
                      parent_wellbore_id=parent)
        s.add(wb)
        s.flush()
        wid = wb.id
        s.commit()
        return wid
    finally:
        s.close()


def _section(m, well_id, name, wellbore_id=None):
    s = m.create_session()
    try:
        sec = Section(well_id=well_id, wellbore_id=wellbore_id, name=name)
        s.add(sec)
        s.flush()
        sid = sec.id
        s.commit()
        return sid
    finally:
        s.close()


def _report(m, well_id, day, wellbore_id=None, section_id=None, depth=100):
    s = m.create_session()
    try:
        dr = DailyReport(well_id=well_id, wellbore_id=wellbore_id,
                         section_id=section_id, report_date=date(2026, 1, day),
                         depth_2400=depth)
        s.add(dr)
        s.flush()
        rid = dr.id
        s.commit()
        return rid
    finally:
        s.close()


def _get_report(m, rid):
    s = m.create_session()
    try:
        dr = s.get(DailyReport, rid)
        return (dr.wellbore_id, dr.section_id)
    finally:
        s.close()


def _status(report, rid, dimension):
    for o in report.outcomes:
        if o.report_id == rid and o.dimension == dimension:
            return o
    raise AssertionError(f"no {dimension} outcome for report {rid}")


# --- A/B: single-wellbore / single-section deterministic resolution ---------


def test_single_wellbore_and_section_resolved():
    m = _mgr()
    pid = _base(m)
    w = _well(m, pid, "A")
    wb = _wellbore(m, w, "A1")
    sec = _section(m, w, "17.5", wellbore_id=wb)
    r = _report(m, w, 1)  # both NULL
    rep = ScopeAttributionService(m).resolve()
    assert _status(rep, r, "wellbore").status == RESOLVED
    assert _status(rep, r, "section").status == RESOLVED
    assert _get_report(m, r) == (wb, sec)


def test_wellbore_resolved_via_section():
    m = _mgr()
    pid = _base(m)
    w = _well(m, pid, "A")
    wb1 = _wellbore(m, w, "A1")
    wb2 = _wellbore(m, w, "A2", wtype="sidetrack", parent=wb1)
    sec = _section(m, w, "12.25", wellbore_id=wb2)
    # report has section (owned by wb2) but NULL wellbore; must resolve to wb2
    r = _report(m, w, 1, section_id=sec)
    rep = ScopeAttributionService(m).resolve()
    out = _status(rep, r, "wellbore")
    assert out.status == RESOLVED and out.method == "via_section"
    assert _get_report(m, r)[0] == wb2  # NOT wb1


# --- C/D: ambiguity is preserved, never guessed ----------------------------


def test_multiple_wellbores_ambiguous():
    m = _mgr()
    pid = _base(m)
    w = _well(m, pid, "B")
    _wellbore(m, w, "B1")
    _wellbore(m, w, "B2", wtype="sidetrack", parent=None)
    r = _report(m, w, 1)  # no section, 2 bores
    rep = ScopeAttributionService(m).resolve()
    assert _status(rep, r, "wellbore").status == AMBIGUOUS
    assert _get_report(m, r)[0] is None


def test_multiple_sections_ambiguous():
    m = _mgr()
    pid = _base(m)
    w = _well(m, pid, "A")
    wb = _wellbore(m, w, "A1")
    _section(m, w, "17.5", wellbore_id=wb)
    _section(m, w, "12.25", wellbore_id=wb)
    r = _report(m, w, 1)  # unique wellbore, but 2 sections in it
    rep = ScopeAttributionService(m).resolve()
    assert _status(rep, r, "wellbore").status == RESOLVED   # unique bore
    assert _status(rep, r, "section").status == AMBIGUOUS   # 2 sections
    assert _get_report(m, r)[1] is None


# --- E: missing scope stays unknown ----------------------------------------


def test_no_wellbore_no_section_unresolved():
    m = _mgr()
    pid = _base(m)
    w = _well(m, pid, "C")
    r = _report(m, w, 1)
    rep = ScopeAttributionService(m).resolve()
    assert _status(rep, r, "wellbore").status == UNRESOLVED
    assert _status(rep, r, "section").status == UNRESOLVED
    assert _get_report(m, r) == (None, None)


# --- F/G: foreign wellbore / section rejected at persistence ----------------


def test_foreign_wellbore_rejected_by_invariant():
    m = _mgr()
    pid = _base(m)
    wa = _well(m, pid, "A")
    wb = _well(m, pid, "B")
    foreign = _wellbore(m, wb, "B1")
    r = _report(m, wa, 1)
    s = m.create_session()
    try:
        dr = s.get(DailyReport, r)
        dr.wellbore_id = foreign  # foreign bore
        with pytest.raises(OwnershipIntegrityError):
            s.commit()
    finally:
        s.rollback()
        s.close()


def test_foreign_section_rejected_by_invariant():
    m = _mgr()
    pid = _base(m)
    wa = _well(m, pid, "A")
    wb = _well(m, pid, "B")
    foreign_sec = _section(m, wb, "17.5")
    r = _report(m, wa, 1)
    s = m.create_session()
    try:
        dr = s.get(DailyReport, r)
        dr.section_id = foreign_sec
        with pytest.raises(OwnershipIntegrityError):
            s.commit()
    finally:
        s.rollback()
        s.close()


# --- H: existing valid scope preserved -------------------------------------


def test_existing_scope_preserved_not_overwritten():
    m = _mgr()
    pid = _base(m)
    w = _well(m, pid, "A")
    wb1 = _wellbore(m, w, "A1")
    wb2 = _wellbore(m, w, "A2", wtype="sidetrack", parent=wb1)
    sec2 = _section(m, w, "12.25", wellbore_id=wb2)
    # report already correctly attributed to wb2/sec2
    r = _report(m, w, 1, wellbore_id=wb2, section_id=sec2)
    rep = ScopeAttributionService(m).resolve()
    assert _status(rep, r, "wellbore").status == ALREADY
    assert _status(rep, r, "section").status == ALREADY
    assert rep.applied == 0
    assert _get_report(m, r) == (wb2, sec2)


# --- I: idempotent -----------------------------------------------------------


def test_resolution_is_idempotent():
    m = _mgr()
    pid = _base(m)
    w = _well(m, pid, "A")
    wb = _wellbore(m, w, "A1")
    _section(m, w, "17.5", wellbore_id=wb)
    _report(m, w, 1)
    svc = ScopeAttributionService(m)
    first = svc.resolve()
    assert first.applied == 2  # wellbore + section
    second = svc.resolve()
    assert second.applied == 0


# --- J/K: sidetrack sibling isolation --------------------------------------


def test_sidetrack_sibling_not_cross_attributed():
    m = _mgr()
    pid = _base(m)
    w = _well(m, pid, "A")
    wb1 = _wellbore(m, w, "A1")
    wb2 = _wellbore(m, w, "A2", wtype="sidetrack", parent=wb1)
    s1 = _section(m, w, "S1", wellbore_id=wb1)
    _section(m, w, "S2", wellbore_id=wb2)
    # report tied to section S1 (bore wb1) with NULL wellbore
    r = _report(m, w, 1, section_id=s1)
    ScopeAttributionService(m).resolve()
    assert _get_report(m, r)[0] == wb1  # never wb2


# --- INVALID detection (defensive, read-only) ------------------------------


def test_invalid_when_report_wellbore_contradicts_section(monkeypatch):
    # Build a legitimately-attributed report, then simulate a contradictory
    # state by bypassing the invariant (raw column mutation via analyze only).
    m = _mgr()
    pid = _base(m)
    w = _well(m, pid, "A")
    wb1 = _wellbore(m, w, "A1")
    wb2 = _wellbore(m, w, "A2", wtype="sidetrack", parent=wb1)
    s1 = _section(m, w, "S1", wellbore_id=wb1)
    r = _report(m, w, 1, wellbore_id=wb1, section_id=s1)
    # Move the section under wb2 directly in the DB (no report change), creating
    # a report(wb1) vs section(wb2) contradiction that analyze must flag.
    s = m.create_session()
    try:
        sec = s.get(Section, s1)
        sec.wellbore_id = wb2  # allowed: section still in well A
        s.commit()
    finally:
        s.close()
    rep = ScopeAttributionService(m).analyze(w)
    assert _status(rep, r, "wellbore").status == INVALID


# --- Coverage metric --------------------------------------------------------


def test_coverage_reports_real_quality_not_fabricated():
    m = _mgr()
    pid = _base(m)
    w = _well(m, pid, "A")
    wb = _wellbore(m, w, "A1")
    _section(m, w, "17.5", wellbore_id=wb)
    _report(m, w, 1)  # resolvable
    _report(m, w, 2, wellbore_id=wb)  # already
    svc = ScopeAttributionService(m)
    before = svc.coverage(w)
    assert before["wellbore_coverage_pct"] == 100.0  # 1 already + 1 resolvable
    # A well with no reports -> None (unknown), never fabricated 0/100.
    empty_well = _well(m, pid, "Z")
    empty = svc.coverage(empty_well)
    assert empty["wellbore_coverage_pct"] is None
    assert empty["total_reports"] == 0


# --- L/M/N: KPI coverage improvement after resolution ----------------------


def test_kpi_coverage_improves_after_resolution():
    m = _mgr()
    pid = _base(m)
    w = _well(m, pid, "A")
    wb = _wellbore(m, w, "A1")
    sec = _section(m, w, "17.5", wellbore_id=wb)
    # Two reports with NULL wellbore/section, drilling params + time logs.
    for day, (di, do, h) in [(1, (1000, 1100, 5)), (2, (1100, 1400, 5))]:
        s = m.create_session()
        dr = DailyReport(well_id=w, report_date=date(2026, 1, day),
                         depth_2400=do)
        s.add(dr)
        s.flush()
        rid = dr.id
        s.add(DrillingParameters(well_id=w, report_id=rid,
                                 report_date=date(2026, 1, day),
                                 depth_in=di, depth_out=do, hours_on_bottom=h))
        s.add(TimeLog24H(report_id=rid, time_from=dtime(0, 0),
                         time_to=dtime(12, 0), duration=h, is_npt=False))
        s.commit()
        s.close()

    svc_kpi = OperationsIntelligenceService(m)
    before = svc_kpi.analyze_wellbore(wb)["kpis"]
    assert before == {"reports": 0}  # nothing attributed yet

    applied = ScopeAttributionService(m).resolve(w)
    assert applied.applied == 4  # 2 reports × (wellbore + section)

    after_wb = svc_kpi.analyze_wellbore(wb)["kpis"]
    after_sec = svc_kpi.analyze_section(sec)["kpis"]
    # (100 + 300) / (5 + 5) = 40.0
    assert after_wb["weighted_rop"] == 40.0
    assert after_wb["weighted_rop_valid_pairs"] == 2
    assert after_wb["total_hours"] == 10.0
    assert after_sec["weighted_rop"] == 40.0


def test_unresolved_reports_keep_unknown_kpis():
    # A well with two sibling bores and no section evidence: nothing resolves,
    # so wellbore KPIs stay unknown (reports:0), never fabricated.
    m = _mgr()
    pid = _base(m)
    w = _well(m, pid, "B")
    wb1 = _wellbore(m, w, "B1")
    _wellbore(m, w, "B2", wtype="sidetrack", parent=wb1)
    s = m.create_session()
    dr = DailyReport(well_id=w, report_date=date(2026, 1, 1), depth_2400=100)
    s.add(dr)
    s.flush()
    s.add(DrillingParameters(well_id=w, report_id=dr.id,
                             report_date=date(2026, 1, 1),
                             depth_in=0, depth_out=100, hours_on_bottom=5))
    s.commit()
    s.close()
    ScopeAttributionService(m).resolve(w)
    kpis = OperationsIntelligenceService(m).analyze_wellbore(wb1)["kpis"]
    assert kpis == {"reports": 0}


# --- Q: malformed / empty database is safe ---------------------------------


def test_analyze_empty_database_is_safe():
    m = _mgr()
    _base(m)
    rep = ScopeAttributionService(m).analyze()
    assert rep.total_reports == 0
    assert rep.applied == 0
    cov = ScopeAttributionService(m).coverage()
    assert cov["wellbore_coverage_pct"] is None
