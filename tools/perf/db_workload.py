"""Reproducible synthetic database workload (about 500 daily reports).

Builds an isolated temporary database with deterministic synthetic data (fixed
seed, no real operational values), then times the application's own data-access
methods and records the SQLite query plan of every statement they emit.

    python tools/perf/db_workload.py --output perf.json
    python tools/perf/db_workload.py --drop-secondary-indexes --output noidx.json

``--drop-secondary-indexes`` removes the ``ix_*`` indexes before measuring so
the same code can be compared with and without them. Timings are
machine-dependent evidence, never test assertions; see
docs/DATABASE_PERFORMANCE.md.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import random
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SEED = 4300
MEASURED_OPERATIONS = (
    "list_reports_by_well", "list_reports_by_section", "open_report_header",
    "open_report_full_snapshot", "report_time_logs", "survey_by_well",
    "survey_by_report", "report_revisions", "approval_history",
    "audit_for_report", "recent_audit", "dashboard_reports_today",
    "hierarchy", "cost_totals", "latest_mud_report", "delete_report",
)


_ENVIRONMENT_KEYS = ("DRILLMASTER_ENV", "DRILLMASTER_ENVIRONMENT", "DRILLMASTER_DATA_DIR",
                     "DRILLMASTER_DB_PATH", "DRILLMASTER_AI_IMPORT")


def _configure_environment(directory: Path) -> Path:
    db_path = directory / "workload.db"
    os.environ.update({
        "DRILLMASTER_ENV": "test",
        "DRILLMASTER_DATA_DIR": str(directory),
        "DRILLMASTER_DB_PATH": str(db_path),
        "DRILLMASTER_AI_IMPORT": "0",
    })
    os.environ.pop("DRILLMASTER_ENVIRONMENT", None)
    return db_path


def build_dataset(manager, *, wells: int, reports_per_well: int, seed: int = SEED) -> dict:
    """Insert the deterministic synthetic hierarchy; returns ids and row counts."""
    from core.database import (
        ApprovalAction, AuditLog, BitReport, BulkMaterials, Company, CostRecord, DailyReport,
        DrillingParameters, MudReport, Project, ReportRevision, Section, SurveyPoint, TimeLog24H,
        Well, Wellbore,
    )

    rng = random.Random(seed)
    ids = {"wells": [], "sections": [], "reports": [], "report_dates": []}
    start = date(2025, 1, 1)
    with manager.session_scope() as session:
        company = Company(name="Synthetic Workload Co", code="SYN-CO")
        session.add(company)
        session.flush()
        project = Project(company_id=company.id, name="Synthetic Project", code="SYN-PRJ")
        session.add(project)
        session.flush()
        for w in range(wells):
            well = Well(project_id=project.id, name=f"SYN-WELL-{w + 1:02d}", code=f"SW{w + 1:02d}")
            session.add(well)
            session.flush()
            bore = Wellbore(well_id=well.id, name="Original", wellbore_type="original")
            session.add(bore)
            session.flush()
            sections = []
            for s, name in enumerate(("26 in", "17-1/2 in", "12-1/4 in")):
                section = Section(well_id=well.id, wellbore_id=bore.id, name=name,
                                  depth_from=s * 1000.0, depth_to=(s + 1) * 1000.0)
                session.add(section)
                session.flush()
                sections.append(section.id)
            ids["wells"].append(well.id)
            ids["sections"].extend(sections)
            md = 0.0
            for r in range(reports_per_well):
                day = start + timedelta(days=w * 3 + r)
                section_id = sections[min(2, r * 3 // reports_per_well)]
                status = rng.choice(("Draft", "Submitted", "Approved"))
                report = DailyReport(well_id=well.id, wellbore_id=bore.id, section_id=section_id,
                                     report_date=day, report_number=r + 1, status=status,
                                     depth_2400=md + 30.0, summary=f"synthetic day {r + 1}")
                session.add(report)
                session.flush()
                ids["reports"].append(report.id)
                ids["report_dates"].append(day)
                for h in range(12):
                    session.add(TimeLog24H(report_id=report.id, time_from=dtime(2 * h, 0),
                                           time_to=dtime((2 * h + 2) % 24, 0), duration=2.0,
                                           main_code=rng.choice(("DRL", "TRP", "CIR", "RIG")),
                                           is_npt=rng.random() < 0.05,
                                           activity_description="synthetic activity"))
                session.add(MudReport(well_id=well.id, report_id=report.id, report_date=day,
                                      mw=round(rng.uniform(60, 90), 1)))
                session.add(DrillingParameters(well_id=well.id, report_id=report.id, report_date=day))
                session.add(BitReport(well_id=well.id, report_id=report.id, report_date=day))
                session.add(BulkMaterials(well_id=well.id, report_id=report.id, report_date=day,
                                          material_name="Barite", used=float(rng.randint(0, 50))))
                for _ in range(3):
                    md += rng.uniform(5.0, 15.0)
                    session.add(SurveyPoint(well_id=well.id, report_id=report.id, section_id=section_id,
                                            md=round(md, 2), inc=round(rng.uniform(0, 60), 2),
                                            azi=round(rng.uniform(0, 360), 2)))
                for category in ("Rig", "Services"):
                    session.add(CostRecord(well_id=well.id, category=category, cost_date=day,
                                           actual_cost=float(rng.randint(1000, 50000))))
                if status != "Draft":
                    session.add(ReportRevision(report_id=report.id, revision_no=1, status=status,
                                               snapshot={"synthetic": True}))
                    session.add(ApprovalAction(report_id=report.id, action="submit", status=status))
                for action in ("daily_report_saved", "daily_report_viewed"):
                    session.add(AuditLog(username="synthetic", action=action, entity_type="daily_report",
                                         entity_id=report.id, timestamp=datetime(2025, 1, 1) + timedelta(days=r)))
        for i in range(wells * reports_per_well * 4):  # login noise dominates real audit tables
            session.add(AuditLog(username="synthetic", action="login_failed" if i % 7 == 0 else "login",
                                 entity_type="user", timestamp=datetime(2025, 1, 1) + timedelta(minutes=i)))
    return ids


def _drop_secondary_indexes(manager) -> int:
    """Drop the ix_* indexes through the initialized manager's own connection.

    The manager keeps its production PRAGMAs; nothing recreates the indexes
    until the next initialize(). ANALYZE is deliberately not run in either
    mode because the application never runs it.
    """
    raw = manager.engine.raw_connection()
    try:
        names = [r[0] for r in raw.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'ix\\_%' ESCAPE '\\'")]
        for name in names:
            raw.execute(f'DROP INDEX "{name}"')
        raw.commit()
    finally:
        raw.close()
    return len(names)


def _operations(manager, ids: dict):
    from core.database import DailyReport, TimeLog24H
    from core.report_snapshot import build_report_snapshot

    reports, wells, sections, dates = ids["reports"], ids["wells"], ids["sections"], ids["report_dates"]

    def with_session(fn):
        session = manager.create_session()
        try:
            return fn(session)
        finally:
            session.close()

    deletable = list(reversed(reports))  # each delete consumes one report
    return {
        "list_reports_by_well": lambda i: manager.get_daily_reports_by_well(wells[i % len(wells)]),
        "list_reports_by_section": lambda i: manager.get_daily_reports_by_section(sections[i % len(sections)]),
        "open_report_header": lambda i: manager.get_daily_report_by_id(reports[(i * 37) % len(reports)]),
        "open_report_full_snapshot": lambda i: with_session(lambda s: build_report_snapshot(
            s, s.get(DailyReport, reports[(i * 37) % len(reports)]), manager._SNAPSHOT_MODELS)),
        "report_time_logs": lambda i: with_session(lambda s: s.query(TimeLog24H).filter_by(
            report_id=reports[(i * 37) % len(reports)]).all()),
        "survey_by_well": lambda i: manager.load_survey_points(well_id=wells[i % len(wells)]),
        "survey_by_report": lambda i: manager.load_survey_points(report_id=reports[(i * 37) % len(reports)]),
        "report_revisions": lambda i: manager.get_report_revisions(reports[(i * 37) % len(reports)]),
        "approval_history": lambda i: manager.get_approval_history(reports[(i * 37) % len(reports)]),
        "audit_for_report": lambda i: manager.get_audit_logs(entity_type="daily_report",
                                                            entity_id=reports[(i * 37) % len(reports)]),
        "recent_audit": lambda i: manager.get_audit_logs(limit=100),
        "dashboard_reports_today": lambda i: with_session(lambda s: s.query(DailyReport).filter(
            DailyReport.report_date == dates[(i * 37) % len(dates)]).count()),
        "hierarchy": lambda i: manager.get_full_hierarchy(),
        "cost_totals": lambda i: manager.get_cost_totals(wells[i % len(wells)]),
        "latest_mud_report": lambda i: manager.get_mud_report(well_id=wells[i % len(wells)],
                                                             report_date=dates[(i * 37) % len(dates)]),
        "delete_report": lambda i: manager.delete_daily_report(deletable.pop(0)),
    }


def _capture_statements(manager, fn):
    from sqlalchemy import event

    captured = []

    def listener(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("SELECT", "DELETE", "UPDATE")):
            captured.append((statement, parameters))

    event.listen(manager.engine, "before_cursor_execute", listener)
    try:
        fn()
    finally:
        event.remove(manager.engine, "before_cursor_execute", listener)
    return captured


def explain(db_path: Path, statements) -> list:
    """EXPLAIN QUERY PLAN for each distinct statement (read-only connection)."""
    plans, seen = [], set()
    connection = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        for statement, parameters in statements:
            if statement in seen:
                continue
            seen.add(statement)
            rows = connection.execute("EXPLAIN QUERY PLAN " + statement, parameters or ()).fetchall()
            details = [row[3] for row in rows]
            plans.append({"sql": " ".join(statement.split())[:300], "plan": details,
                          "full_scans": [d for d in details if d.startswith("SCAN ") and " USING " not in d]})
    finally:
        connection.close()
    return plans


def _environment(manager, db_path: Path) -> dict:
    import sqlalchemy

    raw = manager.engine.raw_connection()
    try:
        pragmas = {name: raw.execute(f"PRAGMA {name}").fetchone()[0]
                   for name in ("journal_mode", "synchronous", "foreign_keys", "busy_timeout",
                                "cache_size", "page_size")}
        indexes = raw.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name LIKE 'ix\\_%' ESCAPE '\\'").fetchone()[0]
        version = raw.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        # Used size: in WAL mode the main file alone omits un-checkpointed
        # pages, and dropped indexes leave free pages behind.
        used_pages = (raw.execute("PRAGMA page_count").fetchone()[0]
                      - raw.execute("PRAGMA freelist_count").fetchone()[0])
        logical_bytes = used_pages * pragmas["page_size"]
    finally:
        raw.close()
    return {
        "platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version, "sqlalchemy": sqlalchemy.__version__, "pragmas": pragmas,
        "secondary_indexes": indexes, "schema_version": version,
        "database_used_bytes": logical_bytes,
    }


def run(*, wells: int = 5, reports_per_well: int = 100, repeats: int = 25, warmup: int = 3,
        drop_secondary_indexes: bool = False, seed: int = SEED, keep_directory: bool = False) -> dict:
    directory = Path(tempfile.mkdtemp(prefix="drillmaster-workload-"))
    saved_environment = {key: os.environ.get(key) for key in _ENVIRONMENT_KEYS}
    manager = None
    try:
        db_path = _configure_environment(directory)
        from core.database import DatabaseManager

        manager = DatabaseManager()
        if not manager.initialize():
            raise RuntimeError(f"initialize failed: {manager.last_diagnostic}")
        started = time.perf_counter()
        ids = build_dataset(manager, wells=wells, reports_per_well=reports_per_well, seed=seed)
        setup_seconds = time.perf_counter() - started
        dropped = _drop_secondary_indexes(manager) if drop_secondary_indexes else 0
        environment = _environment(manager, db_path)
        operations = _operations(manager, ids)
        results = {}
        for name in MEASURED_OPERATIONS:
            fn = operations[name]
            statements = _capture_statements(manager, lambda: fn(0))
            plans = explain(db_path, statements)
            runs = 1 if name == "delete_report" else warmup
            for i in range(1, runs):
                fn(i)
            samples = []
            count = min(repeats, 10) if name == "delete_report" else repeats
            for i in range(count):
                t0 = time.perf_counter_ns()
                fn(i + warmup)
                samples.append((time.perf_counter_ns() - t0) / 1e6)
            samples.sort()
            p95 = samples[min(len(samples) - 1, int(round(0.95 * (len(samples) - 1))))]
            results[name] = {
                "runs": len(samples), "median_ms": round(statistics.median(samples), 3),
                "p95_ms": round(p95, 3), "min_ms": round(samples[0], 3),
                "statements": len(statements), "plans": plans,
                "full_scan_statements": sum(1 for p in plans if p["full_scans"]),
            }
        rows = {}
        raw = sqlite3.connect(db_path)
        try:
            for table in ("daily_reports", "time_logs_24h", "survey_points", "audit_logs", "cost_records",
                          "report_revisions", "approval_actions", "mud_reports"):
                rows[table] = raw.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        finally:
            raw.close()
        return {
            "seed": seed, "wells": wells, "reports_per_well": reports_per_well,
            "reports": len(ids["reports"]), "repeats": repeats, "warmup": warmup,
            "drop_secondary_indexes": drop_secondary_indexes, "dropped_indexes": dropped,
            "setup_seconds": round(setup_seconds, 3), "rows_after_run": rows,
            "environment": environment, "operations": results,
        }
    finally:
        if manager is not None:
            manager.close()
        for key, value in saved_environment.items():  # never leak the temporary paths
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if not keep_directory:
            shutil.rmtree(directory, ignore_errors=True)


def summary_table(result: dict) -> str:
    lines = ["| Operation | median ms | p95 ms | statements | statements with full scan |",
             "|---|---:|---:|---:|---:|"]
    for name, data in result["operations"].items():
        lines.append(f"| {name} | {data['median_ms']} | {data['p95_ms']} | {data['statements']} | "
                     f"{data['full_scan_statements']} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wells", type=int, default=5)
    parser.add_argument("--reports-per-well", type=int, default=100)
    parser.add_argument("--repeats", type=int, default=25)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--drop-secondary-indexes", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = run(wells=args.wells, reports_per_well=args.reports_per_well, repeats=args.repeats,
                 warmup=args.warmup, seed=args.seed, drop_secondary_indexes=args.drop_secondary_indexes)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"reports={result['reports']} setup={result['setup_seconds']}s "
          f"indexes={result['environment']['secondary_indexes']} sqlite={result['environment']['sqlite']}")
    print(summary_table(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
