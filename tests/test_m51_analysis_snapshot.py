"""M51 - every read and derived calculation of an Analysis cycle off the GUI thread.

The scenarios in ``tests/m51_analysis_child.py`` run the real
``AnalysisWidget`` on a temporary FILE database in one isolated subprocess
(offscreen Qt on Linux, not Windows desktop testing); each is one test here.
The in-process tests below pin the worker contract: readers run against a
frozen scope that cannot reach widgets, values are plain data, and the
in-memory (synchronous) path paints identical results.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CHILD = HERE / "m51_analysis_child.py"
W12 = ROOT / "tabs" / "w12_Analysis.py"
# A healthy child writes a few KB to stderr in ~30 s.  Runaway output (e.g. an endless
# synchronous paint/read recursion logging a traceback per turn) fails the run at once
# instead of being buffered in this process until the timeout (M51: ~3.8 MB/s).
STDERR_LIMIT = 8 * 1024 * 1024


def _scenarios():
    tree = ast.parse(CHILD.read_text(encoding="utf-8"))
    return [n.name for n in tree.body if isinstance(n, ast.FunctionDef)
            and any(isinstance(d, ast.Name) and d.id == "scenario" for d in n.decorator_list)]


SCENARIOS = _scenarios()


def _env():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(HERE), env.get("PYTHONPATH", "")])
    env.pop("M50_GC_POLICY", None)
    return env


@pytest.fixture(scope="module")
def ui_results():
    pytest.importorskip("PySide6")
    pytest.importorskip("pyqtgraph")
    proc = subprocess.Popen([sys.executable, str(CHILD)], cwd=str(ROOT), env=_env(),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace")
    err = {"size": 0, "tail": "", "runaway": False}

    def drain_stderr():                 # bounded: keeps only a tail, kills on runaway output
        for chunk in iter(lambda: proc.stderr.read(65536), ""):
            err["size"] += len(chunk)
            err["tail"] = (err["tail"] + chunk)[-4000:]
            if err["size"] > STDERR_LIMIT and not err["runaway"]:
                err["runaway"] = True
                proc.kill()

    out = []
    readers = [threading.Thread(target=drain_stderr, daemon=True),
               threading.Thread(target=lambda: out.append(proc.stdout.read()), daemon=True)]
    for reader in readers:
        reader.start()
    try:
        proc.wait(timeout=900)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        pytest.fail(f"UI child timed out after 900 s:\n{err['tail']}")
    finally:
        for reader in readers:
            reader.join(10)
        proc.stdout.close()
        proc.stderr.close()
    stdout = "".join(out)
    if err["runaway"]:
        pytest.fail(f"UI child wrote more than {STDERR_LIMIT} bytes to stderr (runaway errors); "
                    f"killed:\n{err['tail']}")
    results = {}
    for line in stdout.splitlines():
        if line.startswith("M51RESULT "):
            item = json.loads(line[len("M51RESULT "):])
            results[item["name"]] = item
    if not results:
        pytest.fail(f"UI child produced no results (exit {proc.returncode}):\n{err['tail']}")
    return results


def test_every_required_case_has_a_scenario():
    assert len(SCENARIOS) == 12
    for needed in ("no_gui_thread_sql", "plain_python", "equals_synchronous", "reader_error",
                   "analytics_input_error", "db_edit_while_worker_reads", "refresh_during_snapshot",
                   "auto_tick_during_snapshot", "rapid_scope_changes", "view_change_during_snapshot",
                   "close_while_reader_runs", "fails_closed"):
        assert any(needed in name for name in SCENARIOS), needed


@pytest.mark.parametrize("name", SCENARIOS)
def test_m51_analysis_scenario(ui_results, name):
    result = ui_results.get(name)
    assert result is not None, f"scenario {name} did not report (child crashed?)"
    assert result["ok"], result.get("error")


# ---- static contract -------------------------------------------------------------
def _method_source(name):
    tree = ast.parse(W12.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AnalysisWidget")
    return next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)


@pytest.mark.parametrize("painter", ["update_plan_variance", "update_intelligence", "update_data_quality",
                                     "update_scope_indicator", "load_milestones_data",
                                     "run_advanced_analysis", "analyze_cost", "analyze_risk",
                                     "analyze_npt_forecasting", "analyze_rop_prediction"])
def test_painters_do_not_open_sessions_or_call_services(painter):
    """Painters take values from the snapshot/cache; reads live in module readers."""
    source = ast.unparse(_method_source(painter))
    for forbidden in ("create_session(", ".analyze_well(", ".summary(", "get_actual_vs_plan(",
                      "get_wellbores_by_well(", "session.query(", "load_npt_inputs("):
        assert forbidden not in source, (painter, forbidden)


def test_paint_cycle_includes_every_label_read_by_the_snapshot():
    source = ast.unparse(_method_source("_paint_for_revision"))
    for step in ("update_data_quality", "update_plan_variance", "update_intelligence",
                 "update_scope_indicator", "update_analytics", "load_milestones_data", "update_evidence"):
        assert f"self.{step}" in source, step


def test_frozen_scope_exposes_only_reader_methods():
    pytest.importorskip("PySide6")
    import tabs.w12_Analysis as w12
    scope = w12._FrozenScope({"current_well_id": 1}, db=None, revision="r")
    for name in sorted(w12._READER_METHODS):
        assert callable(getattr(scope, name)), name
    for name in ("update_kpi_data", "kpi_cards", "results_text", "_set_status", "run_advanced_analysis"):
        with pytest.raises(AttributeError):
            getattr(scope, name)


def test_memo_service_returns_independent_copies():
    pytest.importorskip("PySide6")
    import tabs.w12_Analysis as w12

    class Counting:
        calls = 0

        def analyze_well(self, well_id):
            Counting.calls += 1
            return {"kpis": {"npt_hours": 1.0}}
    memo = w12._MemoService.__new__(w12._MemoService)
    memo._service, memo._memo = Counting(), {}
    first = memo.analyze_well(7)
    first["kpis"]["npt_hours"] = 99.0          # a caller mutating its copy
    assert memo.analyze_well(7) == {"kpis": {"npt_hours": 1.0}} and Counting.calls == 1


def test_prefetched_error_raises_with_the_original_kind():
    pytest.importorskip("PySide6")
    import tabs.w12_Analysis as w12
    err = w12._LoadError(ValueError("x"))
    with pytest.raises(w12._PrefetchedReadError) as info:
        w12._Prefetched(err).get()
    assert info.value.kind == "ValueError"
    assert w12._Prefetched({"a": 1}).get() == {"a": 1}
