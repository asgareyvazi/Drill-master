"""State-based atomic import tests against an isolated on-disk SQLite database."""
from __future__ import annotations

from datetime import date

import pytest

from core.database import BulkMaterials, Company, DailyReport, DatabaseManager, Project, Section, Well
from core.import_diagnostics import PersistenceError


def _seed_report(manager):
    with manager.session_scope() as session:
        company = Company(name="Import Atomicity Test", code="M42-IMPORT")
        session.add(company)
        session.flush()
        project = Project(company_id=company.id, name="Disposable Import Project", code="M42-IP")
        session.add(project)
        session.flush()
        well = Well(project_id=project.id, name="Disposable Import Well", code="M42-IW")
        session.add(well)
        session.flush()
        section = Section(well_id=well.id, name="8-1/2 in")
        session.add(section)
        session.flush()
        report = DailyReport(well_id=well.id, section_id=section.id,
                             report_date=date(2026, 10, 7), report_number=1)
        session.add(report)
        session.flush()
        return well.id, report.id


def test_valid_duplicate_and_mid_transaction_failure_preserve_database_state(tmp_path, monkeypatch):
    monkeypatch.setenv("DRILLMASTER_ENV", "test")
    monkeypatch.delenv("DRILLMASTER_ENVIRONMENT", raising=False)
    monkeypatch.setenv("DRILLMASTER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DRILLMASTER_DB_PATH", str(tmp_path / "data" / "import.sqlite"))
    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    try:
        well_id, report_id = _seed_report(manager)
        valid = {"bulk_materials": [{
            "material_name": "Diesel", "unit": "liter", "initial_stock": 40,
            "received": 6, "used": 2, "report_date": date(2026, 10, 7),
        }]}
        first = manager.save_imported_multi_tab_data_atomic(well_id, report_id, valid)
        assert first["failed"] == 0 and first["imported"] >= 1
        repeated = manager.save_imported_multi_tab_data_atomic(well_id, report_id, valid)
        assert repeated["failed"] == 0
        with manager.session_scope() as session:
            rows = session.query(BulkMaterials).filter_by(report_id=report_id).all()
            assert len(rows) == 1
            assert rows[0].material_name == "Diesel"
            assert (rows[0].initial_stock, rows[0].received, rows[0].used) == (40, 6, 2)
            before = [(row.id, row.material_name, row.initial_stock, row.received, row.used) for row in rows]

        malformed = {"bulk_materials": [
            {
                "material_name": "Water", "unit": "liter", "initial_stock": 100,
                "received": 10, "used": 5, "report_date": date(2026, 10, 7),
            },
            {
                "material_name": "Diesel", "unit": "liter", "initial_stock": 1,
                "received": "not-a-number", "used": 0, "report_date": date(2026, 10, 7),
            },
        ]}
        with pytest.raises(PersistenceError):
            manager.save_imported_multi_tab_data_atomic(well_id, report_id, malformed)

        with manager.session_scope() as session:
            after = session.query(BulkMaterials).filter_by(report_id=report_id).all()
            state_after = [(row.id, row.material_name, row.initial_stock, row.received, row.used) for row in after]
            assert state_after == before, "failed write must preserve the exact previously committed state"
            assert session.query(DailyReport).filter_by(id=report_id).count() == 1
    finally:
        manager.close()
