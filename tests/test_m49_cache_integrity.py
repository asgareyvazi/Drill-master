"""M49 - the Analysis cache revision sees every edit of an analysis input.

M48 fingerprinted the well with row counts, max ids, ``updated_at`` and value
sums. ``TimeLog24H`` has no ``updated_at``, so an edit of only an NPT code (or
only a currency code written without the ORM) changed none of those and the
page could keep serving the cached, stale view until a manual Refresh.

These tests write with plain SQL on purpose (no ORM ``onupdate`` hook runs),
the way an external tool or a bulk fix would.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import analysis_evidence as ev  # noqa: E402
from m48_synthetic import build  # noqa: E402


@pytest.fixture
def syn():
    db, ids = build()
    yield db, ids
    db.engine.dispose()


def _revision(db, well_id):
    s = db.create_session()
    try:
        return ev.data_revision(s, well_id)
    finally:
        s.close()


def _sql(db, statement, **params):
    s = db.create_session()
    try:
        s.execute(text(statement), params)
        s.commit()
    finally:
        s.close()


def test_revision_is_stable_without_changes(syn):
    db, ids = syn
    assert _revision(db, ids["A"]) == _revision(db, ids["A"])
    assert _revision(db, ids["A"])[0] == str(ev.DATA_REVISION_VERSION)


def test_currency_code_only_change_changes_the_revision(syn):
    db, ids = syn
    before = _revision(db, ids["A"])
    _sql(db, "UPDATE cost_records SET currency = 'GBP' WHERE well_id = :w AND currency = 'EUR'", w=ids["A"])
    assert _revision(db, ids["A"]) != before


def test_npt_code_only_change_changes_the_revision(syn):
    db, ids = syn
    before = _revision(db, ids["A"])
    _sql(db, "UPDATE time_logs_24h SET main_code = 'NPT-Q' WHERE main_code = 'NPT-X'")
    assert _revision(db, ids["A"]) != before


@pytest.mark.parametrize("statement", [
    "UPDATE time_logs_24h SET npt_category = 'Rig repair' WHERE main_code = 'NPT-X'",
    "UPDATE time_logs_24h SET sub_code = 'S1' WHERE main_code = 'NPT-X'",
    "UPDATE time_logs_24h SET is_npt = 0 WHERE main_code = 'NPT-X'",
    "UPDATE time_logs_24h SET status = 'reviewed' WHERE main_code = 'NPT-X'",
    "UPDATE cost_records SET category = 'Rig hire' WHERE currency = 'USD'",
    "UPDATE cost_records SET cost_type = 'CAPEX' WHERE currency = 'USD'",
])
def test_text_only_classification_edits_change_the_revision(syn, statement):
    db, ids = syn
    before = _revision(db, ids["A"])
    _sql(db, statement)
    assert _revision(db, ids["A"]) != before


def test_swapping_values_keeps_counts_ids_and_sums_but_changes_the_revision(syn):
    """Two rows exchange their durations: count, max id and SUM(duration) stay."""
    db, ids = syn
    s = db.create_session()
    try:
        rows = s.execute(text(
            "SELECT t.id, t.duration FROM time_logs_24h t JOIN daily_reports r ON r.id = t.report_id "
            "WHERE r.well_id = :w AND t.duration IS NOT NULL ORDER BY t.id"), {"w": ids["A"]}).fetchall()
    finally:
        s.close()
    (id1, d1), (id2, d2) = next((a, b) for a, b in zip(rows, rows[1:]) if a[1] != b[1])
    before = _revision(db, ids["A"])
    _sql(db, "UPDATE time_logs_24h SET duration = :d WHERE id = :i", d=d2, i=id1)
    _sql(db, "UPDATE time_logs_24h SET duration = :d WHERE id = :i", d=d1, i=id2)
    assert _revision(db, ids["A"]) != before


def test_delete_and_reinsert_with_the_same_id_and_sums_changes_the_revision(syn):
    """SQLite reuses the top rowid: a delete + insert can keep count, max id and sums."""
    db, ids = syn
    s = db.create_session()
    try:
        top = s.execute(text("SELECT id, well_id, category, actual_cost, planned_cost FROM cost_records "
                             "ORDER BY id DESC LIMIT 1")).fetchone()
    finally:
        s.close()
    well = top[1]
    before = _revision(db, well)
    _sql(db, "DELETE FROM cost_records WHERE id = :i", i=top[0])
    _sql(db, "INSERT INTO cost_records (id, well_id, category, actual_cost, planned_cost, currency) "
             "VALUES (:i, :w, :c, :a, :p, 'JPY')", i=top[0], w=well, c=top[2], a=top[3], p=top[4])
    assert _revision(db, well) != before


def test_another_wells_edit_does_not_change_this_wells_revision(syn):
    db, ids = syn
    before = _revision(db, ids["C"])
    _sql(db, "UPDATE time_logs_24h SET main_code = 'NPT-Q' WHERE main_code = 'NPT-X'")   # well A only
    _sql(db, "UPDATE cost_records SET currency = 'GBP' WHERE well_id = :w", w=ids["A"])
    assert _revision(db, ids["C"]) == before


@pytest.mark.parametrize("statement", [
    "UPDATE wells SET name = 'SYN-C2' WHERE id = :w",
    "UPDATE sections SET name = 'S2' WHERE well_id = :w",
    "UPDATE mud_reports SET mud_type = 'OBM' WHERE well_id = :w",
    "UPDATE safety_reports SET days_without_lti = 101 WHERE well_id = :w",
])
def test_every_table_the_page_reads_is_covered(syn, statement):
    db, ids = syn
    from datetime import date

    from core.database import MudReport, Section
    s = db.create_session()
    try:
        s.add(Section(well_id=ids["C"], name="S1"))
        s.add(MudReport(well_id=ids["C"], report_date=date(2026, 2, 1), mud_type="WBM"))
        s.commit()
    finally:
        s.close()
    before = _revision(db, ids["C"])
    _sql(db, statement, w=ids["C"])
    assert _revision(db, ids["C"]) != before
