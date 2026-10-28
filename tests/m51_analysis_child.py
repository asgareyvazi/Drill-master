"""M51 Analysis snapshot scenarios (run by test_m51_analysis_snapshot.py).

M51 moves EVERY database read and derived calculation of an Analysis update
cycle to ``AnalysisSnapshotWorker`` (its own read-only connection); the GUI
thread only paints plain values.  This child reuses the M50 harness
(``m50_analysis_child.Ctx``: real ``AnalysisWidget`` + real
``SelectionManager`` on the M48 synthetic fixture in a TEMPORARY FILE
database, real ``data_revision`` behind a recording hook) and adds a probe on
the GUI's SQLAlchemy engine: every statement executed through it on the GUI
thread is counted, whichever API issued it.  Nothing measured is mocked;
injected failures are real exceptions raised inside the real reader on the
worker thread.  Offscreen Qt on Linux, not Windows desktop testing.
"""
import dataclasses
import datetime
import decimal
import json
import sqlite3
import threading
import traceback

from sqlalchemy import event

import m50_analysis_child as base
from m50_analysis_child import app, ev, until, updated, w12  # noqa: F401  (QApplication first)

SCENARIOS = []


def scenario(fn):
    SCENARIOS.append(fn)
    return fn


class GuiSql:
    """Counts statements run through the GUI engine on the GUI thread."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.statements = []
        self.paused = False
        event.listen(ctx.db.engine, "before_cursor_execute", self._on_execute)

    def _on_execute(self, conn, cursor, statement, parameters, context, executemany):
        if not self.paused and threading.get_ident() == base.MAIN_THREAD:
            self.statements.append(" ".join(statement.split())[:80])

    def close(self):
        event.remove(self.ctx.db.engine, "before_cursor_execute", self._on_execute)


class Ctx(base.Ctx):
    def __init__(self):
        super().__init__()
        self.gui_sql = GuiSql(self)

    def sql(self, *statements, **params):
        self.gui_sql.paused = True            # the test's own writes are not page reads
        try:
            super().sql(*statements, **params)
        finally:
            self.gui_sql.paused = False

    def revision(self, key):
        self.gui_sql.paused = True
        try:
            return super().revision(key)
        finally:
            self.gui_sql.paused = False

    def close(self):
        self.gui_sql.close()
        super().close()

    def choose(self, combo, text):
        """A user selection: the combo's signal runs exactly as in the app."""
        index = combo.findText(text)
        assert index >= 0, text
        combo.setCurrentIndex(index)
        app.processEvents()


def _plain(value, path="value"):
    """Assert ``value`` is plain Python data (no ORM row, session or QObject)."""
    if value is None or isinstance(value, (bool, int, float, str, bytes, decimal.Decimal,
                                           datetime.date, datetime.datetime, datetime.time)):
        return
    if isinstance(value, w12._LoadError):
        return
    if isinstance(value, dict):
        for k, v in value.items():
            _plain(k, f"{path}[key]")
            _plain(v, f"{path}[{k!r}]")
        return
    if type(value) in (list, tuple, set, frozenset):
        for i, item in enumerate(value):
            _plain(item, f"{path}[{i}]")
        return
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        for f in dataclasses.fields(value):
            _plain(getattr(value, f.name), f"{path}.{f.name}")
        return
    raise AssertionError(f"{path} is {type(value).__module__}.{type(value).__name__}, not plain data")


def _snapshots(ctx):
    return [payload for ticket, payload, error in ctx.delivered
            if ticket[2] == "before" and isinstance(payload, tuple)]


# ---- the GUI thread never reads ----------------------------------------------
@scenario
def no_gui_thread_sql_in_any_cycle_or_selection_path(ctx):
    ctx.well("A")
    ctx.well("B")
    # well -> bore -> back to whole well (well B owns the OH/ST1 bores)
    ctx.tab.on_wellbore_changed(ctx.ids["OH"], {"name": "SYN-OH"})
    ctx.idle()
    ctx.tab.on_wellbore_changed(ctx.ids["ST1"], {"name": "SYN-ST1"})
    ctx.idle()
    ctx.tab.on_wellbore_changed(None, None)
    ctx.idle()
    ctx.well("C")
    ctx.tab.refresh_now()
    ctx.idle()
    ctx.tab.auto_update_data()
    ctx.idle()
    ctx.tab.on_section_changed(None, {})
    ctx.idle()
    ctx.tab.on_report_changed(ctx.ids["C_reports"][0], {})      # report -> data quality
    ctx.idle()
    assert "loading" not in ctx.tab.quality_label.text(), ctx.tab.quality_label.text()
    for kind in ("NPT Forecasting", "Cost Analysis", "Risk Assessment", "ROP Prediction"):
        ctx.choose(ctx.tab.analytics_type, kind)
        ctx.idle()
        assert "loading" not in ctx.tab.results_text.toPlainText(), kind
    for i in range(ctx.tab.evidence_metric.count()):
        ctx.tab.evidence_metric.setCurrentIndex(i)
        app.processEvents()
        ctx.idle()
        assert "loading" not in ctx.tab.evidence_state_label.text(), ctx.tab.evidence_state_label.text()
    ctx.sel.select_well(None)
    app.processEvents()
    ctx.well("A")
    assert ctx.gui_sql.statements == [], ctx.gui_sql.statements[:10]
    assert ctx.tab.missing_prefetch == 0 and updated(ctx), (ctx.tab.missing_prefetch, ctx.status())
    # Positive control: the probe does see GUI-thread reads (the synchronous path).
    ctx.tab._uses_revision_worker = lambda: False
    ctx.tab.refresh_now()
    del ctx.tab._uses_revision_worker
    assert len(ctx.gui_sql.statements) > 10, len(ctx.gui_sql.statements)


@scenario
def snapshot_payload_is_plain_python_read_on_a_worker(ctx):
    ctx.well("C")
    ctx.choose(ctx.tab.analytics_type, "Risk Assessment")
    ctx.idle()
    snaps = _snapshots(ctx)
    assert snaps, ctx.delivered
    names = set()
    for revision, values in snaps:
        _plain(values)
        names |= set(values)
    for needed in ("kpis", "td", "npt", "perf", "today", "recent", "milestones", "plan", "intel",
                   "bores", "analytics:Risk Assessment"):
        assert needed in names, (needed, sorted(names))
    assert any(n.startswith("evidence:") for n in names), sorted(names)
    assert ctx.off_main_thread() and ctx.gui_sql.statements == []


@scenario
def snapshot_paint_equals_synchronous_paint(ctx):
    # The canonical services and KPI semantics are unchanged: the values the
    # worker reads paint exactly what the synchronous (in-thread) path paints.
    for key in ("A", "C"):
        ctx.well(key)
        for kind in ("Risk Assessment", "NPT Forecasting"):
            ctx.choose(ctx.tab.analytics_type, kind)
            ctx.idle()
            labels = lambda t=ctx.tab: (t.intelligence_label.text(), t.plan_variance_label.text(),  # noqa: E731
                                        t.quality_label.text(), t.scope_label.text(),
                                        t.milestones_scope_label.text())
            async_view, async_labels = ctx.snapshot(), labels()
            ctx.tab._uses_revision_worker = lambda: False
            ctx.tab.refresh_now()
            sync_view, sync_labels = ctx.snapshot(), labels()
            del ctx.tab._uses_revision_worker
            assert async_view == sync_view, (key, kind)
            assert async_labels == sync_labels, (async_labels, sync_labels)
            assert "loading" not in " ".join(async_labels)


# ---- read errors ---------------------------------------------------------------
@scenario
def reader_error_on_worker_is_explicit_never_no_data_and_retryable(ctx):
    from sqlalchemy.exc import OperationalError
    real = w12.AnalysisWidget.get_npt_data
    calls = []

    def failing(self, session):
        calls.append(threading.get_ident())
        if len(calls) == 1:
            raise OperationalError("SELECT 1", {}, Exception("synthetic"))
        return real(self, session)
    w12.AnalysisWidget.get_npt_data = failing
    try:
        ctx.well("C")
        assert calls and calls[0] != base.MAIN_THREAD
        assert "read npt" in ctx.status() and not updated(ctx), ctx.status()
        value = ctx.tab.npt_total_card.metric_value
        assert value.state == ev.STATE_ERROR and value.value is None, value   # an error, not "No data"
        assert ctx.npt()[0] == {}                       # nothing fabricated
        ctx.tab.auto_update_data()                      # never cached: the next cycle reads again
        ctx.idle()
        assert updated(ctx) and ctx.npt()[0] == {"NPT-Z": 7.0}, (ctx.status(), ctx.npt())
    finally:
        w12.AnalysisWidget.get_npt_data = real
    assert ctx.gui_sql.statements == []


@scenario
def analytics_input_error_on_worker_is_explicit(ctx):
    real = w12._ANALYTICS_INPUTS["Risk Assessment"]

    def failing(page, session):
        raise RuntimeError("synthetic")
    w12._ANALYTICS_INPUTS["Risk Assessment"] = failing
    try:
        ctx.well("C")
        ctx.choose(ctx.tab.analytics_type, "Risk Assessment")
        ctx.idle()
        text = ctx.tab.results_text.toPlainText()
        assert "read/processing error (RuntimeError)" in text and "No result is shown" in text, text
        assert "ERROR" in ctx.tab.analytics_plot.plotItem.titleLabel.text
    finally:
        w12._ANALYTICS_INPUTS["Risk Assessment"] = real
    ctx.tab.refresh_now()
    ctx.idle()
    assert "RISK" in ctx.tab.results_text.toPlainText().upper() and updated(ctx)


# ---- concurrency ----------------------------------------------------------------
@scenario
def db_edit_while_worker_reads_is_detected_and_reloaded(ctx):
    ctx.well("C")
    # Milestones are read in every snapshot (values cached for an unchanged
    # revision, like npt, are skipped by the worker), so the writer hooks there.
    real = w12._read_milestones
    edits = []

    def read_then_edit(page, session):
        value = real(page, session)
        if not edits:
            # An external writer commits while the worker is mid-snapshot.
            con = sqlite3.connect(ctx.db.db_path)
            try:
                con.execute("UPDATE time_logs_24h SET main_code = 'NPT-E' WHERE main_code = 'NPT-Z'")
                con.commit()
            finally:
                con.close()
            edits.append(threading.get_ident())
        return value
    w12._read_milestones = read_then_edit
    try:
        ctx.tab.auto_update_data()
        ctx.idle()
    finally:
        w12._read_milestones = real
    assert edits and edits[0] != base.MAIN_THREAD
    assert ctx.tab.concurrent_changes == 1, ctx.tab.concurrent_changes
    assert ctx.npt()[0] == {"NPT-E": 7.0} and updated(ctx), (ctx.npt(), ctx.status())
    assert ctx.tab._data_rev == ctx.revision("C")
    assert ctx.gui_sql.statements == []


@scenario
def refresh_during_snapshot_supersedes_it(ctx):
    ctx.well("C")
    start = len(ctx.hook.calls)
    ctx.hook.gate(start)                           # honours cancellation
    ctx.tab.auto_update_data()                     # timer tick: snapshot starts, blocks at its revision
    assert until(lambda: len(ctx.hook.calls) == start + 1)
    old = ctx.tab._rev_worker
    assert isinstance(old, w12.AnalysisSnapshotWorker)
    ctx.tab.refresh_now()                          # the user's Refresh cancels and restarts
    ctx.idle()
    assert ctx.hook.cancelled == [start]
    assert old.ticket not in [t for t, _, _ in ctx.delivered], "the cancelled snapshot was delivered"
    assert updated(ctx) and ctx.tab._data_rev == ctx.revision("C")


@scenario
def auto_tick_during_snapshot_does_not_start_a_second_one(ctx):
    ctx.well("C")
    start = len(ctx.hook.calls)
    gate = ctx.hook.gate(start, honour_cancel=False)
    ctx.tab.auto_update_data()
    assert until(lambda: len(ctx.hook.calls) == start + 1)
    worker = ctx.tab._rev_worker
    for _ in range(3):
        ctx.tab.auto_update_data()                 # ticks while it runs
    assert ctx.tab._rev_worker is worker
    gate.set()
    ctx.idle()
    assert len(ctx.hook.calls) == start + 2, ctx.hook.calls[start:]   # one snapshot + one verify
    assert updated(ctx)


@scenario
def rapid_scope_changes_paint_only_the_final_scope(ctx):
    for key in ("A", "B", "C", "B", "A"):
        ctx.well(key, wait=False)
    ctx.idle()
    assert ctx.tab._data_rev == ctx.revision("A") and updated(ctx)
    assert _snapshots(ctx), ctx.delivered
    painted_revisions = [r for r in ctx.painted if r is not None]
    assert painted_revisions[-1] == ctx.revision("A")
    for other in ("B", "C"):
        assert ctx.revision(other) not in painted_revisions, other
    assert ctx.gui_sql.statements == []


@scenario
def view_change_during_snapshot_gets_one_more_cycle(ctx):
    ctx.well("C")
    start = len(ctx.hook.calls)
    gate = ctx.hook.gate(start, honour_cancel=False)
    ctx.tab.auto_update_data()
    assert until(lambda: len(ctx.hook.calls) == start + 1)
    ctx.choose(ctx.tab.analytics_type, "Cost Analysis")     # not in the running snapshot
    assert "loading" in ctx.tab.results_text.toPlainText()
    gate.set()
    ctx.idle()
    text = ctx.tab.results_text.toPlainText()
    assert "loading" not in text and "COST" in text.upper(), text
    assert updated(ctx) and ctx.gui_sql.statements == []


@scenario
def close_while_reader_runs_joins_the_worker(ctx):
    ctx.well("C")
    real = w12._read_milestones                      # read in every snapshot
    entered, release = threading.Event(), threading.Event()

    def slow(page, session):
        entered.set()
        release.wait(5)
        return real(page, session)
    w12._read_milestones = slow
    try:
        painted = len(ctx.painted)
        ctx.tab.auto_update_data()
        assert entered.wait(5)
        worker = ctx.tab._rev_worker
        threading.Timer(0.2, release.set).start()
        ctx.tab.cleanup()                              # joins: cancellation is checked between readers
        assert worker.isFinished() and not worker.isRunning()
        app.processEvents()
        assert len(ctx.painted) == painted, "a closed page painted a late snapshot"
        assert until(lambda: not w12._LIVE_REVISION_WORKERS)
    finally:
        release.set()
        w12._read_milestones = real


@scenario
def worker_scope_proxy_fails_closed(ctx):
    scope = w12._FrozenScope({"current_well_id": ctx.ids["C"]}, ctx.db, "rev")
    for name in ("results_text", "update_kpi_data", "_draw_milestones_chart", "_fetch_cached"):
        try:
            getattr(scope, name)
        except AttributeError:
            continue
        raise AssertionError(f"{name} reachable from a worker scope")
    assert scope._scope_key() and callable(scope.calculate_kpis)


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
        print("M51RESULT " + json.dumps(result), flush=True)


if __name__ == "__main__":
    import sys
    main(set(sys.argv[1:]) or None)
