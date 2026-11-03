#!/usr/bin/env python3
"""M103 "measure first": how long the reads moved off the GUI thread take on a year of SYNTHETIC data.

Builds a temporary file database (one well, ``--days`` daily reports with 12 time-log rows each, one
drilling-parameter row and one cost record per day, 200 calculation-history entries) and reports the
median of ``--repeat`` runs of:

* ``operational_analysis.analyze`` (W12 Operational Analysis refresh),
* ``calculation_history.load_history`` (Calculation History list).

Trajectory comparison already ran in a worker before M103 (``FunctionWorker``); it is not measured here.

Prints JSON. Nothing is written outside the temporary directory. Linux, CPython; timings are
environment-specific and serve only to decide what must not run on the GUI thread (budget 100 ms).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from datetime import date, time as dtime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

GUI_BUDGET_S = 0.100


def _build(db, days: int) -> dict:
    from core.database import CalculationCase, CostRecord, DailyReport, DrillingParameters, TimeLog24H
    from document_link_fixtures import build_link_world

    ids = build_link_world(db)
    well = ids["alpha"]
    start = date(2031, 1, 1)
    with db.session_scope() as session:
        for day in range(days):
            depth = 500.0 + day * 20.0
            report = DailyReport(well_id=well, report_date=start + timedelta(days=day), report_number=100 + day,
                                 depth_0000=depth, depth_2400=depth + 20.0, summary=f"SYN day {day}")
            session.add(report)
            session.flush()
            for hour in range(12):
                session.add(TimeLog24H(report_id=report.id, time_from=dtime(hour * 2, 0),
                                       time_to=dtime(hour * 2 + 1, 59), duration=2.0, main_phase="DRILLING",
                                       main_code="NPT" if hour == 11 else "DRL", is_npt=hour == 11,
                                       npt_category="Rig repair" if hour == 11 else None,
                                       activity_description=f"SYN activity {hour}"))
            session.add(DrillingParameters(well_id=well, report_id=report.id, report_date=report.report_date,
                                           bit_no=f"SYN-{1 + day // 30}", depth_in=depth, depth_out=depth + 20.0,
                                           hours_on_bottom=10.0, wob_min=8.0, wob_max=12.0))
            session.add(CostRecord(well_id=well, category="Rig", description=f"SYN cost {day}", actual_cost=1000.0,
                                   currency="USD", cost_date=start + timedelta(days=day)))
        for n in range(200):
            session.add(CalculationCase(well_id=well, calculator="Quick Calc", name=f"SYN case {n}",
                                        method="SYN method", method_version="1", inputs={"a": n}, results={"r": n}))
    return ids


def _median(fn, repeat: int) -> float:
    samples = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    return statistics.median(samples)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args(argv)

    from core import calculation_history as ch
    from core import analysis_evidence as ev
    from core import operational_analysis as oa
    from synthetic_operations import make_file_database

    with tempfile.TemporaryDirectory() as tmp:
        db = make_file_database(Path(tmp) / "m103_measure.db")
        t0 = time.perf_counter()
        ids = _build(db, args.days)
        build_s = time.perf_counter() - t0
        scope = ev.AnalysisScope(well_id=ids["alpha"])
        timings = {
            "operational_analysis.analyze": _median(lambda: oa.analyze(db, scope), args.repeat),
            "calculation_history.load_history": _median(lambda: ch.load_history(db, well_id=ids["alpha"]),
                                                        args.repeat),
        }
        db.engine.dispose()
    out = {"days": args.days, "time_log_rows": args.days * 12, "repeat": args.repeat,
           "build_s": round(build_s, 3), "gui_budget_s": GUI_BUDGET_S,
           "median_s": {k: round(v, 4) for k, v in timings.items()},
           "over_budget": sorted(k for k, v in timings.items() if v > GUI_BUDGET_S),
           "environment": f"{sys.platform} CPython {sys.version.split()[0]}"}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
