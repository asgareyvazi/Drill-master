"""M309: the D51 CI monitor classifies each job from the jobs API and annotations (pure function, no network)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "d51_ci_monitor", Path(__file__).resolve().parents[1] / "tools" / "quality" / "d51_ci_monitor.py")
monitor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(monitor)


def _job(conclusion, minutes, status="completed"):
    return {"status": status, "conclusion": conclusion, "started_at": "2026-11-22T05:00:00Z",
            "completed_at": f"2026-11-22T{5 + minutes // 60:02d}:{minutes % 60:02d}:00Z"}


@pytest.mark.parametrize("job, messages, expected", [
    (_job("success", 45), [], "SUCCESS"),
    (_job(None, 0, status="in_progress"), [], "IN_PROGRESS"),
    (_job("failure", 42), ["test_m122::test_cancel - AssertionError: child exit 1; Timeout (0:10:00)! Thread 0x7"],
     "D51_WATCHDOG"),
    (_job("failure", 40), ["Fatal Python error: Segmentation fault"], "D51_WATCHDOG"),
    (_job("failure", 45), ["tests.test_m75::test_engine_inventory_document_is_current - AssertionError"],
     "TEST_FAILURE"),
    (_job("cancelled", 60), ["The job has exceeded the maximum execution time of 1h0m0s"], "JOB_TIMEOUT"),
    (_job("cancelled", 47), ["Canceling since a higher priority waiting request for source-gate exists"],
     "SUPERSEDED"),
    (_job("cancelled", 7), ["The operation was canceled."], "SUPERSEDED"),
    (_job("cancelled", 30), ["The operation was canceled."], "OTHER"),
    (_job("failure", 3), [], "OTHER"),
])
def test_classification(job, messages, expected):
    assert monitor.classify(job, [{"message": m} for m in messages]) == expected


def test_absence_is_never_reported_as_a_fix(monkeypatch):
    calls = {"repos/asgareyvazi/Drill-master/actions/runs?branch=b&per_page=100": {"workflow_runs": [
        {"id": 1, "name": "Source release gate", "head_sha": "abcdef0123", "created_at": "2026-11-22T05:00:00Z"}]},
             "repos/asgareyvazi/Drill-master/actions/runs/1/jobs": {"jobs": [
                 {"id": 9, "name": "source (3.12)", **_job("success", 45)}]}}
    monkeypatch.setattr(monitor, "_gh", lambda path: calls[path])
    result = monitor.scan("b", "2026-11-22")
    assert result["d51_recurred"] is False and result["counts"] == {"SUCCESS": 1}
    assert "not a fix" in result["note"]
