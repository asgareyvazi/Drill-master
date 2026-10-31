#!/usr/bin/env python3
"""M51 - per-stage timing of the Analysis update cycle (real flow, file SQLite).

Temporary FILE database (synthetic M48 fixture + N extra time-log rows on
well C), offscreen Qt, GUI-thread GC policy installed as the application does.
Each measured cycle is a real ``refresh_now()`` (cache cleared, every value
re-read) of the real ``AnalysisWidget``.  Nothing measured is replaced: the
readers, revision and paint are wrapped by timers only.

Stages (M51 snapshot path):
  revision        ``data_revision`` on the snapshot worker (before the reads)
  db_sql          SQL cursor-execute time of the readers on the worker
                  (SQLAlchemy ``before/after_cursor_execute``)
  calc            reader wall time minus ``db_sql``: row materialisation, ORM
                  loading and derived calculation (canonical services) - one
                  number, because the readers interleave the two
  gui_paint       ``_paint_for_revision`` on the GUI thread: chart preparation
                  (values -> chart items/cards/tables) and widget updates
  render          one full offscreen render of the page (``QWidget.grab``)
                  after the cycle - the Qt painting cost of the result
  verify          the M50 revision after the paint (worker)
  total           refresh_now() -> "Updated"
  max_gap         largest gap between 5 ms GUI timer ticks during the cycle
                  (the longest time the event loop could not run)

The synchronous path (``_uses_revision_worker`` -> False; every read on the GUI
thread, the pre-M51 load/paint behaviour) is measured for comparison; its
total and max_gap are reported.  The painted values of both paths are
compared every cycle (golden parity).  SYNTHETIC data only; prints JSON.

Usage:  python tools/quality/analysis_responsiveness_m51.py [--rows 1024,4096,16384] [--n 15]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _stats(values):
    values = list(values)
    if not values:
        return {"n": 0}
    p95 = statistics.quantiles(values, n=20, method="inclusive")[18] if len(values) > 1 else values[0]
    return {"n": len(values), "median_ms": round(statistics.median(values), 2),
            "p95_ms": round(p95, 2), "max_ms": round(max(values), 2)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", default="1024,4096,16384")
    parser.add_argument("--n", type=int, default=15)
    args = parser.parse_args(argv)

    from PySide6.QtCore import QElapsedTimer, QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from core import qt_gc
    qt_gc.install(app)
    from core.permissions import permissions
    permissions.set_user({"id": 1, "username": "m51-bench", "role": "engineer"})
    from sqlalchemy import event, text
    from sqlalchemy.engine import Engine

    import tabs.w12_Analysis as w12
    from m48_synthetic import build

    main_thread = threading.get_ident()
    sql_ms = {}                                   # thread ident -> accumulated cursor-execute ms

    @event.listens_for(Engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("m51_t0", []).append(time.perf_counter())

    @event.listens_for(Engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        t0 = conn.info["m51_t0"].pop()
        ident = threading.get_ident()
        sql_ms[ident] = sql_ms.get(ident, 0.0) + (time.perf_counter() - t0) * 1000

    class Ticker:
        def __init__(self):
            self.clock = QElapsedTimer()
            self.timer = QTimer()
            self.timer.setInterval(5)
            self.timer.timeout.connect(self._tick)

        def _tick(self):
            now = self.clock.nsecsElapsed() / 1e6
            self.max_gap = max(self.max_gap, now - self.last)
            self.last = now

        def start(self):
            self.max_gap, self.last = 0.0, 0.0
            self.clock.start()
            self.timer.start()

        def stop(self):
            self._tick()
            self.timer.stop()
            return self.max_gap

    def spin(ms):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    # ---- timing wrappers around the real code -------------------------------------------
    cycle = {}

    real_revision = w12.AnalysisSnapshotWorker._revision

    def timed_revision(self, isolated):
        t0 = time.perf_counter()
        try:
            return real_revision(self, isolated)
        finally:
            cycle["revision"] = (time.perf_counter() - t0) * 1000
    w12.AnalysisSnapshotWorker._revision = timed_revision

    real_rev_worker_run = w12.RevisionWorker.run

    def timed_verify(self):
        t0 = time.perf_counter()
        try:
            return real_rev_worker_run(self)
        finally:
            cycle["verify"] = (time.perf_counter() - t0) * 1000
    w12.RevisionWorker.run = timed_verify

    real_readers = w12.AnalysisWidget._snapshot_readers

    def timed_readers(page):
        def wrap(name, read):
            def timed(scope, session):
                ident = threading.get_ident()
                sql0, t0 = sql_ms.get(ident, 0.0), time.perf_counter()
                try:
                    return read(scope, session)
                finally:
                    wall = (time.perf_counter() - t0) * 1000
                    sql = sql_ms.get(ident, 0.0) - sql0
                    key = name.split(":")[0]
                    cycle.setdefault("readers", {}).setdefault(key, [0.0, 0.0])
                    cycle["readers"][key][0] += wall
                    cycle["readers"][key][1] += sql
                    cycle["worker_thread"] = ident != main_thread
            return timed
        return [(name, wrap(name, read)) for name, read in real_readers(page)]
    w12.AnalysisWidget._snapshot_readers = timed_readers

    real_paint = w12.AnalysisWidget._paint_for_revision

    def timed_paint(page, revision, *args, **kwargs):
        # Since M52 the snapshot path paints in stages (one view per event-loop
        # turn); this wrapper then times only the call that schedules them - use
        # tools/quality/analysis_responsiveness_m52.py for per-stage GUI time.
        t0 = time.perf_counter()
        try:
            return real_paint(page, revision, *args, **kwargs)
        finally:
            cycle["gui_paint"] = cycle.get("gui_paint", 0.0) + (time.perf_counter() - t0) * 1000
    w12.AnalysisWidget._paint_for_revision = timed_paint

    def view(page):
        cards = [(c.metric_key, c.metric_value) for c in (*page.kpi_cards, *page.perf_kpi_cards)]
        cards += [page.npt_total_card.metric_value, page.npt_percent_card.metric_value,
                  page.npt_daily_card.metric_value]
        return (cards, page.npt_category_card.value_label.text(), page.results_text.toPlainText(),
                page.intelligence_label.text(), page.plan_variance_label.text())

    results = {"environment": {"platform": platform.platform(), "python": platform.python_version(),
                               "cpus": os.cpu_count(), "qt_platform": os.environ["QT_QPA_PLATFORM"],
                               "timer_interval_ms": 5, "gc_policy": "gui-thread (core/qt_gc.py)",
                               "cycles_per_size": args.n, "cache": "cleared (refresh_now)"},
               "rows": {}}
    for rows in [int(x) for x in args.rows.split(",")]:
        tmp = tempfile.mkdtemp(prefix="m51bench_")
        data = os.path.join(tmp, "data")
        os.environ.update({"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": data,
                           "DRILLMASTER_DB_PATH": os.path.join(data, "bench.db"),
                           "DRILLMASTER_BACKUP_DIR": os.path.join(data, "backups"),
                           "DRILLMASTER_AI_IMPORT": "0"})
        from core.database import DatabaseManager
        db = DatabaseManager()
        assert db.initialize(), db.last_diagnostic
        db, ids = build(db)
        s = db.create_session()
        report = s.execute(text("SELECT MIN(id) FROM daily_reports WHERE well_id = :w"),
                           {"w": ids["C"]}).scalar()
        s.execute(text("INSERT INTO time_logs_24h (report_id, time_from, time_to, duration, is_npt, main_code) "
                       "VALUES (:r, '00:00:00', '00:01:00', 0.01, :npt, :code)"),
                  [{"r": report, "npt": i % 7 == 0, "code": "NPT-B" if i % 7 == 0 else None}
                   for i in range(rows)])
        s.commit()
        s.close()
        page = w12.AnalysisWidget(db_manager=db)
        page.resize(1400, 900)
        page.show()
        page.on_well_changed(ids["C"], {"name": "SYN-C"})
        assert page.wait_until_idle(60000)
        paint_steps = {}
        for step in ("update_kpi_data", "update_time_depth_data", "update_npt_data", "update_performance_data",
                     "update_daily_data", "update_analytics", "load_milestones_data", "update_evidence",
                     "update_data_quality", "update_plan_variance", "update_intelligence",
                     "update_scope_indicator"):
            def timed_step(_real=getattr(page, step), _name=step):
                t0 = time.perf_counter()
                try:
                    return _real()
                finally:
                    if cycle.get("painting_snapshot_cycle"):
                        paint_steps.setdefault(_name, []).append((time.perf_counter() - t0) * 1000)
            timed_step.__name__ = step
            setattr(page, step, timed_step)        # instance attribute: the paint loop calls self.<step>
        ticker = Ticker()
        out = {k: [] for k in ("revision", "db_sql", "calc", "gui_paint", "render", "verify", "total",
                               "max_gap", "sync_total", "sync_max_gap")}
        per_reader = {}
        parity = True
        for _ in range(args.n):
            # M51 snapshot path
            spin(30)
            cycle.clear()
            cycle["painting_snapshot_cycle"] = True
            ticker.start()
            t0 = time.perf_counter()
            page.refresh_now()
            assert page.wait_until_idle(60000)
            total = (time.perf_counter() - t0) * 1000
            out["max_gap"].append(ticker.stop())
            assert page.status_label.text().startswith("🟢 Updated"), page.status_label.text()
            assert cycle.get("worker_thread"), "readers did not run on a worker"
            t1 = time.perf_counter()
            page.grab()
            out["render"].append((time.perf_counter() - t1) * 1000)
            out["total"].append(total)
            for key in ("revision", "verify", "gui_paint"):
                out[key].append(cycle.get(key, 0.0))
            readers = cycle.get("readers", {})
            out["db_sql"].append(sum(v[1] for v in readers.values()))
            out["calc"].append(sum(v[0] - v[1] for v in readers.values()))
            for key, (wall, sql) in readers.items():
                per_reader.setdefault(key, []).append(wall)
            async_view = view(page)
            cycle["painting_snapshot_cycle"] = False
            # synchronous path (pre-M51 behaviour) for comparison + parity
            spin(30)
            page._uses_revision_worker = lambda: False
            ticker.start()
            t0 = time.perf_counter()
            page.refresh_now()
            out["sync_total"].append((time.perf_counter() - t0) * 1000)
            spin(1)
            out["sync_max_gap"].append(ticker.stop())
            del page._uses_revision_worker
            parity = parity and view(page) == async_view
        page.cleanup()
        page.deleteLater()
        spin(50)
        db.close()
        shutil.rmtree(tmp, ignore_errors=True)
        results["rows"][str(rows)] = {
            "extra_time_log_rows": rows,
            "snapshot_path": {k: _stats(out[k]) for k in ("revision", "db_sql", "calc", "gui_paint",
                                                          "render", "verify", "total", "max_gap")},
            "snapshot_readers_wall": {k: _stats(v) for k, v in sorted(per_reader.items())},
            "gui_paint_steps": {k: _stats(v) for k, v in sorted(paint_steps.items())},
            "synchronous_path": {"total": _stats(out["sync_total"]), "max_gap": _stats(out["sync_max_gap"])},
            "painted_values_equal_sync_vs_snapshot": parity,
        }
        print(f"rows={rows} done", file=sys.stderr, flush=True)
    print(json.dumps(results, indent=2))
    return 0 if all(r["painted_values_equal_sync_vs_snapshot"] for r in results["rows"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
