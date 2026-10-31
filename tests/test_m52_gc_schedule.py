"""M52 §2.1 - the GUI-thread collector defers young collections during a worker's transient heap.

``core/qt_gc.py`` (M50) collects only on the GUI thread.  M52 measured that a
collection while the Analysis snapshot worker is reading traverses its live
young objects (0.6-1.4 million at 64k synthetic rows, 60-186 ms, almost
nothing collected).  A ``hold()`` defers young collections, bounded by age and
by the young-generation size; taking a hold on the GUI thread first collects
what is due; the start-up heap can be frozen once.  Collection still runs only
on the GUI thread.
"""
from __future__ import annotations

import gc
import threading

import pytest

pytest.importorskip("PySide6")

from core import qt_gc  # noqa: E402


@pytest.fixture
def collector():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    was_enabled = gc.isenabled()
    instance = qt_gc.MainThreadGarbageCollector(None, interval_ms=3_600_000)   # ticks only when called
    instance.timer.stop()
    gc.collect()        # start every case with an empty young generation: earlier tests may leave
    #                     gc disabled with gen0 already past its threshold, which a hold would collect
    yield instance
    instance.stop()
    if not was_enabled:
        gc.disable()


def _young(collector):
    """Keep enough new tracked objects alive that generation 0 is due."""
    return [[] for _ in range(collector.threshold[0] * 3)]


def test_a_hold_defers_a_due_young_collection(collector):
    token = collector.hold()
    keep = _young(collector)
    before = list(collector.collections)
    collector.check()
    assert collector.collections == before and collector.deferred == 1
    collector.release(token)
    collector.check()
    assert collector.collections[0] == before[0] + 1, "collection must run once the hold is released"
    del keep


def test_an_old_hold_no_longer_defers(collector, monkeypatch):
    collector.hold()                          # may itself collect what is already due (boundary)
    before = collector.collections[0]
    monkeypatch.setattr(qt_gc, "DEFER_MAX_MS", 0)
    keep = _young(collector)
    collector.check()
    assert collector.collections[0] == before + 1 and collector.forced == 1 and collector.deferred == 0
    del keep


def test_a_large_young_generation_is_collected_despite_a_hold(collector, monkeypatch):
    collector.hold()                          # may itself collect what is already due (boundary)
    before = collector.collections[0]
    monkeypatch.setattr(qt_gc, "DEFER_MAX_YOUNG", collector.threshold[0] + 1)
    keep = _young(collector)
    collector.check()
    assert collector.collections[0] == before + 1 and collector.forced == 1
    del keep


def test_release_is_idempotent_and_thread_safe(collector):
    tokens = [collector.hold() for _ in range(200)]
    workers = [threading.Thread(target=lambda part=tokens[i::4]: [collector.release(t) for t in part])
               for i in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(10)
    collector.release(tokens[0])
    collector.release(None)
    assert collector.active_holds() == 0
    assert collector.stats()["active_holds"] == 0


def test_without_holds_the_m50_policy_is_unchanged(collector):
    keep = _young(collector)
    collector.check()
    assert collector.collections[0] == 1 and collector.deferred == 0 and collector.forced == 0
    assert not gc.isenabled()                 # automatic collection stays off
    del keep


def test_module_helpers_without_an_installed_policy(monkeypatch):
    monkeypatch.setattr(qt_gc, "_collector", None)
    assert qt_gc.hold() is None
    qt_gc.release(None)                       # never raises
    qt_gc.release(123)


def test_taking_a_hold_on_the_gui_thread_first_collects_what_is_due(collector):
    keep = _young(collector)                  # the previous cycle's young objects
    collector.hold()
    assert collector.collections[0] == 1 and collector.boundary_checks == 1
    del keep


def test_a_hold_taken_on_a_worker_thread_never_collects(collector):
    keep = _young(collector)
    tokens = []
    worker = threading.Thread(target=lambda: tokens.append(collector.hold()))
    worker.start()
    worker.join(10)
    assert tokens and collector.collections == [0, 0, 0] and collector.boundary_checks == 0
    del keep


def test_freezing_the_startup_heap_runs_once_on_the_gui_thread(collector, monkeypatch):
    monkeypatch.setattr(qt_gc, "_collector", collector)
    try:
        assert qt_gc.freeze_startup_heap() is True
        assert collector.frozen == gc.get_freeze_count() > 0
        assert qt_gc.freeze_startup_heap() is False          # once only
        results = []
        worker = threading.Thread(target=lambda: results.append(qt_gc.freeze_startup_heap()))
        worker.start()
        worker.join(10)
        assert results == [False]
        assert collector.stats()["frozen"] == collector.frozen
    finally:
        gc.unfreeze()


def test_freezing_never_keeps_cyclic_garbage_alive(collector, monkeypatch):
    """The full collection before gc.freeze(): frozen objects are never collected again."""
    import weakref

    class Node:
        pass

    monkeypatch.setattr(qt_gc, "_collector", collector)
    node = Node()
    node.cycle = node                         # unreachable after del, freed only by a collection
    alive = weakref.ref(node)
    del node
    try:
        assert alive() is not None            # automatic collection is off (the policy)
        assert qt_gc.freeze_startup_heap() is True
        assert alive() is None
    finally:
        gc.unfreeze()
