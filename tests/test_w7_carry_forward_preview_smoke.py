"""Subprocess-isolated UI smoke test for the W7 fuel/water carry-forward preview.

The DB layer marks a carried-forward fuel/water row as a projection
(``is_carry_forward_preview``); this test proves the W7 widget SURFACES that
provenance so a user can never mistake a projection for a persisted fact
(Mission 23, Track A §5). Core semantics are covered Qt-free in
``test_fuel_water_truth.py``; the widget flow runs in an isolated subprocess
because native Qt aborts when mixed with other Qt tests in one interpreter.

Proven here through the real widget:
  * Loading a day WITH a persisted row shows no preview banner.
  * Loading a later day with NO persisted row shows the carry-forward preview
    banner (values are the previous closing balance, clearly labelled).
  * Saving that day turns the projection into a fact and clears the banner.
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
    r1 = DailyReport(well_id=w.id, report_date=date(2026, 1, 1)); s.add(r1); s.flush()
    r2 = DailyReport(well_id=w.id, report_date=date(2026, 1, 2)); s.add(r2); s.flush()
    s.commit()
    wid, r1id, r2id = w.id, r1.id, r2.id
    s.close()

    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QMessageBox.critical = staticmethod(lambda *a, **k: None)

    permissions.set_user({"id": 1, "username": "eng", "role": "engineer"})
    from tabs.w7_logistics_Widget import FuelWaterTab

    tab = FuelWaterTab(db_manager=m)
    tab.show()

    # --- Day 1: enter and save a real row ---
    tab.current_well_id = wid
    tab.current_report_id = r1id
    tab.report_date.setDate(QDate(2026, 1, 1))
    tab.fuel_stock.setValue(100.0)
    tab.fuel_consumed.setValue(50.0)
    assert tab.save_fuel_water_to_db() is True
    assert tab._is_carry_forward_preview is False, "saved row is not a preview"
    assert tab.preview_banner.isVisibleTo(tab) is False

    # --- Day 1: loading the persisted row shows NO preview banner ---
    tab.load_fuel_water_from_db()
    assert tab._is_carry_forward_preview is False, "persisted day must not preview"
    assert tab.preview_banner.isVisibleTo(tab) is False

    # --- Day 2: no persisted row -> carry-forward PREVIEW is shown ---
    tab.current_report_id = r2id
    tab.report_date.setDate(QDate(2026, 1, 2))
    tab.load_fuel_water_from_db()
    assert tab._is_carry_forward_preview is True, "projected day must be marked preview"
    assert tab.preview_banner.isVisibleTo(tab) is True
    assert "PREVIEW" in tab.preview_banner.text()
    # It reflects the previous closing balance (100 stock - 50 burn = 50).
    assert tab.fuel_stock.value() == 50.0

    # --- Saving day 2 turns the projection into a fact and clears the banner ---
    assert tab.save_fuel_water_to_db() is True
    assert tab._is_carry_forward_preview is False
    assert tab.preview_banner.isVisibleTo(tab) is False

    print("W7_CARRY_FORWARD_PREVIEW_OK")
    """
)


def test_w7_carry_forward_preview_smoke_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0 or "W7_CARRY_FORWARD_PREVIEW_OK" not in proc.stdout:
        pytest.fail(
            "W7 carry-forward preview smoke failed\n"
            f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
