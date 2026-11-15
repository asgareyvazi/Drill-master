"""M203: adversarial re-audit of D61 - published tubular reference sets and items against every SQL write path.

M189 added UPDATE / DELETE / INSERT guards. They did not cover the REPLACE conflict resolution: when a row is
replaced, SQLite deletes the old row WITHOUT running its DELETE triggers unless ``recursive_triggers`` is ON
(https://sqlite.org/lang_conflict.html), and the application never turns it on. This file attacks the exact
product schema (a real DatabaseManager file) through four connection kinds and asserts that a published set, its
items, the foreign keys and the case snapshots are byte-for-byte unchanged afterwards, while drafts stay editable.

Fixture: an EMPTY published set, a published set with items, a DRAFT set and a second (draft) version of the same
reference set. Every value is synthetic (``SYN-*``).
"""
from __future__ import annotations

import sqlite3

import pytest

from core import sqlite_connection
from core.engineering import reference_binding as rb
from core.engineering import tubular_reference as tr
from tests.test_m70_integrity import _open, _seed

PROV = tr.Provenance(origin="user", entered_by="synthetic-tester", document="SYN sheet")
SPECS = [tr.TubularSpec("DP", "SYN-DP-48", PROV, grade="SYN-G", nominal_od_in=4.871, id_in=4.013, weight_ppf=18.7),
         tr.TubularSpec("CASING", "SYN-CSG-96", PROV, nominal_od_in=9.611, id_in=8.703, weight_ppf=46.1)]
KINDS = ("application", "raw", "recursive_off", "recursive_on")


@pytest.fixture
def lib(tmp_path, monkeypatch):
    db = _open(tmp_path / "m203.sqlite", tmp_path, monkeypatch)
    _seed(db)
    empty = tr.create_set(db, "SYN empty")["id"]
    # The application refuses to publish an empty set; an empty PUBLISHED row can only come from raw SQL (allowed:
    # OLD.status is DRAFT), so the attack surface includes it.
    with sqlite3.connect(str(db.db_path)) as c:
        c.execute("UPDATE tubular_reference_sets SET status = 'PUBLISHED', content_fingerprint = ? WHERE id = ?",
                  ("e" * 64, empty))
    full = tr.create_set(db, "SYN library")["id"]
    for spec in SPECS:
        tr.add_item(db, full, spec)
    tr.publish_set(db, full)
    next_version = tr.create_set(db, "SYN library")["id"]       # v2 DRAFT of the same set (copies the items)
    draft = tr.create_set(db, "SYN draft")["id"]
    tr.add_item(db, draft, SPECS[0])
    path = str(db.db_path)
    row = next(r for r in tr.search(db, set_id=full) if r["spec"].designation == "SYN-DP-48")
    return {"db": db, "path": path, "empty": empty, "full": full, "next": next_version, "draft": draft,
            "snapshot": tr.reference_snapshot(row)}


def _connect(path, kind):
    if kind == "application":
        return sqlite_connection.connect(path)
    connection = sqlite3.connect(path)
    if kind == "recursive_off":
        connection.execute("PRAGMA recursive_triggers = OFF")
    elif kind == "recursive_on":
        connection.execute("PRAGMA recursive_triggers = ON")
    return connection


def _state(path):
    """Every published row, every item, the foreign-key check: the evidence compared before and after."""
    with sqlite3.connect(path) as c:
        sets = c.execute("SELECT * FROM tubular_reference_sets ORDER BY id").fetchall()
        items = c.execute("SELECT * FROM tubular_reference_items ORDER BY id").fetchall()
        c.execute("PRAGMA foreign_keys = ON")
        fk = c.execute("PRAGMA foreign_key_check").fetchall()
    return sets, items, fk


def _published_items(path, set_id):
    with sqlite3.connect(path) as c:
        return c.execute("SELECT * FROM tubular_reference_items WHERE set_id = ? ORDER BY id", (set_id,)).fetchall()


def _set_row(path, set_id):
    with sqlite3.connect(path) as c:
        return c.execute("SELECT * FROM tubular_reference_sets WHERE id = ?", (set_id,)).fetchone()


def _attacks(lib):
    """(label, sql, params) - every statement must be refused on a published row."""
    path, full, empty, draft = lib["path"], lib["full"], lib["empty"], lib["draft"]
    item = _published_items(path, full)[0]
    item_id = item[0]
    with sqlite3.connect(path) as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(tubular_reference_items)")]
        row = dict(zip(cols, item))
        set_cols = [r[1] for r in c.execute("PRAGMA table_info(tubular_reference_sets)")]
        full_set = dict(zip(set_cols, _set_row(path, full)))
        empty_set = dict(zip(set_cols, _set_row(path, empty)))

    def item_insert(verb, **changes):
        values = dict(row, **changes)
        names = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        return f"{verb} INTO tubular_reference_items ({names}) VALUES ({marks})", tuple(values.values())

    def set_insert(verb, base, **changes):
        values = dict(base, **changes)
        names = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        return f"{verb} INTO tubular_reference_sets ({names}) VALUES ({marks})", tuple(values.values())

    out = [
        ("set UPDATE", "UPDATE tubular_reference_sets SET notes = 'x' WHERE id = ?", (full,)),
        ("set DELETE", "DELETE FROM tubular_reference_sets WHERE id = ?", (full,)),
        ("item UPDATE", "UPDATE tubular_reference_items SET weight_ppf = 1 WHERE id = ?", (item_id,)),
        ("item DELETE", "DELETE FROM tubular_reference_items WHERE id = ?", (item_id,)),
        ("item move to draft", "UPDATE tubular_reference_items SET set_id = ? WHERE id = ?", (draft, item_id)),
        ("item plain INSERT, new id into published set",
         "INSERT INTO tubular_reference_items (set_id, component_type, origin, payload_json, fingerprint) "
         "VALUES (?, 'DP', 'user', '{}', 'syn-new')", (full,)),
        ("item upsert ON CONFLICT(id) DO UPDATE",
         item_insert("INSERT", weight_ppf=1.0)[0] + " ON CONFLICT(id) DO UPDATE SET weight_ppf = excluded.weight_ppf",
         item_insert("INSERT", weight_ppf=1.0)[1]),
    ]
    out += [
        ("item INSERT OR REPLACE, same id, same published set",) + item_insert("INSERT OR REPLACE", weight_ppf=1.0),
        ("item REPLACE INTO, same id, moved to a draft set",) + item_insert("REPLACE", set_id=draft),
        ("item REPLACE INTO, same id, moved to the next version",) + item_insert("REPLACE", set_id=lib["next"]),
        ("item INSERT OR REPLACE on the unique key (set_id, fingerprint), new id",)
        + item_insert("INSERT OR REPLACE", id=None, weight_ppf=2.0),
        ("set INSERT OR REPLACE, same id, DRAFT status",) + set_insert("INSERT OR REPLACE", full_set, status="DRAFT"),
        ("set REPLACE INTO, same id, changed fingerprint",)
        + set_insert("REPLACE", full_set, content_fingerprint="0" * 64),
        ("set REPLACE INTO, empty published set",) + set_insert("REPLACE", empty_set, notes="replaced"),
        ("set INSERT OR REPLACE on the unique key (name, version), new id",)
        + set_insert("INSERT OR REPLACE", full_set, id=None, status="DRAFT"),
        ("set upsert ON CONFLICT(id) DO UPDATE",
         set_insert("INSERT", full_set)[0] + " ON CONFLICT(id) DO UPDATE SET status = 'DRAFT'",
         set_insert("INSERT", full_set)[1]),
        ("set plain INSERT duplicate name/version",) + set_insert("INSERT", full_set, id=None),
        # M210: the same id with ANOTHER unique key - only the id guard can refuse these (the key guard sees a new
        # key), and the conflict on the id would delete the published row without its DELETE trigger.
        ("set REPLACE INTO, same id, another name and version",)
        + set_insert("REPLACE", full_set, name="SYN other", version=77, status="DRAFT"),
        ("item REPLACE INTO, same id, another fingerprint",) + item_insert("REPLACE", fingerprint="syn-other"),
    ]
    return out


@pytest.mark.parametrize("kind", KINDS)
def test_no_sql_write_path_changes_a_published_set_or_its_items(lib, kind):
    before = _state(lib["path"])
    assert before[2] == []
    refused = []
    for label, sql, params in _attacks(lib):
        connection = _connect(lib["path"], kind)
        try:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(sql, params)
                connection.commit()
            refused.append(label)
        finally:
            connection.rollback()
            connection.close()
        assert _state(lib["path"]) == before, f"{kind}: {label} changed stored rows"
    assert len(refused) == len(_attacks(lib))
    # The case snapshot taken before the attacks still matches its set.
    assert rb.drift(lib["db"], lib["snapshot"]).state == rb.MATCH


@pytest.mark.parametrize("kind", KINDS)
def test_drafts_stay_editable_replaceable_and_publishable(lib, kind):
    path, draft, nxt = lib["path"], lib["draft"], lib["next"]
    connection = _connect(path, kind)
    try:
        connection.execute("UPDATE tubular_reference_sets SET notes = 'draft note' WHERE id = ?", (draft,))
        item = connection.execute("SELECT id FROM tubular_reference_items WHERE set_id = ?", (draft,)).fetchone()[0]
        connection.execute("UPDATE tubular_reference_items SET weight_ppf = 18.8 WHERE id = ?", (item,))
        connection.execute("DELETE FROM tubular_reference_items WHERE id = ?", (item,))
        connection.execute("INSERT INTO tubular_reference_items (set_id, component_type, origin, payload_json, "
                           "fingerprint) VALUES (?, 'DP', 'user', '{}', 'syn-draft')", (draft,))
        connection.commit()
    finally:
        connection.close()
    # The importer path (DRAFT) and the publish path still work after the raw edits.
    assert tr.publish_set(lib["db"], nxt)["version"] == 2
    statuses = {s["id"]: s["status"] for s in tr.list_sets(lib["db"])}
    assert statuses[nxt] == tr.PUBLISHED and statuses[draft] == tr.DRAFT


def test_a_draft_row_with_another_key_may_not_be_replaced_either(lib):
    with sqlite3.connect(lib["path"]) as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(tubular_reference_sets)")]
        row = dict(zip(cols, _set_row(lib["path"], lib["draft"])), name="SYN renamed", version=55)
        with pytest.raises(sqlite3.IntegrityError, match="cannot be replaced"):
            c.execute(f"REPLACE INTO tubular_reference_sets ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                      tuple(row.values()))
        assert c.execute("SELECT COUNT(*) FROM tubular_reference_items WHERE set_id = ?",
                         (lib["draft"],)).fetchone()[0] == 1


def test_a_draft_row_may_not_be_replaced_either_because_replace_cascades_silently(lib):
    # REPLACE on a draft set would delete its items through the FK cascade without any trigger: refused too,
    # so the only way to change a draft is UPDATE / DELETE / INSERT, which the importer uses.
    with sqlite3.connect(lib["path"]) as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(tubular_reference_sets)")]
        row = dict(zip(cols, _set_row(lib["path"], lib["draft"])))
        with pytest.raises(sqlite3.IntegrityError, match="cannot be replaced"):
            c.execute(f"REPLACE INTO tubular_reference_sets ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                      tuple(row.values()))
        assert c.execute("SELECT COUNT(*) FROM tubular_reference_items WHERE set_id = ?",
                         (lib["draft"],)).fetchone()[0] == 1


def test_the_guards_survive_backup_and_restore_and_an_upgrade_reinstalls_them(lib, tmp_path):
    from core import storage_guards
    with sqlite3.connect(lib["path"]) as c:
        names = storage_guards.installed(c)
    for name in ("trg_tubular_set_noreplace_v1", "trg_tubular_set_nodupkey_v1", "trg_tubular_item_noreplace_v1",
                 "trg_tubular_item_nodupkey_v1"):
        assert name in names
    copy = tmp_path / "copy.sqlite"
    with sqlite3.connect(lib["path"]) as src, sqlite3.connect(copy) as dst:
        src.backup(dst)
    with sqlite3.connect(copy) as c:
        assert "trg_tubular_set_noreplace_v1" in storage_guards.installed(c)
        c.execute("DROP TRIGGER trg_tubular_set_noreplace_v1")
        assert storage_guards.install(c) == ["trg_tubular_set_noreplace_v1"]
