"""M377: CI run states are SUCCESS / SUPERSEDED / TIMEOUT / FAILURE / IN_PROGRESS and are never conflated."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ci_run_states", ROOT / "tools" / "quality" / "ci_run_states.py")
crs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crs)


def _job(name, status="completed", conclusion="success", start="2026-11-23T10:10:00Z", end="2026-11-23T10:40:00Z"):
    return {"name": name, "status": status, "conclusion": conclusion, "startedAt": start, "completedAt": end}


def _run(jobs, rid=1, created="2026-11-23T10:10:00Z", workflow="Source", branch="b"):
    return {"databaseId": rid, "workflowName": workflow, "headBranch": branch, "headSha": "3ca8b80e",
            "status": "completed", "createdAt": created, "jobs": jobs}


def test_all_green_is_success():
    assert crs.classify_run(_run([_job("3.11"), _job("3.12")]))["state"] == crs.SUCCESS


def test_one_running_leg_keeps_the_run_in_progress_not_green():
    r = crs.classify_run(_run([_job("3.11"), _job("3.12", status="in_progress", conclusion="", end=None)]))
    assert r["state"] == crs.IN_PROGRESS


def test_d88_job_timeout_reported_as_cancelled_is_timeout():
    leg = _job("3.12", conclusion="cancelled", start="2026-11-23T10:10:00Z", end="2026-11-23T11:10:00Z")
    r = crs.classify_run(_run([_job("3.11"), leg]), timeout_minutes=60)
    assert r["state"] == crs.TIMEOUT
    assert r["jobs"][1]["reason"].startswith("cancelled after 60.0 min")


def test_explicit_timed_out_is_timeout():
    assert crs.classify_job(_job("x", conclusion="timed_out"), timeout_minutes=None,
                            superseded_at=None)["state"] == crs.TIMEOUT


def test_cancel_by_a_newer_push_is_superseded():
    old = _run([_job("3.13", conclusion="cancelled", end="2026-11-23T10:20:05Z")], rid=1)
    newer = _run([], rid=2, created="2026-11-23T10:20:00Z")
    r = crs.classify_run(old, [newer], timeout_minutes=60)
    assert r["state"] == crs.SUPERSEDED


def test_newer_run_of_another_workflow_or_branch_does_not_supersede():
    old = _run([_job("3.13", conclusion="cancelled", end="2026-11-23T10:20:05Z")], rid=1)
    others = [_run([], rid=2, created="2026-11-23T10:15:00Z", workflow="Windows"),
              _run([], rid=3, created="2026-11-23T10:15:00Z", branch="other")]
    assert crs.classify_run(old, others, timeout_minutes=60)["state"] == crs.FAILURE


def test_unexplained_cancel_is_failure_never_green():
    r = crs.classify_run(_run([_job("3.11"), _job("3.13", conclusion="cancelled")]), timeout_minutes=60)
    assert r["state"] == crs.FAILURE and "not a pass" in r["jobs"][1]["reason"]


@pytest.mark.parametrize("conclusion", ["failure", "skipped", "startup_failure", "neutral", "", "action_required"])
def test_every_other_conclusion_is_failure(conclusion):
    assert crs.classify_job(_job("x", conclusion=conclusion), timeout_minutes=60,
                            superseded_at=None)["state"] == crs.FAILURE


def test_worst_job_wins():
    jobs = [_job("a"), _job("b", conclusion="cancelled", end="2026-11-23T11:10:00Z"), _job("c", conclusion="failure")]
    assert crs.classify_run(_run(jobs), timeout_minutes=60)["state"] == crs.FAILURE


def test_completed_run_without_jobs_is_not_success():
    assert crs.classify_run(_run([]))["state"] == crs.FAILURE


def test_cli_exit_code_is_zero_only_for_success(tmp_path):
    import json

    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps(_run([_job("3.11")])))
    bad.write_text(json.dumps(_run([_job("3.11", conclusion="cancelled")])))
    assert crs.main([str(good)]) == 0
    assert crs.main([str(bad), "--timeout-minutes", "60"]) == 1


def test_timeout_annotation_wins_over_stale_job_times():
    """3ca8b80 source 3.12: gh run view reported 42 min; the annotation says the 1 h limit was exceeded."""
    leg = _job("3.12", conclusion="cancelled", start="2026-11-23T10:10:15Z", end="2026-11-23T10:52:57Z")
    leg["annotations"] = ["The job has exceeded the maximum execution time of 1h0m0s", "The operation was canceled."]
    assert crs.classify_run(_run([leg]), timeout_minutes=60)["state"] == crs.TIMEOUT
