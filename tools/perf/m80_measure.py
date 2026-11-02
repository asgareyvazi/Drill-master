#!/usr/bin/env python3
"""M80 measurements on a SYNTHETIC temporary database (never a user database).

Measures the M72-M74 paths a user waits on: history count + first page
versus loading everything, saving a 2000-station survey revision, saving an
architecture revision, and the build-hold solver. Prints JSON; timings are
for the machine that ran it and are evidence, not a gate.

    python tools/perf/m80_measure.py [--cases 3000]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def _timed(fn, repeat: int = 5) -> dict:
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    return {"median_ms": round(statistics.median(samples), 2), "max_ms": round(max(samples), 2), "runs": repeat}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, default=3000)
    args = parser.parse_args(argv)
    os.environ.setdefault("DRILLMASTER_AI_IMPORT", "0")
    from synthetic_operations import make_file_database

    from core import calculation_cases as cc
    from core import calculation_history as ch
    from core import survey_revisions as sr
    from core import well_architecture as wa
    from core.database import Company, Project, Well
    from core.well_plan_designer import solve_build_hold
    from test_m74_well_architecture import ARCH

    db = make_file_database(Path(tempfile.mkdtemp(prefix="m80-perf-")) / "perf.db")
    with db.session_scope() as session:
        company = Company(name="SYN CO", code="SYN")
        session.add(company)
        session.flush()
        project = Project(name="SYN FIELD", code="SYNF", company_id=company.id)
        session.add(project)
        session.flush()
        well = Well(name="SYN-P-01", code="SYN-P-01", project_id=project.id)
        session.add(well)
        session.flush()
        well_id = well.id
    for i in range(args.cases):
        cc.save_case(db, calculator="x", name=f"SYN perf {i}", inputs={"a": i}, results={"r": i}, well_id=well_id)
    stations = [{"md": float(i), "inc": min(i / 40.0, 60.0), "azi": 135.0} for i in range(0, 20000, 10)]
    out = {
        "machine": {"python": platform.python_version(), "platform": platform.platform(), "cpus": os.cpu_count()},
        "cases": args.cases,
        "history_full_load": _timed(lambda: ch.load_history(db, well_id=well_id)),
        "history_count_and_first_page": _timed(lambda: (ch.count_history(db, well_id=well_id),
                                                        ch.load_history(db, well_id=well_id, limit=200))),
        "survey_revision_save_2000_stations": _timed(
            lambda: sr.save_revision(db, well_id, stations, depth_datum="RKB", azimuth_reference="true"), repeat=3),
        "architecture_revision_save": _timed(lambda: wa.save_revision(db, well_id, ARCH)),
        "build_hold_solver_x1000": _timed(lambda: [solve_build_hold(
            {"north": -300.0, "east": 300.0, "tvd": 1400.0}, kop_md=500.0, dls=3.0) for _ in range(1000)], repeat=3),
    }
    db.engine.dispose()
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
