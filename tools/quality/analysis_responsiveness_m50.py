#!/usr/bin/env python3
"""M50 - measured GUI responsiveness of the Analysis data revision.

Temporary FILE database (synthetic M48 fixture + N extra time-log rows on
well C), offscreen Qt, GUI-thread GC policy installed as the application does.
A 5 ms ``QTimer`` on the GUI thread records the largest gap between ticks
(the longest time the event loop could not run) while:

  revision-sync   ``ev.data_revision`` on the GUI thread (the M49 behaviour)
  revision-async  ``RevisionWorker`` (M50) - the GUI only waits for the signal
  cycle-sync      a whole page update on the synchronous path
  cycle-async     a whole page update on the M50 path (revision before +
                  load/paint + revision after)

The load/paint steps run on the GUI thread on BOTH paths (unchanged by M50),
so the cycle numbers show what remains.  Prints JSON; SYNTHETIC data only.

Usage:  python tools/quality/analysis_responsiveness_m50.py [--rows 1024,4096,16384] [--n 15]
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
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _stats(values):
    return {"n": len(values), "median_ms": round(statistics.median(values), 2),
            "max_ms": round(max(values), 2), "min_ms": round(min(values), 2)}


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
    permissions.set_user({"id": 1, "username": "m50-bench", "role": "engineer"})
    from sqlalchemy import text

    import tabs.w12_Analysis as w12
    from core import analysis_evidence as ev
    from m48_synthetic import build

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
            self._tick()                       # the gap up to "done" counts too
            self.timer.stop()
            return self.max_gap

    def spin(ms):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    results = {"environment": {"platform": platform.platform(), "python": platform.python_version(),
                               "cpus": os.cpu_count(), "qt_platform": os.environ["QT_QPA_PLATFORM"],
                               "timer_interval_ms": 5, "gc_policy": "gui-thread (core/qt_gc.py)"},
               "rows": {}}
    for rows in [int(x) for x in args.rows.split(",")]:
        tmp = tempfile.mkdtemp(prefix="m50bench_")
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
        out = {"revision_sync": [], "revision_async": [], "hash_ms_worker": [],
               "cycle_sync": [], "cycle_async": []}
        ticker = Ticker()
        for _ in range(args.n):
            # (a) revision phase only
            spin(20)
            ticker.start()
            session = db.create_session()
            t0 = time.perf_counter()
            ev.data_revision(session, ids["C"])
            session.close()
            spin(1)
            out["revision_sync"].append(ticker.stop())
            assert time.perf_counter() - t0 > 0

            spin(20)
            worker = w12.RevisionWorker(db, ids["C"], ("bench",))
            box = {}
            loop = QEventLoop()
            worker.done.connect(lambda ticket, rev, err: (box.update(rev=rev, err=err), loop.quit()))
            ticker.start()
            t0 = time.perf_counter()
            worker.start()
            loop.exec()
            out["revision_async"].append(ticker.stop())
            out["hash_ms_worker"].append((time.perf_counter() - t0) * 1000)
            worker.wait()
            worker.deleteLater()
            assert box["err"] is None and box["rev"]
        page = w12.AnalysisWidget(db_manager=db)
        page.show()
        page.on_well_changed(ids["C"], {"name": "SYN-C"})
        page.wait_until_idle()
        for _ in range(args.n):
            # (b) whole page cycle, both paths
            spin(20)
            page._uses_revision_worker = lambda: False
            ticker.start()
            page.refresh_now()
            spin(1)
            out["cycle_sync"].append(ticker.stop())
            del page._uses_revision_worker
            spin(20)
            ticker.start()
            page.refresh_now()
            assert page.wait_until_idle()
            out["cycle_async"].append(ticker.stop())
            assert page.status_label.text().startswith("🟢 Updated"), page.status_label.text()
        page.cleanup()
        page.deleteLater()
        spin(50)
        db.close()
        shutil.rmtree(tmp, ignore_errors=True)
        results["rows"][str(rows)] = {
            "extra_time_log_rows": rows,
            "max_event_loop_gap_revision_sync": _stats(out["revision_sync"]),
            "max_event_loop_gap_revision_async": _stats(out["revision_async"]),
            "revision_wall_time_async": _stats(out["hash_ms_worker"]),
            "max_event_loop_gap_cycle_sync": _stats(out["cycle_sync"]),
            "max_event_loop_gap_cycle_async": _stats(out["cycle_async"]),
        }
        print(f"rows={rows} done", file=sys.stderr, flush=True)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
