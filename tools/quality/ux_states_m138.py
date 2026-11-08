#!/usr/bin/env python3
"""M138 - measured user-visible states of the six M130-M135 workbench panels (real widgets, offscreen Qt).

For every panel, in a left-to-right and a right-to-left run, on a SYNTHETIC file database:

* ``construct_ms``  building the widget (the 3D layer panel inside its real host, the trajectory viewer)
* ``none``          what the panel says with no well selected (must be an explicit NOT ASSESSED, never blank)
* ``empty``         a well without any record: latency until the background read delivered, and the text
* ``data``          a well with records: latency until the background read delivered, and the text
* ``error``         the panel's own job function fails (injected); the message, the Retry button, and the
                    state after Retry once the failure is gone
* ``direction``     the effective layout direction of the panel and of every child widget
* ``axes``          (trend panel) chart axis labels and their units

Offscreen Linux on this machine (see ``environment``) - NOT Windows desktop evidence. No timing threshold is
asserted anywhere; the latencies describe this run only. SYNTHETIC data only.

Usage:  python tools/quality/ux_states_m138.py [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import date, time as clock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

NOTE = "offscreen Linux; not a Windows desktop measurement"
INJECTED = "SYN-M138 injected failure"
SURVEY_ROWS = [{"md": 0, "inc": 0, "azi": 0}, {"md": 500, "inc": 0, "azi": 0}, {"md": 1000, "inc": 30, "azi": 90},
               {"md": 1500, "inc": 30, "azi": 90}]
DAY1, DAY2 = date(2026, 4, 1), date(2026, 4, 2)


# ---------------------------------------------------------------------------------------------- synthetic world
def build_world(db) -> dict:
    """Well SYN-UX (one wellbore, two DDRs with bit/parameter rows, a mud report, an NPT event matching an NPT
    time-log row and one that only overlaps another, DDR survey points and a survey revision) and well SYN-EMPTY (a wellbore and nothing else)."""
    from sqlalchemy import text

    from core import survey_revisions as sr
    from core.database import DailyReport, DrillingParameters, MudReport, NPTReport, SurveyPoint, TimeLog24H

    with db.session_scope() as s:
        q = s.execute
        q(text("INSERT INTO companies(name, code) VALUES ('Synthetic Co', 'M138')"))
        company = q(text("SELECT id FROM companies WHERE code='M138'")).scalar()
        q(text("INSERT INTO projects(company_id, name, code) VALUES (:c, 'Synthetic UX', 'M138P')"), {"c": company})
        project = q(text("SELECT id FROM projects WHERE code='M138P'")).scalar()
        ids = {}
        for code in ("UX", "EMPTY"):
            q(text("INSERT INTO wells(project_id, name, code) VALUES (:p, :n, :c)"),
              {"p": project, "n": f"SYN-{code}", "c": f"M138{code}"})
            well = q(text("SELECT id FROM wells WHERE code=:c"), {"c": f"M138{code}"}).scalar()
            q(text("INSERT INTO wellbores(well_id, name, wellbore_type) VALUES (:w, :n, 'original')"),
              {"w": well, "n": f"SYN-{code} OH"})
            ids[code] = (well, q(text("SELECT id FROM wellbores WHERE well_id=:w"), {"w": well}).scalar())
        well, bore = ids["UX"]
        r1 = DailyReport(well_id=well, wellbore_id=bore, report_date=DAY1, report_number=1)
        r2 = DailyReport(well_id=well, wellbore_id=bore, report_date=DAY2, report_number=2)
        s.add_all([r1, r2])
        s.flush()
        for report, day, d_out, drilled, hours, rop in ((r1, DAY1, 350.0, 250.0, 20.0, 12.5),
                                                       (r2, DAY2, 500.0, 150.0, 10.0, 15.0)):
            s.add(DrillingParameters(well_id=well, report_id=report.id, report_date=day, bit_no="1", bit_rerun=1,
                                     bit_size=12.25, bit_type="PDC", depth_in=100.0, depth_out=d_out,
                                     bit_drilled=drilled, hours_on_bottom=hours, avg_rop=rop, wob_min=10.0,
                                     wob_max=20.0, rpm_min=120.0, rpm_max=140.0))
        s.add(MudReport(well_id=well, report_id=r1.id, report_date=DAY1, mud_type="WBM", mw=75.0, pv=20.0, yp=10.0))
        s.add(TimeLog24H(report_id=r1.id, time_from=clock(8, 0), time_to=clock(12, 0), duration=4.0, is_npt=True))
        s.add(NPTReport(well_id=well, report_id=r1.id, npt_date=DAY1, start_time=clock(8, 0), end_time=clock(12, 0),
                        duration_hours=4.0, npt_category="Equipment", npt_code="RIG", npt_description="SYN"))
        # DDR 2: the register and the time log overlap but differ (2.5 h vs 1.5 h) -> an UNCERTAIN group
        s.add(TimeLog24H(report_id=r2.id, time_from=clock(9, 30), time_to=clock(11, 0), duration=1.5, is_npt=True))
        s.add(NPTReport(well_id=well, report_id=r2.id, npt_date=DAY2, start_time=clock(9, 0), end_time=clock(11, 0),
                        duration_hours=2.5, npt_category="Equipment", npt_code="RIG", npt_description="SYN pump"))
        for row in SURVEY_ROWS:
            s.add(SurveyPoint(well_id=well, report_id=r1.id, md=float(row["md"]), inc=float(row["inc"]),
                              azi=float(row["azi"])))
        reports = [r1.id, r2.id]
    survey = sr.save_revision(db, well, SURVEY_ROWS, wellbore_id=bore, depth_datum="RKB", azimuth_reference="true")
    return {"well": well, "bore": bore, "well_name": "SYN-UX", "empty": ids["EMPTY"][0], "empty_name": "SYN-EMPTY",
            "survey": survey["id"], "reports": reports}


# ---------------------------------------------------------------------------------------------- panel adapters
def _table_text(table, column=None) -> str:
    rows = []
    for i in range(table.rowCount()):
        cells = [table.item(i, j).text() if table.item(i, j) else "" for j in range(table.columnCount())]
        rows.append(" | ".join(cells if column is None else [cells[column]]))
    return " / ".join(rows)


class _Adapter:
    """How the measurement drives one panel through its public API (the calls the host tabs make)."""
    name = module = job = ""

    def __init__(self, db, world, out_dir):
        self.db, self.world, self.out_dir = db, world, out_dir
        self.host = self.panel = None

    def build(self):
        raise NotImplementedError

    def scope(self, well):
        self.panel.set_scope(well)

    def wait(self) -> bool:
        return self.panel.wait(30000)

    def text(self) -> str:
        return self.panel.scope_label.text() + " || " + self.panel.status.text()

    def after_data(self, _entry) -> None:
        """Extra user-visible steps after the scope delivered (e.g. picking layers); default none."""

    def close(self, app):
        from PySide6.QtCore import QCoreApplication, QEvent
        widget = self.host or self.panel
        widget.shutdown(5000)
        widget.close()
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()


class BitRuns(_Adapter):
    name, module, job = "BitRunWorkbench", "tabs.bit_run_panel", "_load_runs_job"

    def build(self):
        from tabs.bit_run_panel import BitRunWorkbench
        self.panel = BitRunWorkbench(self.db)


class Trends(_Adapter):
    name, module, job = "ParameterTrendPanel", "tabs.parameter_trend_panel", "_load_trends_job"

    def build(self):
        from tabs.parameter_trend_panel import ParameterTrendPanel
        self.panel = ParameterTrendPanel(self.db)

    def text(self) -> str:
        return self.panel.scope_label.text() + " || " + self.panel.summary_label.text()

    def after_data(self, entry) -> None:
        axes = {}
        for key, plot in (("parameter", self.panel.plot), ("mse", self.panel.mse_plot)):
            if plot is None:
                axes[key] = None
                continue
            item = plot.getPlotItem()
            axes[key] = {"left": item.getAxis("left").labelText, "bottom": item.getAxis("bottom").labelText}
        entry["axes"] = axes


class Layers(_Adapter):
    """The 3D layer panel inside its real host: the trajectory viewer composes the working survey."""
    name, module, job = "TrajectoryLayersPanel", "tabs.trajectory_layers_panel", "_catalogue_job"

    def build(self):
        from tabs.trajectory_viewer import TrajectoryViewerTab
        self.host = TrajectoryViewerTab(self.db)
        self.panel = self.host.layers_panel

    def scope(self, well):
        self.host.set_context(well)

    def text(self) -> str:
        return self.panel.frame_label.text() + " || " + _table_text(self.panel.status_table)

    def after_data(self, entry) -> None:
        started = time.perf_counter()
        self.panel.select(base=self.world["survey"])
        entry["layers_ok"] = self.panel.wait(30000)
        entry["layers_ms"] = round((time.perf_counter() - started) * 1000, 1)
        entry["layers_text"] = self.text()
        self.panel.select(base="working")          # back to the default base for the next step


class Mud(_Adapter):
    name, module, job = "MudEvaluationPanel", "tabs.mud_engineering_panel", "_load_samples_job"

    def build(self):
        from tabs.mud_engineering_panel import MudEvaluationPanel
        self.panel = MudEvaluationPanel(self.db)


class Npt(_Adapter):
    name, module, job = "NptReconciliationPanel", "tabs.npt_reconciliation_panel", "_reconcile_job"

    def build(self):
        from tabs.npt_reconciliation_panel import NptReconciliationPanel
        self.panel = NptReconciliationPanel(self.db)

    def text(self) -> str:
        return " || ".join((self.panel.scope_label.text(), self.panel.totals_label.text(), self.panel.status.text()))


class Package(_Adapter):
    """Scope = the well; its data state is a real build (no PDF) into a fresh folder, then the part table."""
    name, module, job = "WellPackagePanel", "tabs.well_package_panel", "_bores_job"

    def build(self):
        from tabs.well_package_panel import WellPackagePanel
        self.panel = WellPackagePanel(self.db)

    def scope(self, well):
        names = {self.world["well"]: self.world["well_name"], self.world["empty"]: self.world["empty_name"]}
        self.panel.set_well(well, names.get(well, ""))
        from core.context_jobs import CANCELLED, ERROR, STALE
        if well is not None and self.panel.wait(30000) and self.panel.bore_jobs.state not in (ERROR, STALE, CANCELLED):
            folder = self.out_dir / f"pkg-{well}-{time.monotonic_ns()}"
            folder.mkdir(parents=True)
            self.panel.build_into(str(folder), include_pdf=False)

    def text(self) -> str:
        parts = _table_text(self.panel.table, column=None)
        text = self.panel.scope_label.text() + " || " + self.panel.status.text() + " || " + parts
        return text.replace(str(self.out_dir), "<work>")

    def after_data(self, entry) -> None:
        import tabs.well_package_panel as module
        original = module._build_job
        module._build_job = _failing
        try:
            folder = self.out_dir / f"pkg-fail-{time.monotonic_ns()}"
            folder.mkdir(parents=True)
            self.panel.build_into(str(folder), include_pdf=False)
            self.panel.wait(30000)
            entry["build_error_text"] = self.panel.status.text().replace(str(self.out_dir), "<work>")
        finally:
            module._build_job = original


ADAPTERS = (BitRuns, Trends, Layers, Mud, Npt, Package)


def _failing(_db, _params, _cancel):
    raise RuntimeError(INJECTED)


@contextmanager
def _injected(adapter):
    import importlib
    module = importlib.import_module(adapter.module)
    original = getattr(module, adapter.job)
    setattr(module, adapter.job, _failing)
    try:
        yield
    finally:
        setattr(module, adapter.job, original)


def _timed_scope(adapter, well) -> dict:
    started = time.perf_counter()
    adapter.scope(well)
    ok = adapter.wait()
    return {"ms": round((time.perf_counter() - started) * 1000, 1), "delivered": ok, "text": adapter.text()}


def _direction_report(widget, expected) -> dict:
    from PySide6.QtWidgets import QWidget
    children = widget.findChildren(QWidget)
    off = sorted({type(c).__name__ for c in children if c.layoutDirection() != expected})
    return {"panel": widget.layoutDirection() == expected, "children": len(children), "not_following": off}


def measure_panel(app, adapter_cls, db, world, out_dir, expected) -> dict:
    adapter = adapter_cls(db, world, out_dir)
    entry = {"panel": adapter.name}
    started = time.perf_counter()
    adapter.build()
    app.processEvents()
    entry["construct_ms"] = round((time.perf_counter() - started) * 1000, 1)
    try:
        entry["direction"] = _direction_report(adapter.host or adapter.panel, expected)
        adapter.scope(None)
        adapter.wait()
        entry["none"] = {"text": adapter.text()}
        entry["empty"] = _timed_scope(adapter, world["empty"])
        entry["data"] = _timed_scope(adapter, world["well"])
        adapter.after_data(entry["data"])
        adapter.scope(None)
        adapter.wait()
        with _injected(adapter):
            failed = _timed_scope(adapter, world["well"])
            failed["retry_visible"] = not adapter.panel.retry_btn.isHidden()
        started = time.perf_counter()
        adapter.panel.retry_btn.click()           # the failure is gone; Retry re-reads the current scope
        adapter.wait()
        failed["after_retry_ms"] = round((time.perf_counter() - started) * 1000, 1)
        failed["after_retry_text"] = adapter.text()
        failed["retry_hidden_after"] = adapter.panel.retry_btn.isHidden()
        entry["error"] = failed
    finally:
        adapter.close(app)
    return entry


def measure(db, world, *, rtl: bool, out_dir: Path) -> dict:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    previous = app.layoutDirection()
    expected = Qt.RightToLeft if rtl else Qt.LeftToRight
    app.setLayoutDirection(expected)
    try:
        panels = [measure_panel(app, cls, db, world, out_dir, expected) for cls in ADAPTERS]
    finally:
        app.setLayoutDirection(previous)
    return {"direction": "rtl" if rtl else "ltr", "panels": panels}


def environment() -> dict:
    return {"platform": platform.platform(), "python": platform.python_version(), "cpus": os.cpu_count(),
            "qpa": os.environ.get("QT_QPA_PLATFORM"), "note": NOTE}


# ---------------------------------------------------------------------------------------------- command line
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json")
    args = parser.parse_args(argv)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    work = Path(tempfile.mkdtemp(prefix="m138_ux_"))
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(work),
                       "DRILLMASTER_LOG_DIR": str(work / "logs"), "DRILLMASTER_BACKUP_DIR": str(work / "backups"),
                       "DRILLMASTER_AI_IMPORT": "0"}.items():
        os.environ[key] = value
    sys.path.insert(0, str(ROOT / "tests"))
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from core.permissions import permissions, session_user
    from synthetic_operations import make_file_database

    db = make_file_database(work / "ux.db")
    world = build_world(db)
    user = session_user(db.authenticate_user("admin", "Synthetic-Admin-1!"))
    permissions.set_user(user)
    db.enforce_authorization(permissions)
    result = {"tool": "M138 panel states v1", "environment": environment(),
              "runs": [measure(db, world, rtl=rtl, out_dir=work / "packages") for rtl in (False, True)]}
    db.engine.dispose()
    del app
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.json:
        Path(args.json).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
