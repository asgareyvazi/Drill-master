"""Qt-free tests for the persisted DrillPipe catalog presentation logic.

These cover browse-row construction, canonical search/filter and the
detail/provenance rendering without constructing any Qt widget, per the
project's headless test contract. Engineering values are synthetic test
fixtures (ACME/test), not real vendor data.
"""
from __future__ import annotations

from core.engineering.drill_pipe import DrillPipeSpec, Provenance, SpecIssue
from core.engineering.drill_pipe_catalog_view import (
    CATALOG_COLUMNS,
    build_catalog_rows,
    build_detail_fields,
    detail_text,
    filter_catalog_rows,
)


def _spec(**kw):
    base = dict(
        manufacturer="ACME", model="5DP", nominal_od_in=5.0,
        nominal_weight_ppf=19.5, grade="S-135", connection="NC50",
        nominal_id_in=4.276,
    )
    base.update(kw)
    return DrillPipeSpec(**base)


def test_build_rows_skips_specs_without_identity():
    good = _spec()
    no_od = _spec(nominal_od_in=None)
    no_wt = _spec(nominal_weight_ppf=None)
    rows = build_catalog_rows([good, no_od, no_wt])
    assert len(rows) == 1
    assert rows[0].cell("manufacturer") == "ACME"


def test_cells_cover_all_declared_columns():
    rows = build_catalog_rows([_spec(
        provenance=Provenance(source="vendor.xlsx [Aa]", status="verified"))])
    row = rows[0]
    for key, _ in CATALOG_COLUMNS:
        assert key in row.cells
    assert row.cell("source") == "vendor.xlsx [Aa]"
    assert row.cell("status") == "verified"
    assert row.cell("nominal_od_in") == "5"       # :g formatting
    assert row.cell("nominal_weight_ppf") == "19.5"


def test_filter_is_case_and_space_insensitive():
    rows = build_catalog_rows([
        _spec(manufacturer="ACME", connection="NC50"),
        _spec(manufacturer="Vallourec", model="VAM",
              nominal_weight_ppf=23.4, connection="5-1/2 FH"),
    ])
    assert len(filter_catalog_rows(rows, "")) == 2
    assert len(filter_catalog_rows(rows, "NC50")) == 1       # case-insensitive
    assert len(filter_catalog_rows(rows, "  nc50 ")) == 1    # surrounding space collapsed
    assert len(filter_catalog_rows(rows, "VALLOUREC")) == 1  # case-insensitive
    assert len(filter_catalog_rows(rows, "5-1/2  fh")) == 1  # repeated space collapsed
    assert len(filter_catalog_rows(rows, "s-135")) == 2      # shared grade
    assert len(filter_catalog_rows(rows, "nonexistent")) == 0


def test_filter_matches_fingerprint_fragment():
    rows = build_catalog_rows([_spec()])
    fp = rows[0].fingerprint
    assert len(filter_catalog_rows(rows, fp[2:10])) == 1


def test_detail_fields_expose_identity_engineering_and_provenance():
    spec = _spec(
        tool_joint_od_in=6.625, tensile_rating_klbf=530.0,
        provenance=Provenance(source="ACME.xlsx [Aa]", status="unverified",
                              notes="row 7"),
        extra={"Notes": "premium"},
    )
    fields = build_detail_fields(spec)
    groups = {f.group for f in fields}
    assert {"Identity", "Engineering", "Provenance"} <= groups
    labels = {f.label: f.value for f in fields}
    assert labels["Manufacturer"] == "ACME"
    assert labels["Nominal weight (ppf)"] == "19.5"
    assert labels["Source"] == "ACME.xlsx [Aa]"
    assert labels["Import note"] == "row 7"
    # identity fingerprint present, and NOT a bare DB id
    assert any(f.label == "Identity fingerprint" for f in fields)
    # unmapped vendor column preserved
    assert any(f.label == "Vendor column: Notes" and f.value == "premium"
               for f in fields)


def test_detail_fields_surface_issues():
    spec = _spec(nominal_id_in=None, issues=(
        SpecIssue("nominal_id_in", "CONFLICTING_SOURCE", "columns disagree"),
    ))
    fields = build_detail_fields(spec)
    assert any(f.group == "Issues" and "CONFLICTING_SOURCE" in f.label
               for f in fields)


def test_detail_text_is_grouped_and_readable():
    text = detail_text(_spec())
    assert "[Identity]" in text
    assert "[Engineering]" in text
    assert "[Provenance]" in text
    assert "Manufacturer: ACME" in text


def test_unknown_values_render_blank_not_none():
    row = build_catalog_rows([_spec(grade=None)])[0]
    assert row.cell("grade") == ""
