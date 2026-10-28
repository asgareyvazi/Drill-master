"""M51 §9: GUI-thread garbage collection under mixed load, in an isolated process.

Runs ``tests/m51_gc_soak_child.py`` (real 3D view open/dispose, real Analysis
refreshes on a temporary FILE database, real Knowledge Assistant questions,
worker-built reference cycles; ``core.qt_gc`` installed as the app does) and
checks each scenario.  The process is separate because the policy disables
automatic collection process-wide.  Offscreen Qt - NOT a Windows desktop test.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CHILD = HERE / "m51_gc_soak_child.py"


@pytest.fixture(scope="module")
def soak():
    pytest.importorskip("PySide6")
    pytest.importorskip("pyqtgraph")
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(HERE), env.get("PYTHONPATH", "")])
    env.pop("M50_GC_POLICY", None)                       # the production policy, never the "off" switch
    proc = subprocess.run([sys.executable, str(CHILD)], cwd=str(ROOT), env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=900)
    results = {}
    for line in proc.stdout.splitlines():
        if line.startswith("M51SOAK "):
            item = json.loads(line[len("M51SOAK "):])
            results[item["name"]] = item
    if proc.returncode != 0 or len(results) != 2:
        pytest.fail(f"soak child exit {proc.returncode}, {len(results)} result(s):\n{proc.stderr[-4000:]}")
    return results


def test_mixed_load_never_collects_on_a_worker_and_reclaims_everything_on_the_gui_thread(soak):
    result = soak["soak"]
    assert result["ok"], result.get("error")
    detail = result["detail"]
    assert detail["rounds"] >= 6 and detail["worker_collections"] == 0 and detail["gui_collections"] >= 1
    assert detail["cycles_reclaimed"] == detail["rounds"] * 200 and detail["views_alive"] == 0
    assert detail["watchdog"]["worker_collections"] == 0 and detail["watchdog"]["reenabled"] == 0
    assert detail["watchdog"]["automatic_enabled"] is False


def test_the_watchdog_detects_a_worker_collection_and_re_enabled_automatic_collection(soak):
    result = soak["watchdog_detects_worker_collection_and_reenable"]
    assert result["ok"], result.get("error")
    assert result["detail"] == {"worker_collections_detected": 1, "reenabled_detected": 1}


def test_the_windows_gate_repeats_the_real_lifecycle_in_isolated_processes_without_skips():
    workflow = (ROOT / ".github" / "workflows" / "windows-release-gate.yml").read_text(encoding="utf-8")
    start = workflow.index("- name: Repeated 3D and Analysis lifecycle (M51, isolated repetitions)")
    step = workflow[start:workflow.index("- name: Build portable bundle", start)]
    main = workflow[workflow.index("python -m pytest -ra -q tests/test_packaging_smoke.py"):start]
    modules = ["tests/test_trajectory_3d.py", "tests/test_trajectory_3d_lifecycle_m46.py",
               "tests/test_m50_analysis_async.py", "tests/test_m50_trajectory_3d_disposal.py",
               "tests/test_m51_gc_soak.py"]
    assert all((ROOT / m).is_file() for m in modules)
    assert ", ".join(f"'{m}'" for m in modules) in step                     # the real modules, nothing stubbed
    positions = [main.index(m + " ") for m in modules]
    assert positions == sorted(positions), "repetitions keep the regression suite's order"
    assert "$repetitions = 3" in step and "foreach ($repetition in 1..$repetitions)" in step
    assert "python -m pytest" in step and step.count("python -m pytest") == 1  # one fresh interpreter each time
    assert "RUNNER_TEMP" in step and "-$repetition\"" in step                 # own data root per repetition
    commands = "\n".join(line for line in step.splitlines() if not line.strip().startswith("#"))
    for banned in ("--deselect", " -k ", "no:faulthandler", "--continue-on-collection-errors", "-W ignore",
                   "QT_LOGGING_RULES", "M50_GC_POLICY", "skip"):
        assert banned not in commands, banned
    assert "$lifecycleExit = $LASTEXITCODE" in step and "if ($lifecycleExit -ne 0)" in step
    assert step.index("junit_report.py") < step.index("if ($lifecycleExit -ne 0)")
    assert "throw \"Repeated 3D and Analysis lifecycle failed" in step
