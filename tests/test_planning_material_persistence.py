"""Persistence + truthful-status regression for Planning Material Inventory.

Two guarantees are asserted:

1. A material row saved through ``MaterialInventoryTab.save_material_row``
   is actually committed to the database (verified by re-querying with a
   *separate* session — not by repainting the same widget).
2. When no well is selected, ``save_material_row`` returns ``False`` and does
   not silently claim success (root cause of a false-success defect: the row
   was left visible in the table while nothing was persisted).

The widget is real Qt, so the work runs in an isolated subprocess (native Qt
aborts when mixed with other Qt tests in the shared interpreter); the parent
only checks the exit status.
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

    from core.database import DatabaseManager, Base, BulkMaterials

    mgr = DatabaseManager()
    mgr.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(mgr.engine)
    mgr.Session = sessionmaker(bind=mgr.engine, autoflush=False, autocommit=False)

    from PySide6.QtWidgets import QApplication, QTableWidgetItem
    app = QApplication.instance() or QApplication([])

    from tabs.w10_Planning_Widget import MaterialInventoryTab

    tab = MaterialInventoryTab(mgr)

    # --- Case 1: no well selected => must NOT claim success ---
    tab.current_well_id = None
    tab.material_table.setRowCount(1)
    for c, v in [(0, "Barite"), (1, "kg"), (2, "100"), (3, "0"), (4, "0")]:
        tab.material_table.setItem(0, c, QTableWidgetItem(v))
    assert tab.save_material_row(0) is False, "save must fail without a well"

    # --- Case 2: well selected => row persists and reloads ---
    tab.current_well_id = 42
    tab.current_section_id = None
    tab.current_report_id = None
    ok = tab.save_material_row(0)
    assert ok is True, "save should succeed with a well selected"

    # Verify with a SEPARATE session (fresh read, not a repaint).
    s = mgr.create_session()
    try:
        rows = s.query(BulkMaterials).filter(
            BulkMaterials.well_id == 42,
            BulkMaterials.material_name == "Barite",
        ).all()
        assert len(rows) == 1, len(rows)
        assert rows[0].initial_stock == 100.0, rows[0].initial_stock
        assert rows[0].unit == "kg", rows[0].unit
    finally:
        s.close()

    print("OK")
    """
)


def test_material_row_persists_and_reports_truthfully():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        env=env,
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        "child failed\nSTDOUT:\n" + proc.stdout + "\nSTDERR:\n" + proc.stderr
    )
    assert "OK" in proc.stdout, proc.stdout
