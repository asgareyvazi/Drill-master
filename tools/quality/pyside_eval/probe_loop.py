"""M324: run the D63 window-release probe N times per mode on the INSTALLED PySide6 and fail on any crash.

Evaluation tooling only (isolated CI job); it never changes a pin. Exit status 0 only if every run exits 0.
"""
from __future__ import annotations

import argparse
import os
import re
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
                                       "--windows", "3", "--mode", mode,
                                       # dump every thread's stack before the hard timeout so a hang names its frame
                                       "--hang-dump", str(max((args.timeout - 30) // 2, 5)),
                                       # D51: a pure-Python heartbeat; it stops printing if one thread holds the GIL
                                       "--heartbeat", str(max(args.timeout // 10, 2))],
                                      capture_output=True, text=True,
                                      timeout=args.timeout)
            except subprocess.TimeoutExpired as exc:          # a hang is a finding, never an unannotated failure
                out = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                err = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                proc = subprocess.CompletedProcess(exc.cmd, "HANG", out, err + f"\n(no exit after {args.timeout} s)")
            elapsed = time.monotonic() - started
            if proc.returncode == "HANG" and "Timeout (" in (proc.stderr or ""):
                proc.returncode = "HANG (stacks dumped)"
            last = (proc.stdout.strip().splitlines() or [""])[-1]
            line = f"PySide6 {PySide6.__version__} {sys.platform} py{sys.version_info[0]}.{sys.version_info[1]} " \
                   f"mode={mode} run={run} rc={proc.returncode} {elapsed:.0f}s {last}"
            print(line, flush=True)
            results.append(line)
            if proc.returncode != 0:
                failures += 1
                if "HANG" in str(proc.returncode):            # annotations are cut at 4096 characters
                    tail = compact_hang_report(proc.stderr or "")
                else:
                    tail = (proc.stderr or proc.stdout or "")[-1500:]
                if os.environ.get("GITHUB_ACTIONS"):          # job logs are not readable; annotations are
                    print(f"::error title=D63 probe {mode} run {run} rc={proc.returncode}::"
                          f"{_escape(line)}%0A{_escape(tail)}", flush=True)
    print(f"probe failures: {failures}")
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice title=D63 probe summary ({failures} failed)::{_escape(chr(10).join(results))}", flush=True)
    return 1 if failures else 0


FRAME = re.compile(r'File "([^"]+)", line (\d+) in (\S+)')
ROLES = (("home_tab.py:", "dash-worker"), ("db_maintenance.py:", "maint"), ("async_workers.py:", "worker"),
         ("d63_window_release_probe.py:", "main"))


def thread_role(labels) -> str:
    """main / hb / dash-worker / maint / worker / other from one thread's frame labels."""
    if any(label.startswith("d63_window_release_probe.py:") and label.endswith(" run") for label in labels):
        return "hb"                                   # the heartbeat thread's loop lives in the probe file
    return next((role for key, role in ROLES if any(label.startswith(key) for label in labels)), "other")


def compact_hang_report(stderr: str, frames: int = 4, limit: int = 3600) -> str:
    """Condense faulthandler dumps and HB lines of one hung run so they fit one GitHub annotation.

    Every dump keeps, per thread, a role (main / dash-worker / maint / hb / other), the innermost ``frames`` frames
    and the first application frame. The HB lines (``--heartbeat``) are kept with the newest last; when the text is
    too long the oldest HB lines go first, then the oldest dumps.
    """
    dumps, beats = [], []
    current = None
    thread = None
    for line in stderr.splitlines():
        if line.startswith("HB "):
            beats.append(line[:400])
        elif line.startswith("Timeout ("):
            current = []
            dumps.append(current)
            thread = None
        elif current is not None and (line.startswith("Thread ") or line.startswith("Current thread ")):
            thread = {"frames": [], "app": None}
            current.append(thread)
        elif thread is not None:
            match = FRAME.search(line)
            if match:
                path, number, name = match.groups()
                label = f"{os.path.basename(path)}:{number} {name}"
                thread["frames"].append(label)
                if thread["app"] is None and "site-packages" not in path and "/lib/python" not in path \
                        and "d63_window_release_probe" not in path:
                    thread["app"] = label
    rendered = []
    for index, dump in enumerate(dumps, 1):
        lines = [f"DUMP {index}:"]
        for item in dump:
            role = thread_role(item["frames"])
            inner = " < ".join(item["frames"][:frames])
            app = f" [app {item['app']}]" if item["app"] and item["app"] not in inner else ""
            lines.append(f" {role}: {inner}{app}")
        rendered.append("\n".join(lines))
    header = f"{len(dumps)} dump(s), {len(beats)} heartbeat(s)" + ("" if beats else " - NO heartbeat printed")
    while True:
        text = "\n".join([header] + rendered + beats)
        if len(text) <= limit or (not beats and len(rendered) <= 1):
            return text[-limit:]
        if len(beats) > 2:
            beats.pop(0)
        elif len(rendered) > 1:
            rendered.pop(0)
        elif beats:
            beats.pop(0)


def _escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


if __name__ == "__main__":
    raise SystemExit(main())
