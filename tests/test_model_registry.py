"""One ORM registry, complete registration, and fresh == upgraded schemas (M43).

The application's schema is declared once, in ``core.database``. These tests
fail if a second declarative base appears, if a mapped class or table escapes
the authoritative metadata, or if a database upgraded from any supported
historical version differs from a freshly created one in columns, types,
nullability, primary keys, foreign keys (with actions), unique constraints or
indexes.

Limitation: historical schemas are reconstructed from the current DDL minus
the columns/tables each later version added (see
``tests/test_database_migration_acceptance._build_old_schema``); they are not
captured databases from old installers.
"""
from __future__ import annotations

import ast
import gc
import importlib
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy.orm import registry as sa_registry

import core.database as database
from tests.test_database_migration_acceptance import _build_old_schema, _configure

ROOT = Path(__file__).resolve().parents[1]
APPLICATION_ROOTS = ("core", "tabs", "dialogs", "ui", "config")
APPLICATION_FILES = ("app.py", "main_window.py", "run.py", "reset_database.py", "verify_release.py")
AUTHORITATIVE = Path("core/database.py")
BASE_FACTORIES = {"declarative_base", "DeclarativeBase", "DeclarativeBaseNoMeta", "registry", "as_declarative"}


def _application_sources():
    for root in APPLICATION_ROOTS:
        yield from sorted((ROOT / root).rglob("*.py"))
    for name in APPLICATION_FILES:
        if (ROOT / name).is_file():
            yield ROOT / name


def _base_factories_used(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if name in BASE_FACTORIES:
                lines.append(node.lineno)
        elif isinstance(node, ast.ClassDef):
            for base in node.bases:
                name = base.id if isinstance(base, ast.Name) else base.attr if isinstance(base, ast.Attribute) else None
                if name in {"DeclarativeBase", "DeclarativeBaseNoMeta"}:
                    lines.append(node.lineno)
    return lines


def test_only_core_database_creates_a_declarative_base():
    offenders = {}
    for path in _application_sources():
        rel = path.relative_to(ROOT)
        lines = _base_factories_used(path)
        if lines and rel != AUTHORITATIVE:
            offenders[rel.as_posix()] = lines
    assert offenders == {}, f"second ORM base/registry declared: {offenders}"
    assert len(_base_factories_used(ROOT / AUTHORITATIVE)) == 1


def test_legacy_model_module_re_exports_the_authoritative_classes():
    legacy = importlib.import_module("core.db_models")
    assert legacy.Base is database.Base
    assert legacy.__all__, "the compatibility surface must be explicit"
    for name in legacy.__all__:
        assert getattr(legacy, name) is getattr(database, name), name


def test_every_live_registry_with_mappers_is_the_authoritative_one():
    for module in ("core.db_models", "core.db_services", "core.managers"):
        importlib.import_module(module)
    registries = [obj for obj in gc.get_objects() if isinstance(obj, sa_registry) and obj.mappers]
    assert registries == [database.Base.registry]


def test_registration_is_complete_and_table_names_are_unique():
    mappers = list(database.Base.registry.mappers)
    tables = [mapper.local_table.name for mapper in mappers]
    assert len(tables) == len(set(tables)), "a table is mapped by more than one class"
    assert set(tables) == set(database.Base.metadata.tables), "metadata table without a mapped class (or vice versa)"
    declared = {
        obj for obj in vars(database).values()
        if isinstance(obj, type) and "__tablename__" in vars(obj)
    }
    assert declared == {mapper.class_ for mapper in mappers}


# --------------------------------------------------------------------------
# Live-schema signature


def _signature(path) -> dict:
    with sqlite3.connect(path) as connection:
        names = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        out = {}
        for table in names:
            q = '"' + table.replace('"', '""') + '"'
            columns = {
                row[1]: (row[2].upper(), bool(row[3]), row[5])  # type, NOT NULL, PK position
                for row in connection.execute(f"PRAGMA table_info({q})")
            }
            foreign_keys = sorted(
                (row[3], row[2], row[4], row[5].upper(), row[6].upper())  # from, table, to, on_update, on_delete
                for row in connection.execute(f"PRAGMA foreign_key_list({q})")
            )
            indexes = set()
            for row in connection.execute(f"PRAGMA index_list({q})"):
                name, unique, origin = row[1], bool(row[2]), row[3]
                cols = tuple(r[2] for r in connection.execute(f'PRAGMA index_info("{name}")'))
                # Auto-index names differ between a CREATE TABLE and a rebuild;
                # compare constraint-backed indexes by content, explicit ones by name.
                indexes.add((name if origin == "c" else origin, unique, cols))
            out[table] = {"columns": columns, "foreign_keys": foreign_keys, "indexes": sorted(indexes)}
        return out


def _fresh_signature(tmp_path, monkeypatch) -> dict:
    path = tmp_path / "fresh.sqlite"
    _configure(tmp_path, monkeypatch, path)
    manager = database.DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    manager.close()
    return _signature(path)


def test_fresh_database_contains_exactly_the_declared_schema(tmp_path, monkeypatch):
    live = _fresh_signature(tmp_path, monkeypatch)
    metadata = database.Base.metadata
    assert set(live) == set(metadata.tables) | {"schema_version"}
    for name, table in metadata.tables.items():
        assert set(live[name]["columns"]) == {c.name for c in table.columns}, name
        assert {c for c, v in live[name]["columns"].items() if v[2]} == {c.name for c in table.primary_key}, name
        declared_fks = sorted((fk.parent.name, fk.column.table.name, fk.column.name) for fk in table.foreign_keys)
        assert sorted(fk[:3] for fk in live[name]["foreign_keys"]) == declared_fks, name
        declared_indexes = {i.name for i in table.indexes if i.name}
        assert declared_indexes <= {i[0] for i in live[name]["indexes"]}, name


def _unversioned(path) -> None:
    """A pre-versioning database: the v1 layout without a schema_version table."""
    _build_old_schema(path, 1)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE schema_version")


@pytest.mark.parametrize("old_version", [None, 1, 2, 3, 4])
def test_upgraded_database_is_equivalent_to_a_fresh_one(tmp_path, monkeypatch, old_version):
    fresh = _fresh_signature(tmp_path / "f", monkeypatch)
    path = tmp_path / f"v{old_version}.sqlite"
    _configure(tmp_path, monkeypatch, path)
    if old_version is None:
        _unversioned(path)
    else:
        _build_old_schema(path, old_version)
    manager = database.DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    manager.close()
    upgraded = _signature(path)
    assert set(upgraded) == set(fresh)
    differences = {
        table: {part: (upgraded[table][part], fresh[table][part])
                for part in ("columns", "foreign_keys", "indexes")
                if upgraded[table][part] != fresh[table][part]}
        for table in fresh
    }
    differences = {table: parts for table, parts in differences.items() if parts}
    assert differences == {}, differences
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version FROM schema_version").fetchall() == [(5,)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_foreign_keys_are_enforced_on_application_connections(tmp_path, monkeypatch):
    path = tmp_path / "fk.sqlite"
    _configure(tmp_path, monkeypatch, path)
    manager = database.DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    try:
        raw = manager.engine.raw_connection()
        try:
            assert raw.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            with pytest.raises(sqlite3.IntegrityError):
                raw.execute("INSERT INTO sections(well_id, name) VALUES (?, ?)", (987654, "orphan"))
            raw.rollback()
        finally:
            raw.close()
    finally:
        manager.close()


def test_legacy_service_functions_operate_on_the_migrated_schema(tmp_path, monkeypatch):
    """core.db_services (unwired) now persists through the authoritative models."""
    from core import db_services

    path = tmp_path / "legacy-v2.sqlite"
    _configure(tmp_path, monkeypatch, path)
    _build_old_schema(path, 2)  # an upgraded database, not only a fresh one
    manager = database.DatabaseManager()
    assert manager.initialize(), manager.last_diagnostic
    try:
        with sqlite3.connect(path) as connection:
            well_id = connection.execute("SELECT id FROM wells").fetchone()[0]
        proc_id = db_services.save_procedure(manager, {"well_id": well_id, "title": "Trip out"})
        assert isinstance(proc_id, int)
        assert db_services.save_procedure_steps(manager, proc_id, [{"activity_description": "Flow check"}])
        assert db_services.get_procedure_by_id(manager, proc_id)["title"] == "Trip out"
        assert [s["activity_description"] for s in db_services.get_procedure_steps(manager, proc_id)] == ["Flow check"]
        # An orphan reference is rejected by the enforced foreign key, not stored.
        assert db_services.save_procedure(manager, {"well_id": 987654, "title": "orphan"}) is None
    finally:
        manager.close()
