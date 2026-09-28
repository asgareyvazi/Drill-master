"""Fuel/Water (W7 FuelWaterInventory) truth-boundary regressions — Mission 22.

Locks the concrete fuel/water semantics the codebase previously got wrong:

  * ``days_remaining`` is UNKNOWN (None -> "N/A") when there is no known
    positive consumption rate — never a fabricated 0 (which reads as an
    imminent-stockout alarm) and never infinity (§9).
  * low-stock warnings fire only on a KNOWN runway below threshold; a
    zero/unknown burn rate must not raise a false alarm (§10).
  * carry-forward fills only a missing opening and is surfaced as a clearly
    marked PREVIEW, distinguishable from a persisted row (§11).

Qt-free: helper unit tests plus a real in-memory DatabaseManager.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base, DatabaseManager, Company, Project, Well, DailyReport,
)
from core.fuel_water_semantics import days_remaining, is_low_stock


# ---------------------------------------------------------------------------
# Pure semantics (§9/§10)
# ---------------------------------------------------------------------------

class TestDaysRemaining:
    def test_zero_consumption_is_unknown_not_zero(self):
        assert days_remaining(100.0, 0.0) is None

    def test_unknown_consumption_is_unknown(self):
        assert days_remaining(100.0, None) is None

    def test_unknown_remaining_is_unknown(self):
        assert days_remaining(None, 50.0) is None

    def test_negative_consumption_is_unknown(self):
        assert days_remaining(100.0, -5.0) is None

    def test_known_positive_rate_computes_runway(self):
        assert days_remaining(100.0, 50.0) == 2.0

    def test_zero_remaining_with_burn_is_zero_days(self):
        # A genuine empty tank with active burn IS zero days — a real fact.
        assert days_remaining(0.0, 50.0) == 0.0


class TestLowStockWarning:
    def test_no_false_alarm_when_no_burn(self):
        assert is_low_stock(100.0, 0.0) is False

    def test_no_false_alarm_when_consumption_unknown(self):
        assert is_low_stock(100.0, None) is False

    def test_warns_on_known_short_runway(self):
        assert is_low_stock(100.0, 50.0) is True  # 2 days < 3

    def test_no_warning_on_comfortable_runway(self):
        assert is_low_stock(100.0, 10.0) is False  # 10 days


# ---------------------------------------------------------------------------
# Persistence semantics
# ---------------------------------------------------------------------------

def _env():
    m = DatabaseManager()
    m.engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    s = m.create_session()
    try:
        c = Company(name="X", code="X"); s.add(c); s.flush()
        p = Project(name="P", code="P", company_id=c.id); s.add(p); s.flush()
        w = Well(name="W", code="W", project_id=p.id); s.add(w); s.flush()
        r1 = DailyReport(well_id=w.id, report_date=date(2026, 1, 1)); s.add(r1); s.flush()
        r2 = DailyReport(well_id=w.id, report_date=date(2026, 1, 2)); s.add(r2); s.flush()
        s.commit()
        ids = {"well": w.id, "r1": r1.id, "r2": r2.id}
    finally:
        s.close()
    return m, ids


@pytest.fixture
def env():
    return _env()


class TestPersistence:
    def test_zero_consumption_stores_null_runway(self, env):
        m, ids = env
        m.save_fuel_water_inventory({
            "well_id": ids["well"], "report_id": ids["r1"],
            "report_date": date(2026, 1, 1),
            "fuel_stock": 100.0, "fuel_consumed": 0.0,
            "water_stock": 50.0, "water_consumed": 0.0})
        row = m.get_fuel_water_inventory(well_id=ids["well"], report_id=ids["r1"])[0]
        assert row["days_remaining_fuel"] is None
        assert row["days_remaining_water"] is None

    def test_positive_consumption_stores_runway(self, env):
        m, ids = env
        m.save_fuel_water_inventory({
            "well_id": ids["well"], "report_id": ids["r1"],
            "report_date": date(2026, 1, 1),
            "fuel_stock": 100.0, "fuel_consumed": 50.0})
        row = m.get_fuel_water_inventory(well_id=ids["well"], report_id=ids["r1"])[0]
        # remaining 50 / burn 50 = 1 day
        assert row["days_remaining_fuel"] == 1.0

    def test_persisted_row_not_marked_preview(self, env):
        m, ids = env
        m.save_fuel_water_inventory({
            "well_id": ids["well"], "report_id": ids["r1"],
            "report_date": date(2026, 1, 1),
            "fuel_stock": 100.0, "fuel_consumed": 50.0})
        row = m.get_fuel_water_inventory(well_id=ids["well"], report_id=ids["r1"])[0]
        assert row["is_carry_forward_preview"] is False

    def test_carry_forward_is_marked_preview(self, env):
        m, ids = env
        m.save_fuel_water_inventory({
            "well_id": ids["well"], "report_id": ids["r1"],
            "report_date": date(2026, 1, 1),
            "fuel_stock": 100.0, "fuel_consumed": 50.0})
        # Request the NEXT day which has no persisted row -> preview projected.
        preview = m.get_fuel_water_inventory(
            well_id=ids["well"], report_id=ids["r2"], report_date=date(2026, 1, 2))
        assert preview and preview[0]["is_carry_forward_preview"] is True
        assert preview[0]["source_report_date"] == date(2026, 1, 1)
        # It reflects the previous closing balance, not a fresh zero.
        assert preview[0]["fuel_stock"] == 50.0
