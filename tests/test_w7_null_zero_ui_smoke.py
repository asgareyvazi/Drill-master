"""Subprocess-isolated UI smoke test for W7 fuel/water NULL-vs-zero stock.

Mission 24, Track J (§26-28). The DB layer round-trips a genuinely UNKNOWN
stock as NULL; this test proves the W7 WIDGET surfaces and preserves that state
instead of collapsing it to a fabricated 0.0:

  * A persisted NULL stock loads as the "unknown" special value ("—"),
    NOT 0.0, and re-saving preserves the NULL.
  * A persisted explicit 0.0 loads as 0.0 (a reported empty tank), and the
    two states remain distinct through the widget round-trip.

Core semantics are covered Qt-free in ``test_w7_null_zero_semantics.py``; the
widget flow runs in an isolated subprocess because native Qt aborts when mixed
with other Qt tests in one interpreter.
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
        Base, DatabaseManager, Company, Project, Well, DailyReport)
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
    w = Well(name="W", code="W", project_id=p.id); s.add(w); s.flush()
    r1 = DailyReport(well_id=w.id, report_date=date(2026, 5, 1)); s.add(r1); s.flush()
    r2 = DailyReport(well_id=w.id, report_date=date(2026, 5, 2)); s.add(r2); s.flush()
    s.commit()
    wid, r1id, r2id = w.id, r1.id, r2.id
    s.close()

    # r1: a persisted UNKNOWN fuel stock (NULL), carry-forward disabled.
    m.save_fuel_water_inventory({
        "well_id": wid, "report_id": r1id, "report_date": date(2026, 5, 1),
        "fuel_stock": None, "fuel_consumed": 0.0, "carry_forward": False})
    # r2: a persisted EXPLICIT ZERO fuel stock (empty tank fact).
    m.save_fuel_water_inventory({
        "well_id": wid, "report_id": r2id, "report_date": date(2026, 5, 2),
        "fuel_stock": 0.0, "fuel_consumed": 0.0, "carry_forward": False})

    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QMessageBox.critical = staticmethod(lambda *a, **k: None)

    permissions.set_user({"id": 1, "username": "eng", "role": "engineer"})
    from tabs.w7_logistics_Widget import (
        FuelWaterTab, _stock_value, _STOCK_UNKNOWN_SENTINEL)

    tab = FuelWaterTab(db_manager=m)
    tab.show()

    # --- Load the UNKNOWN-stock day: spinbox shows "—", value is unknown ---
    tab.current_well_id = wid
    tab.current_report_id = r1id
    tab.report_date.setDate(QDate(2026, 5, 1))
    tab.load_fuel_water_from_db()
    assert _stock_value(tab.fuel_stock) is None, "NULL stock must load as unknown"
    assert tab.fuel_stock.value() <= _STOCK_UNKNOWN_SENTINEL, "at the unknown mark"
    assert tab.fuel_stock.text().strip() == "—", "unknown stock renders as em dash"

    # Re-saving the unknown day must PRESERVE NULL, not fabricate 0.0.
    assert tab.save_fuel_water_to_db() is True
    row1 = m.get_fuel_water_inventory(well_id=wid, report_id=r1id)[0]
    assert row1["fuel_stock"] is None, "re-save preserved NULL"
    assert row1["fuel_remaining"] is None
    assert row1["days_remaining_fuel"] is None

    # --- Load the EXPLICIT-ZERO day: spinbox shows a real 0.0 ---
    tab.current_report_id = r2id
    tab.report_date.setDate(QDate(2026, 5, 2))
    tab.load_fuel_water_from_db()
    assert _stock_value(tab.fuel_stock) == 0.0, "explicit 0.0 loads as 0.0"
    assert tab.fuel_stock.text().strip() != "—", "explicit zero is not the unknown mark"

    # Re-saving the explicit-zero day preserves the reported 0.0 fact.
    assert tab.save_fuel_water_to_db() is True
    row2 = m.get_fuel_water_inventory(well_id=wid, report_id=r2id)[0]
    assert row2["fuel_stock"] == 0.0, "re-save preserved explicit 0.0"

    # The two states never collapsed into one another.
    assert row1["fuel_stock"] is None and row2["fuel_stock"] == 0.0

    print("W7_NULL_ZERO_UI_OK")
    """
)


def test_w7_null_zero_ui_smoke_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "W7_NULL_ZERO_UI_OK" not in proc.stdout:
        pytest.fail(
            "W7 NULL/zero UI smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
