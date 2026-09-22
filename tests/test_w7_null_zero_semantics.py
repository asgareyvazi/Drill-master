"""W7 fuel/water NULL-vs-zero stock semantics — Mission 24 Track J (§26-28).

The defect: a genuinely UNKNOWN physical stock (persisted as NULL, e.g. from an
import or a restore that preserves nullable columns) used to be collapsed to a
fabricated ``0.0`` on the W7 load/save round-trip. A "0 stock" is a critical
operational fact (empty tank); an "unknown stock" is the absence of one. They
must never collapse into each other.

These tests exercise the REAL persistence path (DatabaseManager.
save_fuel_water_inventory / get_fuel_water_inventory) against an isolated
in-memory database. The three states under test:

    State A (explicit 0.0)  -> a reported fact: 0.0 survives the round-trip.
    State B (missing/NULL)  -> unknown: stays NULL, yields NULL runway.
    State C (nonzero)       -> the real number survives unchanged.

Acceptance cases (§28):
  A. NULL stock            -> unknown runway (days_remaining is None).
  B. 0 stock / 0 burn      -> 0 remaining, runway unknown (no burn to divide).
  C. 100 stock / 10 burn   -> 90 remaining, 9 days runway.
  D. NULL / 0 round-trip   -> explicit 0.0 and NULL both preserved distinctly.
  E. nullable camp/dw NULL -> preserved as NULL, never fabricated 0.0.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base, DatabaseManager, Company, Project, Well, DailyReport,
)


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
        r1 = DailyReport(well_id=w.id, report_date=date(2026, 3, 1)); s.add(r1); s.flush()
        r2 = DailyReport(well_id=w.id, report_date=date(2026, 3, 2)); s.add(r2); s.flush()
        s.commit()
        ids = {"well": w.id, "r1": r1.id, "r2": r2.id}
    finally:
        s.close()
    return m, ids


@pytest.fixture
def env():
    m, ids = _env()
    yield m, ids
    m.close()


def _row(m, ids, rid):
    rows = m.get_fuel_water_inventory(well_id=ids["well"], report_id=rid)
    assert rows, "expected a persisted row"
    return rows[0]


# ---------------------------------------------------------------------------
# Case A — NULL stock -> unknown runway
# ---------------------------------------------------------------------------

class TestCaseAUnknownStock:
    def test_null_fuel_stock_persists_null_and_unknown_runway(self, env):
        m, ids = env
        # carry_forward disabled so an omitted opening genuinely stays unknown.
        m.save_fuel_water_inventory({
            "well_id": ids["well"], "report_id": ids["r1"],
            "report_date": date(2026, 3, 1),
            "fuel_stock": None, "fuel_consumed": 0.0,
            "carry_forward": False})
        row = _row(m, ids, ids["r1"])
        assert row["fuel_stock"] is None            # not fabricated 0.0
        assert row["fuel_remaining"] is None         # unknown, not derived
        assert row["days_remaining_fuel"] is None    # unknown runway

    def test_omitted_fuel_stock_is_unknown_not_zero(self, env):
        m, ids = env
        m.save_fuel_water_inventory({
            "well_id": ids["well"], "report_id": ids["r1"],
            "report_date": date(2026, 3, 1),
            "fuel_consumed": 5.0,   # movement reported, opening not
            "carry_forward": False})
        row = _row(m, ids, ids["r1"])
        assert row["fuel_stock"] is None
        assert row["fuel_remaining"] is None
        assert row["days_remaining_fuel"] is None


# ---------------------------------------------------------------------------
# Case B — explicit 0 stock / 0 burn
# ---------------------------------------------------------------------------

class TestCaseBExplicitZero:
    def test_zero_stock_zero_burn_is_zero_remaining_unknown_runway(self, env):
        m, ids = env
        m.save_fuel_water_inventory({
            "well_id": ids["well"], "report_id": ids["r1"],
            "report_date": date(2026, 3, 1),
            "fuel_stock": 0.0, "fuel_consumed": 0.0,
            "carry_forward": False})
        row = _row(m, ids, ids["r1"])
        assert row["fuel_stock"] == 0.0              # explicit fact preserved
        assert row["fuel_remaining"] == 0.0          # empty tank is a fact
        # No burn rate -> runway is UNKNOWN, never a fabricated 0-day alarm.
        assert row["days_remaining_fuel"] is None


# ---------------------------------------------------------------------------
# Case C — 100 stock / 10 burn -> 90 remaining, 9 days
# ---------------------------------------------------------------------------

class TestCaseCKnownRunway:
    def test_hundred_stock_ten_burn(self, env):
        m, ids = env
        m.save_fuel_water_inventory({
            "well_id": ids["well"], "report_id": ids["r1"],
            "report_date": date(2026, 3, 1),
            "fuel_stock": 100.0, "fuel_consumed": 10.0,
            "carry_forward": False})
        row = _row(m, ids, ids["r1"])
        assert row["fuel_stock"] == 100.0
        assert row["fuel_remaining"] == 90.0         # 100 + 0 - 10
        assert row["days_remaining_fuel"] == 9.0      # 90 / 10


# ---------------------------------------------------------------------------
# Case D — NULL / 0 round-trip distinctness
# ---------------------------------------------------------------------------

class TestCaseDRoundTripDistinct:
    def test_zero_and_null_stay_distinct_across_round_trip(self, env):
        m, ids = env
        # r1: explicit zero water stock.
        m.save_fuel_water_inventory({
            "well_id": ids["well"], "report_id": ids["r1"],
            "report_date": date(2026, 3, 1),
            "water_stock": 0.0, "water_consumed": 0.0,
            "carry_forward": False})
        # r2: unknown water stock (omitted, carry-forward off).
        m.save_fuel_water_inventory({
            "well_id": ids["well"], "report_id": ids["r2"],
            "report_date": date(2026, 3, 2),
            "water_consumed": 0.0,
            "carry_forward": False})
        zero_row = _row(m, ids, ids["r1"])
        null_row = _row(m, ids, ids["r2"])
        assert zero_row["water_stock"] == 0.0
        assert null_row["water_stock"] is None
        # The two states did not collapse into one another.
        assert zero_row["water_stock"] != null_row["water_stock"]


# ---------------------------------------------------------------------------
# Case E — nullable camp/drinking-water fields
# ---------------------------------------------------------------------------

class TestCaseENullableExtraFields:
    def test_camp_and_dw_null_preserved(self, env):
        m, ids = env
        m.save_fuel_water_inventory({
            "well_id": ids["well"], "report_id": ids["r1"],
            "report_date": date(2026, 3, 1),
            "fuel_stock": 100.0, "fuel_consumed": 10.0,
            "fuel_camp_stock": None, "dw_stock": None,
            "carry_forward": False})
        row = _row(m, ids, ids["r1"])
        assert row["fuel_camp_stock"] is None
        assert row["dw_stock"] is None

    def test_camp_and_dw_explicit_zero_preserved(self, env):
        m, ids = env
        m.save_fuel_water_inventory({
            "well_id": ids["well"], "report_id": ids["r1"],
            "report_date": date(2026, 3, 1),
            "fuel_stock": 100.0, "fuel_consumed": 10.0,
            "fuel_camp_stock": 0.0, "dw_stock": 0.0,
            "carry_forward": False})
        row = _row(m, ids, ids["r1"])
        assert row["fuel_camp_stock"] == 0.0
        assert row["dw_stock"] == 0.0


# ---------------------------------------------------------------------------
# Carry-forward still fills ONLY a missing opening (no regression)
# ---------------------------------------------------------------------------

class TestCarryForwardStillFillsMissingOnly:
    def test_missing_opening_carries_previous_closing(self, env):
        m, ids = env
        m.save_fuel_water_inventory({
            "well_id": ids["well"], "report_id": ids["r1"],
            "report_date": date(2026, 3, 1),
            "fuel_stock": 100.0, "fuel_consumed": 10.0})   # closing 90
        # Day 2 omits opening -> carry-forward fills 90.
        m.save_fuel_water_inventory({
            "well_id": ids["well"], "report_id": ids["r2"],
            "report_date": date(2026, 3, 2),
            "fuel_consumed": 0.0})
        row = _row(m, ids, ids["r2"])
        assert row["fuel_stock"] == 90.0

    def test_explicit_zero_opening_not_overwritten_by_carry_forward(self, env):
        m, ids = env
        m.save_fuel_water_inventory({
            "well_id": ids["well"], "report_id": ids["r1"],
            "report_date": date(2026, 3, 1),
            "fuel_stock": 100.0, "fuel_consumed": 10.0})   # closing 90
        # Day 2 explicitly reports an EMPTY tank (0.0) — a fact, not missing.
        m.save_fuel_water_inventory({
            "well_id": ids["well"], "report_id": ids["r2"],
            "report_date": date(2026, 3, 2),
            "fuel_stock": 0.0, "fuel_consumed": 0.0})
        row = _row(m, ids, ids["r2"])
        assert row["fuel_stock"] == 0.0     # not overwritten with 90
        assert row["fuel_remaining"] == 0.0
