"""Well-scoped calculation-history regression.

The six engineering-calculation history dialogs listed every well's saved runs
together (``repo.all()``), so opening history for Well A also showed Well B's
runs with no way to tell them apart (mission §13/§24). History is now scoped to
the current well by default, with a toggle to browse all wells, using the
``well_id`` each saved record already carries. No repository or schema change.

* The Qt-free filter (`filter_saved_by_well`) is tested directly.
* The dialog wiring is exercised in a subprocess (native Qt aborts in the
  shared interpreter) against a fake in-memory repo spanning two wells.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from types import SimpleNamespace

import pytest


def _run(well_id):
    return SimpleNamespace(well_id=well_id)


def test_filter_scopes_to_current_well():
    from dialogs.history_well_filter import filter_saved_by_well
    saved = [_run(7), _run(9), _run(7), _run(None)]

    # Current well 7, this-well-only -> only the two well-7 runs.
    only7 = filter_saved_by_well(saved, 7, this_well_only=True)
    assert [s.well_id for s in only7] == [7, 7]

    # Toggle off -> everything.
    assert len(filter_saved_by_well(saved, 7, this_well_only=False)) == 4

    # No active well context -> everything regardless of the flag.
    assert len(filter_saved_by_well(saved, None, this_well_only=True)) == 4


pytest.importorskip("PySide6")


_CHILD = textwrap.dedent(
    """
    import os, datetime
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    def mk(cid, well):
        return SimpleNamespace(
            id=cid, label="run", method="mse.teale.v1",
            snapshot_schema_version=1, input_snapshot={}, result={},
            well_id=well, created_at=datetime.datetime(2026, 9, 20, 10, cid),
            input_parameters={"wob_lbf": 1000, "rpm": 100, "rop_ft_hr": 50,
                              "bit_diameter_in": 8.5, "torque_ft_lbf": 500},
            summary={"mse_psi": 30000, "axial_term_psi": 1,
                     "rotary_term_psi": 2, "bit_area_in2": 56.7},
        )

    class FakeRepo:
        def all(self):
            return [mk(1, 7), mk(2, 9), mk(3, 7), mk(4, None)]

    from dialogs.mse_history_dialog import MSEHistoryDialog

    dlg = MSEHistoryDialog(FakeRepo(), current_method="mse.teale.v1",
                           well_id=7, well_label="NORTH-12 (#7)")
    assert dlg.scope_box.isChecked() is True
    assert dlg.table.rowCount() == 2, dlg.table.rowCount()

    dlg.scope_box.setChecked(False)
    assert dlg.table.rowCount() == 4, dlg.table.rowCount()

    dlg.show(); app.processEvents()
    assert dlg.scope_box.isVisible() is True

    # No well context: checkbox hidden, all runs listed.
    dlg2 = MSEHistoryDialog(FakeRepo(), current_method="mse.teale.v1")
    dlg2.show(); app.processEvents()
    assert dlg2.scope_box.isVisible() is False
    assert dlg2.table.rowCount() == 4, dlg2.table.rowCount()

    print("OK")
    """
)


def test_history_dialog_scopes_and_toggles():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        env=env, cwd=repo_root, capture_output=True, text=True,
    )
    assert proc.returncode == 0, (
        "child failed\nSTDOUT:\n" + proc.stdout + "\nSTDERR:\n" + proc.stderr
    )
    assert "OK" in proc.stdout, proc.stdout
