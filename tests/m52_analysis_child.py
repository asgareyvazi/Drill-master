"""M52 §2.1 Analysis staged paint + worker-prepared payloads (run by test_m52_analysis_payloads.py).

Real ``AnalysisWidget`` + real ``SelectionManager`` on the M48 synthetic fixture
in a TEMPORARY FILE database, so the page takes its production path (snapshot
worker, staged paint).  Qt offscreen platform, isolated subprocess; each
scenario prints one ``M52RESULT {json}`` line.  Nothing is mocked: wrappers only
record calls, threads and event-loop turns.  Offscreen-Qt tests on Linux, not
Windows desktop testing.
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from PySide6.QtCore import QCoreApplication, QEvent, QThread, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

from core import qt_gc  # noqa: E402

qt_gc.install(app)

from core.permissions import permissions  # noqa: E402

permissions.set_user({"id": 1, "username": "m52", "role": "engineer"})

from sqlalchemy import text  # noqa: E402

import tabs.w12_Analysis as w12  # noqa: E402
from core import analysis_payloads as ap  # noqa: E402
from core.selection_manager import SelectionManager  # noqa: E402
from m48_synthetic import build  # noqa: E402
from tabs.analysis_views import ChartImageView  # noqa: E402

for _name in ("warning", "information", "critical", "question"):
    setattr(QMessageBox, _name, staticmethod(lambda *a, **k: QMessageBox.Ok))

MAIN_THREAD = threading.get_ident()
SCENARIOS = []
EXTRA_ROWS = 1500                    # well C: 1500 extra time-log rows, every 7th NPT


def scenario(fn):
    SCENARIOS.append(fn)
    return fn


def until(condition, timeout_ms=15000):
    waited = 0
    while not condition() and waited < timeout_ms:
        app.processEvents()
        QThread.msleep(5)
        waited += 5
    app.processEvents()
    return condition()


class Ctx:
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="m52ana_")
        data = os.path.join(self.tmp, "data")
        os.environ.update({"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": data,
                           "DRILLMASTER_DB_PATH": os.path.join(data, "synthetic-m52.db"),
                           "DRILLMASTER_BACKUP_DIR": os.path.join(data, "backups"),
                           "DRILLMASTER_AI_IMPORT": "0"})
        from core.database import DatabaseManager
        self.db = DatabaseManager()
        assert self.db.initialize(), self.db.last_diagnostic
        self.db, self.ids = build(self.db)
        s = self.db.create_session()
        report = s.execute(text("SELECT MIN(id) FROM daily_reports WHERE well_id = :w"),
                           {"w": self.ids["C"]}).scalar()
        s.execute(text("INSERT INTO time_logs_24h (report_id, time_from, time_to, duration, is_npt, main_code) "
                       "VALUES (:r, '00:00:00', '00:01:00', 0.01, :npt, :code)"),
                  [{"r": report, "npt": i % 7 == 0, "code": "NPT-B" if i % 7 == 0 else None}
                   for i in range(EXTRA_ROWS)])
        s.commit()
        s.close()
        self.sel = SelectionManager()
        self.sel.clear()
        self.tab = w12.AnalysisWidget(db_manager=self.db)
        assert self.tab._uses_revision_worker(), "a file database must use the snapshot worker"
        self.tab.resize(1400, 900)
        self.tab.show()
        app.processEvents()
        self.steps = []              # (generation, step name, job id) of every paint step

    def close(self):
        try:
            self.tab.cleanup()
            self.sel.clear()
            self.tab.hide()
            self.tab.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            until(lambda: not w12._LIVE_REVISION_WORKERS, 5000)
        finally:
            self.db.close()
            shutil.rmtree(self.tmp, ignore_errors=True)

    def well(self, key, wait=True):
        self.sel.select_well(self.ids[key], {"name": f"SYN-{key}"})
        app.processEvents()
        if wait:
            self.idle()

    def idle(self):
        assert self.tab.wait_until_idle(30000), "update cycle did not finish"
        assert until(lambda: not w12._LIVE_REVISION_WORKERS), "worker thread still registered"

    def record_steps(self, after_first=None):
        """Record every paint step; ``after_first(job)`` is scheduled after the first staged step."""
        real = self.tab._run_paint_step
        fired = []

        def recording(step, failed):
            job = self.tab._paint_job
            self.steps.append((self.tab._generation, step.__name__, id(job) if job else None))
            result = real(step, failed)
            if after_first is not None and job is not None and not fired:
                fired.append(True)
                QTimer.singleShot(0, lambda j=job: after_first(j))
            return result
        self.tab._run_paint_step = recording

    def view(self):
        t = self.tab
        cards = [(c.metric_key, c.metric_value) for c in (*t.kpi_cards, *t.perf_kpi_cards)]
        pie = t.findChild(ChartImageView, "npt_pie_view")
        milestones = t.findChild(ChartImageView, "milestones_view")
        td = t.chart_data.get("time_depth") or {}
        return (cards, t.npt_category_card.value_label.text(), t.results_text.toPlainText(),
                t.npt_table.rows(), pie.chart.spec if pie is not None and pie.chart else None,
                milestones.chart.spec if milestones is not None and milestones.chart
                else (milestones.message() if milestones is not None else None),
                (td.get("days"), td.get("depths"), td.get("gains")))


# ---- payloads come from the worker ----------------------------------------------------------------
@scenario
def snapshot_paint_builds_no_payload_on_the_gui_thread(ctx):
    threads = []
    real = w12.ap.prepare

    def recording(values, settings, failed_type=Exception):
        threads.append(threading.get_ident())
        return real(values, settings, failed_type=failed_type)
    w12.ap.prepare = recording
    try:
        ctx.well("C")
        ctx.tab.refresh_now()        # a second cycle: the views exist and have their final size
        ctx.idle()
    finally:
        w12.ap.prepare = real
    t = ctx.tab
    assert threads and all(ident != MAIN_THREAD for ident in threads), "payloads prepared on the GUI thread"
    builds_before = dict(t.payload_gui_builds)
    used_before = t.payload_worker_used
    t.refresh_now()
    ctx.idle()
    assert t.payload_gui_builds == builds_before, (builds_before, t.payload_gui_builds)
    assert t.payload_worker_used - used_before >= 4, t.payload_worker_used - used_before   # rows, pie, milestones, td
    npt = t.chart_data["npt"]
    assert t.npt_table.rows() == ap.npt_rows(npt["entries"]) and t.npt_table.rowCount() >= EXTRA_ROWS // 7
    pie = t.findChild(ChartImageView, "npt_pie_view")
    assert pie.chart.spec == ("pie", ap.pie_spec(npt["categories"]))


@scenario
def staged_and_synchronous_paint_are_identical(ctx):
    ctx.well("C")
    staged = ctx.view()
    ctx.tab._uses_revision_worker = lambda: False
    try:
        ctx.tab.refresh_now()        # every read and build on the GUI thread (pre-M51 path)
    finally:
        del ctx.tab._uses_revision_worker
    assert ctx.view() == staged


# ---- the staged paint yields between views ---------------------------------------------------------
@scenario
def staged_paint_yields_to_the_event_loop_between_views(ctx):
    ticks = [0]
    ticker = QTimer()
    ticker.setInterval(0)
    ticker.timeout.connect(lambda: ticks.__setitem__(0, ticks[0] + 1))
    at_step = []
    real = ctx.tab._run_paint_step

    def recording(step, failed):
        at_step.append(ticks[0])
        return real(step, failed)
    ctx.tab._run_paint_step = recording
    ticker.start()
    try:
        ctx.well("C")
    finally:
        ticker.stop()
    steps = len(ctx.tab._paint_steps())
    assert len(at_step) >= steps, at_step
    last = at_step[-steps:]
    assert all(b > a for a, b in zip(last, last[1:])), f"no event-loop turn between two views: {last}"


@scenario
def scope_change_mid_paint_stops_the_old_paint(ctx):
    ctx.well("A")
    old_generation = ctx.tab._generation
    ctx.record_steps(after_first=lambda job: ctx.well("C", wait=False))
    ctx.tab.refresh_now()
    ctx.idle()
    first_new = next(i for i, (g, _n, _j) in enumerate(ctx.steps) if g != old_generation)
    assert all(g != old_generation for g, _n, _j in ctx.steps[first_new:]), ctx.steps
    assert sum(1 for g, _n, _j in ctx.steps if g == old_generation) < len(ctx.tab._paint_steps())
    depth = next(c.metric_value for c in ctx.tab.kpi_cards if c.metric_key == "current_depth")
    assert depth.value == 700.0, depth           # well C's value, never well A's


@scenario
def section_change_mid_paint_cancels_the_old_paint(ctx):
    # A section change bumps the scope generation and refreshes only the daily view; that view's
    # read outside a paint requests a new cycle, which cancels the superseded staged paint.  This
    # indirect cancel is what makes every scope change stop the old paint (mutation report M52).
    ctx.well("C")
    jobs = []

    def change_section(job):
        jobs.append(job)
        ctx.tab.on_section_changed(None, None)
    ctx.record_steps(after_first=change_section)
    ctx.tab.refresh_now()
    ctx.idle()
    assert jobs and jobs[0].cancelled, "a section change must cancel the superseded staged paint"
    painted = [s for s in ctx.steps if s[2] == id(jobs[0])]
    assert len(painted) == 1, painted             # only the step before the scope change


@scenario
def refresh_mid_paint_cancels_the_staged_paint(ctx):
    ctx.well("C")
    jobs = []

    def refresh(job):
        jobs.append(job)
        ctx.tab.refresh_now()
    ctx.record_steps(after_first=refresh)
    ctx.tab.refresh_now()
    ctx.idle()
    assert jobs and jobs[0].cancelled, "the superseded staged paint was not cancelled"
    after = [s for s in ctx.steps if s[2] == id(jobs[0])]
    assert len(after) == 1, after                 # only the step before the refresh
    assert ctx.tab.status_label.text().startswith("🟢 Updated"), ctx.tab.status_label.text()


@scenario
def update_request_mid_paint_runs_one_more_cycle(ctx):
    ctx.well("C")
    starts = []
    real = ctx.tab._start_snapshot

    def counting(*args, **kwargs):
        starts.append(1)
        return real(*args, **kwargs)
    ctx.tab._start_snapshot = counting
    ctx.record_steps(after_first=lambda job: ctx.tab.update_all_data())
    ctx.tab.refresh_now()
    ctx.idle()
    assert until(lambda: ctx.tab._paint_job is None and ctx.tab._rev_worker is None)
    ctx.idle()
    assert len(starts) == 2, starts               # the request was neither lost nor interleaved
    assert not ctx.tab._snapshot_wanted


@scenario
def cleanup_mid_paint_leaves_no_job_or_thread(ctx):
    ctx.well("C")
    ctx.record_steps(after_first=lambda job: ctx.tab.cleanup())
    ctx.tab.refresh_now()
    assert until(lambda: ctx.tab._paint_job is None and not w12._LIVE_REVISION_WORKERS)
    count = len(ctx.steps)
    for _ in range(20):
        app.processEvents()
        QThread.msleep(5)
    assert len(ctx.steps) == count, "a paint step ran after cleanup"


@scenario
def snapshot_worker_holds_young_collections_only_while_it_runs(ctx):
    seen = []
    real = w12.AnalysisSnapshotWorker._read_all

    def recording(worker, isolated, revision):
        seen.append(qt_gc._collector.active_holds())        # read on the worker thread
        return real(worker, isolated, revision)
    w12.AnalysisSnapshotWorker._read_all = recording
    try:
        ctx.well("C")
    finally:
        w12.AnalysisSnapshotWorker._read_all = real
    assert seen and all(n >= 1 for n in seen), seen
    assert until(lambda: qt_gc._collector.active_holds() == 0, 5000), "a hold outlived its worker"
    assert qt_gc._collector.stats()["worker_collections"] == 0


# ---- states and export ---------------------------------------------------------------------------
@scenario
def deselect_clears_rows_pie_and_milestones(ctx):
    ctx.well("C")
    t = ctx.tab
    assert t.npt_table.rowCount() > 0
    ctx.sel.select_well(None)
    app.processEvents()
    pie = t.findChild(ChartImageView, "npt_pie_view")
    milestones = t.findChild(ChartImageView, "milestones_view")
    assert t.npt_table.rowCount() == 0
    assert pie.chart is None and not pie.isVisible()
    assert milestones.chart is None and milestones.message() == "Milestones: no well selected"


@scenario
def npt_export_writes_the_shown_pie(ctx):
    ctx.well("C")
    for suffix, magic in ((".png", b"\x89PNG"), (".pdf", b"%PDF")):
        target = os.path.join(ctx.tmp, "npt" + suffix)
        original = QFileDialog.getSaveFileName
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (target, ""))
        try:
            ctx.tab.export_chart_image("npt")
        finally:
            QFileDialog.getSaveFileName = original
        with open(target, "rb") as fh:
            assert fh.read(4) == magic, suffix


@scenario
def chart_view_rerenders_after_resize_off_thread_and_drops_stale(ctx):
    spec = (("NPT-A", 2.0), ("NPT-B", 1.0))
    threads, gate = [], threading.Event()

    def render(size):
        threads.append(threading.get_ident())
        return ap.render_pie(spec, size)
    view = ChartImageView(minimum=(100, 100))
    view.resize(400, 300)
    view.show()
    view.show_image(ap.render_pie(spec, (400, 300)), render=render)
    view.resize(900, 700)
    assert until(lambda: view.rerenders == 1, 10000), "no re-render after the resize"
    assert threads and all(ident != MAIN_THREAD for ident in threads)
    assert abs(view.chart.width - view.contentsRect().width()) <= 2

    def slow(size):
        gate.wait(10)
        return ap.render_pie(spec, size)
    view.show_image(ap.render_pie(spec, (300, 200)), render=slow)
    assert until(lambda: view._worker is not None, 5000)
    view.show_message("superseded")               # a newer state while the re-render runs
    gate.set()
    assert until(lambda: view._worker is None, 10000)
    assert view.chart is None and view.message() == "superseded"
    view.cleanup()
    view.deleteLater()


def main(selected=None):
    for fn in SCENARIOS:
        if selected and fn.__name__ not in selected:
            continue
        ctx = None
        try:
            ctx = Ctx()
            fn(ctx)
            result = {"name": fn.__name__, "ok": True}
        except Exception:
            result = {"name": fn.__name__, "ok": False, "error": traceback.format_exc()[-3000:]}
        finally:
            if ctx is not None:
                try:
                    ctx.close()
                except Exception as exc:
                    result = {"name": fn.__name__, "ok": False,
                              "error": f"close failed: {type(exc).__name__}: {exc}"}
        print("M52RESULT " + json.dumps(result), flush=True)


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
