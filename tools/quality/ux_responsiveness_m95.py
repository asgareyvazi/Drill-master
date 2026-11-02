#!/usr/bin/env python3
"""M95 - measured responsiveness of the desktop UI paths (real MainWindow, file SQLite, offscreen Qt).

Synthetic world (the M70 link fixture) plus ``--days`` daily reports with ``--logs`` time-log rows each on the
first well. The application's GUI-thread GC policy is installed as in production. Measured, each with the
longest gap between 5 ms GUI timer ticks (``max_gap_ms`` = the longest time the event loop could not run):

* ``startup``      MainWindow construction + first show
* ``well_switch``  ``navigate_to`` another well until the event queue is idle (median of ``--n``)
* ``tab_visit``    first visit of every selection-scoped tab after a well selection (per tab)
* ``oa_refresh``   W12 Operational Analysis refresh over the synthetic year (median of ``--n``)
* ``catalogue``    Help › Method Catalogue open
* ``export``       W11 EOWR HTML export on the export worker (GUI gap measured while it runs)

Offscreen Linux numbers describe this machine only: they are NOT a Windows desktop measurement.
SYNTHETIC data only; prints JSON.

Usage:  python tools/quality/ux_responsiveness_m95.py [--days 365] [--logs 8] [--n 5]
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
from datetime import date, time as dtime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


class GapMeter:
    """Largest interval between ticks of a 5 ms GUI timer while a block runs."""

    def __init__(self):
        from PySide6.QtCore import QTimer
        self.timer = QTimer()
        self.timer.setInterval(5)
        self.timer.timeout.connect(self._tick)
        self.last = None
        self.max_gap = 0.0

    def _tick(self):
        now = time.perf_counter()
        if self.last is not None:
            self.max_gap = max(self.max_gap, now - self.last)
        self.last = now

    def __enter__(self):
        self.last, self.max_gap = time.perf_counter(), 0.0
        self.timer.start()
        return self

    def __exit__(self, *exc):
        self._tick()
        self.timer.stop()


def _idle(app, seconds=0.05):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.002)


def _measure(app, action, settle=0.05):
    with GapMeter() as meter:
        start = time.perf_counter()
        action()
        _idle(app, settle)
        total = time.perf_counter() - start - settle
    return {"ms": round(total * 1000, 2), "max_gap_ms": round(meter.max_gap * 1000, 2)}


def _seed_year(db, well_id, days, logs):
    from core.database import DailyReport, TimeLog24H
    with db.session_scope() as s:
        depth = 500.0
        for d in range(days):
            report = DailyReport(well_id=well_id, report_date=date(2025, 1, 1) + timedelta(days=d),
                                 report_number=100 + d, depth_0000=depth, depth_2400=depth + 40.0)
            depth += 40.0
            s.add(report)
            s.flush()
            step = 24 // max(logs, 1)
            for i in range(logs):
                code = "DRL" if i % 3 == 0 else ("RPR" if i % 7 == 6 else "CIR")
                s.add(TimeLog24H(report_id=report.id, time_from=dtime(i * step), time_to=dtime(((i + 1) * step) % 24),
                                 duration=float(step), main_code=code, is_npt=(code == "RPR")))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--logs", type=int, default=8)
    parser.add_argument("--n", type=int, default=5)
    args = parser.parse_args(argv)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    work = Path(tempfile.mkdtemp(prefix="m95_ux_"))
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(work),
                       "DRILLMASTER_LOG_DIR": str(work / "logs"), "DRILLMASTER_BACKUP_DIR": str(work / "backups"),
                       "DRILLMASTER_AI_IMPORT": "0"}.items():
        os.environ[key] = value
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from core import qt_gc
    qt_gc.install(app)
    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(work / "settings"))
    from core.base_tab import DrillTabBase
    from core.permissions import permissions, session_user
    from core.selection_manager import SelectionManager
    from document_link_fixtures import build_link_world
    from synthetic_operations import make_file_database

    db = make_file_database(work / "ux.db")
    ids = build_link_world(db)
    _seed_year(db, ids["alpha"], args.days, args.logs)
    user = session_user(db.authenticate_user("admin", "Synthetic-Admin-1!"))
    permissions.set_user(user)
    db.enforce_authorization(permissions)
    import tabs.w2_Daily_Report as w2
    w2.QMessageBox.question = staticmethod(lambda *a, **k: w2.QMessageBox.No)   # no modal in a measurement
    from main_window import MainWindow

    out = {"environment": {"platform": platform.platform(), "python": platform.python_version(),
                           "qpa": os.environ.get("QT_QPA_PLATFORM"), "days": args.days, "logs_per_day": args.logs,
                           "note": "offscreen Linux; not a Windows desktop measurement"}}
    holder = {}
    out["startup"] = _measure(app, lambda: holder.update(win=MainWindow(db_manager=db, user=user,
                                                                        startup_result=None)) or holder["win"].show(),
                              settle=0.3)
    win = holder["win"]
    switches = []
    for i in range(args.n):
        target = ids["alpha"] if i % 2 == 0 else ids["twin_1"]
        switches.append(_measure(app, lambda t=target: win.navigate_to({"type": "well", "id": t}), settle=0.2))
    out["well_switch"] = {"median_ms": statistics.median(s["ms"] for s in switches),
                          "max_gap_ms": max(s["max_gap_ms"] for s in switches)}
    win.navigate_to({"type": "well", "id": ids["alpha"]})
    _idle(app, 0.3)
    visits = {}
    for i in range(win.tab_widget.count()):
        tab = win.tab_widget.widget(i)
        if isinstance(tab, DrillTabBase):
            visits[type(tab).__name__] = _measure(app, lambda t=tab: win.tab_widget.setCurrentWidget(t), settle=0.1)
    out["tab_visit"] = visits
    w12 = next(win.tab_widget.widget(i) for i in range(win.tab_widget.count())
               if type(win.tab_widget.widget(i)).__name__ == "AnalysisWidget")
    win.tab_widget.setCurrentWidget(w12)
    w12.analysis_tabs.setCurrentWidget(w12.operational_panel)
    runs = [_measure(app, w12.operational_panel.refresh, settle=0.02) for _ in range(args.n)]
    result = w12.operational_panel.result
    out["oa_refresh"] = {"median_ms": statistics.median(r["ms"] for r in runs),
                         "max_gap_ms": max(r["max_gap_ms"] for r in runs),
                         "daily_rows": len(result.tables["daily"][1]) if result else None}
    out["catalogue"] = _measure(app, lambda: win.show_method_catalogue(), settle=0.1)
    win._method_catalogue.close()

    import tabs.w11_Export as w11
    export = next(win.tab_widget.widget(i) for i in range(win.tab_widget.count())
                  if type(win.tab_widget.widget(i)).__name__ == "ExportWidget")
    win.tab_widget.setCurrentWidget(export)
    _idle(app, 0.2)
    target = work / "eowr.html"
    w11.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(target), ""))
    export.eowr_fmt.setCurrentText("HTML")

    def run_export():
        export._export_eowr()
        end = time.perf_counter() + 120
        while export.export_running() and time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.002)
    out["export"] = _measure(app, run_export)
    out["export"]["written"] = target.exists()

    SelectionManager().clear()
    win._close_confirmed = True
    win.close()
    _idle(app, 0.2)
    db.engine.dispose()
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
