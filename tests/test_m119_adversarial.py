"""M119: second adversarial review - probes that attack resolved findings from angles their own tests did not use,
and a check of what the tests actually assert.  SYNTHETIC data only.
"""
from __future__ import annotations

import ast
import copy
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import calculation_history as ch  # noqa: E402
from core import survey_revisions as sr  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ROWS = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 300.0, "inc": 0.0, "azi": 0.0},
        {"md": 600.0, "inc": 20.0, "azi": 357.0}, {"md": 900.0, "inc": 35.0, "azi": 10.0}]
#: tests without an assert whose only claim is "must not raise" - reviewed in M119 (see the PySide6 probe below)
MUST_NOT_RAISE = {
    "tests/test_ownership_parent_edits.py::test_consistent_parent_and_child_edit_is_allowed",
    "tests/test_trajectory_3d.py::test_a_destroyed_view_leaves_no_pending_draw",
    "tests/test_trajectory_3d.py::test_matplotlib_redraw_requests_cannot_outlive_the_canvas",
}


def _revision():
    return {"revision": 1, "stations": copy.deepcopy(ROWS), "results": sr.compute(ROWS)}


# ---- D1 (verify_results): angles the M105 tests did not take ------------------------------------------------
def test_d1_azimuth_wrap_is_a_match_but_a_real_azimuth_change_is_not():
    rev = _revision()
    rev["results"][0]["azi"] = 360.0 - 1e-9                       # 0 deg stored as 359.999999999: same direction
    assert sr.verify_results(rev)["status"] == "MATCH"
    rev["results"][2]["azi"] = rev["results"][2]["azi"] + 180.0    # the opposite direction
    assert sr.verify_results(rev)["status"] == "DIFFERENT"


@pytest.mark.parametrize("attack", ["swap", "bool", "string", "extra", "nan"])
def test_d1_reordered_or_mistyped_results_never_match(attack):
    rev = _revision()
    rows = rev["results"]
    if attack == "swap":
        rows[1], rows[2] = rows[2], rows[1]
    elif attack == "bool":
        rows[0]["inc"] = False                                       # == 0 in Python, but not a number here
    elif attack == "string":
        rows[3]["tvd"] = str(rows[3]["tvd"])
    elif attack == "extra":
        rows[1]["closure"] = 1.0
    else:
        rows[2]["dls"] = float("nan")
    assert sr.verify_results(rev)["status"] == "DIFFERENT"
    with pytest.raises(sr.SurveyRevisionError):
        sr.verify_for_use({**rev, "integrity": "VERIFIED", "results_integrity": "NOT RECORDED"}, "a probe")


def test_d2_a_missing_integrity_state_is_never_treated_as_verified():
    rev = _revision()
    with pytest.raises(sr.SurveyRevisionError, match="station hash"):
        sr.verify_for_use(rev, "a probe")                            # no 'integrity' key at all
    with pytest.raises(sr.SurveyRevisionError, match="station hash"):
        sr.verify_for_use({**rev, "integrity": None}, "a probe")


# ---- D35: a malformed stored record is reported, never a crash ---------------------------------------------
@pytest.mark.parametrize("stored", [{"total_bbl": 12.0}, [1, 2], "12"])
def test_d35_a_malformed_cement_result_is_unreadable(stored, tmp_path, monkeypatch):
    from core import well_architecture as wa
    from tests.test_m109_cement_worksheet import _entry, _saved_case
    from tests.test_m70_integrity import _open, _seed

    manager = _open(tmp_path / "m119.sqlite", tmp_path, monkeypatch)
    try:
        well = _seed(manager)["A"][0]
        _rev, case = _saved_case(manager, well)
        entry = _entry(manager, case["id"], well)
        outcome = wa.verify_cement_case(manager, entry.inputs, stored, entry.version)
        assert outcome["status"] == "UNREADABLE" and "not a worksheet payload" in outcome["detail"]
        assert outcome["values"] == {}                               # nothing that could be stored
    finally:
        manager.close()


def test_d35_any_adapter_failure_is_unreadable_with_its_reason(monkeypatch):
    from core import trajectory_compare as tc

    def broken(*_args, **_kwargs):
        raise KeyError("rows")
    monkeypatch.setattr(tc, "verify_record", broken)
    entry = ch.HistoryEntry(source="Trajectory", table="trajectory_calculations", record_id=1, name="SYN",
                            method="m", version="v", created_at=None, well_id=None, scope="", inputs={}, results={})
    outcome = ch.recalculate_entry(entry)
    assert outcome["status"] == "UNREADABLE" and "KeyError" in outcome["detail"]
    assert outcome["values"] == {} and outcome["method_matches"] is None


# ---- what the tests assert -----------------------------------------------------------------------------------
def _assertion_free_tests():
    found = set()
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        for node in tree.body:
            if not (isinstance(node, ast.FunctionDef) and node.name.startswith("test_")):
                continue
            reached = [node] + [functions[c.func.id] for c in ast.walk(node) if isinstance(c, ast.Call)
                                and isinstance(c.func, ast.Name) and c.func.id in functions]
            checks = any(isinstance(x, ast.Assert) or (isinstance(x, ast.Attribute) and x.attr in
                                                       ("raises", "fail", "warns", "check_call", "run"))
                         or (isinstance(x, ast.Name) and "assert" in x.id.lower())
                         or (isinstance(x, ast.Attribute) and "assert" in x.attr.lower())
                         for m in reached for x in ast.walk(m))
            if not checks:
                found.add(f"tests/{path.name}::{node.name}")
    return found


def test_every_test_asserts_something_or_is_a_reviewed_must_not_raise_test():
    assert _assertion_free_tests() == MUST_NOT_RAISE


def test_the_must_not_raise_tests_can_fail_because_pyside_propagates_slot_exceptions(tmp_path):
    script = tmp_path / "probe.py"
    script.write_text(
        "from PySide6.QtCore import QTimer\nfrom PySide6.QtWidgets import QApplication\n"
        "app = QApplication([])\n"
        "def boom():\n    raise RuntimeError('slot failed')\n"
        "QTimer.singleShot(0, boom)\n"
        "try:\n    [app.processEvents() for _ in range(3)]\n    print('NOT RAISED')\n"
        "except RuntimeError:\n    print('RAISED')\n", encoding="utf-8")
    done = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=60,
                          env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
    assert done.stdout.strip().splitlines()[-1] == "RAISED", done.stdout + done.stderr
