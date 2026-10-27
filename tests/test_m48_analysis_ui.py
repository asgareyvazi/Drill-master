"""M48 - Operations Analysis (W12) through the REAL widget.

The scenarios live in ``tests/m48_ui_child.py`` and run in ONE isolated
subprocess (Qt offscreen platform), the same isolation the existing W12 UI
smoke tests use: building the full pyqtgraph dashboard inside the shared
pytest interpreter is environmentally fragile. Each scenario is reported here
as its own test. These are offscreen-Qt tests on Linux, not Windows desktop
testing.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

HERE = Path(__file__).resolve().parent
CHILD = HERE / "m48_ui_child.py"
SCENARIOS = re.findall(r"^@scenario\ndef (\w+)\(", CHILD.read_text(encoding="utf-8"), re.M)


def _env():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONIOENCODING"] = "utf-8"          # the child prints UTF-8 JSON on every OS
    env["PYTHONPATH"] = os.pathsep.join([str(HERE.parent), env.get("PYTHONPATH", "")])
    return env


@pytest.fixture(scope="module")
def ui_results():
    proc = subprocess.run([sys.executable, str(CHILD)], cwd=str(HERE.parent), env=_env(),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=600)
    results = {}
    for line in proc.stdout.splitlines():
        if line.startswith("M48RESULT "):
            item = json.loads(line[len("M48RESULT "):])
            results[item["name"]] = item
    if not results:
        pytest.fail(f"UI child produced no results (exit {proc.returncode}):\n"
                    f"{proc.stderr[-4000:]}")
    return results


def test_scenarios_were_discovered():
    assert len(SCENARIOS) >= 30 and len(set(SCENARIOS)) == len(SCENARIOS)
    assert {"e2e_performance_report_export_switch_well",
            "e2e_npt_coverage_forecast_not_assessed_export", "e2e_cost_and_risk"} <= set(SCENARIOS)


@pytest.mark.parametrize("name", SCENARIOS)
def test_w12_scenario(ui_results, name):
    assert name in ui_results, f"scenario {name} did not report (child crashed?)"
    result = ui_results[name]
    assert result["ok"], result.get("error")


_NO_PYQTGRAPH = r"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.modules["pyqtgraph"] = None          # simulate the optional dependency missing
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
from core.permissions import permissions
permissions.set_user({"id": 1, "username": "m48", "role": "engineer"})
import tabs.w12_Analysis as w12
assert w12.PYQTGRAPH_AVAILABLE is False
sys.path.insert(0, "tests")
from m48_synthetic import build
db, ids = build()
from core.selection_manager import SelectionManager
sel = SelectionManager()
tab = w12.AnalysisWidget(db_manager=db)
sel.select_well(ids["C"], {"name": "SYN-C"})
tab.refresh()
sel.select_well(None)
sel.clear()
print("NO_PYQTGRAPH_OK")
"""


def test_w12_degrades_without_pyqtgraph():
    proc = subprocess.run([sys.executable, "-c", _NO_PYQTGRAPH], cwd=str(HERE.parent),
                          env=_env(), capture_output=True, text=True, timeout=300)
    assert "NO_PYQTGRAPH_OK" in proc.stdout, proc.stderr[-3000:]
