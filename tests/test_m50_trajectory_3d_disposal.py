"""M50 §8: a destroyed 3D view leaves no Qt wrapper for the cyclic garbage collector.

The Windows gate crashed natively (access violation / stack overflow) at the
first render or event processing of a NEW 3D view, with the test's own line as
the top Python frame - the signature of an automatic garbage collection
freeing Qt wrappers left over from earlier views.  Measured on Linux before the
fix: every disposed view (close + deleteLater, shiboken6.delete, or through its
parent tab) left the view, its canvas, timer and child widgets in reference
cycles (figure <-> canvas, canvas.draw_idle -> view, Matplotlib's first-import
exception/frame cycles reaching the constructing view), freed only by a later
collection running inside whatever Qt work came next.

These tests are deterministic: automatic collection is disabled, the view is
disposed, then (1) the view and canvas must already be gone by reference
counting and (2) an explicit collection must find no Qt wrapper created by the
test (wrappers that existed before it - other tests' widgets - are held and
excluded, after their queued deletions are flushed).
Offscreen Qt - NOT a native Windows desktop test.  SYNTHETIC trajectory.
"""
import gc
import os
import subprocess
import sys
import textwrap
import weakref
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from core.trajectory_3d import scene_from_trajectory  # noqa: E402
from core.well_trajectory import compose_well_trajectory  # noqa: E402
from test_trajectory_3d import TURN_PROFILE, _dispose, _rows, app  # noqa: E402,F401  (fixture)

ROOT = Path(__file__).resolve().parents[1]


def _scene():
    return scene_from_trajectory(compose_well_trajectory(_rows(TURN_PROFILE)), "m")


def _qt_wrappers_left_after(app, make, destroy, patch_draw=False):  # noqa: F811
    import shiboken6

    from PySide6.QtCore import QCoreApplication, QEvent

    from tabs.trajectory_3d_view import Trajectory3DView
    # Measure only what THIS test creates.  Earlier tests may leave deleteLater() events queued; processing
    # them inside the window below turns their wrappers into cyclic garbage (seen in CI full-suite order:
    # ExcelImportDialog, BitRecordTab, ...).  Flush them first, then hold every pre-existing wrapper so
    # none can become garbage (or have its id reused) while this test runs.
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    gc.collect()
    gc.disable()
    before = [o for o in gc.get_objects() if isinstance(o, shiboken6.Shiboken.Object)]
    before_ids = {id(o) for o in before}
    try:
        widget = make()
        view = widget if isinstance(widget, Trajectory3DView) else widget.view3d
        if not view.interactive:
            pytest.skip("no interactive Matplotlib Qt canvas in this environment")
        if patch_draw:                                     # what the M46 lifecycle tests do
            original = view.canvas.draw
            view.canvas.draw = lambda: original()
        widget.resize(700, 500)
        widget.show()
        app.processEvents()
        view.render(_scene())
        view.zoom(1.1)
        for _ in range(3):
            app.processEvents()
        refs = {"view": weakref.ref(view), "canvas": weakref.ref(view.canvas)}
        destroy(app, widget)
        del widget, view
        if patch_draw:
            del original
        alive = sorted(name for name, ref in refs.items() if ref() is not None)
        gc.set_debug(gc.DEBUG_SAVEALL)
        gc.collect()
        gc.set_debug(0)
        wrappers = sorted({type(o).__name__ for o in gc.garbage
                           if isinstance(o, shiboken6.Shiboken.Object) and id(o) not in before_ids})
        return alive, wrappers
    finally:
        gc.set_debug(0)
        gc.garbage.clear()
        del before
        gc.enable()


def _shiboken_delete(app, widget):  # noqa: F811
    import shiboken6
    shiboken6.delete(widget)
    app.processEvents()


def _view():
    from tabs.trajectory_3d_view import Trajectory3DView
    return Trajectory3DView()


def _viewer_tab():
    from tabs.trajectory_viewer import TrajectoryViewerTab
    return TrajectoryViewerTab(None)


@pytest.mark.parametrize("make", [_view, _viewer_tab], ids=["view", "viewer-tab"])
@pytest.mark.parametrize("destroy", [_dispose, _shiboken_delete], ids=["deleteLater", "shiboken-delete"])
def test_destroyed_view_is_freed_now_and_leaves_no_qt_wrapper_for_gc(app, make, destroy):  # noqa: F811
    alive, wrappers = _qt_wrappers_left_after(app, make, destroy)
    assert alive == [], f"still referenced after disposal: {alive}"
    assert wrappers == [], f"Qt wrappers left to a later garbage collection: {wrappers}"


def test_patched_canvas_attributes_do_not_keep_the_destroyed_canvas(app):  # noqa: F811
    alive, wrappers = _qt_wrappers_left_after(app, _view, _dispose, patch_draw=True)
    assert alive == [] and wrappers == [], (alive, wrappers)


def test_first_matplotlib_import_inside_a_view_leaves_no_qt_wrapper_for_gc():
    """Fresh interpreter, so the view's constructor really performs Matplotlib's first import."""
    script = textwrap.dedent("""
        import gc, sys, weakref
        sys.path[:0] = [{root!r}, {tests!r}]
        assert "matplotlib" not in sys.modules
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication
        import shiboken6
        app = QApplication.instance() or QApplication([])
        gc.collect(); gc.disable()
        from tabs.trajectory_3d_view import Trajectory3DView
        view = Trajectory3DView()
        if not view.interactive:
            print("SKIP"); sys.exit(0)
        view.resize(600, 400); view.show(); app.processEvents()
        ref = weakref.ref(view)
        view.close(); view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete); app.processEvents()
        del view
        alive = ref() is not None
        gc.set_debug(gc.DEBUG_SAVEALL); gc.collect(); gc.set_debug(0)
        wrappers = sorted({{type(o).__name__ for o in gc.garbage if isinstance(o, shiboken6.Shiboken.Object)}})
        print("RESULT", alive, wrappers)
    """).format(root=str(ROOT), tests=str(ROOT / "tests"))
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=180, env=env,
                          cwd=str(ROOT))
    lines = [line for line in done.stdout.splitlines() if line.startswith(("RESULT", "SKIP"))]
    assert done.returncode == 0 and lines, (done.returncode, done.stdout[-2000:], done.stderr[-2000:])
    if lines[-1] == "SKIP":
        pytest.skip("no interactive Matplotlib Qt canvas in this environment")
    assert lines[-1] == "RESULT False []", lines[-1]
