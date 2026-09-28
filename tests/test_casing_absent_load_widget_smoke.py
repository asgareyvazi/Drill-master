"""Subprocess-isolated UI smoke test for the W13 casing combined-collapse line.

The engine now reports a NOT-supplied axial load as ``fyax_psi = None`` instead
of a fabricated ``0.0``/``80000.0`` pair. The W13 result line must therefore
render the absent case explicitly ("fyax=n/a (no axial load supplied)") — a
naive ``f"{fy:,.0f}"`` raises ``TypeError`` when the reviewer's own semantics
reach the widget.

Constructing ``EngineeringCalculatorTab`` inside the shared pytest interpreter
is environmentally fragile (native Qt aborts), so the widget flow runs in an
isolated subprocess and the parent only checks the exit status plus the marker.
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

    m = DatabaseManager()
    m.engine = create_engine("sqlite:///:memory:",
                             connect_args={"check_same_thread": False},
                             poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab
    tab = EngineeringCalculatorTab(m)

    # Geometry only — axial tension / internal pressure left at their 0 defaults,
    # which the tab maps to "not supplied" (None) exactly like an empty field.
    tab.csg_od.setValue(9.625)
    tab.csg_id_calc.setValue(8.681)
    tab.csg_wall.setValue(0.472)
    tab.csg_yield.setValue(80000.0)

    assert tab.csg_axial.value() == 0, "precondition: axial spin at its default"
    tab._csg_calc_strength()
    line = tab.csg_combined_res.text()
    assert "fyax=n/a" in line, f"absent axial load must not print a fyax value: {line!r}"
    assert tab._csg_last_run is not None, "a successful calc must cache the run"
    values = tab._csg_last_run["result_values"]
    assert values["fyax_psi"] is None, values["fyax_psi"]
    assert values["axial_tension_supplied"] is False

    # An explicitly supplied zero IS a stated value and must still be displayed.
    tab.csg_axial.setValue(100000.0)
    tab._csg_calc_strength()
    line = tab.csg_combined_res.text()
    assert "fyax=" in line and "n/a" not in line, f"supplied tension must print fyax: {line!r}"
    values = tab._csg_last_run["result_values"]
    assert values["axial_tension_supplied"] is True
    assert values["fyax_psi"] < 80000.0

    print("CSG_ABSENT_SMOKE_OK")
    """
)


def test_w13_casing_absent_load_rendering_smoke_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "CSG_ABSENT_SMOKE_OK" not in proc.stdout:
        pytest.fail(
            "W13 casing absent-load smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
