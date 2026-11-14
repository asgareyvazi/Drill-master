"""M181-M183: controlled tubular reference import (``tubular-import-v1``) into DRAFT sets.

Every value below is SYNTHETIC (designations ``SYN-*``, deliberately non-catalogue numbers). The application
ships no pipe rows (M181: no permitted source was found). Fresh isolated databases; real Qt for the dialog.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.engineering import tubular_import as ti  # noqa: E402
from core.engineering import tubular_reference as tr  # noqa: E402

USER = tr.Provenance(origin="user", entered_by="synthetic-tester", notes="synthetic test file")
HEADER = ["Component type", "Designation", "Grade", "Connection", "Nominal OD (in)", "ID (in)", "nominal weight (lb/ft)",
          "Tensile (klbf)", "Page", "Remarks"]
ROWS = [["DP", "SYN-DP-1", "SYN-G1", "SYN-C1", 4.123, 3.111, 17.3, "", "7", "kept out"],
        ["Drill collar", "SYN-DC-1", "", "SYN-C2", "6.321", "2.222", "", 812.5, "", ""]]


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db(tmp_path):
    from core.database import DatabaseManager
    manager = DatabaseManager()
    manager.db_path = str(tmp_path / "tubular_import.db")
    manager.initialize()
    return manager


def _csv(path: Path, rows=ROWS, header=HEADER) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def _draft(db, name="SYN library"):
    return tr.create_set(db, name)["id"]


def _items(db, set_id=None):
    return tr.search(db, published_only=False, set_id=set_id)


def _audits(db, action="tubular_reference_import"):
    from core.database import AuditLog
    with db.session_scope() as session:
        return [(a.action, a.details) for a in session.query(AuditLog).filter_by(action=action)]


# ------------------------------------------------------------------------------------- happy path

def test_preview_then_confirmed_import_keeps_provenance_and_unknowns(db, tmp_path):
    set_id = _draft(db)
    path = _csv(tmp_path / "syn.csv")
    preview = ti.preview_file(db, set_id, str(path), USER)
    assert preview.blocking == [] and preview.counts()[ti.NEW] == 2 and preview.importable
    assert preview.ignored_columns == ["Remarks"]                      # listed, never read
    assert preview.columns["Nominal OD (in)"] == "nominal_od_in" and preview.columns["Page"] == "page"
    assert _items(db) == [] and _audits(db) == []                      # preview writes nothing
    result = ti.apply_import(db, preview, confirmed=True, reason="synthetic acceptance")
    assert result["imported"] == 2 and result["sha256"] == ti.file_sha256(str(path))
    rows = {r["spec"].designation: r["spec"] for r in _items(db, set_id)}
    dp, dc = rows["SYN-DP-1"], rows["SYN-DC-1"]
    assert dp.nominal_od_in == 4.123 and dp.id_in == 3.111 and dp.weight_ppf == 17.3
    assert dp.tensile_klbf is None and dp.display_value("tensile_klbf") == tr.UNAVAILABLE   # blank is not 0
    assert dc.component_type == "DC" and dc.grade is None and dc.weight_ppf is None and dc.tensile_klbf == 812.5
    assert dp.provenance.file_fingerprint == result["sha256"] and dp.provenance.page == "7"
    assert "source row 2" in dp.provenance.notes and "source row 3" in dc.provenance.notes
    assert dp.provenance.origin == "user" and dp.wall_in is None                       # nothing derived
    audit = _audits(db)
    assert len(audit) == 1 and json.loads(audit[0][1])["imported"] == 2
    assert json.loads(audit[0][1])["reason"] == "synthetic acceptance"
    assert str(tmp_path) not in json.dumps([r["spec"].to_payload() for r in _items(db)])   # the raw file is not kept


def test_json_list_and_items_object_are_read(db, tmp_path):
    set_id = _draft(db)
    data = [{"component_type": "HWDP", "designation": "SYN-HW-1", "nominal_od_in": 4.77, "id_in": 2.51},
            {"component_type": "TUBING", "designation": "SYN-TB-1", "nominal_od_in": 2.91, "extra": "x"}]
    plain = tmp_path / "a.json"
    plain.write_text(json.dumps(data), encoding="utf-8")
    wrapped = tmp_path / "b.json"
    wrapped.write_text(json.dumps({"items": data, "provenance": {"licence": "ignored"}}), encoding="utf-8")
    assert ti.preview_file(db, set_id, str(plain), USER).counts()[ti.NEW] == 2
    preview = ti.preview_file(db, set_id, str(wrapped), USER)
    assert preview.counts()[ti.NEW] == 2 and "extra" in preview.ignored_columns
    assert any("provenance" in note for note in preview.ignored_columns)
    bad = tmp_path / "c.json"
    bad.write_text(json.dumps([1, 2]), encoding="utf-8")
    with pytest.raises(ti.TubularImportError, match="list of objects"):
        ti.preview_file(db, set_id, str(bad), USER)


def test_xlsx_needs_a_sheet_choice_and_refuses_formula_cells(db, tmp_path):
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Pipes"
    sheet.append(["Component type", "Designation", "Nominal OD (in)", "ID (in)"])
    sheet.append(["DP", "SYN-X-1", 3.71, 2.93])
    sheet.append(["DP", "SYN-X-2", "=C2*2", 2.93])
    workbook.create_sheet("Notes")
    path = tmp_path / "syn.xlsx"
    workbook.save(path)
    set_id = _draft(db)
    with pytest.raises(ti.TubularImportError, match="2 sheets"):
        ti.preview_file(db, set_id, str(path), USER)
    preview = ti.preview_file(db, set_id, str(path), USER, sheet="Pipes")
    states = {r.spec.designation: r for r in preview.rows}
    assert states["SYN-X-1"].status == ti.NEW
    assert states["SYN-X-2"].status == ti.INVALID and "formula" in states["SYN-X-2"].issues[0]
    with pytest.raises(ti.TubularImportError, match="not in the workbook"):
        ti.preview_file(db, set_id, str(path), USER, sheet="Missing")


# ----------------------------------------------------------------------------------- refusals

@pytest.mark.parametrize("header,needle", [
    (["Component type", "Designation", "Nominal OD"], "canonical unit"),
    (["Component type", "Designation", "Nominal OD (mm)"], "canonical unit"),
    (["Component type", "Designation", "nominal_od_in", "Nominal OD (in)"], "already provides"),
    (["Designation", "Nominal OD (in)"], "no component_type column"),
    (["Component type", "Nominal OD (in)"], "no designation column"),
])
def test_headers_without_the_canonical_unit_or_with_gaps_block_the_whole_file(db, tmp_path, header, needle):
    set_id = _draft(db)
    path = _csv(tmp_path / "h.csv", rows=[["DP", "SYN-1", 3.3, 3.3][:len(header)]], header=header)
    preview = ti.preview_file(db, set_id, str(path), USER)
    assert any(needle in b for b in preview.blocking) and not preview.importable
    with pytest.raises(ti.TubularImportError, match="blocked"):
        ti.apply_import(db, preview, confirmed=True, reason="x")
    assert _items(db) == [] and _audits(db) == []


@pytest.mark.parametrize("cell,needle", [
    ("5-1/2", "not a plain number"), ("nan", "not finite"), ("inf", "not finite"), ("-inf", "not finite"),
    ("0", "positive"), ("-3.2", "positive"), ("=A1", "formula"),
])
def test_bad_cells_make_the_row_invalid_never_zero_or_guessed(db, tmp_path, cell, needle):
    set_id = _draft(db)
    path = _csv(tmp_path / "c.csv", rows=[["DP", "SYN-BAD", "", "", cell, "", "", "", "", ""], ROWS[1]])
    preview = ti.preview_file(db, set_id, str(path), USER)
    bad = next(r for r in preview.rows if r.spec.designation == "SYN-BAD")
    assert bad.status == ti.INVALID and any(needle in i for i in bad.issues)


def test_booleans_and_unknown_component_types_are_invalid(db, tmp_path):
    set_id = _draft(db)
    path = tmp_path / "b.json"
    path.write_text(json.dumps([{"component_type": "DP", "designation": "SYN-B", "nominal_od_in": True},
                                {"component_type": "Riser", "designation": "SYN-R", "nominal_od_in": 9.9},
                                {"component_type": "DP", "designation": "", "nominal_od_in": 3.9}]), encoding="utf-8")
    rows = ti.preview_file(db, set_id, str(path), USER).rows
    assert [r.status for r in rows] == [ti.INVALID] * 3
    assert "boolean" in rows[0].issues[0] and "Riser" in rows[1].issues[0] and "designation" in rows[2].issues[0]


def test_invalid_or_conflicting_rows_block_unless_a_partial_import_is_accepted(db, tmp_path):
    set_id = _draft(db)
    path = _csv(tmp_path / "p.csv", rows=[ROWS[0], ["DP", "SYN-BAD", "", "", "abc", "", "", "", "", ""]])
    preview = ti.preview_file(db, set_id, str(path), USER)
    with pytest.raises(ti.TubularImportError, match="partial"):
        ti.apply_import(db, preview, confirmed=True, reason="x")
    assert _items(db) == []
    result = ti.apply_import(db, preview, confirmed=True, reason="x", accept_partial=True)
    assert result["imported"] == 1 and result["skipped"][ti.INVALID] == 1
    assert [r["spec"].designation for r in _items(db)] == ["SYN-DP-1"]


def test_duplicates_conflicts_and_already_present_rows_are_never_overwritten(db, tmp_path):
    set_id = _draft(db)
    changed = list(ROWS[0])
    changed[5] = 3.05                                            # same identity, different ID
    rows = [ROWS[0], list(ROWS[0][:8]) + ["9", ""], changed, ROWS[1], ROWS[1]]
    preview = ti.preview_file(db, set_id, str(_csv(tmp_path / "d.csv", rows=rows)), USER)
    assert [r.status for r in preview.rows] == [ti.CONFLICT, ti.DUPLICATE_IN_FILE, ti.CONFLICT, ti.NEW,
                                                ti.DUPLICATE_IN_FILE]
    assert "identical to row 2" in preview.rows[1].issues[0]
    ti.apply_import(db, preview, confirmed=True, reason="x", accept_partial=True)
    assert [r["spec"].designation for r in _items(db)] == ["SYN-DC-1"]
    again = ti.preview_file(db, set_id, str(_csv(tmp_path / "e.csv", rows=[ROWS[1]])), USER)
    assert [r.status for r in again.rows] == [ti.ALREADY_PRESENT] and not again.importable
    other = list(ROWS[1])
    other[5] = "2.444"
    clash = ti.preview_file(db, set_id, str(_csv(tmp_path / "f.csv", rows=[other])), USER)
    assert clash.rows[0].status == ti.CONFLICT and "never overwritten" in clash.rows[0].issues[0]
    with pytest.raises(ti.TubularImportError):
        ti.apply_import(db, again, confirmed=True, reason="x")
    assert len(_items(db)) == 1


@pytest.mark.parametrize("prov,needle", [
    (tr.Provenance(origin="manufacturer", manufacturer="SYN Mill", document="SYN-DS-1"), "licence"),
    (tr.Provenance(origin="manufacturer", document="SYN-DS-1", licence="SYN licence"), "manufacturer"),
    (tr.Provenance(origin="derived", derived_from="x"), "cannot be imported"),
    (tr.Provenance(origin="manufacturer", manufacturer="SYN", document="API Spec 5DP Table 4", licence="CC0"),
     "owner-gated"),
    (tr.Provenance(origin="user", document="copied from API 5CT"), "owner-gated"),
    (tr.Provenance(origin="user", notes="values from API RP 7G"), "owner-gated"),
    (tr.Provenance(origin="user", url="https://example.invalid/iso-11960.pdf", notes="ISO 11960"), "owner-gated"),
    (tr.Provenance(origin="user", url="https://example.invalid/ISO-11961.pdf"), "owner-gated"),
    (tr.Provenance(origin="user", document="API-5C3 tables"), "owner-gated"),
])
def test_provenance_rules_and_standards_tables_block_the_file(db, tmp_path, prov, needle):
    set_id = _draft(db)
    preview = ti.preview_file(db, set_id, str(_csv(tmp_path / "s.csv")), prov)
    assert any(needle in b for b in preview.blocking) and not preview.importable


def test_unrelated_standard_numbers_do_not_block_the_file(db, tmp_path):
    set_id = _draft(db)
    prov = tr.Provenance(origin="user", notes="mill is ISO 9001 certified; SYN 5DP-like naming")
    assert ti.preview_file(db, set_id, str(_csv(tmp_path / "u.csv")), prov).blocking == []


def test_manufacturer_file_with_document_and_licence_is_accepted(db, tmp_path):
    prov = tr.Provenance(origin="manufacturer", manufacturer="SYN Mill", document="SYN datasheet",
                         revision="r3", licence="SYN written permission #1")
    set_id = _draft(db)
    preview = ti.preview_file(db, set_id, str(_csv(tmp_path / "m.csv")), prov)
    assert preview.blocking == []
    ti.apply_import(db, preview, confirmed=True, reason="licensed")
    spec = _items(db)[0]["spec"]
    assert spec.provenance.licence == "SYN written permission #1" and spec.provenance.revision == "r3"


def test_confirmation_reason_file_identity_and_set_state_are_rechecked(db, tmp_path):
    set_id = _draft(db)
    path = _csv(tmp_path / "r.csv")
    preview = ti.preview_file(db, set_id, str(path), USER)
    with pytest.raises(ti.TubularImportError, match="not confirmed"):
        ti.apply_import(db, preview, confirmed=False, reason="x")
    with pytest.raises(ti.TubularImportError, match="reason"):
        ti.apply_import(db, preview, confirmed=True, reason="  ")
    path.write_text(path.read_text(encoding="utf-8") + "DP,SYN-LATE,,,3.4,,,,,\n", encoding="utf-8")
    with pytest.raises(ti.TubularImportError, match="changed after the preview"):
        ti.apply_import(db, preview, confirmed=True, reason="x")
    preview = ti.preview_file(db, set_id, str(path), USER)
    tr.add_item(db, set_id, preview.rows[0].spec)                # someone adds the same item meanwhile
    with pytest.raises(ti.TubularImportError, match="set changed"):
        ti.apply_import(db, preview, confirmed=True, reason="x")
    assert len(_items(db)) == 1 and _audits(db) == []
    preview = ti.preview_file(db, set_id, str(path), USER)
    tr.publish_set(db, set_id)
    with pytest.raises(ti.TubularImportError, match="no longer a draft"):
        ti.apply_import(db, preview, confirmed=True, reason="x")
    assert len(_items(db)) == 1
    blocked = ti.preview_file(db, set_id, str(path), USER)
    assert any("immutable" in b for b in blocked.blocking)


def test_a_failing_audit_rolls_the_whole_import_back(db, tmp_path, monkeypatch):
    set_id = _draft(db)
    preview = ti.preview_file(db, set_id, str(_csv(tmp_path / "a.csv")), USER)

    def boom(*_a, **_k):
        raise RuntimeError("audit store unavailable")
    monkeypatch.setattr(db, "_add_mandatory_audit", boom)
    with pytest.raises(RuntimeError):
        ti.apply_import(db, preview, confirmed=True, reason="x")
    assert _items(db) == []


def test_unsupported_large_and_empty_files_are_refused(db, tmp_path, monkeypatch):
    set_id = _draft(db)
    other = tmp_path / "x.txt"
    other.write_text("a", encoding="utf-8")
    with pytest.raises(ti.TubularImportError, match="not supported"):
        ti.preview_file(db, set_id, str(other), USER)
    monkeypatch.setattr(ti, "MAX_ROWS", 1)
    with pytest.raises(ti.TubularImportError, match="limit"):
        ti.preview_file(db, set_id, str(_csv(tmp_path / "big.csv")), USER)
    monkeypatch.setattr(ti, "MAX_FILE_BYTES", 10)
    with pytest.raises(ti.TubularImportError, match="bytes"):
        ti.preview_file(db, set_id, str(_csv(tmp_path / "big2.csv")), USER)
    monkeypatch.setattr(ti, "MAX_FILE_BYTES", 1 << 20)
    empty = ti.preview_file(db, set_id, str(_csv(tmp_path / "e.csv", rows=[])), USER)
    assert "no data rows" in " ".join(empty.blocking)
    with pytest.raises(ti.TubularImportError, match="does not exist"):
        ti.preview_file(db, 999, str(_csv(tmp_path / "n.csv")), USER)


def test_the_documented_row_limit_refuses_a_5001_row_file_before_reading_its_values(db, tmp_path):
    set_id = _draft(db)
    big = tmp_path / "rows.csv"
    big.write_text("component_type,designation\n" + "".join(f"DP,SYN-{n}\n" for n in range(5001)), encoding="utf-8")
    with pytest.raises(ti.TubularImportError, match="5001 rows; the limit is 5000"):
        ti.preview_file(db, set_id, str(big), USER)


def test_no_pipe_rows_are_shipped_and_the_template_has_headers_only(db):
    assert tr.list_sets(db) == []                                          # M183: empty library by default
    template = Path(__file__).resolve().parents[1] / "docs" / "engineering" / "tubular_import_template.csv"
    lines = [row for row in csv.reader(template.open(encoding="utf-8")) if row]
    assert len(lines) == 1
    _by_index, _shown, ignored, blocking = ti.map_columns(lines[0])
    assert blocking == [] and ignored == []


# --------------------------------------------------------------------------------- real Qt dialog

def test_dialog_creates_previews_imports_publishes_and_the_search_cites_it(db, qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from dialogs.tubular_import_dialog import TubularImportDialog
    from dialogs.tubular_reference_dialog import TubularReferenceDialog

    warnings_shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings_shown.append(a[2]))
    source = _csv(tmp_path / "ui.csv")
    before = source.read_bytes()
    dialog = TubularImportDialog(db)
    try:
        assert dialog.set_combo.count() == 0 and "No draft set" in dialog.status.text()
        assert dialog.confirm_import() is None and "NOT IMPORTED" in warnings_shown[-1]
        assert dialog.create_draft("SYN UI library")["version"] == 1
        dialog.path_edit.setText(str(source))
        preview = dialog.run_preview()
        assert preview.counts()[ti.NEW] == 2 and dialog.import_btn.isEnabled() and dialog.table.rowCount() == 2
        dialog.notes_edit.setText("changed")                                 # any input change voids the preview
        assert dialog.preview is None and not dialog.import_btn.isEnabled()
        dialog.run_preview()
        assert dialog.confirm_import() is None and "reason" in warnings_shown[-1]    # reason required
        assert _items(db) == []
        dialog.reason_edit.setText("synthetic UI journey")
        result = dialog.confirm_import()
        assert result["imported"] == 2 and "Imported 2 row(s)" in dialog.status.text()
        assert dialog.publish_current()["version"] == 1 and "immutable" in dialog.status.text()
        assert dialog.set_combo.count() == 0
        assert dialog.publish_current() is None and "NOT PUBLISHED" in warnings_shown[-1]
    finally:
        dialog.deleteLater()
    assert source.read_bytes() == before                                     # the source file is untouched
    search = TubularReferenceDialog(db)
    try:
        assert search.table.rowCount() == 2
        search.table.selectRow(0)
        search._use_selected()
        snapshot = search.selected_snapshot
        assert snapshot["set_name"] == "SYN UI library" and tr.verify_snapshot(snapshot) == []
        assert snapshot["spec"]["provenance"]["file_fingerprint"] == ti.file_sha256(str(source))
    finally:
        search.deleteLater()


def test_dialog_reports_blocked_previews_without_writing(db, qapp, tmp_path):
    from dialogs.tubular_import_dialog import TubularImportDialog

    dialog = TubularImportDialog(db)
    try:
        dialog.create_draft("SYN blocked")
        dialog.path_edit.setText(str(_csv(tmp_path / "b.csv", header=["Component type", "Designation", "OD (in)",
                                                                         "Nominal OD (mm)"])))
        preview = dialog.run_preview()
        assert preview.blocking and "BLOCKED" in dialog.summary.text() and not dialog.import_btn.isEnabled()
        dialog.path_edit.setText(str(tmp_path / "missing.csv"))
        assert dialog.run_preview() is None and "NOT PREVIEWED" in dialog.summary.text()
    finally:
        dialog.deleteLater()
    assert _items(db) == []
