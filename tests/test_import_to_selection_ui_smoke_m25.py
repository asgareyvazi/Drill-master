"""Mission 25 — Track L: SelectionManager import propagation (subprocess Qt).

Proves the post-import selection cascade carries the bore dimension end to end:

* select_full_context(..., wellbore_id=ST) emits well → wellbore → section →
  report IN THAT ORDER and leaves current_wellbore_id == ST.
* A W12 AnalysisWidget wired to the manager ends up scoped to ST-1 (not
  Whole-Well) without any extra user click.
* When the resolved bore is None (unknown), the manager's wellbore stays None
  (Whole-Well) and is never inferred to be Original.

SelectionManager is a QObject and native Qt aborts when mixed with other Qt
tests in one interpreter, so this runs in an isolated subprocess.
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
    from datetime import date
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from core.database import (
        Base, DatabaseManager, Company, Project, Well, Wellbore, Section,
        DailyReport)
    from core.permissions import permissions

    m = DatabaseManager()
    m.engine = create_engine("sqlite:///:memory:",
                             connect_args={"check_same_thread": False},
                             poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    s = m.create_session()
    c = Company(name="C", code="C"); s.add(c); s.flush()
    p = Project(name="P", code="P", company_id=c.id); s.add(p); s.flush()
    w = Well(name="W1", code="W1", project_id=p.id); s.add(w); s.flush()
    orig = Wellbore(well_id=w.id, name="Original", wellbore_type="original")
    s.add(orig); s.flush()
    st1 = Wellbore(well_id=w.id, name="ST-1", wellbore_type="sidetrack",
                   parent_wellbore_id=orig.id, kickoff_md=2500)
    s.add(st1); s.flush()
    sec = Section(name='12-1/4"', well_id=w.id, wellbore_id=st1.id, depth_from=2500)
    s.add(sec); s.flush()
    rpt = DailyReport(well_id=w.id, section_id=sec.id, wellbore_id=st1.id,
                      report_number=100, report_date=date(2026, 3, 1), depth_2400=3000)
    s.add(rpt); s.flush()
    wid, oid, stid, secid, rid = w.id, orig.id, st1.id, sec.id, rpt.id
    s.commit(); s.close()

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    permissions.set_user({"id": 1, "username": "eng", "role": "engineer"})

    from core.selection_manager import SelectionManager
    SelectionManager._instance = None
    sm = SelectionManager()

    order = []
    sm.well_changed.connect(lambda *a: order.append("well"))
    sm.wellbore_changed.connect(lambda *a: order.append("wellbore"))
    sm.section_changed.connect(lambda *a: order.append("section"))
    sm.report_changed.connect(lambda *a: order.append("report"))

    # W12 exists BEFORE the import/selection (as at app startup), so the
    # selection cascade must DRIVE it into the ST-1 scope with no extra click.
    from tabs.w12_Analysis import AnalysisWidget
    w12 = AnalysisWidget(db_manager=m)

    well_data = m.get_well_by_id(wid) or {}
    section_data = next(x for x in m.get_sections_by_well(wid) if x["id"] == secid)
    report_data = m.get_daily_report_by_id(rid)
    # Effective bore resolution mirrors _targeted_refresh.
    wellbore_id = report_data.get("wellbore_id") or section_data.get("wellbore_id")
    wellbore_data = next((wb for wb in m.get_wellbores_by_well(wid)
                          if wb["id"] == wellbore_id), None)

    sm.select_full_context(wid, secid, rid, well_data, section_data, report_data,
                           wellbore_id=wellbore_id, wellbore_data=wellbore_data)

    assert order == ["well", "wellbore", "section", "report"], order
    assert sm.current_well_id == wid
    assert sm.current_wellbore_id == stid, sm.current_wellbore_id
    assert sm.current_section_id == secid
    assert sm.current_report_id == rid

    # The pre-existing W12 widget is now scoped to ST-1, not Whole-Well.
    assert w12.current_wellbore_id == stid, w12.current_wellbore_id
    assert "ST-1" in w12.scope_label.text() or f"#{stid}" in w12.scope_label.text(), \
        w12.scope_label.text()

    # --- Unknown-bore report: manager wellbore stays None (never Original) ---
    s2 = m.create_session()
    runk = DailyReport(well_id=wid, section_id=None, wellbore_id=None,
                       report_number=101, report_date=date(2026, 3, 2), depth_2400=1500)
    s2.add(runk); s2.flush(); runk_id = runk.id; s2.commit(); s2.close()

    SelectionManager._instance = None
    sm2 = SelectionManager()
    rdata = m.get_daily_report_by_id(runk_id)
    eff = rdata.get("wellbore_id")  # section None too
    sm2.select_full_context(wid, None, runk_id, well_data, {}, rdata,
                            wellbore_id=eff, wellbore_data=None)
    assert sm2.current_wellbore_id is None, sm2.current_wellbore_id
    assert sm2.current_wellbore_id != oid

    print("IMPORT_TO_SELECTION_OK")
    """
)


def test_import_to_selection_ui_smoke_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "IMPORT_TO_SELECTION_OK" not in proc.stdout:
        pytest.fail(
            "import->selection UI smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
