"""Regression coverage for Operations Intelligence model/schema alignment."""

from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
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
    Well,
)
from core.operations_intelligence import OperationsIntelligenceService


def _manager_with_report():
    manager = DatabaseManager()
    manager.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(bind=manager.engine, autoflush=False, autocommit=False)

    session = manager.create_session()
    company = Company(name="OI Regression Company", code="OI-CO")
    session.add(company)
    session.flush()
    project = Project(name="OI Regression Project", code="OI-PR", company_id=company.id)
    session.add(project)
    session.flush()
    well = Well(name="OI Regression Well", code="OI-WELL", project_id=project.id)
    session.add(well)
    session.flush()
    section = Section(name="12-1/4 in", well_id=well.id)
    session.add(section)
    session.flush()
    report = DailyReport(
        well_id=well.id,
        section_id=section.id,
        report_number=1,
        report_date=date(2025, 10, 27),
        depth_2400=1000.0,
    )
    session.add(report)
    session.flush()
    session.add(
        DrillingParameters(
            well_id=well.id,
            report_id=report.id,
            report_date=report.report_date,
            wob_min=10.0,
            wob_max=20.0,
            torque_min=100.0,
            torque_max=140.0,
            rpm_min=80.0,
            rpm_max=100.0,
            avg_rop=12.5,
        )
    )
    session.commit()
    well_id = well.id
    session.close()
    return manager, well_id


def test_operations_intelligence_uses_current_drilling_parameters_schema():
    manager, well_id = _manager_with_report()
    result = OperationsIntelligenceService(manager).analyze_well(well_id)

    assert "error" not in result["kpis"]
    assert result["kpis"]["wob_trend"] == [15.0]
    assert result["kpis"]["torque_trend"] == [120.0]
    assert result["kpis"]["rpm_trend"] == [90.0]


from datetime import time as _time

from core.database import DailyReport as _DailyReport, TimeLog24H, Well as _Well


def _manager_empty_well():
    """A well with one daily report but no time logs and no drilling params.

    ROP, NPT% and productive time are therefore genuinely unknown.
    """
    manager, existing_well_id = _manager_with_report()
    session = manager.create_session()
    try:
        project_id = session.get(_Well, existing_well_id).project_id
        well = _Well(name="Unknown Metrics Well", code="OI-EMPTY", project_id=project_id)
        session.add(well)
        session.flush()
        session.add(
            _DailyReport(
                well_id=well.id,
                report_number=1,
                report_date=date(2025, 10, 28),
                depth_2400=500.0,
            )
        )
        session.commit()
        well_id = well.id
    finally:
        session.close()
    return manager, well_id


def test_unknown_rop_and_npt_are_none_not_fabricated_zero():
    """KPI-01 regression: absent source data yields None (unknown), not 0.0.

    Reporting 0.0 m/hr ROP or 0% NPT for a well with no time logs / no
    drilling parameters asserts a false fact. Unknown must stay unknown, the
    same no-fabrication contract already applied to cost_per_meter.
    """
    manager, well_id = _manager_empty_well()
    kpis = OperationsIntelligenceService(manager).analyze_well(well_id)["kpis"]

    assert kpis["average_rop"] is None
    assert kpis["npt_percent"] is None
    assert kpis["productive_hours"] is None
    # Unknown NPT must not fabricate an NPT insight, and analysis must not crash.
    assert "error" not in kpis
    # cost stays None too (no cost records) — unchanged behaviour.
    assert kpis["cost_per_meter"] is None


def test_known_rop_and_npt_are_computed():
    """With time logs and ROP present, real values are still reported."""
    manager, existing_well_id = _manager_with_report()
    session = manager.create_session()
    try:
        project_id = session.get(_Well, existing_well_id).project_id
        well = _Well(name="Known Metrics Well", code="OI-KNOWN", project_id=project_id)
        session.add(well)
        session.flush()
        report = _DailyReport(
            well_id=well.id, report_number=1,
            report_date=date(2025, 10, 29), depth_2400=800.0,
        )
        session.add(report)
        session.flush()
        session.add(TimeLog24H(
            report_id=report.id, time_from=_time(0), time_to=_time(18),
            duration=18.0, is_npt=False,
        ))
        session.add(TimeLog24H(
            report_id=report.id, time_from=_time(18), time_to=_time(23, 59),
            duration=6.0, is_npt=True,
        ))
        session.add(DrillingParameters(
            well_id=well.id, report_id=report.id,
            report_date=report.report_date, avg_rop=15.0,
        ))
        session.commit()
        well_id = well.id
    finally:
        session.close()

    kpis = OperationsIntelligenceService(manager).analyze_well(well_id)["kpis"]
    assert kpis["average_rop"] == 15.0
    assert kpis["npt_percent"] == 25.0  # 6 of 24 hours
    assert kpis["productive_hours"] == 18.0
