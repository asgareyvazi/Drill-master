"""Executable SQLite backup/restore drill against disposable file-backed data."""
from __future__ import annotations

import json
import sqlite3

import pytest
from datetime import date

from core.database import AuditLog, Company, DailyReport, DatabaseManager, Project, Section, User, Well, Wellbore
from core.engineering.engines.mse import MSEEngine
from core.repositories.mse_repository import MSECalculationRepository


INPUTS = {
    "wob_lbf": 24000.0,
    "rpm": 100.0,
    "torque_ft_lbf": 7200.0,
    "rop_ft_hr": 25.0,
    "bit_diameter_in": 8.5,
}


def test_file_database_backup_corruption_restore_and_reopen(tmp_path, monkeypatch):
    data_root = tmp_path / "user-data"
    live_path = data_root / "drillmaster.db"
    backup_path = tmp_path / "external-backup" / "verified.db"
    monkeypatch.setenv("DRILLMASTER_ENV", "test")
    monkeypatch.delenv("DRILLMASTER_ENVIRONMENT", raising=False)
    monkeypatch.setenv("DRILLMASTER_DATA_DIR", str(data_root))
    monkeypatch.setenv("DRILLMASTER_DB_PATH", str(live_path))
    monkeypatch.setenv("DRILLMASTER_AI_IMPORT", "0")

    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    with manager.session_scope() as session:
        company = Company(name="Temporary Acceptance Company", code="M42-TEMP")
        session.add(company)
        session.flush()
        project = Project(company_id=company.id, name="Temporary Project", code="M42-PROJ")
        session.add(project)
        session.flush()
        well = Well(project_id=project.id, name="Temporary Well", code="M42-WELL")
        session.add(well)
        session.flush()
        bore = Wellbore(well_id=well.id, name="Original", wellbore_type="original")
        session.add(bore)
        session.flush()
        section = Section(well_id=well.id, wellbore_id=bore.id, name="12-1/4 in", depth_from=0, depth_to=1000)
        session.add(section)
        session.flush()
        report = DailyReport(
            well_id=well.id, wellbore_id=bore.id, section_id=section.id,
            report_date=date(2026, 10, 7), report_number=41, summary="M42 disposable restore drill",
        )
        session.add(report)
        session.flush()
        ids = (company.id, project.id, well.id, bore.id, section.id, report.id)
        session.add(AuditLog(username="test-operator", action="m42-backup-drill", entity_type="daily_report",
                             entity_id=report.id, details=json.dumps({"scenario": "temporary"})))

    result = MSEEngine.calculate(**INPUTS)
    assert result.success
    repository = MSECalculationRepository(manager)
    calculation_id = repository.save_run(
        inputs=INPUTS, result_values=result.values, method=MSEEngine.METHOD,
        label="temporary M42 backup sample", well_id=ids[2],
    )
    assert calculation_id and repository.count() == 1
    assert manager.authenticate_user("admin", "admin123")

    assert manager.backup_to(backup_path) == str(backup_path)
    with sqlite3.connect(backup_path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT COUNT(*) FROM audit_logs WHERE action='m42-backup-drill'").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM mse_calculations").fetchone() == (1,)
        password_hash = connection.execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()[0]
        assert password_hash.startswith("$2") and password_hash != "admin123"

    manager.close()
    # Destructive operations below are confined to pytest's disposable tmp_path.
    live_path.write_bytes(b"deliberately corrupted disposable database")
    with sqlite3.connect(live_path) as damaged:
        with pytest.raises(sqlite3.DatabaseError, match="not a database"):
            damaged.execute("PRAGMA integrity_check").fetchone()
    live_path.write_bytes(backup_path.read_bytes())

    reopened = DatabaseManager()
    assert reopened.initialize(), reopened.last_diagnostic
    try:
        with reopened.session_scope() as session:
            assert session.get(Company, ids[0]).name == "Temporary Acceptance Company"
            assert session.get(Project, ids[1]).company_id == ids[0]
            assert session.get(Well, ids[2]).project_id == ids[1]
            assert session.get(Wellbore, ids[3]).well_id == ids[2]
            assert session.get(Section, ids[4]).wellbore_id == ids[3]
            assert session.get(DailyReport, ids[5]).wellbore_id == ids[3]
            assert session.query(AuditLog).filter_by(action="m42-backup-drill").count() == 1
            assert session.query(User).filter_by(username="admin").one().password_hash.startswith("$2")
        restored = MSECalculationRepository(reopened).get(calculation_id)
        assert restored is not None
        assert restored.input_parameters == INPUTS
        assert restored.result["mse_psi"] == result.values["mse_psi"]
        raw = reopened.engine.raw_connection()
        try:
            assert raw.execute("PRAGMA foreign_key_check").fetchall() == []
            assert raw.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == 4
        finally:
            raw.close()
    finally:
        reopened.close()
