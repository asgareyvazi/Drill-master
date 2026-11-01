"""M70: plan immutability, plan snapshot integrity, well deletion of the history tables.

Real ``DatabaseManager`` on temporary SQLite files (fresh and upgraded from a
pre-M62 schema), the real connection pool, authorization hooks and storage
triggers. Synthetic data only.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest
from sqlalchemy import exc as sa_exc
from sqlalchemy import text, update

from core import calculation_cases as cc
from core import directional_plans as dp
from core.authorization import AuthorizationError
from core.database import Base, CalculationCase, DatabaseManager, DirectionalPlanRevision
from core.storage_guards import trigger_statements
from core.well_plan_designer import design_plan
from tests.test_data_layer_authorization import Principal
from tests.test_database_migration_acceptance import _build_old_schema, _configure

SEGMENTS = [{"type": "hold", "length": 500.0},
            {"type": "curve", "inc": 30.0, "azi": 135.0, "dls": 3.0},
            {"type": "hold_to_tvd", "tvd": 1500.0}]
NEW_TABLES = ("calculation_source_links", "calculation_cases", "directional_plan_revisions")


def _inputs(**overrides):
    base = dict(segments=SEGMENTS, targets=[{"name": "T1", "north": -300.0, "east": 300.0, "tvd": 1400.0,
                                             "radius": 50.0}])
    base.update(overrides)
    return dp.plan_inputs(base.pop("segments"), **base)


def _open(path, tmp_path, monkeypatch, *, principal=None) -> DatabaseManager:
    _configure(tmp_path, monkeypatch, path)
    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    if principal is not None:
        users = dict(sqlite3.connect(path).execute("SELECT username, id FROM users").fetchall())
        manager.enforce_authorization(Principal(principal, users["admin"], "admin"))
    return manager


def _seed(manager) -> dict:
    with manager.session_scope() as session:
        q = session.execute
        q(text("INSERT INTO companies(name, code) VALUES ('Synthetic Co', 'M70')"))
        company = q(text("SELECT id FROM companies WHERE code='M70'")).scalar()
        q(text("INSERT INTO projects(company_id, name, code) VALUES (:c, 'Synthetic', 'M70P')"), {"c": company})
        project = q(text("SELECT id FROM projects WHERE code='M70P'")).scalar()
        ids = {}
        for code in ("A", "B"):
            q(text("INSERT INTO wells(project_id, name, code) VALUES (:p, :n, :c)"),
              {"p": project, "n": f"SYN-{code}", "c": f"M70{code}"})
            well = q(text("SELECT id FROM wells WHERE code=:c"), {"c": f"M70{code}"}).scalar()
            q(text("INSERT INTO wellbores(well_id, name, wellbore_type) VALUES (:w, :n, 'original')"),
              {"w": well, "n": f"SYN-{code} OH"})
            bore = q(text("SELECT id FROM wellbores WHERE well_id=:w"), {"w": well}).scalar()
            ids[code] = (well, bore)
    return ids


@pytest.fixture(params=["fresh", "upgraded"])
def env(request, tmp_path, monkeypatch):
    path = tmp_path / f"{request.param}.sqlite"
    if request.param == "upgraded":
        _build_old_schema(path, 5)
        with sqlite3.connect(path) as connection:  # a pre-M62 database: none of the history tables
            for table in NEW_TABLES:
                connection.execute(f"DROP TABLE {table}")
    manager = _open(path, tmp_path, monkeypatch)
    ids = _seed(manager)
    yield manager, path, ids
    manager.close()


def _count(path, sql, *args):
    with sqlite3.connect(path) as connection:
        return connection.execute(sql, args).fetchone()[0]


# ---------------------------------------------------------------- M70.1 immutability
IMMUTABLE_VALUES = {
    "inputs": {"segments": []}, "results": {"stations": []}, "method": "other", "method_version": "v0",
    "plan_key": "forged", "revision": 99, "name": "renamed", "note": "edited", "created_at": datetime(2001, 1, 1),
}


def test_the_guards_exist_on_fresh_and_upgraded_databases(env):
    _manager, path, _ids = env
    with sqlite3.connect(path) as connection:
        live = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert set(trigger_statements()) <= live


@pytest.mark.parametrize("column", sorted(IMMUTABLE_VALUES) + ["well_id", "wellbore_id", "parent_id", "created_by"])
def test_every_plan_column_except_status_is_immutable_on_every_write_path(env, column):
    manager, path, ids = env
    (well_a, bore_a), (well_b, bore_b) = ids["A"], ids["B"]
    first = dp.save_plan(manager, well_id=well_a, wellbore_id=bore_a, name="P", inputs=_inputs())
    plan = dp.revise_plan(manager, first["id"], _inputs())
    value = {"well_id": well_b, "wellbore_id": bore_b, "parent_id": None, "created_by": 1}.get(
        column, IMMUTABLE_VALUES.get(column))
    if column == "wellbore_id":
        value = None  # even "unknown" is refused while the wellbore exists
    # 1) ORM unit of work
    with pytest.raises(sa_exc.DBAPIError, match="immutable"):
        with manager.session_scope() as session:
            row = session.get(DirectionalPlanRevision, plan["id"])
            setattr(row, column, value)
    # 2) ORM bulk update
    with pytest.raises(sa_exc.DBAPIError, match="immutable"):
        with manager.session_scope() as session:
            session.execute(update(DirectionalPlanRevision).where(DirectionalPlanRevision.id == plan["id"])
                            .values({column: value}))
    # 3) raw SQL on a separate connection
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.DatabaseError, match="immutable"):
        connection.execute(f"UPDATE directional_plan_revisions SET {column} = ? WHERE id = ?",
                           ("{}" if isinstance(value, dict) else str(value) if isinstance(value, datetime) else value,
                            plan["id"]))
    assert dp.get_plan(manager, plan["id"]) == plan


def test_an_editor_cannot_update_plans_outside_the_lifecycle_and_the_denial_is_audited(tmp_path, monkeypatch):
    path = tmp_path / "authz.sqlite"
    manager = _open(path, tmp_path, monkeypatch)
    (well, bore) = _seed(manager)["A"]
    plan = dp.save_plan(manager, well_id=well, wellbore_id=bore, name="P", inputs=_inputs())
    manager.close()
    editor = _open(path, tmp_path, monkeypatch, principal="engineer")
    try:
        with pytest.raises(AuthorizationError):
            with editor.session_scope() as session:
                session.get(DirectionalPlanRevision, plan["id"]).status = "approved"
        assert _count(path, "SELECT COUNT(*) FROM audit_logs WHERE action='authorization_denied'") == 1
        assert dp.set_status(editor, plan["id"], "approved")["status"] == "approved"   # the lifecycle path
    finally:
        editor.close()


def test_status_transitions_are_enforced_by_service_and_storage(env):
    manager, path, ids = env
    well, bore = ids["A"]
    plan = dp.save_plan(manager, well_id=well, wellbore_id=bore, name="P", inputs=_inputs())
    assert dp.set_status(manager, plan["id"], "approved")["status"] == "approved"
    with pytest.raises(dp.PlanIntegrityError, match="cannot go from approved to draft"):
        dp.set_status(manager, plan["id"], "draft")
    assert dp.set_status(manager, plan["id"], "archived")["status"] == "archived"
    with pytest.raises(dp.PlanIntegrityError, match="stays archived"):
        dp.set_status(manager, plan["id"], "approved")
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.DatabaseError, match="status transition"):
        connection.execute("UPDATE directional_plan_revisions SET status='draft' WHERE id=?", (plan["id"],))
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.DatabaseError, match="status transition"):
        connection.execute("UPDATE directional_plan_revisions SET status='bogus' WHERE id=?", (plan["id"],))
    rejected = _count(path, "SELECT COUNT(*) FROM audit_logs WHERE action='PLAN_STATUS_REJECTED' "
                            "AND entity_id=?", plan["id"])
    assert rejected == 2
    assert dp.get_plan(manager, plan["id"])["status"] == "archived"


def test_calculation_cases_are_immutable_on_every_write_path(env):
    manager, path, ids = env
    well, _bore = ids["A"]
    case = cc.save_case(manager, calculator="Quick Calc", name="c1", inputs={"a": 1}, results={"b": 2},
                        well_id=well)
    with pytest.raises(sa_exc.DBAPIError, match="immutable"):
        with manager.session_scope() as session:
            session.get(CalculationCase, case["id"]).results = {"b": 3}
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.DatabaseError, match="immutable"):
        connection.execute("UPDATE calculation_cases SET name='x' WHERE id=?", (case["id"],))


# ---------------------------------------------------------------- M70.2 snapshot consistency
def test_a_supplied_result_must_correspond_to_the_stored_inputs(env):
    manager, _path, ids = env
    well, bore = ids["A"]
    other = design_plan(SEGMENTS[:2], targets=[])
    with pytest.raises(dp.PlanIntegrityError, match="does not correspond to the inputs"):
        dp.save_plan(manager, well_id=well, wellbore_id=bore, name="P", inputs=_inputs(), result=other)
    inputs = _inputs()
    matching = dp.run_inputs(inputs)
    saved = dp.save_plan(manager, well_id=well, wellbore_id=bore, name="P", inputs=inputs, result=matching)
    assert saved["results"]["result_sha256"] == dp.result_fingerprint(saved["results"])
    assert dp.result_fingerprint(dict(saved["results"], warnings=["forged"])) != saved["results"]["result_sha256"]


def test_lineage_well_and_wellbore_boundaries_are_enforced(env):
    manager, _path, ids = env
    (well_a, bore_a), (well_b, bore_b) = ids["A"], ids["B"]
    with pytest.raises(dp.PlanIntegrityError, match=f"Wellbore {bore_b} does not belong to well {well_a}"):
        dp.save_plan(manager, well_id=well_a, wellbore_id=bore_b, name="P", inputs=_inputs())
    plan_a = dp.save_plan(manager, well_id=well_a, wellbore_id=bore_a, name="A", inputs=_inputs())
    with pytest.raises(dp.PlanIntegrityError, match="belongs to well"):
        dp.save_plan(manager, well_id=well_b, wellbore_id=bore_b, name="B", inputs=_inputs(), parent_id=plan_a["id"])
    with pytest.raises(dp.PlanIntegrityError, match="cannot move to another well"):
        dp.save_plan(manager, well_id=well_b, wellbore_id=bore_b, name="A", inputs=_inputs(),
                     plan_key=plan_a["plan_key"], parent_id=None)
    with pytest.raises(dp.PlanIntegrityError, match="does not exist; save it as a new plan"):
        dp.save_plan(manager, well_id=well_a, wellbore_id=bore_a, name="A", inputs=_inputs(), plan_key="nope")
    with pytest.raises(dp.PlanIntegrityError, match="Parent revision 999999 does not exist"):
        dp.save_plan(manager, well_id=well_a, wellbore_id=bore_a, name="A", inputs=_inputs(), parent_id=999999)
    with pytest.raises(dp.PlanIntegrityError, match="not valid and was not saved"):
        dp.save_plan(manager, well_id=well_a, wellbore_id=bore_a, name="A",
                     inputs=_inputs(segments=[{"type": "hold", "length": float("nan")}]))


def test_stale_and_concurrent_revisions_are_rejected_and_archived_rows_stay_archived(env, monkeypatch):
    manager, _path, ids = env
    well, bore = ids["A"]
    r1 = dp.save_plan(manager, well_id=well, wellbore_id=bore, name="P", inputs=_inputs())
    r2 = dp.revise_plan(manager, r1["id"], _inputs())
    with pytest.raises(dp.StaleRevisionError, match="Revision 1 is not the latest revision \\(2\\)"):
        dp.revise_plan(manager, r1["id"], _inputs())
    monkeypatch.setattr(dp, "_next_revision", lambda session, key: 2)   # another writer already took rev 2
    with pytest.raises(dp.StaleRevisionError, match="saved at the same time"):
        dp.revise_plan(manager, r2["id"], _inputs())
    monkeypatch.undo()
    dp.set_status(manager, r2["id"], "archived")
    r3 = dp.revise_plan(manager, r2["id"], _inputs())
    assert (r3["revision"], r3["status"], r3["parent_id"]) == (3, "draft", r2["id"])
    assert dp.get_plan(manager, r2["id"])["status"] == "archived"
    assert [p["revision"] for p in dp.list_plans(manager, well, include_archived=True) if p["plan_key"] == r1["plan_key"]] == [3, 2, 1]


# ---------------------------------------------------------------- M70.3 well deletion
def _history_rows(path, well):
    return {
        "plans": _count(path, "SELECT COUNT(*) FROM directional_plan_revisions WHERE well_id=?", well),
        "cases": _count(path, "SELECT COUNT(*) FROM calculation_cases WHERE well_id=?", well),
        "links": _count(path, "SELECT COUNT(*) FROM calculation_source_links WHERE source_well_id=?", well),
    }


def _fill(manager, path, well, bore):
    r1 = dp.save_plan(manager, well_id=well, wellbore_id=bore, name="P", inputs=_inputs())
    dp.revise_plan(manager, r1["id"], _inputs())
    dp.clone_plan(manager, r1["id"], "Q")
    c1 = cc.save_case(manager, calculator="Quick Calc", name="c1", inputs={"a": 1}, results={"b": 2},
                      well_id=well, wellbore_id=bore)
    c2 = cc.save_case(manager, calculator="Quick Calc", name="c2", inputs={"a": 1}, results={"b": 2},
                      well_id=well, wellbore_id=bore, parent_id=c1["id"])
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO calculation_source_links(case_id, link_type, source_table, source_id, source_well_id, "
            "source_wellbore_id, verification_status, method_changed, created_at) "
            "VALUES (?, 'recalculation_of', 'directional_plan_revisions', ?, ?, ?, 'MATCH', 0, CURRENT_TIMESTAMP)",
            (c2["id"], r1["id"], well, bore))


def test_deleting_a_well_removes_its_history_rows_with_one_audit_record(env, tmp_path, monkeypatch):
    manager, path, ids = env
    (well_a, bore_a), (well_b, bore_b) = ids["A"], ids["B"]
    _fill(manager, path, well_a, bore_a)
    _fill(manager, path, well_b, bore_b)
    manager.close()
    admin = _open(path, tmp_path, monkeypatch, principal="admin")
    try:
        assert admin.delete_hierarchy_entity("well", well_a) is True
    finally:
        admin.close()
    assert _count(path, "SELECT COUNT(*) FROM wells WHERE id=?", well_a) == 0
    assert _history_rows(path, well_a) == {"plans": 0, "cases": 0, "links": 0}
    assert _history_rows(path, well_b) == {"plans": 3, "cases": 2, "links": 1}     # the other well is untouched
    assert _count(path, "SELECT COUNT(*) FROM audit_logs WHERE action='delete' AND entity_type='well' "
                        "AND entity_id=?", well_a) == 1
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_a_failed_audit_rolls_the_whole_well_deletion_back(env, monkeypatch):
    manager, path, ids = env
    well, bore = ids["A"]
    _fill(manager, path, well, bore)

    def broken_audit(*_a, **_k):
        raise RuntimeError("synthetic audit failure")

    monkeypatch.setattr(manager, "_add_mandatory_audit", broken_audit)
    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        manager.delete_hierarchy_entity("well", well)
    assert _count(path, "SELECT COUNT(*) FROM wells WHERE id=?", well) == 1
    assert _history_rows(path, well) == {"plans": 3, "cases": 2, "links": 1}


def test_a_viewer_cannot_delete_a_well_with_history(env, tmp_path, monkeypatch):
    manager, path, ids = env
    well, bore = ids["A"]
    _fill(manager, path, well, bore)
    manager.close()
    viewer = _open(path, tmp_path, monkeypatch, principal="viewer")
    try:
        with pytest.raises(AuthorizationError):
            viewer.delete_hierarchy_entity("well", well)
    finally:
        viewer.close()
    assert _history_rows(path, well) == {"plans": 3, "cases": 2, "links": 1}


def test_deleting_a_wellbore_sets_history_references_to_unknown(env):
    manager, path, ids = env
    well, bore = ids["A"]
    _fill(manager, path, well, bore)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("DELETE FROM wellbores WHERE id=?", (bore,))
    assert _count(path, "SELECT COUNT(*) FROM directional_plan_revisions WHERE wellbore_id IS NOT NULL "
                        "AND well_id=?", well) == 0
    assert _count(path, "SELECT COUNT(*) FROM calculation_cases WHERE wellbore_id IS NOT NULL AND well_id=?", well) == 0
    assert _history_rows(path, well) == {"plans": 3, "cases": 2, "links": 1}


def test_the_model_declares_the_history_cascades():
    for table in NEW_TABLES:
        for fk in Base.metadata.tables[table].foreign_keys:
            target = fk.column.table.name
            if target == "wells" or (table == "calculation_source_links" and target == "calculation_cases"):
                assert fk.ondelete == "CASCADE", (table, fk)
            elif target in ("wellbores", table):
                assert fk.ondelete == "SET NULL", (table, fk)
