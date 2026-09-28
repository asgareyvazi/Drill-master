"""Well-context attribution regression for the Engineering Calculator.

The six persisted engineering calculations attribute each saved run to the
current well (``current_well_id``). Before this guard the tab showed no
indication of which well was active, so an engineer could silently save a run
to the wrong well or to no well. The tab now:

* shows a live well-context banner that tracks the SelectionManager selection
  (propagated through ``DrillTabBase.on_well_changed``), and
* states the well attribution in every save-confirmation dialog via
  ``_save_attribution_line``.

This asserts both the banner text and the attribution line across the
no-well, named-well, unnamed-well and cleared states. Full Qt widgets abort
when mixed with other Qt tests in the shared interpreter, so the widget runs
in an isolated subprocess; the parent only checks the exit status.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("PySide6")


_CHILD = textwrap.dedent(
    """
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab

    t = EngineeringCalculatorTab(None)

    # No well selected: warn, and attribution must say "not attributed".
    assert "No well selected" in t.well_context_label.text(), t.well_context_label.text()
    assert "Not attributed to any well" in t._save_attribution_line()

    # Named well: banner + attribution name it with the durable id.
    t.on_well_changed(7, {"name": "NORTH-12", "id": 7})
    assert t.current_well_id == 7
    assert "NORTH-12 (#7)" in t.well_context_label.text(), t.well_context_label.text()
    assert "Attributed to well: NORTH-12 (#7)." in t._save_attribution_line()

    # Unnamed well data still attributes by durable id (never blank/wrong well).
    t.on_well_changed(9, {})
    assert "Well #9" in t.well_context_label.text(), t.well_context_label.text()
    assert "Attributed to well: Well #9." in t._save_attribution_line()

    # Cleared: back to the explicit no-well warning (no stale Well #9 leak).
    t.on_well_changed(None, None)
    assert t.current_well_id is None
    assert "No well selected" in t.well_context_label.text(), t.well_context_label.text()
    assert "Not attributed to any well" in t._save_attribution_line()

    print("OK")
    """
)


_CHILD_PRESELECT = textwrap.dedent(
    """
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    # A well is selected BEFORE the calculator tab is first created. The tab
    # must inherit that context (DrillTabBase seeds it) instead of resetting to
    # None, otherwise a saved run would be attributed to no well despite an
    # active selection.
    from core.selection_manager import SelectionManager
    sm = SelectionManager()
    sm.select_well(5, {"name": "PRE-SELECT-5", "id": 5})

    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab
    t = EngineeringCalculatorTab(None)

    assert t.current_well_id == 5, t.current_well_id
    assert "PRE-SELECT-5 (#5)" in t.well_context_label.text(), t.well_context_label.text()
    assert "Attributed to well: PRE-SELECT-5 (#5)." in t._save_attribution_line()

    print("OK")
    """
)


def _run_child(source):
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", source],
        env=env,
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        "child failed\nSTDOUT:\n" + proc.stdout + "\nSTDERR:\n" + proc.stderr
    )
    assert "OK" in proc.stdout, proc.stdout


def test_calculator_shows_and_attributes_well_context():
    _run_child(_CHILD)


def test_calculator_inherits_preexisting_well_selection():
    _run_child(_CHILD_PRESELECT)
