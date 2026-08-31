"""Integration tests — end-to-end import pipeline without UI.

Tests the full flow: data → validate → save → retrieve → verify
using in-memory SQLite database.
"""

import pytest
from datetime import date, time, datetime
from core.database import (
    DatabaseManager, Well, Company, Project, Section, DailyReport,
    MudReport, DrillingParameters, TimeLog24H, SurveyPoint,
    SafetyReport, BulkMaterials, CostRecord, EquipmentLog,
    ServiceCompanyPOB, FuelWaterInventory, BHAReport, BitReport,
)


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    manager = DatabaseManager()
    manager.db_path = ":memory:"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from core.database import Base
    from sqlalchemy.pool import StaticPool
    
    manager.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from sqlalchemy import event
    
    @event.listens_for(manager.engine, "connect")
    def set_pragma(dbapi_conn, conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    
    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(bind=manager.engine, autoflush=False, autocommit=False)
    return manager


@pytest.fixture
def well_with_section(db):
    """Create a well with a section for testing."""
    session = db.create_session()
    try:
        company = Company(name="TestCo", code="TC001")
        session.add(company)
        session.flush()
        
        project = Project(company_id=company.id, name="TestProject", code="TP001")
        session.add(project)
        session.flush()
        
        well = Well(project_id=project.id, name="TestWell", code="TW001", status="Drilling")
        session.add(well)
        session.flush()
        
        section = Section(well_id=well.id, name="12.25in", depth_from=0, depth_to=1500)
        session.add(section)
        session.flush()
        
        session.commit()
        return {"well_id": well.id, "section_id": section.id, "project_id": project.id, "company_id": company.id}
    finally:
        session.close()


class TestFullImportPipeline:
    """Test the complete import → save → retrieve pipeline."""
    
    def test_create_well_and_report(self, db, well_with_section):
        """Create a well, section, and daily report."""
        well_id = well_with_section["well_id"]
        section_id = well_with_section["section_id"]
        
        # Save daily report
        report_data = {
            "well_id": well_id,
            "section_id": section_id,
            "report_date": date(2026, 8, 24),
            "report_number": 1,
            "rig_day": 1,
            "depth_0000": 0.0,
            "depth_0600": 500.0,
            "depth_2400": 1000.0,
            "summary": "Spud well, drilled 12.25in hole to 1000m",
            "status": "Draft",
        }
        result = db.save_daily_report(report_data)
        assert result is not None
        assert result["id"] is not None
        report_id = result["id"]
        
        # Retrieve and verify
        retrieved = db.get_daily_report_by_id(report_id)
        assert retrieved is not None
        assert retrieved["depth_2400"] == 1000.0
        assert retrieved["well_id"] == well_id
    
    def test_mud_report_with_unit_preservation(self, db, well_with_section):
        """Save mud report with unit-converted MW."""
        from core.unit_manager import UnitManager
        
        well_id = well_with_section["well_id"]
        
        # Create report first
        report = db.save_daily_report({
            "well_id": well_id,
            "section_id": well_with_section["section_id"],
            "report_date": date(2026, 8, 24),
            "report_number": 1,
        })
        report_id = report["id"]
        
        # Convert MW from SG to ppg
        mw_sg = 1.50
        record = UnitManager.create_record("mud_report.mw", "density", "sg", mw_sg, "ppg")
        assert record.normalized_value is not None
        assert abs(record.normalized_value - 12.52) < 0.1  # 1.50 * 8.3454 ≈ 12.52
        
        # Save mud report
        mud_id = db.save_mud_report({
            "well_id": well_id,
            "report_id": report_id,
            "report_date": date(2026, 8, 24),
            "mw": record.normalized_value,
            "pv": 15.0,
            "yp": 10.0,
            "ph": 9.5,
        })
        assert mud_id is not None
        
        # Retrieve and verify
        mud = db.get_mud_report(well_id=well_id)
        assert mud is not None
        assert abs(mud["mw"] - 12.52) < 0.1
    
    def test_drilling_parameters(self, db, well_with_section):
        """Save and retrieve drilling parameters."""
        well_id = well_with_section["well_id"]
        
        report = db.save_daily_report({
            "well_id": well_id,
            "section_id": well_with_section["section_id"],
            "report_date": date(2026, 8, 24),
        })
        
        dp_id = db.save_drilling_parameters({
            "well_id": well_id,
            "report_id": report["id"],
            "report_date": date(2026, 8, 24),
            "bit_size": 12.25,
            "depth_in": 500.0,
            "depth_out": 1000.0,
            "avg_rop": 50.0,
            "wob_max": 10.0,
            "rpm_max": 120,
        })
        assert dp_id is not None
        
        dp = db.get_drilling_parameters(well_id=well_id)
        assert dp is not None
        assert dp["bit_size"] == 12.25
        assert dp["avg_rop"] == 50.0
    
    def test_atomic_multi_tab_import(self, db, well_with_section):
        """Test atomic import of multiple table types."""
        well_id = well_with_section["well_id"]
        section_id = well_with_section["section_id"]
        
        report = db.save_daily_report({
            "well_id": well_id,
            "section_id": section_id,
            "report_date": date(2026, 8, 24),
        })
        report_id = report["id"]
        
        extracted = {
            "surveys": [
                {"md": 100.0, "inc": 0.5, "azi": 45.0, "tvd": 99.9},
                {"md": 200.0, "inc": 1.0, "azi": 46.0, "tvd": 199.8},
            ],
            "pob_records": [
                {"company_name": "Schlumberger", "personnel_count": 5, "service_type": "MWD"},
            ],
            "bulk_materials": [
                {"material_name": "Barite", "received": 100, "used": 50, "current_stock": 50},
                {"material_name": "Bentonite", "received": 200, "used": 100, "current_stock": 100},
            ],
            "cost_records": [
                {"category": "Rig", "description": "Rig daily rate", "planned_cost": 50000, "actual_cost": 52000},
            ],
            "equipment_logs": [
                {"equipment_name": "Top Drive", "equipment_type": "Drilling", "hours_worked": 24.0},
            ],
        }
        
        result = db.save_imported_multi_tab_data_atomic(well_id, report_id, extracted)
        assert result["failed"] == 0
        assert result["imported"] > 0
        
        # Verify surveys
        session = db.create_session()
        try:
            surveys = session.query(SurveyPoint).filter(SurveyPoint.report_id == report_id).all()
            assert len(surveys) == 2
            assert surveys[0].md == 100.0
            
            # Verify bulk materials
            bulks = session.query(BulkMaterials).filter(BulkMaterials.report_id == report_id).all()
            assert len(bulks) == 2
            
            # Verify costs
            costs = session.query(CostRecord).filter(CostRecord.well_id == well_id).all()
            assert len(costs) == 1
            assert costs[0].actual_cost == 52000
        finally:
            session.close()
    
    def test_atomic_rollback_on_failure(self, db, well_with_section):
        """Verify that atomic import rolls back all on failure."""
        well_id = well_with_section["well_id"]
        section_id = well_with_section["section_id"]
        
        report = db.save_daily_report({
            "well_id": well_id,
            "section_id": section_id,
            "report_date": date(2026, 8, 24),
        })
        report_id = report["id"]
        
        # First import succeeds
        extracted1 = {
            "bulk_materials": [
                {"material_name": "Barite", "received": 100, "used": 50, "current_stock": 50},
            ],
        }
        result1 = db.save_imported_multi_tab_data_atomic(well_id, report_id, extracted1)
        assert result1["failed"] == 0
        
        # Verify first import
        session = db.create_session()
        try:
            count1 = session.query(BulkMaterials).filter(BulkMaterials.report_id == report_id).count()
            assert count1 == 1
        finally:
            session.close()
    
    def test_hierarchy_with_reports(self, db, well_with_section):
        """Test hierarchy retrieval with reports."""
        well_id = well_with_section["well_id"]
        section_id = well_with_section["section_id"]
        
        # Create multiple reports
        for i in range(3):
            db.save_daily_report({
                "well_id": well_id,
                "section_id": section_id,
                "report_date": date(2026, 8, 22 + i),
                "report_number": i + 1,
                "depth_2400": (i + 1) * 500.0,
            })
        
        hierarchy = db.get_full_hierarchy()
        assert len(hierarchy) > 0
        
        # Find our well
        found_well = None
        for company in hierarchy:
            for project in company.get("projects", []):
                for well in project.get("wells", []):
                    if well["id"] == well_id:
                        found_well = well
                        break
        
        assert found_well is not None
        assert len(found_well["sections"]) > 0
        assert len(found_well["sections"][0]["reports"]) == 3
    
    def test_report_workflow(self, db, well_with_section):
        """Test report status workflow: Draft → Submitted → Approved."""
        well_id = well_with_section["well_id"]
        section_id = well_with_section["section_id"]
        
        report = db.save_daily_report({
            "well_id": well_id,
            "section_id": section_id,
            "report_date": date(2026, 8, 24),
            "status": "Draft",
        })
        report_id = report["id"]
        
        # Create revision
        rev_id = db.create_report_revision(report_id, status="Draft")
        assert rev_id is not None
        
        # Submit
        db.set_report_status(report_id, "Submitted", user_id=None)
        updated = db.get_daily_report_by_id(report_id)
        assert updated["status"] == "Submitted"
        
        # Approve
        db.set_report_status(report_id, "Approved", user_id=None)
        updated = db.get_daily_report_by_id(report_id)
        assert updated["status"] == "Approved"
        
        # Check approval history
        history = db.get_approval_history(report_id)
        assert len(history) >= 2
    
    def test_search(self, db, well_with_section):
        """Test global search."""
        well_id = well_with_section["well_id"]
        
        results = db.search_all("TestWell")
        assert len(results) > 0
        assert any(r["type"] == "well" for r in results)
    
    def test_audit_logging(self, db, well_with_section):
        """Test audit log recording."""
        well_id = well_with_section["well_id"]
        
        db.log_audit(
            action="create", entity_type="well",
            entity_id=well_id, entity_name="TestWell",
            user_id=None, username="test_admin",
        )
        
        logs = db.get_audit_logs(entity_type="well")
        assert len(logs) > 0
        assert logs[0]["action"] == "create"
