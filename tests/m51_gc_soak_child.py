"""M51 §9 soak: the GUI-thread garbage-collection policy under mixed load (run by test_m51_gc_soak.py).

One isolated process with ``core.qt_gc`` installed exactly as ``DrillMasterApp``
does (``m50_analysis_child`` installs it at import).  Interleaved rounds of:
the real interactive ``Trajectory3DView`` (Qt Matplotlib canvas) opened,
drawn and disposed; real ``AnalysisWidget`` refreshes on a TEMPORARY FILE
database (revision + snapshot workers); real Knowledge Assistant questions on
the SYNTHETIC M50 corpus (keyword retrieval, ``AskWorker`` thread, no model);
and worker threads that build reference cycles.  The generation thresholds are
lowered so that automatic collection, were it enabled, would fire constantly.

Measured: where every collection started (the policy's own watchdog and an
independent ``gc.callbacks`` recorder); WHERE the worker-built cycles were
reclaimed (a weakref callback runs in the collecting thread); that disposed 3D
views are gone; ``gc.garbage`` stays empty.  Positive controls prove the
watchdog detects an explicit worker-thread ``gc.collect()`` and re-enabled
automatic collection.  Offscreen Qt - NOT a Windows desktop test.
Prints one ``M51SOAK {json}`` line per scenario.
"""
import gc
import json
import os
import sys
import threading
import time
import traceback
import weakref

import m50_analysis_child as base
from m50_analysis_child import app, until  # noqa: F401  (QApplication + qt_gc first)

from core import qt_gc

ROUNDS = int(os.environ.get("M51_SOAK_ROUNDS", "6"))
CYCLES = 200                      # reference cycles built per round on a worker thread
MAIN = threading.get_ident()


class Thing:
    """A plain object that can be weakly referenced."""


def _rss_mb():
    """Peak resident set size in MB (``resource`` on POSIX, ``psutil`` if present); None when unknown."""
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(peak / (2**20 if sys.platform == "darwin" else 2**10), 1)
    except ImportError:  # silent-ok: Windows has no resource module; psutil is tried next
        pass
    try:
        import psutil
        return round(psutil.Process().memory_info().peak_wset / 2**20, 1)
    except Exception:  # silent-ok: psutil is optional; the peak is then reported as unknown (None)
        return None


def _view_once(scene):
    from PySide6.QtCore import QCoreApplication, QEvent

    from tabs.trajectory_3d_view import Trajectory3DView
    view = Trajectory3DView()
    assert view.interactive, "the real Qt Matplotlib canvas is required"
    view.resize(480, 360)
    view.show()
    view.render(scene)
    app.processEvents()
    view._draw_now()
    app.processEvents()
    ref, canvas_ref = weakref.ref(view), weakref.ref(view.canvas)
    view.close()
    view.deleteLater()
    del view
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    return ref, canvas_ref


def _worker_cycles(count, reclaimed, refs):
    """Build reference cycles on a worker thread and drop them there.  The weakrefs are held OUTSIDE the
    cycles (CPython never calls the callback of a weakref that is itself garbage), so each callback runs in
    whichever thread reclaims its cycle."""
    def run():
        for _ in range(count):
            a, b = Thing(), Thing()
            a.other, b.other = b, a
            refs.append(weakref.ref(a, lambda _r: reclaimed.append(threading.get_ident())))
    thread = threading.Thread(target=run, name="m51-soak-cycles")
    thread.start()
    thread.join()


def _panel(ctx):
    from document_link_fixtures import without_session_user
    from m50_knowledge_fixtures import build_m50_corpus

    from tabs.knowledge_assistant import KnowledgeAssistantPanel

    class KeywordOnly:
        embed_model = ""
        chat_model = ""
    with without_session_user():
        build_m50_corpus(ctx.db)
    panel = KnowledgeAssistantPanel(ctx.db)
    panel._adapter = lambda: KeywordOnly()
    return panel


def _ask(panel, question):
    panel.question_edit.setPlainText(question)
    assert panel.ask()
    assert until(lambda: panel.worker is None and panel.current_state not in
                 ("searching", "retrieving", "generating"), 20000), panel.current_state
    return panel.last_answer


QUESTIONS = ("mud weight for the 16 in section of SYN-KE-05", "وزن گل در مقطع ۱۲-۱/۴ اینچ",
             "What is the kick tolerance?", "standpipe presure")


def soak(ctx):
    from core.trajectory_3d import scene_from_trajectory
    from core.well_trajectory import compose_well_trajectory
    rows = [{"id": n + 1, "md": md, "inc": inc, "azi": azi, "report_id": 1} for n, (md, inc, azi) in
            enumerate([(0.0, 0.0, 0.0), (1000.0, 30.0, 0.0), (1300.0, 30.0, 90.0), (1500.0, 30.0, 90.0)])]
    scene = scene_from_trajectory(compose_well_trajectory(rows), "m")
    collector = qt_gc._collector
    assert collector is not None and qt_gc.installed()
    start = collector.stats()
    starts = []

    def record(phase, info):
        if phase == "start":
            starts.append(threading.get_ident())
    panel = _panel(ctx)
    reclaimed, refs, views, answers = [], [], [], []
    rss_before = _rss_mb()
    old_threshold = gc.get_threshold()
    gc.callbacks.append(record)
    gc.set_threshold(50, 5, 5)
    t0 = time.perf_counter()
    try:
        for round_no in range(ROUNDS):
            views.append(_view_once(scene))
            ctx.well("ABC"[round_no % 3])
            ctx.tab.refresh_now()
            ctx.idle()
            answers.append(_ask(panel, QUESTIONS[round_no % len(QUESTIONS)]).state)
            _worker_cycles(CYCLES, reclaimed, refs)
            assert not gc.isenabled(), "automatic collection must stay disabled"
        until(lambda: len(reclaimed) >= ROUNDS * CYCLES, 10000)     # the GUI-thread timer collects
    finally:
        gc.callbacks.remove(record)
        gc.set_threshold(*old_threshold)
        panel.cleanup()
        panel.deleteLater()
        app.processEvents()
    end = collector.stats()
    worker_starts = [i for i in starts if i != MAIN]
    alive = sum(1 for ref, canvas in views if ref() is not None or canvas() is not None)
    assert worker_starts == [], f"{len(worker_starts)} collections started on worker threads"
    assert end["worker_collections"] == start["worker_collections"], end
    assert end["reenabled"] == start["reenabled"], end
    assert len(reclaimed) == ROUNDS * CYCLES, (len(reclaimed), ROUNDS * CYCLES)
    assert set(reclaimed) == {MAIN}, "worker-built cycles must be reclaimed on the GUI thread"
    assert alive == 0, f"{alive} disposed 3D views are still alive"
    assert gc.garbage == []
    assert ctx.off_main_thread(), "Analysis revisions must run on workers"
    assert all(state in ("ready", "no_evidence") for state in answers), answers
    return {"rounds": ROUNDS, "seconds": round(time.perf_counter() - t0, 2), "gui_collections": len(starts),
            "worker_collections": len(worker_starts), "cycles_reclaimed": len(reclaimed),
            "views_alive": alive, "answers": answers, "peak_rss_mb_before": rss_before, "peak_rss_mb_after": _rss_mb(),
            "watchdog": end}


def watchdog_detects_worker_collection_and_reenable(ctx):
    collector = qt_gc._collector
    before = collector.stats()
    thread = threading.Thread(target=gc.collect, name="m51-explicit-collect")
    thread.start()
    thread.join()
    after = collector.stats()
    assert after["worker_collections"] == before["worker_collections"] + 1, after
    assert "m51-explicit-collect" in after["worker_threads"], after
    gc.enable()                                       # what a misbehaving library could do
    collector.check()                                 # the next GUI-thread tick
    assert not gc.isenabled() and collector.stats()["reenabled"] == before["reenabled"] + 1
    return {"worker_collections_detected": after["worker_collections"] - before["worker_collections"],
            "reenabled_detected": 1}


SCENARIOS = [soak, watchdog_detects_worker_collection_and_reenable]


def main():
    for fn in SCENARIOS:
        ctx = None
        try:
            ctx = base.Ctx()
            detail = fn(ctx)
            result = {"name": fn.__name__, "ok": True, "detail": detail}
        except Exception:
            result = {"name": fn.__name__, "ok": False, "error": traceback.format_exc()[-3000:]}
        finally:
            if ctx is not None:
                try:
                    ctx.close()
                except Exception as exc:
                    result = {"name": fn.__name__, "ok": False, "error": f"close failed: {type(exc).__name__}"}
        print("M51SOAK " + json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
