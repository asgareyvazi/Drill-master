"""Mandatory audit for irreversible and core hierarchy mutations (M43 closure, Phase 2).

Contract: the business change and its audit record commit in ONE transaction.
If the audit record cannot be written the change is rolled back; a refused
change writes no business audit record. Synthetic in-memory databases only.
"""

from __future__ import annotations

import json
import logging
from datetime import date, time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import core.database as database
from core.authorization import AuthorizationError
from core.database import (
    AuditLog, Base, Company, DailyReport, DatabaseManager, Project, Section, TimeLog24H as TimeLog, Well,
)


class Principal:
    def __init__(self, user_id, username, granted):
        self.user_id, self.username, self._granted = user_id, username, set(granted)

    def has_permission(self, name):
        return name in self._granted


@pytest.fixture
def manager():
    db = DatabaseManager()
    db.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                              poolclass=StaticPool)
    Base.metadata.create_all(db.engine)
    db.Session = sessionmaker(bind=db.engine, autoflush=False, autocommit=False)
    return db


@pytest.fixture
def ids(manager):
    session = manager.create_session()
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
    report = DailyReport(well_id=well.id, section_id=section.id, report_date=date(2026, 1, 1), report_number=7)
    session.add(report)
    session.flush()
    session.add(TimeLog(report_id=report.id, time_from=time(0), time_to=time(6), activity_description="synthetic"))
    session.add(TimeLog(report_id=report.id, time_from=time(6), time_to=time(12), activity_description="synthetic 2"))
    session.commit()
    out = dict(company=company.id, project=project.id, well=well.id, section=section.id, report=report.id)
    session.close()
    return out


def _audits(db, **filters):
    session = db.create_session()
    try:
        return [(a.action, a.entity_type, a.entity_id, a.entity_name, a.user_id, a.username, a.details)
                for a in session.query(AuditLog).filter_by(**filters).order_by(AuditLog.id).all()]
    finally:
        session.close()


def _exists(db, model, key):
    session = db.create_session()
    try:
        return session.get(model, key) is not None
    finally:
        session.close()


@pytest.fixture
def broken_audit(monkeypatch):
    def refuse(**_kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(database, "AuditLog", refuse)


# ------------------------------------------------------------------ deletes

def test_delete_well_writes_its_audit_record_with_the_enforced_actor(manager, ids):
    manager.enforce_authorization(Principal(41, "synthetic-admin", {"can_delete_well"}))
    assert manager.delete_well(ids["well"]) is True
    assert not _exists(manager, Well, ids["well"])
    assert not _exists(manager, DailyReport, ids["report"])  # cascade still applies
    assert _audits(manager, action="delete") == [
        ("delete", "well", ids["well"], "Synthetic Well", 41, "synthetic-admin", "")]


def test_delete_well_is_rolled_back_when_its_audit_record_fails(manager, ids, broken_audit, caplog):
    with caplog.at_level(logging.ERROR, logger="core.database"):
        assert manager.delete_well(ids["well"]) is False
    assert _exists(manager, Well, ids["well"]), "delete must not survive without its audit record"
    assert _exists(manager, DailyReport, ids["report"])
    assert "RuntimeError" in caplog.text and "audit store unavailable" not in caplog.text


def test_refused_well_delete_leaves_data_and_no_delete_record(manager, ids):
    manager.enforce_authorization(Principal(42, "synthetic-viewer", set()))
    assert manager.delete_well(ids["well"]) is False
    assert _exists(manager, Well, ids["well"])
    assert _audits(manager, action="delete") == []
    denied = _audits(manager, action="authorization_denied")
    assert denied and denied[0][4] == 42  # security record still written


def test_delete_daily_report_audits_child_counts_but_no_content(manager, ids):
    assert manager.delete_daily_report(ids["report"]) is True
    assert not _exists(manager, DailyReport, ids["report"])
    [(action, kind, entity_id, name, _uid, _user, details)] = _audits(manager, action="delete")
    assert (action, kind, entity_id, name) == ("delete", "daily_report", ids["report"], "Report #7")
    assert json.loads(details) == {"child_rows_deleted": 2}
    assert "synthetic" not in details


def test_delete_daily_report_is_rolled_back_when_its_audit_record_fails(manager, ids, broken_audit):
    with pytest.raises(RuntimeError):
        manager.delete_daily_report(ids["report"])
    assert _exists(manager, DailyReport, ids["report"])
    session = manager.create_session()
    try:
        assert session.query(TimeLog).filter_by(report_id=ids["report"]).count() == 2  # children kept too
    finally:
        session.close()


def test_refused_report_delete_raises_and_writes_no_delete_record(manager, ids):
    manager.enforce_authorization(Principal(43, "synthetic-engineer", {"can_edit_reports"}))
    with pytest.raises(AuthorizationError):
        manager.delete_daily_report(ids["report"])
    assert _exists(manager, DailyReport, ids["report"])
    assert _audits(manager, action="delete") == []


@pytest.mark.parametrize("kind,model,name", [
    ("company", Company, "Synthetic Co"), ("project", Project, "Synthetic Project"),
    ("section", Section, "8-1/2 in")])
def test_hierarchy_service_delete_is_audited_atomically(manager, ids, kind, model, name):
    assert manager.delete_hierarchy_entity(kind, ids[kind]) is True
    assert not _exists(manager, model, ids[kind])
    assert [row[:4] for row in _audits(manager, action="delete")] == [("delete", kind, ids[kind], name)]


@pytest.mark.parametrize("kind,model", [("company", Company), ("project", Project), ("section", Section)])
def test_hierarchy_service_delete_rolls_back_without_audit(manager, ids, broken_audit, kind, model):
    with pytest.raises(RuntimeError):
        manager.delete_hierarchy_entity(kind, ids[kind])
    assert _exists(manager, model, ids[kind])
    assert _exists(manager, DailyReport, ids["report"])


def test_missing_entity_is_not_deleted_and_not_audited(manager, ids):
    assert manager.delete_hierarchy_entity("project", 999_999) is False
    assert manager.delete_well(999_999) is False
    assert manager.delete_daily_report(999_999) is False
    assert _audits(manager, action="delete") == []


def test_unknown_entity_type_is_rejected(manager, ids):
    with pytest.raises(ValueError):
        manager.delete_hierarchy_entity("wellbore", 1)


# --------------------------------------------------------- create / update

def test_save_well_audits_create_and_update_in_the_same_transaction(manager, ids):
    assert manager.save_well({"name": "Synthetic Well 2", "project_id": ids["project"]}) is True
    session = manager.create_session()
    try:
        new_id = session.query(Well.id).filter_by(name="Synthetic Well 2").scalar()
    finally:
        session.close()
    assert manager.save_well({"id": new_id, "name": "Synthetic Well 2b", "project_id": ids["project"]}) is True
    assert [row[:4] for row in _audits(manager, entity_type="well")] == [
        ("create", "well", new_id, "Synthetic Well 2"), ("update", "well", new_id, "Synthetic Well 2b")]


def test_save_well_is_rolled_back_when_its_audit_record_fails(manager, ids, broken_audit):
    assert manager.save_well({"name": "Synthetic Well 3", "project_id": ids["project"]}) is False
    session = manager.create_session()
    try:
        assert session.query(Well).filter_by(name="Synthetic Well 3").count() == 0
    finally:
        session.close()


def test_save_daily_report_audits_create_in_the_same_transaction(manager, ids):
    result = manager.save_daily_report({"well_id": ids["well"], "section_id": ids["section"],
                                        "report_date": "2026-01-02", "report_number": 8})
    assert result and result["id"]
    assert [row[:4] for row in _audits(manager, entity_type="daily_report")] == [
        ("create", "daily_report", result["id"], "Report #8")]


def test_save_daily_report_is_rolled_back_when_its_audit_record_fails(manager, ids, broken_audit):
    assert not manager.save_daily_report({"well_id": ids["well"], "section_id": ids["section"],
                                          "report_date": "2026-01-03", "report_number": 9})
    session = manager.create_session()
    try:
        assert session.query(DailyReport).filter_by(report_number=9).count() == 0
    finally:
        session.close()


def test_caller_owned_session_is_audited_at_the_callers_boundary(manager, ids):
    """A caller-owned session commits nothing here and adds no record (w2 audits after its commit)."""
    session = manager.create_session()
    try:
        assert manager.save_well({"name": "Synthetic Well 4", "project_id": ids["project"]}, session=session)
        session.rollback()
    finally:
        session.close()
    assert _audits(manager, entity_type="well") == []


# -------------------------------------------------------------- best effort

def test_log_audit_reports_success_and_failure_without_message(manager, ids, monkeypatch, caplog):
    assert manager.log_audit("login", "user", 1, "synthetic-user") is True

    def refuse(**_kwargs):
        raise RuntimeError("SELECT secret FROM users")

    monkeypatch.setattr(database, "AuditLog", refuse)
    with caplog.at_level(logging.ERROR, logger="core.database"):
        assert manager.log_audit("login", "user", 1, "synthetic-user") is False
    assert "RuntimeError" in caplog.text and "secret" not in caplog.text


# --------------------------------------------------------------- UI callers

def test_main_window_delete_routes_through_the_audited_service(manager, ids, monkeypatch):
    import main_window
    from types import SimpleNamespace

    calls = []
    fake = SimpleNamespace(
        db_manager=manager, _DELETE_PROMPTS=main_window.MainWindow._DELETE_PROMPTS,
        _check_delete_permission=lambda kind: True,
        status_manager=SimpleNamespace(show_success=lambda *a: calls.append(("ok",) + a),
                                       show_error=lambda *a: calls.append(("error",) + a)),
        _invalidate_hierarchy_cache=lambda: calls.append(("invalidate",)),
        populate_hierarchy=lambda: calls.append(("populate",)),
    )
    monkeypatch.setattr(main_window.QMessageBox, "question",
                        staticmethod(lambda *a, **k: main_window.QMessageBox.Yes))
    assert main_window.MainWindow._delete_hierarchy_item(fake, "project", ids["project"]) is True
    assert [row[:3] for row in _audits(manager, action="delete")] == [("delete", "project", ids["project"])]
    assert calls[0][0] == "ok" and ("populate",) in calls


def test_main_window_delete_reports_failure_and_keeps_data(manager, ids, broken_audit, monkeypatch):
    import main_window
    from types import SimpleNamespace

    errors = []
    fake = SimpleNamespace(
        db_manager=manager, _DELETE_PROMPTS=main_window.MainWindow._DELETE_PROMPTS,
        _check_delete_permission=lambda kind: True,
        status_manager=SimpleNamespace(show_success=lambda *a: pytest.fail("no success on failure"),
                                       show_error=lambda *a: errors.append(a)),
        _invalidate_hierarchy_cache=lambda: None, populate_hierarchy=lambda: None,
    )
    monkeypatch.setattr(main_window.QMessageBox, "question",
                        staticmethod(lambda *a, **k: main_window.QMessageBox.Yes))
    assert main_window.MainWindow._delete_hierarchy_item(fake, "section", ids["section"]) is False
    assert errors and "audit store unavailable" not in errors[0][1]
    assert _exists(manager, Section, ids["section"])
