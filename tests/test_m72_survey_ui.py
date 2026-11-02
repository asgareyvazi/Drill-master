"""M72 desktop flows (offscreen Qt, SYNTHETIC SQLite database): survey revisions panel,
plan designer tie-in and solver, plan-vs-actual on a survey revision with target checks."""
from __future__ import annotations

import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

from core import survey_revisions as sr  # noqa: E402
from core import trajectory_compare as tc  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402
from tests.test_m72_surveys_solver import J_STATIONS  # noqa: E402


@pytest.fixture
def viewer(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    manager = _open(tmp_path / "ui.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    manager.save_survey_points([dict(s, well_id=ids["A"][0]) for s in J_STATIONS])
    from tabs.trajectory_viewer import TrajectoryViewerTab
    widget = TrajectoryViewerTab(manager)
    widget.set_context(ids["A"][0])
    yield widget, manager, ids
    widget.compare_panel.wait_until_idle()
    widget.deleteLater()
    app.processEvents()
    manager.close()


def test_freeze_import_preview_and_compare_from_the_panel(viewer, tmp_path):
    widget, manager, ids = viewer
    panel = widget.survey_revisions
    assert widget.view_tabs.indexOf(panel) >= 0
    assert panel.freeze_current() is None and "depth datum" in panel.status.text()     # declared, never assumed
    panel.datum_edit.setText("RKB")
    first = panel.freeze_current()
    assert first["revision"] == 1 and panel.table.rowCount() == 1
    assert widget.plan_designer.tie_combo.count() == 2                                 # tie-in list refreshed
    csv = tmp_path / "SYN_survey_ft.csv"
    csv.write_text("MD,Inc,Azi\n0,0,0\n1640.41994751,0,0\n2132.54593176,15,135\n2624.67191601,30,135\n"
                   "2952.75590551,31,135\n")
    panel.unit_combo.setCurrentIndex(panel.unit_combo.findData("ft"))
    checked = panel.preview_file(str(csv))
    assert checked.ok and checked.stations[1]["md"] == pytest.approx(500.0) and panel.confirm_btn.isEnabled()
    assert "Preview of SYN_survey_ft.csv" in panel.detail.toPlainText()
    second = panel.confirm_import()
    assert second["mode"] == "replace" and second["parent_id"] == first["id"] and second["source_unit"] == "ft"
    panel.table.selectRow(0)
    diff = panel.compare_selected()
    assert diff["added"] == [pytest.approx(900.0)] and "1 added" in panel.detail.toPlainText()
    bad = tmp_path / "SYN_conflict.csv"
    bad.write_text("MD,Inc,Azi\n0,0,0\n100,1,0\n100,2,0\n")
    panel.unit_combo.setCurrentIndex(panel.unit_combo.findData("m"))
    assert not panel.preview_file(str(bad)).ok and not panel.confirm_btn.isEnabled()
    assert len(sr.list_revisions(manager, ids["A"][0])) == 2


def test_designer_ties_in_solves_and_hands_a_continuous_plan_to_compare(viewer):
    widget, manager, ids = viewer
    well = ids["A"][0]
    rev = sr.save_revision(manager, well, J_STATIONS[:2], depth_datum="RKB")          # vertical to MD 500
    designer, compare = widget.plan_designer, widget.compare_panel
    designer.refresh_tie_ins()
    designer.tie_combo.setCurrentIndex(designer.tie_combo.findData(rev["id"]))
    hd = 488.7133898
    designer.add_target("T", -hd * math.cos(math.radians(45)), hd * math.sin(math.radians(45)), 1500.0, 2.0)
    designer.kop_spin.setValue(500.0)
    designer.build_spin.setValue(3.0)
    answer = designer.solve_to_target()
    assert answer["feasible"] and designer.result.ok and "Solved" in designer.summary_label.text()
    assert designer.result.stations[0]["md"] == 500.0 and designer.result.targets[0]["distance"] < 1e-6
    plan = designer.save_new_plan("SYN tied plan")
    assert plan["inputs"]["tie_in"]["survey_revision_id"] == rev["id"]
    reopened = designer.open_plan(plan["id"])
    assert designer.tie_combo.currentData() == rev["id"] and designer.result.ok and reopened["id"] == plan["id"]
    assert designer.send_to_compare() is True
    assert compare.plan_rows[0]["md"] == 0.0 and "tied to survey rev" in compare.plan_source
    assert compare.plan_targets and compare.plan_targets[0]["name"] == "T"
    # actual = the frozen J survey; the plan continues it, so the first 800 m coincide
    actual = sr.save_revision(manager, well, J_STATIONS, mode="replace", parent_id=rev["id"], depth_datum="RKB")
    compare.refresh_actual_sources()
    compare.actual_combo.setCurrentIndex(compare.actual_combo.findData(actual["id"]))
    compare.run()
    assert compare.wait_until_idle()
    assert compare.result.status == tc.ASSESSED
    (check,) = compare.result.target_checks
    assert check["status"] == "ASSESSED" and check["hit"] is False and check["distance_m"] > 2.0
    assert any("Target T: actual path passes" in compare.reason_list.item(i).text()
               for i in range(compare.reason_list.count()))
    record_id = compare.save()
    assert record_id is not None
    import json
    from core.database import TrajectoryCalculation
    with manager.session_scope() as session:
        stored = session.get(TrajectoryCalculation, record_id).parameters_json
    blob = json.dumps(stored)
    assert str(actual["stations_sha256"]) in blob and '"actual_source": "survey revision"' in blob
    assert '"target_checks"' in blob


def test_a_plan_whose_revision_is_missing_is_not_redesigned_from_the_surface(viewer):
    widget, manager, ids = viewer
    designer = widget.plan_designer
    rev = sr.save_revision(manager, ids["A"][0], J_STATIONS[:2], depth_datum="RKB")
    designer.refresh_tie_ins()
    designer.tie_combo.setCurrentIndex(designer.tie_combo.findData(rev["id"]))
    designer.add_segment("hold", 100.0, None, None, None)
    plan = designer.save_new_plan("SYN pinned")
    designer.tie_combo.removeItem(designer.tie_combo.findData(rev["id"]))
    designer.refresh_tie_ins = lambda: None                    # simulate an unavailable revision list
    designer.open_plan(plan["id"])
    assert designer.result is None and "not available" in designer.summary_label.text()


def test_a_stale_wellbore_selection_is_confirmed_in_the_database_before_it_is_recorded(viewer):
    from core.selection_manager import SelectionManager
    _widget, manager, ids = viewer
    sel = SelectionManager()
    (well_a, bore_a), (_well_b, bore_b) = ids["A"], ids["B"]
    try:
        sel.select_well(well_a, {"id": well_a})
        sel.select_wellbore(bore_a, {"id": bore_a, "well_id": well_a})
        assert sel.wellbore_for(well_a, db=manager) == bore_a
        sel._wellbore_id = 999_999                         # a selection left over from another database
        assert sel.wellbore_for(well_a) == 999_999 and sel.wellbore_for(well_a, db=manager) is None
        sel._wellbore_id = bore_b                          # exists, but on the other well
        assert sel.wellbore_for(well_a, db=manager) is None
    finally:
        sel.clear()
