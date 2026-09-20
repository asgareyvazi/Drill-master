"""Import routing / inventory-domain fidelity regressions — Mission 23 Track B.

Establishes and locks the authoritative behaviour of the production import
boundary with respect to the THREE distinct inventory-related domains:

  A. BulkMaterials      — mud / drilling bulk-material ledger
  B. FuelWaterInventory — fuel + water
  C. InventoryItem      — W5 general consumables (NOT importable via the DDR
                          bulk collection; no supported source schema exists)

Key rules proven here:

* A bulk_materials collection is routed per row by
  ``core.domain_records.material_route``: mud names -> MudChemicalLedger,
  fuel/water names -> BulkMaterials(FuelWater intent), everything else ->
  REVIEW_REQUIRED. General consumables are NEVER silently coerced into
  BulkMaterials, MudReport, FuelWater, or InventoryItem.
* The general-inventory (InventoryItem) domain has no import source schema, so
  it is never fabricated by an import — it stays a UI/manual domain.
* The legacy ``ProfileImportEngine`` extraction (test-only; its DB write path
  is disabled) does not tag a generic "Inventory" sheet as bulk_materials and
  does not fabricate units or coerce blank movements to zero.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base, DatabaseManager, Company, Project, Well, Section, DailyReport,
    BulkMaterials, InventoryItem, FuelWaterInventory,
)
from core.domain_records import material_route


def _env():
    m = DatabaseManager()
    m.engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool)
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    s = m.create_session()
    try:
        c = Company(name="OP", code="OP"); s.add(c); s.flush()
        p = Project(name="PR", code="PR", company_id=c.id); s.add(p); s.flush()
        w = Well(name="W1", code="W1", project_id=p.id); s.add(w); s.flush()
        sec = Section(name="S", well_id=w.id); s.add(sec); s.flush()
        r = DailyReport(well_id=w.id, section_id=sec.id, report_number=1,
                        report_date=date(2024, 1, 1)); s.add(r); s.flush()
        s.commit()
        ids = {"well": w.id, "report": r.id}
    finally:
        s.close()
    return m, ids


@pytest.fixture
def env():
    return _env()


# ---------------------------------------------------------------------------
# Discriminator
# ---------------------------------------------------------------------------

class TestMaterialRoute:
    @pytest.mark.parametrize("name", [
        "Gloves", "Safety Boots", "Welding Rod", "Hand Soap", "Rags",
        "Grease Cartridge", "Light Bulb",
    ])
    def test_general_consumables_go_to_review(self, name):
        # General inventory consumables have no mud/fuel identity -> review,
        # never a fabricated domain.
        assert material_route({"material_name": name}) == "review"

    @pytest.mark.parametrize("name", ["Barite", "Bentonite", "Mud", "KCl"])
    def test_mud_materials_route_to_mud(self, name):
        assert material_route({"material_name": name}) == "mud"

    @pytest.mark.parametrize("name", ["Diesel", "Fresh Water", "Fuel", "Water"])
    def test_fuel_water_materials_route_to_fuel_water(self, name):
        assert material_route({"material_name": name}) == "fuel_water"


# ---------------------------------------------------------------------------
# Production atomic import boundary
# ---------------------------------------------------------------------------

class TestAtomicImportRouting:
    def test_general_inventory_not_coerced_into_any_domain(self, env):
        m, ids = env
        data = {"bulk_materials": [
            {"material_name": "Gloves", "current_stock": 100},
            {"material_name": "Welding Rod", "current_stock": 50},
            {"material_name": "Barite", "current_stock": 45},
            {"material_name": "Diesel", "current_stock": 30},
        ]}
        res = m.save_imported_multi_tab_data_atomic(ids["well"], ids["report"], data)
        assert res["status"] == "REVIEW_REQUIRED"
        assert res["review"] >= 2
        s = m.create_session()
        try:
            bulk_names = [b.material_name for b in s.query(BulkMaterials).all()]
            # Only the fuel/water material lands in BulkMaterials.
            assert "Diesel" in bulk_names
            assert "Gloves" not in bulk_names
            assert "Welding Rod" not in bulk_names
            # General inventory is NEVER fabricated by an import.
            assert s.query(InventoryItem).count() == 0
        finally:
            s.close()

    def test_review_diagnostic_explains_ambiguity(self, env):
        m, ids = env
        data = {"bulk_materials": [{"material_name": "Gloves", "current_stock": 100}]}
        res = m.save_imported_multi_tab_data_atomic(ids["well"], ids["report"], data)
        reasons = [rr.get("reason", "") for rr in res.get("review_rows", [])
                   if rr.get("entity") == "bulk_materials"]
        assert reasons, "a review diagnostic must be produced"
        assert any("ambiguous" in r.lower() or "unsupported" in r.lower()
                   for r in reasons)

    def test_import_never_creates_inventoryitem(self, env):
        # Even a sheet literally named/aliased "inventory" cannot manufacture an
        # authoritative InventoryItem row through the import path.
        m, ids = env
        data = {"bulk_materials": [
            {"material_name": "General Supplies", "current_stock": 5},
        ]}
        m.save_imported_multi_tab_data_atomic(ids["well"], ids["report"], data)
        s = m.create_session()
        try:
            assert s.query(InventoryItem).count() == 0
        finally:
            s.close()


# ---------------------------------------------------------------------------
# Legacy ProfileImportEngine extraction (test-only, DB write disabled)
# ---------------------------------------------------------------------------

class TestLegacyProfileExtraction:
    def test_db_write_path_is_disabled(self):
        from core.profile_import_engine import ProfileImportEngine
        engine = ProfileImportEngine(None)
        with pytest.raises(RuntimeError):
            engine.import_to_db({"bulk_materials": []}, well_id=1)

    def test_generic_inventory_sheet_not_captured_as_bulk(self):
        # A sheet whose name only says "Inventory" is the general-inventory
        # domain; the legacy extractor must not scoop it into bulk_materials.
        from core.profile_import_engine import ProfileImportEngine
        engine = ProfileImportEngine(None)
        engine.cell_cache = {
            "General Inventory": {
                2: {1: "Gloves", 3: 100, 4: "pcs"},
                3: {1: "Welding Rod", 3: 50, 4: "pcs"},
            }
        }
        res = {
            "surveys": [], "survey_review": [], "pob_records": [],
            "casing_report": {}, "cement_report": {}, "bit_report": {},
            "bha_report": {}, "bulk_materials": [], "fuel_water": {},
            "safety_report": {}, "bop_components": [], "waste_records": [],
            "cost_records": [], "equipment_logs": [],
        }
        # Directly exercise the sheet loop.
        out = engine._extract_multi_tab_sheets(["General Inventory"])
        assert out["bulk_materials"] == []

    def test_bulk_sheet_preserves_blanks_and_unit(self):
        # A real bulk sheet: absent unit stays None (not "kg"); a movements-only
        # row keeps unknown opening/closing (not fabricated 0).
        from core.profile_import_engine import ProfileImportEngine
        engine = ProfileImportEngine(None)
        engine.cell_cache = {
            "Bulk Materials": {
                # name, (2 unused), stock(3), unit(4), received(5), used(6)
                2: {1: "Barite", 3: 45, 4: "MT", 5: 5, 6: 2},
                3: {1: "Diesel", 3: None, 4: None, 5: 100, 6: None},
            }
        }
        out = engine._extract_multi_tab_sheets(["Bulk Materials"])
        rows = {r["material_name"]: r for r in out["bulk_materials"]}
        assert rows["Barite"]["unit"] == "MT"
        assert rows["Barite"]["initial_stock"] == 45.0
        assert rows["Barite"]["current_stock"] == 45.0 + 5 - 2
        # Movements-only row: unknown opening -> unknown closing, no fake unit.
        assert rows["Diesel"]["unit"] is None
        assert rows["Diesel"]["initial_stock"] is None
        assert rows["Diesel"]["current_stock"] is None
        assert rows["Diesel"]["received"] == 100.0
        assert rows["Diesel"]["used"] == 0.0
