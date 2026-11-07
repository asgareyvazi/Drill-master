"""CI failure annotations emitted by verify_release (diagnostics only)."""
from __future__ import annotations

import verify_release

JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="4">
  <testcase classname="tests.test_a" name="test_ok"/>
  <testcase classname="tests.test_a" name="test_fails[50%-x]">
    <failure message="assert 1 == 2&#10;second line">traceback text</failure>
  </testcase>
  <testcase classname="tests.test_b" name="test_errors"><error>setup line 1
RuntimeError: fixture broke</error></testcase>
  <testcase classname="tests.test_b" name="test_skipped"><skipped message="why"/></testcase>
</testsuite></testsuites>
"""


def test_annotations_name_each_failure_and_error_on_one_escaped_line(tmp_path, capsys):
    report = tmp_path / "results.xml"
    report.write_text(JUNIT, encoding="utf-8")
    assert verify_release.annotate_failures(report, {"GITHUB_ACTIONS": "true"}) == 2
    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "::error title=pytest failure::tests.test_a::test_fails[50%25-x] - assert 1 == 2 second line",
        "::error title=pytest error::tests.test_b::test_errors - RuntimeError: fixture broke",
    ]


def test_annotations_are_inert_outside_ci_or_without_a_report(tmp_path, capsys):
    report = tmp_path / "results.xml"
    report.write_text(JUNIT, encoding="utf-8")
    assert verify_release.annotate_failures(report, {}) == 0
    assert verify_release.annotate_failures(tmp_path / "missing.xml", {"GITHUB_ACTIONS": "true"}) == 0
    assert capsys.readouterr().out == ""


def test_malformed_report_is_reported_not_raised(tmp_path, capsys):
    report = tmp_path / "results.xml"
    report.write_text("<testsuites><testcase", encoding="utf-8")
    assert verify_release.annotate_failures(report, {"GITHUB_ACTIONS": "true"}) == 1
    assert capsys.readouterr().out.startswith("::error title=pytest report::")


def test_annotation_text_is_single_line_and_bounded():
    text = verify_release._annotation_text("a\r\nb%" + "x" * 500, limit=20)
    assert "\n" not in text and "\r" not in text and text.startswith("a b%25")
    assert len(text) <= 24


# ---- M124: a hung test fails the run and is named (the CI job timeout loses all captured output) ----
DUMP = """....Timeout (0:15:00)!
Thread 0x00007f0000000001 (most recent call first):
  File "/usr/lib/python3.13/threading.py", line 359 in wait
  File "/home/runner/work/Drill-master/Drill-master/core/async_workers.py", line 88 in join

Thread 0x00007f0000000000 (most recent call first):
  File "/usr/lib/python3.13/time.py", line 1 in sleep
  File "/home/runner/work/Drill-master/Drill-master/tests/helpers.py", line 12 in _wait
  File "/home/runner/work/Drill-master/Drill-master/tests/test_slow.py", line 40 in test_waits_for_ever
  File "/opt/venv/lib/python3.13/site-packages/_pytest/python.py", line 167 in pytest_pyfunc_call
  File "/opt/venv/lib/python3.13/site-packages/pluggy/_callers.py", line 103 in _multicall
"""


def test_a_watchdog_dump_names_the_test_function_frame():
    hang = verify_release.describe_hang(DUMP)
    assert "within 0:15:00" in hang
    assert "test frame: tests/test_slow.py:40 in test_waits_for_ever" in hang      # above pytest_pyfunc_call
    assert "blocked in: time.py:1 in sleep" in hang                               # top of the test's thread
    assert verify_release.describe_hang("12 passed in 3.0s") is None


def test_the_hang_threads_line_lists_every_thread_innermost_first():
    """D51: the hung test's thread is often not the cause, so every thread is listed (job logs are lost)."""
    assert verify_release.describe_hang_threads(DUMP) == (
        "2 thread(s): T1: threading.py:359 wait < core/async_workers.py:88 join | "
        "T2 (test): time.py:1 sleep < tests/helpers.py:12 _wait < tests/test_slow.py:40 test_waits_for_ever")
    assert verify_release.describe_hang_threads(DUMP, frames_per_thread=1).endswith("T2 (test): time.py:1 sleep")
    native = "Timeout (0:00:02)!\nThread 0x2 (most recent call first):\n  <no Python frame>\n" + DUMP.split("!\n", 1)[1]
    assert verify_release.describe_hang_threads(native).startswith("3 thread(s): T1: no Python frame | T2: ")
    assert verify_release.describe_hang_threads("12 passed in 3.0s") is None


def test_a_child_dump_quoted_in_a_failure_is_not_a_hang_of_this_run():
    """M134: a D46 child's dump inside the test's assertion text was annotated as "pytest hang ... process ended"."""
    quoted = "F\n" + "\n".join("E       " + line for line in DUMP.replace("....", "", 1).splitlines()) + \
             "\n1 failed, 4876 passed in 2000.0s\n"
    assert verify_release.describe_hang(quoted) is None
    assert verify_release.describe_hang_threads(quoted) is None
    assert verify_release.describe_hang(quoted + DUMP) is not None          # a real dump after it still counts


def test_a_hang_in_a_fixture_falls_back_to_the_first_test_frame():
    fixture_dump = "Timeout (0:00:02)!\nThread 0x1 (most recent call first):\n" \
                   '  File "/r/tests/conftest.py", line 9 in slow_fixture\n' \
                   '  File "/v/_pytest/fixtures.py", line 1 in call_fixture_func\n'
    assert "test frame: tests/conftest.py:9 in slow_fixture" in verify_release.describe_hang(fixture_dump)


def test_the_watchdog_ends_a_hung_test_and_the_gate_names_it(tmp_path):
    """Real pytest subprocess with the repository conftest as a plugin and a 2 s limit."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    tests_dir = Path(__file__).resolve().parent
    (tmp_path / "test_hang_probe.py").write_text(
        "import time\n\n\ndef test_quick():\n    assert True\n\n\n"
        "def test_sleeps_past_the_limit():\n    time.sleep(60)\n", encoding="utf-8")
    env = dict(os.environ, DRILLMASTER_TEST_HANG_SECONDS="2", PYTHONPATH=os.pathsep.join([str(tests_dir), str(tests_dir.parent)]))
    env.pop("PYTEST_ADDOPTS", None)
    done = subprocess.run([sys.executable, "-m", "pytest", "-p", "conftest", "-q", "-p", "no:cacheprovider",
                           str(tmp_path / "test_hang_probe.py")],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=50)
    output = done.stdout + done.stderr
    assert done.returncode != 0                                   # the run FAILS; nothing is skipped
    hang = verify_release.describe_hang(output)
    assert hang and "test_hang_probe.py:9 in test_sleeps_past_the_limit" in hang, output[-2000:]
    assert "within 0:00:02" in hang


def test_without_the_variable_no_watchdog_is_armed(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    tests_dir = Path(__file__).resolve().parent
    (tmp_path / "test_slowish.py").write_text(
        "import time\n\n\ndef test_three_seconds():\n    time.sleep(3)\n", encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(tests_dir), str(tests_dir.parent)]))
    env.pop("DRILLMASTER_TEST_HANG_SECONDS", None)
    env.pop("PYTEST_ADDOPTS", None)
    done = subprocess.run([sys.executable, "-m", "pytest", "-p", "conftest", "-q", "-p", "no:cacheprovider",
                           str(tmp_path / "test_slowish.py")],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=50)
    assert done.returncode == 0 and "Timeout (" not in done.stdout + done.stderr


def test_the_gate_arms_the_watchdog_below_the_job_timeout():
    import re
    from pathlib import Path
    workflow = (Path(verify_release.__file__).resolve().parent / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    job_minutes = int(re.search(r"timeout-minutes: (\d+)", workflow)[1])
    assert 0 < verify_release.TEST_HANG_SECONDS < job_minutes * 60 / 2       # a hang ends well before the job does


def test_the_gate_arms_the_watchdog_and_annotates_a_hang(monkeypatch, capsys):
    import subprocess
    seen = {}

    def fake_run(command, *, echo=True, cwd=None, env=None):
        if "--collect-only" in command:
            return subprocess.CompletedProcess(command, 0, "tests/test_slow.py: 1\n", "")
        seen["env"] = env
        return subprocess.CompletedProcess(command, 1, "", DUMP)

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv("DRILLMASTER_TEST_HANG_SECONDS", raising=False)
    monkeypatch.setattr(verify_release, "_run", fake_run)
    assert verify_release.run_pytest() is False
    assert seen["env"]["DRILLMASTER_TEST_HANG_SECONDS"] == str(verify_release.TEST_HANG_SECONDS)
    out = capsys.readouterr().out
    assert "::error title=pytest hang::a test did not finish within 0:15:00" in out
    assert "tests/test_slow.py:40 in test_waits_for_ever" in out
    assert "::error title=pytest hang threads::2 thread(s): T1: threading.py:359 wait" in out      # D51
