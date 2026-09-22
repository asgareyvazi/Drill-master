"""General-inventory (InventoryItem) authority regressions — Mission 21.

Establishes ONE authoritative persistence path for W5 general consumable
inventory, distinct from the mud/drilling ``BulkMaterials`` ledger and the
``FuelWaterInventory`` schema. Locks:

  * structured persistence (no EquipmentLog notes string as source of truth)
  * identity = (well_id, report_id, item_name)
  * three-state numeric semantics (None / 0.0 / value)
  * closing derivation (opening + received - used; None when opening unknown)
  * carry-forward fills only a MISSING opening, never overwrites explicit 0
  * atomic worksheet save (all-or-nothing), idempotent re-save, clear->empty
  * scope isolation across wells and reports
  * legacy EquipmentLog.notes decoded read-only (unknown preserved)

All tests use a real in-memory DatabaseManager; no mocks.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base, DatabaseManager, Company, Project, Well, DailyReport,
    EquipmentLog,
)
from core import inventory_semantics as inv


def memory_manager():
    m = DatabaseManager()
    m.engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    s = m.create_session()
    try:
        c = Company(name="OEOC", code="OEOC"); s.add(c); s.flush()
        p = Project(name="BB", code="BB", company_id=c.id); s.add(p); s.flush()
        w1 = Well(name="W1", code="W1", project_id=p.id); s.add(w1); s.flush()
        w2 = Well(name="W2", code="W2", project_id=p.id); s.add(w2); s.flush()
        reports = {}
        for wid, d in ((w1.id, date(2026, 1, 1)), (w1.id, date(2026, 1, 2)),
                       (w1.id, date(2026, 1, 3)), (w1.id, date(2026, 1, 4)),
                       (w2.id, date(2026, 1, 1))):
            r = DailyReport(well_id=wid, report_date=d); s.add(r); s.flush()
            reports[(wid, d)] = r.id
        s.commit()
        ids = {"w1": w1.id, "w2": w2.id, "reports": reports}
    finally:
        s.close()
    return m, ids


@pytest.fixture
def env():
    m, ids = memory_manager()
    yield m, ids
    m.close()


# ---------------------------------------------------------------------------
# Semantics helper
# ---------------------------------------------------------------------------

class TestSemantics:
    def test_blank_is_unknown_not_zero(self):
        assert inv.to_float_or_none("") is None
        assert inv.to_float_or_none(None) is None
        assert inv.to_float_or_none("  ") is None

    def test_explicit_zero_is_a_fact(self):
        assert inv.to_float_or_none("0") == 0.0
        assert inv.to_float_or_none(0) == 0.0

    def test_closing_unknown_when_opening_unknown(self):
        assert inv.derive_closing(None, 5, 2) is None

    def test_closing_derived_when_opening_known(self):
        assert inv.derive_closing(100, 20, 10) == 110.0

    def test_movement_absence_is_zero(self):
        assert inv.normalize_movement("") == 0.0
        assert inv.normalize_movement(None) == 0.0


# ---------------------------------------------------------------------------
# Persistence / identity
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_round_trip_structured_fields(self, env):
        m, ids = env
        rid = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        m.save_inventory_items(ids["w1"], rid, [{
            "item_name": "Gloves", "category": "PPE", "opening_stock": "100",
            "received": "20", "used": "10", "unit": "pcs",
            "min_level": "10", "max_level": "500"}],
            report_date=date(2026, 1, 1))
        it = m.get_inventory_items(well_id=ids["w1"], report_id=rid)[0]
        assert it["category"] == "PPE"
        assert it["opening_stock"] == 100.0
        assert it["current_stock"] == 110.0
        assert it["min_level"] == 10.0 and it["max_level"] == 500.0
        assert it["unit"] == "pcs"

    def test_unknown_opening_stays_null(self, env):
        m, ids = env
        rid = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        m.save_inventory_items(ids["w1"], rid, [{
            "item_name": "Rags", "opening_stock": "", "received": "5", "used": "0"}],
            report_date=date(2026, 1, 1))
        it = m.get_inventory_items(well_id=ids["w1"], report_id=rid)[0]
        assert it["opening_stock"] is None
        assert it["current_stock"] is None  # never fabricated 0

    def test_explicit_zero_opening_preserved(self, env):
        m, ids = env
        rid = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        m.save_inventory_items(ids["w1"], rid, [{
            "item_name": "Widget", "opening_stock": "0", "received": "0", "used": "0"}],
            report_date=date(2026, 1, 1))
        it = m.get_inventory_items(well_id=ids["w1"], report_id=rid)[0]
        assert it["opening_stock"] == 0.0
        assert it["current_stock"] == 0.0

    def test_blank_item_name_dropped(self, env):
        m, ids = env
        rid = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        saved = m.save_inventory_items(ids["w1"], rid, [
            {"item_name": "  ", "opening_stock": "5"},
            {"item_name": "Real", "opening_stock": "1"}],
            report_date=date(2026, 1, 1))
        assert saved == 1
        rows = m.get_inventory_items(well_id=ids["w1"], report_id=rid)
        assert [r["item_name"] for r in rows] == ["Real"]

    def test_resave_is_idempotent(self, env):
        m, ids = env
        rid = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        rows = [{"item_name": "Bolts", "opening_stock": "50", "received": "0", "used": "0"}]
        m.save_inventory_items(ids["w1"], rid, rows, report_date=date(2026, 1, 1))
        m.save_inventory_items(ids["w1"], rid, rows, report_date=date(2026, 1, 1))
        m.save_inventory_items(ids["w1"], rid, rows, report_date=date(2026, 1, 1))
        assert len(m.get_inventory_items(well_id=ids["w1"], report_id=rid)) == 1

    def test_clear_then_save_empties_report(self, env):
        m, ids = env
        rid = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        m.save_inventory_items(ids["w1"], rid, [
            {"item_name": "A", "opening_stock": "1"}], report_date=date(2026, 1, 1))
        m.save_inventory_items(ids["w1"], rid, [], report_date=date(2026, 1, 1))
        assert m.get_inventory_items(well_id=ids["w1"], report_id=rid) == []


# ---------------------------------------------------------------------------
# Carry-forward
# ---------------------------------------------------------------------------

class TestCarryForward:
    def test_sequence_100_missing_zero_250(self, env):
        m, ids = env
        seq = [(date(2026, 1, 1), "100"), (date(2026, 1, 2), ""),
               (date(2026, 1, 3), "0"), (date(2026, 1, 4), "250")]
        for d, opening in seq:
            rid = ids["reports"][(ids["w1"], d)]
            m.save_inventory_items(ids["w1"], rid, [
                {"item_name": "Barite", "opening_stock": opening,
                 "received": "0", "used": "0"}], report_date=d)
        openings = []
        for d, _ in seq:
            rid = ids["reports"][(ids["w1"], d)]
            openings.append(m.get_inventory_items(well_id=ids["w1"], report_id=rid)[0]["opening_stock"])
        # missing carries previous closing (100); explicit 0 stays 0.
        assert openings == [100.0, 100.0, 0.0, 250.0]


# ---------------------------------------------------------------------------
# Scope isolation
# ---------------------------------------------------------------------------

class TestScope:
    def test_wells_never_merge(self, env):
        m, ids = env
        r1 = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        r2 = ids["reports"][(ids["w2"], date(2026, 1, 1))]
        m.save_inventory_items(ids["w1"], r1, [
            {"item_name": "Sand", "opening_stock": "10"}], report_date=date(2026, 1, 1))
        m.save_inventory_items(ids["w2"], r2, [
            {"item_name": "Sand", "opening_stock": "99"}], report_date=date(2026, 1, 1))
        assert m.get_inventory_items(well_id=ids["w1"], report_id=r1)[0]["opening_stock"] == 10.0
        assert m.get_inventory_items(well_id=ids["w2"], report_id=r2)[0]["opening_stock"] == 99.0

    def test_reports_are_distinct_records(self, env):
        m, ids = env
        r1 = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        r2 = ids["reports"][(ids["w1"], date(2026, 1, 2))]
        m.save_inventory_items(ids["w1"], r1, [
            {"item_name": "Pipe dope", "opening_stock": "5"}], report_date=date(2026, 1, 1))
        m.save_inventory_items(ids["w1"], r2, [
            {"item_name": "Pipe dope", "opening_stock": "8"}], report_date=date(2026, 1, 2))
        assert len(m.get_inventory_items(well_id=ids["w1"])) == 2
        assert m.get_inventory_items(well_id=ids["w1"], report_id=r1)[0]["opening_stock"] == 5.0
        assert m.get_inventory_items(well_id=ids["w1"], report_id=r2)[0]["opening_stock"] == 8.0


# ---------------------------------------------------------------------------
# Item-name identity within a worksheet (§3)
# ---------------------------------------------------------------------------

class TestIdentity:
    def test_exact_duplicate_names_rejected(self, env):
        m, ids = env
        rid = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        with pytest.raises(ValueError):
            m.save_inventory_items(ids["w1"], rid, [
                {"item_name": "A", "opening_stock": "1"},
                {"item_name": "A", "opening_stock": "2"}],
                report_date=date(2026, 1, 1))

    def test_whitespace_only_difference_is_duplicate(self, env):
        m, ids = env
        rid = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        with pytest.raises(ValueError):
            m.save_inventory_items(ids["w1"], rid, [
                {"item_name": "Barite", "opening_stock": "1"},
                {"item_name": "  Barite  ", "opening_stock": "2"}],
                report_date=date(2026, 1, 1))

    def test_case_distinct_names_are_allowed(self, env):
        # Normalization policy (normalize_item_row) is case-SENSITIVE: 'c' and
        # 'C' are distinct items, not a duplicate.
        m, ids = env
        rid = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        n = m.save_inventory_items(ids["w1"], rid, [
            {"item_name": "c", "opening_stock": "1"},
            {"item_name": "C", "opening_stock": "2"}],
            report_date=date(2026, 1, 1))
        assert n == 2

    def test_distinct_names_saved(self, env):
        m, ids = env
        rid = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        n = m.save_inventory_items(ids["w1"], rid, [
            {"item_name": "A", "opening_stock": "1"},
            {"item_name": "B", "opening_stock": "2"}],
            report_date=date(2026, 1, 1))
        assert n == 2

    def test_same_name_across_reports_is_fine(self, env):
        m, ids = env
        r1 = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        r2 = ids["reports"][(ids["w1"], date(2026, 1, 2))]
        m.save_inventory_items(ids["w1"], r1, [
            {"item_name": "A", "opening_stock": "1"}], report_date=date(2026, 1, 1))
        m.save_inventory_items(ids["w1"], r2, [
            {"item_name": "A", "opening_stock": "2"}], report_date=date(2026, 1, 2))
        assert len(m.get_inventory_items(well_id=ids["w1"])) == 2

    def test_duplicate_rejection_preserves_original_worksheet(self, env):
        # A duplicate-triggered failure must NOT partially save nor wipe the
        # previously persisted worksheet (the delete is rolled back).
        m, ids = env
        rid = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        m.save_inventory_items(ids["w1"], rid, [
            {"item_name": "Gloves", "opening_stock": "100"}],
            report_date=date(2026, 1, 1))
        with pytest.raises(ValueError):
            m.save_inventory_items(ids["w1"], rid, [
                {"item_name": "Gloves", "opening_stock": "9"},
                {"item_name": "Gloves", "opening_stock": "9"}],
                report_date=date(2026, 1, 1))
        rows = m.get_inventory_items(well_id=ids["w1"], report_id=rid)
        assert [(r["item_name"], r["opening_stock"]) for r in rows] == [("Gloves", 100.0)]

    def test_resave_after_dedup_is_idempotent(self, env):
        m, ids = env
        rid = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        rows = [{"item_name": "A", "opening_stock": "1"},
                {"item_name": "B", "opening_stock": "2"}]
        m.save_inventory_items(ids["w1"], rid, rows, report_date=date(2026, 1, 1))
        m.save_inventory_items(ids["w1"], rid, rows, report_date=date(2026, 1, 1))
        assert len(m.get_inventory_items(well_id=ids["w1"], report_id=rid)) == 2


# ---------------------------------------------------------------------------
# Atomicity
# ---------------------------------------------------------------------------

class TestAtomicity:
    def test_row_failure_rolls_back_whole_save(self, env, monkeypatch):
        m, ids = env
        rid = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        # Seed one good row first.
        m.save_inventory_items(ids["w1"], rid, [
            {"item_name": "Seed", "opening_stock": "1"}], report_date=date(2026, 1, 1))

        # Force a failure mid-save; the replace-delete + inserts must all roll
        # back, leaving the previously-seeded row intact.
        import core.inventory_semantics as sem
        real = sem.derive_closing
        calls = {"n": 0}

        def boom(*a, **k):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("injected fault")
            return real(*a, **k)

        # database.py imports derive_closing locally inside the method, so
        # patching the source-module function is what the method will see.
        monkeypatch.setattr(sem, "derive_closing", boom)

        with pytest.raises(RuntimeError):
            m.save_inventory_items(ids["w1"], rid, [
                {"item_name": "One", "opening_stock": "10"},
                {"item_name": "Two", "opening_stock": "20"}],
                report_date=date(2026, 1, 1))
        monkeypatch.setattr(sem, "derive_closing", real)
        # The original seeded row survived (no partial replace).
        rows = m.get_inventory_items(well_id=ids["w1"], report_id=rid)
        assert [r["item_name"] for r in rows] == ["Seed"]


# ---------------------------------------------------------------------------
# Legacy notes compatibility (read-only)
# ---------------------------------------------------------------------------

class TestLegacy:
    def test_legacy_notes_decoded_unknown_preserved(self, env):
        m, ids = env
        rid = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        s = m.create_session()
        try:
            s.add(EquipmentLog(
                well_id=ids["w1"], report_id=rid, equipment_type="Inventory",
                equipment_name="OldItem", equipment_id="Cat",
                notes="Stock:100|Recv:|Used:5|Rem:95|Unit:kg"))
            s.commit()
        finally:
            s.close()
        rows = m.get_legacy_inventory_notes(ids["w1"], report_id=rid)
        assert rows[0]["item_name"] == "OldItem"
        assert rows[0]["opening_stock"] == 100.0
        assert rows[0]["received"] is None  # blank stays unknown, not 0
        assert rows[0]["used"] == 5.0
        assert rows[0]["unit"] == "kg"

    def test_authoritative_takes_precedence_over_legacy(self, env):
        m, ids = env
        rid = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        # Legacy row exists...
        s = m.create_session()
        try:
            s.add(EquipmentLog(
                well_id=ids["w1"], report_id=rid, equipment_type="Inventory",
                equipment_name="Legacy", notes="Stock:1|Unit:kg"))
            s.commit()
        finally:
            s.close()
        # ...but an authoritative InventoryItem also exists.
        m.save_inventory_items(ids["w1"], rid, [
            {"item_name": "Current", "opening_stock": "7"}], report_date=date(2026, 1, 1))
        current = m.get_inventory_items(well_id=ids["w1"], report_id=rid)
        assert [r["item_name"] for r in current] == ["Current"]

    def test_save_retires_legacy_for_same_scope(self, env):
        # Saving the worksheet is the explicit migration act: legacy notes for
        # the SAME (well, report) are retired so they can never shadow the
        # authoritative store afterward.
        m, ids = env
        rid = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        s = m.create_session()
        try:
            s.add(EquipmentLog(
                well_id=ids["w1"], report_id=rid, equipment_type="Inventory",
                equipment_name="Legacy", notes="Stock:1|Unit:kg"))
            s.commit()
        finally:
            s.close()
        assert len(m.get_legacy_inventory_notes(ids["w1"], report_id=rid)) == 1
        m.save_inventory_items(ids["w1"], rid, [
            {"item_name": "Current", "opening_stock": "7"}],
            report_date=date(2026, 1, 1))
        assert m.get_legacy_inventory_notes(ids["w1"], report_id=rid) == []

    def test_clear_then_save_does_not_resurrect_legacy(self, env):
        # The §5 resurrection bug: legacy load -> clear all -> save empty ->
        # reload previously re-surfaced legacy rows. After retirement, a cleared
        # worksheet stays empty on reload.
        m, ids = env
        rid = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        s = m.create_session()
        try:
            s.add(EquipmentLog(
                well_id=ids["w1"], report_id=rid, equipment_type="Inventory",
                equipment_name="Legacy", notes="Stock:100|Unit:kg"))
            s.commit()
        finally:
            s.close()
        # User clears the worksheet and saves (empty rows).
        m.save_inventory_items(ids["w1"], rid, [], report_date=date(2026, 1, 1))
        # Neither authoritative nor legacy rows remain -> nothing to resurrect.
        assert m.get_inventory_items(well_id=ids["w1"], report_id=rid) == []
        assert m.get_legacy_inventory_notes(ids["w1"], report_id=rid) == []

    def test_retirement_is_scoped_to_report_and_inventory_type(self, env):
        # Retirement must not touch other reports' legacy inventory, nor
        # non-inventory EquipmentLog rows.
        m, ids = env
        rid1 = ids["reports"][(ids["w1"], date(2026, 1, 1))]
        rid2 = ids["reports"][(ids["w1"], date(2026, 1, 2))]
        s = m.create_session()
        try:
            for rid in (rid1, rid2):
                s.add(EquipmentLog(
                    well_id=ids["w1"], report_id=rid, equipment_type="Inventory",
                    equipment_name="Legacy", notes="Stock:1|Unit:kg"))
            s.add(EquipmentLog(
                well_id=ids["w1"], report_id=rid1, equipment_type="Rig Equipment",
                equipment_name="Pump", notes="ok"))
            s.commit()
        finally:
            s.close()
        m.save_inventory_items(ids["w1"], rid1, [
            {"item_name": "Current", "opening_stock": "7"}],
            report_date=date(2026, 1, 1))
        # report 1 legacy retired, report 2 legacy intact
        assert m.get_legacy_inventory_notes(ids["w1"], report_id=rid1) == []
        assert len(m.get_legacy_inventory_notes(ids["w1"], report_id=rid2)) == 1
        # Non-inventory equipment survives
        s = m.create_session()
        try:
            n = s.query(EquipmentLog).filter_by(
                well_id=ids["w1"], equipment_type="Rig Equipment").count()
        finally:
            s.close()
        assert n == 1
