"""M62: continuous target distance, numerical safeguards, persistent plan revisions, plots.

References are independent closed forms (planar circular build: HD = R(1-cos t),
TVD = KOP + R sin t, MD = KOP + R t), not the module's own arc formula.
Persistence uses a temporary SQLite database with synthetic data; the panel
test runs offscreen (not Windows desktop testing).
"""
from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from core import directional_plans as dp
from core.well_plan_designer import PLAN_VERSION, arc_point, design_plan

KOP, DLS = 500.0, 3.0
R = 30.0 / math.radians(DLS)                      # 572.957795 m radius for 3 deg/30 m


def _build_plan(targets=()):
    return design_plan([{"type": "hold", "length": KOP}, {"type": "curve", "inc": 30.0, "azi": 0.0, "dls": DLS},
                        {"type": "hold", "length": 300.0}], step=30.0, targets=targets)


# ---- continuous target distance -------------------------------------------------------------------
def test_a_target_on_the_arc_between_stations_is_hit_exactly():
    theta = math.radians(10.5)                    # MD 605: between the 590 and 620 stations
    target = {"name": "T1", "north": R * (1 - math.cos(theta)), "east": 0.0, "tvd": KOP + R * math.sin(theta),
              "radius": 0.5}
    (result,) = _build_plan([target]).targets
    assert result["distance"] == pytest.approx(0.0, abs=1e-6)
    assert result["closest_md"] == pytest.approx(KOP + R * theta, abs=1e-4)
    assert result["hit"]
    assert result["station_distance"] > 7.0       # the M55 station check would have missed it
    assert result["closest_station_md"] in (590.0, 620.0)


def test_a_point_off_a_vertical_hold_measures_the_perpendicular_offset():
    plan = design_plan([{"type": "hold", "length": 1000.0}], step=30.0,
                       targets=[{"name": "T", "north": 7.0, "east": 0.0, "tvd": 515.0, "radius": 5.0}])
    (result,) = plan.targets
    assert result["distance"] == pytest.approx(7.0, abs=1e-9)
    assert result["closest_md"] == pytest.approx(515.0, abs=1e-6)
    assert not result["hit"]                      # 7 m > 5 m radius
    assert result["closest_point"]["tvd"] == pytest.approx(515.0, abs=1e-6)


def test_the_arc_reproduces_the_canonical_station_positions():
    stations = _build_plan().stations
    for s1, s2 in zip(stations, stations[1:]):
        md, north, east, tvd = arc_point(s1, s2, 1.0)
        assert (md, north, east, tvd) == pytest.approx((s2["md"], s2["north"], s2["east"], s2["tvd"]), abs=1e-6)


def test_a_target_without_radius_is_never_a_hit_and_version_is_m62():
    plan = _build_plan([{"name": "T", "north": 0.0, "east": 0.0, "tvd": 100.0}])
    assert plan.targets[0]["distance"] == pytest.approx(0.0, abs=1e-6) and not plan.targets[0]["hit"]
    assert plan.version == PLAN_VERSION == "M72 plan designer v3"


# ---- numerical safeguards ----------------------------------------------------------------------
@pytest.mark.parametrize("segments, targets, message", [
    ([{"type": "hold", "length": float("nan")}], [], "Segment 1: length is not a finite number."),
    ([{"type": "curve", "inc": 30.0, "dls": float("inf")}], [], "Segment 1: dls is not a finite number."),
    ([{"type": "hold", "length": 100.0}], [{"name": "T", "north": float("inf"), "east": 0, "tvd": 1}],
     "Target T: north is not a finite number."),
    ([{"type": "curve", "inc": 180.0, "azi": 0.0, "dls": 3.0}], [], "antiparallel"),
    ([{"type": "hold_to_tvd", "tvd": -5.0}], [], "is not below the current"),
])
def test_unsafe_inputs_are_explicit_errors(segments, targets, message):
    plan = design_plan(segments, targets=targets)
    assert not plan.ok and message in plan.error and not plan.stations


def test_turn_only_at_vertical_is_a_no_op_warning_not_a_nan():
    plan = design_plan([{"type": "hold", "length": 100.0}, {"type": "curve", "inc": 0.0, "azi": 90.0, "dls": 2.0}])
    assert plan.ok and "already at the target direction" in plan.warnings[0]
    assert all(math.isfinite(v) for s in plan.stations for v in s.values())


# ---- persistence --------------------------------------------------------------------------------
@pytest.fixture
def db_well():
    from synthetic_operations import make_file_database
    from core.database import Company, Project, Well

    manager = make_file_database(Path(tempfile.mkdtemp(prefix="m62-plans-")) / "plans.db")
    with manager.session_scope() as session:
        company = Company(name="SYN CO", code="SYN")
        session.add(company)
        session.flush()
        project = Project(name="SYN FIELD", code="SYNF", company_id=company.id)
        session.add(project)
        session.flush()
        well = Well(name="SYN-PLAN-01", code="SYN-PLAN-01", project_id=project.id)
        session.add(well)
        session.flush()
        well_id = well.id
    yield manager, well_id
    manager.engine.dispose()


def _inputs(length=300.0):
    return dp.plan_inputs([{"type": "hold", "length": KOP}, {"type": "curve", "inc": 30.0, "azi": 45.0, "dls": DLS},
                           {"type": "hold", "length": length}], targets=[{"name": "T", "north": 50, "east": 50,
                                                                          "tvd": 900, "radius": 30}])


def test_revisions_are_immutable_and_linked(db_well):
    db, well_id = db_well
    first = dp.save_plan(db, well_id=well_id, name="SYN plan", inputs=_inputs())
    assert first["revision"] == 1 and first["status"] == "draft" and first["method_version"] == PLAN_VERSION
    second = dp.revise_plan(db, first["id"], _inputs(length=450.0), note="longer hold")
    assert second["revision"] == 2 and second["parent_id"] == first["id"] and second["plan_key"] == first["plan_key"]
    assert dp.get_plan(db, first["id"])["inputs"] == _inputs()           # the parent is unchanged
    report = dp.compare_plans(first, second)
    assert [d["input"] for d in report["inputs"]] == ["segments"]
    td = next(r for r in report["results"] if r["quantity"] == "td_md")
    assert td["delta"] == pytest.approx(150.0, abs=1e-6)
    names = [(p["name"], p["revision"]) for p in dp.list_plans(db, well_id)]
    assert names == [("SYN plan", 2), ("SYN plan", 1)]


def test_clone_archive_and_invalid_plans(db_well, tmp_path):
    db, well_id = db_well
    first = dp.save_plan(db, well_id=well_id, name="SYN plan", inputs=_inputs())
    clone = dp.clone_plan(db, first["id"], "SYN sidetrack option")
    assert clone["plan_key"] != first["plan_key"] and clone["revision"] == 1 and clone["parent_id"] == first["id"]
    archived = dp.set_status(db, first["id"], "archived")
    assert archived["status"] == "archived"
    assert [p["name"] for p in dp.list_plans(db, well_id)] == ["SYN sidetrack option"]
    assert len(dp.list_plans(db, well_id, include_archived=True)) == 2
    with pytest.raises(ValueError, match="stays archived"):
        dp.set_status(db, first["id"], "draft")
    with pytest.raises(ValueError, match="not valid"):
        dp.save_plan(db, well_id=well_id, name="bad", inputs=dp.plan_inputs([{"type": "hold", "length": -1}]))
    out = tmp_path / "plan.csv"
    dp.export_plan_csv(clone, str(out))
    lines = out.read_text(encoding="utf-8").splitlines()
    assert "rev 1" in lines[0] and "not validated" in lines[0] and lines[1].startswith("MD (m)")
    assert len(lines) == 2 + len(clone["results"]["stations"])


def test_plan_tables_have_authorization_policies():
    from core.authorization import EDIT, NOBODY, TABLE_POLICY

    assert TABLE_POLICY["directional_plan_revisions"].required("insert") == (EDIT,)
    assert TABLE_POLICY["calculation_cases"].required("write") == (NOBODY,)


# ---- panel (offscreen) --------------------------------------------------------------------------
def test_panel_saves_revises_reopens_and_plots(db_well):
    from PySide6 import QtWidgets
    from tabs.well_plan_designer_panel import WellPlanDesignerPanel

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    db, well_id = db_well
    panel = WellPlanDesignerPanel(handover=True, db_manager=db)
    try:
        panel.set_well(well_id)
        panel.add_segment("hold", KOP)
        panel.add_segment("curve", None, 30.0, 0.0, DLS)
        panel.add_segment("hold", 300.0)
        first = panel.save_new_plan("SYN panel plan")
        assert first["revision"] == 1 and panel.plan_combo.count() == 1
        incs = panel.plot_series("inc")
        assert incs[0] == 0.0 and max(incs) == pytest.approx(30.0)
        assert max(panel.plot_series("dls")) == pytest.approx(DLS)
        panel.segment_table.item(2, 1).setText("400")
        second = panel.save_revision()
        assert second["revision"] == 2 and panel.plan_combo.count() == 2
        panel.open_plan(first["id"])
        assert panel.segment_table.item(2, 1).text() == "300.0"
        assert panel.current_plan["id"] == first["id"]
        report = panel.compare_with(second["id"])
        assert any(r["quantity"] == "td_md" and r["delta"] == pytest.approx(100.0) for r in report["results"])
        assert "Compare" in panel.plan_status_label.text()
    finally:
        panel.deleteLater()
        app.processEvents()


def test_a_survey_only_database_stub_disables_the_plan_library_without_breaking_the_panel():
    from PySide6 import QtWidgets
    from tabs.well_plan_designer_panel import WellPlanDesignerPanel

    class SurveyOnly:
        def load_survey_points(self, **_):
            return []

    class Broken:
        def session_scope(self):
            raise RuntimeError("synthetic database failure")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    panels = [WellPlanDesignerPanel(db_manager=SurveyOnly()), WellPlanDesignerPanel(db_manager=Broken())]
    try:
        panels[0].set_well(1)
        assert panels[0].plan_combo.count() == 0 and not panels[0].save_new_btn.isEnabled()
        panels[1].set_well(1)
        assert "could not be loaded: synthetic database failure" in panels[1].plan_status_label.text()
    finally:
        for panel in panels:
            panel.deleteLater()
        app.processEvents()
