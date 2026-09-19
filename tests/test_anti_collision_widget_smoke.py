"""Subprocess-isolated UI smoke test for the W13 Anti-Collision screening tab.

Constructing the full ``EngineeringCalculatorTab`` in the shared pytest
interpreter is environmentally fragile (native Qt aborts when mixed with other
Qt tests). So the widget flow runs in an isolated subprocess; the shared process
only checks the exit status. Core engine logic is covered Qt-free in
``test_anti_collision_engine.py``.

This verifies the Wave-3 functionalization: the Anti-Collision engine (the only
mature engine that previously had no GUI, reachable only via AI-tools/bridge) is
now invoked end-to-end from the human calculator via ``CalculatorBridge`` — no
engineering logic in the UI. Screening honesty is preserved (warnings surfaced;
results transient by design, never persisted).
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

    from core.engineering.core import TrajectoryEngine
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab
    tab = EngineeringCalculatorTab()

    # --- Guard: no reference well -> distinct MISSING_INPUT, no crash ---
    tab.dd_surveys = []
    tab.ac_offset_surveys = []
    tab._ac_screen()
    assert "MISSING_INPUT" in tab.ac_summary.text(), tab.ac_summary.text()
    assert "reference" in tab.ac_summary.text().lower(), tab.ac_summary.text()

    # --- Build a reference well (Multi-Survey), min-curvature positions ---
    ref_raw = [
        {"md": 0, "inc": 0, "azi": 0},
        {"md": 500, "inc": 0, "azi": 0},
        {"md": 1000, "inc": 30, "azi": 90},
    ]
    pts = TrajectoryEngine.calculate(ref_raw)
    tab.dd_surveys = [
        {"md": r["md"], "inc": r["inc"], "azi": r["azi"],
         "tvd": p.tvd, "north": p.north, "east": p.east, "dls": p.dls}
        for r, p in zip(ref_raw, pts)
    ]

    # --- Guard: reference present but no offset -> MISSING_INPUT for offset ---
    tab._ac_screen()
    assert "MISSING_INPUT" in tab.ac_summary.text(), tab.ac_summary.text()
    assert "offset" in tab.ac_summary.text().lower(), tab.ac_summary.text()

    # --- Enter an offset well; recalc positions via canonical MC ---
    off_raw = [
        {"md": 0, "inc": 0, "azi": 0},
        {"md": 500, "inc": 2, "azi": 90},
        {"md": 1000, "inc": 5, "azi": 90},
    ]
    tab.ac_offset_surveys = [dict(s) for s in off_raw]
    tab._ac_recalculate()
    tab._ac_refresh_table()
    assert tab.ac_table.rowCount() == 3

    # --- Screen with radii + a collision threshold ---
    tab.ac_ref_radius.setValue(0.1)
    tab.ac_off_radius.setValue(0.1)
    tab.ac_threshold.setValue(50.0)
    tab._ac_screen()
    summary = tab.ac_summary.text()
    assert "Closest approach" in summary, summary
    # Clearance is computed only because both radii were supplied.
    assert "Clearance" in summary, summary
    # Screening honesty must always be surfaced.
    assert "Screening model only" in summary, summary
    # Collision scan requested -> a status is reported.
    assert "Collision scan" in summary, summary
    # Result table populated from separation_vs_md rows.
    assert tab.ac_result_table.rowCount() >= 2, tab.ac_result_table.rowCount()

    # --- No engineering logic in the UI: it must delegate to the bridge ---
    import inspect
    src = inspect.getsource(EngineeringCalculatorTab._ac_screen)
    assert "CalculatorBridge.anti_collision" in src, "must delegate to canonical bridge"

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
