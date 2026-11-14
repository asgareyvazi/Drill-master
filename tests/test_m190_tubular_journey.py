"""M190: 20-step tubular reference journey through the real main window and a real file database.

Real MainWindow (the M70 window fixture: real file database, real authorization, admin session), the real
import dialog on a SYNTHETIC CSV (its SHA-256 is checked at the end), the real search dialog, the real drill-string
component dialog, the real W13 Weight and Casing Strength pages, case save / reopen and drift. No pipe data ships;
every value below is a synthetic number chosen not to match any catalogue.
"""
from __future__ import annotations

import csv
import hashlib
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_m70_selection_audit import _pump, window  # noqa: E402,F401

HEADER = ["Component type", "Designation", "Grade", "Connection", "Nominal OD (in)", "ID (in)",
          "Nominal weight (lb/ft)", "Tool joint OD (in)", "Page"]
ROWS = [["DP", "SYN-J-DP", "SYN-G", "SYN-C", "4.871", "4.013", "18.7", "6.37", "3"],
        ["DP", "SYN-J-NOID", "", "", "3.911", "", "12.9", "", "3"],
        ["CASING", "SYN-J-CSG", "SYN-80", "", "9.611", "8.703", "46.1", "", "4"],
        ["DP", "SYN-J-FORMULA", "", "", "=5+0.5", "4.1", "", "", "5"]]


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _tab(win, name):
    return next(win.tab_widget.widget(i) for i in range(win.tab_widget.count())
                if type(win.tab_widget.widget(i)).__name__ == name)


def _pick(db, win, component_type, designation):
    from dialogs.tubular_reference_dialog import TubularReferenceDialog

    picker = TubularReferenceDialog(db, win, component_type=component_type)
    try:
        picker.text_edit.setText(designation)
        assert picker.table.rowCount() == 1, picker.status.text()
        picker.table.selectRow(0)
        picker._use_selected()
        return picker.selected_snapshot
    finally:
        picker.deleteLater()


def test_m190_twenty_step_tubular_journey(window, tmp_path, monkeypatch):  # noqa: F811
    from PySide6.QtWidgets import QMessageBox
    for name, answer in (("information", QMessageBox.Ok), ("warning", QMessageBox.Ok),
                         ("critical", QMessageBox.Ok), ("question", QMessageBox.No)):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, _answer=answer, **k: _answer))
    from core import calculation_cases as cc
    from core import calculation_history as ch
    from core.database import AuditLog
    from core.engineering import reference_binding as rb
    from core.engineering import tubular_reference as tr
    from core.selection_manager import SelectionManager
    from dialogs.engineering_dialogs import AddPipeDialog
    from dialogs.tubular_import_dialog import TubularImportDialog
    from dialogs.tubular_reference_dialog import TubularReferenceDialog

    win, db, ids = window
    well = ids["alpha"]

    # 1. The real window offers the library; it starts empty (no shipped pipe data) and offers the importer.
    actions = [a.text() for m in win.menuBar().findChildren(type(win.menuBar().actions()[0].menu()))
               for a in m.actions()]
    assert any("Tubular Reference Library" in t for t in actions)
    browser = TubularReferenceDialog(db, win)
    assert browser.table.rowCount() == 0 and "ships no pipe data" in browser.status.text()
    assert browser.manage_btn.text() == "Import / publish…"
    browser.deleteLater()

    # 2. A synthetic file in the template layout; its fingerprint is recorded.
    source = tmp_path / "syn_tubulars.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows([HEADER] + ROWS)
    before = _sha(source)

    # 3. A draft set is created in the real import dialog.
    dialog = TubularImportDialog(db, win)
    draft = dialog.create_draft("SYN journey tubulars")
    assert draft["status"] == tr.DRAFT and dialog.set_combo.currentData() == draft["id"]

    # 4. Preview: three NEW rows, the formula row INVALID; nothing is written.
    dialog.path_edit.setText(str(source))
    dialog.document_edit.setText("SYN measurement sheet")
    preview = dialog.run_preview()
    assert [r.status for r in preview.rows] == ["NEW", "NEW", "NEW", "INVALID"]
    assert "formula" in " ".join(preview.rows[3].issues) and tr.search(db, published_only=False) == []

    # 5. Confirming without accepting the partial import is refused: NOT IMPORTED, nothing written.
    dialog.reason_edit.setText("journey library")
    assert dialog.confirm_import() is None and dialog.status.text().startswith("NOT IMPORTED")
    assert tr.search(db, published_only=False) == []

    # 6. With explicit consent the three NEW rows are imported, with per-row provenance.
    dialog.partial_check.setChecked(True)
    result = dialog.confirm_import()
    assert result["imported"] == 3 and dialog.status.text().startswith("Imported 3 row(s)")
    rows = tr.search(db, published_only=False)
    assert {r["spec"].designation for r in rows} == {"SYN-J-DP", "SYN-J-NOID", "SYN-J-CSG"}
    assert all(r["spec"].provenance.file_fingerprint == before for r in rows)

    # 7. The import is audited, once.
    with db.session_scope() as session:
        assert session.query(AuditLog).filter_by(action="tubular_reference_import").count() == 1

    # 8. Publishing makes the set citable and immutable.
    published = dialog.publish_current()
    assert published["version"] == 1 and dialog.set_combo.count() == 0
    assert [s["status"] for s in tr.list_sets(db) if s["id"] == published["id"]] == [tr.PUBLISHED]
    dialog.deleteLater()

    # 9. The well is selected through the shared selection; the W13 page follows it.
    w13 = _tab(win, "EngineeringCalculatorTab")
    SelectionManager().select_well(well, {"name": "SYN-ALPHA"}, force=True)
    _pump(0.3)
    assert w13.current_well_id == well

    # 10. The drill-string dialog fills only what the library item holds.
    pipe = AddPipeDialog(w13)
    assert pipe.library_btn.isEnabled()
    assert pipe.apply_library_snapshot(_pick(db, win, "DP", "SYN-J-DP"))
    assert (pipe.od.value(), pipe.id_.value(), pipe.weight.value()) == (4.871, 4.013, 18.7)
    pipe.length.setValue(3000.0)
    pipe._save()
    component = pipe.result
    pipe.deleteLater()
    assert component[rb.BINDING_KEY]["snapshot"]["spec"]["designation"] == "SYN-J-DP"

    # 11. An item without an ID leaves the ID for the user; nothing is guessed.
    partial = AddPipeDialog(w13)
    partial.apply_library_snapshot(_pick(db, win, "DP", "SYN-J-NOID"))
    assert partial.id_.value() == 0.0 and "Unavailable in the library: id" in partial.library_label.text()
    partial.deleteLater()

    # 12. The Weight page calculates with the library component and saves a case that keeps the snapshot.
    assert w13.calculator_finder.open_path("Weight")
    w13.wt_pipes[:] = [component]
    w13._wt_refresh_table()
    w13.wt_mw.setValue(75.0)
    w13.wt_inc.setValue(0.0)
    w13.wt_tds.setValue(40.0)
    w13._wt_calculate()
    weight_case = w13.case_bar.save_case("SYN journey weight")
    assert weight_case["inputs"]["extra:pipes"]["value"][0][rb.BINDING_KEY] == component[rb.BINDING_KEY]

    # 13. History re-runs the case: MATCH.
    entry = next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == weight_case["id"])
    assert ch.recalculate_entry(entry)["status"] == "MATCH"

    # 14. Casing Strength from the library: yield is unknown, so nothing is rated.
    assert w13.calculator_finder.open_path("CSG/CMT › Casing Strength")
    w13.load_casing_from_library(_pick(db, win, "CASING", "SYN-J-CSG"))
    w13._csg_calc_strength()
    assert w13.csg_burst_res.text().startswith("Not calculated: yield strength unknown")

    # 15. The user enters the yield; the case records library values and a user-entered yield.
    w13.csg_yield.setValue(80000.0)
    w13._csg_calc_strength()
    casing_case = w13.case_bar.save_case("SYN journey casing")
    fields = casing_case["inputs"]["extra:provenance"]["value"]["fields"]
    assert fields["od_in"] == "reference" and fields["yield_psi"] == "user"

    # 16. A newer library version is published; reopening reports it and keeps the stored values.
    revision = tr.create_set(db, "SYN journey tubulars")
    tr.publish_set(db, revision["id"])
    assert w13.calculator_finder.open_path("Weight")
    w13.case_bar.reopen(weight_case["id"])
    assert "Library references: 1 MATCH" in w13.case_bar.status.text()
    assert "NOT applied" in w13.case_bar.last_reference_report[0]["message"]
    assert w13.wt_pipes[0]["od"] == 4.871

    # 17. Editing a filled value detaches the library; the next case stores no reference.
    edited = AddPipeDialog(w13, edit_data=w13.wt_pipes[0])
    edited.od.setValue(4.9)
    edited._save()
    assert rb.BINDING_KEY not in edited.result
    w13.wt_pipes[:] = [edited.result]
    edited.deleteLater()
    w13._wt_refresh_table()
    w13._wt_calculate()
    plain_case = w13.case_bar.save_case("SYN journey weight, edited")
    assert rb.find_bindings(plain_case["inputs"]) == []

    # 18. The stored snapshots survive a fresh read from the database file.
    stored = cc.get_case(db, casing_case["id"])
    assert [r["state"] for r in rb.drift_report(db, stored["inputs"])] == [rb.MATCH]

    # 19. A published set cannot be changed in place.
    with pytest.raises(tr.TubularReferenceError):
        tr.add_item(db, published["id"], tr.TubularSpec("DP", "SYN-LATE", tr.Provenance(origin="user")))

    # 20. The source file was never modified and is not stored: only its name and SHA-256 are kept.
    assert _sha(source) == before
    with db.session_scope() as session:
        details = [a.details or "" for a in session.query(AuditLog).filter_by(action="tubular_reference_import")]
    assert before in details[0] and "SYN-J-FORMULA" not in details[0]
