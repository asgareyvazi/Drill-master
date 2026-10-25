"""M46: the survey editor shows exactly the scope its Save writes.

With a well selected and no daily report, ``SurveyDataTab.load_data`` used
to list the survey rows of EVERY report of the well.  Their stored derived
columns (TVD/N/E/VS) are per-report frames that restart at N = E = 0, so
the table mixed frames under the "Calculated using Minimum Curvature"
highlight, and Save (scope ``(well, None)``) was refused because those rows
belong to reports.  SYNTHETIC data only.
"""
from datetime import date

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from core.database import Company, DailyReport, Project, Well  # noqa: E402
from document_link_fixtures import without_session_user  # noqa: E402
from test_scope_attribution import _mgr  # noqa: E402


def _rows(well_id, report_id, mds):
    return [{"well_id": well_id, "report_id": report_id, "md": md, "inc": 10.0, "azi": 45.0} for md in mds]


@pytest.fixture
def world():
    QApplication.instance() or QApplication([])
    with without_session_user():
        db = _mgr()
        s = db.create_session()
        company = Company(name="SYNTHETIC SCOPE CO", code="SYN-SCO")
        s.add(company)
        s.flush()
        project = Project(name="SYNTHETIC SCOPE PROJECT", code="SYN-SCP", company_id=company.id)
        s.add(project)
        s.flush()
        well = Well(name="SYN-SCOPE-01", code="SYN-SC1", project_id=project.id)
        s.add(well)
        s.flush()
        r1 = DailyReport(well_id=well.id, report_date=date(2026, 3, 1), report_number=1)
        r2 = DailyReport(well_id=well.id, report_date=date(2026, 3, 2), report_number=2)
        s.add_all([r1, r2])
        s.commit()
        w, a, b = well.id, r1.id, r2.id
        s.close()
        assert db.save_survey_records(_rows(w, a, (100.0, 200.0)), replace_scope=(w, a))["rejected"] == 0
        assert db.save_survey_records(_rows(w, b, (200.0, 300.0)), replace_scope=(w, b))["rejected"] == 0
        assert db.save_survey_records(_rows(w, None, (50.0,)), replace_scope=(w, None))["rejected"] == 0
        yield db, (w, a, b)


def _mds(tab):
    return [float(tab.survey_table.item(r, 1).text()) for r in range(tab.survey_table.rowCount())]


def test_without_a_report_only_well_level_rows_are_listed(world, monkeypatch):
    from tabs.w6_Trajectory_Widget import SurveyDataTab
    db, (well, r1, r2) = world
    tab = SurveyDataTab(db)
    tab.current_well_id, tab.current_report_id = well, None
    tab.load_data()
    assert _mds(tab) == [50.0]                       # not 50, 100, 200, 200, 300 from three frames
    tab.current_report_id = r1
    tab.load_data()
    assert _mds(tab) == [100.0, 200.0]
    tab.current_report_id = r2
    tab.load_data()
    assert _mds(tab) == [200.0, 300.0]


def test_well_scope_save_round_trips_without_touching_report_rows(world, monkeypatch):
    from tabs.w6_Trajectory_Widget import SurveyDataTab
    db, (well, r1, r2) = world
    for name in ("warning", "critical", "information"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: QMessageBox.Ok)
    tab = SurveyDataTab(db)
    tab.current_well_id, tab.current_report_id = well, None
    tab.load_data()
    assert tab.save_data() is not False              # v1: refused - rows of reports in a well-level snapshot
    assert [p["md"] for p in db.load_survey_points(report_id=r1)] == [100.0, 200.0]
    assert [p["md"] for p in db.load_survey_points(report_id=r2)] == [200.0, 300.0]
    assert [p["md"] for p in db.load_survey_points(well_id=well) if p["report_id"] is None] == [50.0]
