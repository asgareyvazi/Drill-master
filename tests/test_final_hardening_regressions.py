"""Regression tests for the final no-fabrication and boundary hardening pass."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base,
    Company,
    DailyReport,
    DatabaseManager,
    Project,
    Section,
    SurveyPoint,
    Well,
)
from core.engineering.engines.bit_performance import BitPerformanceEngine
from core.engineering.engines.casing import CasingEngine
from core.engineering.engines.trajectory import TrajectoryCalculator
from core.engineering.result import MissingInputError
from core.import_quality import TimeLogValidator


def test_trajectory_rejects_missing_directional_inputs():
    with pytest.raises(MissingInputError, match=r"MISSING_INPUT: survey\[0\]\.inc"):
        TrajectoryCalculator.calculate([{"md": 0.0, "azi": 0.0}])
    with pytest.raises(MissingInputError, match=r"MISSING_INPUT: survey\[0\]\.azi"):
        TrajectoryCalculator.calculate([{"md": 0.0, "inc": 0.0}])


def test_atomic_survey_import_preserves_null_angles_for_review():
    manager = DatabaseManager()
    manager.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(bind=manager.engine, autoflush=False, autocommit=False)

    session = manager.create_session()
    company = Company(name="Hardening Co", code="HC")
    session.add(company)
    session.flush()
    project = Project(name="Hardening Project", code="HP", company_id=company.id)
    session.add(project)
    session.flush()
    well = Well(name="Hardening Well", code="HW", project_id=project.id)
    session.add(well)
    session.flush()
    section = Section(name="17-1/2 in", well_id=well.id)
    session.add(section)
    session.flush()
    report = DailyReport(
        well_id=well.id,
        section_id=section.id,
        report_date=date(2026, 1, 1),
        report_number=1,
    )
    session.add(report)
    session.commit()
    well_id, report_id = well.id, report.id
    session.close()

    result = manager.save_imported_multi_tab_data_atomic(
        well_id,
        report_id,
        {"surveys": [{"md": 0.0, "inc": 0.0}]},
    )
    assert result["failed"] == 0
    assert result["survey_review"] == 1

    session = manager.create_session()
    try:
        row = session.query(SurveyPoint).filter_by(report_id=report_id).one()
        assert row.md == 0.0
        assert row.inc == 0.0
        assert row.azi is None
    finally:
        session.close()


def test_time_validator_rejects_bad_clock_tokens_and_duration_without_crashing():
    assert TimeLogValidator._to_minutes("24:01") is None
    assert TimeLogValidator._to_minutes("12:61") is None
    assert TimeLogValidator._to_minutes("12:00 trailing") is None

    report = TimeLogValidator.validate_logs(
        [{
            "time_from": "00:00",
            "time_to": "01:00",
            "duration": "not-a-number",
        }]
    )
    assert any("Duration must be numeric" in issue.message for issue in report.errors)


def test_time_validator_detects_overlap_across_midnight():
    report = TimeLogValidator.validate_logs(
        [
            {"time_from": "22:00", "time_to": "02:00", "duration": 4.0},
            {"time_from": "01:00", "time_to": "03:00", "duration": 2.0},
        ]
    )
    assert any("overlap" in issue.message.lower() for issue in report.errors)


def test_numeric_boundary_inputs_return_engineering_failures():
    assert not CasingEngine.burst(9.625, 0.472, 80000, design_factor=0).success
    assert not BitPerformanceEngine.from_daily_params(
        {
            "depth_in": 1000,
            "depth_out": 1100,
            "hours_on_bottom": 2,
            "torque": "unknown",
        }
    ).success


def test_hydraulics_rejects_nonphysical_public_inputs():
    from core.hydraulics_engine import AdvancedHydraulicsEngine

    with pytest.raises(ValueError, match="gpm"):
        AdvancedHydraulicsEngine.calc_bit_pressure_drop(-1, 12, 0.5)
    with pytest.raises(ValueError, match="efficiency"):
        AdvancedHydraulicsEngine.calc_pump_output(7, 12, 0)


def test_imported_md_zero_is_not_skipped_by_profile_extraction():
    from core.profile_import_engine import ProfileImportEngine

    engine = ProfileImportEngine(None)
    engine.cell_cache = {
        "Directional Survey": {
            2: {1: 0.0, 3: 0.0, 4: 0.0},
            3: {1: 100.0, 3: 1.0},
        }
    }
    result = engine._extract_multi_tab_sheets(["Directional Survey"])
    assert result["surveys"] == [{"md": 0.0, "inc": 0.0, "azi": 0.0}]
    assert result["survey_review"] == [{
        "row": 3,
        "md": 100.0,
        "missing": ["azi"],
        "decision": "REVIEW",
    }]


def test_new_database_reports_require_source_dates():
    manager = DatabaseManager()
    manager.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(bind=manager.engine, autoflush=False, autocommit=False)

    assert manager.save_bit_report(1, {"bit_records_json": []}) is None
    assert manager.save_seven_days_lookahead({"well_id": 1, "activity": "Drill"}) is None
