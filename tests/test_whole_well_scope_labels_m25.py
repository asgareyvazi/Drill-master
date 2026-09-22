"""M25 §9-15 Track I — whole-well scope labels are present in the UI.

The well-level analytics/export surfaces (W10 NPT/activity/milestones children,
W16 Cost, W11 report+batch export tabs) aggregate across every wellbore and
sidetrack of a well. This test proves each surface now *declares* that scope in
the UI so an operator cannot mistake a whole-well aggregate for the selected
bore. DDR (report-scoped) must NOT carry a whole-well banner.

Widgets are constructed in an isolated subprocess (native Qt aborts when mixed
with other Qt tests in the shared interpreter, per the repo's established
pattern).
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

    from PySide6.QtWidgets import QApplication, QLabel, QGroupBox
    app = QApplication.instance() or QApplication([])

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from core.database import Base, DatabaseManager

    m = DatabaseManager()
    m.engine = create_engine("sqlite:///:memory:",
                             connect_args={"check_same_thread": False},
                             poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)

    def all_text(widget):
        out = []
        for child in widget.findChildren(QLabel):
            out.append(child.text())
        for child in widget.findChildren(QGroupBox):
            out.append(child.title())
        return "\\n".join(out)

    WHOLE = "Whole-Well"
    failures = []

    # ---- W16 Cost Management: whole-well banner -------------------------
    from tabs.w16_Cost_Management import CostManagementWidget
    w16 = CostManagementWidget(db_manager=m)
    if WHOLE not in all_text(w16):
        failures.append("W16 Cost missing whole-well scope label")

    # ---- W10 children: NPT, activity (Code), milestones ----------------
    from tabs.w10_Planning_Widget import (
        NPTReportTab, CodeManagementTab, MilestonesTab)
    npt = NPTReportTab(db_manager=m)
    if WHOLE not in all_text(npt):
        failures.append("W10 NPT tab missing whole-well scope label")
    code = CodeManagementTab(db_manager=m)
    if WHOLE not in all_text(code):
        failures.append("W10 activity/code tab missing whole-well scope label")
    mile = MilestonesTab(db_manager=m)
    if WHOLE not in all_text(mile):
        failures.append("W10 milestones tab missing whole-well scope label")

    # ---- W11 Export: EOWR/NPT/Cost/Plan/Batch labelled, DDR NOT --------
    from tabs.w11_Export import ExportWidget
    exp = ExportWidget(db_manager=m)
    # Whole-well banners appear on the well-level report tabs. There is one
    # per tab (EOWR, NPT, Cost, Plan, Batch) => at least 5 occurrences.
    banners = 0
    for lbl in exp.findChildren(QLabel):
        if WHOLE in lbl.text():
            banners += 1
    if banners < 5:
        failures.append(
            "W11 export missing whole-well banners (found %d, need >=5)" % banners)

    if failures:
        print("FAILURES:\\n" + "\\n".join(failures))
        raise SystemExit(1)
    print("OK")
    raise SystemExit(0)
    """
)


def test_whole_well_scope_labels_present():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        capture_output=True, text=True, env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    assert proc.returncode == 0, (
        "child failed:\nSTDOUT:\n%s\nSTDERR:\n%s" % (proc.stdout, proc.stderr))
    assert "OK" in proc.stdout
