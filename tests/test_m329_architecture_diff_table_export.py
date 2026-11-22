"""M329: architecture revision diff — duplicate identities, table rows, CSV / XLSX export (SYNTHETIC)."""
from __future__ import annotations

import csv

import pytest

from core import architecture_diff as ad
from core import well_architecture as wa
from test_m311_architecture_diff import _with, world  # noqa: F401  (fixture)
from test_m74_well_architecture import ARCH

F_A = {"kind": "formation", "name": "SYN F9", "top_md": 2000, "bottom_md": 2050}
F_B = {"kind": "formation", "name": "SYN F9", "top_md": 2100, "bottom_md": 2150}


def _named(result, name="SYN F9"):
    return [r for r in result["rows"] if r["name"] == name]


def test_reordered_duplicates_are_unchanged_not_two_spurious_changes():
    result = ad.compare_components(ARCH + [dict(F_A), dict(F_B)], ARCH + [dict(F_B), dict(F_A)])
    assert result["identical"]
    assert all(r["status"] == ad.UNCHANGED and not r["ambiguous"] for r in _named(result))
    assert any("no ambiguity left" in n for n in result["notes"])


def test_identical_duplicate_is_paired_first_and_only_the_remainder_is_ambiguous():
    edited = {**F_B, "bottom_md": 2160}
    result = ad.compare_components(ARCH + [dict(F_A), dict(F_B)], ARCH + [edited, dict(F_A)])
    rows = _named(result)
    unchanged = [r for r in rows if r["status"] == ad.UNCHANGED]
    changed = [r for r in rows if r["status"] == ad.CHANGED]
    assert len(unchanged) == 1 and not unchanged[0]["ambiguous"]
    assert unchanged[0]["occurrence_old"] == 1 and unchanged[0]["occurrence_new"] == 2
    assert len(changed) == 1 and changed[0]["ambiguous"]
    assert changed[0]["changes"] == [{"field": "bottom_md", "old": 2150.0, "new": 2160.0}]
    assert any("1 matched in stored order (ambiguous)" in n for n in result["notes"])


def test_extra_duplicate_is_added_and_ambiguous_single_identities_are_not_flagged():
    result = ad.compare_components(ARCH + [dict(F_A)], ARCH + [dict(F_A), dict(F_B)])
    rows = _named(result)
    assert [r["status"] for r in rows] == [ad.UNCHANGED, ad.ADDED]
    assert rows[1]["ambiguous"] and rows[1]["occurrence_new"] == 2 and rows[1]["occurrence_old"] is None
    assert not any(r["ambiguous"] for r in result["rows"] if r["name"] != "SYN F9")


def test_table_rows_one_per_changed_field_and_unchanged_on_request():
    newer = _with({("casing", "9-5/8 csg"): {"bottom_md": 1010, "id_in": None},
                   ("accessory", "SYN float collar"): None})
    result = ad.compare_components(ARCH, newer)
    rows = ad.table_rows(result)
    casing = [r for r in rows if r[1] == "casing"]
    assert {r[4] for r in casing} == {"bottom_md", "id_in"}
    assert ("id_in", 8.681, None) in {(r[4], r[5], r[6]) for r in casing}
    assert any(r[0] == ad.REMOVED and r[2] == "SYN float collar" and r[4] == "" for r in rows)
    assert not any(r[0] == ad.UNCHANGED for r in rows)
    everything = ad.table_rows(result, include_unchanged=True)
    assert sum(1 for r in everything if r[0] == ad.UNCHANGED) == result["counts"][ad.UNCHANGED]


def _compared(db, ids):
    first = wa.save_revision(db, ids["dev"], ARCH)
    second = wa.save_revision(db, ids["dev"], _with({("tubing", "Tubing"): {"bottom_md": 1910, "id_in": None},
                                                     ("formation", "SYN F1"): {"name": "=HYPERLINK(1)"}}))
    return first, second, ad.compare_revisions(db, first["id"], second["id"])


def test_csv_export_carries_both_shas_unknown_as_empty_and_neutralises_formulas(world, tmp_path):  # noqa: F811
    db, ids = world
    first, second, result = _compared(db, ids)
    path = ad.export(result, tmp_path / "diff.csv")
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    meta = {r[0]: r[1] for r in rows if len(r) == 2}
    assert meta["older components SHA-256"] == first["components_sha256"]
    assert meta["newer components SHA-256"] == second["components_sha256"]
    assert meta["method"] == ad.DIFF_VERSION and meta["older revision"] == "1" and meta["newer revision"] == "2"
    header = rows.index(list(ad.TABLE_COLUMNS))
    body = rows[header + 1:]
    assert ["CHANGED", "tubing", "Tubing", "", "id_in", "2.992", "", ""] in body      # unknown → empty, not 0
    assert any(r[2] == "'=HYPERLINK(1)" for r in body)
    assert not any(c.startswith("=") for r in rows for c in r)


def test_xlsx_export_matches_the_table(world, tmp_path):  # noqa: F811
    from openpyxl import load_workbook

    db, ids = world
    _first, second, result = _compared(db, ids)
    path = ad.export(result, tmp_path / "diff.xlsx", include_unchanged=True)
    values = [tuple(c for c in row) for row in load_workbook(path).active.iter_rows(values_only=True)]
    header = values.index(tuple(ad.TABLE_COLUMNS))
    assert len(values) - header - 1 == len(ad.table_rows(result, include_unchanged=True))
    assert ("newer components SHA-256", second["components_sha256"]) in [v[:2] for v in values[:header]]
    assert ("CHANGED", "tubing", "Tubing", None, "bottom_md", 1900, 1910, None) in values


def test_export_refuses_other_formats(world, tmp_path):  # noqa: F811
    db, ids = world
    _first, _second, result = _compared(db, ids)
    with pytest.raises(ad.ArchitectureDiffError, match="csv or .xlsx"):
        ad.export(result, tmp_path / "diff.pdf")


def test_panel_shows_the_diff_table_exports_and_clears_on_refresh(world, tmp_path):  # noqa: F811
    from PySide6 import QtWidgets

    from tabs.w3b_wellbore_schematic_tab import WellboreSchematicTab

    db, ids = world
    _compared(db, ids)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tab = WellboreSchematicTab(db)
    try:
        tab.current_well_id = ids["dev"]
        panel = tab.architecture_panel
        panel.refresh()
        assert panel.export_comparison(str(tmp_path / "none.csv")) is None    # nothing compared yet
        assert panel.diff_table.isHidden()
        panel.table.selectRow(0)
        panel.compare_btn.click()
        assert not panel.diff_table.isHidden() and not panel.diff_controls.isHidden()
        shown = {(panel.diff_table.item(i, 4).text(), panel.diff_table.item(i, 5).text(),
                  panel.diff_table.item(i, 6).text()) for i in range(panel.diff_table.rowCount())}
        assert ("id_in", "2.992", "unknown") in shown and ("bottom_md", "1900", "1910") in shown
        changed_rows = panel.diff_table.rowCount()
        panel.diff_unchanged_check.setChecked(True)
        assert panel.diff_table.rowCount() > changed_rows
        written = panel.export_comparison(str(tmp_path / "panel.csv"))
        assert written and "SHA-256" in open(written, encoding="utf-8-sig").read()
        panel.refresh()
        assert panel.last_comparison is None and panel.diff_table.isHidden()
    finally:
        tab.deleteLater()
        app.processEvents()


def test_zero_to_unknown_is_a_change_not_equal_to_zero():
    newer = _with({("casing", "9-5/8 csg"): {"top_md": None}})
    result = ad.compare_components(ARCH, newer)
    casing = next(r for r in result["rows"] if r["kind"] == "casing")
    assert casing["status"] == ad.CHANGED
    assert casing["changes"] == [{"field": "top_md", "old": 0.0, "new": None}]
    assert "top_md 0 → unknown" in " ".join(ad.summary_lines(result))


def _bound(item_fingerprint, version):
    from core.engineering import reference_binding as rb

    return {"contract": rb.CONTRACT_VERSION, "fields": {"od_in": "od_in"}, "unavailable": [],
            "snapshot": {"set_name": "SYN casing set", "set_version": version, "item_fingerprint": item_fingerprint,
                         "spec": {"od_in": 9.625}}}


def test_library_binding_change_names_both_cited_items_d90():
    older = _with({("casing", "9-5/8 csg"): {"tubular_reference": _bound("a" * 64, 1)}})
    newer = _with({("casing", "9-5/8 csg"): {"tubular_reference": _bound("b" * 64, 2)}})
    result = ad.compare_components(older, newer)
    casing = next(r for r in result["rows"] if r["kind"] == "casing")
    assert casing["status"] == ad.CHANGED
    assert casing["changes"] == [{"field": "library binding", "old": "SYN casing set v1 item aaaaaaaaaaaa",
                                  "new": "SYN casing set v2 item bbbbbbbbbbbb"}]
    unbound = ad.compare_components(older, ARCH)
    change = next(r for r in unbound["rows"] if r["kind"] == "casing")["changes"]
    assert change == [{"field": "library binding", "old": "SYN casing set v1 item aaaaaaaaaaaa", "new": None}]
    assert "library binding SYN casing set v1 item aaaaaaaaaaaa → unknown" in " ".join(ad.summary_lines(unbound))
