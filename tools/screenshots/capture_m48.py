"""Capture M48 screenshots of the running application with SYNTHETIC data.

Runs the real ``MainWindow`` against a throw-away file database in a
temporary directory (real initialisation, real sign-in with a random admin
password), fills it with the M48 synthetic wells (tests/m48_synthetic.py:
SYN-A / SYN-B / SYN-C, invented values) and selects wells through the real
``SelectionManager``. Saves ``QWidget.grab()`` images of the Operations
Analysis page:

* KPI cards with units for a complete well (SYN-C);
* NPT coverage: valid zero vs partial vs missing days (SYN-A);
* the evidence trend with a selected point and its source report (SYN-C);
* an ambiguous evidence row with the drill-down disabled (SYN-B depth);
* the ROP projection NOT ASSESSED on too few dates (SYN-A);
* the rule-based risk screening with criteria and rules (SYN-C);
* mixed-currency cost never summed (SYN-A);
* the page after deselecting the well.

Environment honesty: run with ``QT_QPA_PLATFORM=offscreen`` (raster
rendering, no window manager, bundled fonts). Images show the application's
real widgets and data, not a native Windows desktop.

Usage::

    QT_QPA_PLATFORM=offscreen python tools/screenshots/capture_m48.py --out DIR
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _pump(app, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="drillmaster-m48-shots-"))
    os.environ.update({"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(work),
                       "DRILLMASTER_DB_PATH": str(work / "synthetic.db"),
                       "DRILLMASTER_LOG_DIR": str(work / "logs"),
                       "DRILLMASTER_BACKUP_DIR": str(work / "backups"),
                       "DRILLMASTER_AI_IMPORT": "0"})
    sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QMessageBox

    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(work / "settings"))
    app = QApplication.instance() or QApplication(sys.argv)
    for name in ("warning", "information", "critical", "question"):
        setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))

    from core import analysis_evidence as ev
    from core.database import DatabaseManager
    from core.permissions import permissions, session_user
    from core.selection_manager import SelectionManager
    from m48_synthetic import build

    password = secrets.token_urlsafe(18) + "aA1!"
    db = DatabaseManager(bootstrap_passwords={"admin": password})
    db.db_path = str(work / "synthetic.db")
    if not db.initialize():
        raise SystemExit(f"database initialization failed: {db.last_diagnostic}")
    _db, ids = build(db)
    user = session_user(db.authenticate_user("admin", password))
    permissions.set_user(user)
    db.enforce_authorization(permissions)

    from main_window import MainWindow

    window = MainWindow(db_manager=db, user=user, startup_result=None)
    window.resize(1600, 1300)
    window.show()
    _pump(app, 2.0)
    page = window.analysis_widget
    window.tab_widget.setCurrentWidget(page)
    sel = SelectionManager()

    def shot(name: str):
        path = out / f"{name}.png"
        window.grab().save(str(path))
        print("saved", path)

    def select(key):
        sel.select_well(ids[key], {"name": f"SYN-{key}"})
        _pump(app, 1.0)

    def analysis(kind):
        page.analysis_tabs.setCurrentIndex(page.analysis_tabs.indexOf(
            page.analysis_tabs.widget(4)))
        page.analytics_type.blockSignals(True)
        page.analytics_type.setCurrentText(kind)
        page.analytics_type.blockSignals(False)
        page.run_advanced_analysis()
        _pump(app, 0.5)
        scroll = page.results_text.parentWidget()
        while scroll is not None and not hasattr(scroll, "ensureWidgetVisible"):
            scroll = scroll.parentWidget()
        if scroll is not None:      # minimal scroll: chart title and results both in view
            scroll.ensureWidgetVisible(page.results_text, 0, 0)
        _pump(app, 0.5)

    def evidence(metric, row):
        page.analysis_tabs.setCurrentWidget(page.evidence_tab)
        page.evidence_metric.setCurrentIndex(page.evidence_metric.findData(metric))
        page.evidence_level.setCurrentIndex(page.evidence_level.findData(ev.SCOPE_WELL))
        page.evidence_load_btn.click()
        page.select_evidence_row(row)
        _pump(app, 0.8)

    select("C")
    page.analysis_tabs.setCurrentIndex(0)
    _pump(app, 0.8)
    shot("m48_kpi_cards_units")

    select("A")
    page.analysis_tabs.setCurrentIndex(1)
    _pump(app, 0.8)
    shot("m48_npt_coverage_states")

    select("C")
    evidence("rop", 2)
    shot("m48_evidence_trend_point")

    select("B")
    page.evidence_metric.setCurrentIndex(page.evidence_metric.findData("depth"))
    rows = page._evidence_rows
    ambiguous = next(i for i, r in enumerate(rows) if r.state == ev.STATE_AMBIGUOUS)
    evidence("depth", ambiguous)
    shot("m48_evidence_ambiguous_disabled")

    select("A")
    analysis("ROP Prediction")
    shot("m48_projection_not_assessed")

    analysis("Cost Analysis")
    shot("m48_cost_mixed_currency")

    select("C")
    analysis("Risk Assessment")
    shot("m48_risk_rule_based")

    sel.select_well(None)
    _pump(app, 0.8)
    shot("m48_no_selection")

    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
