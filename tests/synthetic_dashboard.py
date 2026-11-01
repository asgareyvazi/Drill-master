"""SYNTHETIC enrichment for the M53 dashboard (charts, cost, rigs).

Builds on :func:`synthetic_operations.build_synthetic_operations` and adds,
for SYN-DEV-01 only unless stated:

* rig names (SYN-RIG-A for DEV/QA, SYN-RIG-B for VERT/DONE) and target depths;
* one DrillingParameters row per report: depth_in = previous 24:00 depth,
  depth_out = 24:00 depth (300 m per day), hours_on_bottom 15 h, avg_rop 20
  m/h; bit "1" for reports 1-3, bit "2" for 4-6;
* one MudReport per report with MW 70.0 + report number (pcf, as stored);
* two extra NPT categories (report 4: 1.5 h "Wait on weather" replacing
  drilling time, so each day still logs 24 h);
* cost records in USD: Rig 100,000 planned / 90,000 actual, Mud 20,000 /
  30,000 (total 120,000 planned, 120,000 actual);
* SYN-QA-03: two cost records, one USD and one EUR (mixed currency);
* one saved MSE calculation for SYN-DEV-01 (mse_psi 25,000).

Hand-derived expectations are written next to the tests that use them.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from synthetic_operations import build_synthetic_operations


def build_dashboard_fixture(db, end_date):
    from core.database import (CostRecord, DailyReport, DrillingParameters, MSECalculationRecord, MudReport,
                               TimeLog24H, Well)
    ids = build_synthetic_operations(db, end_date=end_date)
    session = db.create_session()
    try:
        for key, rig, target in (("dev", "SYN-RIG-A", 2500.0), ("qa", "SYN-RIG-A", 1200.0),
                                 ("vert", "SYN-RIG-B", 900.0), ("done", "SYN-RIG-B", 950.0)):
            well = session.get(Well, ids[key])
            well.rig_name, well.target_depth = rig, target
        previous = 0.0
        for number in range(1, 7):
            report = session.get(DailyReport, ids["reports"][number])
            session.add(DrillingParameters(
                well_id=ids["dev"], report_id=report.id, report_date=report.report_date,
                bit_no="1" if number <= 3 else "2", depth_in=previous, depth_out=report.depth_2400,
                hours_on_bottom=15.0, avg_rop=20.0))
            session.add(MudReport(well_id=ids["dev"], report_id=report.id, report_date=report.report_date,
                                  mw=70.0 + number))
            previous = report.depth_2400
            if number == 4:
                drilling = (session.query(TimeLog24H).filter(TimeLog24H.report_id == report.id,
                                                             TimeLog24H.is_npt.is_(False)).one())
                drilling.duration -= 1.5
                session.add(TimeLog24H(report_id=report.id, time_from=time(20, 0), time_to=time(21, 30),
                                       duration=1.5, main_phase="DRILLING", main_code="NPT", is_npt=True,
                                       npt_category="Wait on weather", activity_description="SYNTHETIC wait"))
        for category, planned, actual in (("Rig", 100_000.0, 90_000.0), ("Mud", 20_000.0, 30_000.0)):
            session.add(CostRecord(well_id=ids["dev"], category=category, planned_cost=planned,
                                   actual_cost=actual, currency="USD",
                                   cost_date=end_date - timedelta(days=2), status="Approved"))
        for currency in ("USD", "EUR"):
            session.add(CostRecord(well_id=ids["qa"], category="Services", planned_cost=1000.0,
                                   actual_cost=500.0, currency=currency, cost_date=end_date - timedelta(days=9),
                                   status="Approved"))
        session.add(MSECalculationRecord(well_id=ids["dev"], label="SYNTHETIC MSE", method="Teale",
                                         snapshot_schema_version=1, input_snapshot_json={}, result_json={},
                                         mse_psi=25_000.0,
                                         created_at=datetime.combine(end_date, time(12, 0))))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return ids
