"""M122 - D28: Knowledge Assistant worker lifecycle.

Root cause (source-backed, see the M121-M140 report §B/D28): the panel released
a retired worker with *check, then connect*::

    if worker.isRunning():
        self._old_workers.append(worker)
        worker.finished.connect(lambda w=worker: self._forget(w))

``CancelToken.cancel()`` aborts the streaming HTTP read, so a cancelled worker
unwinds at once and can end its thread between ``isRunning()`` (True) and
``connect`` - ``finished`` is then emitted with nobody listening, ``_forget`` never
runs and the worker stays in ``_old_workers`` for ever (the 10 s wait in
``test_generation_never_blocks_the_ui_and_cancel_works`` timed out once in a
loaded full suite).  The fix connects first and only then looks at the thread.

These tests make the race deterministic: the thread-state queries are wrapped
so the thread ends exactly inside the window (the UI thread "pre-empted" after
the query).  No timeout was raised; no retry was added.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
import warnings
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402

import test_m49_knowledge_ui as m49  # noqa: E402
from m49_fake_ollama import FakeOllama  # noqa: E402
from tabs import knowledge_assistant as kat  # noqa: E402

app = m49.app            # the M49 fixtures, reused (not their tests)
world = m49.world
KICK = m49.KICK
_wait = m49._wait
_model_ready = m49._model_ready


def _flush(app_):
    """Deliver queued calls AND deferred deletions (processEvents alone does not delete)."""
    app_.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app_.processEvents()


def _settle(app_, condition, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        _flush(app_)
        if condition():
            return True
        time.sleep(0.005)
    _flush(app_)
    return condition()


def _live_ask_workers(panel):
    return [w for w in panel.findChildren(kat.AskWorker) if w.isRunning()]


def _ask_workers(panel):
    return panel.findChildren(kat.AskWorker)


def _generating(app_, panel, fake):
    _model_ready(app_, panel, fake)
    panel.question_edit.setPlainText(KICK)
    assert panel.ask()
    assert _wait(app_, lambda: panel.current_state == "generating", 10)
    return panel.worker


def _stale_then_finish(worker):
    """Each thread-state query returns what it read, then lets the thread END before
    the caller's next statement runs - the UI thread pre-empted right after the check."""
    for name in ("isRunning", "isFinished"):
        original = getattr(worker, name)

        def query(original=original):
            value = original()
            worker.wait(10000)
            return value
        setattr(worker, name, query)


def _finish_then_read(worker):
    """The thread ends before any thread-state query is answered."""
    for name in ("isRunning", "isFinished"):
        original = getattr(worker, name)

        def query(original=original):
            worker.wait(10000)
            return original()
        setattr(worker, name, query)


# ------------------------------------------------------------- the D28 race
@pytest.mark.parametrize("inject", [_stale_then_finish, _finish_then_read], ids=["stale-then-finish", "finish-then-read"])
def test_cancel_releases_the_worker_however_its_end_interleaves_with_the_check(app, world, inject):
    _tab, panel, _ids, _db = world
    with FakeOllama(hold_after_first=20.0) as fake:
        worker = _generating(app, panel, fake)
        inject(worker)
        panel.cancel()
        assert panel.current_state == "cancelled" and panel.last_answer is None
        assert _settle(app, lambda: not panel._old_workers, 5), "a retired worker was never released (D28)"
        assert _settle(app, lambda: not _ask_workers(panel), 5)
    assert panel.last_answer is None


@pytest.mark.parametrize("inject", [_stale_then_finish, _finish_then_read], ids=["stale-then-finish", "finish-then-read"])
def test_superseding_question_releases_the_old_worker_however_it_interleaves(app, world, inject):
    _tab, panel, _ids, _db = world
    with FakeOllama(hold_after_first=20.0) as fake:
        old = _generating(app, panel, fake)
        inject(old)
        fake.release.set()                     # the new question must not be held
        assert panel.ask()                     # supersedes the running generation
        assert panel.worker is not old
        assert _settle(app, lambda: panel.worker is None and panel.current_state not in
                       ("searching", "retrieving", "generating"), 10)
        assert _settle(app, lambda: not panel._old_workers and not _ask_workers(panel), 5)
    assert panel.current_state == "ready" and panel.last_answer is not None


@pytest.mark.parametrize("inject", [_stale_then_finish, _finish_then_read], ids=["stale-then-finish", "finish-then-read"])
def test_scope_change_releases_the_old_worker_however_it_interleaves(app, world, inject):
    _tab, panel, ids, _db = world
    with FakeOllama(hold_after_first=20.0) as fake:
        worker = _generating(app, panel, fake)
        inject(worker)
        m49._set_scope(panel, m49.kr.SCOPE_DOCUMENT, ids["lessons"])
        assert panel.current_state == "stale"
        assert _settle(app, lambda: not panel._old_workers and not _ask_workers(panel), 5)
    assert panel.last_answer is None and panel.answer_view.toPlainText() == ""


@pytest.mark.parametrize("inject", [_stale_then_finish, _finish_then_read], ids=["stale-then-finish", "finish-then-read"])
def test_retired_scope_list_worker_is_released_however_it_interleaves(app, world, inject):
    """The second check-then-connect site (``_retire``) used by the scope pickers."""
    _tab, panel, _ids, _db = world
    gate = threading.Event()

    class Slow(kat.ScopeChoicesWorker):
        def run(self):
            gate.wait(10)

    worker = Slow(panel._choices_token["targets"], "documents", None, None, None, None, parent=panel)
    worker.done.connect(panel._choices_read)      # as _request_choices connects every scope-list worker
    worker.start()
    inject(worker)
    gate.set()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        panel._retire(worker)
    # CI at 4878476 counted a new "Failed to disconnect (None)" RuntimeWarning group: this test retired a
    # worker that had no receiver, which production never does.  No warning may be emitted here.
    assert not [w for w in caught if issubclass(w.category, RuntimeWarning)], [str(w.message) for w in caught]
    assert _settle(app, lambda: worker not in panel._old_workers, 5)
    assert _settle(app, lambda: not [w for w in panel.findChildren(Slow)], 5)


def test_a_completed_question_releases_its_worker(app, world):
    """Before M122 a finished AskWorker was dropped from ``self.worker`` but never
    deleted: one QThread object accumulated on the panel per question."""
    _tab, panel, _ids, _db = world
    for _ in range(5):
        m49._ask(app, panel, KICK)
        assert panel.current_state == "ready"
    assert _settle(app, lambda: not _ask_workers(panel) and not panel._old_workers, 5)


def test_completed_corpus_check_worker_is_released(app, world):
    """``_corpus_checked`` connected ``finished`` only after ``done`` arrived - usually too late."""
    _tab, panel, _ids, _db = world

    class Instant(kat.CorpusCheckWorker):
        def run(self):
            self.done.emit(self.token, None, "synthetic")

    panel._check_token += 1
    worker = Instant(panel._check_token, None, parent=panel)
    worker.done.connect(panel._corpus_checked)
    panel.check_worker = worker
    worker.start()
    assert worker.wait(5000)                   # finished is emitted before done is handled
    assert _settle(app, lambda: not panel.findChildren(Instant), 5)


# ------------------------------------------------------- stress / measured
def test_repeated_cancel_cycles_measured_and_bounded(app, world):
    """30 ask/cancel cycles: cancel latency, release time and live workers are measured;
    no worker leaks and no late result is ever shown."""
    _tab, panel, _ids, _db = world
    latencies, releases = [], []
    with FakeOllama(hold_after_first=20.0) as fake:
        _model_ready(app, panel, fake)
        panel.question_edit.setPlainText(KICK)
        for _ in range(30):
            assert panel.ask()
            assert _wait(app, lambda: panel.current_state == "generating", 10)
            t0 = time.monotonic()
            panel.cancel()
            latencies.append(time.monotonic() - t0)
            assert panel.current_state == "cancelled"
            t1 = time.monotonic()
            assert _settle(app, lambda: not panel._old_workers, 5)
            releases.append(time.monotonic() - t1)
            assert not _live_ask_workers(panel)
        assert _settle(app, lambda: not _ask_workers(panel), 5)
    assert panel.last_answer is None and panel.current_state == "cancelled"
    assert max(latencies) < 0.5                 # cancel() itself never blocks the UI thread
    print(f"M122 cancel latency max {max(latencies) * 1000:.1f} ms; "
          f"release max {max(releases) * 1000:.1f} ms; median {sorted(releases)[15] * 1000:.1f} ms")


def _cpu_load_body(app, world):
    """The full-suite failure happened under load: four CPU-bound Python threads compete
    for the GIL while 15 cancel cycles run; every retired worker is still released.

    What is asserted is the lifecycle, not the worker's speed: each cancel lands wherever the
    worker is (reading the corpus, building the index, retrieving, generating) and every retired
    worker must be released, with no result accepted after the cancel.  CI 3.13 at ``4878476``
    showed why the stage must not be a precondition: under GIL starvation the panel did not reach
    "retrieving"/"generating" within 15 s on one cycle (precondition, before any release check).
    The bound is unchanged; the stage reached is recorded, and the state history, timings and
    last error are reported if a lifecycle assertion fails.
    """
    _tab, panel, _ids, _db = world
    stop = threading.Event()
    history: list = []
    original_set_state = panel._set_state

    def recording_set_state(state, detail=""):
        history.append((time.monotonic(), state))
        original_set_state(state, detail)

    def burn():
        x = 0
        while not stop.is_set():
            x = (x * 31 + 7) % 1000003

    cycles = []
    burners = [threading.Thread(target=burn, daemon=True) for _ in range(4)]
    panel._set_state = recording_set_state
    for t in burners:
        t.start()
    try:
        with FakeOllama(hold_after_first=20.0) as fake:
            _model_ready(app, panel, fake)
            panel.question_edit.setPlainText(KICK)
            for _ in range(15):
                mark, started = len(history), time.monotonic()
                assert panel.ask()
                worker = panel.worker
                reached = _wait(app, lambda: panel.worker is None or any(
                    state in ("retrieving", "generating") for _t, state in history[mark:]), 15)
                live = worker is not None and worker.isRunning()
                panel.cancel()
                cancelled_at = time.monotonic()
                released = _settle(app, lambda: not panel._old_workers, 10)
                cycle = {"stage_seen": reached, "live_at_cancel": live, "elapsed_to_cancel": round(cancelled_at - started, 2),
                         "release_s": round(time.monotonic() - cancelled_at, 2), "states": [s for _t, s in history[mark:]],
                         "last_error": panel.last_error}
                cycles.append(cycle)
                assert released, cycles
                if live:                            # a cancelled live worker's result is never accepted later
                    assert panel.current_state == "cancelled" and panel.last_answer is None, cycles
            assert _settle(app, lambda: not _ask_workers(panel), 10), cycles
    finally:
        stop.set()
        del panel._set_state
        for t in burners:
            t.join(5)
    assert any(c["live_at_cancel"] for c in cycles), cycles   # the load case was exercised, not skipped
    print(f"M122 load: {sum(c['live_at_cancel'] for c in cycles)}/15 cancels hit a live worker, "
          f"{sum(c['stage_seen'] for c in cycles)}/15 had reached retrieval; "
          f"release max {max(c['release_s'] for c in cycles):.2f} s")



# D46: the load case runs in a fresh interpreter. CI 3.12 (the coverage leg) at 82071b2, job 127593402948,
# stopped at the 15 min watchdog inside one processEvents() of this test, with the main thread executing
# dataclasses.asdict - code the assistant does not run, i.e. work of widgets left alive by the ~130 test
# modules before it, slowed by coverage tracing and the four GIL burners. Same body, same assertions, same
# bounds; only the other modules' objects are gone. The child dumps every thread after CHILD_DUMP_S and is
# stopped at CHILD_TIMEOUT_S (both inside the 900 s job watchdog), and the dump is put in the failure.
CHILD_DUMP_S = 600       # faulthandler dump in the child (pytest faulthandler_timeout)
CHILD_TIMEOUT_S = 720    # the child is stopped here; its output so far is reported


def _tail(text, lines=120):
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    return "\n".join((text or "").splitlines()[-lines:])


def test_cancel_under_cpu_load_releases_every_worker():
    tests_dir = Path(__file__).resolve().parent
    root = tests_dir.parent
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join([str(tests_dir), str(root)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH")
                                                                       else []))
    command = [sys.executable, "-X", "faulthandler", "-m", "pytest", "-p", "no:cacheprovider", "-q", "-s",
               "-W", "ignore", "-o", f"faulthandler_timeout={CHILD_DUMP_S}", str(tests_dir / "m122_cpu_load_child.py")]
    try:
        proc = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=CHILD_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"the CPU-load cancel cycles did not finish within {CHILD_TIMEOUT_S} s\n"
                    f"stdout:\n{_tail(exc.stdout)}\nstderr:\n{_tail(exc.stderr)}")
    output = proc.stdout + proc.stderr
    # the body prints its summary only after every lifecycle assertion held (the suite's -q prints no totals)
    summary = re.search(r"^M122 load: (\d+)/15 cancels hit a live worker.*$", output, re.MULTILINE)
    assert proc.returncode == 0 and summary and int(summary.group(1)) > 0, _tail(output)
    print(summary.group(0))

def test_cancel_before_the_worker_reaches_the_model(app, world):
    """Cancel immediately after ask(): the worker may still be reading the corpus."""
    _tab, panel, _ids, _db = world
    with FakeOllama(hold_after_first=20.0, delay_before=0.3) as fake:
        _model_ready(app, panel, fake)
        panel.question_edit.setPlainText(KICK)
        for _ in range(10):
            assert panel.ask()
            panel.cancel()                      # same UI turn as ask()
            assert panel.current_state == "cancelled"
            assert _settle(app, lambda: not panel._old_workers, 5)
        _wait(app, lambda: False, 0.5)          # anything still queued is delivered now
    assert panel.last_answer is None and panel.current_state == "cancelled"
    assert _settle(app, lambda: not _ask_workers(panel), 5)


def test_out_of_order_completion_only_the_newest_is_shown(app, world):
    """An older worker that finishes AFTER a newer one is never shown (generation guard)."""
    _tab, panel, _ids, _db = world
    panel.question_edit.setPlainText(KICK)
    assert panel.ask()
    first = panel.worker
    assert panel.ask()                          # supersede at once (extractive, quick)
    second = panel.worker
    assert first is not second
    assert second.wait(10000) and first.wait(10000)
    _wait(app, lambda: False, 0.5)
    assert panel.current_state == "ready" and panel.last_answer is not None
    assert _settle(app, lambda: not panel._old_workers and not _ask_workers(panel), 5)


def test_panel_cleanup_during_generation_ends_every_thread(app, world):
    """Closing the tab (app shutdown path) while a generation is held: cleanup cancels,
    waits for the thread and returns quickly; nothing is left running."""
    tab, panel, _ids, _db = world
    with FakeOllama(hold_after_first=20.0) as fake:
        worker = _generating(app, panel, fake)
        t0 = time.monotonic()
        panel.cleanup()
        elapsed = time.monotonic() - t0
        assert worker.isFinished() and not _live_ask_workers(panel)
        assert elapsed < 3.0, elapsed
    _wait(app, lambda: False, 0.3)
    assert panel.last_answer is None


def test_cleanup_keeps_an_unfinished_worker_referenced(app, world, monkeypatch):
    """A thread that does not end within cleanup's wait is never destroyed while running:
    it is detached from the panel and held until its ``finished``."""
    _tab, panel, _ids, _db = world
    gate = threading.Event()

    class Stuck(kat.ScopeChoicesWorker):
        def run(self):
            gate.wait(10)

    worker = Stuck(0, "documents", None, None, None, None, parent=panel)
    worker.start()
    panel._old_workers.append(worker)
    monkeypatch.setattr(kat, "CLEANUP_WAIT_MS", 50)
    panel.cleanup()
    assert worker.isRunning() and worker.parent() is None     # detached, not destroyed
    from core import async_workers
    assert worker in async_workers._RELEASING
    gate.set()
    assert worker.wait(5000)
    assert _settle(app, lambda: worker not in async_workers._RELEASING, 5)
