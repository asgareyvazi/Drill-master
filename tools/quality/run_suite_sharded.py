"""Run the whole test suite as N sequential pytest processes (memory-bounded local runs).

One pytest process for the whole suite reached about 3.5 GB RSS and was killed by the kernel OOM killer on a 4 GB
sandbox (M361-M400). This runner collects every ``tests/test_*.py`` file, splits the sorted list into ``--shards``
contiguous groups and runs each group in its own process, sequentially, writing one summary line per shard and a
total. It is a local aid only: CI still runs the suite in one process (``verify_release.py``). Order-dependent
tests (D53) may behave differently across shard boundaries; a shard failure is reported, never hidden.

Usage: python tools/quality/run_suite_sharded.py [--shards 6] [--out FILE]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUMMARY = re.compile(r"^=*\s*(\d+ (?:passed|failed|error|skipped|deselected).*?) in [\d.]+s")


def shards(files, count):
    size = -(-len(files) // count)
    return [files[i:i + size] for i in range(0, len(files), size)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shards", type=int, default=6)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    files = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests").glob("test_*.py"))
    lines, worst = [f"{len(files)} test files in {args.shards} shard(s)"], 0
    for index, group in enumerate(shards(files, args.shards), start=1):
        start = time.monotonic()
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "ignore",
                               "-rfE", *group], cwd=ROOT, capture_output=True, text=True)
        tail = proc.stdout.strip().splitlines()
        found = [m.group(1) for line in tail[-5:] for m in [SUMMARY.search(line)] if m]
        failures = [line for line in tail if line.startswith(("FAILED ", "ERROR "))]
        lines.append(f"shard {index} ({group[0]} .. {group[-1]}, {len(group)} files): exit {proc.returncode}; "
                     f"{found[-1] if found else 'no summary line'}; {time.monotonic() - start:.0f} s")
        lines.extend(f"  {line}" for line in failures)
        worst = max(worst, proc.returncode)
        print(lines[-1 - len(failures)], flush=True)
        for line in failures:
            print(f"  {line}", flush=True)
    if args.out:
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return worst


if __name__ == "__main__":
    sys.exit(main())
