"""Subprocess-isolated smoke test for the T&D Calculation History dialog.

Constructing real Qt widgets in the shared pytest interpreter is environmentally
fragile here, so the dialog is exercised in an isolated subprocess; the shared
process only checks the exit status. Core logic is covered Qt-free in
``test_torque_drag_history.py``.
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
    from core.repositories.torque_drag_repository import (
        TorqueDragCalculationRepository)

    m = DatabaseManager()
    m.engine = create_engine("sqlite:///:memory:",
                             connect_args={"check_same_thread": False},
                             poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    repo = TorqueDragCalculationRepository(m)

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from dialogs.torque_drag_history_dialog import TorqueDragHistoryDialog

    # Empty state must not crash.
    d0 = TorqueDragHistoryDialog(repo, current_method=TorqueDragEngine.METHOD)
    assert d0.table.rowCount() == 0

    # Save two runs, reload the dialog, inspect + verify the first row.
    survey = [{"md": 0, "inc": 0, "azi": 0}, {"md": 3048.0, "inc": 0, "azi": 0}]
    comp = {"type": "Drill Pipe", "od": 5.0, "id": 4.276, "length": 3048.0,
            "weight": 19.5, "grade": "S-135", "connection": "NC50"}
    def save(components, label):
        res = TorqueDragEngine.calculate(survey, components, mud_density_ppg=10.0,
                                         friction_factor=0.3)
        repo.save_run(survey=survey, components=components, mud_density_ppg=10.0,
                      friction_factor=0.3, result_values=res.values,
                      method=TorqueDragEngine.METHOD, label=label)
        return res

    r = save([comp], "A")
    save([comp, dict(comp, id=3.5)], "B")

    d = TorqueDragHistoryDialog(repo, current_method=TorqueDragEngine.METHOD)
    assert d.table.rowCount() == 2

    # Select row 0 -> details populated, verify button enabled.
    d.table.selectRow(0)
    assert d.details.toPlainText().strip() != ""
    assert d.verify_btn.isEnabled()

    # Run verification (observational) -> newest row (B) reproduces exactly.
    newest_id = repo.all()[0].id
    before = repo.get(newest_id).summary["total_buoyed_weight"]
    d._on_verify()
    assert "MATCH" in d.status_label.text(), d.status_label.text()

    # Verification did not modify the stored result.
    after = repo.get(newest_id).summary["total_buoyed_weight"]
    assert after == before

    print("TD_HISTORY_SMOKE_OK")
    """
)


def test_history_dialog_smoke_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "TD_HISTORY_SMOKE_OK" not in proc.stdout:
        pytest.fail(
            "T&D history dialog smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
