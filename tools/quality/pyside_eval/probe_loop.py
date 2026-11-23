"""M324: run the D63 window-release probe N times per mode on the INSTALLED PySide6 and fail on any crash.

Evaluation tooling only (isolated CI job); it never changes a pin. Exit status 0 only if every run exits 0.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
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
    parser.add_argument("--native-dump", action="store_true",
                        help="D51: on a HANG attach gdb to the stuck probe and keep every thread's native stack "
                             "before it is killed (needs gdb and ptrace permission)")
    args = parser.parse_args(argv)
    import PySide6

    failures = 0
    results = []
    for mode in args.modes.split(","):
        for run in range(1, args.runs + 1):
            started = time.monotonic()
            command = [sys.executable, str(ROOT / "tools/quality/d63_window_release_probe.py"),
                       "--windows", "3", "--mode", mode,
                       # dump every thread's stack before the hard timeout so a hang names its frame
                       "--hang-dump", str(max((args.timeout - 30) // 2, 5)),
                       # D51: a pure-Python heartbeat; it stops printing if one thread holds the GIL
                       "--heartbeat", str(max(args.timeout // 10, 2))]
            proc, native = run_probe(command, args.timeout, args.native_dump)
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
                    if native:                                # separate quota: warnings, 4096 characters each
                        print(f"::warning title=D63 native stacks {mode} run {run}::{_escape(native)}", flush=True)
                elif native:
                    print(native, flush=True)
    print(f"probe failures: {failures}")
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice title=D63 probe summary ({failures} failed)::{_escape(chr(10).join(results))}", flush=True)
    return 1 if failures else 0


def run_probe(command, timeout: int, native_dump: bool):
    """Run one probe; on a HANG optionally take native stacks with gdb, then kill it.

    Returns ``(CompletedProcess, native_report)``; ``returncode`` is ``"HANG"`` when the probe did not exit in time
    (a hang is a finding, never an unannotated failure)."""
    child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        out, err = child.communicate(timeout=timeout)
        return subprocess.CompletedProcess(command, child.returncode, out, err), ""
    except subprocess.TimeoutExpired:
        pass
    native = native_stacks(child.pid) if native_dump else ""
    child.kill()
    out, err = child.communicate()
    return subprocess.CompletedProcess(command, "HANG", out, err + f"\n(no exit after {timeout} s)"), native


def native_stacks(pid: int) -> str:
    """Every thread's native backtrace of ``pid`` (gdb batch mode), condensed by compact_gdb_report."""
    gdb = shutil.which("gdb")
    if gdb is None:
        return "native stacks: gdb not installed"
    try:
        result = subprocess.run([gdb, "-p", str(pid), "-batch", "-nx", "-ex", "set pagination off",
                                 "-ex", "thread apply all bt 80"], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return "native stacks: gdb did not finish in 120 s"
    text = result.stdout + "\n" + result.stderr
    if "ptrace: Operation not permitted" in text:
        return "native stacks: ptrace not permitted (set kernel.yama.ptrace_scope=0)"
    return compact_gdb_report(text)


GDB_THREAD = re.compile(r'^Thread (\d+) \(.*?(?:LWP (\d+))?\)?\s*"?([^"]*)"?\)?:?\s*$')
GDB_FRAME = re.compile(r"^#\d+\s+(?:0x[0-9a-fA-F]+ in )?(.+?)\s*\((?:.*)$")
BLOCKING = re.compile(r"mutex|futex|take_gil|RestoreThread|GILState_Ensure|AcquireThread|lock|cond_wait|wait",
                      re.IGNORECASE)


LIBC_WAIT = re.compile(r"^(__futex|__GI___futex|do_futex_wait|__new_sem_wait|___sem_clockwait|__pthread_cond|"
                       r"___pthread_cond|PyCOND_TIMEDWAIT|_PySemaphore_|syscall$)")


def compact_gdb_report(text: str, frames: int = 12, limit: int = 3900, deep: int = 2) -> str:
    """One line per thread: ``T<n> <name>: f0 < f1 < ...`` (innermost first, arguments dropped).

    Thread 1 (the main thread) and threads with a blocking frame (mutex, futex, GIL) come first. The first ``deep``
    threads keep all their frames apart from the libc wait wrappers (they are the two ends of a lock cycle); the
    others are cut to fewer frames first when the text is too long."""
    threads = []
    current = None
    for line in text.splitlines():
        line = line.rstrip()
        if line.startswith("Thread ") and "(" in line:
            match = GDB_THREAD.match(line)
            number = match.group(1) if match else line.split()[1]
            name = (match.group(3) if match else "").strip() or "?"
            current = {"n": int(number) if number.isdigit() else 0, "name": name[:20], "frames": []}
            threads.append(current)
        elif current is not None and line.startswith("#"):
            match = GDB_FRAME.match(line)
            label = match.group(1) if match else line.split(" in ")[-1]
            label = re.sub(r"<.*>", "<>", label.split(" from ")[0]).strip()[:60]
            if not current["frames"] or current["frames"][-1] != label:
                current["frames"].append(label)
    if not threads:
        return "native stacks: no threads parsed\n" + text[-1500:]

    def rank(item):
        blocking = any(BLOCKING.search(f) for f in item["frames"][:6])
        return (item["n"] != 1, not blocking, item["n"])

    threads.sort(key=rank)
    for item in threads[:deep]:
        item["frames"] = [f for f in item["frames"] if not LIBC_WAIT.search(f)] or item["frames"]
    depth = frames
    while True:
        lines = [f"native stacks: {len(threads)} thread(s)"]
        for index, item in enumerate(threads):
            keep = len(item["frames"]) if index < deep else (frames if index < 4 else depth)
            lines.append(f"T{item['n']} {item['name']}: " + " < ".join(item["frames"][:keep]))
        report = "\n".join(lines)
        if len(report) <= limit or depth <= 2:
            return report[:limit]
        depth -= 2


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
