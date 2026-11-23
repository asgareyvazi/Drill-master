"""M324: run the D63 window-release probe N times per mode on the INSTALLED PySide6 and fail on any crash.

Evaluation tooling only (isolated CI job); it never changes a pin. Exit status 0 only if every run exits 0.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--modes", default="auto,product")
    parser.add_argument("--timeout", type=int, default=300, help="seconds per probe run before it counts as a HANG")
    args = parser.parse_args(argv)
    import PySide6

    failures = 0
    results = []
    for mode in args.modes.split(","):
        for run in range(1, args.runs + 1):
            started = time.monotonic()
            try:
                proc = subprocess.run([sys.executable, str(ROOT / "tools/quality/d63_window_release_probe.py"),
                                       "--windows", "3", "--mode", mode], capture_output=True, text=True,
                                      timeout=args.timeout)
            except subprocess.TimeoutExpired as exc:          # a hang is a finding, never an unannotated failure
                out = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                err = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                proc = subprocess.CompletedProcess(exc.cmd, "HANG", out, err + f"\n(no exit after {args.timeout} s)")
            elapsed = time.monotonic() - started
            last = (proc.stdout.strip().splitlines() or [""])[-1]
            line = f"PySide6 {PySide6.__version__} {sys.platform} py{sys.version_info[0]}.{sys.version_info[1]} " \
                   f"mode={mode} run={run} rc={proc.returncode} {elapsed:.0f}s {last}"
            print(line, flush=True)
            results.append(line)
            if proc.returncode != 0:
                failures += 1
                tail = (proc.stderr or proc.stdout or "")[-1500:]
                if os.environ.get("GITHUB_ACTIONS"):          # job logs are not readable; annotations are
                    print(f"::error title=D63 probe {mode} run {run} rc={proc.returncode}::"
                          f"{_escape(line)}%0A{_escape(tail)}", flush=True)
    print(f"probe failures: {failures}")
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice title=D63 probe summary ({failures} failed)::{_escape(chr(10).join(results))}", flush=True)
    return 1 if failures else 0


def _escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


if __name__ == "__main__":
    raise SystemExit(main())
