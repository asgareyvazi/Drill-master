#!/usr/bin/env python3
"""M377 — classify GitHub Actions runs and jobs into exactly five states, never conflating them.

    SUCCESS      completed, conclusion success
    IN_PROGRESS  queued / in_progress / waiting (no conclusion yet) — never counted as green
    SUPERSEDED   cancelled AND a newer run of the same workflow on the same branch was created before the cancel
                 (a push cancels in-flight runs via the workflow's concurrency group)
    TIMEOUT      conclusion timed_out, an annotation "exceeded the maximum execution time", or cancelled after running for at least the job's timeout-minutes
                 (GitHub reports a job-level timeout as "cancelled"; D88 is this case on the 3.12 coverage leg)
    FAILURE      everything else: failure, startup_failure, action_required, skipped, neutral, stale, and a cancel
                 that is neither superseded nor a timeout. A skipped or cancelled job is never a pass.

A run's state is the worst of its jobs (FAILURE > TIMEOUT > SUPERSEDED > IN_PROGRESS > SUCCESS), so one green leg
never makes a run green. The classification is evidence bookkeeping only: it does not say WHY a job failed (D51 /
M266 / D88 stay separate defects with their own records).

Usage::

    gh run view <id> --json databaseId,workflowName,headBranch,headSha,status,conclusion,createdAt,jobs > run.json
    python tools/quality/ci_run_states.py run.json [--newer newer_runs.json] [--timeout-minutes 60]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional

SUCCESS, IN_PROGRESS, SUPERSEDED, TIMEOUT, FAILURE = "SUCCESS", "IN_PROGRESS", "SUPERSEDED", "TIMEOUT", "FAILURE"
STATES = (SUCCESS, IN_PROGRESS, SUPERSEDED, TIMEOUT, FAILURE)
_RANK = {SUCCESS: 0, IN_PROGRESS: 1, SUPERSEDED: 2, TIMEOUT: 3, FAILURE: 4}
TIMEOUT_SLACK_S = 60.0          # a cancel within one minute of the limit is the limit
TIMEOUT_ANNOTATION = "exceeded the maximum execution time"


def _time(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def classify_job(job: Mapping[str, Any], *, timeout_minutes: Optional[float],
                 superseded_at: Optional[datetime]) -> Dict[str, Any]:
    status = str(job.get("status") or "").lower()
    conclusion = str(job.get("conclusion") or "").lower()
    started, completed = _time(job.get("startedAt")), _time(job.get("completedAt"))
    duration = (completed - started).total_seconds() if started and completed else None
    out = {"name": job.get("name"), "status": status, "conclusion": conclusion or None, "duration_s": duration}
    if status != "completed":
        return {**out, "state": IN_PROGRESS, "reason": f"status {status or 'unknown'}"}
    if conclusion == "success":
        return {**out, "state": SUCCESS, "reason": "completed successfully"}
    if conclusion == "timed_out":
        return {**out, "state": TIMEOUT, "reason": "conclusion timed_out"}
    notes = " ".join(str(a) for a in job.get("annotations") or [])
    if conclusion in ("cancelled", "failure") and TIMEOUT_ANNOTATION in notes:
        return {**out, "state": TIMEOUT, "reason": "annotation: " + TIMEOUT_ANNOTATION}
    if conclusion == "cancelled":
        if timeout_minutes is not None and duration is not None and duration >= timeout_minutes * 60 - TIMEOUT_SLACK_S:
            return {**out, "state": TIMEOUT,
                    "reason": f"cancelled after {duration / 60:.1f} min ≥ timeout-minutes {timeout_minutes:g}"}
        if superseded_at is not None and (completed is None or superseded_at <= completed):
            return {**out, "state": SUPERSEDED, "reason": "cancelled after a newer run of the workflow started"}
        return {**out, "state": FAILURE, "reason": "cancelled, neither superseded nor at the timeout (not a pass)"}
    return {**out, "state": FAILURE, "reason": f"conclusion {conclusion or 'missing'} (not a pass)"}


def superseded_time(run: Mapping[str, Any], others: Iterable[Mapping[str, Any]]) -> Optional[datetime]:
    """Creation time of the first newer run of the same workflow on the same branch, if any."""
    created = _time(run.get("createdAt"))
    newer = [_time(o.get("createdAt")) for o in others
             if o.get("workflowName") == run.get("workflowName") and o.get("headBranch") == run.get("headBranch")
             and o.get("databaseId") != run.get("databaseId")]
    newer = [t for t in newer if t is not None and created is not None and t > created]
    return min(newer) if newer else None


def classify_run(run: Mapping[str, Any], others: Iterable[Mapping[str, Any]] = (), *,
                 timeout_minutes: Optional[float] = None) -> Dict[str, Any]:
    sup = superseded_time(run, others)
    jobs = [classify_job(j, timeout_minutes=timeout_minutes, superseded_at=sup) for j in run.get("jobs") or []]
    if jobs:
        state = max((j["state"] for j in jobs), key=_RANK.__getitem__)
    else:
        state = IN_PROGRESS if str(run.get("status")).lower() != "completed" else FAILURE
    return {"run": run.get("databaseId"), "workflow": run.get("workflowName"), "sha": run.get("headSha"),
            "state": state, "jobs": jobs}


def load_from_github(run_id: int, repo: str) -> Dict[str, Any]:
    """Run + jobs from the REST API (``actions/runs/{id}/jobs``) with each job's check-run annotations.

    ``gh run view --json jobs`` was observed to return a stale ``completedAt`` for a job that was still running
    (3ca8b80, source 3.12: 10:52:57 reported, 11:10:30 actual), so durations are taken from the jobs API."""
    import subprocess

    def api(path: str) -> Any:
        out = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=True, timeout=60)
        return json.loads(out.stdout)

    run = api(f"repos/{repo}/actions/runs/{run_id}")
    jobs = []
    for job in api(f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100").get("jobs", []):
        notes = api(f"repos/{repo}/check-runs/{job['id']}/annotations") if job.get("status") == "completed" else []
        jobs.append({"name": job.get("name"), "status": job.get("status"), "conclusion": job.get("conclusion"),
                     "startedAt": job.get("started_at"), "completedAt": job.get("completed_at"),
                     "annotations": [n.get("message", "") for n in notes]})
    return {"databaseId": run.get("id"), "workflowName": run.get("name"), "headBranch": run.get("head_branch"),
            "headSha": run.get("head_sha"), "status": run.get("status"), "conclusion": run.get("conclusion"),
            "createdAt": run.get("created_at"), "jobs": jobs}


def render(result: Mapping[str, Any]) -> List[str]:
    lines = [f"run {result['run']} {result['workflow']} {str(result['sha'] or '')[:7]}: {result['state']}"]
    for job in result["jobs"]:
        lines.append(f"  {job['name']}: {job['state']} — {job['reason']}")
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_json", nargs="?", help="saved run JSON (or use --github RUN_ID)")
    parser.add_argument("--github", type=int, help="fetch the run from the GitHub REST API")
    parser.add_argument("--repo", default="asgareyvazi/Drill-master")
    parser.add_argument("--newer", help="JSON list of other runs (gh run list --json ...) for SUPERSEDED")
    parser.add_argument("--timeout-minutes", type=float, default=None)
    args = parser.parse_args(argv)
    if args.github:
        run = load_from_github(args.github, args.repo)
    else:
        with open(args.run_json, encoding="utf-8") as fh:
            run = json.load(fh)
    others: List[Mapping[str, Any]] = []
    if args.newer:
        with open(args.newer, encoding="utf-8") as fh:
            others = json.load(fh)
    result = classify_run(run, others, timeout_minutes=args.timeout_minutes)
    print("\n".join(render(result)))
    return 0 if result["state"] == SUCCESS else 1


if __name__ == "__main__":
    sys.exit(main())
