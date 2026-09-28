"""Mission 29 adversarial contracts, not successful-process-only assertions."""

from datetime import date, datetime, time
from types import SimpleNamespace

import pytest
from sqlalchemy import Date, DateTime, Integer, Float, Boolean, JSON, Time, text

from core.database import (
    Base,
    Well,
    Section,
    DailyReport,
    TimeLog24H,
    SafetyReport,
    WellPlan,
    PlannedActivity,
    OwnershipIntegrityError,
)
from core.actual_vs_plan import compare, ActualVsPlanEngine, compare_plan_activities
from test_cost_truth_boundary import memory_manager


@pytest.fixture
def env():
    db, well = memory_manager()
    with db.session_scope() as s:
        owner = s.get(Well, well)
        other = Well(name="Other", code="Other", project_id=owner.project_id)
        s.add(other)
        s.flush()
        first = Section(well_id=well, name="First")
        second = Section(well_id=well, name="Second")
        foreign = Section(well_id=other.id, name="Foreign")
        s.add_all([first, second, foreign])
        s.flush()
        report = DailyReport(well_id=well, section_id=first.id, report_date=date(2026, 1, 1))
        plan = WellPlan(well_id=well, plan_name="Plan")
        s.add_all([report, plan])
        s.flush()
        ids = dict(
            well=well,
            other=other.id,
            section=first.id,
            second=second.id,
            foreign=foreign.id,
            report=report.id,
            plan=plan.id,
        )
    yield db, ids
    db.close()


@pytest.mark.parametrize(
    "p,a",
    [
        (None, None),
        (None, 0),
        (0, None),
        (0, 0),
        (None, 100),
        (100, None),
        (0, 100),
        (100, 0),
        (100, 100),
        (100, 80),
        (80, 100),
    ],
)
def test_required_eleven_pair_plan_matrix(p, a):
    scalar = compare("Depth", p, a)
    canonical = ActualVsPlanEngine.compare_metrics({"depth_m": p}, {"depth_m": a})
    metric = canonical.values.get("depth_m") or canonical.metadata["unavailable_metrics"]["depth_m"]
    activity = compare_plan_activities([dict(planned_depth_to=p, planned_duration_hours=p)], a, a)[0]
    assert (scalar.planned, scalar.actual) == (p, a)
    assert metric["variance"] == activity.variance == scalar.variance
    assert metric["status"] == activity.status == scalar.status
    if p is None or a is None:
        assert scalar.variance is None and scalar.status == "unavailable"
    elif p == 0 and a != 0:
        assert scalar.variance_pct is None and scalar.status == "unavailable"
    else:
        expected = (a - p) / abs(p) * 100 if p else 0
        assert scalar.variance_pct == pytest.approx(expected)
        assert scalar.status == ("on-track" if abs(expected) <= 10 else "ahead" if expected > 0 else "behind")


SCOPED = sorted(
    [
        m.class_
        for m in Base.registry.mappers
        if hasattr(m.class_, "well_id") and hasattr(m.class_, "section_id") and m.class_ is not DailyReport
    ],
    key=lambda model: model.__name__,
)


def required_values(model):
    values = {}
    for col in model.__table__.columns:
        if col.primary_key or col.nullable or col.default is not None or col.foreign_keys:
            continue
        value = "record"
        if isinstance(col.type, DateTime):
            value = datetime(2026, 1, 1)
        elif isinstance(col.type, Date):
            value = date(2026, 1, 1)
        elif isinstance(col.type, Time):
            value = time(0)
        elif isinstance(col.type, Boolean):
            value = False
        elif isinstance(col.type, (Integer, Float)):
            value = 0
        elif isinstance(col.type, JSON):
            value = []
        values[col.name] = value
    return values


@pytest.mark.parametrize("model", SCOPED, ids=lambda model: model.__name__)
@pytest.mark.parametrize("relationship_first", [False, True])
def test_all_section_owned_models_reject_cross_well_relationships(env, model, relationship_first):
    db, ids = env
    with pytest.raises(OwnershipIntegrityError):
        with db.session_scope() as s:
            row = model(**required_values(model))
            if relationship_first:
                if "section" in model.__mapper__.relationships:
                    row.section = s.get(Section, ids["foreign"])
                else:
                    row.section_id = ids["foreign"]
                row.well_id = ids["well"]
            else:
                row.well_id = ids["well"]
                if "section" in model.__mapper__.relationships:
                    row.section = s.get(Section, ids["foreign"])
                else:
                    row.section_id = ids["foreign"]
            s.add(row)
            s.flush()


def test_report_child_section_disagreement_and_parent_edits(env):
    db, ids = env
    with pytest.raises(OwnershipIntegrityError):
        with db.session_scope() as s:
            s.add(
                SafetyReport(
                    well_id=ids["well"], report_id=ids["report"], section_id=ids["second"], report_date=date(2026, 1, 1)
                )
            )
    with db.session_scope() as s:
        s.add(
            SafetyReport(
                well_id=ids["well"], section_id=ids["section"], report_id=ids["report"], report_date=date(2026, 1, 1)
            )
        )
    with pytest.raises(OwnershipIntegrityError):
        with db.session_scope() as s:
            s.get(DailyReport, ids["report"]).section = s.get(Section, ids["second"])


def test_activity_plan_ownership_and_parent_move(env):
    db, ids = env
    with db.session_scope() as s:
        s.add(
            PlannedActivity(
                well_id=ids["well"],
                plan_id=ids["plan"],
                activity_name="A",
                planned_start=datetime(2026, 1, 1),
                planned_end=datetime(2026, 1, 2),
            )
        )
    with pytest.raises(OwnershipIntegrityError):
        with db.session_scope() as s:
            s.get(WellPlan, ids["plan"]).well = s.get(Well, ids["other"])


def test_startup_validator_rejects_stored_section_contradiction_without_repair(env):
    db, ids = env
    with db.engine.begin() as c:
        c.execute(
            text("INSERT INTO safety_reports (well_id,section_id,report_date) VALUES (:well,:section,:date)"),
            dict(well=ids["well"], section=ids["foreign"], date="2026-01-01"),
        )
    raw = db.engine.raw_connection()
    try:
        with pytest.raises(OwnershipIntegrityError):
            db._verify_stored_ownership(raw)
        assert raw.execute("SELECT section_id FROM safety_reports").fetchone()[0] == ids["foreign"]
    finally:
        raw.close()


def test_npt_report_scope_and_unknown_duration(env):
    from tabs.w10_Planning_Widget import NPTReportTab

    from inspect import getclosurevars

    NPTReportTab = getclosurevars(NPTReportTab.__init__).nonlocals["widget_class"]
    db, ids = env
    with db.session_scope() as s:
        other = DailyReport(well_id=ids["well"], section_id=ids["second"], report_date=date(2026, 1, 2))
        s.add(other)
        s.flush()
        s.add_all(
            [
                TimeLog24H(report_id=ids["report"], time_from=time(0), time_to=time(1), duration=1, is_npt=True),
                TimeLog24H(report_id=other.id, time_from=time(0), time_to=time(2), duration=2, is_npt=True),
            ]
        )
    stub = SimpleNamespace(current_well_id=ids["well"])
    with db.session_scope() as s:
        result = NPTReportTab.get_npt_data(stub, s, report_id=ids["report"])
        assert result["total_npt"] == result["total_hours"] == 1
        assert len(result["entries"]) == 1
        assert NPTReportTab.get_npt_data(stub, s, section_id=ids["second"])["total_hours"] == 2
        s.add(TimeLog24H(report_id=ids["report"], time_from=time(1), time_to=time(2), duration=None, is_npt=True))
    with db.session_scope() as s:
        result = NPTReportTab.get_npt_data(stub, s, report_id=ids["report"])
        assert result["total_npt"] is result["total_hours"] is result["npt_percentage"] is None
        assert result["entries"][1]["hours"] is None


def test_milestone_unknown_and_zero_are_distinct_in_both_consumers(env):
    from test_w12_milestones_m25 import _milestone_stub
    from tabs.w10_Planning_Widget import MilestonesTab

    db, ids = env
    st = _milestone_stub(db, ids["well"])
    st.load_milestones_data()
    assert all(v is None for v in st.captured[1] + st.captured[2])
    captured = []
    stub = SimpleNamespace(
        current_well_id=ids["well"],
        db=db,
        _draw_chart=lambda *v: captured.append(v),
        _fill_table=lambda *v: None,
        _show_no_data=lambda: pytest.fail("explicit section is not no-data"),
    )
    MilestonesTab.load_data(stub)
    assert all(v is None for v in captured[-1][1] + captured[-1][2])
    with db.session_scope() as s:
        s.get(Section, ids["section"]).planned_days = 0
        s.add(TimeLog24H(report_id=ids["report"], time_from=time(0), time_to=time(1), duration=0, is_npt=False))
    MilestonesTab.load_data(stub)
    index = captured[-1][0].index("First")
    assert captured[-1][1][index] == captured[-1][2][index] == 0


def test_permission_is_entity_specific_and_main_window_fails_closed(monkeypatch):
    from core.permissions import permissions
    from core.hierarchy_operations import check_delete_permission
    from main_window import MainWindow

    monkeypatch.setattr(permissions, "_user", dict(role="supervisor"))
    assert check_delete_permission(entity_type="report")
    assert not check_delete_permission(entity_type="well")
    assert not check_delete_permission(entity_type="company")

    def broken(*args):
        raise RuntimeError("permission failure")

    monkeypatch.setattr(permissions, "has_permission", broken)
    assert MainWindow._check_delete_permission(SimpleNamespace(status_manager=None), "well") is False


def test_no_ddr_does_not_hide_cost_or_safety_evidence(env):
    from core.operations_intelligence import OperationsIntelligenceService

    db, ids = env
    assert db.delete_daily_report(ids["report"])
    db.save_afe_worksheet(ids["well"], [dict(category="Rig", planned_cost=100, actual_cost=80, currency="EUR")])
    with db.session_scope() as s:
        s.add(
            SafetyReport(
                well_id=ids["well"], report_date=date(2026, 1, 1), days_without_lti=0, lti_count=1, near_miss_count=0
            )
        )
    result = OperationsIntelligenceService(db).analyze_well(ids["well"])
    assert result["kpis"]["reports"] == 0 and result["kpis"]["total_cost"] == 80
    assert result["kpis"]["safety_kpi"]["total_lti"] == 1
    assert result["kpis"]["data_quality_score"] is None


def test_snapshot_restore_missing_target_cannot_succeed(env):
    db, ids = env
    snapshot = db.create_import_snapshot(ids["report"])
    assert snapshot["report"]["id"] == ids["report"]
    assert db.delete_daily_report(ids["report"])
    assert db.restore_import_snapshot(snapshot) is False


def test_afe_legacy_summary_uses_same_currency_contract():
    from core.cost_semantics import summarize_afe

    assert (
        summarize_afe([dict(actual_cost=100, currency="USD"), dict(actual_cost=100, currency="EUR")])["total_actual"]
        is None
    )


def test_copy_previous_uses_target_date_zero_closing_and_no_safety_assessment(env, monkeypatch):
    from core.database import FuelWaterInventory
    from core.permissions import permissions
    from dialogs.hierarchy_dialogs import NewDailyReportDialog

    db, ids = env
    monkeypatch.setattr(permissions, "_user", {"role": "engineer"})
    with db.session_scope() as s:
        target = DailyReport(well_id=ids["well"], section_id=ids["section"], report_date=date(2026, 2, 1))
        s.add(target)
        s.flush()
        target_id = target.id
        s.add(
            FuelWaterInventory(
                well_id=ids["well"],
                report_id=ids["report"],
                section_id=ids["section"],
                report_date=date(2026, 1, 1),
                fuel_stock=100,
                fuel_remaining=0,
                water_stock=100,
                water_remaining=None,
            )
        )
        s.add(
            SafetyReport(
                well_id=ids["well"], report_id=ids["report"], report_date=date(2026, 1, 1), days_without_lti=100
            )
        )
    with db.session_scope() as s:
        assert NewDailyReportDialog._copy_all_report_data(SimpleNamespace(), s, ids["report"], target_id)
    with db.session_scope() as s:
        row = s.query(FuelWaterInventory).filter_by(report_id=target_id).one()
        assert row.report_date == date(2026, 2, 1)
        assert row.fuel_stock == row.fuel_remaining == 0
        assert row.water_stock is row.water_remaining is row.days_remaining_fuel is None
        assert s.query(SafetyReport).filter_by(report_id=target_id).count() == 0
        s.get(DailyReport, target_id).status = "Final"
    with db.session_scope() as s:
        with pytest.raises(ValueError, match="not editable"):
            NewDailyReportDialog._copy_all_report_data(SimpleNamespace(), s, ids["report"], target_id)


def test_snapshot_nested_json_detached_in_both_directions(env):
    from copy import deepcopy

    db, ids = env
    with db.session_scope() as s:
        s.get(DailyReport, ids["report"]).header_snapshot = {"identity": {"name": "captured"}}
        s.add(
            SafetyReport(
                well_id=ids["well"],
                report_id=ids["report"],
                report_date=date(2026, 1, 1),
                equipment_checks={"check": {"assessment": None}},
            )
        )
    snapshot = db.create_import_snapshot(ids["report"])
    original = deepcopy(snapshot)
    with db.session_scope() as s:
        s.get(DailyReport, ids["report"]).header_snapshot = {"identity": {"name": "changed live"}}
    assert snapshot["report"]["header_snapshot"]["identity"]["name"] == "captured"
    assert db.restore_import_snapshot(snapshot)
    assert snapshot == original
    snapshot["report"]["header_snapshot"]["identity"]["name"] = "changed caller"
    safety = next(values for model, values in snapshot["children"] if model is SafetyReport)
    safety["equipment_checks"]["check"]["assessment"] = 0
    with db.session_scope() as s:
        assert s.get(DailyReport, ids["report"]).header_snapshot["identity"]["name"] == "captured"
        assert s.query(SafetyReport).one().equipment_checks["check"]["assessment"] is None


def test_template_selection_zero_one_many_is_explicit(tmp_path, monkeypatch):
    import json
    import core.ddr_import_service as service

    # The production resolver uses the package root, not process CWD.
    monkeypatch.setattr(service, "__file__", str(tmp_path / "core" / "ddr_import_service.py"))
    templates = tmp_path / "templates"
    templates.mkdir()
    assert service.DDRImportService._auto_match_template(["DDR Data"]) is None
    template = {"sheet_1_DDR_Data": {"source": "one"}}
    (templates / "first.json").write_text(json.dumps(template))
    assert service.DDRImportService._auto_match_template(["DDR Data"]) == template
    (templates / "second.json").write_text(json.dumps(template))
    with pytest.raises(ValueError, match="Ambiguous"):
        service.DDRImportService._auto_match_template(["DDR Data"])


def test_learning_store_uses_user_data_not_application_directory(tmp_path, monkeypatch):
    from dialogs.smart_template_dialog import LearningManager
    from core.runtime_config import user_templates_dir

    monkeypatch.setenv("DRILLMASTER_DATA_DIR", str(tmp_path))
    manager = LearningManager()
    assert manager._get_path() == str(user_templates_dir() / "_learning_data.json")
    assert user_templates_dir() == tmp_path / "templates"


@pytest.mark.parametrize(
    "planned,actual",
    [
        (None, None),
        (None, 0),
        (0, None),
        (0, 0),
        (None, 100),
        (100, None),
        (0, 100),
        (100, 0),
        (100, 100),
        (100, 80),
        (80, 100),
    ],
)
def test_persisted_plan_matrix_matches_scalar_contract(env, planned, actual):
    db, ids = env
    with db.session_scope() as s:
        s.get(WellPlan, ids["plan"]).planned_final_depth = planned
        s.get(DailyReport, ids["report"]).depth_2400 = actual
    result = db.get_actual_vs_plan(ids["well"])["depth"]
    expected = compare("Depth", planned, actual)
    assert result == dict(
        planned=planned, actual=actual, delta=expected.variance, pct=expected.variance_pct, status=expected.status
    )


def test_unrecorded_header_measurements_do_not_hide_real_parameter_rop(env):
    from core.database import DrillingParameters, TripSheetEntry

    db, ids = env
    with db.session_scope() as s:
        s.add(
            DrillingParameters(well_id=ids["well"], report_id=ids["report"], report_date=date(2026, 1, 1), avg_rop=12.5)
        )
    assert db.get_actual_vs_plan(ids["well"])["rop"]["actual"] == 12.5
    with db.session_scope() as s:
        row = s.get(DailyReport, ids["report"])
        assert row.rop_meter is row.wob is row.rpm is row.torque is row.pressure is None
    assert db.save_trip_sheet_entries(
        [dict(well_id=ids["well"], report_id=ids["report"], time="01:00", activity="Trip")]
    )
    with db.session_scope() as s:
        row = s.query(TripSheetEntry).one()
        assert row.depth is row.cum_trip is row.duration is None


def test_rop_forecast_uses_calendar_dates_not_observation_ordinals(env):
    from core.database import DrillingParameters
    from tabs.w12_Analysis import AnalysisWidget

    db, ids = env
    with db.session_scope() as s:
        s.add_all(
            [
                DrillingParameters(well_id=ids["well"], report_date=date(2026, 1, 1), avg_rop=0),
                DrillingParameters(well_id=ids["well"], report_date=date(2026, 1, 10), avg_rop=9),
            ]
        )
    plotted, messages = [], []
    stub = SimpleNamespace(
        current_well_id=ids["well"],
        _scope_params_query=lambda s: s.query(DrillingParameters).filter_by(well_id=ids["well"]),
        _scope_reports_query=lambda s: s.query(DailyReport).filter_by(well_id=ids["well"]),
        analytics_plot=SimpleNamespace(clear=lambda: None, plot=lambda *a, **k: plotted.append(a)),
        results_text=SimpleNamespace(setText=messages.append),
    )
    with db.session_scope() as s:
        AnalysisWidget.analyze_rop_prediction(stub, s)
    assert plotted[0][0] == [1, 10] and plotted[0][1] == [0, 9]
    assert plotted[2][0] == [11, 12, 13, 14, 15]
    assert "1.000 m/hr per day" in messages[-1]


@pytest.mark.parametrize("rig_days", [None, 0])
def test_w12_calendar_rate_unique_endpoints_and_canonical_unknown(env, rig_days):
    from test_kpi_parity import _Stub
    from tabs.w12_Analysis import AnalysisWidget
    db, ids = env
    stub = _Stub(db, ids["well"])
    stub._canonical_scope_kpis = lambda: {"rig_days": rig_days}
    with db.session_scope() as session:
        session.get(DailyReport, ids["report"]).depth_2400 = 0
        session.add(DailyReport(well_id=ids["well"], section_id=ids["section"],
                               report_date=date(2026, 1, 10), depth_2400=90))
    with db.session_scope() as session:
        result = AnalysisWidget.calculate_kpis(stub, session)
        assert result["total_days"] == rig_days
        assert result["daily_gain"] == 10
        timeline = AnalysisWidget.get_time_depth_data(stub, session)
        assert [r["day"] for r in timeline] == [1, 10]
        assert timeline[-1]["gain"] == 90  # interval change, NOT daily metres
        session.add(DailyReport(well_id=ids["well"], section_id=ids["second"],
                               report_date=date(2026, 1, 10), depth_2400=999))
    with db.session_scope() as session:
        assert AnalysisWidget.calculate_kpis(stub, session)["daily_gain"] is None


def test_w12_mud_sample_is_not_two_directional_measurements(env):
    from test_w12_analytics_truth import _Stub
    from tabs.w12_Analysis import AnalysisWidget
    from core.database import MudReport
    db, ids = env
    with db.session_scope() as session:
        session.add(MudReport(well_id=ids["well"], report_id=ids["report"],
                              report_date=date(2026, 1, 1), mw=1.2))
    with db.session_scope() as session:
        data = AnalysisWidget.get_today_data(_Stub(ids["well"]), session)
        assert data["mud_weight"] == 1.2
        assert data["mw_in"] is None and data["mw_out"] is None
        assert data["main_activity"] is None
        header = session.get(DailyReport, ids["report"])
        header.mud_weight_in, header.mud_weight_out = 0, 1.3
    with db.session_scope() as session:
        data = AnalysisWidget.get_today_data(_Stub(ids["well"]), session)
        assert data["mw_in"] == 0 and data["mw_out"] == 1.3


@pytest.mark.parametrize("failure", ["serialization", "replace", "fsync"])
def test_mapping_write_failure_preserves_disk_memory_and_cleans_temporary(tmp_path, monkeypatch, failure):
    import json
    from copy import deepcopy
    from core.mapping_store import MappingStore
    import core.runtime_config as config
    path = tmp_path / "mapping.json"
    store = MappingStore(path)
    store.remember("fp", {"depth": "A1"})
    disk, memory = path.read_bytes(), deepcopy(store.data)
    if failure != "serialization":
        def fail(*args, **kwargs):
            raise OSError("injected " + failure)
        monkeypatch.setattr(config.os, failure, fail)
    with pytest.raises((OSError, TypeError)):
        store.remember("fp", {"depth": object() if failure == "serialization" else "B2"})
    assert path.read_bytes() == disk and store.data == memory
    assert list(tmp_path.iterdir()) == [path]
    assert json.loads(path.read_text())["mappings"]["fp"]["revision"] == 1


def test_mapping_remember_owns_nested_input_after_success(tmp_path):
    from core.mapping_store import MappingStore
    store = MappingStore(tmp_path / "mapping.json")
    incoming = {"depth": {"column": "A"}}
    store.remember("fp", incoming)
    incoming["depth"]["column"] = "Z"
    assert store.get("fp")["fields"]["depth"]["column"] == "A"



def test_chart_export_false_result_is_not_success(monkeypatch):
    import tabs.w10_Planning_Widget as module
    errors = []
    monkeypatch.setattr(module.QMessageBox, "critical", lambda *args: errors.append(args))
    stub = SimpleNamespace(grab=lambda: SimpleNamespace(save=lambda path: False))
    from inspect import getclosurevars
    cls = getclosurevars(module.NPTReportTab.__init__).nonlocals["widget_class"]
    assert cls.export_charts_to_file(stub, "failed.png") is False
    assert errors and "not exported" in errors[0][2]



def test_template_save_io_failure_has_no_success_message(tmp_path, monkeypatch):
    import dialogs.smart_template_dialog as module
    monkeypatch.setattr(module, "user_templates_dir", lambda: tmp_path)
    successes, errors = [], []
    monkeypatch.setattr(module.QMessageBox, "information", lambda *args: successes.append(args))
    monkeypatch.setattr(module.QMessageBox, "critical", lambda *args: errors.append(args))
    def fail(*args, **kwargs):
        raise OSError("injected write failure")
    monkeypatch.setattr(module, "atomic_write_json", fail)
    stub = SimpleNamespace(template_name=SimpleNamespace(text=lambda: "M29"),
                           assignments={"depth": {"sheet": "DDR", "row": 1, "col": 1}},
                           _find_anchor_for_cell=lambda *args: "Depth")
    assert module.SmartTemplateDialog._save_template(stub) is False
    assert errors and not successes and not (tmp_path / "M29.json").exists()
