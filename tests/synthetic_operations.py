"""Deterministic SYNTHETIC operations dataset (M44).

Every name is prefixed ``SYN-`` / ``SYNTHETIC`` and no value comes from a real
well or report.  Used by the dashboard, trajectory and document tests and by
``tools/screenshots/capture_m44.py``.  Never point it at an operational DB.

Wells
-----
SYN-DEV-01   Drilling. Six consecutive reports; directional J profile
             (vertical to 600 m, build 2 deg/30 m at azimuth 135 deg to 40 deg,
             hold to 1800 m).  Each report repeats the previous report's last
             station, exactly like real DDR survey tables.  NPT on two days.
SYN-VERT-02  Planning. No reports.
SYN-QA-03    Drilling. Two old reports: the latest has no reported depth,
             a conflicting repeated station and a station without azimuth.
SYN-DONE-04  Completed. One report.
"""
from __future__ import annotations

from datetime import date, time, timedelta

COMPANY = "SYNTHETIC DEMO CO (not real data)"
PROJECT = "SYNTHETIC FIELD"
KOP_M, BUILD_PER_30M, HOLD_INC, AZIMUTH = 600.0, 2.0, 40.0, 135.0


def j_profile_inclination(md: float) -> float:
    if md <= KOP_M:
        return 0.0
    return min(HOLD_INC, (md - KOP_M) / 30.0 * BUILD_PER_30M)


def _stations(md_from: float, md_to: float, step: float = 30.0):
    md = md_from
    while md <= md_to + 1e-9:
        yield {"md": round(md, 2), "inc": round(j_profile_inclination(md), 4), "azi": AZIMUTH}
        md += step


def build_synthetic_operations(db, end_date: date = date(2026, 1, 15)) -> dict:
    """Populate an initialized DatabaseManager; return the created ids."""
    from core.database import Company, DailyReport, Project, Section, TimeLog24H, Well

    ids: dict = {"reports": {}}
    session = db.create_session()
    try:
        company = Company(name=COMPANY, code="SYN")
        session.add(company)
        session.flush()
        project = Project(name=PROJECT, code="SYNF", company_id=company.id)
        session.add(project)
        session.flush()

        def well(name, status, well_type):
            row = Well(name=name, code=name, project_id=project.id, status=status, well_type=well_type)
            session.add(row)
            session.flush()
            return row

        dev = well("SYN-DEV-01", "Drilling", "Directional")
        vert = well("SYN-VERT-02", "Planning", "Vertical")
        qa = well("SYN-QA-03", "Drilling", "Vertical")
        done = well("SYN-DONE-04", "Completed", "Vertical")
        ids.update(dev=dev.id, vert=vert.id, qa=qa.id, done=done.id, company=company.id, project=project.id)

        top = Section(name="SYN 17-1/2 in", well_id=dev.id)
        mid = Section(name="SYN 12-1/4 in", well_id=dev.id)
        qa_section = Section(name="SYN 8-1/2 in", well_id=qa.id)
        done_section = Section(name="SYN 6 in", well_id=done.id)
        session.add_all([top, mid, qa_section, done_section])
        session.flush()

        depths = [300.0, 600.0, 900.0, 1200.0, 1500.0, 1800.0]
        npt_hours = {3: 3.5, 5: 2.0}
        for number, depth in enumerate(depths, 1):
            report = DailyReport(
                well_id=dev.id, section_id=(top if number <= 2 else mid).id,
                report_date=end_date - timedelta(days=len(depths) - number), report_number=number,
                rig_day=number, depth_0000=depths[number - 2] if number > 1 else 0.0, depth_2400=depth,
                summary=f"SYNTHETIC day {number}: drilled to {depth:.0f} m", status="Submitted")
            session.add(report)
            session.flush()
            ids["reports"][number] = report.id
            npt = npt_hours.get(number, 0.0)
            session.add(TimeLog24H(report_id=report.id, time_from=time(0, 0), time_to=time(18, 0),
                                   duration=24.0 - npt, main_phase="DRILLING", main_code="DRL",
                                   is_npt=False, activity_description="SYNTHETIC drilling"))
            if npt:
                session.add(TimeLog24H(report_id=report.id, time_from=time(18, 0), time_to=time(23, 59),
                                       duration=npt, main_phase="DRILLING", main_code="NPT", is_npt=True,
                                       npt_category="Rig repair", activity_description="SYNTHETIC repair"))

        qa_reports = []
        for number, depth in ((1, 200.0), (2, None)):
            report = DailyReport(well_id=qa.id, section_id=qa_section.id,
                                 report_date=end_date - timedelta(days=10 - number), report_number=number,
                                 depth_2400=depth, summary="SYNTHETIC QA report", status="Draft")
            session.add(report)
            session.flush()
            qa_reports.append(report.id)
        ids["qa_reports"] = qa_reports
        done_report = DailyReport(well_id=done.id, section_id=done_section.id,
                                  report_date=end_date - timedelta(days=30), report_number=1,
                                  depth_2400=950.0, summary="SYNTHETIC final report", status="Approved")
        session.add(done_report)
        session.flush()
        ids["done_report"] = done_report.id
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    previous = 0.0
    for number, depth in enumerate(depths, 1):
        report_id = ids["reports"][number]
        rows = [dict(row, well_id=ids["dev"], report_id=report_id, tool="MWD")
                for row in _stations(previous, depth)]
        db.save_survey_records(rows, replace_scope=(ids["dev"], report_id))
        previous = depth

    first, second = ids["qa_reports"]
    db.save_survey_records([{"md": md, "inc": inc, "azi": 10.0, "well_id": ids["qa"], "report_id": first}
                            for md, inc in ((0.0, 0.0), (100.0, 0.5), (200.0, 1.0))],
                           replace_scope=(ids["qa"], first))
    db.save_survey_records([
        {"md": 200.0, "inc": 3.0, "azi": 10.0, "well_id": ids["qa"], "report_id": second},   # conflicts
        {"md": 300.0, "inc": 1.5, "azi": None, "well_id": ids["qa"], "report_id": second},   # no azimuth
    ], replace_scope=(ids["qa"], second))
    return ids


def make_file_database(path):
    """A fresh initialized file DatabaseManager at ``path`` (test credentials)."""
    from core.database import DatabaseManager

    db = DatabaseManager(bootstrap_passwords={"admin": "Synthetic-Admin-1!", "engineer": "Synthetic-Eng-1!",
                                              "viewer": "Synthetic-View-1!"})
    db.db_path = str(path)
    assert db.initialize(), db.last_diagnostic
    return db
