"""M52 trajectory comparison panel on a temporary file SQLite DB (synthetic wells, offscreen Qt).

Real panel, real DatabaseManager, real worker thread; nothing is mocked except
one deliberate read failure.  Offscreen Qt - not Windows desktop testing.
"""
from __future__ import annotations

import csv
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from core import trajectory_compare as tc  # noqa: E402
from synthetic_operations import make_file_database  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    from core.database import Company, Project, SurveyPoint, Well
    db = make_file_database(tmp_path_factory.mktemp("m52traj") / "synthetic-m52-traj.db")
    with db.session_scope() as session:
        company = Company(name="Synthetic Co", code="SYNC")
        session.add(company)
        session.flush()
        project = Project(name="Synthetic Field", code="SYNP", company_id=company.id)
        session.add(project)
        session.flush()
        ids = {}
        for name, northing, easting in (("SYN-REF", 1000.0, 2000.0), ("SYN-OFF", 1006.0, 2008.0)):
            well = Well(name=name, code=name, project_id=project.id, northing=northing, easting=easting,
                        rte_msl=10.0)
            session.add(well)
            session.flush()
            ids[name] = well.id
            for md in (0.0, 300.0, 600.0, 900.0):
                session.add(SurveyPoint(well_id=well.id, md=md, inc=0.0, azi=0.0))
        nodatum = Well(name="SYN-NODATUM", code="SYN-NODATUM", project_id=project.id)
        session.add(nodatum)
        session.flush()
        ids["SYN-NODATUM"] = nodatum.id
        for md in (0.0, 500.0):
            session.add(SurveyPoint(well_id=nodatum.id, md=md, inc=0.0, azi=0.0))
    yield db, ids
    db.engine.dispose()


@pytest.fixture
def panel(app, synthetic):
    from tabs.trajectory_compare_panel import TrajectoryComparePanel
    widget = TrajectoryComparePanel(synthetic[0])
    widget.set_well(synthetic[1]["SYN-REF"])
    yield widget
    widget.cleanup()
    widget.deleteLater()
    app.processEvents()


def _select_offset(panel, well_id):
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("offset"))
    panel.offset_combo.setCurrentIndex(panel.offset_combo.findData(well_id))


def test_offset_list_excludes_the_selected_well(panel, synthetic):
    ids = [panel.offset_combo.itemData(i) for i in range(panel.offset_combo.count())]
    assert synthetic[1]["SYN-REF"] not in ids and synthetic[1]["SYN-OFF"] in ids


def test_unconfirmed_crs_is_not_assessed_and_nothing_can_be_saved(panel, synthetic):
    _select_offset(panel, synthetic[1]["SYN-OFF"])
    panel.crs_check.setChecked(False)
    panel.run()
    assert panel.wait_until_idle()
    assert panel.result.status == tc.NOT_ASSESSED and tc.NOT_ASSESSED in panel.status_label.text()
    assert any("CRS" in panel.reason_list.item(i).text() for i in range(panel.reason_list.count()))
    assert panel.table.rowCount() == 0 and not panel.save_button.isEnabled()
    assert panel.save() is None


def test_missing_datum_lists_the_reason(panel, synthetic):
    _select_offset(panel, synthetic[1]["SYN-NODATUM"])
    panel.crs_check.setChecked(True)
    panel.run()
    assert panel.wait_until_idle()
    reasons = [panel.reason_list.item(i).text() for i in range(panel.reason_list.count())]
    assert panel.result.status == tc.NOT_ASSESSED
    assert "offset well: northing is missing" in reasons and "offset well: rte_msl is missing" in reasons


def test_offset_comparison_runs_on_a_worker_and_saves_new_records(panel, synthetic, tmp_path):
    from core.database import TrajectoryCalculation
    _select_offset(panel, synthetic[1]["SYN-OFF"])
    panel.crs_check.setChecked(True)
    panel.run()
    assert panel._worker is not None or panel.result is not None
    assert panel.wait_until_idle()
    assert panel.result.status == tc.ASSESSED
    assert panel.result.closest["distance_m"] == pytest.approx(10.0, abs=0.01)
    assert tc.LABEL in panel.status_label.text() and panel.table.rowCount() == len(panel.result.rows)
    first, second = panel.save(), panel.save()
    assert first and second and first != second                  # a new record each time, never an update
    with synthetic[0].session_scope() as session:
        rows = session.query(TrajectoryCalculation).filter(TrajectoryCalculation.id.in_([first, second])).all()
        assert {r.description for r in rows} == {tc.LABEL}
        assert all(r.method == tc.METHOD_VERSION for r in rows)
        assert rows[0].results_json["closest"]["distance_m"] == pytest.approx(10.0, abs=0.01)
    out = tmp_path / "comparison.csv"
    assert panel.export_csv(str(out))
    lines = list(csv.reader(out.open(encoding="utf-8")))
    assert lines[0] == [f"# {tc.LABEL}"] and lines[2][2] == "Centre-to-centre (m)"
    assert len(lines) == 3 + len(panel.result.rows)


def test_plan_comparison_from_a_csv_file(panel, tmp_path):
    plan = tmp_path / "plan.csv"
    plan.write_text("MD (ft),Inc,Azi\n0,0,0\n3280.84,0,0\n", encoding="utf-8")
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("plan"))
    panel.plan_unit_combo.setCurrentIndex(panel.plan_unit_combo.findData("ft"))
    assert panel.load_plan(str(plan)) and "2 stations" in panel.plan_label.text()
    panel.run()
    assert panel.wait_until_idle()
    assert panel.result.status == tc.ASSESSED and panel.result.kind == "plan_vs_actual"
    assert all(abs(r["distance_m"]) < 0.01 for r in panel.result.rows)   # vertical well on a vertical plan
    assert panel.table.columnCount() == 7


def test_a_bad_plan_is_refused_and_no_comparison_runs(panel, tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("Depth,Something\n1,2\n3,4\n", encoding="utf-8")
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("plan"))
    assert not panel.load_plan(str(bad)) and "Plan refused" in panel.plan_label.text()
    panel.run()
    assert panel.result is None and "Load a plan file first" in panel.status_label.text()


def test_a_stale_result_is_dropped(panel):
    stale = tc.Comparison(status=tc.ASSESSED, rows=[{"reference_md": 1.0, "offset_md": 1.0, "distance_m": 0.1}],
                          closest={"reference_md": 1.0, "offset_md": 1.0, "distance_m": 0.1}, kind="well_to_well")
    panel._done(panel._token - 1, stale)
    assert panel.result is None and panel.table.rowCount() == 0


def test_a_read_error_is_a_state_not_an_empty_result(panel, monkeypatch):
    def broken(**_kwargs):
        raise OSError("synthetic read failure")
    monkeypatch.setattr(panel.db_manager, "load_survey_points", broken)
    panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("offset"))
    panel.run()
    assert panel.result is None and "could not be read (OSError)" in panel.status_label.text()


def test_the_viewer_has_the_compare_tab_and_follows_the_well(app, synthetic):
    from tabs.trajectory_viewer import TrajectoryViewerTab
    viewer = TrajectoryViewerTab(synthetic[0])
    try:
        titles = [viewer.view_tabs.tabText(i) for i in range(viewer.view_tabs.count())]
        assert "Compare / clearance" in titles
        viewer.set_context(synthetic[1]["SYN-OFF"])
        assert viewer.compare_panel.well_id == synthetic[1]["SYN-OFF"]
        ids = [viewer.compare_panel.offset_combo.itemData(i) for i in range(viewer.compare_panel.offset_combo.count())]
        assert synthetic[1]["SYN-OFF"] not in ids
    finally:
        viewer.compare_panel.cleanup()
        viewer.deleteLater()
        app.processEvents()
