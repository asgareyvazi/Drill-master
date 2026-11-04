#!/usr/bin/env python3
"""M115 - measured start-up breakdown and right-to-left / left-to-right check (real MainWindow, offscreen Qt).

Measures, on a fresh SYNTHETIC file database (the M70 link fixture):

* ``startup_ms``      MainWindow construction + first show until the event queue is idle
* ``create_tabs_ms``  the part spent in ``MainWindow.create_tabs`` (all tabs are built eagerly)
* ``tabs``            construction time per tab, in tab order (time between consecutive ``addTab`` calls)
* ``visits``          for every tab: first visit time, the effective layout direction, and any exception

``--rtl`` sets the application layout direction to right-to-left before the window is built; run LTR and RTL
in separate processes (one MainWindow per process). Offscreen Linux numbers describe this machine only - NOT a
Windows desktop measurement. SYNTHETIC data only; prints JSON.

Usage:  python tools/quality/ux_startup_m115.py [--rtl] [--json OUT]
"""
from __future__ import annotations

import argparse
import faulthandler
import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def _pump(app, seconds):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.005)


def measure(rtl: bool = False, work: Path = None) -> dict:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    work = Path(work or tempfile.mkdtemp(prefix="m115_ux_"))
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(work),
                       "DRILLMASTER_LOG_DIR": str(work / "logs"), "DRILLMASTER_BACKUP_DIR": str(work / "backups"),
                       "DRILLMASTER_AI_IMPORT": "0"}.items():
        os.environ[key] = value
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtWidgets import QApplication, QTabWidget
    app = QApplication.instance() or QApplication([])
    app.setLayoutDirection(Qt.RightToLeft if rtl else Qt.LeftToRight)
    from core import qt_gc
    qt_gc.install(app)
    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(work / "settings"))
    from core.permissions import permissions, session_user
    from document_link_fixtures import build_link_world
    from synthetic_operations import make_file_database

    db = make_file_database(work / "ux.db")
    ids = build_link_world(db)
    user = session_user(db.authenticate_user("admin", "Synthetic-Admin-1!"))
    permissions.set_user(user)
    db.enforce_authorization(permissions)
    import tabs.w2_Daily_Report as w2
    w2.QMessageBox.question = staticmethod(lambda *a, **k: w2.QMessageBox.No)   # no modal in a measurement
    import main_window as mw

    marks = {"tabs": [], "last": None, "create": None}
    original_add = QTabWidget.addTab
    original_create = mw.MainWindow.create_tabs

    def timed_add(self, widget, *args):
        now = time.perf_counter()
        if marks["last"] is not None and getattr(self, "_m115_main", False):
            marks["tabs"].append((str(args[-1]) if args else type(widget).__name__,
                                  type(widget).__name__, round((now - marks["last"]) * 1000, 1)))
            marks["last"] = now
        return original_add(self, widget, *args)

    def timed_create(self):
        self.tab_widget._m115_main = True
        marks["last"] = start = time.perf_counter()
        try:
            return original_create(self)
        finally:
            marks["create"] = round((time.perf_counter() - start) * 1000, 1)
            marks["last"] = None

    QTabWidget.addTab = timed_add
    mw.MainWindow.create_tabs = timed_create
    try:
        started = time.perf_counter()
        win = mw.MainWindow(db_manager=db, user=user, startup_result=None)
        win.show()
        _pump(app, 0.3)
        startup = round((time.perf_counter() - started) * 1000 - 300, 1)
    finally:
        QTabWidget.addTab = original_add
        mw.MainWindow.create_tabs = original_create
    win.navigate_to({"type": "well", "id": ids["alpha"]})
    _pump(app, 0.3)
    visits = []
    for index in range(win.tab_widget.count()):
        tab = win.tab_widget.widget(index)
        entry = {"tab": win.tab_widget.tabText(index), "class": type(tab).__name__}
        began = time.perf_counter()
        try:
            win.tab_widget.setCurrentIndex(index)
            _pump(app, 0.05)
            entry["ms"] = round((time.perf_counter() - began) * 1000 - 50, 1)
            entry["direction"] = "rtl" if tab.layoutDirection() == Qt.RightToLeft else "ltr"
            entry["visible"] = tab.isVisible()
        except Exception as exc:  # silent-ok: recorded per tab and reported as a failure by the caller
            entry["error"] = f"{type(exc).__name__}: {exc}"
        visits.append(entry)
    tabs = [{"tab": label, "class": cls, "ms": ms} for label, cls, ms in marks["tabs"]]
    result = {
        "environment": {"platform": platform.platform(), "python": platform.python_version(),
                        "qpa": os.environ.get("QT_QPA_PLATFORM"),
                        "note": "offscreen Linux; not a Windows desktop measurement"},
        "direction": "rtl" if rtl else "ltr",
        "startup_ms": startup,
        "create_tabs_ms": marks["create"],
        "tab_count": win.tab_widget.count(),
        "tabs": tabs,
        "slowest_tabs": sorted(tabs, key=lambda t: -t["ms"])[:5],
        "visits": visits,
    }
    _close(app, win, db)
    return result


def _close(app, win, db) -> None:
    """Shut the window down the way the application does (M102 fixture), and prove it closed.

    The measurement answers every QMessageBox.question with No, which includes the exit confirmation, so the
    close is confirmed explicitly. A close that is ignored would leave worker threads running at interpreter
    exit, so it is an error here rather than a timing-dependent crash."""
    from core.selection_manager import SelectionManager
    end = time.monotonic() + 10
    while win._hierarchy_worker is not None and time.monotonic() < end:
        _pump(app, 0.05)
    SelectionManager().clear()
    win._close_confirmed = True
    win.close()
    _pump(app, 0.2)
    if win.isVisible() or win._hierarchy_worker is not None:
        raise RuntimeError("the main window did not close (close ignored or hierarchy worker still running)")
    db.engine.dispose()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rtl", action="store_true")
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    faulthandler.enable()          # a native crash prints its stack instead of a bare exit status
    result = measure(rtl=args.rtl)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
