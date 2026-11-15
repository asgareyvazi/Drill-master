"""M204: every immutable table refuses every supported SQL write route that could change a stored row.

The M70 / M96 / M136 / M178 guards (``core.storage_guards._OWNED``) and the M189 + M203 tubular guards are attacked
generically, table by table, on a real application database file:

* ``UPDATE`` of a frozen column (``id``), through raw SQL and through the application's ORM session (bulk update);
* ``INSERT OR REPLACE`` / ``REPLACE INTO`` on the stored id and on every declared unique key;
* ``INSERT ... ON CONFLICT(id) DO UPDATE``;

each with ``recursive_triggers`` OFF (the SQLite default, which lets REPLACE delete without DELETE triggers) and ON.
The stored row must be byte-for-byte unchanged afterwards. Rows are synthetic and inserted with foreign keys off on
a scratch connection; the guards do not depend on the referenced rows for these routes.

Out of scope, stated rather than hidden: anyone who can write the file can ``DROP TRIGGER`` (owner gate P13).
"""
from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import text

from core import storage_guards as sg
from tests.test_m70_integrity import _open, _seed

TABLES = {table: keys for _prefix, (table, keys, _owner) in sg._OWNED.items()}
TABLES.update({table: ((constraint, key),) for table, (_p, constraint, key) in sg._TUBULAR_UNIQUE.items()})
PUBLISHED = {"tubular_reference_sets"}          # the items row is attached to a published set below


def _dummy(column_type: str, name: str):
    kind = (column_type or "").upper()
    if name == "status":
        return "PUBLISHED"
    if "INT" in kind or "BOOL" in kind:
        return 7
    if any(k in kind for k in ("REAL", "FLOA", "DOUB", "NUMERIC")):
        return 1.5
    if "DATE" in kind or "TIME" in kind:
        return "2026-01-02 03:04:05"
    return f"syn-{name}"


@pytest.fixture
def db(tmp_path, monkeypatch):
    manager = _open(tmp_path / "m204.sqlite", tmp_path, monkeypatch)
    _seed(manager)
    return manager


def _insert_row(path, table, row_id, status="PUBLISHED"):
    with sqlite3.connect(path) as c:
        c.execute("PRAGMA foreign_keys = OFF")
        info = c.execute(f"PRAGMA table_info({table})").fetchall()
        values = {}
        for _cid, name, ctype, notnull, default, pk in info:
            if pk:
                values[name] = row_id
            elif notnull and default is None:
                values[name] = _dummy(ctype, name)
        if table == "tubular_reference_items":
            values["set_id"] = 4242
        if table == "tubular_reference_sets":
            values.update(name="syn-published", version=1, status=status, content_fingerprint="f" * 64)
        if table in ("directional_plan_revisions",):
            values["status"] = "approved"
        c.execute(f"INSERT INTO {table} ({', '.join(values)}) VALUES ({', '.join('?' * len(values))})",
                  tuple(values.values()))
        return dict(zip([i[1] for i in info], c.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()))


def _prepare(path, table):
    """The row under attack. An item is added while its set is a DRAFT, then the set is published (raw UPDATE,
    allowed from DRAFT) - the guards refuse new items in a published set, which is part of what is tested."""
    if table != "tubular_reference_items":
        return _insert_row(path, table, 4243)
    _insert_row(path, "tubular_reference_sets", 4242, status="DRAFT")
    row = _insert_row(path, table, 4243)
    with sqlite3.connect(path) as c:
        c.execute("UPDATE tubular_reference_sets SET status = 'PUBLISHED' WHERE id = 4242")
    return row


def _routes(table, row, keys):
    cols = list(row)
    marks = ", ".join("?" for _ in cols)
    same = tuple(row[c] for c in cols)
    out = [("UPDATE id", f"UPDATE {table} SET id = id + 1000 WHERE id = ?", (row["id"],)),
           ("INSERT OR REPLACE same id", f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({marks})", same),
           ("REPLACE INTO same id", f"REPLACE INTO {table} ({', '.join(cols)}) VALUES ({marks})", same),
           ("ON CONFLICT(id) DO UPDATE", f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({marks}) "
                                         f"ON CONFLICT(id) DO UPDATE SET id = excluded.id", same)]
    for constraint, _key in keys:
        other = dict(row, id=row["id"] + 500)
        out.append((f"REPLACE on unique key {constraint}",
                    f"REPLACE INTO {table} ({', '.join(cols)}) VALUES ({marks})", tuple(other[c] for c in cols)))
    return out


def _snapshot(path, table, row_id):
    with sqlite3.connect(path) as c:
        return c.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone(), \
            c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


@pytest.mark.parametrize("recursive", ["OFF", "ON"])
@pytest.mark.parametrize("table", sorted(TABLES))
def test_every_immutable_table_refuses_update_replace_and_upsert(db, table, recursive):
    path = str(db.db_path)
    row = _prepare(path, table)
    before = _snapshot(path, table, row["id"])
    assert before[0] is not None
    for label, sql, params in _routes(table, row, TABLES[table]):
        with sqlite3.connect(path) as c:
            c.execute(f"PRAGMA recursive_triggers = {recursive}")
            c.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError):
                c.execute(sql, params)
            c.rollback()
        assert _snapshot(path, table, row["id"]) == before, f"{table}: {label} (recursive {recursive}) changed it"


@pytest.mark.parametrize("table", sorted(TABLES))
def test_the_orm_session_bulk_update_is_refused_too(db, table):
    path = str(db.db_path)
    row = _prepare(path, table)
    before = _snapshot(path, table, row["id"])
    with pytest.raises(Exception, match="immutable|append-only|cannot|not allowed"):
        with db.session_scope() as session:
            session.execute(text(f"UPDATE {table} SET id = id + 1000 WHERE id = :i"), {"i": row["id"]})
    assert _snapshot(path, table, row["id"]) == before


def test_every_guarded_table_has_a_noreplace_trigger_installed(db):
    with sqlite3.connect(str(db.db_path)) as c:
        names = sg.installed(c)
    for prefix, (table, keys, _owner) in sg._OWNED.items():
        assert f"{prefix}_noreplace_v{sg.INSERT_GUARD_VERSION}" in names, table
        if keys:
            assert f"{prefix}_nodupkey_v{sg.INSERT_GUARD_VERSION}" in names, table
    for _table, (prefix, _c, _k) in sg._TUBULAR_UNIQUE.items():
        assert f"{prefix}_noreplace_v{sg.TUBULAR_INSERT_GUARD_VERSION}" in names
        assert f"{prefix}_nodupkey_v{sg.TUBULAR_INSERT_GUARD_VERSION}" in names
