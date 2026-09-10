"""Inventory zero-vs-missing semantics regressions (2026-09-10 phase).

Non-negotiable invariant under test:

    State A: source explicitly reports opening = 0   -> a real fact (0.0)
    State B: opening value is absent                  -> missing (NULL/None)
    State C: opening is nonzero                       -> the real value

    These three states must never collapse into one another, and
    carry-forward is a fallback for MISSING opening data only — never a
    replacement for an explicit opening value.

Fixed violations proven here:
  A. ledger carry-forward  — core/mud_ledger.py treated an explicit 0
     opening (with no movement) as missing and overwrote it with the
     previous closing.
  B. save path             — core/database.py save_bulk_material's
     carry_forward (default True) overwrote even explicitly supplied
     nonzero openings; missing became 0.0.
  C. import normalization  — core/profile_import_engine.py coerced
     missing stock to 0.0 (``initial or 0.0``), destroying the
     missing/zero distinction before persistence.

All tests exercise real production code (DatabaseManager.save_bulk_material,
MudChemicalLedger, save_imported_multi_tab_data_atomic, the profile
extractor) against isolated databases. No mocks or stubs are used.
"""

import json
from datetime import date

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base, DatabaseManager, BulkMaterials, Company, Project, Well, Section,
    DailyReport,
)
from core.mud_ledger import MudChemicalLedger, LedgerEntry


def memory_manager():
    manager = DatabaseManager()
    manager.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(
        bind=manager.engine, autoflush=False, autocommit=False
    )
    session = manager.create_session()
    try:
        company = Company(name="OEOC", code="OEOC")
        session.add(company)
        session.flush()
        project = Project(name="Bid Boland", code="BB", company_id=company.id)
        session.add(project)
        session.flush()
        well = Well(name="Zero-Semantics", code="ZS-1", project_id=project.id)
        session.add(well)
        session.commit()
        well_id = well.id
    finally:
        session.close()
    return manager, well_id


@pytest.fixture
def env():
    manager, well_id = memory_manager()
    yield manager, well_id
    manager.close()


def fetch_row(manager, well_id, d):
    session = manager.create_session()
    try:
        return session.query(BulkMaterials).filter(
            BulkMaterials.well_id == well_id,
            BulkMaterials.report_date == d,
            BulkMaterials.material_name == "Barite",
        ).one()
    finally:
        session.close()


# =====================================================================
# Save path — explicit zero (State A)
# =====================================================================

class TestSavePathExplicitZero:
    def test_explicit_zero_opening_not_replaced_by_previous_closing(self, env):
        manager, well_id = env
        # Day 1: real stock, closing 100.
        manager.save_bulk_material({
            "well_id": well_id, "report_date": date(2024, 10, 1),
            "material_name": "Barite", "unit": "kg",
            "initial_stock": 100.0, "received": 0.0, "used": 0.0,
        })
        # Day 2: the report explicitly says stock is ZERO.
        manager.save_bulk_material({
            "well_id": well_id, "report_date": date(2024, 10, 2),
            "material_name": "Barite", "unit": "kg",
            "initial_stock": 0.0, "received": 0.0, "used": 0.0,
        })
        row = fetch_row(manager, well_id, date(2024, 10, 2))
        # Old code: carry_forward overwrote the explicit 0.0 with 100.
        assert row.initial_stock == 0.0
        assert row.current_stock == 0.0

    def test_update_branch_preserves_explicit_zero(self, env):
        manager, well_id = env
        manager.save_bulk_material({
            "well_id": well_id, "report_date": date(2024, 10, 1),
            "material_name": "Barite", "initial_stock": 500.0,
            "received": 0.0, "used": 0.0,
        })
        # Same well+date+material -> UPDATE branch.
        manager.save_bulk_material({
            "well_id": well_id, "report_date": date(2024, 10, 1),
            "material_name": "Barite", "initial_stock": 0.0,
            "received": 0.0, "used": 0.0,
        })
        row = fetch_row(manager, well_id, date(2024, 10, 1))
        assert row.initial_stock == 0.0
        assert row.current_stock == 0.0


# =====================================================================
# Save path — missing (State B)
# =====================================================================

class TestSavePathMissing:
    def test_missing_opening_without_previous_stays_null(self, env):
        manager, well_id = env
        manager.save_bulk_material({
            "well_id": well_id, "report_date": date(2024, 10, 1),
            "material_name": "Barite", "received": 10.0, "used": 4.0,
            # no initial_stock supplied
        })
        row = fetch_row(manager, well_id, date(2024, 10, 1))
        # Old code persisted 0.0 — missing collapsed into zero.
        assert row.initial_stock is None
        # Closing is unknown too — never fabricated from a 0 opening.
        assert row.current_stock is None

    def test_missing_opening_carries_previous_closing(self, env):
        """Carry-forward remains available for genuinely missing data."""
        manager, well_id = env
        manager.save_bulk_material({
            "well_id": well_id, "report_date": date(2024, 10, 1),
            "material_name": "Barite", "initial_stock": 100.0,
            "received": 20.0, "used": 30.0,   # closing 90
        })
        manager.save_bulk_material({
            "well_id": well_id, "report_date": date(2024, 10, 2),
            "material_name": "Barite", "received": 0.0, "used": 10.0,
            # opening not reported
        })
        row = fetch_row(manager, well_id, date(2024, 10, 2))
        assert row.initial_stock == 90.0        # carried from closing
        assert row.current_stock == 80.0        # 90 + 0 - 10

    def test_update_branch_missing_opening_gives_unknown_closing(self, env):
        manager, well_id = env
        manager.save_bulk_material({
            "well_id": well_id, "report_date": date(2024, 10, 1),
            "material_name": "Barite", "initial_stock": 5.0,
        })
        # Update that clears the opening to missing.
        manager.save_bulk_material({
            "well_id": well_id, "report_date": date(2024, 10, 1),
            "material_name": "Barite", "initial_stock": None,
            "received": 0.0, "used": 0.0,
        })
        row = fetch_row(manager, well_id, date(2024, 10, 1))
        assert row.initial_stock is None
        assert row.current_stock is None


# =====================================================================
# Save path — nonzero (State C)
# =====================================================================

class TestSavePathNonzero:
    def test_explicit_nonzero_not_overwritten_by_carry_forward(self, env):
        manager, well_id = env
        manager.save_bulk_material({
            "well_id": well_id, "report_date": date(2024, 10, 1),
            "material_name": "Barite", "initial_stock": 100.0,
            "received": 0.0, "used": 0.0,
        })
        manager.save_bulk_material({
            "well_id": well_id, "report_date": date(2024, 10, 2),
            "material_name": "Barite", "initial_stock": 250.0,
            "received": 0.0, "used": 0.0,
            # carry_forward defaults True — but 250.0 is explicit.
        })
        row = fetch_row(manager, well_id, date(2024, 10, 2))
        # Old code: carry_forward replaced the explicit 250.0 with 100.0.
        assert row.initial_stock == 250.0
        assert row.current_stock == 250.0

    def test_carry_forward_false_leaves_opening_missing(self, env):
        manager, well_id = env
        manager.save_bulk_material({
            "well_id": well_id, "report_date": date(2024, 10, 1),
            "material_name": "Barite", "initial_stock": 100.0,
        })
        manager.save_bulk_material({
            "well_id": well_id, "report_date": date(2024, 10, 2),
            "material_name": "Barite", "received": 5.0, "used": 0.0,
            "carry_forward": False,
        })
        row = fetch_row(manager, well_id, date(2024, 10, 2))
        assert row.initial_stock is None
        assert row.current_stock is None


# =====================================================================
# A. Ledger carry-forward — explicit zero never replaced
# =====================================================================

class TestLedgerCarryForward:
    def _add_row(self, manager, well_id, d, initial, received, used):
        session = manager.create_session()
        try:
            session.add(BulkMaterials(
                well_id=well_id, report_date=d, material_name="Barite",
                unit="kg", initial_stock=initial, received=received,
                used=used,
                current_stock=(
                    initial + received - used
                    if initial is not None else None
                ),
            ))
            session.commit()
        finally:
            session.close()

    def test_ledger_three_state_sequence(self, env):
        manager, well_id = env
        # Day 1: nonzero fact. Day 2: opening missing (NULL). Day 3:
        # explicit zero fact.
        self._add_row(manager, well_id, date(2024, 10, 1), 100.0, 0.0, 20.0)
        self._add_row(manager, well_id, date(2024, 10, 2), None, 0.0, 30.0)
        self._add_row(manager, well_id, date(2024, 10, 3), 0.0, 0.0, 0.0)

        entries = MudChemicalLedger(manager).get_ledger_for_well(well_id)
        by_date = {e.date: e for e in entries}

        # Day 1: fact used as-is.
        assert by_date[date(2024, 10, 1)].opening_stock == 100.0
        assert by_date[date(2024, 10, 1)].closing_stock == 80.0

        # Day 2: missing opening carried from previous closing (80),
        # even though the row has movements (old heuristic refused).
        assert by_date[date(2024, 10, 2)].opening_stock == 80.0
        assert by_date[date(2024, 10, 2)].closing_stock == 50.0

        # Day 3: explicit zero is a FACT — old code replaced it with 80.
        assert by_date[date(2024, 10, 3)].opening_stock == 0.0
        assert by_date[date(2024, 10, 3)].closing_stock == 0.0

    def test_ledger_unknown_opening_propagates_unknown_closing(self, env):
        manager, well_id = env
        self._add_row(manager, well_id, date(2024, 10, 1), None, 0.0, 5.0)
        entries = MudChemicalLedger(manager).get_ledger_for_well(well_id)
        assert entries[0].opening_stock is None
        assert entries[0].closing_stock is None

    def test_ledger_validate_tolerates_unknown_stock(self, env):
        manager, well_id = env
        self._add_row(manager, well_id, date(2024, 10, 1), None, 0.0, 5.0)
        self._add_row(manager, well_id, date(2024, 10, 2), 10.0, 0.0, 40.0)
        ledger = MudChemicalLedger(manager)
        alerts = ledger.validate(ledger.get_ledger_for_well(well_id))
        # The unknown row produces no false alerts; the known row flags
        # unusual consumption as designed.
        types = [a["type"] for a in alerts]
        assert "Unusual Consumption" in types
        assert all(a["date"] != date(2024, 10, 1) for a in alerts)


# =====================================================================
# C. Import normalization — extraction preserves the trichotomy
# =====================================================================

class TestImportNormalization:
    def _engine_with_bulk_cache(self):
        from core.profile_import_engine import ProfileImportEngine

        engine = ProfileImportEngine(None)
        engine.cell_cache = {
            "DDR Data": {
                10: {1: "Bulk Data"},
                11: {1: "Mat. Type", 2: "Unit", 3: "Barite", 4: "Diesel"},
                12: {1: "on hand (kg)", 3: 45, 4: None},
                13: {1: "used", 3: 5, 4: 100},
                14: {1: "received", 3: 0, 4: 50},
            }
        }
        # Same default shape analyze_and_extract() passes in.
        result = {"bulk_materials": []}
        engine._extract_embedded_ddr_data(result)
        return result

    def test_missing_stock_extracts_as_none_not_zero(self):
        result = self._engine_with_bulk_cache()
        rows = {r["material_name"]: r for r in result["bulk_materials"]}

        barite = rows["Barite"]
        assert barite["initial_stock"] == 45.0
        assert barite["current_stock"] == 45.0 + 0 - 5

        # Diesel has movements but no on-hand value: the old code
        # fabricated initial 0.0 and a derived closing.
        diesel = rows["Diesel"]
        assert diesel["initial_stock"] is None
        assert diesel["current_stock"] is None
        assert diesel["used"] == 100.0
        assert diesel["received"] == 50.0

    def test_explicit_zero_stock_extracts_as_zero(self):
        from core.profile_import_engine import ProfileImportEngine

        engine = ProfileImportEngine(None)
        engine.cell_cache = {
            "DDR Data": {
                10: {1: "Bulk Data"},
                11: {1: "Mat. Type", 2: "Unit", 3: "Barite"},
                12: {1: "on hand (kg)", 3: 0},
                13: {1: "used", 3: 0},
                14: {1: "received", 3: 0},
            }
        }
        result = {"bulk_materials": []}
        engine._extract_embedded_ddr_data(result)
        barite = result["bulk_materials"][0]
        # An explicit 0 in the sheet is a reported zero, not missing.
        assert barite["initial_stock"] == 0.0
        assert barite["current_stock"] == 0.0

    def test_atomic_import_persists_null_not_zero(self, tmp_path):
        """End-to-end: extracted rows persist NULL through the atomic
        importer (movement-only Diesel row)."""
        manager = DatabaseManager()
        manager.db_path = str(tmp_path / "atomic.db")
        assert manager.initialize()
        try:
            with manager.session_scope() as session:
                company = session.get(Company, 1)
                company.name, company.code = "OP", "OP"
                project = session.get(Project, 1)
                project.name, project.code = "AT", "AT"
                well = session.get(Well, 1)
                well.name, well.code = "Atomic Well", "AW"
                section = Section(name="S", well_id=well.id)
                session.add(section)
                session.flush()
                report = DailyReport(
                    well_id=well.id, section_id=section.id,
                    report_number=1, report_date=date(2024, 10, 22),
                )
                session.add(report)
                session.flush()
                report_id = report.id
                well_id = well.id

            result = manager.save_imported_multi_tab_data_atomic(
                well_id, report_id,
                {
                    "bulk_materials": [
                        # fuel/water-routed rows land in BulkMaterials
                        {"material_name": "Diesel", "initial_stock": None,
                         "received": 50.0, "used": 100.0},
                        {"material_name": "Fresh Water", "initial_stock": 0.0,
                         "received": 0.0, "used": 0.0,
                         "current_stock": 0.0},
                    ]
                },
            )
            assert result["failed"] == 0

            session = manager.create_session()
            try:
                rows = {
                    r.material_name: r
                    for r in session.query(BulkMaterials).all()
                }
                # Missing opening persists as NULL (old: 0.0).
                assert rows["Diesel"].initial_stock is None
                assert rows["Diesel"].current_stock is None
                # Explicit zero persists as 0.0.
                assert rows["Fresh Water"].initial_stock == 0.0
            finally:
                session.close()
        finally:
            manager.close()


# =====================================================================
# Repeated import — no transformation, no duplication
# =====================================================================

class TestRepeatedImport:
    def test_save_path_reimport_is_idempotent(self, env):
        manager, well_id = env
        payload = {
            "well_id": well_id, "report_date": date(2024, 10, 1),
            "material_name": "Barite", "initial_stock": 0.0,
            "received": 0.0, "used": 0.0,
        }
        manager.save_bulk_material(dict(payload))
        manager.save_bulk_material(dict(payload))  # re-import same report

        session = manager.create_session()
        try:
            rows = session.query(BulkMaterials).filter(
                BulkMaterials.well_id == well_id,
                BulkMaterials.material_name == "Barite",
            ).all()
        finally:
            session.close()
        assert len(rows) == 1
        # Explicit zero survived the round-trip unchanged.
        assert rows[0].initial_stock == 0.0
        assert rows[0].current_stock == 0.0

    def test_atomic_reimport_upserts_not_duplicates(self, tmp_path):
        manager = DatabaseManager()
        manager.db_path = str(tmp_path / "atomic2.db")
        assert manager.initialize()
        try:
            with manager.session_scope() as session:
                well = session.get(Well, 1)
                well.name, well.code = "Atomic Well 2", "AW2"
                section = Section(name="S", well_id=well.id)
                session.add(section)
                session.flush()
                report = DailyReport(
                    well_id=well.id, section_id=section.id,
                    report_number=1, report_date=date(2024, 10, 22),
                )
                session.add(report)
                session.flush()
                report_id, well_id = report.id, well.id

            data = {
                "bulk_materials": [
                    {"material_name": "Diesel", "initial_stock": 0.0,
                     "received": 10.0, "used": 5.0},
                ]
            }
            assert manager.save_imported_multi_tab_data_atomic(
                well_id, report_id, data)["failed"] == 0
            assert manager.save_imported_multi_tab_data_atomic(
                well_id, report_id, json.loads(json.dumps(data)))["failed"] == 0

            session = manager.create_session()
            try:
                rows = session.query(BulkMaterials).filter(
                    BulkMaterials.report_id == report_id
                ).all()
            finally:
                session.close()
            # Old code: re-import ADDED a duplicate row.
            assert len(rows) == 1
            # And the values were not transformed by the round-trip.
            assert rows[0].initial_stock == 0.0
            assert rows[0].received == 10.0
            assert rows[0].used == 5.0
            assert rows[0].current_stock == 5.0
        finally:
            manager.close()


# =====================================================================
# Ledger entry dataclass — the trichotomy at the representation level
# =====================================================================

class TestLedgerEntryRepresentation:
    def test_three_states_stay_distinct(self):
        from datetime import date as d
        missing = LedgerEntry(date=d(2024, 1, 1), material_name="X")
        zero = LedgerEntry(
            date=d(2024, 1, 1), material_name="X", opening_stock=0.0
        )
        nonzero = LedgerEntry(
            date=d(2024, 1, 1), material_name="X", opening_stock=12.5
        )
        assert missing.opening_stock is None and missing.closing_stock is None
        assert zero.opening_stock == 0.0 and zero.closing_stock == 0.0
        assert nonzero.opening_stock == 12.5
        assert nonzero.closing_stock == 12.5
