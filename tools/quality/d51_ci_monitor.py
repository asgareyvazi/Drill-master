"""M309 (D51) monitor: scan GitHub Actions jobs of one branch for the D51 signature and classify every non-success.

Read-only. Uses ``gh api`` (authentication comes from the environment; no token is read, printed or stored).
Raw job logs are served from a host outside the sandbox allowlist, so the evidence is the jobs API (step
names, durations, conclusions) plus check-run annotations, as in M266.

Classes:
  D51_WATCHDOG   an annotation carries the faulthandler watchdog / wall-clock signature
                 ("Timeout (0:", "Fatal Python error", "Segmentation fault", "most recent call first")
  TEST_FAILURE   a failed step with ordinary test-failure annotations
  JOB_TIMEOUT    cancelled after >= 55 minutes (the 60-minute job limit; D88 class)
  SUPERSEDED     cancelled in under 15 minutes (a newer push)
  OTHER          anything else that is not success

    python tools/quality/d51_ci_monitor.py --branch arena/72010272-drill-master --since 2026-11-21 [--json out]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

REPO = "asgareyvazi/Drill-master"
WATCHDOG_MARKERS = ("Timeout (0:", "Fatal Python error", "Segmentation fault", "most recent call first")


def _gh(path: str) -> Any:
    out = subprocess.run(["gh", "api", path], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def _minutes(start: Optional[str], end: Optional[str]) -> Optional[float]:
    if not start or not end:
        return None
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return round((datetime.strptime(end, fmt) - datetime.strptime(start, fmt)).total_seconds() / 60.0, 1)


def classify(job: Dict[str, Any], annotations: List[Dict[str, Any]]) -> str:
    if job.get("conclusion") == "success":
        return "SUCCESS"
    if job.get("status") != "completed":
        return "IN_PROGRESS"
    texts = " ".join(str(a.get("message") or "") for a in annotations)
    if any(marker in texts for marker in WATCHDOG_MARKERS):
        return "D51_WATCHDOG"
    minutes = _minutes(job.get("started_at"), job.get("completed_at")) or 0.0
    if job.get("conclusion") == "cancelled":
        if "higher priority waiting request" in texts:      # the concurrency group: a newer push replaced it
            return "SUPERSEDED"
        if "exceeded the maximum execution time" in texts or minutes >= 55:
            return "JOB_TIMEOUT"
        return "SUPERSEDED" if minutes < 15 else "OTHER"
    if job.get("conclusion") == "failure" and annotations:
        return "TEST_FAILURE"
    return "OTHER"


def scan(branch: str, since: str, limit: int = 100) -> Dict[str, Any]:
    runs = _gh(f"repos/{REPO}/actions/runs?branch={branch}&per_page={min(limit, 100)}")["workflow_runs"]
    rows = []
    for run in runs:
        if run["created_at"][:10] < since:
            continue
        for job in _gh(f"repos/{REPO}/actions/runs/{run['id']}/jobs")["jobs"]:
            annotations = []
            if job.get("conclusion") not in ("success", None):
                try:
                    annotations = _gh(f"repos/{REPO}/check-runs/{job['id']}/annotations")
                except subprocess.CalledProcessError:
                    annotations = [{"message": "annotations unavailable"}]
            rows.append({"run": run["id"], "workflow": run["name"], "sha": run["head_sha"][:7],
                         "created": run["created_at"], "job": job["name"], "status": job["status"],
                         "conclusion": job.get("conclusion"),
                         "minutes": _minutes(job.get("started_at"), job.get("completed_at")),
                         "class": classify(job, annotations),
                         "annotations": [str(a.get("message") or "")[:300] for a in annotations][:5]})
    counts: Dict[str, int] = {}
    for row in rows:
        counts[row["class"]] = counts.get(row["class"], 0) + 1
    return {"branch": branch, "since": since, "jobs": rows, "counts": counts,
            "d51_recurred": counts.get("D51_WATCHDOG", 0) > 0,
            "note": "absence of D51 in this window is not a fix; it only bounds the observed recurrence rate"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--branch", required=True)
    parser.add_argument("--since", required=True, help="YYYY-MM-DD (run creation date, UTC)")
    parser.add_argument("--json", help="write the full result to this path")
    args = parser.parse_args(argv)
    result = scan(args.branch, args.since)
    for row in result["jobs"]:
        print(f"{row['class']:<13} {row['run']} {row['sha']} {row['created'][:16]} {row['job']!r} "
              f"{row['conclusion']} {row['minutes']} min")
        for message in row["annotations"]:
            print(f"      ann: {message}")
    print(f"counts: {result['counts']}  d51_recurred={result['d51_recurred']}")
    print(result["note"])
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=1, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
