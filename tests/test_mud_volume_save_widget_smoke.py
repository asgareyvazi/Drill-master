"""Subprocess-isolated UI smoke test for the W13 Mud Volume 'Save Calculation' flow.

Constructing the full ``EngineeringCalculatorTab`` in the shared pytest
interpreter is environmentally fragile (native Qt aborts when mixed with other
Qt tests). So the widget flow runs in an isolated subprocess; the shared process
only checks the exit status. Core logic is covered Qt-free in
``test_mud_volume_persistence.py``.
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
    from core.engineering.engines.mud_volume import MudVolumeEngine

    m = DatabaseManager.__new__(DatabaseManager)
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
    tab._mud_bal_last_run = None
    tab._mud_bal_save_calculation()
    assert tab._mud_volume_repo().count() == 0, "no-run save must persist nothing"

    # Drive the real handler: set widget values then calculate + save.
    tab.mud_bal_active.setValue(800.0)
    tab.mud_bal_add.setValue(50.0)
    tab.mud_bal_loss.setValue(20.0)
    tab.mud_bal_tin.setValue(10.0)
    tab.mud_bal_tout.setValue(5.0)
    tab.mud_bal_ret.setValue(15.0)
    tab.mud_bal_dil.setValue(8.0)
    tab.mud_bal_dump.setValue(3.0)
    tab._mud_balance()
    assert tab._mud_bal_last_run is not None, "successful calc must cache a run"
    tab._mud_bal_save_calculation()

    repo = tab._mud_volume_repo()
    assert repo.count() == 1, "one run should be persisted"
    saved = repo.all()[0]
    assert saved.summary["final_volume_bbl"] == 855.0
    assert saved.input_parameters["active_volume_bbl"] == 800.0
    outcome = saved.verify(current_method=MudVolumeEngine.METHOD)
    assert outcome.status == "MATCH", outcome.status
    recalc = saved.recalculate()
    assert recalc.values["final_volume_bbl"] == saved.result["final_volume_bbl"]

    print("MUDVOL_SAVE_SMOKE_OK")
    """
)


def test_w13_mud_volume_save_calculation_smoke_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "MUDVOL_SAVE_SMOKE_OK" not in proc.stdout:
        pytest.fail(
            "W13 mud volume save-calculation smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
