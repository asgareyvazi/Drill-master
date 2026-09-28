"""Subprocess-isolated presentation test for Planning primary data tables.

Regression guard for the "tiny viewport" defect: the Code Management main
table and the Well Plan FACT/PLAN tables were being squeezed to ~1-3 rows by
tall charts stacked in the same page. The fix gives each *primary* table a
useful minimum viewport (and Well Plan is now wrapped scrollable like its
sibling tabs). This asserts the resulting geometry so it cannot regress.

Full Qt widgets are built in an isolated subprocess (native Qt aborts when
mixed with other Qt tests in the shared interpreter); the shared process only
checks the exit status.
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
    from PySide6.QtWidgets import QApplication, QTableWidget
    app = QApplication.instance() or QApplication([])

    from tabs.w10_Planning_Widget import PlanningWidget

    pw = PlanningWidget(None)
    pw.resize(1400, 900)
    pw.show()
    app.processEvents()

    def visible_rows(t):
        rh = t.verticalHeader().defaultSectionSize() or 30
        hh = t.horizontalHeader().height()
        return max(0, (t.height() - hh) // max(rh, 1))

    # Bring each sub-tab forward, then measure its primary table(s).
    tw = pw.tab_widget
    assert tw.count() == 8, tw.count()

    # Code Management primary table.
    code_tab = pw.code_tab
    for i in range(tw.count()):
        if tw.widget(i) is code_tab or tw.widget(i).isAncestorOf(code_tab):
            tw.setCurrentIndex(i)
    app.processEvents()
    code_rows = visible_rows(pw.code_tab.code_table)
    assert code_rows >= 5, f"Code Management table too short: {code_rows} rows"

    # Well Plan FACT + PLAN tables.
    wp = pw.well_plan_tab
    for i in range(tw.count()):
        if tw.widget(i) is wp or tw.widget(i).isAncestorOf(wp):
            tw.setCurrentIndex(i)
    app.processEvents()
    fact_rows = visible_rows(pw.well_plan_tab.fact_table)
    plan_rows = visible_rows(pw.well_plan_tab.plan_table)
    assert fact_rows >= 5, f"Well Plan FACT table too short: {fact_rows} rows"
    assert plan_rows >= 5, f"Well Plan PLAN table too short: {plan_rows} rows"

    # The scrollable wrapper must still forward the tab's real methods.
    assert hasattr(pw.well_plan_tab, "set_current_well")
    assert hasattr(pw.well_plan_tab, "load_plans_list")

    print("PLANNING_TABLE_PRESENTATION_OK")
    """
)


def test_planning_primary_tables_have_usable_viewport():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "PLANNING_TABLE_PRESENTATION_OK" not in proc.stdout:
        pytest.fail(
            "Planning table presentation smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
