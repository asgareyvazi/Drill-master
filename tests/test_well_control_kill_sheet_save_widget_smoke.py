"""Subprocess-isolated UI smoke test for the W13 kill-sheet Save/History flow.

Constructing the full ``EngineeringCalculatorTab`` in the shared pytest
interpreter is environmentally fragile (native Qt aborts when mixed with other
Qt tests). So the widget flow runs in an isolated subprocess; the shared process
only checks the exit status. Core logic is covered Qt-free in
``test_well_control_kill_sheet_persistence.py``.

This proves the real W13 handler path: read widgets -> build canonical inputs ->
compute -> save whole result, then reload + verify MATCH. It also proves the
history dialog reads the PERSISTED record (not live widgets): after saving, the
widgets are mutated and the reloaded run must be unchanged (mission §34/§45).
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
    from core.engineering.engines.well_control import WellControlEngine

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
    tab._wc_last_kill_inputs = None
    tab._wc_last_kill_result = None
    tab._wc_save_calculation()
    assert tab._wc_kill_sheet_repo().count() == 0, "no-run save must persist nothing"

    # Drive the real handler: set widget values + pipe program, then calc + save.
    tab.wc_tvd.setValue(3000.0)
    tab.wc_md.setValue(3200.0)
    tab.wc_shoe_tvd.setValue(2000.0)
    tab.wc_shoe_md.setValue(2050.0)
    tab.wc_hole_size.setValue(8.5)
    tab.wc_last_csg.setValue(9.625)
    tab.wc_last_csg_id.setValue(8.835)
    tab.wc_mw.setValue(90.0)
    tab.wc_frac.setValue(0.8)
    tab.wc_sidpp.setValue(500.0)
    tab.wc_sicp.setValue(700.0)
    tab.wc_pit_gain.setValue(10.0)
    tab.wc_scr1.setValue(800.0)
    tab.wc_scr1_spm.setValue(30.0)
    tab.wc_scr2.setValue(600.0)
    tab.wc_scr2_spm.setValue(25.0)
    tab.wc_pump_output.setValue(0.09)
    tab.wc_pipes = [
        {"type": "DP", "od": 5.0, "id": 4.276, "length": 2800.0},
        {"type": "DC", "od": 6.5, "id": 2.8125, "length": 150.0},
    ]
    tab._wc_calc_kill()
    assert getattr(tab, "_wc_last_kill_result", None) is not None
    assert tab._wc_last_kill_result.success, "kill sheet must succeed"
    tab._wc_save_calculation()

    repo = tab._wc_kill_sheet_repo()
    assert repo.count() == 1, "one run should be persisted"
    saved = repo.all()[0]
    stored_kill_mw = saved.result["kill_mw_ppg"]
    assert saved.summary["kill_mw_ppg"] is not None
    outcome = saved.verify(current_method=WellControlEngine.METHOD)
    assert outcome.status == "MATCH", outcome.status
    recalc = saved.recalculate()
    assert recalc.values["choke_schedule"] == saved.result["choke_schedule"]

    # Historical independence: mutate current widgets + pipe program, then the
    # ALREADY-persisted run must be byte-identical (history != current state).
    tab.wc_mw.setValue(120.0)
    tab.wc_pipes.append({"type": "HWDP", "od": 5.0, "id": 3.0, "length": 500.0})
    tab._wc_calc_kill()
    reloaded = repo.get(saved.id)
    assert reloaded.result["kill_mw_ppg"] == stored_kill_mw, "history must not change"
    assert repo.count() == 1, "recompute alone must not persist a new run"

    # History dialog constructs + lists from persisted records (read-only).
    from dialogs.well_control_kill_sheet_history_dialog import (
        WellControlKillSheetHistoryDialog)
    dlg = WellControlKillSheetHistoryDialog(
        repo, current_method=WellControlEngine.METHOD)
    assert dlg.table.rowCount() == 1

    print("WC_SAVE_SMOKE_OK")
    """
)


def test_w13_kill_sheet_save_calculation_smoke_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "WC_SAVE_SMOKE_OK" not in proc.stdout:
        pytest.fail(
            "W13 kill-sheet save-calculation smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
