"""Subprocess-isolated UI smoke test for the W13 'Save Calculation' flow.

Constructing the full ``EngineeringCalculatorTab`` in the shared pytest
interpreter is environmentally fragile (native Qt aborts when mixed with other
Qt tests). So the widget flow runs in an isolated subprocess; the shared process
only checks the exit status. Core logic is covered Qt-free in
``test_torque_drag_persistence.py``.
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
    from core.engineering.engines.torque_drag import TorqueDragEngine

    m = DatabaseManager()
    m.engine = create_engine("sqlite:///:memory:",
                             connect_args={"check_same_thread": False},
                             poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)

    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    # Never let a modal dialog block a headless run.
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QMessageBox.critical = staticmethod(lambda *a, **k: None)

    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab
    tab = EngineeringCalculatorTab(m)

    # Saving with no run present must be a no-op (no crash, nothing persisted).
    tab._wt_last_td_run = None
    tab._wt_save_calculation()
    assert tab._torque_drag_repo().count() == 0, "no-run save must persist nothing"

    # Simulate a successful T&D run cache, then save.
    survey = [{"md": 0, "inc": 0, "azi": 0}, {"md": 3048.0, "inc": 0, "azi": 0}]
    comp = {"type": "Drill Pipe", "od": 5.0, "id": 4.276, "length": 3048.0,
            "weight": 19.5, "grade": "S-135", "connection": "NC50",
            "reference_fingerprint": "fp-xyz"}
    r = TorqueDragEngine.calculate(survey, [comp], mud_density_ppg=10.0,
                                   friction_factor=0.3)
    tab._wt_last_td_run = {
        "survey": survey, "components": [comp], "mud_density_ppg": 10.0,
        "friction_factor": 0.3, "wob_klbf": 0.0, "wellbore_id_in": None,
        "result_values": r.values, "method": TorqueDragEngine.METHOD,
    }
    tab._wt_save_calculation()

    repo = tab._torque_drag_repo()
    assert repo.count() == 1, "one run should be persisted"
    saved = repo.all()[0]
    assert saved.reference_fingerprints == ["fp-xyz"]
    recalc = saved.recalculate()
    assert recalc.values["total_buoyed_weight"] == r.values["total_buoyed_weight"]

    print("TD_SAVE_SMOKE_OK")
    """
)


def test_w13_save_calculation_smoke_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "TD_SAVE_SMOKE_OK" not in proc.stdout:
        pytest.fail(
            "W13 save-calculation smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
