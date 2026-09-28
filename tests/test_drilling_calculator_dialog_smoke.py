"""Subprocess-isolated UI smoke test for the legacy DrillingCalculatorDialog.

The legacy 'Calculator' popup (toolbar/menu → DrillingCalculatorDialog) is a
lightweight quick-estimate kill-sheet entry point that remains active. After the
ICP/FCP single-owner consolidation it must still open and render, now producing
engine-identical ICP/FCP. Building full Qt widgets in the shared pytest
interpreter is fragile (native abort), so this runs in an isolated subprocess.
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
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from dialogs.calculator_dialog import DrillingCalculatorDialog
    from core.engineering.engines.well_control import WellControlEngine as WC

    dlg = DrillingCalculatorDialog()
    dlg.tvd.setValue(3000.0)
    dlg.current_mw.setValue(75.0)
    dlg.sidpp.setValue(500.0)
    dlg.sicp.setValue(700.0)
    dlg.slow_pump_rate.setValue(800.0)
    dlg.shoe_tvd.setValue(2000.0)
    dlg.frac_grad.setValue(0.8)
    dlg._calc_kill_sheet()
    text = dlg.kill_result.toPlainText()
    assert "KILL SHEET" in text, text

    # engine-computed expected values (single owner)
    tvd_ft = 3000.0 * 3.28084
    mw_ppg = 75.0 / 7.48
    kmw = WC.calculate_kill_mw(mw_ppg, 500.0, tvd_ft)
    icp = WC.calculate_icp(800.0, 500.0)
    fcp = WC.calculate_fcp(800.0, kmw, mw_ppg)
    assert f"{icp:.0f} psi (ICP)" in text, text
    assert f"{fcp:.0f} psi (FCP)" in text, text
    assert "MAASP:" in text

    # validation: TVD/MW must be > 0 (explicit failure, no crash)
    dlg.tvd.setValue(0.0)
    dlg._calc_kill_sheet()
    assert "TVD and MW must be > 0" in dlg.kill_result.toPlainText()

    print("DRILLING_CALC_SMOKE_OK")
    """
)


def test_drilling_calculator_kill_sheet_smoke_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "DRILLING_CALC_SMOKE_OK" not in proc.stdout:
        pytest.fail(
            "DrillingCalculatorDialog kill-sheet smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
