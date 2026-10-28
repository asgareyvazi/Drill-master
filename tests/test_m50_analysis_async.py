"""M50 - Analysis data revision off the GUI thread, without weakening it.

* Core: ``ev.data_revision(..., cancelled=...)`` keeps the M49 digest and
  stops on request (polled every 512 rows).
* GC policy (``core/qt_gc.py``): cyclic collection only on the GUI thread.
  M50 found and captured (native stacks) a deadlock when a collection ran on a
  worker thread and destroyed GUI objects there.
* UI: the scenarios in ``tests/m50_analysis_child.py`` run the real
  ``AnalysisWidget`` on a temporary FILE database in one isolated subprocess
  (offscreen Qt on Linux, not Windows desktop testing); each is one test here.
"""
from __future__ import annotations

import ast
import gc
import json
import os
import re
import subprocess
import sys
import threading
import weakref
from pathlib import Path

import pytest
from sqlalchemy import text

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from core import analysis_evidence as ev  # noqa: E402
from m48_synthetic import build  # noqa: E402

CHILD = HERE / "m50_analysis_child.py"
SCENARIOS = re.findall(r"^@scenario\ndef (\w+)\(", CHILD.read_text(encoding="utf-8"), re.M)


# ---- core: cancellation without changing the digest -------------------------
@pytest.fixture
def syn():
    db, ids = build()
    s = db.create_session()
    report = s.execute(text("SELECT MIN(id) FROM daily_reports WHERE well_id = :w"),
                       {"w": ids["C"]}).scalar()
    for i in range(1100):           # > 2 x 512 rows in the time-log digest
        s.execute(text("INSERT INTO time_logs_24h (report_id, time_from, time_to, duration, is_npt) "
                       "VALUES (:r, '00:00:00', '00:01:00', 0.01, 0)"), {"r": report})
    s.commit()
    s.close()
    yield db, ids
    db.engine.dispose()


def _revision(db, well_id, **kwargs):
    s = db.create_session()
    try:
        return ev.data_revision(s, well_id, **kwargs)
    finally:
        s.close()


def test_cancel_callable_does_not_change_the_digest(syn):
    db, ids = syn
    polls = []
    plain = _revision(db, ids["C"])
    polled = _revision(db, ids["C"], cancelled=lambda: polls.append(1) and False)
    assert plain == polled and plain[0] == str(ev.DATA_REVISION_VERSION)
    assert len(polls) >= 3          # once up front + every 512 time-log rows


def test_cancel_stops_the_scan_mid_table(syn):
    db, ids = syn
    polls = []

    def cancel_on_third_poll():
        polls.append(1)
        return len(polls) >= 3
    with pytest.raises(ev.RevisionCancelled):
        _revision(db, ids["C"], cancelled=cancel_on_third_poll)
    assert len(polls) == 3          # stopped at the poll that asked, not at the end


def test_cancel_before_start_reads_nothing(syn):
    db, ids = syn
    with pytest.raises(ev.RevisionCancelled):
        _revision(db, ids["C"], cancelled=lambda: True)


# ---- GC policy ---------------------------------------------------------------
@pytest.fixture
def qapp():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_gc_policy_collects_cycles_from_the_gui_thread_only(qapp):
    from core import qt_gc
    assert gc.isenabled()
    collector = qt_gc.install(qapp, interval_ms=60000)
    try:
        assert qt_gc.installed() and not gc.isenabled()
        assert qt_gc.install(qapp) is collector               # idempotent

        class Node:
            pass
        node = Node()
        node.self = node                                      # a reference cycle
        ref = weakref.ref(node)
        del node
        keep = [[] for _ in range(collector.threshold[0] + 10)]   # pass the gen-0 threshold
        threads = []
        gc.callbacks.append(lambda phase, info: threads.append(threading.get_ident()))
        try:
            worker = threading.Thread(target=lambda: keep.append([[[]] for _ in range(50000)]))
            worker.start()
            worker.join()
            assert ref() is not None, "collected automatically (on some thread)"
            assert threads == []
            collector.check()                                 # the GUI-thread timer tick
            assert ref() is None and collector.collections[0] >= 1
            assert set(threads) == {threading.get_ident()}
            keep.clear()
        finally:
            gc.callbacks.pop()
    finally:
        qt_gc.uninstall()
    assert gc.isenabled() and not qt_gc.installed()


def test_gc_policy_refuses_a_worker_thread(qapp):
    from core import qt_gc
    errors = []

    def attempt():
        try:
            qt_gc.install(qapp)
        except RuntimeError as exc:
            errors.append(str(exc))
    worker = threading.Thread(target=attempt)
    worker.start()
    worker.join()
    assert errors and not qt_gc.installed() and gc.isenabled()


def test_application_installs_the_gc_policy_before_initialising():
    """Source contract: DrillMasterApp.__init__ installs it before initialize()
    (which can open the database and start workers)."""
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "DrillMasterApp")
    init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    calls = [ast.unparse(n.func) for n in ast.walk(init) if isinstance(n, ast.Call)]
    assert "qt_gc.install" in calls and "self.initialize" in calls
    assert calls.index("qt_gc.install") < calls.index("self.initialize")


# ---- UI scenarios (isolated subprocess) ---------------------------------------
def _env():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), env.get("PYTHONPATH", "")])
    env.pop("M50_GC_POLICY", None)
    return env


@pytest.fixture(scope="module")
def ui_results():
    pytest.importorskip("PySide6")
    pytest.importorskip("pyqtgraph")
    proc = subprocess.run([sys.executable, str(CHILD)], cwd=str(ROOT), env=_env(),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=600)
    results = {}
    for line in proc.stdout.splitlines():
        if line.startswith("M50RESULT "):
            item = json.loads(line[len("M50RESULT "):])
            results[item["name"]] = item
    if not results:
        pytest.fail(f"UI child produced no results (exit {proc.returncode}):\n{proc.stderr[-4000:]}")
    return results


def test_every_required_case_has_a_scenario():
    assert len(SCENARIOS) == 18
    for needed in ("currency_only", "timelog_code", "npt_reclassification", "same_count_and_sum",
                   "delete_and_reinsert", "well_change_mid_hash", "deselect_mid_hash",
                   "late_old_result", "revision_error", "tab_closed_with_active_worker",
                   "concurrent_edit_between_revision_and_load", "async_page_matches_synchronous",
                   "repeated_concurrent_edits", "never_computed_on_the_gui_thread",
                   "cyclic_gc_never_runs_on_a_worker_thread", "section_change_mid_hash"):
        assert any(name.startswith(needed) or needed in name for name in SCENARIOS), needed


@pytest.mark.parametrize("name", SCENARIOS)
def test_m50_analysis_scenario(ui_results, name):
    result = ui_results.get(name)
    assert result is not None, f"scenario {name} did not report (child crashed?)"
    assert result["ok"], result.get("error")
