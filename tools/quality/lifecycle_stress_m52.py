"""M52 lifecycle stress harness: fresh interpreters, crash evidence, orphans, memory (stdlib only).

M50/M51 left an intermittent native crash in the Qt/Matplotlib lifecycle that was never reproduced on
demand.  This harness runs the real lifecycle test modules again and again, each repetition in a NEW
interpreter with its own data root, and records what a crash needs for a root-cause analysis instead of
only a red step:

* the exit code, classified (pytest codes, Windows NTSTATUS crash codes such as 0xC0000005 access
  violation, POSIX signals) - a native death is never folded into "test failure";
* the identity of the test that was running (the ``DRILLMASTER-TEST-START`` breadcrumb written by
  tests/conftest.py) and the faulthandler stack (``Fatal Python error`` / ``Windows fatal exception``);
  ``faulthandler_timeout`` dumps every thread's stack if a repetition hangs;
* new crash dumps in ``--dump-dir`` (Windows Error Reporting LocalDumps, configured by the workflow);
* processes left alive after the repetition exited (Windows: a Job Object holding the pytest process and
  its children; POSIX: the repetition's own process group).  Survivors are recorded, killed and fail
  the repetition;
* the peak memory of the pytest process, and the trend over the repetitions.

The verdict is FAIL on any non-zero exit, timeout, orphan or new dump.  Nothing is skipped, deselected or
suppressed; the harness adds observation only.  It is a stress and evidence tool: a run without a crash is
not proof that the crash is gone.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
BREADCRUMB = "DRILLMASTER-TEST-START "
PYTEST_CODES = {0: "pytest: all tests passed", 1: "pytest: tests failed", 2: "pytest: interrupted",
                3: "pytest: internal error", 4: "pytest: usage error", 5: "pytest: no tests collected"}
NTSTATUS = {0xC0000005: "access violation", 0xC0000409: "stack buffer overrun / fail-fast",
            0xC0000374: "heap corruption", 0xC00000FD: "stack overflow", 0x80000003: "breakpoint",
            0xE06D7363: "unhandled C++ exception", 0xC0000135: "DLL not found",
            0xC000013A: "terminated by Ctrl+C", 0xC0000142: "DLL initialisation failed"}


def classify_exit(code: Optional[int], timed_out: bool = False) -> dict:
    """Name an exit code; ``native_crash`` is True only for a process death outside pytest's own codes."""
    if timed_out:
        return {"kind": "timeout", "native_crash": False, "text": "killed after the repetition timeout"}
    if code is None:
        return {"kind": "unknown", "native_crash": False, "text": "no exit code"}
    if code in PYTEST_CODES:
        return {"kind": "pytest", "native_crash": False, "text": PYTEST_CODES[code]}
    if -64 <= code < 0:                          # POSIX signal; a signed NTSTATUS is far below -64
        try:
            name = signal.Signals(-code).name
        except ValueError:
            name = f"signal {-code}"
        return {"kind": "signal", "native_crash": True, "text": f"killed by {name}"}
    unsigned = code & 0xFFFFFFFF
    if unsigned in NTSTATUS or unsigned >= 0xC0000000:
        return {"kind": "ntstatus", "native_crash": True,
                "text": f"0x{unsigned:08X} {NTSTATUS.get(unsigned, 'NTSTATUS error')}"}
    return {"kind": "other", "native_crash": False, "text": f"exit code {code}"}


def parse_log(text: str, stack_lines: int = 40) -> dict:
    """Last test started and the faulthandler block(s); the log holds test ids and code paths only."""
    started = [line[len(BREADCRUMB):].strip() for line in text.splitlines() if line.startswith(BREADCRUMB)]
    lines = text.splitlines()
    fatal: list[str] = []
    for index, line in enumerate(lines):
        if line.startswith(("Fatal Python error", "Windows fatal exception", "Timeout (0:")):
            fatal = lines[index:index + stack_lines]
            break
    return {"tests_started": len(started), "last_test_started": started[-1] if started else None,
            "fatal_stack": fatal}


def junit_totals(path: Path) -> Optional[dict]:
    if not path.is_file():
        return None
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return {"unreadable": str(exc)}
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    keys = ("tests", "failures", "errors", "skipped")
    return {key: sum(int(suite.get(key, 0) or 0) for suite in suites) for key in keys}


# ---- process tree: Windows Job Object / POSIX process group --------------------------------------------
class _Tree:
    """Tracks the pytest process and everything it starts, so that survivors can be found and killed."""

    def __init__(self, proc: subprocess.Popen):
        self.proc, self.job, self.error = proc, None, None
        if os.name == "nt":
            try:
                import ctypes
                k32 = ctypes.WinDLL("kernel32", use_last_error=True)
                k32.CreateJobObjectW.restype = ctypes.c_void_p
                k32.CreateJobObjectW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
                k32.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
                job = k32.CreateJobObjectW(None, None)
                if not job:
                    raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
                if not k32.AssignProcessToJobObject(job, int(proc._handle)):
                    raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
                self.job, self._k32, self._ct = job, k32, ctypes
            except (OSError, AttributeError, ValueError) as exc:
                self.error = f"job object unavailable: {exc}"

    def survivors(self) -> Optional[list[dict]]:
        """Processes of this repetition still alive (None if this cannot be determined)."""
        if os.name == "nt":
            if self.job is None:
                return None
            ct = self._ct

            class _List(ct.Structure):
                _fields_ = [("assigned", ct.c_ulong), ("listed", ct.c_ulong), ("ids", ct.c_size_t * 256)]
            info = _List()
            self._k32.QueryInformationJobObject.argtypes = (ct.c_void_p, ct.c_int, ct.c_void_p, ct.c_ulong,
                                                            ct.c_void_p)
            if not self._k32.QueryInformationJobObject(self.job, 3, ct.byref(info), ct.sizeof(info), None):
                self.error = f"QueryInformationJobObject failed ({ct.get_last_error()})"
                return None
            return [{"pid": int(info.ids[i])} for i in range(info.listed)]
        if not Path("/proc").is_dir():
            self.error = "no /proc: survivors cannot be listed on this platform"
            return None
        pgid = self.proc.pid                         # start_new_session=True: own process group
        found = []
        for entry in Path("/proc").glob("[0-9]*"):
            try:
                stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
                fields = stat[stat.rindex(")") + 2:].split()
                if int(fields[2]) == pgid and fields[0] != "Z":
                    found.append({"pid": int(entry.name), "name": stat[stat.index("(") + 1:stat.rindex(")")]})
            except (OSError, ValueError, IndexError):
                continue                             # silent-ok: the process ended while being read
        return found

    def kill(self) -> None:
        if os.name == "nt":
            if self.job is not None:
                self._k32.TerminateJobObject.argtypes = (self._ct.c_void_p, self._ct.c_uint)
                self._k32.TerminateJobObject(self.job, 1)
            else:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True, check=False)
            return
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            return

    def peak_memory_mb(self) -> Optional[float]:
        if os.name != "nt":
            return None                              # POSIX: measured with wait4 by the caller
        try:
            ct = self._ct if self.job is not None else __import__("ctypes")

            class _Counters(ct.Structure):
                _fields_ = [("cb", ct.c_ulong), ("PageFaultCount", ct.c_ulong)] + [
                    (name, ct.c_size_t) for name in (
                        "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                        "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage",
                        "PeakPagefileUsage")]
            counters = _Counters()
            counters.cb = ct.sizeof(counters)
            k32 = ct.WinDLL("kernel32", use_last_error=True)
            k32.K32GetProcessMemoryInfo.argtypes = (ct.c_void_p, ct.c_void_p, ct.c_ulong)
            if k32.K32GetProcessMemoryInfo(int(self.proc._handle), ct.byref(counters), counters.cb):
                return round(counters.PeakWorkingSetSize / 2**20, 1)
        except (OSError, AttributeError, ValueError) as exc:
            self.error = (self.error or "") + f" memory not measured: {exc}"
        return None


@dataclass
class Repetition:
    number: int
    exit_code: Optional[int] = None
    classification: dict = field(default_factory=dict)
    seconds: float = 0.0
    peak_memory_mb: Optional[float] = None
    junit: Optional[dict] = None
    log: dict = field(default_factory=dict)
    orphans: Optional[list] = None
    new_dumps: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    log_file: str = ""

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.orphans and not self.new_dumps


def _dumps(folder: Optional[Path]) -> dict:
    if not folder or not folder.is_dir():
        return {}
    return {p.name: p.stat().st_size for p in folder.glob("*.dmp")}


def run_repetition(number: int, modules: list[str], work_root: Path, timeout: float,
                   dump_dir: Optional[Path] = None, extra_env: Optional[dict] = None) -> Repetition:
    rep = Repetition(number)
    root = work_root / f"repetition-{number}"
    (root / "data").mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({"DRILLMASTER_ENV": "test", "DRILLMASTER_CRASH_BREADCRUMB": "1", "PYTHONFAULTHANDLER": "1",
                "DRILLMASTER_DATA_DIR": str(root / "data"), "DRILLMASTER_DB_PATH": str(root / "data" / "acceptance.db"),
                "DRILLMASTER_LOG_DIR": str(root / "logs"), "DRILLMASTER_BACKUP_DIR": str(root / "backups")})
    env.update(extra_env or {})
    junit = root / "lifecycle.xml"
    log_path = root / "lifecycle.log"
    hang_dump = max(30, int(timeout) - 30)
    command = [sys.executable, "-X", "faulthandler", "-m", "pytest", "-ra", "-q", "-p", "no:cacheprovider",
               "-o", f"faulthandler_timeout={hang_dump}", *modules, f"--junitxml={junit}"]
    before = _dumps(dump_dir)
    started = time.monotonic()
    timed_out = False
    with open(log_path, "wb") as log:
        kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        proc = subprocess.Popen(command, cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT, **kwargs)
        tree = _Tree(proc)
        if os.name == "nt":
            try:
                rep.exit_code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                tree.kill()
                rep.exit_code = proc.wait()
            rep.peak_memory_mb = tree.peak_memory_mb()
        else:
            deadline = started + timeout
            while True:
                pid, status, usage = os.wait4(proc.pid, os.WNOHANG)
                if pid:
                    rep.exit_code = os.waitstatus_to_exitcode(status)
                    proc.returncode = rep.exit_code
                    rep.peak_memory_mb = round(usage.ru_maxrss / 1024, 1)   # Linux reports KiB
                    break
                if time.monotonic() > deadline:
                    timed_out = True
                    tree.kill()
                time.sleep(0.2)
    rep.seconds = round(time.monotonic() - started, 1)
    rep.classification = classify_exit(rep.exit_code, timed_out)
    time.sleep(2.0)                                  # let children that are shutting down finish
    survivors = tree.survivors()
    if survivors is None:
        rep.notes.append(f"orphan check NOT RUN: {tree.error}")
    else:
        rep.orphans = survivors
        if survivors:
            tree.kill()
    if tree.error and survivors is not None:
        rep.notes.append(tree.error)
    after = _dumps(dump_dir)
    rep.new_dumps = [{"file": name, "bytes": size} for name, size in after.items() if name not in before]
    text = log_path.read_text(encoding="utf-8", errors="replace")
    rep.log = parse_log(text)
    rep.junit = junit_totals(junit)
    rep.log_file = str(log_path)
    return rep


def summarise(reps: list[Repetition], modules: list[str], dump_status: str, require_orphan_check: bool) -> dict:
    memory = [r.peak_memory_mb for r in reps if r.peak_memory_mb is not None]
    orphan_unknown = [r.number for r in reps if r.orphans is None]
    failures = [r.number for r in reps if not r.passed]
    verdict = "FAIL" if failures or (require_orphan_check and orphan_unknown) else "PASS"
    return {
        "tool": "tools/quality/lifecycle_stress_m52.py",
        "platform": sys.platform, "python": sys.version.split()[0],
        "modules": modules, "repetitions": len(reps), "verdict": verdict,
        "failed_repetitions": failures,
        "native_crashes": [r.number for r in reps if r.classification.get("native_crash")],
        "timeouts": [r.number for r in reps if r.classification.get("kind") == "timeout"],
        "orphan_check_not_run": orphan_unknown,
        "crash_dumps": dump_status,
        "memory_peak_mb": {"per_repetition": memory, "first": memory[0] if memory else None,
                           "last": memory[-1] if memory else None, "max": max(memory) if memory else None},
        "results": [asdict(r) | {"passed": r.passed} for r in reps],
        "note": "Stress evidence only: a run without a crash does not prove that the intermittent crash is fixed.",
    }


def markdown(summary: dict) -> str:
    lines = [f"### M52 lifecycle stress - {summary['verdict']} ({summary['repetitions']} fresh interpreters, "
             f"{summary['platform']}, Python {summary['python']})", "",
             f"Crash dumps: {summary['crash_dumps']}", "",
             "| # | exit | classification | s | peak MB | tests (fail/err/skip) | orphans | dumps | last test started |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in summary["results"]:
        j = r["junit"] or {}
        totals = "no report" if not j or "unreadable" in j else f"{j['tests']} ({j['failures']}/{j['errors']}/{j['skipped']})"
        orphans = "NOT RUN" if r["orphans"] is None else str(len(r["orphans"]))
        last = r["log"].get("last_test_started") or "-"
        lines.append(f"| {r['number']} | {r['exit_code']} | {r['classification'].get('text')} | {r['seconds']} | "
                     f"{r['peak_memory_mb']} | {totals} | {orphans} | {len(r['new_dumps'])} | `{last}` |")
    for r in summary["results"]:
        if r["log"].get("fatal_stack"):
            lines += ["", f"Repetition {r['number']} faulthandler stack:", "```",
                      *r["log"]["fatal_stack"], "```"]
        for note in r["notes"]:
            lines.append(f"- repetition {r['number']}: {note}")
    lines += ["", summary["note"]]
    return "\n".join(lines) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("modules", nargs="+")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=900.0, help="seconds per repetition")
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--markdown-out", type=Path)
    parser.add_argument("--dump-dir", type=Path)
    parser.add_argument("--dump-status", default="NOT CONFIGURED")
    parser.add_argument("--require-orphan-check", action="store_true")
    args = parser.parse_args(argv)
    missing = [m for m in args.modules if not (ROOT / m).is_file()]
    if missing:
        parser.error(f"missing test modules: {missing}")
    reps = []
    for number in range(1, args.repetitions + 1):
        rep = run_repetition(number, args.modules, args.work_root, args.timeout, args.dump_dir)
        reps.append(rep)
        print(f"repetition {number}/{args.repetitions}: exit {rep.exit_code} ({rep.classification['text']}), "
              f"{rep.seconds} s, orphans {'NOT RUN' if rep.orphans is None else len(rep.orphans)}, "
              f"dumps {len(rep.new_dumps)}", flush=True)
    summary = summarise(reps, args.modules, args.dump_status, args.require_orphan_check)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.write_text(markdown(summary), encoding="utf-8")
    print(f"verdict: {summary['verdict']}", flush=True)
    return 0 if summary["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
