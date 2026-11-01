"""M55 directional: survey file import, plan designer, designer panel and import dialog.

Golden values for the designer are independent closed-form circular-arc
geometry (R = 30 / DLS[rad]); the designer itself positions stations with the
canonical minimum-curvature engine. Synthetic files in a temp dir only. UI tests
run on offscreen Qt (not Windows desktop testing).
"""
from __future__ import annotations

import csv
import math

import pytest

from core.survey_file_import import FT_TO_M, import_survey_file, import_survey_rows
from core.well_plan_designer import design_plan, dogleg_deg


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


# ---- survey file import ---------------------------------------------------------------------------
def test_csv_with_a_header_unit_in_feet_is_converted_exactly(tmp_path):
    path = _write(tmp_path / "s.csv", "MD (ft),Inc,Azi\n0,0,0\n1000,2.5,45\n2000,10,47.5\n")
    result = import_survey_file(path)
    assert result.ok and result.unit == "ft" and result.unit_source == "header"
    assert [s["md"] for s in result.stations] == pytest.approx([0.0, 1000 * FT_TO_M, 2000 * FT_TO_M])
    assert result.stations[1]["source_md"] == 1000 and result.stations[1]["source_unit"] == "ft"
    assert result.columns == {"md": "MD (ft)", "inc": "Inc", "azi": "Azi"}


def test_a_file_without_a_stated_unit_is_refused_until_the_user_chooses(tmp_path):
    path = _write(tmp_path / "s.csv", "Depth,Inclination,Azimuth\n0,0,0\n100,1,10\n")
    refused = import_survey_file(path)
    assert not refused.ok and refused.error == "The depth unit is not stated in the file; choose metres or feet explicitly."
    chosen = import_survey_file(path, unit="m")
    assert chosen.ok and chosen.unit_source == "user" and [s["md"] for s in chosen.stations] == [0.0, 100.0]


def test_a_header_unit_conflicting_with_the_choice_is_refused(tmp_path):
    path = _write(tmp_path / "s.csv", "MD (m),Inc,Azi\n0,0,0\n100,1,10\n")
    result = import_survey_file(path, unit="ft")
    assert not result.ok and "states 'm' but 'ft' was chosen" in result.error


def test_invalid_rows_are_rejected_with_their_source_row(tmp_path):
    path = _write(tmp_path / "s.csv", "MD,Inc,Azi\n0,0,0\n100,200,10\n200,3,400\n200,3,20\n300,x,5\n400,4,25\n")
    result = import_survey_file(path, unit="m")
    # Two rows claim MD 200; the first has an invalid azimuth. Both are rejected
    # (ambiguous station) and each reason is reported - nothing is picked silently.
    assert [s["md"] for s in result.stations] == [0.0, 400.0]
    reasons = {(i["row"], i["reason"]) for i in result.issues}
    assert (5, "Negative or duplicate measured depth") in reasons
    assert (3, "Inclination must be between 0 and 180 degrees") in reasons
    assert (4, "Azimuth must be in [0, 360) degrees") in reasons
    assert (6, "inc requires a finite numeric measurement") in reasons


def test_whitespace_aligned_text_and_a_title_line_are_read(tmp_path):
    text = "# synthetic survey\nSYNTHETIC SURVEY LISTING\nMeasured Depth   Incl   Azimuth\n0   0   0\n150.5   1.25   90\n"
    result = import_survey_file(_write(tmp_path / "s.txt", text), unit="m", azimuth_reference="grid north")
    assert result.ok and [s["md"] for s in result.stations] == [0.0, 150.5]
    assert result.azimuth_reference == "grid north"


def test_missing_columns_and_unknown_types_are_explicit(tmp_path):
    assert import_survey_rows([["MD", "Inc"], [0, 0]], unit="m").error.startswith("No header row with MD")
    assert import_survey_file(_write(tmp_path / "s.json", "{}")).error.startswith("Unsupported survey file type")


def test_an_xlsx_sheet_can_be_selected(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    workbook.active.title = "Notes"
    workbook.active.append(["Synthetic notes only"])
    sheet = workbook.create_sheet("Survey")
    for row in (["MD (m)", "Inc", "Azi"], [0, 0, 0], [500, 5, 120]):
        sheet.append(row)
    path = tmp_path / "s.xlsx"
    workbook.save(path)
    assert import_survey_file(path).error.startswith("No header row")          # first sheet has no survey
    result = import_survey_file(path, sheet="Survey")
    assert result.ok and result.sheet == "Survey" and result.stations[-1]["md"] == 500.0


# ---- plan designer (independent closed-form golden values) -----------------------------------------
def _radius(dls):
    return 30.0 / math.radians(dls)


def test_j_profile_matches_closed_form_arc_geometry():
    r = design_plan([{"type": "hold", "length": 500}, {"type": "curve", "inc": 30, "azi": 135, "dls": 3},
                     {"type": "hold_to_tvd", "tvd": 1500}], step=30, vs_azimuth=135,
                    targets=[{"name": "T1", "north": -345.58, "east": 345.58, "tvd": 1500, "radius": 10}])
    assert r.ok and r.warnings == []
    R = _radius(3)
    eob = next(s for s in r.stations if abs(s["md"] - 800.0) < 1e-6)
    assert eob["tvd"] == pytest.approx(500 + R * math.sin(math.radians(30)), abs=1e-6)
    assert math.hypot(eob["north"], eob["east"]) == pytest.approx(R * (1 - math.cos(math.radians(30))), abs=1e-6)
    hold = (1500 - (500 + R * 0.5)) / math.cos(math.radians(30))
    td = r.stations[-1]
    assert td["md"] == pytest.approx(800 + hold, abs=1e-6) and td["tvd"] == pytest.approx(1500, abs=1e-6)
    assert td["vs"] == pytest.approx(R * (1 - math.cos(math.radians(30))) + hold * 0.5, abs=1e-6)
    assert max(s["dls"] for s in r.stations) == pytest.approx(3.0, abs=1e-6)
    assert [s["type"] for s in r.segments] == ["Vertical to KOP", "Build", "Hold to TVD"]
    assert r.targets[0]["hit"] is True and r.targets[0]["distance"] < 0.05


def test_a_target_off_the_plan_or_without_a_radius_is_not_reported_as_hit():
    segments = [{"type": "hold", "length": 500}, {"type": "curve", "inc": 30, "azi": 135, "dls": 3},
                {"type": "hold_to_tvd", "tvd": 1500}]
    r = design_plan(segments, step=30, vs_azimuth=135, targets=[
        {"name": "mirror", "north": 345.58, "east": 345.58, "tvd": 1500, "radius": 10},   # azimuth 45, not 135
        {"name": "no radius", "north": -345.58, "east": 345.58, "tvd": 1500}])
    mirror, unsized = r.targets
    assert mirror["hit"] is False and mirror["distance"] > 10.0
    assert unsized["hit"] is False and unsized["radius"] == 0.0 and unsized["distance"] < 0.05


def test_s_profile_drop_and_dls_limit_warning():
    r = design_plan([{"type": "hold", "length": 300}, {"type": "curve", "inc": 20, "azi": 90, "dls": 2},
                     {"type": "hold", "length": 200}, {"type": "curve", "inc": 0, "azi": 90, "dls": 4}],
                    dls_limit=3.0)
    assert r.ok
    assert [s["type"] for s in r.segments] == ["Vertical to KOP", "Build", "Hold", "Drop"]
    assert r.stations[-1]["inc"] == pytest.approx(0.0, abs=1e-9)
    assert r.warnings == ["Segment 4 (Drop) DLS 4.00 deg/30 m exceeds the limit 3.00 deg/30 m."]
    # displacement: build arc + hold + drop arc, all due east (closed form)
    east = _radius(2) * (1 - math.cos(math.radians(20))) + 200 * math.sin(math.radians(20)) \
        + _radius(4) * (1 - math.cos(math.radians(20)))
    assert r.stations[-1]["east"] == pytest.approx(east, abs=1e-6)


def test_a_turn_at_constant_inclination_uses_the_spherical_dogleg():
    r = design_plan([{"type": "hold", "length": 100}, {"type": "curve", "inc": 30, "azi": 135, "dls": 3},
                     {"type": "curve", "inc": 30, "azi": 180, "dls": 2}])
    expected = math.degrees(math.acos(math.cos(math.radians(30)) ** 2
                                      + math.sin(math.radians(30)) ** 2 * math.cos(math.radians(45))))
    assert dogleg_deg(30, 135, 30, 180) == pytest.approx(expected)
    turn = r.segments[-1]
    assert turn["type"] == "Turn" and turn["length"] == pytest.approx(expected / 2 * 30)
    assert r.stations[-1]["azi"] == pytest.approx(180.0) and r.stations[-1]["inc"] == pytest.approx(30.0)


@pytest.mark.parametrize("segments, message", [
    ([{"type": "hold", "length": -5}], "hold length must be positive"),
    ([{"type": "curve", "inc": 10, "dls": 0}], "DLS must be positive"),
    ([{"type": "curve", "inc": 190, "dls": 2}], "between 0 and 180"),
    ([{"type": "hold", "length": 500}, {"type": "hold_to_tvd", "tvd": 400}], "is not below the current"),
    ([{"type": "curve", "inc": 90, "dls": 3}, {"type": "hold_to_tvd", "tvd": 2000}], "cannot hold to a TVD"),
    ([{"type": "spiral"}], "unknown type 'spiral'"),
    ([], "The plan has no segments."),
])
def test_invalid_plans_are_refused_with_a_reason(segments, message):
    result = design_plan(segments)
    assert not result.ok and message in result.error


# ---- UI (offscreen Qt) -------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_the_designer_panel_designs_exports_and_hands_the_plan_over(app, tmp_path):
    from tabs.well_plan_designer_panel import WellPlanDesignerPanel
    received = []
    panel = WellPlanDesignerPanel(use_plan=lambda rows, source: received.append((rows, source)))
    assert not panel.export_btn.isEnabled() and not panel.use_btn.isEnabled()
    panel.add_segment("hold", length=500)
    panel.add_segment("curve", inc=30, azi=135, dls=3)
    panel.add_segment("hold_to_tvd", length=1500)
    panel.dls_limit_spin.setValue(2.5)
    panel.add_target("T1", north=-345.58, east=345.58, tvd=1500, radius=10)
    result = panel.design()
    assert result.ok and panel.station_table.rowCount() == len(result.stations)
    text = panel.summary_label.text()
    assert "WARNING: Segment 2 (Build) DLS 3.00 deg/30 m exceeds the limit 2.50 deg/30 m." in text
    assert "T1: closest 0.0 m at MD 1623.9 m — inside radius" in text
    assert panel.use_btn.isEnabled() and panel.send_to_compare()
    rows, source = received[0]
    assert source.startswith("Designed plan (M55 plan designer v1)") and rows[-1]["md"] == pytest.approx(1623.903, abs=1e-3)
    out = tmp_path / "plan.csv"
    assert panel.export_csv(str(out))
    lines = list(csv.reader(out.open(encoding="utf-8")))
    assert lines[0][0].startswith("# M55 plan designer v1; Minimum curvature")
    assert lines[1][0].startswith("# WARNING: Segment 2") and lines[2][0] == "MD (m)"
    panel.deleteLater()


def test_the_designer_panel_names_a_missing_input(app):
    from tabs.well_plan_designer_panel import WellPlanDesignerPanel
    panel = WellPlanDesignerPanel()
    panel.add_segment("curve", inc=None, dls=3)
    assert panel.design() is None
    assert panel.summary_label.text() == "Not designed: Segment 1: enter the target inclination and DLS."
    assert not panel.export_btn.isEnabled()
    panel.deleteLater()


def test_the_survey_import_dialog_requires_an_explicit_unit(app, tmp_path):
    from dialogs.survey_import_dialog import SurveyImportDialog
    path = _write(tmp_path / "s.csv", "Depth,Inc,Azi\n0,0,0\n100,1,10\n200,250,10\n")
    dialog = SurveyImportDialog(str(path))
    assert not dialog.import_btn.isEnabled()
    assert dialog.status_label.text().startswith("Not importable: The depth unit is not stated")
    dialog.unit_combo.setCurrentIndex(dialog.unit_combo.findData("ft"))
    assert dialog.import_btn.isEnabled() and dialog.import_btn.text() == "Import 2 station(s)"
    assert dialog.station_table.item(1, 1).text() == f"{100 * FT_TO_M:.2f}"
    assert dialog.issue_table.rowCount() == 1 and "Inclination" in dialog.issue_table.item(0, 2).text()
    dialog.deleteLater()


# ---- M55 product integration (offscreen Qt, temporary file SQLite DB, synthetic wells) -------------
@pytest.fixture(scope="module")
def vertical_well(tmp_path_factory):
    from core.database import Company, Project, SurveyPoint, Well
    from synthetic_operations import make_file_database
    db = make_file_database(tmp_path_factory.mktemp("m55int") / "synthetic-m55.db")
    with db.session_scope() as session:
        company = Company(name="Synthetic Co", code="SYNC")
        session.add(company)
        session.flush()
        project = Project(name="Synthetic Field", code="SYNP", company_id=company.id)
        session.add(project)
        session.flush()
        well = Well(name="SYN-VERT", code="SYN-VERT", project_id=project.id)
        session.add(well)
        session.flush()
        well_id = well.id
        for md in (0.0, 300.0, 600.0, 900.0):
            session.add(SurveyPoint(well_id=well_id, md=md, inc=0.0, azi=0.0))
    yield db, well_id
    db.engine.dispose()


def _dispose(app, widget):
    from PySide6.QtCore import QCoreApplication, QEvent
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_the_viewer_sends_a_designed_plan_to_plan_vs_actual(app, vertical_well):
    from core import trajectory_compare as tc
    from tabs.trajectory_viewer import TrajectoryViewerTab
    db, well_id = vertical_well
    viewer = TrajectoryViewerTab(db)
    try:
        viewer.set_context(well_id, None)
        tab_titles = [viewer.view_tabs.tabText(i) for i in range(viewer.view_tabs.count())]
        assert "Plan designer" in tab_titles
        designer, compare = viewer.plan_designer, viewer.compare_panel
        designer.add_segment("hold", length=900)                 # vertical plan on a vertical well
        assert designer.design().ok and designer.send_to_compare()
        assert viewer.view_tabs.currentWidget() is compare and compare.mode == "plan"
        assert compare.plan_label.text().startswith("Designed plan (M55 plan designer v1)")
        compare.run()
        assert compare.wait_until_idle()
        assert compare.result.status == tc.ASSESSED and compare.result.kind == "plan_vs_actual"
        assert all(abs(r["distance_m"]) < 0.01 for r in compare.result.rows)
        # Kick off at 300 m to the east: the vertical actual well departs from the plan only below KOP.
        designer.segment_table.setRowCount(0)
        designer.add_segment("hold", length=300)
        designer.add_segment("curve", inc=12, azi=90, dls=3)
        designer.add_segment("hold", length=480)
        assert designer.design().ok and designer.send_to_compare()
        assert compare.result is None                            # the old answer is cleared
        compare.run()
        assert compare.wait_until_idle()
        rows = compare.result.rows
        shallow = [r["distance_m"] for r in rows if r["actual_md"] <= 300.0]
        deep = [r["distance_m"] for r in rows if r["actual_md"] > 300.0]
        assert shallow and all(abs(d) < 0.01 for d in shallow)
        assert deep and deep == sorted(deep) and deep[-1] > 10.0
    finally:
        _dispose(app, viewer)


def test_the_comparison_refuses_an_unusable_handed_over_plan(app, vertical_well):
    from tabs.trajectory_compare_panel import TrajectoryComparePanel
    db, well_id = vertical_well
    panel = TrajectoryComparePanel(db)
    try:
        panel.set_well(well_id)
        assert not panel.set_plan_rows([{"md": 0, "inc": 0, "azi": 0}], "one station")
        assert not panel.set_plan_rows([{"md": "x", "inc": 0, "azi": 0}, {"md": 1}], "garbage")
        assert panel.plan_rows is None and panel.plan_label.text().startswith("Plan refused")
    finally:
        panel.cleanup()
        _dispose(app, panel)


def test_w6_import_fills_the_editable_survey_table_in_metres_without_saving(app, tmp_path, vertical_well):
    from tabs.w6_Trajectory_Widget import SurveyDataTab
    db, well_id = vertical_well
    before = len(db.load_survey_points(well_id=well_id))
    tab = SurveyDataTab(db)
    try:
        path = _write(tmp_path / "ft.csv", "MD (ft),Inc,Azi\n0,0,0\n1000,2.5,45\n2000,5,47.5\n")
        result = import_survey_file(str(path), azimuth_reference="grid north")
        assert tab.apply_imported_surveys(result)
        assert tab.survey_table.rowCount() == 3
        assert [tab.survey_table.item(r, 1).text() for r in range(3)] == ["0", "304.8", "609.6"]
        assert tab.survey_table.item(2, 3).text() == "47.5" and tab.survey_table.item(1, 0) is None
        assert "azimuth reference: grid north" in tab.survey_import_note and "not saved" in tab.survey_import_note
        assert len(db.load_survey_points(well_id=well_id)) == before          # nothing persisted
        refused = import_survey_file(str(_write(tmp_path / "nounit.csv", "Depth,Inc,Azi\n0,0,0\n10,1,1\n")))
        assert not refused.ok and not tab.apply_imported_surveys(refused) and tab.survey_table.rowCount() == 3
    finally:
        _dispose(app, tab)


def test_the_embedded_designer_holds_no_python_reference_to_the_viewer(app):
    """M50 contract: a callback attribute pointing back at the viewer formed a reference
    cycle, leaving Qt wrappers to an arbitrary garbage collection (native crash risk)."""
    import gc

    from tabs.trajectory_viewer import TrajectoryViewerTab
    viewer = TrajectoryViewerTab(None)
    try:
        assert viewer.plan_designer.use_plan is None and viewer.plan_designer.handover is True
        assert viewer not in gc.get_referents(*vars(viewer.plan_designer).values())
    finally:
        _dispose(app, viewer)
