"""M220: the tubular importer never imports hidden, ambiguous or unchecked content, and never rewrites its source.

Synthetic files generated in tmp_path: hidden rows / columns / sheets (XLSX and XLSM), repeated JSON keys, CSV values
without a header, formulas, an over-limit (zip-bomb) archive. The source file is byte-identical after preview and
import; a published set is never updated in place.
"""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook

from core.engineering import tubular_import as ti
from core.engineering import tubular_reference as tr
from tests.test_m181_m183_tubular_import import HEADER, ROWS, USER, _csv, _draft, _items, db  # noqa: F401


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _workbook(path: Path, *, hide_row=None, hide_col=None, hidden_sheet=False, extra=None) -> Path:
    wb = Workbook()
    ws = wb.active
    if hidden_sheet:
        ws.title = "visible"
        ws.append(["nothing here"])
        ws = wb.create_sheet("data")
        ws.sheet_state = "hidden"
    ws.append(HEADER)
    for row in ROWS + (extra or []):
        ws.append(row)
    if hide_row:
        ws.row_dimensions[hide_row].hidden = True
    if hide_col:
        ws.column_dimensions[hide_col].hidden = True
    wb.save(path)
    return path


HIDDEN = ["DP", "SYN-HIDDEN", "SYN-G1", "SYN-C1", 5.5, 4.0, 21.9, "", "", ""]


@pytest.mark.parametrize("suffix", [".xlsx", ".xlsm"])
def test_a_hidden_row_is_invalid_and_a_partial_import_leaves_it_out(db, tmp_path, suffix):  # noqa: F811
    path = _workbook(tmp_path / f"hidden_row{suffix}", hide_row=4, extra=[HIDDEN])
    before = _sha(path)
    set_id = _draft(db)
    preview = ti.preview_file(db, set_id, str(path), USER)
    status = {r.spec.designation: (r.status, r.issues) for r in preview.rows}
    assert status["SYN-HIDDEN"][0] == ti.INVALID and "hidden" in status["SYN-HIDDEN"][1][0]
    with pytest.raises(ti.TubularImportError, match="invalid"):
        ti.apply_import(db, preview, confirmed=True, reason="synthetic")
    ti.apply_import(db, preview, confirmed=True, reason="synthetic", accept_partial=True)
    assert sorted(i["spec"].designation for i in _items(db, set_id)) == ["SYN-DC-1", "SYN-DP-1"]
    assert _sha(path) == before                                 # the source is never rewritten


def test_a_hidden_mapped_column_a_hidden_header_row_and_a_hidden_sheet_block_the_file(db, tmp_path):  # noqa: F811
    set_id = _draft(db)
    for path, words in ((_workbook(tmp_path / "col.xlsx", hide_col="F"), "column 'ID (in)' is hidden"),
                        (_workbook(tmp_path / "head.xlsx", hide_row=1), "header row is hidden"),
                        (_workbook(tmp_path / "sheet.xlsx", hidden_sheet=True), "sheet 'data' is hidden")):
        preview = ti.preview_file(db, set_id, str(path), USER, sheet="data" if "sheet" in path.name else None)
        assert any(words in b for b in preview.blocking), preview.blocking
        with pytest.raises(ti.TubularImportError, match="blocked"):
            ti.apply_import(db, preview, confirmed=True, reason="synthetic", accept_partial=True)
    assert _items(db, set_id) == []


def test_a_hidden_unmapped_column_is_only_listed_as_ignored(db, tmp_path):  # noqa: F811
    path = _workbook(tmp_path / "remarks.xlsx", hide_col="J")      # "Remarks" is not an engineering field
    preview = ti.preview_file(db, _draft(db), str(path), USER)
    assert preview.blocking == [] and "Remarks" in " ".join(preview.ignored_columns)


def test_repeated_json_keys_and_invalid_json_are_refused(db, tmp_path):  # noqa: F811
    set_id = _draft(db)
    dup = tmp_path / "dup.json"
    dup.write_text('[{"component_type": "DP", "designation": "SYN-J", "nominal_od_in": 4.5, "nominal_od_in": 5.0}]')
    with pytest.raises(ti.TubularImportError, match="repeats the key"):
        ti.preview_file(db, set_id, str(dup), USER)
    bad = tmp_path / "bad.json"
    bad.write_text('[{"component_type": "DP",')
    with pytest.raises(ti.TubularImportError, match="Not a valid JSON"):
        ti.preview_file(db, set_id, str(bad), USER)


def test_a_csv_value_without_a_header_invalidates_its_row(db, tmp_path):  # noqa: F811
    path = tmp_path / "extra.csv"
    path.write_text("component_type,designation,nominal_od_in\nDP,SYN-X,4.5,9.99\nDP,SYN-Y,5.5\n")
    preview = ti.preview_file(db, _draft(db), str(path), USER)
    status = {r.spec.designation: r for r in preview.rows}
    assert status["SYN-X"].status == ti.INVALID and "without a header" in status["SYN-X"].issues[0]
    assert status["SYN-Y"].status == ti.NEW


def test_a_formula_cell_is_never_imported_as_its_cached_value(db, tmp_path):  # noqa: F811
    wb = Workbook()
    ws = wb.active
    ws.append(HEADER)
    ws.append(["DP", "SYN-F", "SYN-G1", "SYN-C1", "=4+0.5", 3.8, "", "", "", ""])
    path = tmp_path / "formula.xlsx"
    wb.save(path)
    preview = ti.preview_file(db, _draft(db), str(path), USER)
    assert preview.rows[0].status == ti.INVALID and "formula" in preview.rows[0].issues[0]


def test_an_over_limit_archive_is_refused_before_it_is_read(db, tmp_path):  # noqa: F811
    path = tmp_path / "bomb.xlsx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/padding.bin", b"0" * (520 * 1024 * 1024))
    set_id = _draft(db)
    with pytest.raises(ti.TubularImportError, match="uncompressed exceeds"):
        ti.preview_file(db, set_id, str(path), USER)
    junk = tmp_path / "junk.xlsx"
    junk.write_bytes(b"not a zip at all")
    with pytest.raises(ti.TubularImportError):
        ti.preview_file(db, set_id, str(junk), USER)


def test_a_published_set_is_never_updated_in_place(db, tmp_path):  # noqa: F811
    set_id = _draft(db)
    first = ti.preview_file(db, set_id, str(_csv(tmp_path / "a.csv")), USER)
    ti.apply_import(db, first, confirmed=True, reason="synthetic")
    tr.publish_set(db, set_id)
    more = _csv(tmp_path / "b.csv", rows=[["DP", "SYN-NEW", "SYN-G9", "SYN-C9", 5.0, 4.2, "", "", "", ""]])
    preview = ti.preview_file(db, set_id, str(more), USER)
    assert any("immutable" in b for b in preview.blocking)
    with pytest.raises(ti.TubularImportError):
        ti.apply_import(db, preview, confirmed=True, reason="synthetic")
    assert sorted(i["spec"].designation for i in _items(db, set_id)) == ["SYN-DC-1", "SYN-DP-1"]


def test_an_over_limit_used_range_is_refused_and_the_source_is_unchanged(db, tmp_path):  # noqa: F811
    # One far cell gives a used range of 500 001 rows x 10 columns, above the 5 000 000-cell limit of a sheet.
    path = _workbook(tmp_path / "wide.xlsx")
    from openpyxl import load_workbook
    workbook = load_workbook(path)
    workbook.active.cell(row=500_001, column=10, value="SYN far cell")
    workbook.save(path)
    before = _sha(path)
    set_id = _draft(db)
    with pytest.raises(ti.TubularImportError, match=r"cells\), above the limit of 5000000"):
        ti.preview_file(db, set_id, str(path), USER)
    assert _items(db, set_id) == [] and _sha(path) == before
