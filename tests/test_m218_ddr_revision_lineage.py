"""M218: DDR -> analysis lineage - a later DDR revision never alters what was saved from the earlier data.

* the report revision snapshot taken at submit (``transition_report``) survives later DDR edits, a carry-forward
  and a re-opened day, and it is immutable for EVERY writer (the ORM policy applied to enforced sessions only):
  UPDATE, REPLACE INTO, INSERT OR REPLACE and ON CONFLICT DO UPDATE are refused, with ``recursive_triggers`` OFF
  and ON. Deleting the report (or its well) still deletes its revisions.
* a trajectory view saved from the DDR survey stations keeps its stored snapshot after a station is corrected; the
  drift check reports the difference instead of redrawing.
* a calculation case built from DDR values keeps its inputs after the DDR changes.

Synthetic data on a fresh file database; raw ``sqlite3`` connections for the adversarial writers.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date

import pytest

from core.database import DailyReport, MudReport, ReportRevision, Section, SurveyPoint, User, Well
from synthetic_operations import make_file_database

ENG = lambda p: p in {"can_edit_reports", "can_export"}                                   # noqa: E731
SUP = lambda p: p in {"can_edit_reports", "can_approve_reports", "can_export"}           # noqa: E731


@pytest.fixture
def world(tmp_path):
    db = make_file_database(tmp_path / "m218.db")
    with db.session_scope() as s:
        from core.database import Project
        project = s.query(Project).first()
        eng = User(username="m218-eng", password_hash="x", role="engineer")
        sup = User(username="m218-sup", password_hash="x", role="supervisor")
        well = Well(project_id=project.id, name="M218", code="M218")
        s.add_all([eng, sup, well])
        s.flush()
        section = Section(well_id=well.id, name="12.25")
        s.add(section)
        s.flush()
        report = DailyReport(well_id=well.id, section_id=section.id, report_number=1, report_date=date(2026, 9, 1),
                             status="Draft", summary="first", depth_2400=1300.0)
        s.add(report)
        s.flush()
        s.add_all([MudReport(well_id=well.id, report_id=report.id, report_date=date(2026, 9, 1), mw=1.20)]
                  + [SurveyPoint(well_id=well.id, report_id=report.id, md=md, inc=inc, azi=90.0)
                     for md, inc in ((0.0, 0.0), (500.0, 5.0), (1000.0, 12.0))])
        ids = {"eng": eng.id, "sup": sup.id, "well": well.id, "section": section.id, "report": report.id}
    result = db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
    assert result.ok, result
    yield db, ids
    db.engine.dispose()


def _revision(db, report_id):
    with db.session_scope() as s:
        row = s.query(ReportRevision).filter_by(report_id=report_id).order_by(ReportRevision.id).first()
        return row.id, json.dumps(row.snapshot, sort_keys=True, default=str), row.status


def test_later_ddr_revisions_never_change_the_submitted_snapshot(world):
    db, ids = world
    rev_id, before, status = _revision(db, ids["report"])
    assert status == "Submitted" and '"mw": 1.2' in before and '"summary": "first"' in before
    assert db.transition_report(ids["report"], "reject", has_permission=SUP, user_id=ids["sup"],
                                comment="re-check mud").ok
    db.save_daily_report({"id": ids["report"], "summary": "second"})        # rejected -> editable
    with db.session_scope() as s:
        s.query(MudReport).filter_by(report_id=ids["report"]).one().mw = 1.35
    assert _revision(db, ids["report"]) == (rev_id, before, "Submitted")
    revisions = db.get_report_revisions(ids["report"])
    assert len(revisions) == 2 and revisions[-1]["snapshot"]["report"]["summary"] == "first"


@pytest.mark.parametrize("recursive", ["OFF", "ON"])
@pytest.mark.parametrize("statement", [
    "UPDATE report_revisions SET snapshot = '{}' WHERE id = :id",
    "UPDATE report_revisions SET status = 'Approved' WHERE id = :id",
    "UPDATE report_revisions SET comment = 'rewritten' WHERE id = :id",
    "UPDATE report_revisions SET report_id = report_id, revision_no = revision_no + 1 WHERE id = :id",
    "REPLACE INTO report_revisions (id, report_id, revision_no, status, snapshot, created_at) "
    "VALUES (:id, :report, 1, 'Submitted', '{}', '2026-01-01')",
    "INSERT OR REPLACE INTO report_revisions (id, report_id, revision_no, status, snapshot, created_at) "
    "VALUES (:id, :report, 1, 'Submitted', '{}', '2026-01-01')",
    "INSERT INTO report_revisions (id, report_id, revision_no, status, snapshot, created_at) "
    "VALUES (:id, :report, 1, 'Submitted', '{}', '2026-01-01') ON CONFLICT(id) DO UPDATE SET snapshot = '{}'",
])
def test_every_raw_writer_is_refused(world, statement, recursive):
    db, ids = world
    rev_id, before, _ = _revision(db, ids["report"])
    with sqlite3.connect(db.db_path) as raw:
        raw.execute(f"PRAGMA recursive_triggers = {recursive}")
        with pytest.raises(sqlite3.DatabaseError, match="report_revisions"):
            raw.execute(statement, {"id": rev_id, "report": ids["report"]})
    assert _revision(db, ids["report"])[:2] == (rev_id, before)


def test_an_unenforced_orm_session_cannot_rewrite_a_snapshot(world):
    from sqlalchemy.exc import DatabaseError
    db, ids = world
    rev_id, before, _ = _revision(db, ids["report"])
    with pytest.raises(DatabaseError, match="immutable"):
        with db.session_scope() as s:
            s.get(ReportRevision, rev_id).snapshot = {"report": {"summary": "forged"}}
    with pytest.raises(DatabaseError, match="immutable"):
        with db.session_scope() as s:
            s.query(ReportRevision).filter_by(id=rev_id).update({"status": "Approved"})
    assert _revision(db, ids["report"])[:2] == (rev_id, before)


def test_new_revisions_and_report_and_well_deletion_still_work(world):
    db, ids = world
    assert db.transition_report(ids["report"], "approve", has_permission=SUP, user_id=ids["sup"],
                                comment="ok").ok
    assert len(db.get_report_revisions(ids["report"])) == 2
    assert db.delete_daily_report(ids["report"])
    with db.session_scope() as s:
        assert s.query(ReportRevision).count() == 0
        report = DailyReport(well_id=ids["well"], section_id=ids["section"], report_number=2,
                             report_date=date(2026, 9, 2), status="Draft", summary="day 2")
        s.add(report)
        s.flush()
        report_id = report.id
    assert db.transition_report(report_id, "submit", has_permission=ENG, user_id=ids["eng"]).ok
    assert db.delete_well(ids["well"])
    with db.session_scope() as s:
        assert s.query(ReportRevision).count() == 0


def test_a_saved_trajectory_view_keeps_its_snapshot_after_a_station_is_corrected(world):
    from core import trajectory_views as tv
    db, ids = world
    view = tv.save_view(db, ids["well"], "M218 view", {"scope": "report"}, report_id=ids["report"])
    stored = tv.get_view(db, view["id"])
    assert tv.drift(db, stored).state == tv.MATCH
    with db.session_scope() as s:                                         # the DDR station is corrected
        s.query(SurveyPoint).filter_by(report_id=ids["report"], md=1000.0).one().inc = 13.0
    again = tv.get_view(db, view["id"])
    assert again["stations"] == stored["stations"] and again["stations_sha256"] == stored["stations_sha256"]
    assert again["integrity"] == "VERIFIED"
    assert tv.drift(db, again).state == tv.DIFFERENT


def test_a_calculation_case_built_from_ddr_values_keeps_its_inputs(world):
    from core import calculation_cases as cc
    db, ids = world
    with db.session_scope() as s:
        mw = s.query(MudReport).filter_by(report_id=ids["report"]).one().mw
    case = cc.save_case(db, calculator="Hydraulics", name="M218 from DDR", well_id=ids["well"],
                        inputs={"mw": {"value": mw, "label": f"MW from report {ids['report']}"}},
                        results={"ecd": {"value": 1.31}})
    with db.session_scope() as s:
        s.query(MudReport).filter_by(report_id=ids["report"]).one().mw = 1.50
    assert cc.get_case(db, case["id"])["inputs"]["mw"]["value"] == 1.20
