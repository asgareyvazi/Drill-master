"""D53: the test session collects cyclic garbage only on the main (GUI) thread, as the application does.

``app.py`` installs ``core.qt_gc`` (M50). The suite ran with automatic collection on, so a background read
(the trajectory viewer's layer catalogue in a ``ContextJobRunner`` thread) started collections that destroyed
earlier tests' pyqtgraph items and table items off the GUI thread; the next ``QApplication.allWidgets()`` at the
end of ``tests/test_m44_ui.py`` segfaulted (full local suite of the D52/M137 tree, 3 of 3 module runs).
These tests prove where collection happens now; they do not depend on a crash reproducing.
"""
import gc
import threading
import weakref

import pytest

import conftest


class _Node:
    pass


def _young_load():
    """Allocate past the generation-0 threshold on the calling thread (what a worker's query compile does)."""
    return [[[]] for _ in range(max(50_000, gc.get_threshold()[0] * 20))]


def _cycle_collected_by(make):
    """Make an unreachable reference cycle, load a worker thread, then collect on the main thread.

    Returns (name of the thread that collected the cycle before the main-thread step, or None; same after it).
    """
    seen = []
    obj = make()
    obj_ref = weakref.finalize(obj, lambda: seen.append(threading.current_thread().name))
    del obj
    keep = []
    worker = threading.Thread(target=lambda: keep.append(_young_load()), name="d53-worker")
    worker.start()
    worker.join()
    before = list(seen)
    for _ in range(3):                    # three main-thread steps reach generation 2 if the cycle was promoted
        conftest.collect_due_garbage()
        keep.append(_young_load())
    gc.collect()                          # explicit, main thread: whatever is left is reclaimed here
    assert not obj_ref.alive
    return before, list(seen)


def test_the_session_runs_without_automatic_collection_and_watches_other_threads():
    assert not gc.isenabled()
    assert conftest._gc_watch in gc.callbacks


def test_a_worker_thread_that_allocates_never_collects_a_cycle():
    def make():
        node = _Node()
        node.me = node
        return node
    before, after = _cycle_collected_by(make)
    assert before == []                   # with automatic collection the worker collected it (thread d53-worker)
    assert after == ["MainThread"]


def test_a_qt_object_in_a_cycle_is_destroyed_on_the_main_thread():
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QObject

    def make():
        obj = QObject()
        obj.me = obj                      # a Python attribute on the wrapper: a reference cycle
        return obj
    before, after = _cycle_collected_by(make)
    assert before == [] and after == ["MainThread"]


def test_collecting_from_a_worker_thread_is_refused():
    counts = []

    def attempt():
        node = _Node()
        node.me = node
        ref = weakref.ref(node)
        del node
        keep = _young_load()              # generation 0 is now due
        conftest.collect_due_garbage()
        counts.append(ref() is not None)
        del keep
    worker = threading.Thread(target=attempt)
    worker.start()
    worker.join()
    assert counts == [True]
    gc.collect()


def test_the_watchdog_counts_a_collection_that_starts_off_the_main_thread():
    before = conftest._GC_WATCH["worker_collections"]
    worker = threading.Thread(target=gc.collect, name="d53-explicit")
    worker.start()
    worker.join()
    assert conftest._GC_WATCH["worker_collections"] == before + 1


_CARRIED = {}


def test_a_cycle_left_by_a_test_with_generation_0_due():
    node = _Node()
    node.me = node
    _CARRIED["seen"] = seen = []
    _CARRIED["finalizer"] = weakref.finalize(node, lambda: seen.append(threading.current_thread().name))
    del node
    _CARRIED["load"] = _young_load()      # still alive at teardown: generation 0 is past its threshold
    # the precondition the next test relies on: nothing collected the cycle during this test
    assert _CARRIED["finalizer"].alive and seen == []
    assert gc.get_count()[0] > gc.get_threshold()[0]


def test_is_collected_by_the_teardown_of_that_test_on_the_main_thread():
    _CARRIED.pop("load")
    assert not _CARRIED["finalizer"].alive and _CARRIED["seen"] == ["MainThread"]


@pytest.mark.interpreter_gc
def test_an_interpreter_gc_test_gets_the_default_back_for_its_duration():
    assert gc.isenabled()


def test_and_the_policy_is_restored_after_it():
    assert not gc.isenabled()


def test_a_test_that_switches_automatic_collection_back_on():
    gc.enable()                           # what test_m132/test_m50 helpers did in their ``finally`` (D53)
    assert gc.isenabled()


def test_is_caught_by_the_watchdog_and_the_policy_holds_for_the_next_test():
    assert not gc.isenabled()
    assert conftest._GC_WATCH["reenabled"][-1].endswith(
        "test_d53_gui_thread_gc.py::test_a_test_that_switches_automatic_collection_back_on")
    conftest._GC_WATCH["reenabled"].pop()  # deliberate; keep the session summary to real offenders


def test_a_nested_configure_and_unconfigure_leaves_the_session_policy_in_force():
    """``tests/test_test_process_isolation.py`` runs a fresh copy of these hooks inside the session."""
    import runpy
    from pathlib import Path
    from types import SimpleNamespace
    hooks = runpy.run_path(str(Path(conftest.__file__)))
    config = SimpleNamespace()
    hooks["pytest_configure"](config)
    hooks["pytest_unconfigure"](config)
    assert not gc.isenabled()
    assert conftest._gc_watch in gc.callbacks


def test_the_module_policy_is_the_applications_rule():
    """The session rule mirrors ``MainThreadGarbageCollector._collect_due`` (M50): same thresholds, same order."""
    import inspect
    pytest.importorskip("PySide6")
    from core import qt_gc
    app_rule = inspect.getsource(qt_gc.MainThreadGarbageCollector._collect_due)
    test_rule = inspect.getsource(conftest.collect_due_garbage)
    for line in ("if count0 > threshold[0]:", "gc.collect(0)", "if count1 > threshold[1]:", "gc.collect(1)",
                 "if count2 > threshold[2]:", "gc.collect(2)"):
        assert line in test_rule
        assert line.replace("threshold", "self.threshold") in app_rule
