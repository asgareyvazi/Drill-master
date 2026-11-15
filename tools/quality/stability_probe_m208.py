"""M208 / M209: repeat the trajectory regression files with crash and hang diagnostics, record what happened.

D63 (one SIGSEGV, exit 139, no frame) and D51 (one CI hang in ``tests/test_m132_trajectory_layers.py:199``) are
investigated separately and NOTHING is suppressed: no retry inside a run, no longer timeout, no signal handler
that turns a crash into a pass. Each iteration is an independent pytest process with

* ``-X faulthandler`` (a fatal signal prints every thread's Python stack - the frame D63 never had), and
* ``-o faulthandler_timeout=<s>`` - a *diagnostic only*: if one test runs longer than that, pytest dumps every
  thread's stack and the test keeps running (it is not stopped, so the hang would still be visible as a hang).

Every iteration is recorded (exit code, signal, duration, summary line, any ``Fatal Python error`` / ``Timeout``
dump) into the JSON written with ``--json``; ``complete`` is true only when every planned iteration finished.

Usage: python tools/quality/stability_probe_m208.py --iterations 6 --json <path>
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = ["tests/test_m132_trajectory_layers.py", "tests/test_m178_trajectory_views.py",
         "tests/test_trajectory_3d.py", "tests/test_trajectory_3d_lifecycle_m46.py"]
DUMP = re.compile(r"(Fatal Python error: .*|Timeout \(\d+:\d+:\d+\)!.*)")


def _sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def run(iterations: int, dump_after: int, out: Path) -> dict:
    env = dict(os.environ, QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"),
               DRILLMASTER_ENV="test", PYTHONFAULTHANDLER="1")
    record = {"tool": "stability_probe_m208", "sha": _sha(), "python": platform.python_version(),
              "qt_platform": env["QT_QPA_PLATFORM"], "files": FILES, "iterations_planned": iterations,
              "faulthandler_timeout_s": dump_after, "runs": [], "complete": False}
    for index in range(1, iterations + 1):
        start = time.monotonic()
        proc = subprocess.run([sys.executable, "-X", "faulthandler", "-m", "pytest", "-p", "no:cacheprovider",
                               "-q", "-W", "ignore", "-o", f"faulthandler_timeout={dump_after}", *FILES],
                              cwd=ROOT, env=env, capture_output=True, text=True)
        text = proc.stdout + proc.stderr
        summary = next((line for line in reversed(text.splitlines()) if re.search(r"\d+ (passed|failed)", line)), "")
        dumps = DUMP.findall(text)
        entry = {"iteration": index, "returncode": proc.returncode,
                 "signal": -proc.returncode if proc.returncode < 0 else None,
                 "duration_s": round(time.monotonic() - start, 1), "summary": summary.strip(), "dumps": dumps,
                 "dump_excerpt": text[text.find(dumps[0]):][:4000] if dumps else ""}
        record["runs"].append(entry)
        out.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"iteration {index}: rc={proc.returncode} {entry['duration_s']}s {summary.strip()} dumps={len(dumps)}",
              flush=True)
    record["complete"] = len(record["runs"]) == iterations
    record["crashes"] = sum(1 for r in record["runs"] if r["returncode"] < 0 or r["returncode"] == 139)
    record["hang_dumps"] = sum(1 for r in record["runs"] if any(d.startswith("Timeout") for d in r["dumps"]))
    record["failures"] = sum(1 for r in record["runs"] if r["returncode"] not in (0,))
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=6)
    parser.add_argument("--dump-after", type=int, default=120)
    parser.add_argument("--json", required=True)
    args = parser.parse_args()
    record = run(args.iterations, args.dump_after, Path(args.json))
    print(json.dumps({k: record[k] for k in ("complete", "crashes", "hang_dumps", "failures")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
