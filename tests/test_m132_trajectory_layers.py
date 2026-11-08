"""M132: revision-aware 3D layers.

SYNTHETIC records only. Golden (by hand, independent of the code): survey revision stations MD 0 / 500 (vertical),
1000 (inc 30 deg, azi 90 deg), 1500 (inc 30, azi 90). The arc 500 -> 1000 m turns 30 deg over 500 m, radius
R = 500 / (pi / 6) = 954.93 m. A point at MD 750 is 250 m along it, theta = 250 / R = 15 deg:
TVD = 500 + R sin 15 = 747.15 m, East = R (1 - cos 15) = 32.54 m, North = 0.
"""
from __future__ import annotations

import copy
import gc

import pytest

from core import directional_plans as dp
from core import survey_revisions as sr
from core import trajectory_layers as tl
from core import well_architecture as wa
from tests.test_m70_integrity import _open, _seed

ROWS = [{"md": 0, "inc": 0, "azi": 0}, {"md": 500, "inc": 0, "azi": 0}, {"md": 1000, "inc": 30, "azi": 90},
        {"md": 1500, "inc": 30, "azi": 90}]
ARCH = [
    {"kind": "casing", "name": "13-3/8 csg", "top_md": 0, "bottom_md": 500, "od_in": 13.375, "id_in": 12.415,
     "hole_in": 17.5},
    {"kind": "shoe", "name": "13-3/8 csg", "top_md": 500},
    {"kind": "casing", "name": "9-5/8 csg", "top_md": 0, "bottom_md": 2000, "od_in": 9.625, "id_in": 8.681,
     "hole_in": 12.25},
    {"kind": "shoe", "name": "9-5/8 csg", "top_md": 2000},
    {"kind": "accessory", "name": "SYN marker", "top_md": 750},
]


@pytest.fixture
def env(tmp_path, monkeypatch):
    manager = _open(tmp_path / "m132.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    well, bore = ids["A"]
    survey = sr.save_revision(manager, well, ROWS, wellbore_id=bore, depth_datum="RKB", azimuth_reference="true")
    tie = sr.tie_in_from_revision(survey, md=1000)
    segments = [{"type": "hold", "length": 300.0}]
    plan = dp.save_plan(manager, well_id=well, wellbore_id=bore, name="SYN plan", inputs=dp.plan_inputs(
        segments, tie_in=tie, azimuth_reference="true", depth_datum="RKB",
        targets=[{"name": "T1", "north": 0.0, "east": 400.0, "tvd": 1200.0, "radius": 30.0}]))
    arch = wa.save_revision(manager, well, ARCH, wellbore_id=bore, survey_revision_id=survey["id"])
    yield {"manager": manager, "well": well, "bore": bore, "survey": survey, "plan": plan, "arch": arch,
           "segments": segments, "tie": tie}
    manager.close()


def _all(env, **kw):
    args = dict(wellbore_id=env["bore"], survey_id=env["survey"]["id"], plan_id=env["plan"]["id"],
                architecture_id=env["arch"]["id"])
    args.update(kw)
    return tl.build(env["manager"], env["well"], **args)


def test_pinned_records_are_overlaid_in_one_frame(env):
    result = _all(env)
    assert [layer.status for layer in result.layers] == [tl.DRAWN, tl.NOT_SELECTED, tl.DRAWN, tl.DRAWN, tl.DRAWN]
    assert result.method == tl.LAYER_METHOD and "NO CRS" in result.label
    assert "survey revision 1" in result.frame_label and "true north, datum RKB" in result.frame_label
    survey = result.layer(tl.SURVEY).path
    assert survey.tvd[0] == 0.0 and survey.east[1] == 0.0 and survey.tvd[1] == pytest.approx(500.0)
    plan = result.layer(tl.PLAN).path
    assert (plan.east[0], plan.north[0], plan.tvd[0]) == pytest.approx(
        (survey.east[2], survey.north[2], survey.tvd[2]))                 # the plan starts at its tie-in station
    targets = result.layer(tl.TARGETS)
    assert [(m.name, m.east, m.tvd, m.note) for m in targets.markers] == [("T1", 400.0, 1200.0, "radius 30 m")]
    assert targets.not_placed == ()
    plan = copy.deepcopy(dp.get_plan(env["manager"], env["plan"]["id"]))     # the designer refuses such a
    plan["inputs"]["targets"].append({"name": "T2", "north": None, "east": 10.0, "tvd": 900.0})   # target; defence
    targets = tl.assemble(env["survey"], plan=plan, well_id=env["well"]).layer(tl.TARGETS)
    assert targets.not_placed == (("T2", "a coordinate is not recorded"),) and len(targets.markers) == 1


def test_architecture_positions_follow_the_minimum_curvature_arc(env):
    arch = _all(env).layer(tl.ARCHITECTURE)
    markers = {m.name: m for m in arch.markers}
    assert (markers["shoe 13-3/8 csg"].east, markers["shoe 13-3/8 csg"].tvd) == pytest.approx((0.0, 500.0))
    marker = markers["accessory SYN marker"]
    assert marker.tvd == pytest.approx(747.15, abs=0.01) and marker.east == pytest.approx(32.54, abs=0.01)
    assert marker.north == pytest.approx(0.0, abs=1e-9)
    assert "shoe 9-5/8 csg" not in markers                                  # 2000 m is below the last station
    reasons = dict(arch.not_placed)
    assert "no extrapolation" in reasons["shoe 9-5/8 csg"] and "below the last survey station" in reasons["casing 9-5/8 csg"]
    deep = next(i for i in arch.intervals if i.name == "casing 9-5/8 csg")
    assert deep.tvd[-1] == pytest.approx(_all(env).layer(tl.SURVEY).path.tvd[-1])   # drawn to the last station only


def test_an_unpinned_or_foreign_tied_plan_is_not_overlaid(env):
    m, well, bore = env["manager"], env["well"], env["bore"]
    loose = dp.save_plan(m, well_id=well, wellbore_id=bore, name="SYN loose", inputs=dp.plan_inputs(
        env["segments"], tie_in={"md": 1000, "inc": 30, "azi": 90}, azimuth_reference="true", depth_datum="RKB"))
    layer = _all(env, plan_id=loose["id"]).layer(tl.PLAN)
    assert layer.status == tl.NOT_DRAWN and "not tied in to a survey revision" in layer.reason
    assert _all(env, plan_id=loose["id"]).layer(tl.TARGETS).status == tl.NOT_DRAWN
    second = sr.save_revision(m, well, ROWS + [{"md": 1600, "inc": 30, "azi": 90}], wellbore_id=bore,
                              depth_datum="RKB", azimuth_reference="true")
    layer = _all(env, survey_id=second["id"]).layer(tl.PLAN)
    assert layer.status == tl.NOT_DRAWN and "not to the base revision 2" in layer.reason
    undeclared = dp.save_plan(m, well_id=well, wellbore_id=bore, name="SYN undeclared",
                              inputs=dp.plan_inputs(env["segments"], tie_in=env["tie"]))
    layer = _all(env, plan_id=undeclared["id"]).layer(tl.PLAN)
    assert layer.status == tl.NOT_DRAWN and "plan azimuth reference NOT DECLARED" in layer.reason


def test_a_second_revision_is_overlaid_only_with_the_same_references_and_origin(env):
    m, well, bore = env["manager"], env["well"], env["bore"]
    same = sr.save_revision(m, well, ROWS + [{"md": 1600, "inc": 31, "azi": 91}], wellbore_id=bore,
                            depth_datum="RKB", azimuth_reference="true")
    assert _all(env, compare_id=same["id"]).layer(tl.COMPARE).status == tl.DRAWN
    grid = sr.transform_revision(m, same["id"], "grid", convergence_deg=1.5, parameter_source="SYN convergence",
                                 reference_date="2026-01-01")
    layer = _all(env, compare_id=grid["id"]).layer(tl.COMPARE)
    assert layer.status == tl.NOT_DRAWN and "azimuth reference differs: base true vs second revision grid" in layer.reason
    shifted = sr.save_revision(m, well, [dict(r, md=r["md"] + 100) for r in ROWS], wellbore_id=bore,
                               depth_datum="RKB", azimuth_reference="true")
    layer = _all(env, compare_id=shifted["id"]).layer(tl.COMPARE)
    assert layer.status == tl.NOT_DRAWN and "different origins" in layer.reason
    assert "the same revision" in _all(env, compare_id=env["survey"]["id"]).layer(tl.COMPARE).reason


def test_a_survey_failing_integrity_draws_nothing():
    record = copy.deepcopy({"id": 1, "revision": 1, "well_id": 1, "wellbore_id": None, "azimuth_reference": "true",
                            "depth_datum": "RKB", "stations": ROWS, "stations_sha256": "x" * 64,
                            "results": sr.compute(ROWS), "integrity": "HASH MISMATCH"})
    result = tl.assemble(record, plan={"id": 2, "well_id": 1, "name": "p", "inputs": {}, "results": {}}, well_id=1)
    assert [layer.status for layer in result.layers][:1] == [tl.NOT_DRAWN]
    assert "station hash" in result.layer(tl.SURVEY).reason and not result.drawable
    assert "failed its checks" in result.layer(tl.PLAN).reason


def test_a_tampered_plan_result_is_not_drawn(env):
    plan = copy.deepcopy(dp.get_plan(env["manager"], env["plan"]["id"]))
    plan["results"]["stations"][-1]["tvd"] += 5.0
    layer = tl.assemble(env["survey"], plan=plan, well_id=env["well"]).layer(tl.PLAN)
    assert layer.status == tl.NOT_DRAWN and "SHA-256" in layer.reason


def test_an_unpinned_architecture_is_not_placed(env):
    m, well, bore = env["manager"], env["well"], env["bore"]
    loose = wa.save_revision(m, well, ARCH, wellbore_id=bore)
    layer = _all(env, architecture_id=loose["id"]).layer(tl.ARCHITECTURE)
    assert layer.status == tl.NOT_DRAWN and "not pinned to a survey revision" in layer.reason
    layer = _all(env, survey_id=None).layer(tl.ARCHITECTURE)
    assert layer.status == tl.NOT_DRAWN and "select the survey it was drawn against" in layer.reason


def test_a_plan_alone_is_drawn_in_its_own_frame(env):
    result = _all(env, survey_id=None, architecture_id=None)
    assert result.layer(tl.PLAN).drawn and "its own tie-in" in result.frame_label
    assert "no survey revision selected" in result.frame_label


def test_wellbore_scope_excludes_other_and_unscoped_records(env):
    m, well = env["manager"], env["well"]
    from core.database import Wellbore

    with m.session_scope() as session:
        sidetrack = Wellbore(well_id=well, name="SYN-A ST1", wellbore_type="sidetrack")
        session.add(sidetrack)
        session.flush()
        sidetrack_id = sidetrack.id
    other = sr.save_revision(m, well, ROWS, wellbore_id=sidetrack_id, depth_datum="RKB", azimuth_reference="true")
    unscoped = sr.save_revision(m, well, ROWS, depth_datum="RKB", azimuth_reference="true")
    cat = tl.catalogue(m, well, env["bore"])
    assert [s["id"] for s in cat["surveys"]] == [env["survey"]["id"]]
    excluded = dict(cat["excluded"])
    assert "not the selected wellbore" in excluded[f"survey_revisions #{other['id']}"]
    assert "not recorded for a wellbore" in excluded[f"survey_revisions #{unscoped['id']}"]
    layer = _all(env, survey_id=other["id"]).layer(tl.SURVEY)
    assert layer.status == tl.NOT_DRAWN and "not the selected wellbore" in layer.reason
    whole = tl.catalogue(m, well, None)
    assert len(whole["surveys"]) == 3 and whole["excluded"] == []


def test_display_units_convert_lengths_only(env):
    metres, feet = _all(env), _all(env, unit="ft")
    assert feet.layer(tl.SURVEY).path.tvd[1] == pytest.approx(500.0 * 3.28084)
    assert feet.layer(tl.TARGETS).markers[0].note == f"radius {30 * 3.28084:g} ft"
    assert metres.layer(tl.SURVEY).path.tvd[1] == 500.0


# ---- real widgets: W6 Trajectory › 3D view -----------------------------------------------------------------------
@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def viewer(app, env):
    from tabs.trajectory_viewer import TrajectoryViewerTab

    tab = TrajectoryViewerTab(env["manager"])
    tab.set_context(env["well"])
    assert tab.layers_panel.wait()
    yield tab
    from test_trajectory_3d import _dispose

    tab.shutdown(5000)
    _dispose(app, tab)                       # deterministic destruction (M50), never at a later gc point


def _legend(view):
    legend = view.axes.get_legend()
    return [t.get_text() for t in legend.get_texts()] if legend is not None else []


def _rows(panel):
    t = panel.status_table
    return [tuple(t.item(i, j).text() for j in range(t.columnCount())) for i in range(t.rowCount())]


def test_the_3d_view_overlays_the_selected_revisions(viewer, env):
    panel, view = viewer.layers_panel, viewer.view3d
    assert panel.parent() is not None and panel.choices()["base"] == "working"      # default: as before M132
    assert panel.base_combo.findData(env["survey"]["id"]) > 0 and panel.plan_combo.findData(env["plan"]["id"]) > 0
    panel.select(base=env["survey"]["id"], plan=env["plan"]["id"], architecture=env["arch"]["id"])
    assert panel.wait() and view.layer_set is not None and view.scene is None
    legend = _legend(view)
    assert any(t.startswith("Survey revision 1") for t in legend) and any(t.startswith("Plan 'SYN plan'") for t in legend)
    assert any("Targets of" in t for t in legend) and any("Architecture revision 1 (strings)" == t for t in legend)
    assert "survey revision 1" in view.hint.text() and "NO CRS" in view.hint.text()
    rows = _rows(panel)
    assert [r[2] for r in rows[:5]] == [tl.DRAWN, tl.NOT_SELECTED, tl.DRAWN, tl.DRAWN, tl.DRAWN]
    assert any(r[2] == "NOT PLACED" and "shoe 9-5/8 csg" in r[0] for r in rows)
    viewer.unit_combo.setCurrentIndex(viewer.unit_combo.findData("ft"))             # units rebuild the layers
    assert panel.wait() and view.layer_set.unit == "ft"
    assert view.layer_set.layer(tl.SURVEY).path.tvd[1] == pytest.approx(500.0 * 3.28084)
    view.zoom(1.25)
    view.reset_view()                                                               # camera works in layer mode


def test_a_record_outside_the_frame_is_listed_not_drawn(viewer, env):
    m, well, bore = env["manager"], env["well"], env["bore"]
    loose = dp.save_plan(m, well_id=well, wellbore_id=bore, name="SYN loose", inputs=dp.plan_inputs(
        env["segments"], tie_in={"md": 1000, "inc": 30, "azi": 90}, azimuth_reference="true", depth_datum="RKB"))
    panel = viewer.layers_panel
    panel.set_scope(None)
    viewer._sync_layers()                                                           # re-read the records
    assert panel.wait()
    panel.select(base=env["survey"]["id"], plan=loose["id"])
    assert panel.wait()
    plan_row = next(r for r in _rows(panel) if r[0].startswith("Plan 'SYN loose'"))
    assert plan_row[2] == tl.NOT_DRAWN and "not tied in to a survey revision" in plan_row[3]
    assert not any(t.startswith("Plan") for t in _legend(viewer.view3d))


def test_the_working_survey_base_overlays_nothing(viewer, env):
    panel = viewer.layers_panel
    panel.select(base="working", plan=env["plan"]["id"])
    assert viewer.view3d.layer_set is None
    plan_row = next(r for r in _rows(panel) if r[0] == "Plan revision")
    assert plan_row[2] == tl.NOT_DRAWN and "no revision identity" in plan_row[3]


def test_wellbore_scope_lists_excluded_records(viewer, env):
    from core.database import Wellbore

    m, well = env["manager"], env["well"]
    with m.session_scope() as session:
        sidetrack = Wellbore(well_id=well, name="SYN-A ST1", wellbore_type="sidetrack")
        session.add(sidetrack)
        session.flush()
        sidetrack_id = sidetrack.id
    panel = viewer.layers_panel
    panel.set_scope(well, sidetrack_id)
    assert panel.wait()
    assert panel.base_combo.findData(env["survey"]["id"]) == -1                     # another wellbore's revision
    assert any(r[2] == "EXCLUDED (scope)" and "not the selected wellbore" in r[3] for r in _rows(panel))


def test_layers_are_read_on_a_worker_and_a_late_result_is_never_shown(viewer, env, monkeypatch):
    import threading

    from tabs import trajectory_layers_panel as tlp

    gate, entered, threads, real = threading.Event(), threading.Event(), [], tl.build

    def slow(db, well, **kw):
        threads.append(threading.current_thread() is threading.main_thread())
        entered.set()
        gate.wait(10)
        return real(db, well, **kw)

    monkeypatch.setattr(tlp.tl, "build", slow)
    panel = viewer.layers_panel
    try:
        panel.select(base=env["survey"]["id"])
        assert panel.jobs.synchronous is False and entered.wait(10)
        panel.set_scope(None)                                                       # cleared while reading
        gate.set()
        assert panel.wait() and threads == [False]
        assert panel.layer_set is None and viewer.view3d.layer_set is None
        assert panel.jobs.rejected["superseded"] >= 1
    finally:
        gate.set()


def test_the_layers_follow_the_central_wellbore_selection_and_w6_cleanup_joins_the_reader(app, env, monkeypatch):
    """M124 identity: the explicitly selected wellbore scopes the records; clearing the selection resets them."""
    from core.database import Wellbore
    from core.selection_manager import SelectionManager
    from tabs.trajectory_viewer import TrajectoryViewerTab
    from tabs.w6_Trajectory_Widget import TrajectoryWidget
    from test_trajectory_3d import _dispose

    m, well = env["manager"], env["well"]
    with m.session_scope() as session:
        sidetrack = Wellbore(well_id=well, name="SYN-A ST1", wellbore_type="sidetrack")
        session.add(sidetrack)
        session.flush()
        sidetrack_id = sidetrack.id
    sel = SelectionManager()
    sel.clear()
    tab = TrajectoryViewerTab(m)
    try:
        sel.select_well(well, {"id": well, "name": "SYN-A"})
        tab.set_context(well)
        assert tab.layers_panel.wait() and tab.layers_panel.wellbore_id is None
        sel.select_wellbore(sidetrack_id, {"name": "SYN-A ST1"})
        assert tab.layers_panel.wait() and tab.layers_panel.wellbore_id == sidetrack_id
        assert tab.layers_panel.base_combo.findData(env["survey"]["id"]) == -1
        sel.clear()                          # no explicit wellbore any more: back to the whole well (W6 itself
        assert tab.layers_panel.wait() and tab.layers_panel.wellbore_id is None       # resets the viewer's well)
        assert tab.layers_panel.base_combo.findData(env["survey"]["id"]) > 0
        tab.set_context(None)
        assert tab.layers_panel.base_combo.count() == 2 and tab.layers_panel.well_id is None
    finally:
        sel.clear()
        tab.shutdown(5000)
        _dispose(app, tab)
    calls, original = [], TrajectoryViewerTab.shutdown

    def recording(viewer, timeout_ms=5000):
        calls.append(timeout_ms)
        return original(viewer, timeout_ms)

    # Patched on the class, not the instance: a closure stored on the widget would be a reference cycle that
    # leaves Qt garbage for a later gc pass (the M50 rule; it crashed a later MainWindow test).
    monkeypatch.setattr(TrajectoryViewerTab, "shutdown", recording)
    w6 = TrajectoryWidget(m)
    try:
        assert w6.viewer_tab is not None                                   # built in W6 init_ui
        w6.cleanup()
        assert calls == [5000]
    finally:
        _dispose(app, w6)
        del w6
        # W6 keeps edit-tracking closures over itself (core.editor_bindings): free that cycle HERE, at an idle
        # point, never inside a later test's Qt work (M50; D49 made it collectable at all).
        gc.collect()


def test_a_disposed_tab_is_not_retained_by_the_status_or_shortcut_managers(app, env):
    """D49: ``StatusBarManager`` held every registered tab strongly and ``ShortcutManager`` closed a cycle with it,
    so a disposed W6 (with its 3D view and layer reader) stayed alive and was freed by an arbitrary later
    garbage-collection pass inside another test's Qt work (native crash). Now nothing global keeps it."""
    import weakref

    from core.managers import ShortcutManager, StatusBarManager
    from tabs.w6_Trajectory_Widget import TrajectoryWidget
    from test_trajectory_3d import _dispose

    w6 = TrajectoryWidget(env["manager"])
    assert StatusBarManager()._widgets.get("TrajectoryWidget") is w6
    assert isinstance(w6.shortcut_manager, ShortcutManager) and w6.shortcut_manager.main_window is w6
    refs = [weakref.ref(w6), weakref.ref(w6.viewer_tab), weakref.ref(w6.viewer_tab.layers_panel)]
    w6.cleanup()
    _dispose(app, w6)
    del w6
    gc.collect()
    assert [ref() for ref in refs] == [None, None, None]
    assert "TrajectoryWidget" not in StatusBarManager()._widgets


def test_a_widget_with_shortcuts_is_freed_by_reference_counting(app):
    """D49: without editor bindings, a widget wired by ``setup_widget_with_managers`` has no reference cycle, so it
    is freed when released - not by a later garbage-collection pass (gc disabled here to prove it)."""
    import weakref

    from PySide6.QtWidgets import QWidget

    from core.managers import StatusBarManager, setup_widget_with_managers
    from test_trajectory_3d import _dispose

    widget = QWidget()
    setup_widget_with_managers(widget, "M132 probe", setup_shortcuts=True)
    StatusBarManager().register_widget("M132 probe", widget)
    ref = weakref.ref(widget)
    gc.collect()
    was_enabled = gc.isenabled()          # D53: the test session runs with automatic collection off
    gc.disable()
    try:
        _dispose(app, widget)
        del widget
        assert ref() is None
    finally:
        if was_enabled:
            gc.enable()
