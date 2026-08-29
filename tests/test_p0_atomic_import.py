"""P0: Atomic Import Transaction Tests"""

import unittest
import tempfile
import os
from datetime import date
from pathlib import Path
import sys

# Ensure repo root in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import DatabaseManager, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class AtomicImportTests(unittest.TestCase):
    def setUp(self):
        # Use temporary DB file
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.db = DatabaseManager()
        self.db.db_path = self.db_path
        self.db.initialize()

    def tearDown(self):
        try:
            self.db.close()
        except Exception:
            pass
        # cleanup
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_atomic_import_success(self):
        """Test that atomic import saves all tables or none."""
        # Create well, section, report first
        from core.database import Well, Project, Company

        with self.db.session_scope() as session:
            company = Company(name="TestCo", code="TC001")
            session.add(company)
            session.flush()
            project = Project(company_id=company.id, name="TestProj", code="TP001")
            session.add(project)
            session.flush()
            well = session.query(Well).first()
            if not well:
                from core.database import Well as WellModel
                well = WellModel(project_id=project.id, name="TestWell", code="TW001")
                session.add(well)
                session.flush()
            well_id = well.id

        # Create section
        section_id = self.db.save_section({"well_id": well_id, "name": "Test Section", "depth_from": 0, "depth_to": 1000})

        # Create daily report
        report = self.db.save_daily_report({
            "well_id": well_id,
            "section_id": section_id,
            "report_date": date.today(),
            "report_number": 1,
            "status": "Draft",
        })
        report_id = report["id"]

        extracted = {
            "surveys": [{"md": 100, "inc": 5, "azi": 45, "tvd": 99}],
            "pob_records": [{"company_name": "Test POB Co", "personnel_count": 5}],
            "bulk_materials": [{"material_name": "Bentonite", "initial_stock": 100, "received": 50, "used": 20, "current_stock": 130, "report_date": date.today(), "unit": "kg"}],
        }

        results = self.db.save_imported_multi_tab_data_atomic(well_id, report_id, extracted)

        self.assertIn("surveys", results)
        self.assertEqual(results["surveys"], 1)
        self.assertIn("pob_records", results)

        # Verify data persisted via direct query
        with self.db.session_scope() as session:
            from core.database import SurveyPoint, ServiceCompanyPOB
            survey_count = session.query(SurveyPoint).filter(SurveyPoint.report_id == report_id).count()
            self.assertEqual(survey_count, 1)
            pob_count = session.query(ServiceCompanyPOB).filter(ServiceCompanyPOB.report_id == report_id).count()
            self.assertEqual(pob_count, 1)

    def test_atomic_rollback_on_failure(self):
        """If any step fails, rollback all."""
        from core.database import Well, Project, Company

        with self.db.session_scope() as session:
            company = Company(name="TestCo2", code="TC002")
            session.add(company)
            session.flush()
            project = Project(company_id=company.id, name="TestProj2", code="TP002")
            session.add(project)
            session.flush()
            well = session.query(Well).first()
            well_id = well.id

        section_id = self.db.save_section({"well_id": well_id, "name": "Sec2", "depth_from": 0, "depth_to": 500})
        report = self.db.save_daily_report({
            "well_id": well_id,
            "section_id": section_id,
            "report_date": date.today(),
            "report_number": 2,
            "status": "Draft",
        })
        report_id = report["id"]

        # Invalid extracted: survey without md should be counted as failed but not crash
        extracted = {
            "surveys": [{"inc": 5, "azi": 45}],  # missing md
            "pob_records": [{"company_name": "", "personnel_count": 5}],  # empty name -> skip
        }

        results = self.db.save_imported_multi_tab_data_atomic(well_id, report_id, extracted)
        # Should not have saved invalid
        with self.db.session_scope() as session:
            from core.database import SurveyPoint
            count = session.query(SurveyPoint).filter(SurveyPoint.report_id == report_id).count()
            self.assertEqual(count, 0)

    def test_snapshot_rollback(self):
        """Snapshot and restore for existing report."""
        from core.database import Well

        with self.db.session_scope() as session:
            well = session.query(Well).first()
            well_id = well.id

        section_id = self.db.save_section({"well_id": well_id, "name": "SecSnap", "depth_from": 0, "depth_to": 300})
        report = self.db.save_daily_report({
            "well_id": well_id,
            "section_id": section_id,
            "report_date": date(2026, 1, 15),
            "report_number": 10,
            "status": "Draft",
            "summary": "Original",
        })
        report_id = report["id"]

        snapshot = self.db.create_import_snapshot(report_id)
        self.assertIsNotNone(snapshot)
        self.assertIsNotNone(snapshot.get("report"))

        # Simulate failed import by changing report
        with self.db.session_scope() as session:
            from core.database import DailyReport
            r = session.get(DailyReport, report_id)
            r.summary = "Corrupted"

        # Restore
        restored = self.db.restore_import_snapshot(snapshot)
        self.assertTrue(restored)

        # Check original restored
        restored_report = self.db.get_daily_report_by_id(report_id)
        self.assertEqual(restored_report["summary"], "Original")


if __name__ == "__main__":
    unittest.main()
