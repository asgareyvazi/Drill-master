"""Qt-free tests for the vendor-workbook drill-pipe importer.

These exercise the full vertical slice — a synthetic (clearly non-vendor,
labelled ACME/test) Excel workbook → canonical normalization → persisted
reference catalog — without constructing any Qt widget, per the project's
headless test contract. All engineering values here are invented test fixtures,
not real vendor data.
"""
from __future__ import annotations

import os
import tempfile

import pytest

pytest.importorskip("openpyxl")
from openpyxl import Workbook  # noqa: E402

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from core.database import Base, DatabaseManager  # noqa: E402
from core.engineering.drill_pipe_import import (  # noqa: E402
    DrillPipeImportError,
    import_workbook,
    parse_workbook,
)
from core.repositories.drill_pipe_reference_repository import (  # noqa: E402
    DrillPipeReferenceRepository,
)

HDR = ["Manufacturer", "Product", "OD (in)", "ID (in)",
       "Weight (ppf)", "Grade", "Connection"]


def _write(rows, sheet="Aa"):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for r in rows:
        ws.append(r)
    path = tempfile.mktemp(suffix=".xlsx")
    wb.save(path)
    return path


def _repo():
    m = DatabaseManager()
    m.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(m.engine)
    m.Session = sessionmaker(bind=m.engine, autoflush=False, autocommit=False)
    return DrillPipeReferenceRepository(m)


# --------------------------------------------------------------------------
# Parsing: robustness to messy vendor presentation
# --------------------------------------------------------------------------
def test_detects_header_below_title_and_blank_rows():
    path = _write([
        ["ACME Drill Pipe Data Sheet Rev C"],
        [],
        HDR,
        ["ACME", "5DP", "5.000", "4.276", "19.5", "S-135", "NC50"],
    ])
    try:
        pw = parse_workbook(path, sheet="Aa")
        assert pw.header_row == 3
        assert len(pw.specs) == 1
        assert pw.specs[0].nominal_od_in == 5.0
        assert pw.specs[0].nominal_weight_ppf == 19.5
    finally:
        os.remove(path)


def test_blank_interior_row_is_skipped_not_rejected():
    path = _write([
        HDR,
        ["ACME", "5DP", "5.0", "4.276", "19.5", "S-135", "NC50"],
        [],
        ["ACME", "5DP", "5.0", "4.0", "25.6", "S-135", "NC50"],
    ])
    try:
        pw = parse_workbook(path, sheet="Aa")
        assert len(pw.specs) == 2
        blanks = [r for r in pw.skipped if r.note == "blank row"]
        assert len(blanks) == 1
    finally:
        os.remove(path)


def test_provenance_records_source_sheet_and_row():
    path = _write([HDR, ["ACME", "5DP", "5.0", "4.276", "19.5", "S-135", "NC50"]])
    try:
        pw = parse_workbook(path, sheet="Aa", source_label="vendor.xlsx")
        prov = pw.specs[0].provenance
        assert "vendor.xlsx" in prov.source
        assert "[Aa]" in prov.source
        assert prov.notes == "row 2"
    finally:
        os.remove(path)


def test_unmapped_columns_preserved_in_extra():
    path = _write([
        HDR + ["Notes"],
        ["ACME", "5DP", "5.0", "4.276", "19.5", "S-135", "NC50", "premium"],
    ])
    try:
        pw = parse_workbook(path, sheet="Aa")
        assert pw.specs[0].extra.get("Notes") == "premium"
    finally:
        os.remove(path)


def test_missing_file_raises_structural_error():
    with pytest.raises(DrillPipeImportError):
        parse_workbook("/no/such/file.xlsx")


def test_no_header_row_raises_structural_error():
    path = _write([["random"], ["garbage", "text"]])
    try:
        with pytest.raises(DrillPipeImportError):
            parse_workbook(path, sheet="Aa")
    finally:
        os.remove(path)


def test_missing_sheet_raises():
    path = _write([HDR, ["ACME", "5DP", "5.0", "4.276", "19.5", "S-135", "NC50"]])
    try:
        with pytest.raises(DrillPipeImportError):
            parse_workbook(path, sheet="DoesNotExist")
    finally:
        os.remove(path)


# --------------------------------------------------------------------------
# Adversarial normalization (delegated to from_vendor_row, verified here)
# --------------------------------------------------------------------------
def test_conflicting_alias_columns_leave_field_none():
    path = _write([
        ["Manufacturer", "OD", "OD (in)", "Weight (ppf)"],
        ["ACME", "5.000", "5.125", "19.5"],
    ])
    try:
        pw = parse_workbook(path, sheet="Aa")
        row = pw.rows[0]
        assert row.spec.nominal_od_in is None
        kinds = {i.kind for i in row.spec.issues}
        assert "CONFLICTING_SOURCE" in kinds
        assert not row.spec.has_identity
    finally:
        os.remove(path)


def test_numeric_string_and_whitespace_normalize():
    path = _write([HDR, ["ACME", "5DP", " 5.000 ", "4.276", "19.5", "S-135", "NC50"]])
    try:
        pw = parse_workbook(path, sheet="Aa")
        assert pw.specs[0].nominal_od_in == 5.0
    finally:
        os.remove(path)


def test_invalid_and_identityless_rows_are_counted_invalid_on_import():
    path = _write([
        HDR,
        ["ACME", "5DP", "5.0", "4.276", "19.5", "S-135", "NC50"],  # valid
        ["Bad", None, "n/a", None, None, None, None],              # no identity
        ["ACME", "5DP", "-3", "4.0", "19.5", "S-135", "NC50"],     # invalid OD
    ])
    repo = _repo()
    try:
        res = import_workbook(repo, path, sheet="Aa")
        d = res.as_dict()
        assert d["inserted"] == 1
        assert d["invalid"] == 2
        assert repo.count() == 1
    finally:
        os.remove(path)


# --------------------------------------------------------------------------
# Full vertical slice: import → persist → outcomes
# --------------------------------------------------------------------------
def test_import_inserts_then_is_idempotent():
    path = _write([
        HDR,
        ["ACME", "5DP", "5.0", "4.276", "19.5", "S-135", "NC50"],
        ["Vallourec", "VAM", "5.875", "5.153", "23.4", "S-135", "5-1/2 FH"],
    ])
    repo = _repo()
    try:
        r1 = import_workbook(repo, path, sheet="Aa").as_dict()
        assert (r1["inserted"], r1["unchanged"]) == (2, 0)
        assert repo.count() == 2
        r2 = import_workbook(repo, path, sheet="Aa").as_dict()
        assert (r2["inserted"], r2["unchanged"]) == (0, 2)
        assert repo.count() == 2  # no duplicates on re-import
    finally:
        os.remove(path)


def test_enrichment_fills_missing_then_conflict_is_isolated():
    repo = _repo()
    base = _write([HDR, ["ACME", "5DP", "5.0", None, "19.5", "S-135", "NC50"]])
    enrich = _write([HDR, ["ACME", "5DP", "5.0", "4.276", "19.5", "S-135", "NC50"]])
    conflict = _write([HDR, ["ACME", "5DP", "5.0", "3.5", "19.5", "S-135", "NC50"]])
    try:
        assert import_workbook(repo, base, sheet="Aa").as_dict()["inserted"] == 1
        r2 = import_workbook(repo, enrich, sheet="Aa").as_dict()
        assert r2["enriched"] == 1
        fp = repo.all()[0].identity_fingerprint()
        assert repo.get_by_identity(fp).nominal_id_in == 4.276
        r3 = import_workbook(repo, conflict, sheet="Aa").as_dict()
        assert r3["conflicting"] == 1
        # conflicting import must NOT overwrite the trusted stored value
        assert repo.all()[0].nominal_id_in == 4.276
        assert repo.count() == 1
    finally:
        for p in (base, enrich, conflict):
            os.remove(p)


def test_one_bad_row_does_not_abort_the_batch():
    path = _write([
        HDR,
        ["ACME", "5DP", "5.0", "4.276", "19.5", "S-135", "NC50"],
        ["ACME", "5DP", "not-a-number", "4.0", "19.5", "S-135", "NC50"],
        ["Vallourec", "VAM", "5.875", "5.153", "23.4", "S-135", "5-1/2 FH"],
    ])
    repo = _repo()
    try:
        res = import_workbook(repo, path, sheet="Aa").as_dict()
        assert res["inserted"] == 2  # the two good rows survive
        assert res["invalid"] == 1
        assert repo.count() == 2
    finally:
        os.remove(path)
