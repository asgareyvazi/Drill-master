"""Subprocess-isolated UI smoke test for W12 wellbore-scope context (Mission 24).

The scope-routing logic is covered Qt-free in ``test_w12_wellbore_scope.py``;
this test proves the *widget* actually re-scopes when a wellbore is selected via
the shared ``SelectionManager`` and that the visible scope indicator tells the
truth. It runs in an isolated subprocess because constructing the full pyqtgraph
dashboard in the shared pytest interpreter is environmentally fragile.

Proven through the real widget:
  * Selecting a multi-bore well shows "Whole-Well Aggregate".
  * Selecting a wellbore switches scope and names the bore.
  * Switching bores updates the indicator (no stale scope).
  * Switching to a different well clears the bore scope.
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
        Base, DatabaseManager, Company, Project, Well, Wellbore, Section, DailyReport)

    m = DatabaseManager()
    m.engine = create_engine("sqlite:///:memory:",
                             connect_args={"check_same_thread": False},
                             poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    m.create_session()
    s = m.create_session()
    c = Company(name="C", code="C"); s.add(c); s.flush()
    p = Project(name="P", code="P", company_id=c.id); s.add(p); s.flush()
    w = Well(name="W1", code="W1", project_id=p.id); s.add(w); s.flush()
    w2 = Well(name="W2", code="W2", project_id=p.id); s.add(w2); s.flush()
    orig = Wellbore(well_id=w.id, name="Original", wellbore_type="original"); s.add(orig); s.flush()
    st1 = Wellbore(well_id=w.id, name="ST-1", wellbore_type="sidetrack"); s.add(st1); s.flush()
    sec = Section(name="12-1/4", well_id=w.id, wellbore_id=orig.id, depth_from=0); s.add(sec); s.flush()
    s.add(DailyReport(well_id=w.id, section_id=sec.id, wellbore_id=orig.id,
                      report_number=1, report_date=date(2026, 1, 1), depth_2400=1000))
    s.commit()
    wid, w2id, oid, sid = w.id, w2.id, orig.id, st1.id
    s.close()

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from core.permissions import permissions
    permissions.set_user({"id": 1, "username": "e", "role": "engineer"})
    from core.selection_manager import SelectionManager
    from tabs.w12_Analysis import AnalysisWidget

    sel = SelectionManager()
    tab = AnalysisWidget(db_manager=m)
    tab.show()

    sel.select_well(wid, {"name": "W1"})
    assert tab.current_wellbore_id is None
    assert "Aggregate" in tab.scope_label.text(), tab.scope_label.text()

    sel.select_wellbore(oid, {"id": oid, "name": "Original", "well_id": wid})
    assert tab.current_wellbore_id == oid
    assert "Original" in tab.scope_label.text()

    sel.select_wellbore(sid, {"id": sid, "name": "ST-1", "well_id": wid})
    assert tab.current_wellbore_id == sid
    assert "ST-1" in tab.scope_label.text()

    sel.select_well(w2id, {"name": "W2"})
    assert tab.current_well_id == w2id
    assert tab.current_wellbore_id is None, tab.current_wellbore_id
    assert tab.scope_label.text().startswith("\\U0001f310 Scope: Whole Well"), tab.scope_label.text()

    print("W12_SCOPE_UI_OK")
    """
)


def test_w12_scope_ui_smoke_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "W12_SCOPE_UI_OK" not in proc.stdout:
        pytest.fail(
            "W12 scope UI smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
