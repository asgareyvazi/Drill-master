"""Subprocess-isolated UI smoke test for the W16 AFE save/reload flow.

Constructing the full ``CostManagementWidget`` in the shared pytest interpreter
is environmentally fragile (native Qt aborts when mixed with other Qt tests), so
the widget flow runs in an isolated subprocess; the shared process only checks
the exit status. Core cost semantics are covered Qt-free in
``test_cost_truth_boundary.py``.

Proven here through the real widget:
  * ``save_data`` actually persists the AFE worksheet (it used to ``return
    True`` and persist nothing).
  * The worksheet reloads from persisted ``CostRecord`` budget lines.
  * The Summary card shows persisted actual cost, not a synthetic rig-rate.
  * A Viewer role is blocked from saving.
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
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from core.database import (
        Base, DatabaseManager, Company, Project, Well, CostRecord)
    from core.permissions import permissions

    m = DatabaseManager()
    m.engine = create_engine("sqlite:///:memory:",
                             connect_args={"check_same_thread": False},
                             poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    s = m.create_session()
    c = Company(name="X", code="X"); s.add(c); s.flush()
    p = Project(name="P", code="P", company_id=c.id); s.add(p); s.flush()
    w = Well(name="W", code="W", project_id=p.id); s.add(w); s.commit()
    wid = w.id; s.close()

    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QMessageBox.critical = staticmethod(lambda *a, **k: None)

    permissions.set_user({"id": 1, "username": "eng", "role": "engineer"})
    from tabs.w16_Cost_Management import CostManagementWidget

    tab = CostManagementWidget(db_manager=m)
    tab.on_well_changed(wid, {})
    tab.afe_table.cellWidget(0, 2).setValue(123456)
    outcome = tab.save_data()
    assert bool(outcome) is True, "engineer save should succeed"
    assert getattr(outcome, "saved", 0) >= 1, "save should persist AFE lines"

    # No-well save must NOT report success (honest blocked outcome, §2.4).
    tab.current_well_id = None
    blocked = tab.save_data()
    assert bool(blocked) is False, "no-well save must not claim success"
    tab.on_well_changed(wid, {})

    s = m.create_session()
    lines = s.query(CostRecord).filter(
        CostRecord.well_id == wid, CostRecord.cost_type == "AFE").all()
    s.close()
    assert lines, "AFE save must persist CostRecord budget lines"
    assert any(l.actual_cost == 123456 for l in lines), "actual cost persisted"

    # Fresh widget reloads persisted values.
    tab2 = CostManagementWidget(db_manager=m)
    tab2.on_well_changed(wid, {})
    reloaded = any(
        (tab2.afe_table.cellWidget(r, 2) and
         tab2.afe_table.cellWidget(r, 2).value() == 123456)
        for r in range(tab2.afe_table.rowCount()))
    assert reloaded, "worksheet must reload persisted actual cost"

    tab2._generate_summary()
    assert "123,456" in tab2.card_total.value_label.text(), \\
        "Summary must show persisted actual cost, not a synthetic rate"

    # Viewer is read-only.
    permissions.set_user({"id": 2, "username": "v", "role": "viewer"})
    assert tab2.save_data() is False, "viewer save must be blocked"

    print("W16_COST_SMOKE_OK")
    """
)


def test_w16_cost_save_reload_smoke_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "W16_COST_SMOKE_OK" not in proc.stdout:
        pytest.fail(
            "W16 cost save/reload smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
