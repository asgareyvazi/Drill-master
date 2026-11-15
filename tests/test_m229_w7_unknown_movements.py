"""D75 (found while closing the D71 fuel / water residual): an UNKNOWN daily movement survives the W7 round-trip.

Before the fix a movement stored as NULL (the DDR importer and the carry-forward preview leave unreported
consumption / receipts NULL) loaded into W7 as 0.00 L; saving the day without any edit stored 0.0 consumed and
received and a "remaining" derived from them (evidence:
``docs/mission-reports/m201-m230-evidence/d75_w7_unknown_movement_before_fix.txt``). Now the movement boxes have the
same "—" mark as the stock boxes: a loaded NULL shows "—", saves back as NULL and leaves remaining / runway unknown,
while an explicit 0.0 stays a real 0.0 and a fresh form still starts at 0 (no movement while authoring a day).

The widget flow runs in a subprocess like the other W7 smokes (native Qt in one interpreter with other Qt tests).
SYNTHETIC data only.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from datetime import date

import pytest

pytest.importorskip("PySide6")

_SETUP = """
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from datetime import date
from sqlalchemy import create_engine, null
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from core.database import Base, DatabaseManager, Company, Project, Well, DailyReport, FuelWaterInventory

def make_db():
    m = DatabaseManager()
    m.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    s = m.create_session()
    c = Company(name="SYN", code="SYN"); s.add(c); s.flush()
    p = Project(name="SYN", code="SYN", company_id=c.id); s.add(p); s.flush()
    w = Well(name="SYN-W", code="SYN-W", project_id=p.id); s.add(w); s.flush()
    reports = [DailyReport(well_id=w.id, report_date=date(2026, 5, d)) for d in (1, 2, 3)]
    s.add_all(reports); s.flush()
    # day 1: as the DDR importer stores unreported movements - explicit NULL; day 2: explicit zero movements
    s.add(FuelWaterInventory(well_id=w.id, report_id=reports[0].id, report_date=date(2026, 5, 1), fuel_type="Diesel",
                             fuel_stock=1000.0, fuel_consumed=null(), fuel_received=null(), water_stock=500.0,
                             water_consumed=null(), water_received=null(), fuel_remaining=null(),
                             water_remaining=null()))
    s.add(FuelWaterInventory(well_id=w.id, report_id=reports[1].id, report_date=date(2026, 5, 2), fuel_type="Diesel",
                             fuel_stock=900.0, fuel_consumed=0.0, fuel_received=0.0, water_stock=400.0,
                             water_consumed=0.0, water_received=0.0, fuel_remaining=900.0, water_remaining=400.0))
    s.commit()
    ids = (w.id, [r.id for r in reports])
    s.close()
    return m, ids

def row(m, wid, rid):
    return m.get_fuel_water_inventory(well_id=wid, report_id=rid)[0]
"""

_CHILD = textwrap.dedent(_SETUP) + textwrap.dedent(
    """
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    for name in ("information", "warning", "critical"):
        setattr(QMessageBox, name, staticmethod(lambda *a, **k: None))
    from core.permissions import permissions
    permissions.set_user({"id": 1, "username": "eng", "role": "engineer"})
    from tabs.w7_logistics_Widget import FuelWaterTab, _stock_value

    m, (wid, (r1, r2, r3)) = make_db()
    tab = FuelWaterTab(db_manager=m)
    tab.current_well_id = wid

    def load(rid, day):
        tab.current_report_id = rid
        tab.report_date.setDate(QDate(2026, 5, day))
        tab.load_fuel_water_from_db()

    MOVES = ("fuel_consumed", "fuel_received", "water_consumed", "water_received")

    # 1) a stored NULL movement loads as the unknown mark and survives a save without edits
    load(r1, 1)
    for name in MOVES:
        assert getattr(tab, name).text().strip() == "—", name
        assert _stock_value(getattr(tab, name)) is None, name
    assert "remaining unknown" in tab.results_label.text() and "1,000.0 L remaining" not in tab.results_label.text()
    assert tab.save_fuel_water_to_db() is True
    saved = row(m, wid, r1)
    assert [saved[k] for k in MOVES] == [None] * 4, saved
    assert saved["fuel_stock"] == 1000.0 and saved["fuel_remaining"] is None and saved["water_remaining"] is None
    assert saved["days_remaining_fuel"] is None

    # 2) the operator enters the real consumption: only that value is written, remaining stays unknown while the
    #    receipt is still unknown
    tab.fuel_consumed.setValue(120.0)
    assert tab.save_fuel_water_to_db() is True
    saved = row(m, wid, r1)
    assert saved["fuel_consumed"] == 120.0 and saved["fuel_received"] is None and saved["fuel_remaining"] is None
    tab.fuel_received.setValue(0.0)                      # an explicit "nothing received" completes the balance
    assert tab.save_fuel_water_to_db() is True
    saved = row(m, wid, r1)
    assert saved["fuel_received"] == 0.0 and saved["fuel_remaining"] == 880.0

    # 3) explicit zero movements stay real zeros, distinct from unknown
    load(r2, 2)
    for name in MOVES:
        assert _stock_value(getattr(tab, name)) == 0.0 and getattr(tab, name).text().strip() != "—", name
    assert tab.save_fuel_water_to_db() is True
    saved = row(m, wid, r2)
    assert [saved[k] for k in MOVES] == [0.0] * 4 and saved["fuel_remaining"] == 900.0

    # 4) the D71 residual end to end: the carry-forward preview of day 3 shows yesterday's closing balance and
    #    unknown movements; confirming it with Save records the balance and leaves the movements NULL
    load(r3, 3)
    assert tab._is_carry_forward_preview
    assert _stock_value(tab.fuel_stock) == 900.0
    for name in MOVES:
        assert _stock_value(getattr(tab, name)) is None, name
    assert tab.save_fuel_water_to_db() is True
    saved = row(m, wid, r3)
    assert saved["fuel_stock"] == 900.0 and [saved[k] for k in MOVES] == [None] * 4 and saved["fuel_remaining"] is None

    # 5) a fresh / cleared form still starts at 0 (no movement while authoring), never at the unknown mark
    tab.clear_fields()
    for name in MOVES:
        assert _stock_value(getattr(tab, name)) == 0.0, name
    print("D75_W7_UNKNOWN_MOVEMENTS_OK")
    """
)


def test_unknown_movements_survive_the_w7_round_trip_in_subprocess():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run([sys.executable, "-c", _CHILD], cwd=repo_root, env=env, capture_output=True, text=True,
                          timeout=180)
    if proc.returncode != 0 or "D75_W7_UNKNOWN_MOVEMENTS_OK" not in proc.stdout:
        pytest.fail(f"D75 W7 round-trip failed\nrc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")


def test_the_save_api_keeps_a_none_movement_null_and_an_omitted_one_at_the_legacy_zero():
    namespace: dict = {}
    exec(textwrap.dedent(_SETUP), namespace)             # noqa: S102 - the shared synthetic setup above
    m, (wid, (_r1, _r2, r3)) = namespace["make_db"]()
    m.save_fuel_water_inventory({"well_id": wid, "report_id": r3, "report_date": date(2026, 5, 3),
                                 "fuel_stock": 300.0, "fuel_consumed": None, "fuel_received": 10.0,
                                 "water_stock": 200.0, "carry_forward": False})
    saved = namespace["row"](m, wid, r3)
    assert saved["fuel_consumed"] is None and saved["fuel_received"] == 10.0
    assert saved["fuel_remaining"] is None and saved["days_remaining_fuel"] is None
    # keys a caller does not send keep the historical 0.0 default (no behaviour change for those callers)
    assert saved["water_consumed"] == 0.0 and saved["water_received"] == 0.0 and saved["water_remaining"] == 200.0
