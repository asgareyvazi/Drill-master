"""Data-layer authorization (core.authorization) with direct service calls (M43).

These tests bypass every UI guard and call DatabaseManager / repositories
directly, as a new code path or a missed decorator would.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import sqlite3
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

import core.database as database
from core.authorization import TABLE_POLICY, AuthorizationError
from core.database import AuditLog, CostRecord, DailyReport, DatabaseManager, User, Well
from core.permissions import ROLE_PERMISSIONS
from tests.test_database_migration_acceptance import _configure

ROOT = Path(__file__).resolve().parents[1]
IDS: dict = {}  # ids of the seeded synthetic hierarchy (filled by seeded_template)


class Principal:
    """Same resolution rules as core.permissions.PermissionManager."""

    def __init__(self, role, user_id, username, permissions=None, explode=False):
        self.role, self.user_id, self.username = role, user_id, username
        self.permissions, self.explode = dict(permissions or {}), explode

    def has_permission(self, permission):
        if self.explode:
            raise RuntimeError("resolver failure")
        if permission in self.permissions:
            return bool(self.permissions[permission])
        granted = ROLE_PERMISSIONS.get(self.role, set())
        return permission in granted or "*" in granted


@pytest.fixture(scope="module")
def seeded_template(tmp_path_factory):
    """One initialized database with a hierarchy and one report, copied per test."""
    mp = pytest.MonkeyPatch()
    base = tmp_path_factory.mktemp("authz")
    path = base / "seed.sqlite"
    _configure(base, mp, path)
    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    with manager.session_scope() as session:
        q = session.execute
        q(text("INSERT INTO companies(name, code) VALUES ('Synthetic Co', 'SC')"))
        company = q(text("SELECT id FROM companies WHERE code='SC'")).scalar()
        q(text("INSERT INTO projects(company_id, name, code) VALUES (:c, 'Synthetic Project', 'SP')"), {"c": company})
        project = q(text("SELECT id FROM projects WHERE code='SP'")).scalar()
        q(text("INSERT INTO wells(project_id, name, code) VALUES (:p, 'SYNW-1', 'S1')"), {"p": project})
        well = q(text("SELECT id FROM wells WHERE code='S1'")).scalar()
        q(text("INSERT INTO sections(well_id, name) VALUES (:w, '12-1/4')"), {"w": well})
        section = q(text("SELECT id FROM sections WHERE well_id=:w"), {"w": well}).scalar()
        q(text("INSERT INTO daily_reports(well_id, section_id, report_date, report_number, status) "
               "VALUES (:w, :s, '2026-01-02', 1, 'Draft')"), {"w": well, "s": section})
        report = q(text("SELECT id FROM daily_reports WHERE well_id=:w"), {"w": well}).scalar()
        users = {name: uid for uid, name in q(text("SELECT id, username FROM users"))}
    IDS.update(project=project, well=well, section=section, report=report)
    manager.close()
    mp.undo()
    return path, users


@pytest.fixture()
def db_for(seeded_template, tmp_path, monkeypatch):
    template, users = seeded_template
    path = tmp_path / "case.sqlite"
    shutil.copy(template, path)
    _configure(tmp_path, monkeypatch, path)
    managers = []

    def open_as(role, *, permissions=None, explode=False, enforce=True):
        manager = DatabaseManager()
        assert manager.initialize(), manager.last_diagnostic
        if enforce:
            username = {"supervisor": "admin", "manager": "admin"}.get(role, role)
            uid = users.get(username, users["admin"])
            manager.enforce_authorization(Principal(role, uid, username, permissions, explode))
        managers.append(manager)
        return manager

    yield open_as, path
    for manager in managers:
        manager.close()


def _count(path, sql, *args):
    with sqlite3.connect(path) as connection:
        return connection.execute(sql, args).fetchone()[0]


def _denials(path):
    return _count(path, "SELECT COUNT(*) FROM audit_logs WHERE action='authorization_denied'")


def _refused(call):
    """True when the call raised AuthorizationError or reported failure."""
    try:
        return not call()
    except AuthorizationError:
        return True


# ---------------------------------------------------------------- policy shape

def test_every_mapped_table_has_a_policy_and_no_policy_is_stale():
    tables = set(database.Base.metadata.tables)
    assert set(TABLE_POLICY) == tables


def test_unenforced_manager_keeps_library_behaviour(db_for):
    open_as, path = db_for
    manager = open_as("viewer", enforce=False)
    assert manager.save_well({"project_id": IDS["project"], "name": "SYNW-2", "code": "S2"})
    assert _count(path, "SELECT COUNT(*) FROM wells WHERE code='S2'") == 1


def test_enforcement_requires_a_real_principal(db_for):
    open_as, _ = db_for
    manager = open_as("viewer", enforce=False)
    with pytest.raises(ValueError):
        manager.enforce_authorization(None)
    assert not manager.authorization_enforced


# ---------------------------------------------------------------- role matrix

ROLES = ("admin", "supervisor", "engineer", "manager", "viewer")


@pytest.mark.parametrize("role,allowed", [
    ("admin", True), ("supervisor", True), ("engineer", True), ("manager", True), ("viewer", False)])
def test_creating_a_well_requires_can_create_well(db_for, role, allowed):
    open_as, path = db_for
    manager = open_as(role)
    refused = _refused(lambda: manager.save_well({"project_id": IDS["project"], "name": "SYNW-NEW", "code": "SN"}))
    assert refused is (not allowed)
    assert _count(path, "SELECT COUNT(*) FROM wells WHERE name='SYNW-NEW'") == (1 if allowed else 0)
    assert _denials(path) == (0 if allowed else 1)


@pytest.mark.parametrize("role,allowed", [
    ("admin", True), ("supervisor", True), ("engineer", True), ("manager", False), ("viewer", False)])
def test_editing_report_data_requires_can_edit_reports(db_for, role, allowed):
    open_as, path = db_for
    manager = open_as(role)
    refused = _refused(lambda: manager.generic_save(CostRecord, {
        "well_id": IDS["well"], "cost_date": date(2026, 1, 2), "category": "Rig", "actual_cost": 10.0}))
    assert refused is (not allowed)
    assert _count(path, "SELECT COUNT(*) FROM cost_records") == (1 if allowed else 0)


@pytest.mark.parametrize("role,allowed", [
    ("admin", True), ("supervisor", True), ("engineer", False), ("manager", False), ("viewer", False)])
def test_deleting_a_report_requires_can_delete_reports(db_for, role, allowed):
    open_as, path = db_for
    manager = open_as(role)
    refused = _refused(lambda: manager.delete_daily_report(IDS["report"]))
    assert refused is (not allowed)
    assert _count(path, "SELECT COUNT(*) FROM daily_reports WHERE id=?", IDS["report"]) == (0 if allowed else 1)


@pytest.mark.parametrize("role", ROLES)
def test_deleting_a_well_requires_can_delete_well(db_for, role):
    open_as, path = db_for
    manager = open_as(role)
    refused = _refused(lambda: manager.delete_well(IDS["well"]))
    assert refused is (role != "admin")
    assert _count(path, "SELECT COUNT(*) FROM wells WHERE id=?", IDS["well"]) == (0 if role == "admin" else 1)


def test_explicit_per_user_permission_overrides_the_role(db_for):
    open_as, path = db_for
    manager = open_as("engineer", permissions={"can_delete_reports": True})
    assert manager.delete_daily_report(IDS["report"])
    assert _count(path, "SELECT COUNT(*) FROM daily_reports WHERE id=?", IDS["report"]) == 0


def test_viewer_cannot_persist_engineering_calculation_runs(db_for):
    """Closes the M43 finding: w13 'Save Calculation' had no permission check."""
    from core.repositories.mse_repository import MSECalculationRepository

    open_as, path = db_for
    run = dict(inputs={"wob_klbf": 20.0}, result_values={"mse_psi": 12345.0},
               method="Teale (1965) Mechanical Specific Energy", label="MSE", well_id=IDS["well"])
    viewer = open_as("viewer")
    with pytest.raises(AuthorizationError):
        MSECalculationRepository(viewer).save_run(**run)
    assert _count(path, "SELECT COUNT(*) FROM mse_calculations") == 0
    engineer = open_as("engineer")
    assert MSECalculationRepository(engineer).save_run(**run)
    assert _count(path, "SELECT COUNT(*) FROM mse_calculations") == 1


def test_user_records_require_can_manage_users(db_for):
    open_as, path = db_for
    for role, allowed in (("engineer", False), ("admin", True)):
        manager = open_as(role)
        refused = _refused(lambda: manager.generic_save(User, {"id": 3, "full_name": f"renamed by {role}"}))
        assert refused is (not allowed)
    assert _count(path, "SELECT COUNT(*) FROM users WHERE full_name='renamed by engineer'") == 0
    assert _count(path, "SELECT COUNT(*) FROM users WHERE full_name='renamed by admin'") == 1


def test_enforcement_reaches_a_session_factory_assigned_outside_initialize(seeded_template, tmp_path):
    """Managers wired by hand (scripts, tests) cannot silently stay unguarded."""
    import shutil

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    path = tmp_path / "manual.sqlite"
    shutil.copy(seeded_template[0], path)
    manager = DatabaseManager.__new__(DatabaseManager)
    manager.engine = create_engine(f"sqlite:///{path}")
    manager.Session = sessionmaker(bind=manager.engine)
    assert manager.authorization_enforced is False
    manager.enforce_authorization(Principal("viewer", seeded_template[1]["viewer"], "viewer"))
    with pytest.raises(AuthorizationError):
        with manager.session_scope() as session:
            session.add(Well(project_id=IDS["project"], name="SYNW-M", code="SM"))
    manager.engine.dispose()
    assert _count(path, "SELECT COUNT(*) FROM wells WHERE code='SM'") == 0


def test_enforcement_refuses_an_unsupported_session_factory():
    manager = DatabaseManager.__new__(DatabaseManager)
    manager.Session = lambda: None
    with pytest.raises(RuntimeError):
        manager.enforce_authorization(Principal("admin", 1, "admin"))
    assert manager.authorization_enforced is False


def test_a_failing_permission_resolver_denies(db_for):
    open_as, path = db_for
    manager = open_as("admin", explode=True)
    assert _refused(lambda: manager.save_well({"project_id": IDS["project"], "name": "SYNW-X", "code": "SX"}))
    assert _count(path, "SELECT COUNT(*) FROM wells WHERE code='SX'") == 0


# ---------------------------------------------------------------- audit & lifecycle

def test_audit_log_is_append_only_even_for_admin(db_for):
    open_as, path = db_for
    viewer = open_as("viewer")
    viewer.log_audit("viewed", entity_type="well", entity_id=IDS["well"], user_id=None, username="viewer")
    assert _count(path, "SELECT COUNT(*) FROM audit_logs WHERE action='viewed'") == 1
    admin = open_as("admin")
    with pytest.raises(AuthorizationError):
        with admin.session_scope() as session:
            session.query(AuditLog).filter_by(action="viewed").one().details = "rewritten"
    with pytest.raises(AuthorizationError):
        with admin.session_scope() as session:
            session.delete(session.query(AuditLog).filter_by(action="viewed").one())
    assert _count(path, "SELECT COUNT(*) FROM audit_logs WHERE action='viewed' AND details=''") == 1


def test_denials_are_audited_with_the_actor_and_nothing_else_persists(db_for, seeded_template):
    open_as, path = db_for
    _, users = seeded_template
    manager = open_as("viewer")
    before = _count(path, "SELECT COUNT(*) FROM daily_reports")
    assert _refused(lambda: manager.save_daily_report({
        "well_id": IDS["well"], "section_id": IDS["section"], "report_date": date(2026, 1, 3), "report_number": 2}))
    assert _count(path, "SELECT COUNT(*) FROM daily_reports") == before
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT user_id, entity_type, details FROM audit_logs WHERE action='authorization_denied'").fetchone()
    assert row[0] == users["viewer"] and row[1] == "daily_reports"
    assert json.loads(row[2])["operation"] == "insert"


def test_manager_approves_through_the_lifecycle_but_cannot_edit_the_report(db_for, monkeypatch):
    open_as, path = db_for
    import core.validators as validators

    monkeypatch.setattr(validators.DailyReportValidator, "validate",
                        staticmethod(lambda data: type("V", (), {"is_valid": True, "errors": []})()))
    engineer = open_as("engineer")
    eng = engineer._authorization.principal
    rid = IDS["report"]
    submitted = engineer.transition_report(rid, "submit", has_permission=eng.has_permission, user_id=eng.user_id)
    assert submitted.ok, submitted.message
    manager = open_as("manager")
    mgr = manager._authorization.principal
    approved = manager.transition_report(rid, "approve", has_permission=mgr.has_permission,
                                         user_id=mgr.user_id, comment="ok")
    assert approved.ok, approved.message
    assert _count(path, "SELECT status FROM daily_reports WHERE id=?", rid) == "Approved"
    # The same manager cannot change report content directly ...
    assert _refused(lambda: manager.generic_save(DailyReport, {"id": rid, "forecast": "edited"}))
    # ... nor the status outside the lifecycle.
    assert _refused(lambda: manager.generic_save(DailyReport, {"id": rid, "status": "Draft"}))
    assert _count(path, "SELECT status FROM daily_reports WHERE id=?", rid) == "Approved"
    assert _count(path, "SELECT COUNT(*) FROM daily_reports WHERE id=? AND forecast='edited'", rid) == 0


def test_the_lifecycle_scope_admits_only_status_columns(db_for):
    """Inside REPORT_LIFECYCLE a principal without can_edit_reports may change
    status/updated_at, and nothing else on the report."""
    from core.authorization import REPORT_LIFECYCLE, operation_scope

    open_as, path = db_for
    manager = open_as("manager")
    rid = IDS["report"]
    with operation_scope(REPORT_LIFECYCLE):
        with pytest.raises(AuthorizationError):
            with manager.session_scope() as session:
                session.get(DailyReport, rid).forecast = "smuggled"
        with manager.session_scope() as session:
            session.get(DailyReport, rid).status = "Submitted"
    assert _count(path, "SELECT status FROM daily_reports WHERE id=?", rid) == "Submitted"
    assert _count(path, "SELECT COUNT(*) FROM daily_reports WHERE forecast='smuggled'") == 0


# ---------------------------------------------------------------- bulk / textual paths

def test_bulk_orm_update_and_delete_are_checked(db_for):
    open_as, path = db_for
    viewer = open_as("viewer")
    with pytest.raises(AuthorizationError):
        with viewer.session_scope() as session:
            session.query(Well).filter(Well.id == IDS["well"]).update({"name": "renamed"}, synchronize_session=False)
    with pytest.raises(AuthorizationError):
        with viewer.session_scope() as session:
            session.query(DailyReport).filter(DailyReport.id == IDS["report"]).delete(synchronize_session=False)
    assert _count(path, "SELECT name FROM wells WHERE id=?", IDS["well"]) == "SYNW-1"
    assert _count(path, "SELECT COUNT(*) FROM daily_reports WHERE id=?", IDS["report"]) == 1


def test_textual_dml_through_an_enforced_session_is_refused(db_for):
    open_as, path = db_for
    admin = open_as("admin")
    with pytest.raises(AuthorizationError):
        with admin.session_scope() as session:
            session.execute(text("DELETE FROM daily_reports"))
    assert _count(path, "SELECT COUNT(*) FROM daily_reports WHERE id=?", IDS["report"]) == 1


# ---------------------------------------------------------------- import scope

def test_import_requires_can_import_and_covers_report_writes(db_for):
    from tests.test_well_centric_acceptance import ddr_payload, import_ddr

    open_as, path = db_for
    viewer = open_as("viewer")
    before = _count(path, "SELECT COUNT(*) FROM daily_reports")
    try:
        result = import_ddr(viewer, ddr_payload("SYNW-1", "2026-01-05"), IDS["well"])
    except AuthorizationError:
        result = None
    assert _count(path, "SELECT COUNT(*) FROM daily_reports") == before
    assert not (result or {}).get("success", False)
    # A manager holds can_import (but not can_edit_reports): the import scope applies.
    manager = open_as("manager")
    result = import_ddr(manager, ddr_payload("SYNW-1", "2026-01-05"), IDS["well"])
    assert _count(path, "SELECT COUNT(*) FROM daily_reports") == before + 1, result


# ---------------------------------------------------------------- static guard

_DML = re.compile(r"^\s*(INSERT\s+(OR\s+\w+\s+)?INTO\s|REPLACE\s+INTO\s|DELETE\s+FROM\s|UPDATE\s+[\"\w{}]+\s+SET\s)", re.I)
# Reviewed raw-SQL writers: schema migration/repair and system bookkeeping.
RAW_DML_ALLOWLIST = {
    ("core/database.py", "_apply_safe_schema_upgrades"),
    ("core/database.py", "_install_wellbore_foreign_key"),
    ("core/database.py", "_rebuild_live_table"),
    ("core/database.py", "_rebuild_live_table_preserving_objects"),
    ("core/database.py", "assert_import_schema_supported"),
    ("core/login_throttle.py", "clear"),
    ("core/login_throttle.py", "record_failure"),
}


def _raw_dml_sites():
    sites = set()
    files = [p for root in ("core", "tabs", "dialogs", "ui", "config") for p in (ROOT / root).rglob("*.py")]
    files += [ROOT / name for name in ("app.py", "main_window.py", "reset_database.py") if (ROOT / name).exists()]
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))

        def visit(node, function):
            for child in ast.iter_child_nodes(node):
                name = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else function
                literal = None
                if isinstance(child, ast.Constant) and isinstance(child.value, str):
                    literal = child.value
                elif isinstance(child, ast.JoinedStr):
                    literal = "".join(v.value for v in child.values
                                      if isinstance(v, ast.Constant) and isinstance(v.value, str))
                if literal and _DML.match(literal):
                    sites.add((path.relative_to(ROOT).as_posix(), name))
                visit(child, name)

        visit(tree, "<module>")
    return sites


def test_no_unreviewed_raw_sql_writer_bypasses_the_orm_guard():
    unexpected = _raw_dml_sites() - RAW_DML_ALLOWLIST
    assert unexpected == set(), (
        "raw SQL INSERT/UPDATE/DELETE outside the reviewed system functions bypasses the data-layer "
        f"authorization guard; write through the ORM or review and allowlist: {sorted(unexpected)}")
