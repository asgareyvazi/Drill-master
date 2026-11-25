#!/usr/bin/env python3
"""M468: EOWR source-data sections — scale benchmark (SYNTHETIC).

Builds a synthetic well with ``days`` daily reports and, per day, ``logs`` 24-hour time logs, ``logs // 4`` morning
logs, one bit-report snapshot with ``bits`` records, one BHA with ``components`` components, one material request
and one equipment log; plus a second well with the same shape that must never leak in. It then generates the EOWR
(HTML and Excel) and checks the rendered row counts against counts computed HERE from the generator parameters
(independent of the engine), the chronological order of the time-log rows and well isolation. Timings are measured
values for this machine (they are reported, not byte-compared).

Usage::

    PYTHONPATH=.:tests python tools/quality/benchmark_m468_eowr.py [--days 60] [--logs 24] [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import date, time as dtime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]


def build(db, days: int, logs: int, bits: int, components: int) -> dict:
    from sqlalchemy import text
    from core.database import (BHAReport, BitReport, DailyReport, EquipmentLog, MaterialRequest, TimeLog24H,
                               TimeLogMorning)
    wells = {}
    with db.session_scope() as s:
        q = s.execute
        q(text("INSERT INTO companies(name, code) VALUES ('SYN M468', 'M468')"))
        company = q(text("SELECT id FROM companies WHERE code='M468'")).scalar()
        q(text("INSERT INTO projects(company_id, name, code) VALUES (:c, 'SYN M468', 'M468P')"), {"c": company})
        project = q(text("SELECT id FROM projects WHERE code='M468P'")).scalar()
        for code in ("A", "B"):
            q(text("INSERT INTO wells(project_id, name, code) VALUES (:p, :n, :c)"),
              {"p": project, "n": f"SYN-M468-{code}", "c": f"M468{code}"})
            well = q(text("SELECT id FROM wells WHERE code=:c"), {"c": f"M468{code}"}).scalar()
            wells[code] = well
            minutes = 24 * 60 // logs
            for d in range(days):
                day = date(2026, 1, 1) + timedelta(days=d)
                rep = DailyReport(well_id=well, report_date=day, report_number=d + 1)
                s.add(rep)
                s.flush()
                # inserted in reverse time order: the report must sort them
                for i in reversed(range(logs)):
                    start = i * minutes
                    s.add(TimeLog24H(report_id=rep.id, time_from=dtime(start // 60, start % 60),
                                     time_to=dtime(((start + minutes) // 60) % 24, (start + minutes) % 60),
                                     duration=minutes / 60.0, activity_description=f"SYN-{code} d{d:03d} l{i:03d}"))
                for i in range(logs // 4):
                    s.add(TimeLogMorning(report_id=rep.id, time_from=dtime(i % 24, 0), time_to=dtime(i % 24, 30),
                                         duration=0.5, activity_description=f"SYN-{code} tour"))
                s.add(BitReport(well_id=well, report_id=rep.id, report_date=day, report_name=f"SYN {d}",
                                bit_records_json=json.dumps([{"Bit No": f"SYN-{code}-{d}-{b}", "Size (in)": "8.5"}
                                                             for b in range(bits)])))
                s.add(BHAReport(well_id=well, report_id=rep.id, bha_name=f"SYN BHA {d}",
                                bha_data_json=[{"Component Name": f"SYN-{code} c{c}", "Length (m)": "9.1"}
                                               for c in range(components)]))
                s.add(MaterialRequest(well_id=well, report_id=rep.id, request_date=day,
                                      requested_items=f"SYN-{code} item {d}", requested_quantity=1.0))
                s.add(EquipmentLog(well_id=well, report_id=rep.id, equipment_name=f"SYN-{code} eq {d}",
                                   service_date=day))
    return wells


def run(days: int = 60, logs: int = 24, bits: int = 3, components: int = 12) -> dict:
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from openpyxl import load_workbook
    from core import report_engine as engines
    from synthetic_operations import make_file_database

    expected = {"12. Bit records": days * bits, "13. BHA components": days * components,
                "14. 24-hour time logs": days * logs, "15. Morning tour time logs": days * (logs // 4),
                "16. Material requests": days, "17. Equipment logs": days}
    with tempfile.TemporaryDirectory() as tmp:
        db = make_file_database(Path(tmp) / "m468.db")
        t0 = time.perf_counter()
        wells = build(db, days, logs, bits, components)
        seed_s = time.perf_counter() - t0
        engine = engines.EOWRReportEngine(db)
        out = Path(tmp) / "eowr.html"
        t0 = time.perf_counter()
        ok = engine.generate(wells["A"], str(out), "html")
        html_s = time.perf_counter() - t0
        text = out.read_text(encoding="utf-8") if ok else ""
        got = {e["section"]: e["rows"] for e in engine.last_provenance["sections"] if e["section"] in expected}
        body = text.split("<h1>14. 24-hour time logs</h1>")[1].split("<h1>15.")[0] if ok else ""
        marks = [f"SYN-A d{d:03d} l{i:03d}" for d in (0, days - 1) for i in (0, logs - 1)]
        chronological = all(m in body for m in marks) and [body.index(m) for m in marks] == sorted(
            body.index(m) for m in marks)
        xlsx = Path(tmp) / "eowr.xlsx"
        t0 = time.perf_counter()
        ok_x = engine.generate(wells["A"], str(xlsx), "excel")
        xlsx_s = time.perf_counter() - t0
        wb = load_workbook(xlsx, read_only=True)
        sheet_rows = wb["TimeLog24H"].max_row - 1
        wb.close()
        db.engine.dispose()
    checks = {
        "html_generated": ok, "excel_generated": ok_x,
        "row_counts_match_generator": got == expected,
        "time_logs_chronological": chronological,
        "no_other_well_rows": "SYN-B" not in text,
        "excel_time_log_rows": sheet_rows == expected["14. 24-hour time logs"],
    }
    return {"parameters": {"days": days, "logs_per_day": logs, "bits_per_snapshot": bits,
                           "bha_components": components},
            "expected_rows": expected, "rendered_rows": got, "checks": checks, "passed": all(checks.values()),
            "seconds": {"seed": round(seed_s, 2), "eowr_html": round(html_s, 2), "eowr_excel": round(xlsx_s, 2)},
            "html_bytes": len(text.encode("utf-8"))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--logs", type=int, default=24)
    ap.add_argument("--json")
    args = ap.parse_args(argv)
    result = run(args.days, args.logs)
    print(json.dumps(result, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
