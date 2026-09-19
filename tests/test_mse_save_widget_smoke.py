"""Subprocess-isolated UI smoke test for the W13 MSE 'Save MSE' flow.

Constructing the full ``EngineeringCalculatorTab`` in the shared pytest
interpreter is environmentally fragile (native Qt aborts when mixed with other
Qt tests). So the widget flow runs in an isolated subprocess; the shared process
only checks the exit status. Core logic is covered Qt-free in
``test_mse_persistence.py``.
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
    from core.engineering.engines.mse import MSEEngine

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
    tab._mse_last_run = None
    tab._mse_save_calculation()
    assert tab._mse_repo().count() == 0, "no-run save must persist nothing"

    # Bit Hydraulics needs nozzles (TFA>0) to reach the MSE calculation.
    tab.bit_nozzles = [{"size": 12, "qty": 3}]
    tab.bit_gpm.setValue(250.0)
    tab.bit_mw.setValue(90.0)
    tab.bit_od.setValue(8.5)
    tab.bit_wob.setValue(25.0)       # klbf → 25000 lbf
    tab.bit_rpm.setValue(120.0)
    tab.bit_tq.setValue(8000.0)
    tab.bit_rop.setValue(30.0)
    tab._bit_calculate()
    assert tab._mse_last_run is not None, "successful calc must cache an MSE run"
    # The single WOB klbf→lbf conversion must be owned by the UI.
    assert tab._mse_last_run["inputs"]["wob_lbf"] == 25000.0
    tab._mse_save_calculation()

    repo = tab._mse_repo()
    assert repo.count() == 1, "one run should be persisted"
    saved = repo.all()[0]
    assert saved.summary["mse_psi"] is not None
    assert saved.input_parameters["wob_lbf"] == 25000.0
    outcome = saved.verify(current_method=MSEEngine.METHOD)
    assert outcome.status == "MATCH", outcome.status
    recalc = saved.recalculate()
    assert recalc.values["mse_psi"] == saved.result["mse_psi"]

    print("MSE_SAVE_SMOKE_OK")
    """
)


def test_w13_mse_save_calculation_smoke_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "MSE_SAVE_SMOKE_OK" not in proc.stdout:
        pytest.fail(
            "W13 MSE save-calculation smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
