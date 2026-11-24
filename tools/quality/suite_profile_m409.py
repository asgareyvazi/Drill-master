#!/usr/bin/env python3
"""M409: profile the test suite from a sharded-runner JSON (D88 input for the owner's CI decision).

Reads the ``--json`` output of ``tools/quality/run_suite_sharded.py``; ``pytest_outcome_recorder`` writes each test's
setup + call + teardown seconds. Reports, per file and per test, where the wall time goes. It also shows how a
longest-processing-time-first split into 2 or 3 groups would balance (file granularity, so that order-dependent
tests inside a file (D53) stay together).

The times are LOCAL measurements (one sandbox, no coverage instrumentation). The CI 3.12 leg runs under coverage on a
hosted runner, so only the relative shares carry over. This is decision input; it changes no workflow, and the
60 minute limit is not touched (D88 stays BLOCKED BY OWNER DECISION).

Usage: python tools/quality/suite_profile_m409.py RUN.json [--out FILE.md] [--top 25]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(path: str) -> tuple[dict, dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tests: dict = {}
    for shard in data["shards"]:
        tests.update(shard.get("durations") or {})
    return data, tests


def per_file(tests: dict) -> dict:
    files: dict = {}
    for nodeid, sec in tests.items():
        name = nodeid.split("::", 1)[0]
        files[name] = files.get(name, 0.0) + sec
    return files


def lpt(files: dict, groups: int) -> list:
    bins = [[0.0, []] for _ in range(groups)]
    for name, sec in sorted(files.items(), key=lambda kv: -kv[1]):
        target = min(bins, key=lambda b: b[0])
        target[0] += sec
        target[1].append(name)
    return bins


def report(data: dict, tests: dict, top: int) -> str:
    files = per_file(tests)
    total = sum(files.values())
    wall = sum(s.get("seconds", 0.0) for s in data["shards"])
    meta = data.get("meta", {})
    lines = ["# M409 — suite profile (D88 decision input)", "",
             f"- Source run: SHA `{meta.get('sha')}`{' (dirty tree)' if meta.get('tree_dirty') else ''}, "
             f"Python {meta.get('python_version')}, {len(data['shards'])} shard(s).",
             f"- {len(tests)} tests with a recorded duration in {len(files)} files; summed test time {total:.0f} s; "
             f"summed shard wall time {wall:.0f} s (the difference is interpreter start-up, import and collection).",
             "- LOCAL timings without coverage: only relative shares transfer to the CI 3.12 coverage leg.", "",
             f"## Top {top} files", "", "| # | File | Seconds | Share | Cumulative |", "|---|---|---|---|---|"]
    cumulative = 0.0
    for i, (name, sec) in enumerate(sorted(files.items(), key=lambda kv: -kv[1])[:top], 1):
        cumulative += sec
        lines.append(f"| {i} | `{name}` | {sec:.1f} | {100 * sec / total:.1f} % | {100 * cumulative / total:.1f} % |")
    lines += ["", f"## Top {top} tests", "", "| # | Test | Seconds |", "|---|---|---|"]
    for i, (nodeid, sec) in enumerate(sorted(tests.items(), key=lambda kv: -kv[1])[:top], 1):
        lines.append(f"| {i} | `{nodeid}` | {sec:.1f} |")
    ranked = sorted(files.values(), reverse=True)
    lines += ["", f"Concentration: the 10 slowest files carry {100 * sum(ranked[:10]) / total:.1f} % of the test time; "
              f"{sum(1 for v in ranked if v > 30)} files take more than 30 s. "
              + ("No single file dominates, so a file-level split balances well." if ranked[0] < 0.1 * total
                 else "One file dominates; a file-level split cannot balance below its share.")]
    lines += ["", "## Balance of a file-level split (longest processing time first)", "",
              "| Groups | Group seconds | Largest / ideal |", "|---|---|---|"]
    for groups in (2, 3):
        bins = lpt(files, groups)
        sizes = [b[0] for b in bins]
        lines.append(f"| {groups} | {' / '.join(f'{s:.0f}' for s in sizes)} | {max(sizes) / (total / groups):.3f} |")
    lines += ["", "Scaling the 3.12 leg's last measured duration by the largest group's share estimates a split job's "
              "duration. The owner records the decision (split the coverage leg across jobs, shard it, or keep it "
              "and accept the TIMEOUT risk). Nothing in this report changes CI."]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_json")
    parser.add_argument("--out")
    parser.add_argument("--top", type=int, default=25)
    args = parser.parse_args(argv)
    data, tests = load(args.run_json)
    if not tests:
        print("no durations in this run (recorder older than M409)", file=sys.stderr)
        return 2
    text = report(data, tests, args.top)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
