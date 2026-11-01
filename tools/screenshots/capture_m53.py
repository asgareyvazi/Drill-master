"""Capture M53 Operations Dashboard screenshots (real HomeTab, synthetic data, offscreen Qt).

Every image comes from the application's real ``tabs.home_tab.HomeTab`` working
on a throw-away temporary file database filled by the SYNTHETIC fixtures
``tests/synthetic_operations.py`` + ``tests/synthetic_dashboard.py`` (no real
well, company, location, cost or report data).  The full dashboard canvas is
saved with ``QWidget.grab()``.  Each shot runs in its own interpreter.

* ``dashboard_overview``       - all wells, dark theme, no well selected;
* ``dashboard_selected_well``  - SYN-DEV-01 selected: charts + trajectory preview;
* ``dashboard_empty``          - empty database: empty state, "No data" KPIs;
* ``dashboard_alerts``         - status filter "Active", SYN-QA-03 selected (alerts, unavailable charts);
* ``dashboard_light``          - light theme, single-well filter (cost per metre, NPT cost estimate).

Environment honesty: ``QT_QPA_PLATFORM=offscreen`` (raster, no window manager,
bundled fonts), Linux.  Not a native Windows desktop.

Usage::

    QT_QPA_PLATFORM=offscreen python tools/screenshots/capture_m53.py --out DIR
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHOTS = ("dashboard_overview", "dashboard_selected_well", "dashboard_empty", "dashboard_alerts",
         "dashboard_light")
END = date(2026, 1, 15)


def _pump(app, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


def _home(app, db, today):
    from PySide6.QtCore import QTimer
    import tabs.home_tab as home_tab
    home = home_tab.HomeTab(db)
    home.refresh_timer.stop()
    home.today_provider = lambda: today    # the synthetic data is dated around END
    QTimer.singleShot(0, home.load_data)
    home.resize(1680, 1000)
    home.show()
    _pump(app, 0.3)
    home.wait_for_load()
    _pump(app, 0.3)
    return home


def run_one(shot: str, out: Path) -> Path:
    sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
    from PySide6.QtWidgets import QApplication, QWidget
    app = QApplication.instance() or QApplication([])
    from synthetic_operations import make_file_database
    work = Path(tempfile.mkdtemp(prefix="m53-shot-"))
    db = make_file_database(work / "synthetic-m53.db")
    ids = {}
    if shot != "dashboard_empty":
        from synthetic_dashboard import build_dashboard_fixture
        ids = build_dashboard_fixture(db, END)
    else:
        from core.database import Well
        with db.session_scope() as session:          # the initializer's placeholder well
            session.query(Well).delete()
    home = _home(app, db, END)
    if shot == "dashboard_selected_well":
        home.focus_well(ids["dev"])
    elif shot == "dashboard_alerts":
        home.set_filter(status_group="active")
        home.wait_for_load()
        _pump(app, 0.2)
        home.focus_well(ids["qa"])
    elif shot == "dashboard_light":
        home.apply_theme("light")
        home.set_filter(well_id=ids["dev"])
    path = out / f"m53_{shot}.png"
    home.wait_for_load()
    _pump(app, 0.4)
    canvas = home.findChild(QWidget, "dashboardCanvas")
    (canvas or home).grab().save(str(path))
    home.cleanup()
    db.engine.dispose()
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--shot", choices=SHOTS)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.shot:
        print(run_one(args.shot, out))
        return 0
    failures = 0
    for shot in SHOTS:
        result = subprocess.run([sys.executable, __file__, "--out", str(out), "--shot", shot],
                                env=dict(os.environ), cwd=str(ROOT))
        failures += result.returncode != 0
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
