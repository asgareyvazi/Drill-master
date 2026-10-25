"""M45: 3D survey view - geometry of core/trajectory_3d.py and the viewer tab.

Geometry goldens are independent of the minimum-curvature engine.  Minimum
curvature assumes each survey interval is a circular arc, so for an interval
of length L between unit tangents t1 and t2 (dogleg beta) the end point is
given by the parametric circle

    P(L) = P0 + R * (sin(beta) * t1 + (1 - cos(beta)) * n),
    R = L / beta,   n = (t2 - cos(beta) * t1) / sin(beta)

with t(inc, azi) = (sin inc * sin azi [East], sin inc * cos azi [North],
cos inc [down]).  This is plain circle geometry, not the engine's
ratio-factor formula.  A straight interval adds L * t.

UI part - environment label: QT_QPA_PLATFORM=offscreen (in the sandbox with
stub GL/dbus/xkb libraries), real widgets, real Matplotlib Qt canvas, real
synthetic SQLite database.  Mouse interaction is exercised through the same
handlers Matplotlib calls (no physical mouse); this is NOT native Windows
desktop testing.
"""
import math
import os
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.trajectory_3d import AXIS_CONVENTION, Scene3D, axis_limits, nearest_station, scene_from_trajectory  # noqa: E402
from core.well_trajectory import INSUFFICIENT_DATA, NO_DATA, compose_well_trajectory  # noqa: E402
from synthetic_operations import build_synthetic_operations, make_file_database  # noqa: E402

FT = 0.3048


def _rows(points):
    return [{"id": n + 1, "md": md, "inc": inc, "azi": azi, "report_id": 1} for n, (md, inc, azi) in enumerate(points)]


def _tangent(inc, azi):
    i, a = math.radians(inc), math.radians(azi)
    return (math.sin(i) * math.sin(a), math.sin(i) * math.cos(a), math.cos(i))


def _arc_end(p0, t1, t2, length):
    """Independent circle geometry (see module docstring)."""
    cos_beta = max(-1.0, min(1.0, sum(a * b for a, b in zip(t1, t2))))
    beta = math.acos(cos_beta)
    if beta < 1e-12:
        return tuple(p + length * t for p, t in zip(p0, t1))
    radius = length / beta
    n = tuple((b - cos_beta * a) / math.sin(beta) for a, b in zip(t1, t2))
    return tuple(p + radius * (math.sin(beta) * a + (1 - cos_beta) * c) for p, a, c in zip(p0, t1, n))


# Build 0 -> 30 deg towards north over 1000 m, turn from azimuth 0 to 90 at
# 30 deg inclination over 300 m, hold 200 m towards east.
TURN_PROFILE = [(0.0, 0.0, 0.0), (1000.0, 30.0, 0.0), (1300.0, 30.0, 90.0), (1500.0, 30.0, 90.0)]


def _expected_turn_points():
    points = [(0.0, 0.0, 0.0)]                                  # (east, north, tvd) at the tie-on
    for (md0, inc0, azi0), (md1, inc1, azi1) in zip(TURN_PROFILE, TURN_PROFILE[1:]):
        points.append(_arc_end(points[-1], _tangent(inc0, azi0), _tangent(inc1, azi1), md1 - md0))
    return points


# ------------------------------------------------------------- geometry
def test_vertical_well_is_a_vertical_line_with_tvd_equal_to_md():
    trajectory = compose_well_trajectory(_rows([(100.0 * k, 0.0, 0.0) for k in range(11)]))
    scene = scene_from_trajectory(trajectory, "m")
    assert scene.drawable and scene.md == tuple(100.0 * k for k in range(11))
    assert all(abs(v) < 1e-9 for v in scene.east + scene.north)
    assert scene.tvd == pytest.approx(scene.md, abs=1e-9)
    (x0, x1), (y0, y1), (z0, z1) = axis_limits(scene)
    assert x1 - x0 == pytest.approx(z1 - z0) == pytest.approx(y1 - y0)     # equal scale, no fake slope
    assert (x0 + x1) / 2 == pytest.approx(0.0) and z0 < 0.0 < 1000.0 < z1


def test_build_and_turn_matches_independent_circle_geometry():
    trajectory = compose_well_trajectory(_rows(TURN_PROFILE))
    scene = scene_from_trajectory(trajectory, "m")
    expected = _expected_turn_points()
    assert scene.md == tuple(md for md, _i, _a in TURN_PROFILE)                  # MD order, nothing added
    for k, (east, north, tvd) in enumerate(expected):
        assert scene.point(k) == pytest.approx((east, north, tvd), abs=1e-6), k
    # Sanity of the reference itself: the build is purely northward ...
    radius = 1000.0 / math.radians(30.0)
    assert expected[1] == pytest.approx((0.0, radius * (1 - math.cos(math.radians(30))),
                                         radius * math.sin(math.radians(30))))
    # ... and the turn moves the path east (an East/North swap would fail above).
    assert expected[3][0] > expected[2][0] > 0.0
    # The 3D points are the composer's stations, unchanged.
    assert [(s.east, s.north, s.tvd) for s in trajectory.stations] == [scene.point(k) for k in range(4)]


def test_feet_are_an_exact_display_conversion_of_the_same_points():
    trajectory = compose_well_trajectory(_rows(TURN_PROFILE))
    metres, feet = scene_from_trajectory(trajectory, "m"), scene_from_trajectory(trajectory, "ft")
    assert feet.unit == "ft"
    for column in ("east", "north", "tvd", "md"):
        assert getattr(feet, column) == pytest.approx(tuple(v / FT for v in getattr(metres, column)), rel=1e-12)


def test_excluded_rows_never_become_points():
    rows = _rows([(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (200.0, None, 0.0), (300.0, 2.0, 45.0),
                  (300.0, 9.0, 200.0), (400.0, 4.0, 45.0), (500.0, 6.0, 45.0)])
    trajectory = compose_well_trajectory(rows)
    scene = scene_from_trajectory(trajectory, "m")
    assert {issue.code for issue in trajectory.issues} >= {"MISSING_ANGLE", "CONFLICTING_DUPLICATE"}
    assert 200.0 not in scene.md and 300.0 not in scene.md                    # invalid and conflicting
    assert scene.md == (0.0, 100.0, 400.0, 500.0) == tuple(s.md for s in trajectory.stations)


@pytest.mark.parametrize("rows, status", [
    ([], NO_DATA),
    (_rows([(100.0, 1.0, 10.0)]), INSUFFICIENT_DATA),
    (_rows([(100.0, None, 10.0), (200.0, 400.0, 10.0)]), INSUFFICIENT_DATA),
])
def test_non_drawable_trajectories_give_no_points_and_a_reason(rows, status):
    scene = scene_from_trajectory(compose_well_trajectory(rows), "m")
    assert scene.status == status and not scene.drawable
    assert scene.east == scene.north == scene.tvd == () and scene.message
    with pytest.raises(ValueError):
        axis_limits(scene)
    none = scene_from_trajectory(None)
    assert not none.drawable and none.message == "No well or survey selected."


def test_out_of_order_stations_are_refused_not_reordered():
    station = lambda md: SimpleNamespace(md=md, east=0.0, north=0.0, tvd=md)  # noqa: E731
    fake = SimpleNamespace(drawable=True, status="READY", stations=[station(0.0), station(200.0), station(100.0)])
    with pytest.raises(ValueError):
        scene_from_trajectory(fake)


def test_axis_limits_equal_and_independent():
    scene = scene_from_trajectory(compose_well_trajectory(_rows(TURN_PROFILE)), "m")
    equal = axis_limits(scene)
    assert len({round(hi - lo, 9) for lo, hi in equal}) == 1
    independent = axis_limits(scene, equal=False)
    assert len({round(hi - lo, 6) for lo, hi in independent}) == 3
    for (lo, hi), column in zip(equal, (scene.east, scene.north, scene.tvd)):
        assert lo < min(column) and max(column) < hi
    assert "z = TVD positive down" in AXIS_CONVENTION


def test_nearest_station_uses_tolerance_and_maps_to_station_indices():
    scene = Scene3D("READY", "m", east=(0, 1, 2), north=(0, 0, 0), tvd=(0, 1, 2), md=(0, 1, 2),
                    station_indices=(0, 1, 2))
    projected = [(10.0, 10.0), (50.0, 50.0), (90.0, 90.0)]
    assert nearest_station(scene, projected, 52.0, 49.0, 8.0) == 1
    assert nearest_station(scene, projected, 70.0, 70.0, 8.0) is None
    assert nearest_station(scene, projected, 11.0, 10.0, 8.0) == 0


# ------------------------------------------------------------------ UI
@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    db = make_file_database(tmp_path_factory.mktemp("ui3d") / "syn.db")
    ids = build_synthetic_operations(db, end_date=date.today() - timedelta(days=1))
    yield db, ids
    db.engine.dispose()


def _dispose(app, widget):
    """Destroy a widget deterministically (close, deleteLater, flush), never at
    an arbitrary garbage-collection point inside Qt event dispatch."""
    from PySide6.QtCore import QCoreApplication, QEvent
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.fixture
def viewer(app, synthetic):
    from tabs.trajectory_viewer import TrajectoryViewerTab
    widget = TrajectoryViewerTab(synthetic[0])
    widget.resize(1400, 900)
    widget.view_tabs.setCurrentWidget(widget.view3d)
    widget.show()
    app.processEvents()
    yield widget
    _dispose(app, widget)


def _lines(view):
    return len(view.axes.lines)


def test_3d_tab_shows_the_same_stations_as_the_2d_views(viewer, synthetic):
    _db, ids = synthetic
    titles = [viewer.view_tabs.tabText(i) for i in range(viewer.view_tabs.count())]
    assert titles == ["Plan view", "Vertical section", "3D view"]           # 2D stays the reference
    viewer.set_context(ids["dev"], None)
    view = viewer.view3d
    assert view.interactive and view.scene.drawable and len(view.scene.md) == 61 == len(viewer.stations)
    plan_x, plan_y = viewer.plan_plot.listDataItems()[0].getData()
    _vs, section_tvd = viewer.section_plot.listDataItems()[0].getData()
    assert list(view.scene.east) == pytest.approx(list(plan_x)) and list(view.scene.north) == pytest.approx(list(plan_y))
    assert list(view.scene.tvd) == pytest.approx(list(section_tvd))
    xs, ys, zs = view.axes.lines[0].get_data_3d()                             # the path actually drawn
    assert list(zs) == pytest.approx(list(section_tvd)) and list(xs) == pytest.approx(list(plan_x))
    assert view.scene.point(60)[2] == pytest.approx(1612.06, abs=0.01)        # M44 golden TVD at MD 1800
    low, high = view.axes.get_zlim()
    assert low > high                                                         # TVD axis inverted (down)
    assert "TVD (m, down)" == view.axes.get_zlabel() and view.axes.get_xlabel() == "East (m)"
    assert "equal scale" in view.hint.text() and "relative to the tie-on" in view.hint.text()


def test_clicking_a_station_selects_the_real_station_everywhere(viewer, synthetic):
    _db, ids = synthetic
    viewer.set_context(ids["dev"], None)
    view = viewer.view3d
    x, y = view.projected_points()[60]
    view._mouse_press(SimpleNamespace(x=x, y=y, button=1))
    view._mouse_release(SimpleNamespace(x=x + 1, y=y, button=1))              # a click (<= 4 px)
    assert viewer.selected_index == 60 and viewer.info_labels["MD"].text() == "1,800.00 m"
    assert viewer.info_labels["TVD"].text() == "1,612.06 m" and viewer.table.currentRow() == 60
    assert view.highlighted_point() == pytest.approx(view.scene.point(60))
    assert [i for i in viewer.plan_plot.items() if getattr(i, "_m44_highlight", False)]

    (x, y), (x2, y2) = view.projected_points()[10], view.projected_points()[20]
    assert math.hypot(x2 - x, y2 - y) > 4                                     # really a drag
    view._mouse_press(SimpleNamespace(x=x, y=y, button=1))
    view._mouse_release(SimpleNamespace(x=x2, y=y2, button=1))                # rotation drag ending on a station
    assert viewer.selected_index == 60                                        # not a pick
    assert view.pick_at(-500.0, -500.0) is None and viewer.selected_index == 60

    viewer.table.selectRow(10)                                                # table -> 3D highlight
    assert viewer.selected_index == 10
    assert view.highlighted_point() == pytest.approx(view.scene.point(10))
    assert sum(1 for c in view.axes.collections if getattr(c, "_m45_highlight", False)) == 1


def test_presets_reset_and_zoom_change_only_the_camera(viewer, synthetic):
    _db, ids = synthetic
    viewer.set_context(ids["dev"], None)
    view = viewer.view3d
    data = (view.scene.east, view.scene.north, view.scene.tvd)
    assert view.camera() == (25.0, -60.0)
    view.preset_combo.setCurrentIndex(1)
    assert view.camera() == (90.0, -90.0)
    span = lambda: view.axes.get_xlim()[1] - view.axes.get_xlim()[0]  # noqa: E731
    before = span()
    view.zoom(2.0)
    assert span() == pytest.approx(before / 2.0)
    view._scroll(SimpleNamespace(button="down"))
    assert span() == pytest.approx(before / 2.0 / 0.8)
    assert (view.scene.east, view.scene.north, view.scene.tvd) == data
    view.reset_view()
    assert view.camera() == (25.0, -60.0) and span() == pytest.approx(before)
    viewer.select_station(5)
    viewer.points_check.toggle()                                              # re-render keeps the selection
    assert view.highlighted_point() == pytest.approx(view.scene.point(5))
    view.stations_check.setChecked(False)                                     # 3D-only redraw keeps it too
    assert view.highlighted_point() == pytest.approx(view.scene.point(5))
    assert view.camera() == (25.0, -60.0)


def test_unit_and_scale_options_follow_the_viewer(viewer, synthetic):
    _db, ids = synthetic
    viewer.set_context(ids["dev"], None)
    metres = viewer.view3d.scene
    viewer.unit_combo.setCurrentIndex(viewer.unit_combo.findData("ft"))
    feet = viewer.view3d.scene
    assert feet.unit == "ft" and viewer.view3d.axes.get_xlabel() == "East (ft)"
    assert feet.tvd == pytest.approx(tuple(v / FT for v in metres.tvd))
    viewer.aspect_check.setChecked(False)
    assert viewer.view3d.equal_scale is False and "angles distorted" in viewer.view3d.hint.text()


def test_no_plottable_path_shows_a_reason_and_draws_nothing(viewer, synthetic, monkeypatch):
    db, ids = synthetic
    view = viewer.view3d
    viewer.set_context(ids["dev"], None)
    assert _lines(view) > 0
    viewer.set_context(None)
    assert view.scene is None and _lines(view) == 0 and "Select a well" in view.message.text()
    viewer.set_context(ids["vert"], None)                                     # no surveys
    assert view.scene is None and _lines(view) == 0 and "No survey stations" in view.message.text()
    viewer.scope_combo.setCurrentIndex(viewer.scope_combo.findData("report"))
    viewer.set_context(ids["dev"], None)
    assert _lines(view) == 0 and "daily report" in view.message.text()
    viewer.scope_combo.setCurrentIndex(viewer.scope_combo.findData("well"))

    def broken(**_kwargs):
        raise RuntimeError("synthetic read failure")
    monkeypatch.setattr(db, "load_survey_points", broken)
    viewer.reload()
    assert _lines(view) == 0 and "could not be read" in view.message.text()
    assert view.highlighted_point() is None


def test_single_station_is_not_drawn_in_3d(app):
    from tabs.trajectory_viewer import TrajectoryViewerTab

    class OneStation:
        def load_survey_points(self, well_id=None, report_id=None):
            return [{"id": 1, "md": 100.0, "inc": 1.0, "azi": 10.0, "report_id": 1}]
    viewer = TrajectoryViewerTab(OneStation())
    viewer.set_context(1, None)
    assert viewer.view3d.scene is None and len(viewer.view3d.axes.lines) == 0
    assert "At least two valid stations" in viewer.view3d.message.text()
    _dispose(app, viewer)


def test_without_an_interactive_canvas_nothing_is_presented_as_3d(app):
    from tabs.trajectory_3d_view import Trajectory3DView
    view = Trajectory3DView(canvas_loader=lambda: (None, False, "Interactive 3D needs the Qt canvas."))
    assert not view.interactive and view.canvas is None and view.figure is None
    assert view.message.text().startswith("3D view unavailable")
    assert not view.preset_combo.isEnabled() and not view.reset_button.isEnabled()
    scene = scene_from_trajectory(compose_well_trajectory(_rows(TURN_PROFILE)), "m")
    view.render(scene)
    assert view.scene is None and view.pick_at(0, 0) is None and view.highlighted_point() is None
    _dispose(app, view)


def test_static_agg_fallback_is_reported_as_not_interactive(app, monkeypatch):
    import core.matplotlib_widgets as widgets
    from tabs import trajectory_3d_view
    monkeypatch.setattr(widgets, "select_figure_canvas", lambda: (widgets.AggFigureCanvasWidget, False))
    canvas_class, interactive, reason = trajectory_3d_view._load_canvas()
    assert canvas_class is None and interactive is False and "Qt Matplotlib canvas" in reason
    monkeypatch.undo()
    canvas_class, interactive, reason = trajectory_3d_view._load_canvas()
    assert interactive is True and canvas_class.__name__ == "FigureCanvasQTAgg" and reason == ""


def test_a_destroyed_view_leaves_no_pending_draw(app):
    """Render, then destroy the C++ objects before the event loop runs: no
    queued draw may fire on the deleted canvas (it used to raise
    'Internal C++ object (FigureCanvasQTAgg) already deleted' in whatever
    code processed events next)."""
    import shiboken6

    from tabs.trajectory_viewer import TrajectoryViewerTab
    viewer = TrajectoryViewerTab(None)
    viewer.view3d.render(scene_from_trajectory(compose_well_trajectory(_rows(TURN_PROFILE)), "m"))
    viewer.view3d.zoom(1.25)
    shiboken6.delete(viewer)
    app.processEvents()                                   # must not raise


def test_hidden_view_draws_when_shown(app):
    from tabs.trajectory_3d_view import Trajectory3DView
    view = Trajectory3DView()
    drawn = []
    original = view.canvas.draw
    view.canvas.draw = lambda: (drawn.append(1), original())[1]
    view.render(scene_from_trajectory(compose_well_trajectory(_rows(TURN_PROFILE)), "m"))
    app.processEvents()
    assert drawn == [] and view._dirty                     # hidden: nothing drawn yet
    view.resize(800, 600)
    view.show()
    for _ in range(5):
        app.processEvents()
    assert drawn and not view._dirty                       # drawn once visible
    _dispose(app, view)
