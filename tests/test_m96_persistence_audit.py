"""M96 - persistence audit: foreign keys, deletion through every app path, migrations, rollback,
concurrency and immutability through every write path.

Real ``DatabaseManager`` on temporary SQLite files (fresh and upgraded from an old schema), the real pool,
authorization hooks and storage triggers.  Synthetic data only.

Defects found by this audit and fixed in M96:

* Six legacy W13 calculation tables reference ``wells`` with no ON DELETE action and no ORM cascade: one saved
  W13 calculation made its well (and its project/company) undeletable - ``delete_well`` returned False.
* ``operational_procedures.section_id`` has no ON DELETE action: a procedure blocked its section's deletion.
* The history guards were BEFORE UPDATE only: ``INSERT OR REPLACE`` overwrote an immutable record and a direct
  ``DELETE`` removed one.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, time

import pytest
from sqlalchemy import text

from core import calculation_cases as cc
from core import directional_plans as dp
from core.authorization import DELETE_WELL, AuthorizationError
from core.database import Base, DatabaseManager
from core.repositories.casing_repository import CasingCalculationRepository
from core.storage_guards import install, trigger_statements
from tests.test_casing_persistence import INPUTS as CASING_INPUTS
from tests.test_data_layer_authorization import Principal
from tests.test_database_migration_acceptance import _build_old_schema, _configure
from tests.test_m70_integrity import _inputs

UNMAPPED = DatabaseManager._UNMAPPED_WELL_CHILDREN
HISTORY = ("directional_plan_revisions", "calculation_cases", "calculation_source_links", "survey_revisions",
           "well_architecture_revisions")


def _open(path, tmp_path, monkeypatch, *, principal=None, permissions=None) -> DatabaseManager:
    _configure(tmp_path, monkeypatch, path)
    manager = DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    if principal is not None:
        users = dict(sqlite3.connect(path).execute("SELECT username, id FROM users").fetchall())
        manager.enforce_authorization(Principal(principal, users["admin"], "admin", permissions))
    return manager


@pytest.fixture(params=["fresh", "upgraded"])
def env(request, tmp_path, monkeypatch):
    path = tmp_path / f"{request.param}.sqlite"
    if request.param == "upgraded":
        _build_old_schema(path, 5)
    manager = _open(path, tmp_path, monkeypatch)
    yield manager, path, tmp_path, monkeypatch
    manager.close()


def _q(path, sql, *args):
    with sqlite3.connect(path) as connection:
        return connection.execute(sql, args).fetchall()


def _value(column, parents):
    fks = list(column.foreign_keys)
    if fks:
        return parents[fks[0].column.table.name]
    try:
        kind = column.type.python_type
    except NotImplementedError:
        kind = str
    return {bool: False, int: 1, float: 1.0, datetime: datetime(2026, 1, 1), date: date(2026, 1, 1),
            time: time(1), dict: {}, list: []}.get(kind, "SYN")


def _row(manager, table, parents, target, **overrides):
    """One minimal synthetic row: the ``target`` FK and every NOT NULL column without a default."""
    tbl = Base.metadata.tables[table]
    values = dict(overrides)
    for column in tbl.columns:
        if column.primary_key or column.name in values:
            continue
        is_target = any(fk.column.table.name == target for fk in column.foreign_keys)
        if is_target or (not column.nullable and column.default is None and column.server_default is None):
            values[column.name] = _value(column, parents)
    with manager.engine.begin() as connection:
        return connection.execute(tbl.insert().values(**values)).inserted_primary_key[0]


def _world(manager, tag):
    with manager.session_scope() as s:
        q = s.execute
        q(text("INSERT INTO companies(name, code) VALUES (:n, :c)"), {"n": f"SYN {tag}", "c": f"C{tag}"})
        company = q(text("SELECT id FROM companies WHERE code=:c"), {"c": f"C{tag}"}).scalar()
        q(text("INSERT INTO projects(company_id, name, code) VALUES (:p, 'SYN', :c)"), {"p": company, "c": f"P{tag}"})
        project = q(text("SELECT id FROM projects WHERE code=:c"), {"c": f"P{tag}"}).scalar()
        q(text("INSERT INTO wells(project_id, name, code) VALUES (:p, :n, :c)"),
          {"p": project, "n": f"SYN-W{tag}", "c": f"W{tag}"})
        well = q(text("SELECT id FROM wells WHERE code=:c"), {"c": f"W{tag}"}).scalar()
        q(text("INSERT INTO sections(well_id, name) VALUES (:w, 'SYN 12 1/4')"), {"w": well})
        section = q(text("SELECT id FROM sections WHERE well_id=:w"), {"w": well}).scalar()
        q(text("INSERT INTO wellbores(well_id, name, wellbore_type) VALUES (:w, 'OH', 'original')"), {"w": well})
        bore = q(text("SELECT id FROM wellbores WHERE well_id=:w"), {"w": well}).scalar()
        q(text("INSERT INTO daily_reports(well_id, section_id, report_date, report_number) "
               "VALUES (:w, :s, '2026-01-01', 1)"), {"w": well, "s": section})
        report = q(text("SELECT id FROM daily_reports WHERE well_id=:w"), {"w": well}).scalar()
        admin = q(text("SELECT id FROM users WHERE username='admin'")).scalar()
    case = cc.save_case(manager, calculator="Quick Calc", name="c", inputs={"a": 1}, results={"r": 1},
                        well_id=well)["id"]
    document = _row(manager, "documents", {}, None, sha256=f"{tag:0>64}"[-64:])
    return {"companies": company, "projects": project, "wells": well, "sections": section, "wellbores": bore,
            "daily_reports": report, "users": admin, "calculation_cases": case, "documents": document}


def _referencing(target):
    return sorted({fk.parent.table.name for t in Base.metadata.sorted_tables for fk in t.foreign_keys
                   if fk.column.table.name == target and fk.parent.table.name != target})


# ------------------------------------------------------------------ deletion through every app path
@pytest.mark.parametrize("kind,target", [("well", "wells"), ("section", "sections"), ("report", "daily_reports")])
def test_every_reference_is_removed_or_unlinked_when_its_parent_is_deleted(env, kind, target):
    manager, path, *_ = env
    outcomes, tag = {}, 0
    for table in _referencing(target):
        tag += 1
        parents = _world(manager, f"{kind}{tag}")
        try:
            child = _row(manager, table, parents, target)
        except Exception as exc:                      # recorded, then asserted empty below
            outcomes[table] = f"FIXTURE {type(exc).__name__}: {str(exc).splitlines()[0][:120]}"
            continue
        try:
            assert manager.delete_hierarchy_entity(kind, parents[target]) is True
        except Exception as exc:
            outcomes[table] = f"REFUSED {type(exc).__name__}"
            continue
        refs = [fk.parent.name for fk in Base.metadata.tables[table].foreign_keys if fk.column.table.name == target]
        left = _q(path, f"SELECT {', '.join(refs)} FROM {table} WHERE id=?", child)
        set_null = all(str(fk.ondelete or "").upper() == "SET NULL"
                       for fk in Base.metadata.tables[table].foreign_keys if fk.column.table.name == target)
        if left and any(v is not None for v in left[0]):
            outcomes[table] = f"DANGLING {left[0]}"
        elif kind != "well" and set_null and not left:   # M116 D33: the well survives, so the record must too
            outcomes[table] = "DELETED DESPITE ON DELETE SET NULL"
        elif _q(path, "PRAGMA foreign_key_check"):
            outcomes[table] = "FK VIOLATION"
        elif _q(path, f"SELECT COUNT(*) FROM {target} WHERE id=?", parents[target])[0][0]:
            outcomes[table] = "PARENT LEFT"
    assert outcomes == {}, outcomes
    assert tag >= {"wells": 45, "sections": 20, "daily_reports": 3}[target]


def test_company_delete_sweeps_unmapped_children_and_records_them_in_the_audit(env):
    manager, path, *_ = env
    parents = _world(manager, "co")
    for table in UNMAPPED:
        _row(manager, table, parents, "wells")
    procedure = _row(manager, "operational_procedures", parents, "wells")
    with manager.engine.begin() as connection:
        connection.execute(text("UPDATE operational_procedures SET section_id=:s WHERE id=:i"),
                           {"s": parents["sections"], "i": procedure})
    assert manager.delete_hierarchy_entity("company", parents["companies"]) is True
    for table in (*UNMAPPED, "operational_procedures", "wells", "sections", "calculation_cases"):
        assert _q(path, f"SELECT COUNT(*) FROM {table} WHERE "
                        f"{'id' if table in ('wells',) else 'well_id'}=?", parents["wells"])[0][0] == 0, table
    details = _q(path, "SELECT details FROM audit_logs WHERE action='delete' AND entity_type='company' "
                       "AND entity_id=?", parents["companies"])
    assert len(details) == 1 and all(f"{t}: 1" in details[0][0] for t in UNMAPPED)
    assert _q(path, "PRAGMA foreign_key_check") == []


def test_a_saved_w13_calculation_no_longer_blocks_deleting_its_well(env):
    manager, path, *_ = env
    parents = _world(manager, "w13")
    from core.engineering.engines.casing import CasingEngine
    result = CasingEngine.evaluate(**CASING_INPUTS)
    CasingCalculationRepository(manager).save_run(inputs=CASING_INPUTS, result_values=result.values,
                                                  method=CasingEngine.METHOD, label="w13", well_id=parents["wells"])
    assert manager.delete_well(parents["wells"]) is True
    assert _q(path, "SELECT COUNT(*) FROM casing_calculations WHERE well_id=?", parents["wells"])[0][0] == 0


def test_a_section_delete_unlinks_procedures_for_a_deleter_without_edit_rights(env):
    manager, path, tmp_path, monkeypatch = env
    parents = _world(manager, "sec")
    procedure = _row(manager, "operational_procedures", parents, "sections")
    manager.close()
    deleter = _open(path, tmp_path, monkeypatch, principal="viewer", permissions={DELETE_WELL: True})
    try:
        assert deleter.delete_hierarchy_entity("section", parents["sections"]) is True
        with pytest.raises(AuthorizationError):          # the unlink scope never authorizes a plain update
            with deleter.session_scope() as s:
                s.execute(text("UPDATE operational_procedures SET section_id=NULL WHERE id=:i"), {"i": procedure})
    finally:
        deleter.close()
    assert _q(path, "SELECT well_id, section_id FROM operational_procedures WHERE id=?", procedure) == \
        [(parents["wells"], None)]


def test_a_refused_delete_rolls_the_sweep_back(env):
    manager, path, tmp_path, monkeypatch = env
    parents = _world(manager, "ro")
    for table in UNMAPPED:
        _row(manager, table, parents, "wells")
    procedure = _row(manager, "operational_procedures", parents, "sections")
    manager.close()
    viewer = _open(path, tmp_path, monkeypatch, principal="viewer")
    try:
        with pytest.raises(AuthorizationError):
            viewer.delete_hierarchy_entity("well", parents["wells"])
    finally:
        viewer.close()
    for table in UNMAPPED:
        assert _q(path, f"SELECT COUNT(*) FROM {table} WHERE well_id=?", parents["wells"])[0][0] == 1, table
    assert _q(path, "SELECT section_id FROM operational_procedures WHERE id=?", procedure) == [(parents["sections"],)]


def test_a_failing_audit_rolls_the_sweep_back(env, monkeypatch):
    manager, path, *_ = env
    parents = _world(manager, "au")
    for table in UNMAPPED:
        _row(manager, table, parents, "wells")

    def broken(*_a, **_k):
        raise RuntimeError("synthetic audit failure")
    monkeypatch.setattr(manager, "_add_mandatory_audit", broken)
    with pytest.raises(RuntimeError):
        manager.delete_hierarchy_entity("well", parents["wells"])
    assert all(_q(path, f"SELECT COUNT(*) FROM {t} WHERE well_id=?", parents["wells"])[0][0] == 1 for t in UNMAPPED)


def test_every_well_foreign_key_without_a_db_action_is_covered_by_an_orm_cascade_or_the_sweep():
    """A new table referencing wells must declare ON DELETE, get an ORM cascade, or join the sweep list."""
    from sqlalchemy import inspect as sa_inspect
    from core.database import Well
    cascaded = {rel.mapper.local_table.name for rel in sa_inspect(Well).relationships if "delete" in rel.cascade}
    uncovered = [(fk.parent.table.name, fk.parent.name) for t in Base.metadata.sorted_tables
                 for fk in t.foreign_keys if fk.column.table.name == "wells" and fk.ondelete is None
                 and fk.parent.table.name not in cascaded and fk.parent.table.name not in UNMAPPED]
    assert uncovered == []


# ------------------------------------------------------------------ immutability through every write path
def _history(manager, path):
    parents = _world(manager, "im")
    well = parents["wells"]
    plan = dp.save_plan(manager, well_id=well, name="P", inputs=_inputs())
    from core import survey_revisions as sr
    from core import well_architecture as wa
    from tests.test_m85_survey_references import MAG
    from tests.test_m89_architecture_casing_cement import ARCH
    survey = sr.save_revision(manager, well, MAG, depth_datum="RKB", azimuth_reference="magnetic")
    arch = wa.save_revision(manager, well, ARCH)
    link_case = cc.save_case(manager, calculator="Quick Calc", name="rerun", inputs={"a": 1}, results={"r": 1},
                             well_id=well, parent_id=parents["calculation_cases"])
    ids = {"directional_plan_revisions": plan["id"], "calculation_cases": parents["calculation_cases"],
           "survey_revisions": survey["id"], "well_architecture_revisions": arch["id"]}
    ids["calculation_source_links"] = _row(
        manager, "calculation_source_links", {"calculation_cases": link_case["id"], "wells": well}, None,
        case_id=link_case["id"], source_table="calculation_cases", source_id=parents["calculation_cases"],
        source_well_id=well, link_type="recalculation_of")
    return well, ids


def _snapshot(path, table, row_id):
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        return dict(connection.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone())


@pytest.mark.parametrize("table", HISTORY)
def test_history_rows_resist_replace_delete_and_duplicate_inserts(env, table):
    manager, path, *_ = env
    well, ids = _history(manager, path)
    before = _snapshot(path, table, ids[table])
    columns = ", ".join(before)
    marks = ", ".join("?" for _ in before)
    forged = dict(before)
    forged["note" if "note" in forged else "link_type"] = "FORGED"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for sql in (f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({marks})",
                    f"REPLACE INTO {table} ({columns}) VALUES ({marks})"):
            with pytest.raises(sqlite3.IntegrityError, match="cannot be replaced"):
                connection.execute(sql, list(forged.values()))
        with pytest.raises(sqlite3.IntegrityError, match="deleted only with its owner"):
            connection.execute(f"DELETE FROM {table} WHERE id=?", (ids[table],))
        if table in ("survey_revisions", "well_architecture_revisions", "directional_plan_revisions"):
            duplicate = {k: v for k, v in forged.items() if k != "id"}
            with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed: uq_"):
                connection.execute(f"INSERT OR REPLACE INTO {table} ({', '.join(duplicate)}) "
                                   f"VALUES ({', '.join('?' for _ in duplicate)})", list(duplicate.values()))
    assert _snapshot(path, table, ids[table]) == before
    assert manager.delete_hierarchy_entity("well", well) is True          # the owner's cascade still works
    assert _q(path, f"SELECT COUNT(*) FROM {table} WHERE id=?", ids[table])[0][0] == 0


def test_a_well_less_case_can_never_be_deleted(env):
    manager, path, *_ = env
    case = cc.save_case(manager, calculator="Quick Calc", name="global", inputs={"a": 1}, results={"r": 1})["id"]
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute("DELETE FROM calculation_cases WHERE id=?", (case,))
    assert _q(path, "SELECT COUNT(*) FROM calculation_cases WHERE id=?", case)[0][0] == 1


def test_a_concurrent_plan_revision_is_still_reported_as_stale(env, monkeypatch):
    manager, *_ = env
    parents = _world(manager, "st")
    r1 = dp.save_plan(manager, well_id=parents["wells"], name="P", inputs=_inputs())
    r2 = dp.revise_plan(manager, r1["id"], _inputs())
    monkeypatch.setattr(dp, "_next_revision", lambda session, key: 2)
    with pytest.raises(dp.StaleRevisionError, match="saved at the same time"):
        dp.revise_plan(manager, r2["id"], _inputs())


# ------------------------------------------------------------------ migrations, pragmas, concurrency
def test_guards_install_on_fresh_and_upgraded_databases_and_reinitialising_is_idempotent(env):
    manager, path, tmp_path, monkeypatch = env
    names = set(trigger_statements())
    assert {n for n in names if "_noreplace_" in n or "_nodelete_" in n or "_nodupkey_" in n} and \
        names <= {r[0] for r in _q(path, "SELECT name FROM sqlite_master WHERE type='trigger'")}
    schema = _q(path, "SELECT type, name, sql FROM sqlite_master ORDER BY type, name")
    manager.close()
    again = _open(path, tmp_path, monkeypatch)
    again.close()
    assert _q(path, "SELECT type, name, sql FROM sqlite_master ORDER BY type, name") == schema
    with sqlite3.connect(path) as connection:
        assert install(connection) == []
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_every_pooled_connection_enforces_foreign_keys_wal_and_a_busy_timeout(env):
    manager, *_ = env
    connections = [manager.engine.connect() for _ in range(3)]
    try:
        for connection in connections:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
            assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
            assert connection.execute(text("PRAGMA busy_timeout")).scalar() >= 5000
    finally:
        for connection in connections:
            connection.close()


def test_a_reader_never_sees_an_uncommitted_write_and_a_second_manager_sees_the_commit(env):
    manager, path, tmp_path, monkeypatch = env
    parents = _world(manager, "cc")
    writer = sqlite3.connect(path, isolation_level=None)
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("UPDATE wells SET name='SYN-RENAMED' WHERE id=?", (parents["wells"],))
    with manager.engine.connect() as reader:                 # WAL snapshot: old value while the writer is open
        assert reader.execute(text("SELECT name FROM wells WHERE id=:i"), {"i": parents["wells"]}).scalar() \
            == "SYN-Wcc"
    writer.execute("ROLLBACK")
    second = DatabaseManager()
    assert second.initialize()
    try:
        with second.session_scope() as s:
            s.execute(text("UPDATE wells SET name='SYN-SECOND' WHERE id=:i"), {"i": parents["wells"]})
        with manager.engine.connect() as reader:
            assert reader.execute(text("SELECT name FROM wells WHERE id=:i"),
                                  {"i": parents["wells"]}).scalar() == "SYN-SECOND"
    finally:
        second.close()
    writer.close()


def test_an_exception_inside_a_unit_of_work_leaves_nothing_behind(env):
    manager, path, *_ = env
    parents = _world(manager, "rb")
    before = _q(path, "SELECT COUNT(*) FROM sections")[0][0]
    with pytest.raises(RuntimeError):
        with manager.session_scope() as s:
            s.execute(text("INSERT INTO sections(well_id, name) VALUES (:w, 'SYN TMP')"), {"w": parents["wells"]})
            raise RuntimeError("synthetic failure mid-transaction")
    assert _q(path, "SELECT COUNT(*) FROM sections")[0][0] == before
