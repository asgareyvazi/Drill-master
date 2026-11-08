"""A database created with NOT NULL survey angles still imports an incomplete station for review.

The post-M140 lint review removed an unused schema probe from the atomic import whose comment promised a separate
legacy path. The real guarantee is ``_migrate_nullable_contracts`` (run by ``initialize``); this pins the chain end to
end on a synthetic database.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from core.database import Company, DatabaseManager, Project, SurveyPoint, Well


def _angle_columns(path):
    sql = sqlite3.connect(path).execute("SELECT sql FROM sqlite_master WHERE name='survey_points'").fetchone()[0]
    return sorted(part.strip() for part in sql.split(",") if part.strip().startswith(("inc ", "azi ")))


def test_not_null_angles_are_relaxed_and_the_incomplete_row_is_kept_for_review(tmp_path):
    path = str(tmp_path / "legacy.db")
    db = DatabaseManager()
    db.db_path = path
    db.initialize()
    with db.session_scope() as s:
        company = Company(name="SYN", code="S1")
        s.add(company)
        s.flush()
        project = Project(company_id=company.id, name="SYN P", code="P1")
        s.add(project)
        s.flush()
        well = Well(project_id=project.id, name="SYN-W", code="W1")
        s.add(well)
        s.flush()
        well_id = well.id
    report_id = db.save_daily_report({"well_id": well_id, "report_date": date(2026, 5, 2), "report_number": 1,
                                      "status": "Draft"})["id"]
    db.close()

    con = sqlite3.connect(path)
    sql = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='survey_points'").fetchone()[0]
    legacy = sql.replace("inc FLOAT,", "inc FLOAT NOT NULL,").replace("azi FLOAT,", "azi FLOAT NOT NULL,")
    assert legacy != sql
    extras = [r[0] for r in con.execute("SELECT sql FROM sqlite_master WHERE tbl_name='survey_points' "
                                         "AND type IN ('index','trigger') AND sql IS NOT NULL")]
    con.executescript("PRAGMA foreign_keys=OFF; ALTER TABLE survey_points RENAME TO sp_old; " + legacy
                      + "; DROP TABLE sp_old;" + ";".join(extras) + ";")
    con.commit()
    con.close()
    assert _angle_columns(path) == ["azi FLOAT NOT NULL", "inc FLOAT NOT NULL"]

    db = DatabaseManager()
    db.db_path = path
    db.initialize()
    try:
        assert _angle_columns(path) == ["azi FLOAT", "inc FLOAT"]
        result = db.save_imported_multi_tab_data_atomic(well_id, report_id, {"surveys": [
            {"md": 100.0, "inc": None, "azi": None}, {"md": 200.0, "inc": 1.0, "azi": 10.0}]})
        assert (result["surveys"], result["survey_rejected"], result["survey_review"]) == (2, 0, 1)
        assert result["status"] == "REVIEW_REQUIRED"
        with db.session_scope() as s:
            stored = sorted((p.md, p.inc, p.azi) for p in s.query(SurveyPoint).filter(SurveyPoint.report_id == report_id))
        assert stored == [(100.0, None, None), (200.0, 1.0, 10.0)]   # never 0, never dropped silently
    finally:
        db.close()
