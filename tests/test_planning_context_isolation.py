"""Context-isolation regression for the Planning 7-Day Lookahead sub-tab.

Defect: switching the current well left the previously selected report's
lookahead rows (and its ``current_report_id``) in place, so Well A's plan
leaked into the Well B view until a new report was picked. ``set_current_well``
now clears the report context, the report combo and the table when the well
changes.

The sub-tab is a real Qt widget; native Qt aborts when mixed with other Qt
tests in the shared interpreter, so the widget work runs in an isolated
subprocess and the parent only checks the exit status.
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
    from PySide6.QtWidgets import QApplication, QTableWidgetItem
    app = QApplication.instance() or QApplication([])

    from tabs.w10_Planning_Widget import SevenDaysLookaheadTab

    tab = SevenDaysLookaheadTab(None)

    # Simulate Well A with a loaded report and populated lookahead rows.
    tab.current_well_id = 1
    tab.current_section_id = 10
    tab.current_report_id = 100
    tab.lookahead_table.setRowCount(3)
    for r in range(3):
        tab.lookahead_table.setItem(r, 2, QTableWidgetItem("WellA-activity-" + str(r)))

    assert tab.lookahead_table.rowCount() == 3
    assert tab.current_report_id == 100

    # User selects Well B. No report leakage may survive.
    tab.set_current_well(2)

    assert tab.current_well_id == 2, tab.current_well_id
    assert tab.current_report_id is None, tab.current_report_id
    assert tab.current_section_id is None, tab.current_section_id
    assert tab.lookahead_table.rowCount() == 0, tab.lookahead_table.rowCount()

    print("OK")
    """
)


def test_lookahead_clears_report_context_on_well_switch():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        env=env,
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        "child failed\nSTDOUT:\n" + proc.stdout + "\nSTDERR:\n" + proc.stderr
    )
    assert "OK" in proc.stdout, proc.stdout
