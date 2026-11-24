"""Run the whole test suite as N sequential pytest processes (memory-bounded local runs), with exact counts.

One pytest process for the whole suite reached about 3.5 GB RSS and was killed by the kernel OOM killer on a 4 GB
sandbox (M361-M400). This runner collects every ``tests/test_*.py`` file, splits the sorted list into ``--shards``
contiguous groups and runs each group in its own process, sequentially. It is a local aid only: CI still runs the
suite in one process (``verify_release.py``). Order-dependent tests (D53) may behave differently across shard
boundaries; a shard failure is reported, never hidden.

M407: every shard loads ``tools/quality/pytest_outcome_recorder.py``, which writes pytest's own per-test outcomes.
A shard is OK only when the process exit code is 0, pytest's exit status is 0, at least one test was collected,
every collected test has an outcome, there is no failed / error test and no collection error. The process exit code
alone never makes a shard OK. The text report records the source SHA (and whether the tree was dirty), the
interpreter path and version, the lock-file SHA-256, the exact command, and per shard: the file population,
collected / passed / failed / error / skipped / xfailed / xpassed counts, collection errors, duration, exit code
and the captured failure text. ``--json`` writes the same data machine-readably.

Run it with the real interpreter path (``/home/user/.venv/bin/python``), not through the in-repository ``.venv``
symlink: the release-boundary probe (``test_release_boundary_imports``) forbids repository paths on ``sys.path``.

Usage: python tools/quality/run_suite_sharded.py [--shards 6] [--out FILE] [--json FILE] [--files F ...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTCOMES = ("passed", "failed", "error", "skipped", "xfailed", "xpassed")
PYTEST_ARGS = ["-q", "-p", "no:cacheprovider", "-W", "ignore", "-rfE", "-p", "pytest_outcome_recorder"]


def shards(files, count):
    size = -(-len(files) // count)
    return [files[i:i + size] for i in range(0, len(files), size)]


def _git(*args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def provenance() -> dict:
    lock = ROOT / "requirements-lock.txt"
    status = _git("status", "--porcelain", "--untracked-files=no")
    return {
        "sha": _git("rev-parse", "HEAD"),
        "tree_dirty": bool(status) if status != "UNKNOWN" else None,
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest() if lock.exists() else None,
    }


def shard_ok(result: dict) -> bool:
    counts = result["counts"]
    return (result["exit_code"] == 0 and result.get("pytest_exitstatus") == 0 and result["collected"] > 0
            and not result["not_run"] and not result["collection_errors"]
            and counts.get("failed", 0) == 0 and counts.get("error", 0) == 0)


def run_shard(group: list[str]) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "tools" / "quality"), env.get("PYTHONPATH", "")]))
    with tempfile.TemporaryDirectory(prefix="dm-shard-") as tmp:
        out = Path(tmp) / "outcomes.json"
        env["DRILLMASTER_OUTCOME_JSON"] = str(out)
        start = time.monotonic()
        proc = subprocess.run([sys.executable, "-m", "pytest", *PYTEST_ARGS, *group], cwd=ROOT, env=env,
                              capture_output=True, text=True)
        seconds = time.monotonic() - start
        data = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    if data is None:     # pytest never reached sessionfinish: nothing is counted as run
        data = {"collected": 0, "counts": {}, "not_run": [], "failures": {}, "skipped": [], "xfailed": [],
                "xpassed": [], "pytest_exitstatus": None,
                "collection_errors": [{"nodeid": "<session>", "text": (proc.stdout + proc.stderr)[-4000:]}]}
    data.update(files=group, exit_code=proc.returncode, seconds=round(seconds, 1))
    data["ok"] = shard_ok(data)
    return data


def render(meta: dict, results: list[dict]) -> list[str]:
    lines = [f"SHA={meta['sha']}" + (" (DIRTY TREE)" if meta["tree_dirty"] else ""),
             f"python={meta['python_executable']} ({meta['python_version']})",
             f"requirements-lock.txt sha256={meta['lock_sha256']}",
             f"command={meta['command']}",
             f"{meta['file_count']} test files in {len(results)} shard(s)"]
    total = {key: 0 for key in OUTCOMES}
    collected = 0
    for index, r in enumerate(results, start=1):
        counts = ", ".join(f"{k} {r['counts'].get(k, 0)}" for k in OUTCOMES)
        lines.append(f"shard {index} ({r['files'][0]} .. {r['files'][-1]}, {len(r['files'])} files): "
                     f"{'OK' if r['ok'] else 'NOT OK'}; exit {r['exit_code']}; pytest {r['pytest_exitstatus']}; "
                     f"collected {r['collected']}; {counts}; not run {len(r['not_run'])}; "
                     f"collection errors {len(r['collection_errors'])}; {r['seconds']:.0f} s")
        lines.append("  files: " + " ".join(Path(f).name for f in r["files"]))
        for err in r["collection_errors"]:
            lines.append(f"  COLLECTION ERROR {err['nodeid']}")
        for nodeid, text in r["failures"].items():
            lines.append(f"  FAILED {nodeid}")
            lines.extend("    | " + line for line in text.strip().splitlines()[-25:])
        for kind in ("skipped", "xfailed", "xpassed"):
            lines.extend(f"  {kind.upper()} {nodeid}" for nodeid in r[kind])
        collected += r["collected"]
        for key in OUTCOMES:
            total[key] += r["counts"].get(key, 0)
    ok = all(r["ok"] for r in results)
    lines.append(f"TOTAL collected {collected}; " + ", ".join(f"{k} {total[k]}" for k in OUTCOMES)
                 + f"; {sum(r['seconds'] for r in results):.0f} s; shards {len(results)}; "
                 + ("ALL SHARDS OK" if ok else "NOT OK"))
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shards", type=int, default=6)
    parser.add_argument("--out", default=None)
    parser.add_argument("--json", default=None)
    parser.add_argument("--files", nargs="*", default=None, help="explicit test files instead of tests/test_*.py")
    args = parser.parse_args(argv)
    files = args.files or sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests").glob("test_*.py"))
    meta = provenance()
    meta.update(command=" ".join([sys.executable, *sys.argv]), file_count=len(files),
                pytest_args=PYTEST_ARGS)
    results = []
    for group in shards(files, max(1, min(args.shards, len(files)))):
        r = run_shard(group)
        results.append(r)
        print(f"shard {len(results)}: {'OK' if r['ok'] else 'NOT OK'}; collected {r['collected']}; {r['counts']}; "
              f"{r['seconds']:.0f} s", flush=True)
    lines = render(meta, results)
    if args.out:
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps({"meta": meta, "shards": results}, indent=1), encoding="utf-8")
    print(lines[-1], flush=True)
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
