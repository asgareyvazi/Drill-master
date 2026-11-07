"""Subprocess-isolated UI smoke test for the W13 Anti-Collision screening tab.

Constructing the full ``EngineeringCalculatorTab`` in the shared pytest
interpreter is environmentally fragile (native Qt aborts when mixed with other
Qt tests). So the widget flow runs in an isolated subprocess; the shared process
only checks the exit status. Core engine logic is covered Qt-free in
``test_anti_collision_engine.py``.

M129 (D45): the page no longer screens the unsaved Multi-Survey table against a
hand-typed offset at the same wellhead with a separation-factor column; it is the
trajectory comparison panel (``core.trajectory_compare``) on survey revisions of two
wells. The database path is covered in ``test_m129_surveys_anticollision.py``.
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

    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QMessageBox.critical = staticmethod(lambda *a, **k: None)

    import inspect
    from core import trajectory_compare as tc
    from tabs import trajectory_compare_panel
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab
    tab = EngineeringCalculatorTab()

    # --- M129: the page is the trajectory comparison panel, locked to offset-well mode ---
    panel = tab.ac_panel
    assert panel.mode == "offset" and not panel.mode_combo.isEnabled()
    assert "NO SEPARATION FACTOR" in panel.label_banner.text(), panel.label_banner.text()

    # --- Guard: no well / no database -> a visible state, no result, nothing saveable ---
    panel.run()
    assert panel.result is None and "Select a well first" in panel.status_label.text(), panel.status_label.text()
    assert not panel.save_button.isEnabled() and panel.save() is None

    # --- No engineering logic in the UI and no separation factor column ---
    assert "tc.run_comparison" in inspect.getsource(trajectory_compare_panel._compute)
    headers = [title for _key, title in trajectory_compare_panel.OFFSET_COLUMNS]
    assert not any("factor" in h.lower() for h in headers), headers
    tab.cleanup()

    print("ANTICOLLISION_WIDGET_SMOKE_OK")
    """
)


def test_w13_anti_collision_screening_smoke_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "ANTICOLLISION_WIDGET_SMOKE_OK" not in proc.stdout:
        pytest.fail(
            "W13 anti-collision screening smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
