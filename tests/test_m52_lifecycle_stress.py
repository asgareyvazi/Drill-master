"""M52 lifecycle stress harness (tools/quality/lifecycle_stress_m52.py).

Synthetic one-test modules run in real fresh interpreters: a pass, a real native crash (SIGSEGV through
faulthandler), a leftover child process and a hang.  The breadcrumb hook is the repository's own
(tests/conftest.py), loaded into the synthetic conftest, so the harness is checked against the real format.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lifecycle_stress_m52", ROOT / "tools" / "quality" / "lifecycle_stress_m52.py")
stress = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = stress                 # dataclasses resolve their module by name
spec.loader.exec_module(stress)

CONFTEST = f'''
import importlib.util
_spec = importlib.util.spec_from_file_location("drillmaster_conftest", {str(ROOT / "tests" / "conftest.py")!r})
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
pytest_runtest_logstart = _mod.pytest_runtest_logstart
'''

CRASH = '''
import ctypes, faulthandler, os

def test_native_crash():
    if os.name == "nt":   # this synthetic child only: no crash dialog may block the runner
        ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    faulthandler._sigsegv()
'''


def _module(tmp_path: Path, name: str, body: str) -> str:
    folder = tmp_path / "suite"
    folder.mkdir(exist_ok=True)
    (folder / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    path = folder / f"test_{name}.py"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return str(path)


@pytest.mark.parametrize(("code", "timed_out", "kind", "native", "text"), [
    (0, False, "pytest", False, "all tests passed"),
    (1, False, "pytest", False, "tests failed"),
    (5, False, "pytest", False, "no tests collected"),
    (3221225477, False, "ntstatus", True, "0xC0000005 access violation"),
    (-1073741819, False, "ntstatus", True, "0xC0000005 access violation"),
    (0xC0000409, False, "ntstatus", True, "fail-fast"),
    (-11, False, "signal", True, "SIGSEGV"),
    (7, False, "other", False, "exit code 7"),
    (None, True, "timeout", False, "timeout"),
])
def test_exit_codes_are_classified_and_a_native_death_is_never_a_test_failure(code, timed_out, kind, native, text):
    result = stress.classify_exit(code, timed_out)
    assert result["kind"] == kind and result["native_crash"] is native and text in result["text"]


def test_the_log_parser_finds_the_active_test_and_the_fatal_stack():
    log = ("DRILLMASTER-TEST-START tests/a.py::test_one\n.\nDRILLMASTER-TEST-START tests/a.py::test_two\n"
           "Windows fatal exception: access violation\n\nCurrent thread 0x1 (most recent call first):\n"
           '  File "x.py", line 3 in f\n')
    parsed = stress.parse_log(log)
    assert parsed["tests_started"] == 2 and parsed["last_test_started"] == "tests/a.py::test_two"
    assert parsed["fatal_stack"][0] == "Windows fatal exception: access violation"
    assert any("Current thread" in line for line in parsed["fatal_stack"])
    assert stress.parse_log("all good\n") == {"tests_started": 0, "last_test_started": None, "fatal_stack": []}


def test_a_clean_repetition_passes_with_totals_memory_and_an_orphan_check(tmp_path):
    module = _module(tmp_path, "ok", "def test_ok():\n    assert 1 + 1 == 2\n")
    rep = stress.run_repetition(1, [module], tmp_path / "work", timeout=120)
    assert rep.exit_code == 0 and rep.passed, rep.log
    assert rep.junit == {"tests": 1, "failures": 0, "errors": 0, "skipped": 0}
    assert rep.log["last_test_started"].endswith("test_ok.py::test_ok")
    assert rep.orphans == [] and rep.peak_memory_mb and rep.peak_memory_mb > 5


def test_a_native_crash_is_recorded_with_the_test_that_was_running_and_its_stack(tmp_path):
    module = _module(tmp_path, "crash", CRASH)
    rep = stress.run_repetition(1, [module], tmp_path / "work", timeout=120)
    assert not rep.passed and rep.classification["native_crash"], (rep.exit_code, rep.classification)
    assert rep.log["last_test_started"].endswith("test_crash.py::test_native_crash")
    assert rep.log["fatal_stack"] and "test_crash.py" in "\n".join(rep.log["fatal_stack"])
    assert rep.junit is None                                    # the interpreter died before writing it
    summary = stress.summarise([rep], [module], "NOT CONFIGURED", require_orphan_check=True)
    assert summary["verdict"] == "FAIL" and summary["native_crashes"] == [1]
    assert "test_native_crash" in stress.markdown(summary) and "faulthandler stack" in stress.markdown(summary)


def _alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return Path(f"/proc/{pid}/stat").is_file() and ") Z " not in Path(f"/proc/{pid}/stat").read_text()


def test_a_child_left_running_is_an_orphan_that_fails_the_repetition_and_is_killed(tmp_path):
    pid_file = tmp_path / "orphan.pid"
    module = _module(tmp_path, "orphan", f'''
        import subprocess, sys
        from pathlib import Path

        def test_leaves_a_child():
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
            Path({str(pid_file)!r}).write_text(str(child.pid))
    ''')
    rep = stress.run_repetition(1, [module], tmp_path / "work", timeout=120)
    pid = int(pid_file.read_text())
    assert rep.exit_code == 0 and not rep.passed                # the tests passed; the leftover fails it
    assert pid in [o["pid"] for o in rep.orphans]
    for _ in range(50):
        if not _alive(pid):
            break
        import time
        time.sleep(0.1)
    assert not _alive(pid), "the harness must kill what it found"


def test_a_hang_is_killed_at_the_timeout_and_reported_as_such(tmp_path):
    module = _module(tmp_path, "hang", "import time\n\ndef test_hangs():\n    time.sleep(60)\n")
    rep = stress.run_repetition(1, [module], tmp_path / "work", timeout=6)
    assert rep.classification["kind"] == "timeout" and not rep.passed and rep.seconds < 40
    assert rep.log["last_test_started"].endswith("test_hang.py::test_hangs")


def test_an_unavailable_orphan_check_cannot_pass_when_it_is_required():
    rep = stress.Repetition(1, exit_code=0, classification=stress.classify_exit(0), orphans=None)
    assert stress.summarise([rep], [], "NOT CONFIGURED", require_orphan_check=False)["verdict"] == "PASS"
    assert stress.summarise([rep], [], "NOT CONFIGURED", require_orphan_check=True)["verdict"] == "FAIL"
    dumped = stress.Repetition(2, exit_code=0, classification=stress.classify_exit(0), orphans=[],
                               new_dumps=[{"file": "python.exe.1.dmp", "bytes": 1}])
    assert not dumped.passed                                    # a dump fails even a green repetition


def test_missing_modules_are_refused_before_anything_runs(tmp_path):
    with pytest.raises(SystemExit):
        stress.main(["tests/test_does_not_exist.py", "--work-root", str(tmp_path), "--json-out", str(tmp_path / "x.json")])
    assert not (tmp_path / "x.json").exists()
    assert sys.executable                                       # the harness runs the same interpreter
