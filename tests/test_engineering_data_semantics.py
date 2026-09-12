"""Locks the engineering source-data semantics established by the
2026-09-12 Engineering Data Semantics forensic audit.

These are *semantic* regression tests, not tests for a new feature. No
weighted-ROP KPI exists in production; these tests assert the properties any
future footage/hours calculation must be able to rely on:

* ``DrillingParameters`` is one upserted row per DDR (``report_id``), so
  ``depth_in``/``depth_out``/``hours_on_bottom`` are a single bit-run summary,
  not multiple drilling intervals per report.
* ``depth_out < depth_in`` (negative footage) is rejected at import validation.
* Missing numeric source fields normalise to ``None`` (NULL), never a
  fabricated 0.
* A correct footage-weighted ROP must PAIR footage and hours per row (both
  non-NULL); a naive ``SUM(depth_out-depth_in)/SUM(hours_on_bottom)`` is unsafe
  because SQL ``SUM`` drops NULL footage while still counting that row's hours.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base,
    Company,
    DailyReport,
    DatabaseManager,
    DrillingParameters,
    Project,
    Well,
)
from core.import_quality import ImportValidator
from core.value_normalizer import ValueNormalizer


def _manager():
    manager = DatabaseManager()
    manager.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(bind=manager.engine, autoflush=False, autocommit=False)
    session = manager.create_session()
    company = Company(name="Semantics Co", code="SEM-CO")
    session.add(company)
    session.flush()
    project = Project(name="Semantics Project", code="SEM-PR", company_id=company.id)
    session.add(project)
    session.flush()
    well = Well(name="Semantics Well", code="SEM-WELL", project_id=project.id)
    session.add(well)
    session.flush()
    well_id = well.id
    session.commit()
    session.close()
    return manager, well_id


def _report(manager, well_id, report_date, depth):
    session = manager.create_session()
    try:
        report = DailyReport(well_id=well_id, report_date=report_date, depth_2400=depth)
        session.add(report)
        session.flush()
        rid = report.id
        session.commit()
        return rid
    finally:
        session.close()


def test_drilling_parameters_are_one_upserted_row_per_report():
    """save_drilling_parameters upserts by report_id: a second save for the same
    report updates the existing row instead of creating a duplicate. Footage
    aggregation can therefore treat depth_in/out as one bit-run summary per DDR.
    """
    manager, well_id = _manager()
    rid = _report(manager, well_id, date(2026, 1, 1), 1100.0)

    manager.save_drilling_parameters(
        {"well_id": well_id, "report_id": rid, "report_date": date(2026, 1, 1),
         "depth_in": 1000.0, "depth_out": 1100.0, "hours_on_bottom": 5.0}
    )
    manager.save_drilling_parameters(
        {"well_id": well_id, "report_id": rid, "report_date": date(2026, 1, 1),
         "depth_in": 1000.0, "depth_out": 1150.0, "hours_on_bottom": 6.0}
    )

    session = manager.create_session()
    try:
        rows = session.query(DrillingParameters).filter_by(report_id=rid).all()
        assert len(rows) == 1                       # upsert, not duplicate insert
        assert rows[0].depth_out == 1150.0          # updated in place
        assert rows[0].hours_on_bottom == 6.0
    finally:
        session.close()


def test_import_validation_rejects_negative_footage():
    """depth_out < depth_in is flagged as an error at import validation
    (Case E), so negative footage never reaches persistence as a silent zero."""
    report = ImportValidator.validate_rows(
        [{"depth_in": 1100, "depth_out": 1000}],
        record_type="drilling_params",
        sheet="DP",
    )
    assert report.failed >= 1
    messages = " ".join(str(i) for i in report.issues)
    assert "Depth out must be >= depth in" in messages


def test_missing_depth_and_hours_normalise_to_none_not_zero():
    """Absent numeric source values become None (NULL), never a fabricated 0 —
    the no-fabrication contract at the numeric boundary."""
    assert ValueNormalizer.to_float(None) is None
    assert ValueNormalizer.to_float("") is None
    # A genuine recorded zero is preserved as 0.0.
    assert ValueNormalizer.to_float("0") == 0.0
    assert ValueNormalizer.to_float("1000") == 1000.0


def test_weighted_rop_must_pair_footage_and_hours_per_row():
    """A row with hours but NULL depth_out has UNKNOWN footage. A correct
    weighted ROP pairs footage and hours per row; the naive
    SUM(footage)/SUM(hours) is wrong because SQL SUM skips the NULL footage while
    still counting that row's hours in the denominator. This test documents the
    hazard so any future weighted-ROP feature is implemented safely.
    """
    manager, well_id = _manager()
    r1 = _report(manager, well_id, date(2026, 1, 1), 1100.0)
    r2 = _report(manager, well_id, date(2026, 1, 2), 1200.0)
    manager.save_drilling_parameters(
        {"well_id": well_id, "report_id": r1, "report_date": date(2026, 1, 1),
         "depth_in": 1000.0, "depth_out": 1100.0, "hours_on_bottom": 5.0}
    )
    # hours known, footage unknown (depth_out missing)
    manager.save_drilling_parameters(
        {"well_id": well_id, "report_id": r2, "report_date": date(2026, 1, 2),
         "depth_in": 1100.0, "depth_out": None, "hours_on_bottom": 6.0}
    )

    session = manager.create_session()
    try:
        naive_footage, naive_hours = session.query(
            func.sum(DrillingParameters.depth_out - DrillingParameters.depth_in),
            func.sum(DrillingParameters.hours_on_bottom),
        ).filter(DrillingParameters.well_id == well_id).one()
        # The naive denominator wrongly includes the 6 h whose footage is NULL.
        assert naive_footage == 100.0
        assert naive_hours == 11.0
        assert abs(naive_footage / naive_hours - 9.0909) < 0.01   # WRONG value

        rows = session.query(DrillingParameters).filter_by(well_id=well_id).all()
        paired = [
            r for r in rows
            if r.depth_in is not None and r.depth_out is not None
            and r.hours_on_bottom is not None
        ]
        paired_footage = sum(r.depth_out - r.depth_in for r in paired)
        paired_hours = sum(r.hours_on_bottom for r in paired)
        assert paired_footage == 100.0
        assert paired_hours == 5.0
        assert paired_footage / paired_hours == 20.0             # CORRECT value
    finally:
        session.close()
