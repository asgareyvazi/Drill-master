"""M26 §4/§5/§17/§23 — report-scoped ownership non-contradiction invariant.

The ``before_flush`` guard ``_check_report_scoped_well_ownership`` is a pure
non-contradiction check: a record carrying a ``report_id`` FK onto
``daily_reports`` may not name a report that belongs to a DIFFERENT well than
the record's own ``well_id``. A NULL ``report_id`` (a legitimate well-level
record) always passes — the guard never fabricates ownership.

The M25 tree wired this for only 3 models (BHA/Bit/Downhole) while 27
identically-shaped peers (DrillingParameters, MudReport, SafetyReport,
FormationReport, WellboreSchematic, TripSheetEntry, …) silently accepted a
cross-well contradiction. The guarded set is now derived from the schema, so
every such model is protected on every save path (ORM, helper, import).

These tests use a REAL in-memory DatabaseManager and go through flush/commit —
they are not object-in-memory smoke checks. Committed state is asserted after a
rejection to prove the transaction rolled back (§25).
"""
from datetime import date, datetime, time as dtime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base, DatabaseManager, Company, Project, Well, DailyReport,
    DrillingParameters, MudReport, SafetyReport, FormationReport,
    WellboreSchematic, TripSheetEntry, ROPAnalysis, TimeDepthData,
    _report_scoped_well_models,
)
from core.import_diagnostics import OwnershipIntegrityError


@pytest.fixture()
def two_wells():
    m = DatabaseManager()
    m.engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    s = m.create_session()
    c = Company(name="C", code="C"); s.add(c); s.flush()
    p = Project(name="P", code="P", company_id=c.id); s.add(p); s.flush()
    wa = Well(name="A", code="A", project_id=p.id)
    wb = Well(name="B", code="B", project_id=p.id)
    s.add_all([wa, wb]); s.flush()
    ra = DailyReport(well_id=wa.id, report_number=1, report_date=date(2026, 1, 1))
    rb = DailyReport(well_id=wb.id, report_number=1, report_date=date(2026, 1, 1))
    s.add_all([ra, rb]); s.flush()
    ids = {"wa": wa.id, "wb": wb.id, "ra": ra.id, "rb": rb.id}
    s.commit(); s.close()
    return m, ids


# Representative peers that were UNPROTECTED before M26 (one per data domain).
_PEERS = [
    (DrillingParameters, {"report_date": date(2026, 1, 1)}),
    (MudReport, {"report_date": date(2026, 1, 1)}),
    (SafetyReport, {"report_date": date(2026, 1, 1)}),
    (FormationReport, {}),
    (WellboreSchematic, {"report_date": date(2026, 1, 1)}),
    (TripSheetEntry, {"time": dtime(0, 0), "activity": "trip"}),
    (ROPAnalysis, {"analysis_date": date(2026, 1, 1),
                   "start_depth": 0.0, "end_depth": 100.0}),
    (TimeDepthData, {"timestamp": datetime(2026, 1, 1, 0, 0), "depth": 100.0}),
]


def test_the_full_shape_is_guarded():
    guarded = _report_scoped_well_models()
    # The three historically-guarded models plus their peers are all present.
    for name in ("BHAReport", "BitReport", "DownholeEquipment",
                 "DrillingParameters", "MudReport", "SafetyReport",
                 "FormationReport", "WellboreSchematic", "TripSheetEntry"):
        assert name in guarded, f"{name} must be guarded"
    assert len(guarded) >= 30


@pytest.mark.parametrize("model,extra", _PEERS,
                         ids=[m.__name__ for m, _ in _PEERS])
def test_cross_well_report_reference_is_rejected(two_wells, model, extra):
    m, ids = two_wells
    s = m.create_session()
    try:
        # record in well A, but report_id names well B's report -> contradiction
        s.add(model(well_id=ids["wa"], report_id=ids["rb"], **extra))
        with pytest.raises(OwnershipIntegrityError):
            s.commit()
    finally:
        s.rollback()
        s.close()
    # Nothing was persisted — the transaction rolled back cleanly.
    s = m.create_session()
    try:
        assert s.query(model).count() == 0
    finally:
        s.close()


@pytest.mark.parametrize("model,extra", _PEERS,
                         ids=[m.__name__ for m, _ in _PEERS])
def test_same_well_report_reference_is_accepted(two_wells, model, extra):
    m, ids = two_wells
    s = m.create_session()
    try:
        s.add(model(well_id=ids["wa"], report_id=ids["ra"], **extra))
        s.commit()
    finally:
        s.close()
    s = m.create_session()
    try:
        assert s.query(model).count() == 1
    finally:
        s.close()


@pytest.mark.parametrize("model,extra", _PEERS,
                         ids=[m.__name__ for m, _ in _PEERS])
def test_null_report_id_is_allowed_well_level(two_wells, model, extra):
    """A NULL report_id is a legitimate well-level record; the guard must not
    fabricate ownership by rejecting it."""
    m, ids = two_wells
    s = m.create_session()
    try:
        s.add(model(well_id=ids["wa"], report_id=None, **extra))
        s.commit()
    finally:
        s.close()
    s = m.create_session()
    try:
        assert s.query(model).count() == 1
    finally:
        s.close()
