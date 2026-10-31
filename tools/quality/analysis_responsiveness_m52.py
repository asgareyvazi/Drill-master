#!/usr/bin/env python3
"""M52 §2.1 - GUI responsiveness of the Analysis update cycle (real flow, file SQLite).

Temporary FILE database (synthetic M48 fixture + N extra time-log rows on well
C, every 7th row NPT), offscreen Qt, the GUI-thread GC policy installed as the
application does.  Each measured cycle is a real ``refresh_now()`` of the real
``AnalysisWidget``; nothing measured is replaced - readers, preparation, paint
stages and the collector are wrapped by timers only.

Scenarios (each: 3 warm-up cycles discarded, then ``--n`` measured cycles)
  refresh   data unchanged, cache cleared (Refresh Now): every value re-read,
            every payload rebuilt on the worker
  changed   one synthetic time-log row inserted before every cycle: a new data
            revision every time (auto-update after a write)

Per cycle
  total          refresh_now() -> "Updated" (after the verify revision)
  max_gap        largest gap between 5 ms GUI timer ticks during the cycle - the
                 longest time the event loop could not run (the stall a user feels)
  prep           ``core.analysis_payloads.prepare`` on the snapshot worker
  gui_paint      sum of the GUI time of all paint stages (M52 staged paint)
  gui_stage_max  the slowest single paint stage (one event-loop turn)
  render         one full offscreen render of the page (``QWidget.grab``)
  gc_gui_total / gc_gui_max   cyclic-collector time on the GUI thread
  gui_builds     display payloads the GUI thread had to build itself (fallback)

Golden parity: after every measured cycle the synchronous path (every read and
build on the GUI thread, the pre-M51 behaviour) paints the same revision; cards,
texts, NPT table rows, pie and milestones specs and the time-depth data must be
equal.  RSS / peak RSS (Linux ``/proc/self/status``) are recorded per size.
SYNTHETIC data only; prints JSON.

Usage:  python tools/quality/analysis_responsiveness_m52.py [--rows 1024,4096,16384,65536] [--n 20]
"""
from __future__ import annotations

import argparse
import gc
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
WARMUP = 3


def _stats(values):
    values = list(values)
    if not values:
        return {"n": 0}
    p95 = statistics.quantiles(values, n=20, method="inclusive")[18] if len(values) > 1 else values[0]
    return {"n": len(values), "median_ms": round(statistics.median(values), 2),
            "p95_ms": round(p95, 2), "max_ms": round(max(values), 2)}


def _rss_mb():
    out = {}
    try:
        with open("/proc/self/status", encoding="ascii") as fh:
            for line in fh:
                if line.startswith(("VmRSS:", "VmHWM:")):
                    out["rss_mb" if line.startswith("VmRSS") else "peak_rss_mb"] = round(int(line.split()[1]) / 1024, 1)
    except OSError:
        out["rss_mb"] = None
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", default="1024,4096,16384,65536")
    parser.add_argument("--n", type=int, default=20)
    args = parser.parse_args(argv)

    from PySide6.QtCore import QElapsedTimer, QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from core import qt_gc
    qt_gc.install(app)
    from core.permissions import permissions
    permissions.set_user({"id": 1, "username": "m52-bench", "role": "engineer"})
    from sqlalchemy import text

    import tabs.w12_Analysis as w12
    from m48_synthetic import build
    from tabs.analysis_views import ChartImageView

    main_thread = threading.get_ident()
    cycle = {}

    # ---- collector time on the GUI thread ---------------------------------------------------------
    gc_state = {"t0": None}

    def _gc_hook(phase, _info):
        if threading.get_ident() != main_thread or not cycle.get("measuring"):
            return
        if phase == "start":
            gc_state["t0"] = time.perf_counter()
        elif gc_state["t0"] is not None:
            ms = (time.perf_counter() - gc_state["t0"]) * 1000
            gc_state["t0"] = None
            cycle["gc_total"] = cycle.get("gc_total", 0.0) + ms
            cycle["gc_max"] = max(cycle.get("gc_max", 0.0), ms)
    gc.callbacks.append(_gc_hook)

    # ---- timing wrappers around the real code ---------------------------------------------------
    real_prepare = w12.ap.prepare

    def timed_prepare(values, settings, failed_type=Exception):
        t0 = time.perf_counter()
        try:
            return real_prepare(values, settings, failed_type=failed_type)
        finally:
            cycle["prep"] = (time.perf_counter() - t0) * 1000
            cycle["prep_on_worker"] = threading.get_ident() != main_thread
    w12.ap.prepare = timed_prepare

    real_finish = w12._StagedPaint._finish

    def timed_finish(job, result):
        cycle.setdefault("stages", []).extend(job.step_ms)
        return real_finish(job, result)
    w12._StagedPaint._finish = timed_finish

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

    def view(page):
        cards = [(c.metric_key, c.metric_value) for c in (*page.kpi_cards, *page.perf_kpi_cards)]
        cards += [page.npt_total_card.metric_value, page.npt_percent_card.metric_value,
                  page.npt_daily_card.metric_value]
        pie = page.findChild(ChartImageView, "npt_pie_view")
        milestones = page.findChild(ChartImageView, "milestones_view")
        td = page.chart_data.get("time_depth") or {}
        return (cards, page.npt_category_card.value_label.text(), page.results_text.toPlainText(),
                page.intelligence_label.text(), page.plan_variance_label.text(),
                page.npt_table.rows(),
                pie.chart.spec if pie is not None and pie.chart is not None else None,
                milestones.chart.spec if milestones is not None and milestones.chart is not None
                else (milestones.message() if milestones is not None else None),
                (td.get("days"), td.get("depths"), td.get("gains")))

    results = {"environment": {"platform": platform.platform(), "python": platform.python_version(),
                               "cpus": os.cpu_count(), "qt_platform": os.environ["QT_QPA_PLATFORM"],
                               "timer_interval_ms": 5, "gc_policy": "gui-thread (core/qt_gc.py): holds, boundary collection, start-up heap frozen as in app.py",
                               "warmup_cycles": WARMUP, "cycles_per_scenario": args.n},
               "rows": {}}
    for rows in [int(x) for x in args.rows.split(",")]:
        tmp = tempfile.mkdtemp(prefix="m52bench_")
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
        insert = text("INSERT INTO time_logs_24h (report_id, time_from, time_to, duration, is_npt, main_code) "
                      "VALUES (:r, '00:00:00', '00:01:00', 0.01, :npt, :code)")
        s.execute(insert, [{"r": report, "npt": i % 7 == 0, "code": "NPT-B" if i % 7 == 0 else None}
                           for i in range(rows)])
        s.commit()
        s.close()

        def add_row(i):
            session = db.create_session()
            try:
                session.execute(insert, {"r": report, "npt": i % 7 == 0, "code": "NPT-B" if i % 7 == 0 else None})
                session.commit()
            finally:
                session.close()

        page = w12.AnalysisWidget(db_manager=db)
        page.resize(1400, 900)
        page.show()
        # As app.py does once its main window is shown (only the first call acts).
        qt_gc.freeze_startup_heap()
        page.on_well_changed(ids["C"], {"name": "SYN-C"})
        assert page.wait_until_idle(120000)
        size_result = {"extra_time_log_rows": rows}
        parity = True
        added = 0
        for scenario in ("refresh", "changed"):
            out = {k: [] for k in ("total", "max_gap", "prep", "gui_paint", "gui_stage_max", "render",
                                   "gc_gui_total", "gc_gui_max", "sync_total", "sync_max_gap")}
            stages, builds = {}, 0
            for i in range(WARMUP + args.n):
                measured = i >= WARMUP
                if scenario == "changed":
                    add_row(rows + added)
                    added += 1
                spin(30)
                cycle.clear()
                builds0 = sum(page.payload_gui_builds.values())
                cycle["measuring"] = True
                ticker = Ticker()
                ticker.start()
                t0 = time.perf_counter()
                if scenario == "changed":
                    page.update_all_data()       # auto-update after a write: new revision
                else:
                    page.refresh_now()
                assert page.wait_until_idle(120000)
                total = (time.perf_counter() - t0) * 1000
                gap = ticker.stop()
                cycle["measuring"] = False
                assert page.status_label.text().startswith("🟢 Updated"), page.status_label.text()
                assert cycle.get("prep_on_worker"), "payloads were not prepared on the worker"
                t1 = time.perf_counter()
                page.grab()
                render = (time.perf_counter() - t1) * 1000
                async_view = view(page)
                cycle_builds = sum(page.payload_gui_builds.values()) - builds0
                # synchronous path for parity (pre-M51: every read and build on the GUI thread)
                spin(30)
                page._uses_revision_worker = lambda: False
                ticker_s = Ticker()
                ticker_s.start()
                t2 = time.perf_counter()
                page.refresh_now()
                sync_total = (time.perf_counter() - t2) * 1000
                spin(1)
                sync_gap = ticker_s.stop()
                del page._uses_revision_worker
                parity = parity and view(page) == async_view
                if not measured:
                    continue
                stage_ms = cycle.get("stages", [])
                out["total"].append(total)
                out["max_gap"].append(gap)
                out["prep"].append(cycle.get("prep", 0.0))
                out["gui_paint"].append(sum(ms for _n, ms in stage_ms))
                out["gui_stage_max"].append(max((ms for _n, ms in stage_ms), default=0.0))
                out["render"].append(render)
                out["gc_gui_total"].append(cycle.get("gc_total", 0.0))
                out["gc_gui_max"].append(cycle.get("gc_max", 0.0))
                out["sync_total"].append(sync_total)
                out["sync_max_gap"].append(sync_gap)
                builds += cycle_builds
                for name, ms in stage_ms:
                    stages.setdefault(name, []).append(ms)
            size_result[scenario] = {
                "staged_snapshot_path": {k: _stats(out[k]) for k in ("total", "max_gap", "prep", "gui_paint",
                                                                    "gui_stage_max", "render", "gc_gui_total",
                                                                    "gc_gui_max")},
                "paint_stages": {k: _stats(v) for k, v in sorted(stages.items())},
                "synchronous_path": {"total": _stats(out["sync_total"]), "max_gap": _stats(out["sync_max_gap"])},
                "gui_payload_builds_in_measured_cycles": builds,
            }
        size_result["painted_values_equal_sync_vs_snapshot"] = parity
        size_result["npt_table_rows"] = page.npt_table.rowCount()
        size_result.update(_rss_mb())
        page.cleanup()
        page.deleteLater()
        spin(50)
        db.close()
        shutil.rmtree(tmp, ignore_errors=True)
        results["rows"][str(rows)] = size_result
        print(f"rows={rows} done", file=sys.stderr, flush=True)
    gc.callbacks.remove(_gc_hook)
    print(json.dumps(results, indent=2))
    return 0 if all(r["painted_values_equal_sync_vs_snapshot"] for r in results["rows"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
