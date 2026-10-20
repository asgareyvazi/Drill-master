"""Contracts for exception handlers reclassified in M43 Phase 4.

Each test pins what a formerly silent handler now does: keep the source value,
report the failure, or roll back. Synthetic in-memory databases only.
"""

from __future__ import annotations

import logging
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core import runtime_config
from core.database import (
    AuditLog, Base, Company, DailyReport, DatabaseManager, Project, Section, SevenDaysLookahead, Well,
)


@pytest.fixture
def manager():
    db = DatabaseManager()
    db.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                              poolclass=StaticPool)
    Base.metadata.create_all(db.engine)
    db.Session = sessionmaker(bind=db.engine, autoflush=False, autocommit=False)
    return db


def _report(db):
    session = db.create_session()
    company = Company(name="Synthetic Co", code="SC")
    session.add(company)
    session.flush()
    project = Project(name="Synthetic Project", code="SP", company_id=company.id)
    session.add(project)
    session.flush()
    well = Well(name="Synthetic Well", code="SW", project_id=project.id)
    session.add(well)
    session.flush()
    section = Section(name="8-1/2 in", well_id=well.id)
    session.add(section)
    session.flush()
    report = DailyReport(well_id=well.id, section_id=section.id, report_date=date(2026, 1, 1), report_number=1)
    session.add(report)
    session.commit()
    ids = company.id, well.id, report.id
    session.close()
    return ids


def test_lookahead_hours_that_are_not_numbers_are_kept_verbatim(manager):
    _, well_id, report_id = _report(manager)
    result = manager.save_imported_multi_tab_data_atomic(well_id, report_id, {"lookahead": [
        {"activity": "Run casing", "hours": "12-14", "comments": "weather"},
        {"activity": "Cement", "hours": "inf"},
        {"activity": "Drill", "hours": 6},
    ]})
    assert result["failed"] == 0, result
    session = manager.create_session()
    try:
        remarks = {row.activity: row.remarks for row in session.query(SevenDaysLookahead).all()}
    finally:
        session.close()
    assert remarks["Run casing"] == "[HRs: 12-14] weather"  # formerly dropped silently
    assert remarks["Cement"] == "[HRs: inf]"  # formerly OverflowError -> whole import failed
    assert remarks["Drill"] == "[HRs: 6]"  # numeric formatting unchanged


def test_unparseable_report_date_is_not_stored(manager):
    _, well_id, _ = _report(manager)
    assert manager.save_daily_report({"well_id": well_id, "report_date": "2024-13-45"}) is None
    session = manager.create_session()
    try:
        assert session.query(DailyReport).count() == 1  # only the fixture report
    finally:
        session.close()


def test_session_close_failure_is_logged_without_its_message(manager, caplog):
    class Broken:
        def close(self):
            raise RuntimeError("SELECT secret_column FROM wells WHERE name='Synthetic Well'")

    with caplog.at_level(logging.WARNING, logger="core.database"):
        manager.release_session(Broken())
    assert "Session close failed: RuntimeError" in caplog.text
    assert "secret_column" not in caplog.text and "Synthetic Well" not in caplog.text


def test_mineru_settings_absent_is_quiet_but_corrupt_is_reported(tmp_path, monkeypatch, caplog):
    target = tmp_path / "mineru.json"
    monkeypatch.setenv("DRILLMASTER_MINERU_SETTINGS_PATH", str(target))
    with caplog.at_level(logging.WARNING, logger="core.runtime_config"):
        assert runtime_config.read_mineru_settings() == {}
    assert caplog.text == ""
    target.write_text("{not json", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="core.runtime_config"):
        assert runtime_config.read_mineru_settings() == {}
    assert "unreadable; using defaults: JSONDecodeError" in caplog.text


@pytest.fixture
def hierarchy(monkeypatch):
    from core import hierarchy_operations as ops

    monkeypatch.setattr(ops, "check_delete_permission", lambda *a, **k: True)
    monkeypatch.setattr(ops.QMessageBox, "question", staticmethod(lambda *a, **k: ops.QMessageBox.Yes))
    return ops


def test_hierarchy_delete_writes_its_audit_record_in_the_same_transaction(manager, hierarchy):
    company_id, _, _ = _report(manager)
    assert hierarchy.delete_entity(manager, "company", company_id) is True
    session = manager.create_session()
    try:
        assert session.get(Company, company_id) is None
        audit = session.query(AuditLog).filter_by(action="delete", entity_type="company").one()
        assert audit.entity_id == company_id and audit.entity_name == "Synthetic Co"
    finally:
        session.close()


def test_hierarchy_delete_is_rolled_back_when_the_audit_record_fails(manager, hierarchy, monkeypatch):
    company_id, _, _ = _report(manager)
    import core.database as database

    def refuse(**_kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(database, "AuditLog", refuse)
    assert hierarchy.delete_entity(manager, "company", company_id) is False
    session = manager.create_session()
    try:
        assert session.get(Company, company_id) is not None, "delete must not survive without its audit record"
    finally:
        session.close()
