"""M324: run the D63 window-release probe N times per mode on the INSTALLED PySide6 and fail on any crash.

Evaluation tooling only (isolated CI job); it never changes a pin. Exit status 0 only if every run exits 0.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--modes", default="auto,product")
    args = parser.parse_args(argv)
    import PySide6

    failures = 0
    for mode in args.modes.split(","):
        for run in range(1, args.runs + 1):
            proc = subprocess.run([sys.executable, str(ROOT / "tools/quality/d63_window_release_probe.py"),
                                   "--windows", "3", "--mode", mode], capture_output=True, text=True, timeout=900)
            last = (proc.stdout.strip().splitlines() or [""])[-1]
            print(f"PySide6 {PySide6.__version__} mode={mode} run={run} rc={proc.returncode} {last}", flush=True)
            failures += proc.returncode != 0
    print(f"probe failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
