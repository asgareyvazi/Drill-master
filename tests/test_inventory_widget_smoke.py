"""Subprocess-isolated UI smoke for the W5 Inventory save/reload/isolation flow.

Runs the real ``EquipmentWidget`` in an isolated subprocess (native Qt aborts
when mixed with other Qt tests in the shared interpreter). Proves through the
actual widget that W5 inventory persists to the authoritative InventoryItem
model (not EquipmentLog notes), reloads, keeps unknown distinct from zero, and
isolates wells. Core logic is covered Qt-free in
``test_inventory_item_authority.py``.
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
    from datetime import date
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from core.database import (
        Base, DatabaseManager, Company, Project, Well, DailyReport,
        InventoryItem, EquipmentLog)
    from core.permissions import permissions

    m = DatabaseManager()
    m.engine = create_engine("sqlite:///:memory:",
                             connect_args={"check_same_thread": False},
                             poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    s = m.create_session()
    c = Company(name="X", code="X"); s.add(c); s.flush()
    p = Project(name="P", code="P", company_id=c.id); s.add(p); s.flush()
    w1 = Well(name="W1", code="W1", project_id=p.id); s.add(w1); s.flush()
    w2 = Well(name="W2", code="W2", project_id=p.id); s.add(w2); s.flush()
    r1 = DailyReport(well_id=w1.id, report_date=date(2026, 1, 1)); s.add(r1); s.flush()
    r2 = DailyReport(well_id=w2.id, report_date=date(2026, 1, 1)); s.add(r2); s.flush()
    s.commit()
    w1id, w2id, r1id, r2id = w1.id, w2.id, r1.id, r2.id
    s.close()

    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QMessageBox.critical = staticmethod(lambda *a, **k: None)

    permissions.set_user({"id": 1, "username": "eng", "role": "engineer"})
    from tabs.w5_Equipment_Widget import EquipmentWidget
    tab = EquipmentWidget(db_manager=m)

    # Select well 1 / report 1 and enter inventory (one known, one unknown).
    tab.current_well = w1id
    tab.current_report_id = r1id
    tab.inventory_tab.load_table_data([
        ["Gloves", "PPE", "100", "20", "10", "130", "pcs", "10", "500"],
        ["Rags", "Consumable", "", "5", "0", "", "pcs", "", ""],
    ])
    ok = tab.save_all_data(section_filter={"Inventory"})
    assert ok, "engineer inventory save should succeed"

    # It must have persisted to InventoryItem, NOT EquipmentLog notes.
    s = m.create_session()
    items = s.query(InventoryItem).filter(InventoryItem.well_id == w1id).all()
    notes = s.query(EquipmentLog).filter(
        EquipmentLog.well_id == w1id,
        EquipmentLog.equipment_type == "Inventory").count()
    s.close()
    assert len(items) == 2, "two inventory items persisted"
    assert notes == 0, "no EquipmentLog notes inventory rows written"
    by = {i.item_name: i for i in items}
    assert by["Gloves"].current_stock == 110.0  # 100+20-10, UI 'Remaining' ignored
    assert by["Rags"].opening_stock is None      # blank stayed unknown
    assert by["Rags"].current_stock is None      # not a fabricated 0

    # Reload into a fresh widget: values return, unknown shows blank.
    tab2 = EquipmentWidget(db_manager=m)
    tab2.current_well = w1id
    tab2.current_report_id = r1id
    tab2.load_all_data()
    data = tab2.inventory_tab.get_table_data()
    names = {row[0]: row for row in data}
    assert "Gloves" in names and "Rags" in names, "inventory reloaded"
    assert names["Rags"][2] == "", "unknown opening reloads as blank, not 0"

    # Different well is isolated.
    tab2.current_well = w2id
    tab2.current_report_id = r2id
    tab2.load_all_data()
    assert tab2.inventory_tab.get_table_data() == [], "W2 has no inventory"

    # Clear then save -> empty persisted collection for that report.
    tab.current_well = w1id
    tab.current_report_id = r1id
    tab.inventory_tab.table.setRowCount(0)
    tab.save_all_data(section_filter={"Inventory"})
    assert m.get_inventory_items(well_id=w1id, report_id=r1id) == [], "cleared"

    # Viewer cannot save.
    permissions.set_user({"id": 2, "username": "v", "role": "viewer"})
    tab.inventory_tab.load_table_data([["X", "C", "1", "0", "0", "1", "pcs", "", ""]])
    blocked = tab.save_all_data(section_filter={"Inventory"})
    assert not blocked, "viewer inventory save must be blocked"

    print("W5_INVENTORY_SMOKE_OK")
    """
)


def test_w5_inventory_save_reload_smoke_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "W5_INVENTORY_SMOKE_OK" not in proc.stdout:
        pytest.fail(
            "W5 inventory save/reload smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
