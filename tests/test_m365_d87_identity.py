"""M365 (D87): content-fingerprint identity for archive marks and clone / lineage links (SYNTHETIC).

Closes the two holes the M292 register left open:

* equal-timestamp collision: a replacement row with the same id AND the same ``created_at``;
* NULL-timestamp source: archiving was refused and clones were IDENTITY_WEAK.

Also checks the stated residual, the pre-M365 timestamp rule for legacy marks, the storage guard on the new
column, bulk archive / restore and authorization.
"""
from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import text

from core import calculation_clone_contract as ccc
from core import calculation_workbench as wb
from core import record_identity as ri
from core import storage_guards as sg
from core.database import ADDITIVE_COLUMNS, CalculationArchiveMark, CasingCalculationRecord
from core.engineering.engines.casing import CasingEngine
from core.repositories.casing_repository import CasingCalculationRepository
from test_m286_workbench_clone_archive import INPUTS, _entry, world  # noqa: F401  (shared SYNTHETIC world)

OTHER = dict(INPUTS, yield_psi=110000.0, grade="SYN-110")


def _casing(db, dev, label, inputs=INPUTS):
    return CasingCalculationRepository(db).save_run(
        inputs=inputs, result_values=CasingEngine.evaluate(**inputs).values, method=CasingEngine.METHOD,
        label=label, well_id=dev)


def _sql(db, statement, **params):
    with db.session_scope() as session:
        return session.execute(text(statement), params)


def _created(db, record_id):
    with db.session_scope() as session:
        return session.execute(text("SELECT created_at FROM casing_calculations WHERE id = :i"),
                               {"i": record_id}).scalar()


def _replace(db, dev, record_id, *, inputs=OTHER, created_at="keep"):
    """Delete the row and create a new one that reuses the id; optionally force its created_at."""
    stamp = _created(db, record_id)
    _sql(db, "DELETE FROM casing_calculations WHERE id = :i", i=record_id)
    assert _casing(db, dev, "SYN M365 replacement", inputs) == record_id            # SQLite reused the id
    if created_at == "keep":
        _sql(db, "UPDATE casing_calculations SET created_at = :c WHERE id = :i", c=stamp, i=record_id)
    elif created_at is None:
        _sql(db, "UPDATE casing_calculations SET created_at = NULL WHERE id = :i", i=record_id)
    assert _created(db, record_id) == (stamp if created_at == "keep" else None)


# ---- fingerprint contract ---------------------------------------------------------------------------------
def test_fingerprint_covers_engineering_content_not_labels(world):  # noqa: F811
    db, dev, casing_id, _case_id = world
    with db.session_scope() as session:
        row = session.get(CasingCalculationRecord, casing_id)
        first = ri.fingerprint("casing_calculations", row)
        row.label = "SYN relabelled"
        assert ri.fingerprint("casing_calculations", row) == first                 # a label is not identity
        snapshot = dict(row.input_snapshot_json)
        snapshot["yield_psi"] = 1.0
        row.input_snapshot_json = snapshot
        assert ri.fingerprint("casing_calculations", row) != first                 # engineering content is
        session.rollback()
    assert first.startswith("D87fp1:") and len(first) == len("D87fp1:") + 64
    assert ri.fingerprint("no_such_table", object()) is None
    assert set(ri.IDENTITY_COLUMNS) == set(ccc.ADAPTER_MATRIX)                     # every history table covered


def test_json_text_and_native_json_fingerprint_identically():
    class Row:
        def __init__(self, inputs):
            self.well_id, self.calculator, self.method, self.method_version = 1, "c", "m", "v"
            self.inputs, self.results = inputs, {"b": 2.0}

    assert ri.fingerprint("calculation_cases", Row({"a": 1.0, "z": [1, 2]})) == \
        ri.fingerprint("calculation_cases", Row('{"z": [1, 2], "a": 1.0}'))


# ---- archive marks ----------------------------------------------------------------------------------------
def test_equal_timestamp_replacement_does_not_inherit_an_archive_mark(world):  # noqa: F811
    db, dev, casing_id, _case_id = world
    entry = _entry(db, dev, "casing_calculations", casing_id)
    assert wb.archive(db, entry, "SYN: superseded")["identity"] == ri.CONTENT_PINNED
    _replace(db, dev, casing_id, created_at="keep")                                 # same id, same timestamp
    assert wb.state(db, _entry(db, dev, "casing_calculations", casing_id)) == wb.ACTIVE


def test_a_legacy_mark_without_fingerprint_keeps_the_timestamp_rule(world):  # noqa: F811
    """The pre-M365 weakness is still visible for old marks; it is reported TIMESTAMP_ONLY, not hidden."""
    db, dev, casing_id, _case_id = world
    with db.session_scope() as session:
        stamp = session.get(CasingCalculationRecord, casing_id).created_at
        session.add(CalculationArchiveMark(source_table="casing_calculations", source_id=casing_id,
                                           source_created_at=stamp, well_id=dev, action=wb.ARCHIVE,
                                           reason="SYN legacy mark"))
    _replace(db, dev, casing_id, created_at="keep")
    assert wb.state(db, _entry(db, dev, "casing_calculations", casing_id)) == wb.ARCHIVED   # legacy: inherited


def test_null_timestamp_source_is_archivable_and_its_mark_is_not_inherited(world):  # noqa: F811
    db, dev, casing_id, _case_id = world
    _sql(db, "UPDATE casing_calculations SET created_at = NULL WHERE id = :i", i=casing_id)
    entry = _entry(db, dev, "casing_calculations", casing_id)
    preview = wb.bulk_preview(db, [entry], wb.ARCHIVE)
    assert preview["rows"][0]["plan"] == wb.WILL and preview["rows"][0]["identity"] == ri.CONTENT_PINNED
    assert wb.bulk_apply(db, [entry], wb.ARCHIVE, "SYN: superseded")["counts"][wb.DONE] == 1
    assert wb.state(db, entry) == wb.ARCHIVED
    _replace(db, dev, casing_id, created_at=None)                                   # NULL and NULL
    fresh = _entry(db, dev, "casing_calculations", casing_id)
    assert wb.state(db, fresh) == wb.ACTIVE
    assert wb.bulk_preview(db, [fresh], wb.RESTORE)["rows"][0]["plan"] == wb.SKIP


def test_stated_residual_identical_content_and_identical_timestamp_is_indistinguishable(world):  # noqa: F811
    db, dev, casing_id, _case_id = world
    wb.archive(db, _entry(db, dev, "casing_calculations", casing_id), "SYN: superseded")
    _replace(db, dev, casing_id, inputs=INPUTS, created_at="keep")                  # byte-identical content
    assert wb.state(db, _entry(db, dev, "casing_calculations", casing_id)) == wb.ARCHIVED   # residual, by design


def test_bulk_restore_of_content_pinned_marks(world):  # noqa: F811
    db, dev, casing_id, _case_id = world
    second = _casing(db, dev, "SYN M365 b", OTHER)
    entries = [_entry(db, dev, "casing_calculations", i) for i in (casing_id, second)]
    assert wb.bulk_apply(db, entries, wb.ARCHIVE, "SYN: superseded")["counts"][wb.DONE] == 2
    back = wb.bulk_apply(db, entries, wb.RESTORE, "SYN: needed")
    assert back["counts"][wb.DONE] == 2 and all(wb.state(db, e) == wb.ACTIVE for e in entries)
    with db.session_scope() as session:
        prints = [m.source_fingerprint for m in session.query(CalculationArchiveMark).order_by(CalculationArchiveMark.id)]
    assert len(prints) == 4 and all(p and p.startswith("D87fp1:") for p in prints)


# ---- clone / lineage links --------------------------------------------------------------------------------
def test_equal_timestamp_replacement_is_source_replaced_for_a_clone(world):  # noqa: F811
    db, dev, casing_id, _case_id = world
    clone = wb.clone(db, _entry(db, dev, "casing_calculations", casing_id))
    assert ccc.clone_provenance(db, clone["id"])["identity_basis"] == ri.CONTENT_PINNED
    _replace(db, dev, casing_id, created_at="keep")                                 # predates the link
    prov = ccc.clone_provenance(db, clone["id"])
    assert prov["identity"] == ccc.SOURCE_REPLACED and "fingerprint" in prov["reason"]
    assert ccc.source_entry(db, prov) is None


def test_identical_content_created_after_the_link_is_still_source_replaced(world):  # noqa: F811
    db, dev, casing_id, _case_id = world
    clone = wb.clone(db, _entry(db, dev, "casing_calculations", casing_id))
    _sql(db, "DELETE FROM casing_calculations WHERE id = :i", i=casing_id)
    assert _casing(db, dev, "SYN identical", INPUTS) == casing_id
    _sql(db, "UPDATE casing_calculations SET created_at = '2099-01-01 00:00:00' WHERE id = :i", i=casing_id)
    prov = ccc.clone_provenance(db, clone["id"])
    assert prov["identity"] == ccc.SOURCE_REPLACED and "identical content" in prov["reason"]


def test_a_clone_of_a_null_timestamp_source_is_verified_by_content(world):  # noqa: F811
    db, dev, casing_id, _case_id = world
    _sql(db, "UPDATE casing_calculations SET created_at = NULL WHERE id = :i", i=casing_id)
    clone = wb.clone(db, _entry(db, dev, "casing_calculations", casing_id))
    assert ccc.clone_provenance(db, clone["id"])["identity"] == ccc.VERIFIED
    _replace(db, dev, casing_id, created_at=None)
    assert ccc.clone_provenance(db, clone["id"])["identity"] == ccc.SOURCE_REPLACED


def test_a_legacy_link_without_fingerprint_keeps_the_time_rule(world):  # noqa: F811
    db, dev, casing_id, _case_id = world
    clone = wb.clone(db, _entry(db, dev, "casing_calculations", casing_id))
    raw = sqlite3.connect(db.db_path) if hasattr(db, "db_path") else None
    if raw is None:
        pytest.skip("file path of the synthetic database is not exposed")
    try:                                                  # simulate a pre-M365 link: drop the guard, clear the pin
        raw.execute(f"DROP TRIGGER trg_calculation_source_link_immutable_v{sg.LINK_GUARD_VERSION}")
        raw.execute("UPDATE calculation_source_links SET source_fingerprint = NULL WHERE case_id = ?", (clone["id"],))
        raw.commit()
    finally:
        raw.close()
    prov = ccc.clone_provenance(db, clone["id"])
    assert (prov["identity"], prov["identity_basis"]) == (ccc.VERIFIED, ri.TIMESTAMP_ONLY)


# ---- storage guard, migration, authorization --------------------------------------------------------------
def test_the_fingerprint_of_a_mark_is_immutable(world):  # noqa: F811
    db, dev, casing_id, _case_id = world
    wb.archive(db, _entry(db, dev, "casing_calculations", casing_id), "SYN: superseded")
    with pytest.raises(Exception, match="immutable"):
        _sql(db, "UPDATE calculation_archive_marks SET source_fingerprint = 'forged'")
    names = {row[0] for row in _sql(db, "SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()}
    assert f"trg_calculation_archive_mark_immutable_v{sg.ARCHIVE_MARK_GUARD_VERSION}" in names
    assert "trg_calculation_archive_mark_immutable_v1" not in names
    assert f"trg_calculation_source_link_immutable_v{sg.LINK_GUARD_VERSION}" in names


def test_columns_are_additive_migrations():
    assert ("calculation_archive_marks", "source_fingerprint", "VARCHAR(80)") in ADDITIVE_COLUMNS
    assert ("calculation_source_links", "source_fingerprint", "VARCHAR(80)") in ADDITIVE_COLUMNS


def test_null_time_refusal_still_applies_without_a_fingerprint_contract(world, monkeypatch):  # noqa: F811
    """M304's refusal is replaced by content pinning ONLY where a contract exists; elsewhere it still refuses."""
    db, dev, casing_id, _case_id = world
    _sql(db, "UPDATE casing_calculations SET created_at = NULL WHERE id = :i", i=casing_id)
    entry = _entry(db, dev, "casing_calculations", casing_id)
    monkeypatch.delitem(ri.IDENTITY_COLUMNS, "casing_calculations")
    with pytest.raises(wb.WorkbenchError, match="no creation time"):
        wb.archive(db, entry, "SYN: cannot be pinned")
