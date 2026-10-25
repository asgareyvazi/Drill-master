"""M46: the 3D view's owned draw timer coalesces requests and leaves nothing
pending through rotate/zoom/resize, hide/show and close.  Offscreen Qt
(QT_QPA_PLATFORM=offscreen) - not a native Windows desktop test.  SYNTHETIC
trajectory (tests/test_trajectory_3d.TURN_PROFILE)."""
import pytest

pytest.importorskip("PySide6.QtWidgets")

from core.trajectory_3d import scene_from_trajectory  # noqa: E402
from core.well_trajectory import compose_well_trajectory  # noqa: E402
from test_trajectory_3d import TURN_PROFILE, _dispose, _rows, app  # noqa: E402,F401  (fixture)


def _counted_view(app):  # noqa: F811
    from tabs.trajectory_3d_view import Trajectory3DView
    view = Trajectory3DView()
    if not view.interactive:
        pytest.skip("no interactive Matplotlib Qt canvas in this environment")
    drawn = []
    original = view.canvas.draw
    view.canvas.draw = lambda: (drawn.append(1), original())[1]
    view.resize(700, 500)
    view.show()
    app.processEvents()
    view.render(scene_from_trajectory(compose_well_trajectory(_rows(TURN_PROFILE)), "m"))
    for _ in range(3):
        app.processEvents()
    drawn.clear()
    return view, drawn


def _settle(app):  # noqa: F811
    for _ in range(5):
        app.processEvents()


def test_many_requests_in_one_event_cycle_draw_once_and_leave_no_timer(app):  # noqa: F811
    view, drawn = _counted_view(app)
    for _ in range(25):                                   # rotate/zoom handlers and our own requests
        view.canvas.draw_idle()
        view.zoom(1.05)
    view.apply_preset()
    view.resize(760, 540)
    _settle(app)
    assert drawn == [1]
    assert not view._draw_timer.isActive() and not view._dirty
    _settle(app)
    assert drawn == [1]                                   # nothing re-arms itself
    _dispose(app, view)


def test_hide_show_close_cycle_draws_only_when_visible_and_nothing_survives(app):  # noqa: F811
    import shiboken6
    view, drawn = _counted_view(app)
    view.hide()
    view.zoom(1.25)
    view.canvas.draw_idle()
    _settle(app)
    assert drawn == [] and view._dirty and not view._draw_timer.isActive()   # hidden: deferred, not dropped
    view.show()
    _settle(app)
    assert drawn == [1] and not view._dirty and not view._draw_timer.isActive()
    for _ in range(3):                                    # repeated cycles stay balanced
        view.hide()
        view.zoom(0.9)
        view.show()
        _settle(app)
    assert len(drawn) == 4 and not view._draw_timer.isActive()
    view.zoom(1.1)                                        # a request pending at close ...
    timer = view._draw_timer
    _dispose(app, view)
    assert not shiboken6.isValid(view) and not shiboken6.isValid(timer)   # ... dies with the owned timer
    _settle(app)                                          # and never fires on the deleted canvas
