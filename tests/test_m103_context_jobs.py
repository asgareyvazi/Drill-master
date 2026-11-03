"""M103: reusable background-job pattern (core.context_jobs) and its use by W12 Operational Analysis.

Real QThreads on a SYNTHETIC file database (offscreen Qt).  Gates (threading.Event) make every
interleaving deterministic: a job blocks until the test releases it, so "switch during a job",
"close during a job" and "the newer job finishes first" are reproduced exactly, not by timing.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from core import context_jobs as cj  # noqa: E402


class FakeSelection:
    """Stands in for SelectionManager: the token changes when the test 'switches' the selection."""

    def __init__(self):
        self.generation = 0

    def context_token(self):
        return (self.generation,)

    def is_current(self, token):
        return tuple(token) == self.context_token()

    def switch(self):
        self.generation += 1


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def file_db(tmp_path):
    from synthetic_operations import make_file_database
    db = make_file_database(tmp_path / "m103.db")
    yield db
    db.engine.dispose()


@pytest.fixture
def memory_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from core.database import Base, DatabaseManager
    db = DatabaseManager()
    db.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(db.engine)
    db.Session = sessionmaker(bind=db.engine, autoflush=False, autocommit=False)
    yield db
    db.engine.dispose()


def _runner(db, **kw):
    sel = FakeSelection()
    runner = cj.ContextJobRunner(db, "synthetic job", selection=sel, **kw)
    seen = {"results": [], "states": [], "messages": []}
    runner.result_ready.connect(lambda job_id, dto: seen["results"].append((job_id, dto)))
    runner.state_changed.connect(lambda state, message: (seen["states"].append(state),
                                                         seen["messages"].append(message)))
    return runner, sel, seen


def gated(value, gate: threading.Event, started: threading.Event = None, threads: list = None):
    def compute(db, params, cancel_event):
        if threads is not None:
            threads.append((threading.current_thread() is threading.main_thread(), db))
        if started is not None:
            started.set()
        assert gate.wait(10), "test gate never opened"
        cj.check_cancel(cancel_event)
        return {"value": value, "params": params}
    return compute


def _pump_until(predicate, seconds=10.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def test_result_comes_from_a_worker_thread_with_its_own_read_only_connection(app, file_db):
    runner, _sel, seen = _runner(file_db)
    gate, threads = threading.Event(), []
    gate.set()
    job = runner.start(gated("A", gate, threads=threads), {"well_id": 2})
    assert runner.state == cj.LOADING and not runner.synchronous
    assert runner.wait(10000)
    assert seen["results"] == [(job, {"value": "A", "params": {"well_id": 2}})]
    assert seen["states"] == [cj.LOADING, cj.DONE] and runner.last_duration_s is not None
    in_main, view = threads[0]
    assert in_main is False and view is not file_db                     # never the GUI thread's manager

    def write(db, params, cancel_event):
        from sqlalchemy import text
        with db.session_scope() as session:
            session.execute(text("CREATE TABLE m103_probe (x INTEGER)"))
    runner.start(write, {})
    assert runner.wait(10000)
    assert runner.state == cj.ERROR and "OperationalError" in runner.message   # mode=ro: the worker cannot write


def test_switch_during_a_job_rejects_the_result_as_stale(app, file_db):
    runner, sel, seen = _runner(file_db)
    gate, started = threading.Event(), threading.Event()
    runner.start(gated("old well", gate, started), {})
    assert started.wait(5)
    sel.switch()                                   # the user picks another well while the job runs
    gate.set()
    assert runner.wait(10000)
    assert seen["results"] == [] and runner.state == cj.STALE and runner.rejected["stale"] == 1
    assert "selection changed" in runner.message


def test_the_newer_job_wins_even_when_the_older_one_finishes_last(app, file_db):
    runner, _sel, seen = _runner(file_db)
    gate_old, gate_new, started_old = threading.Event(), threading.Event(), threading.Event()
    old = runner.start(gated("old", gate_old, started_old), {})
    assert started_old.wait(5)
    new = runner.start(gated("new", gate_new), {})
    gate_new.set()                                 # the newer job finishes first ...
    assert _pump_until(lambda: seen["results"])
    gate_old.set()                                 # ... and the older one afterwards
    assert runner.wait(10000)
    assert [job for job, _dto in seen["results"]] == [new] and new == old + 1
    assert runner.rejected["superseded"] == 1 and runner.state == cj.DONE


def test_the_newer_job_wins_when_the_older_one_finishes_first(app, file_db):
    runner, _sel, seen = _runner(file_db)
    gate_old, gate_new, started_old = threading.Event(), threading.Event(), threading.Event()
    runner.start(gated("old", gate_old, started_old), {})
    assert started_old.wait(5)
    new = runner.start(gated("new", gate_new), {})
    gate_old.set()                                 # the superseded job completes first: nothing is shown
    assert _pump_until(lambda: runner.rejected["superseded"] == 1 or runner.rejected["cancelled"] == 1)
    assert seen["results"] == [] and runner.state == cj.LOADING
    gate_new.set()
    assert runner.wait(10000)
    assert [job for job, _dto in seen["results"]] == [new]


def test_close_during_a_job_cancels_and_joins_within_the_bound(app, file_db):
    runner, _sel, seen = _runner(file_db)
    started = threading.Event()

    def cooperative(db, params, cancel_event):
        started.set()
        while True:                                # a long read that checks for cancellation between steps
            cj.check_cancel(cancel_event)
            time.sleep(0.01)
    runner.start(cooperative, {})
    assert started.wait(5)
    t0 = time.monotonic()
    assert runner.shutdown(5000) is True
    assert time.monotonic() - t0 < 5
    _pump_until(lambda: not runner._threads, 2)
    assert seen["results"] == [] and runner.current_id is None


def test_close_with_an_uncooperative_job_reports_it_and_never_shows_its_result(app, file_db, caplog):
    runner, _sel, seen = _runner(file_db)
    gate, started = threading.Event(), threading.Event()

    def stuck(db, params, cancel_event):
        started.set()
        gate.wait(10)                              # ignores cancellation
        return {"late": True}
    runner.start(stuck, {})
    assert started.wait(5)
    assert runner.shutdown(100) is False           # bounded: it does not hang the close
    assert "still running after 100 ms" in caplog.text
    gate.set()
    assert runner.wait(10000)
    assert seen["results"] == []                   # the late result is never shown


def test_cancel_discards_the_result_and_retry_reruns_the_same_snapshot(app, file_db):
    runner, _sel, seen = _runner(file_db)
    gate, started = threading.Event(), threading.Event()
    runner.start(gated("v", gate, started), {"well_id": 7, "start": "2031-07-01"})
    assert started.wait(5)
    runner.cancel()
    assert runner.state == cj.CANCELLED
    gate.set()
    assert runner.wait(10000)
    assert seen["results"] == [] and runner.state == cj.CANCELLED
    job = runner.retry()                           # same compute, same captured parameters
    assert runner.wait(10000)
    assert seen["results"] == [(job, {"value": "v", "params": {"well_id": 7, "start": "2031-07-01"}})]


def test_cancel_discards_the_result_of_a_job_that_ignores_cancellation(app, file_db):
    runner, _sel, seen = _runner(file_db)
    gate, started = threading.Event(), threading.Event()

    def deaf(db, params, cancel_event):
        started.set()
        gate.wait(10)
        return {"computed": "anyway"}              # never looks at cancel_event
    runner.start(deaf, {})
    assert started.wait(5)
    runner.cancel()
    gate.set()
    assert runner.wait(10000)
    assert seen["results"] == [] and runner.state == cj.CANCELLED and runner.rejected["cancelled"] == 1


def test_an_error_shows_the_type_only_and_retry_recovers(app, file_db):
    runner, _sel, seen = _runner(file_db)
    calls = []

    def flaky(db, params, cancel_event):
        calls.append(1)
        if len(calls) == 1:
            raise KeyError("SYN-SECRET-PATH /home/somewhere")
        return {"ok": True}
    runner.start(flaky, {})
    assert runner.wait(10000)
    assert runner.state == cj.ERROR and "KeyError" in runner.message and "SECRET" not in runner.message
    runner.retry()
    assert runner.wait(10000)
    assert runner.state == cj.DONE and seen["results"][-1][1] == {"ok": True}


def test_empty_state_and_in_memory_fallback(app, memory_db):
    runner, _sel, seen = _runner(memory_db, is_empty=lambda dto: not dto["rows"])
    runner.start(lambda db, params, cancel: {"rows": []}, {})
    assert runner.synchronous and runner.state == cj.EMPTY            # no worker on a shared connection
    assert "in-memory database: read on the GUI thread" in seen["messages"][0]
    assert seen["states"] == [cj.LOADING, cj.EMPTY] and len(seen["results"]) == 1


# ---- W12 Operational Analysis on the shared pattern ----------------------------------------------
@pytest.fixture
def oa_tab(app, file_db):
    from core.selection_manager import SelectionManager
    from document_link_fixtures import build_link_world
    from tabs.w12_Analysis import AnalysisWidget
    ids = build_link_world(file_db)
    tab = AnalysisWidget(db_manager=file_db)
    yield tab, ids
    tab.cleanup()
    SelectionManager().clear()
    tab.deleteLater()
    QApplication.processEvents()


def _select(ids, key):
    from core.selection_manager import SelectionManager
    SelectionManager().select_well(ids[key], {"id": ids[key], "name": key})


def test_oa_refresh_runs_in_the_background_and_returns_plain_dtos(oa_tab):
    tab, ids = oa_tab
    _select(ids, "alpha")
    panel = tab.operational_panel
    assert panel.refresh() is not None and panel.result is None       # nothing painted before delivery
    assert panel.cancel_btn.isEnabled()
    result = panel.wait()
    assert result is not None and "SYN-ALPHA-01" in result.scope_label
    assert panel.jobs.state == cj.DONE and not panel.jobs.synchronous and not panel.cancel_btn.isEnabled()
    from core.database import Base
    for _columns, rows in result.tables.values():
        for row in rows:
            assert not any(isinstance(value, Base) for value in row)   # DTOs only, no ORM rows


def test_oa_switch_during_the_job_shows_nothing_of_either_well(oa_tab):
    tab, ids = oa_tab
    _select(ids, "alpha")
    panel = tab.operational_panel
    panel.refresh()
    _select(ids, "twin_1")              # synchronous switch: the alpha result cannot have been delivered yet
    panel.wait()
    assert panel.result is None and all(t.rowCount() == 0 for t in panel.tables.values())
    assert panel.summary.text() == ""


def test_oa_close_during_the_job_joins_the_worker(oa_tab, monkeypatch):
    tab, ids = oa_tab
    _select(ids, "alpha")
    panel = tab.operational_panel
    import tabs.operational_analysis_panel as oap
    started = threading.Event()

    def long_analysis(db, scope, *, start=None, end=None, cancel_event=None):
        started.set()
        while True:                                 # runs until the job is cancelled
            cj.check_cancel(cancel_event)
            time.sleep(0.01)
    monkeypatch.setattr(oap.oa, "analyze", long_analysis)
    panel.refresh()
    assert started.wait(5)
    threads = list(panel.jobs._threads.values())
    tab.cleanup()                                   # tab disposal / app shutdown
    assert threads and not any(t.isRunning() for t in threads)
    QApplication.processEvents()
    assert panel.result is None


def test_oa_error_offers_retry(oa_tab, monkeypatch):
    tab, ids = oa_tab
    _select(ids, "alpha")
    panel = tab.operational_panel
    import tabs.operational_analysis_panel as oap
    real = oap.oa.analyze
    monkeypatch.setattr(oap.oa, "analyze", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("synthetic")))
    panel.refresh()
    panel.wait()
    assert panel.jobs.state == cj.ERROR and panel.retry_btn.isEnabled() and "RuntimeError" in panel.status.text()
    monkeypatch.setattr(oap.oa, "analyze", real)
    assert panel.retry() is not None
    assert panel.wait() is not None and panel.jobs.state == cj.DONE


def test_oa_cancel_points_stop_analyze(file_db):
    from core import analysis_evidence as ev
    from core import operational_analysis as oa
    from document_link_fixtures import build_link_world
    ids = build_link_world(file_db)
    event = threading.Event()
    event.set()
    with pytest.raises(cj.JobCancelled):
        oa.analyze(file_db, ev.AnalysisScope(well_id=ids["alpha"]), cancel_event=event)
    assert oa.analyze(file_db, ev.AnalysisScope(well_id=ids["alpha"]), cancel_event=threading.Event()).summary


def test_measurement_tool_runs_and_reports_budget(tmp_path):
    import json
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run([sys.executable, str(root / "tools" / "quality" / "measure_m103.py"), "--days", "20",
                           "--repeat", "1"], capture_output=True, text=True, timeout=300, cwd=root)
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = json.loads(proc.stdout)
    assert out["days"] == 20 and set(out["median_s"]) == {"operational_analysis.analyze",
                                                          "calculation_history.load_history"}
