"""M48 synthetic multi-well / multi-bore fixture (temp in-memory DB only).

Every value below is invented. The golden numbers quoted in the tests are
derived BY HAND from this table, never by running the code under test.

Well A  "SYN-A" (no wellbores), reports A1..A6 on 2026-01-01..06
  depth_2400: 100, 150, 200, None, 260, 300
  DrillingParameters.avg_rop (linked by report_id):
    A1 0.0 | A2 10.0 | A3 None | A4 -3.0 | A5 8.0 (4 h) | A6 12.0 (2 h) + 6.0 (4 h)
  TimeLog24H:
    A1 24 h productive                       -> valid zero
    A2 2 h NPT "NPT-X" + 22 h productive     -> 2.0 h
    A3 12 h productive                       -> partial (50 %)
    A4 no rows                               -> missing
    A5 1.5 h NPT without code + 22.5 h prod. -> 1.5 h, "Unclassified (no NPT code)"
    A6 24 h productive                       -> valid zero
  CostRecord: USD actual 1000 / planned 1200, EUR actual 500  -> mixed currency
  no SafetyReport

Well B  "SYN-B", wellbores OH and ST1
  OH  B1 2026-01-01 depth 500 rop 5.0 | OH B2 2026-01-02 depth 600 rop 7.0
  ST1 B3 2026-01-02 depth 550 rop 20.0 | ST1 B4 2026-01-03 depth 700 rop 30.0
  legacy DrillingParameters 2026-01-01 rop 99.0 with report_id NULL
  every report: 1 h NPT "NPT-Y" + 23 h productive

Well C  "SYN-C", reports C1..C7 on 2026-02-01..07
  depth_2400 100 x i, avg_rop i (i = 1..7), each 1 h NPT "NPT-Z" + 23 h productive
  CostRecord USD actual 7000 / planned 6000
  SafetyReport 2026-02-07 days_without_lti 100
"""
from datetime import date, time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def build(db=None):
    """Populate ``db`` (an initialized DatabaseManager) or a new in-memory one."""
    from core.database import (Base, Company, CostRecord, DailyReport, DatabaseManager,
                               DrillingParameters, Project, SafetyReport, TimeLog24H, Well,
                               Wellbore)

    if db is None:
        db = DatabaseManager()
        db.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                                  poolclass=StaticPool)
        Base.metadata.create_all(db.engine)
        db.Session = sessionmaker(bind=db.engine, autoflush=False, autocommit=False)
    s = db.create_session()
    company = Company(name="SYN-M48", code="SYN-M48")
    s.add(company)
    s.flush()
    project = Project(name="SYN-M48-P", code="SYN-M48-P", company_id=company.id)
    s.add(project)
    s.flush()
    wa, wb, wc = (Well(name=f"SYN-{x}", code=f"SYN-M48-{x}", project_id=project.id) for x in "ABC")
    s.add_all([wa, wb, wc])
    s.flush()
    oh = Wellbore(well_id=wb.id, name="OH", wellbore_type="original")
    st = Wellbore(well_id=wb.id, name="ST1", wellbore_type="sidetrack")
    s.add_all([oh, st])
    s.flush()
    ids = {"A": wa.id, "B": wb.id, "C": wc.id, "OH": oh.id, "ST1": st.id}
    number = [0]

    def report(well, day, depth, bore=None):
        number[0] += 1
        r = DailyReport(well_id=well.id, wellbore_id=bore, report_number=number[0],
                        report_date=day, depth_2400=depth)
        s.add(r)
        s.flush()
        return r

    def log(rep, hours, npt=False, code=None, start=0):
        s.add(TimeLog24H(report_id=rep.id, time_from=time(start % 24), time_to=time(23, 59),
                         duration=hours, is_npt=npt, main_code=code))

    def rop(well, rep, value, hours=None, day=None):
        s.add(DrillingParameters(well_id=well.id, report_id=rep.id if rep else None,
                                 report_date=day or rep.report_date, avg_rop=value,
                                 hours_on_bottom=hours))

    # ---- Well A
    a = [report(wa, date(2026, 1, i + 1), d) for i, d in enumerate((100, 150, 200, None, 260, 300))]
    ids["A_reports"] = [r.id for r in a]
    rop(wa, a[0], 0.0)
    rop(wa, a[1], 10.0)
    rop(wa, a[2], None)
    rop(wa, a[3], -3.0)
    rop(wa, a[4], 8.0, 4.0)
    rop(wa, a[5], 12.0, 2.0)
    rop(wa, a[5], 6.0, 4.0)
    log(a[0], 24.0)
    log(a[1], 2.0, True, "NPT-X")
    log(a[1], 22.0, start=2)
    log(a[2], 12.0)
    log(a[4], 1.5, True, None)
    log(a[4], 22.5, start=2)
    log(a[5], 24.0)
    s.add_all([CostRecord(well_id=wa.id, category="Rig", currency="USD", actual_cost=1000.0,
                          planned_cost=1200.0),
               CostRecord(well_id=wa.id, category="Mud", currency="EUR", actual_cost=500.0)])

    # ---- Well B (two bores, same-date sidetrack, legacy row)
    b1 = report(wb, date(2026, 1, 1), 500, oh.id)
    b2 = report(wb, date(2026, 1, 2), 600, oh.id)
    b3 = report(wb, date(2026, 1, 2), 550, st.id)
    b4 = report(wb, date(2026, 1, 3), 700, st.id)
    ids["B_reports"] = [b1.id, b2.id, b3.id, b4.id]
    for rep, value in ((b1, 5.0), (b2, 7.0), (b3, 20.0), (b4, 30.0)):
        rop(wb, rep, value)
        log(rep, 1.0, True, "NPT-Y")
        log(rep, 23.0, start=1)
    rop(wb, None, 99.0, day=date(2026, 1, 1))

    # ---- Well C (complete, assessable)
    c = [report(wc, date(2026, 2, i), 100.0 * i) for i in range(1, 8)]
    ids["C_reports"] = [r.id for r in c]
    for i, rep in enumerate(c, start=1):
        rop(wc, rep, float(i))
        log(rep, 1.0, True, "NPT-Z")
        log(rep, 23.0, start=1)
    s.add(CostRecord(well_id=wc.id, category="Rig", currency="USD", actual_cost=7000.0,
                     planned_cost=6000.0))
    s.add(SafetyReport(well_id=wc.id, report_date=date(2026, 2, 7), days_without_lti=100))
    s.commit()
    s.close()
    return db, ids
