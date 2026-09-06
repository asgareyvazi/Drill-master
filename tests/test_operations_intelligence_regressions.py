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
