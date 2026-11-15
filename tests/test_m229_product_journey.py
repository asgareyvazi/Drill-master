"""M229: 35-step product journey through the real main window for the M201-M228 work.

Real Qt widgets (the M70 window fixture: real MainWindow, real file database, real authorization, admin session),
the real DDR pipeline on a COPY of the synthetic golden workbook (SHA-256 checked), the persisted review queue, the
M227 data-quality workspace, the trajectory viewer with a saved view, the tubular library from draft to publish, a
frozen architecture revision, the W13 Volumes / Hydraulics / Weight / Casing Strength pages, the cement worksheet,
calculation history, a second-well leak check, and backup -> modify -> restore through the window's own slots with
no worker left running. SYNTHETIC data only; the protected DDR workbook is never touched.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_m70_selection_audit import _pump, window  # noqa: E402,F401

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_ddr_golden_a.xlsx"
J_STATIONS = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 500.0, "inc": 0.0, "azi": 0.0},
              {"md": 650.0, "inc": 15.0, "azi": 135.0}, {"md": 800.0, "inc": 30.0, "azi": 135.0}]
HEADER = ["Component type", "Designation", "Grade", "Connection", "Nominal OD (in)", "ID (in)",
          "Nominal weight (lb/ft)", "Tool joint OD (in)", "Page"]
ROWS = [["DP", "SYN-Q-DP", "SYN-G", "SYN-C", "4.871", "4.013", "18.7", "6.37", "3"],
        ["CASING", "SYN-Q-CSG", "SYN-80", "", "9.611", "8.703", "46.1", "", "4"]]
ARCH = [
    {"kind": "section", "name": "12-1/4 in hole", "top_md": 0, "bottom_md": 1000, "hole_in": 12.25},
    {"kind": "casing", "name": "SYN csg", "top_md": 0, "bottom_md": 1000, "od_in": 9.611, "id_in": 8.703,
     "hole_in": 12.25, "grade": "SYN-80", "weight_ppf": 46.1},
    {"kind": "shoe", "name": "SYN csg", "top_md": 1000},
    {"kind": "cement", "name": "SYN csg", "top_md": 500, "bottom_md": 1000},
]


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


def _wait_maintenance(win, timeout=120):
    deadline = time.monotonic() + timeout
    while win._maintenance_worker is not None and time.monotonic() < deadline:
        _pump(0.05)
    assert win._maintenance_worker is None, "maintenance worker did not finish"


def test_m229_thirty_five_step_product_journey(window, tmp_path, monkeypatch):  # noqa: F811
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox
    shown = []
    for name, answer in (("information", QMessageBox.Ok), ("warning", QMessageBox.Ok),
                         ("critical", QMessageBox.Ok), ("question", QMessageBox.No)):
        monkeypatch.setattr(QMessageBox, name, staticmethod(
            lambda *a, _answer=answer, _name=name, **k: shown.append((_name, str(a[2]) if len(a) > 2 else ""))
            or _answer))
    from core import calculation_cases as cc
    from core import calculation_history as ch
    from core import data_quality_workspace as dqw
    from core import ddr_carry_forward as carry
    from core import ddr_import_pipeline as pipe
    from core import trajectory_views as tv
    from core import well_architecture as wa
    from core.database import AuditLog, DailyReport, LogisticsPersonnel
    from core.ddr_continuation import DEFERRED_UNRESOLVED, SAFELY_ATTACHED_CONTINUATION
    from core.ddr_import_service import DDRImportService
    from core.ddr_well_identity import CHOOSE_SELECTED, make_decision
    from core.engineering import reference_binding as rb
    from core.engineering import tubular_reference as tr
    from core.import_quality import apply_review_decisions
    from core.import_router import route_file
    from core.selection_manager import SelectionManager
    from dialogs.excel_import_dialog import has_meaningful_canonical_data
    from dialogs.import_review_dialog import ImportReviewDialog
    from dialogs.tubular_import_dialog import TubularImportDialog

    win, db, ids = window
    well, other = ids["alpha"], ids["twin_1"]
    manager = SelectionManager()

    # 1. The real window offers the workspace, the review queue and the tubular library.
    actions = [a.text() for m in win.menuBar().findChildren(type(win.menuBar().actions()[0].menu()))
               for a in m.actions()]
    for label in ("Data Quality Workspace", "Import Review Queue", "Tubular Reference Library"):
        assert any(label in t for t in actions), label

    # 2. A copy of the synthetic workbook; its fingerprint is recorded.
    source = tmp_path / "journey.xlsx"
    shutil.copyfile(FIXTURE, source)
    before = _sha(source)

    # 3. The real DDR pipeline prepares the import (version 2, continuation proposals).
    service = DDRImportService()
    out = pipe.prepare_import(str(source), route=route_file, template_matcher=service._auto_match_template,
                              extract_file=service.extract_file, meaningful=has_meaningful_canonical_data)
    assert out.import_report["pipeline_version"] == 2
    extracted = out.extracted
    apply_review_decisions(extracted, out.import_report["review"])

    # 4. Wrong well: the workbook names another well, so nothing is saved without an operator decision.
    target = DDRImportService(db, well)
    reports_before = len(db.get_reports_by_well(well)) if hasattr(db, "get_reports_by_well") else None
    refused = target.import_records(json.loads(json.dumps(extracted, default=str)))
    assert refused["status"] == "VALIDATION_ERROR" and not refused["report_id"], refused.get("status")
    if reports_before is not None:
        assert len(db.get_reports_by_well(well)) == reports_before

    # 5. An explicit, audited decision files the report under the selected well.
    assessment = target.assess_well_identity(extracted["well_info"])
    extracted["metadata"]["well_identity_decision"] = make_decision(
        assessment, CHOOSE_SELECTED, "the selected well is the operated well of this synthetic report")
    result = target.import_records(extracted)
    report_id = result["report_id"]
    assert report_id, result
    with db.session_scope() as session:
        assert session.get(DailyReport, report_id).well_id == well
        assert session.query(AuditLog).filter_by(action="ddr_well_identity_decision").count() >= 1

    # 6. Every undecided proposal is persisted in the review queue.
    items = db.get_import_review_items(well, report_id=report_id)
    pending = [i for i in items if i["state"] == DEFERRED_UNRESOLVED]
    assert pending and len(pending) == len(out.import_report["review"])

    # 7. The real review dialog shows the open items.
    review = ImportReviewDialog(db, well, win, report_id=report_id)
    _pump(0.1)
    assert review.table.rowCount() == len(pending)
    review.close()

    # 8. The well is selected through the hierarchy path; the data-quality workspace lists the open review.
    manager.select_well(well, {"id": well, "name": "SYN-ALPHA-01"}, force=True)
    win._targeted_refresh(well, None, None)
    _pump(0.4)
    assert win.current_well and win.current_well["id"] == well
    workspace = win.open_data_quality()
    _pump(0.2)
    rows = [i for i in workspace.shown if i.category == dqw.CATEGORY_REVIEW and i.report_id == report_id]
    assert len(rows) == 1 and str(len(pending)) in rows[0].message

    # 9. "Open" on that row opens the review queue of exactly that report (read-only workspace, no writes).
    workspace.table.selectRow(workspace.shown.index(rows[0]))
    opened = workspace.open_selected()
    _pump(0.2)
    assert isinstance(opened, ImportReviewDialog) and opened.table.rowCount() == len(pending)
    opened.close()

    # 10. A deferred continuation is attached later through the audited operation; a decided item stays decided.
    eligible = [i for i in pending if i["eligible"] and i["review_type"] == "continuation"
                and i.get("detected_table", "time_logs_24h") == "time_logs_24h"]
    attached = db.resolve_import_review_item(eligible[0]["id"], well, "ATTACH_CONTINUATION")
    assert attached["state"] == SAFELY_ATTACHED_CONTINUATION
    with pytest.raises(ValueError, match="already decided"):
        db.resolve_import_review_item(eligible[0]["id"], well, "REJECT")

    # 11. The source workbook was never modified.
    assert _sha(source) == before

    # 12. Manual next day: carry-forward needs confirmation; with it, personnel is carried and marked CARRIED.
    with db.session_scope() as session:
        day1 = session.get(DailyReport, report_id)
        session.add(LogisticsPersonnel(well_id=well, report_id=report_id, **_personnel_fields()))
        day2 = DailyReport(well_id=well, section_id=day1.section_id, report_date=day1.report_date
                           + __import__("datetime").timedelta(days=1), report_number=(day1.report_number or 0) + 1)
        session.add(day2)
        session.flush()
        day2_id = day2.id
        with pytest.raises(carry.CarryForwardRefused):
            carry.apply(session, report_id, day2_id, ["personnel"], confirmed=False)
        carry.apply(session, report_id, day2_id, ["personnel"], confirmed=True)
        assert carry.section_states(session, day2_id)["personnel"]["state"] == carry.CARRIED

    # 13. The workspace shows the unconfirmed carried section; after confirmation it is gone.
    workspace.refresh()
    assert any(i.category == dqw.CATEGORY_CARRIED and i.report_id == day2_id for i in workspace.shown)
    with db.session_scope() as session:
        carry.confirm(session, day2_id, ["personnel"], note="checked on the rig")
    workspace.refresh()
    assert not any(i.category == dqw.CATEGORY_CARRIED and i.report_id == day2_id for i in workspace.shown)
    workspace.close()

    # 14. Surveys are stored; the real trajectory viewer draws them.
    assert db.save_survey_points([dict(s, well_id=well) for s in J_STATIONS])
    viewer = _tab(win, "TrajectoryWidget").viewer_tab
    viewer.set_context(well)
    _pump(0.2)
    assert viewer.table.rowCount() == len(J_STATIONS)

    # 15. A named view is saved from the viewer.
    answers = ["SYN journey view", "synthetic"]
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: (answers.pop(0), True)))
    saved_view = viewer.saved_views.save_current()
    assert saved_view is not None and saved_view["station_count"] == len(J_STATIONS)

    # 16. Reopened, the current data reproduce it: MATCH.
    viewer.saved_views.select_view(saved_view["view_key"])
    record, state = viewer.saved_views.open_selected()
    assert state.state == tv.MATCH and record["id"] == saved_view["id"]

    # 17. A later survey edit is reported as DIFFERENT; the saved snapshot is shown, never rewritten.
    assert db.save_survey_points([{"md": 950.0, "inc": 45.0, "azi": 135.0, "well_id": well}])
    viewer.saved_views.select_view(saved_view["view_key"])
    record, state = viewer.saved_views.open_selected()
    assert state.state == tv.DIFFERENT and record["stations_sha256"] == saved_view["stations_sha256"]
    viewer.reload()

    # 18. A draft library set is filled from a synthetic CSV in the real import dialog (no shipped pipe data).
    csv_path = tmp_path / "syn_tubulars.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows([HEADER] + ROWS)
    csv_before = _sha(csv_path)
    importer = TubularImportDialog(db, win)
    draft = importer.create_draft("SYN journey M229")
    importer.path_edit.setText(str(csv_path))
    importer.document_edit.setText("SYN measurement sheet")
    preview = importer.run_preview()
    assert [r.status for r in preview.rows] == ["NEW", "NEW"] and not preview.blocking
    importer.reason_edit.setText("journey library")
    assert importer.confirm_import()["imported"] == 2

    # 19. Publishing makes it citable; a published set cannot be changed in place; the CSV is untouched.
    published = importer.publish_current()
    importer.deleteLater()
    assert published["version"] == 1 and published["id"] == draft["id"]
    with pytest.raises(tr.TubularReferenceError):
        tr.add_item(db, published["id"], tr.TubularSpec("DP", "SYN-LATE", tr.Provenance(origin="user")))
    assert _sha(csv_path) == csv_before

    # 20. The architecture revision pins the library snapshot of its casing.
    csg_snapshot = _pick(db, win, "CASING", "SYN-Q-CSG")
    binding = rb.make_binding(csg_snapshot, rb.ARCHITECTURE_FIELDS)
    components = json.loads(json.dumps(ARCH))
    components[1]["tubular_reference"] = binding
    revision = wa.get_revision(db, wa.save_revision(db, well, components, wellbore_id=ids["bore"])["id"])
    assert revision["components"][1][rb.BINDING_KEY] == binding and tr.verify_snapshot(binding["snapshot"]) == []

    # 21. The W13 page follows the selected well.
    w13 = _tab(win, "EngineeringCalculatorTab")
    assert w13.current_well_id == well
    dp_binding = rb.make_binding(_pick(db, win, "DP", "SYN-Q-DP"), rb.PIPE_COMPONENT_FIELDS)

    def library_pipe(length):
        return rb.attach({"type": "Drill Pipe", "od": 4.871, "id": 4.013, "length": length, "weight": 18.7,
                          "grade": "SYN-G", "connection": "SYN-C", "tj_od": 6.37}, dp_binding)

    def history_status(case):
        entry = next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case["id"])
        return ch.recalculate_entry(entry)["status"]

    # 22. Volumes with a library pipe: the closed-form string volume, a case that keeps the snapshot, MATCH.
    assert w13.calculator_finder.open_path("Volume › Well Volumes")
    w13.vol_pumps[:] = [{"name": "SYN P1", "output_bbl_stk": 0.1, "spm": 100.0}]
    w13.vol_pipes[:] = [library_pipe(3000.0)]
    w13.vol_casings[:] = [{"type": "SYN casing", "od": 9.611, "id": 8.703, "from": 0.0, "to": 1000.0},
                          {"type": "Open Hole", "od": 8.5, "id": 8.5, "from": 1000.0, "to": 3000.0}]
    w13._vol_refresh_pump_table(), w13._vol_refresh_pipe_table(), w13._vol_refresh_csg_table()
    w13.vol_depth.setValue(3000.0)
    w13._vol_calculate()
    assert w13.vol_assessment["results"]["string_volume_bbl"] == pytest.approx(
        4.013 ** 2 / 1029.4 * 3000.0 * 3.28084, rel=1e-9)
    volumes_case = w13.case_bar.save_case("SYN M229 volumes")
    assert volumes_case["inputs"]["extra:pipes"]["value"][0][rb.BINDING_KEY] == dp_binding
    assert history_status(volumes_case) == "MATCH"

    # 23. Hydraulics with the same pipe: a case and MATCH.
    assert w13.calculator_finder.open_path("Hydraulics")
    w13.hy_pumps[:] = [{"name": "SYN P1", "output_bbl_stk": 0.1, "spm": 100.0}]
    w13._hy_refresh_pump_table()
    w13.hy_pipe_rows = [library_pipe(3000.0)]
    w13.hy_csg_rows = [{"type": "SYN casing", "od": 9.611, "id": 8.703, "from": 0.0, "to": 1000.0},
                       {"type": "Open Hole", "od": 8.5, "id": 8.5, "from": 1000.0, "to": 3000.0}]
    w13.hy_nzl_rows = [{"size": 12, "qty": 3}]
    w13._hy_update_tfa()
    w13.hy_bit_diameter.setValue(8.5)
    w13.hy_model.setCurrentText("Bingham Plastic")
    w13.hy_wt.setCurrentText("Vertical")
    w13.hy_bit_dep.setValue(3000.0)
    w13.hy_confirm_defaults.setChecked(True)
    w13._hy_run_calc()
    assert not w13.hy_result.errors
    hydraulics_case = w13.case_bar.save_case("SYN M229 hydraulics")
    assert history_status(hydraulics_case) == "MATCH"

    # 24. Weight with the library pipe: a case that keeps the binding and MATCH.
    assert w13.calculator_finder.open_path("Weight")
    w13.wt_pipes[:] = [library_pipe(3000.0)]
    w13._wt_refresh_table()
    w13.wt_mw.setValue(75.0)
    w13.wt_inc.setValue(0.0)
    w13.wt_tds.setValue(40.0)
    w13._wt_calculate()
    weight_case = w13.case_bar.save_case("SYN M229 weight")
    assert weight_case["inputs"]["extra:pipes"]["value"][0][rb.BINDING_KEY] == dp_binding
    assert history_status(weight_case) == "MATCH"

    # 25. Casing Strength from the library: yield unknown -> not rated; the user's yield is recorded as such.
    assert w13.calculator_finder.open_path("CSG/CMT › Casing Strength")
    w13.load_casing_from_library(csg_snapshot)
    w13._csg_calc_strength()
    assert w13.csg_burst_res.text().startswith("Not calculated: yield strength unknown")
    w13.csg_yield.setValue(80000.0)
    w13._csg_calc_strength()
    casing_case = w13.case_bar.save_case("SYN M229 casing")
    fields = casing_case["inputs"]["extra:provenance"]["value"]["fields"]
    assert fields["od_in"] == "reference" and fields["yield_psi"] == "user"

    # 26. The cement worksheet derives from the frozen revision, stays WORKSHEET and re-runs MATCH; no picker.
    work = wa.cement_annulus(revision["components"], "SYN csg", open_hole_in=12.25, excess_pct=10.0)
    work = {**work, "architecture_revision_id": revision["id"], "architecture_revision": revision["revision"],
            "components_sha256": revision["components_sha256"], "open_hole_in": 12.25,
            "wellbore_id": revision.get("wellbore_id")}
    inputs, results = wa.cement_case_payload(work)
    cement_case = cc.save_case(db, calculator=wa.CEMENT_CALCULATOR, name="SYN M229 cement", inputs=inputs,
                               results=results, method=work["method"], method_version=work["version"],
                               well_id=well, note=f"{wa.CEMENT_WORKSHEET_LABEL} — {work['label']}")
    stored = cc.get_case(db, cement_case["id"])
    assert wa.verify_cement_case(db, stored["inputs"], stored["results"], stored["method_version"])["status"] == \
        "MATCH"
    assert "WORKSHEET" in stored["note"]
    group = w13.cmt_hole.parentWidget()
    from PySide6.QtWidgets import QPushButton
    assert not any("Library" in b.text() for b in group.findChildren(QPushButton))

    # 27. A newer library version is reported on reopen; the stored values and the old snapshot stay.
    newer = tr.create_set(db, "SYN journey M229")
    tr.add_item(db, newer["id"], tr.TubularSpec(component_type="HWDP", designation="SYN-Q-HW",
                                                provenance=tr.Provenance(origin="user", entered_by="journey")))
    tr.publish_set(db, newer["id"])
    assert w13.calculator_finder.open_path("Weight")
    w13.case_bar.reopen(weight_case["id"])
    assert "Library references: 1 MATCH" in w13.case_bar.status.text()
    assert w13.wt_pipes[0]["od"] == 4.871

    # 28. Calculation history lists every case of this well.
    names = {e.name for e in ch.load_history(db, sources=["Calculation case"]) if e.well_id == well}
    for case in (volumes_case, hydraulics_case, weight_case, casing_case, cement_case):
        assert case["name"] in names

    # 29. Second well: selecting it moves W13 and the workspace, and nothing of the first well leaks.
    manager.select_well(other, {"id": other, "name": "SYN-TWIN-01"}, force=True)
    win._targeted_refresh(other, None, None)
    _pump(0.4)
    assert w13.current_well_id == other and win.current_well["id"] == other
    twin_workspace = win.open_data_quality()
    assert all(i.report_id != report_id and i.report_id != day2_id for i in twin_workspace.shown)
    twin_workspace.close()
    assert tv.list_views(db, other) == []
    assert all(c["id"] not in {volumes_case["id"], weight_case["id"]}
               for c in cc.list_cases(db, well_id=other))
    assert db.get_import_review_items(other, report_id=report_id) == []

    # 30. A verified backup is made through the window's own slot.
    backups_before = len(win.backup_service.list_backups())
    win.backup_database_now()
    _wait_maintenance(win)
    assert shown[-1][0] == "information" and "Verified backup created" in shown[-1][1], shown[-3:]
    assert len(win.backup_service.list_backups()) == backups_before + 1
    backup_path = Path(win.backup_service.list_backups(kinds=("backup",))[0][0])     # newest first

    # 31. The data is modified after the backup.
    late = cc.save_case(db, calculator="Quick Calc", name="SYN made after the backup", inputs={"a": 2},
                        results={"r": 2}, well_id=well)

    # 32. No worker is left running before the restore.
    assert win._maintenance_worker is None and win._hierarchy_worker is None
    assert not [t for t in win.findChildren(QThread) if t.isRunning()]

    # 33. Restore through the window, choosing the backup made in step 30.
    import dialogs.database_maintenance_dialog as dialog_module
    chosen_path = backup_path

    class Chosen:
        def __init__(self, *_a, **_k):
            pass

        def exec(self):
            return QDialog.Accepted

        def selected_candidate(self):
            return chosen_path, {}

    monkeypatch.setattr(dialog_module, "RestoreDatabaseDialog", Chosen)
    closed = []
    monkeypatch.setattr(win, "close", lambda: closed.append(win._close_confirmed) or True)
    win.restore_database()
    _wait_maintenance(win)
    assert shown[-1][0] == "information" and "restored and verified" in shown[-1][1], shown[-3:]
    assert closed == [True]

    # 34. The restored file holds the pre-backup cases and not the later one; the journey data survived.
    with sqlite3.connect(db.db_path) as raw:
        case_ids = {r[0] for r in raw.execute("SELECT id FROM calculation_cases")}
        assert late["id"] not in case_ids and {volumes_case["id"], cement_case["id"]} <= case_ids
        assert raw.execute("SELECT well_id FROM daily_reports WHERE id = ?", (report_id,)).fetchone() == (well,)

    # 35. After the restore no worker is orphaned and the source files are still untouched.
    _pump(0.2)
    assert win._maintenance_worker is None
    assert not [t for t in win.findChildren(QThread) if t.isRunning()]
    assert _sha(source) == before and _sha(csv_path) == csv_before


def _personnel_fields():
    from core.database import LogisticsPersonnel
    columns = {c.name for c in LogisticsPersonnel.__table__.columns}
    fields = {}
    for name, value in (("company", "SYN contractor"), ("name", "SYN crew"), ("count", 4), ("pob", 4),
                        ("position", "SYN crew")):
        if name in columns:
            fields[name] = value
    return fields
