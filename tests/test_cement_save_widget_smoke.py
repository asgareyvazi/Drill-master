"""Subprocess-isolated UI smoke test for the W13 cement 'Save Calculation' flow.

Constructing the full ``EngineeringCalculatorTab`` in the shared pytest
interpreter is environmentally fragile (native Qt aborts when mixed with other
Qt tests). So the widget flow runs in an isolated subprocess; the shared process
only checks the exit status. Core logic is covered Qt-free in
``test_cement_persistence.py``.
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
    from core.database import DatabaseManager, Base
    from core.engineering.engines.cement import CementEngine

    m = DatabaseManager()
    m.engine = create_engine("sqlite:///:memory:",
                             connect_args={"check_same_thread": False},
                             poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)

    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QMessageBox.critical = staticmethod(lambda *a, **k: None)

    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab
    tab = EngineeringCalculatorTab(m)

    # Saving with no run present must be a no-op (no crash, nothing persisted).
    tab._cmt_last_run = None
    tab._cmt_save_calculation()
    assert tab._cement_repo().count() == 0, "no-run save must persist nothing"

    # Drive the real handler: set widget values then calculate + save.
    tab.cmt_hole.setValue(12.25)
    tab.cmt_csg.setValue(9.625)
    tab.cmt_len.setValue(2000.0)
    tab.cmt_excess.setValue(30.0)
    tab.cmt_csg_id.setValue(8.681)
    tab.cmt_shoe_track.setValue(80.0)
    tab.cmt_dens.setValue(15.8)
    tab.cmt_yield.setValue(1.15)
    tab.cmt_lead_len.setValue(1500.0)
    tab.cmt_lead_mw.setValue(13.5)
    tab.cmt_tail_len.setValue(500.0)
    tab.cmt_tail_mw.setValue(15.8)
    tab.cmt_shoe_tvd.setValue(8000.0)
    tab.cmt_pump.setValue(8.0)
    tab._csg_calc_cement()
    assert tab._cmt_last_run is not None, "successful calc must cache a run"
    tab._cmt_save_calculation()

    repo = tab._cement_repo()
    assert repo.count() == 1, "one run should be persisted"
    saved = repo.all()[0]
    assert saved.summary["slurry_volume_bbl"] is not None
    outcome = saved.verify(current_method=CementEngine.METHOD)
    assert outcome.status == "MATCH", outcome.status
    recalc = saved.recalculate()
    assert recalc.values["lead"]["slurry_bbl"] == saved.result["lead"]["slurry_bbl"]

    print("CMT_SAVE_SMOKE_OK")
    """
)


def test_w13_cement_save_calculation_smoke_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "CMT_SAVE_SMOKE_OK" not in proc.stdout:
        pytest.fail(
            "W13 cement save-calculation smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
