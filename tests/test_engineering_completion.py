"""Ground-truth coverage for completion-phase canonical contracts."""

import pytest
from datetime import date, datetime, time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.actual_vs_plan import ActualVsPlanEngine
from core.ai_tools import AIToolRegistry
from core.database import (
    Base,
    Company,
    CostRecord,
    DailyReport,
    DatabaseManager,
    PlannedActivity,
    Project,
    TimeLog24H,
    Well,
    WellPlan,
)
from core.engineering.bridge import CalculatorBridge
from core.engineering.core import TrajectoryEngine
from core.engineering.engines.bit_performance import BitPerformanceEngine
from core.engineering.engines.mse import MSEEngine
from core.engineering.engines.casing import CasingEngine
from core.engineering.engines.cement import CementEngine
from core.engineering.engines.fishing import FishingEngine
from core.engineering.engines.mud_volume import MudVolumeEngine
from core.engineering.engines.torque_drag import TorqueDragEngine
from core.engineering.engines.well_control import WellControlEngine


def test_actual_vs_plan_compares_only_present_metrics():
    result = ActualVsPlanEngine.compare_metrics(
        {
            "depth_m": 1000.0,
            "hours": 200.0,
            "cost": 100000.0,
        },
        {
            "depth_m": 800.0,
            "hours": 220.0,
            "cost": 125000.0,
        },
    )
    assert result.success, result.error
    assert result.values["depth_m"]["variance"] == pytest.approx(-200.0)
    assert result.values["depth_m"]["variance_pct"] == pytest.approx(-20.0)
    assert result.values["depth_m"]["status"] == "behind"
    assert result.values["cost"]["status"] == "ahead"
    assert result.scope == "COMPLETE"


def test_actual_vs_plan_does_not_invent_missing_actual_data():
    result = ActualVsPlanEngine.compare_metrics(
        {"depth_m": 1000.0, "hours": 200.0},
        {"depth_m": 800.0},
    )
    assert result.success, result.error
    assert "hours" not in result.values
    assert any("hours" in warning for warning in result.warnings)


def test_database_actual_vs_plan_uses_recorded_hours_and_costs_only():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = DatabaseManager()
    db.engine = engine
    db.Session = sessionmaker(bind=engine)
    session = db.create_session()
    company = Company(name="completion-test-company")
    session.add(company)
    session.flush()
    project = Project(company_id=company.id, name="completion-test-project")
    session.add(project)
    session.flush()
    well = Well(project_id=project.id, name="completion-test-well")
    session.add(well)
    session.flush()
    well_id = well.id
    plan = WellPlan(
        well_id=well_id,
        plan_name="test-plan",
        planned_total_days=10.0,
        planned_final_depth=1000.0,
    )
    session.add(plan)
    session.flush()
    session.add(PlannedActivity(
        well_id=well_id,
        plan_id=plan.id,
        activity_name="drill",
        planned_start=datetime.now(),
        planned_end=datetime.now(),
        planned_duration_hours=200.0,
        planned_depth_to=1000.0,
    ))
    report = DailyReport(
        well_id=well_id,
        report_date=date.today(),
        depth_2400=800.0,
        rop_meter=4.0,
    )
    session.add(report)
    session.flush()
    session.add(TimeLog24H(
        report_id=report.id,
        time_from=time(0),
        time_to=time(12),
        duration=12.0,
        is_npt=True,
    ))
    session.add(CostRecord(
        well_id=well_id,
        category="rig",
        planned_cost=100.0,
        actual_cost=120.0,
    ))
    session.commit()
    session.close()

    metrics = db.get_actual_vs_plan(well_id)
    assert metrics["hours"]["actual"] == pytest.approx(12.0)
    assert metrics["hours"]["actual"] != 24.0
    assert metrics["cost"]["actual"] == pytest.approx(120.0)
    assert metrics["npt_hours"] == pytest.approx(12.0)


def test_report_cost_paths_do_not_create_default_rig_rates():
    try:
        from core.report_engine import CostReportEngine, NPTReportEngine
    except ImportError as exc:
        if "libGL" in str(exc):
            pytest.skip("Qt report engine requires libGL")
        raise

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = DatabaseManager()
    db.engine = engine
    db.Session = sessionmaker(bind=engine)

    cost_data = CostReportEngine(db)._collect_data(999, None, None)
    assert cost_data["total_cost"] is None
    assert cost_data["total_daily_cost"] is None
    assert cost_data["cost_per_meter"] is None

    npt_data = NPTReportEngine(db)._collect_data(999)
    assert npt_data["npt_cost"] is None


def test_bridge_exposes_anti_collision_engineering_result():
    reference = [
        {"md": 0.0, "tvd": 0.0, "north": 0.0, "east": 0.0},
        {"md": 100.0, "tvd": 100.0, "north": 0.0, "east": 0.0},
    ]
    offset = [
        {"md": 0.0, "tvd": 0.0, "north": 3.0, "east": 4.0},
        {"md": 100.0, "tvd": 100.0, "north": 3.0, "east": 4.0},
    ]
    result = CalculatorBridge.anti_collision(reference, offset, coordinates_unit="m")
    assert result.success, result.error
    assert result.value == pytest.approx(5.0)
    assert result.metadata["iscwsa_compliant"] is False


def test_ai_anti_collision_preserves_failure_and_screening_metadata():
    registry = AIToolRegistry()
    invalid = registry.call_tool(
        "calculate_anti_collision",
        reference_trajectory=[{"md": 0, "tvd": 0, "north": 0}],
        offset_trajectory=[{"md": 0, "tvd": 0, "north": 0}],
    )
    assert not invalid["success"]
    assert "MISSING_INPUT" in invalid["error"]

    valid = registry.call_tool(
        "calculate_anti_collision",
        reference_trajectory=[
            {"md": 0, "tvd": 0, "north": 0, "east": 0},
            {"md": 100, "tvd": 100, "north": 0, "east": 0},
        ],
        offset_trajectory=[
            {"md": 0, "tvd": 0, "north": 3, "east": 4},
            {"md": 100, "tvd": 100, "north": 3, "east": 4},
        ],
        coordinates_unit="m",
    )
    assert valid["success"]
    assert valid["value"] == pytest.approx(5.0)
    assert valid["metadata"]["iscwsa_compliant"] is False
    assert valid["scope"] == "PARTIAL / SCREENING"


def test_torque_drag_contract_remains_screening_not_production():
    result = TorqueDragEngine.calculate(
        [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 1000.0, "inc": 30.0, "azi": 10.0}],
        [{"length": 1000.0, "weight": 19.5, "od": 5.0, "id": 4.276}],
        mud_density_ppg=10.0,
        friction_factor=0.2,
    )
    assert result.success, result.error
    assert result.scope == "PARTIAL"
    assert result.metadata["production_ready"] is False
    assert result.values["hookload_pickup"] >= result.values["hookload_slackoff"]


def test_trajectory_bit_and_mse_canonical_ground_truths():
    trajectory = TrajectoryEngine.calculate([
        {"md": 0.0, "inc": 0.0, "azi": 0.0},
        {"md": 100.0, "inc": 0.0, "azi": 0.0},
    ])
    assert trajectory[-1].tvd == pytest.approx(100.0)
    assert trajectory[-1].north == pytest.approx(0.0)

    mse = MSEEngine.calculate(10000.0, 100.0, 5000.0, 100.0, 8.5)
    assert mse.success, mse.error
    assert mse.values["mse_psi"] == pytest.approx(
        mse.values["axial_term_psi"] + mse.values["rotary_term_psi"], abs=0.2
    )

    bit = BitPerformanceEngine.from_run(
        bit_size_in=8.5,
        depth_in=5000.0,
        depth_out=6000.0,
        hours_on_bottom=20.0,
        bit_no="B1",
    )
    assert bit.success, bit.error
    assert bit.values["footage"] == pytest.approx(1000.0)
    assert bit.scope == "COMPLETE"


def test_casing_and_cement_results_keep_explicit_scope():
    casing = CasingEngine.evaluate(9.625, id_in=8.681, wall_in=0.472, yield_psi=80000.0)
    cement = CementEngine.job_volumes(12.25, 9.625, 1000.0, 0.0)
    assert casing.success and casing.scope == "PARTIAL"
    assert casing.metadata["api_tr_5c3_complete"] is False
    assert cement.success and cement.scope == "COMPLETE"
    assert any("laboratory" in warning.lower() for warning in cement.warnings)


def test_fishing_modulus_is_in_result_and_affects_backoff():
    low = FishingEngine.backoff_depth(12.0, 19.5, modulus_psi=30e6)
    high = FishingEngine.backoff_depth(12.0, 19.5, modulus_psi=60e6)
    assert low.success and high.success
    assert low.values["modulus_psi"] == 30e6
    assert high.value == pytest.approx(low.value * 2.0, abs=0.1)


def test_well_control_missing_critical_influx_input_is_explicit():
    result = WellControlEngine.kick_tolerance(
        mw_ppg=14.5,
        shoe_tvd_ft=6000.0,
        current_tvd_ft=10000.0,
        frac_mw_ppg=16.0,
    )
    assert not result.success
    assert "MISSING_INPUT" in result.error
    assert "influx" in result.error.lower()


def test_mud_volume_requires_additive_density_for_weight_up():
    result = MudVolumeEngine.weight_up(80.0, 90.0, 500.0, None)
    assert not result.success
    assert "MISSING_INPUT" in result.error
