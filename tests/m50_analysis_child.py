"""M50 asynchronous Analysis revision scenarios (run by test_m50_analysis_async.py).

Real ``AnalysisWidget`` + real ``SelectionManager`` on the M48 synthetic
fixture, but in a TEMPORARY FILE database (``DatabaseManager.initialize``), so
the page takes its production path: the data revision is computed by
``RevisionWorker`` on its own read-only connection.  Qt offscreen platform,
isolated subprocess; each scenario prints one ``M50RESULT {json}`` line.

Determinism: ``ev.data_revision`` is wrapped by ``Hook``.  The hook always runs
the REAL function (nothing is mocked); it only records the calling thread,
can inject a database error, and can hold a computed result at a gate so a
slow / late hash is reproduced exactly instead of by sleeping.
These are offscreen-Qt tests on Linux, not Windows desktop testing.
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

from PySide6.QtCore import QCoreApplication, QEvent, QThread  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication.instance() or QApplication([])

from core import qt_gc  # noqa: E402

if os.environ.get("M50_GC_POLICY", "1") == "1":
    qt_gc.install(app)       # what DrillMasterApp does at startup

from core.permissions import permissions  # noqa: E402

permissions.set_user({"id": 1, "username": "m50", "role": "engineer"})

import tabs.w12_Analysis as w12  # noqa: E402
from core import analysis_evidence as ev  # noqa: E402
from core.selection_manager import SelectionManager  # noqa: E402
from m48_synthetic import build  # noqa: E402

for _name in ("warning", "information", "critical", "question"):
    setattr(QMessageBox, _name, staticmethod(lambda *a, **k: QMessageBox.Ok))

REAL_REVISION = ev.data_revision
MAIN_THREAD = threading.get_ident()
SCENARIOS = []


def scenario(fn):
    SCENARIOS.append(fn)
    return fn


class Hook:
    """Wraps the real ``data_revision``; per-call gates and injected errors."""

    def __init__(self):
        self.calls = []          # (thread ident, well id)
        self.binds = []          # engine each call read through
        self.gates = {}          # call index -> (Event, honour_cancel)
        self.fail = {}           # call index -> exception to raise
        self.cancelled = []      # call indexes that stopped through ``cancelled``

    def gate(self, index, honour_cancel=True):
        event = threading.Event()
        self.gates[index] = (event, honour_cancel)
        return event

    def __call__(self, session, well_id, cancelled=None):
        index = len(self.calls)
        self.calls.append((threading.get_ident(), well_id))
        self.binds.append(session.get_bind())
        if index in self.fail:
            raise self.fail[index]
        revision = REAL_REVISION(session, well_id, cancelled=cancelled)
        if index in self.gates:
            event, honour = self.gates[index]
            while not event.wait(0.005):
                if honour and cancelled is not None and cancelled():
                    self.cancelled.append(index)
                    raise ev.RevisionCancelled()
        return revision


def until(condition, timeout_ms=10000):
    for _ in range(timeout_ms // 5):
        if condition():
            return True
        app.processEvents()
        QThread.msleep(5)
    app.processEvents()
    return condition()


class Probe(w12.AnalysisWidget):
    """Records paints and deliveries.  A subclass, not instance patching: the
    worker's ``done`` stays connected to a bound method of the page QObject,
    exactly as in production (Qt drops it when the page is destroyed)."""

    def __init__(self, ctx, **kwargs):
        self._probe_ctx = ctx
        super().__init__(**kwargs)

    def _paint_for_revision(self, revision):
        self._probe_ctx.painted.append(revision)
        return super()._paint_for_revision(revision)

    def _on_revision(self, ticket, revision, error):
        self._probe_ctx.delivered.append((ticket, revision, error))
        return super()._on_revision(ticket, revision, error)


class Ctx:
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="m50ana_")
        data = os.path.join(self.tmp, "data")
        os.environ.update({"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": data,
                           "DRILLMASTER_DB_PATH": os.path.join(data, "synthetic-m50.db"),
                           "DRILLMASTER_BACKUP_DIR": os.path.join(data, "backups"),
                           "DRILLMASTER_AI_IMPORT": "0"})
        from core.database import DatabaseManager
        self.db = DatabaseManager()
        assert self.db.initialize(), self.db.last_diagnostic
        self.db, self.ids = build(self.db)
        self.hook = Hook()
        ev.data_revision = self.hook
        self.sel = SelectionManager()
        self.sel.clear()
        self.painted = []        # revision passed to every _paint_for_revision call
        self.delivered = []      # every ticket that reached _on_revision
        self.tab = Probe(self, db_manager=self.db)
        assert self.tab._uses_revision_worker(), "a file database must use the revision worker"
        self.tab.show()
        app.processEvents()

    def close(self):
        ev.data_revision = REAL_REVISION
        for event, _ in self.hook.gates.values():
            event.set()
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

    # helpers -------------------------------------------------------------
    def well(self, key, wait=True):
        self.sel.select_well(self.ids[key], {"name": f"SYN-{key}"})
        app.processEvents()
        if wait:
            self.idle()

    def idle(self):
        assert self.tab.wait_until_idle(15000), "revision cycle did not finish"
        assert until(lambda: not w12._LIVE_REVISION_WORKERS), "worker thread still registered"

    def revision(self, key):
        s = self.db.create_session()
        try:
            return REAL_REVISION(s, self.ids[key])
        finally:
            s.close()

    def sql(self, *statements, **params):
        """Write like an external tool would: plain SQL, no ORM onupdate hooks."""
        from sqlalchemy import text
        s = self.db.create_session()
        try:
            for statement in statements:
                s.execute(text(statement), params)
            s.commit()
        finally:
            s.close()

    def status(self):
        return self.tab.status_label.text()

    def npt(self):
        data = self.tab.chart_data.get("npt") or {}
        return dict(data.get("categories") or {}), self.tab.npt_total_card.metric_value

    def cost_text(self):
        self.tab.analytics_type.blockSignals(True)
        self.tab.analytics_type.setCurrentText("Cost Analysis")
        self.tab.analytics_type.blockSignals(False)
        self.tab.run_advanced_analysis()
        # M51: on a file database the analysis inputs are read by the snapshot
        # worker (the page shows "loading…" first); wait for that cycle.
        self.idle()
        return self.tab.results_text.toPlainText()

    def snapshot(self):
        t = self.tab
        cards = [(c.metric_key, c.metric_value) for c in (*t.kpi_cards, *t.perf_kpi_cards)]
        cards += [t.npt_total_card.metric_value, t.npt_percent_card.metric_value,
                  t.npt_daily_card.metric_value]
        return (cards, t.npt_category_card.value_label.text(), self.npt()[0],
                t.results_text.toPlainText())

    def off_main_thread(self):
        return all(ident != MAIN_THREAD for ident, _ in self.hook.calls)


def updated(ctx):
    return ctx.status().startswith("🟢 Updated")


# ---- required cases 1-5: every kind of edit reaches the view without Refresh
@scenario
def currency_only_change_reaches_view_through_async_cycle(ctx):
    ctx.well("A")
    assert "actual EUR 500.00" in ctx.cost_text() and updated(ctx)
    ctx.sql("UPDATE cost_records SET currency = 'GBP' WHERE well_id = :w AND currency = 'EUR'",
            w=ctx.ids["A"])
    ctx.tab.auto_update_data()                       # timer path
    ctx.idle()
    text = ctx.tab.results_text.toPlainText()
    assert "actual GBP 500.00" in text and "EUR" not in text, text
    assert updated(ctx) and ctx.tab._data_rev == ctx.revision("A")
    assert ctx.off_main_thread(), ctx.hook.calls


@scenario
def timelog_code_change_reaches_view(ctx):
    ctx.well("C")
    assert ctx.npt()[0] == {"NPT-Z": 7.0}
    ctx.sql("UPDATE time_logs_24h SET main_code = 'NPT-W' WHERE main_code = 'NPT-Z'")
    ctx.tab.auto_update_data()
    ctx.idle()
    assert ctx.npt()[0] == {"NPT-W": 7.0} and updated(ctx)
    assert ctx.off_main_thread()


@scenario
def npt_reclassification_with_same_duration_reaches_view(ctx):
    ctx.well("C")
    ctx.sql("UPDATE time_logs_24h SET main_code = 'NPT-Q' WHERE id = "
            "(SELECT MIN(id) FROM time_logs_24h WHERE main_code = 'NPT-Z')")
    ctx.tab.auto_update_data()
    ctx.idle()
    categories, total = ctx.npt()
    assert categories == {"NPT-Z": 6.0, "NPT-Q": 1.0} and total.value == 7.0, categories


@scenario
def same_count_and_sum_swap_reaches_view(ctx):
    # Well A report A2: one 2 h NPT row + one 22 h productive row.  Swapping
    # the durations keeps row count, ids and the duration sum; NPT goes from
    # 2 + 1.5 = 3.5 h to 22 + 1.5 = 23.5 h (hand-derived from the fixture).
    ctx.well("A")
    assert ctx.npt()[1].value == 3.5
    ctx.sql("UPDATE time_logs_24h SET duration = CASE WHEN is_npt = 1 THEN 22.0 ELSE 2.0 END "
            "WHERE report_id = (SELECT report_id FROM time_logs_24h WHERE main_code = 'NPT-X')")
    ctx.tab.auto_update_data()
    ctx.idle()
    assert ctx.npt()[1].value == 23.5 and updated(ctx), ctx.npt()


@scenario
def delete_and_reinsert_same_id_reaches_view(ctx):
    ctx.well("C")
    ctx.sql("CREATE TEMP TABLE m50_row AS SELECT * FROM time_logs_24h WHERE id = "
            "(SELECT MAX(id) FROM time_logs_24h WHERE main_code = 'NPT-Z')",
            "UPDATE m50_row SET main_code = 'NPT-D'",
            "DELETE FROM time_logs_24h WHERE id = (SELECT id FROM m50_row)",
            "INSERT INTO time_logs_24h SELECT * FROM m50_row",
            "DROP TABLE m50_row")
    ctx.tab.auto_update_data()
    ctx.idle()
    assert ctx.npt()[0] == {"NPT-Z": 6.0, "NPT-D": 1.0}, ctx.npt()


# ---- 6-8: stale results ----------------------------------------------------
def _deliver_late(ctx, ticket, revision):
    """Re-deliver a result exactly as an already-posted queued call would."""
    ctx.tab._on_revision(ticket, revision, None)
    app.processEvents()


@scenario
def well_change_mid_hash_never_shows_old_well(ctx):
    gate = ctx.hook.gate(0, honour_cancel=False)     # A's hash will finish late
    ctx.well("A", wait=False)
    assert until(lambda: len(ctx.hook.calls) == 1)
    old = ctx.tab._rev_worker
    assert ctx.status().startswith("🟡 Updating"), ctx.status()     # visible updating state
    assert all(c.metric_value.state == ev.STATE_RUNNING for c in ctx.tab.kpi_cards)
    ctx.well("C", wait=False)                        # A still hashing (ignores cancel)
    assert ctx.tab.wait_until_idle(15000)
    assert ctx.npt()[0] == {"NPT-Z": 7.0} and updated(ctx)
    gate.set()
    old.wait(5000)
    app.processEvents()
    _deliver_late(ctx, old.ticket, ctx.revision("A"))
    assert ctx.npt()[0] == {"NPT-Z": 7.0} and ctx.npt()[1].value == 7.0
    assert ctx.tab._data_rev == ctx.revision("C")
    assert ctx.revision("A") not in ctx.painted, "the old well's revision was painted"
    assert updated(ctx)


@scenario
def deselect_mid_hash_paints_nothing(ctx):
    gate = ctx.hook.gate(0, honour_cancel=False)
    ctx.well("A", wait=False)
    assert until(lambda: len(ctx.hook.calls) == 1)
    old = ctx.tab._rev_worker
    ctx.sel.select_well(None)
    app.processEvents()
    gate.set()
    old.wait(5000)
    app.processEvents()
    _deliver_late(ctx, old.ticket, ctx.revision("A"))
    ctx.idle()
    assert ctx.painted == [], ctx.painted
    assert ctx.status() == "🔴 No well selected"
    assert all(c.metric_value.state == ev.STATE_NO_SELECTION for c in ctx.tab.kpi_cards)


@scenario
def late_old_result_after_refresh_is_ignored(ctx):
    ctx.well("C")
    before = ctx.revision("C")
    start = len(ctx.hook.calls)
    gate = ctx.hook.gate(start, honour_cancel=False)
    ctx.tab.auto_update_data()                       # cycle 1: hashes the OLD data, then waits
    assert until(lambda: len(ctx.hook.calls) == start + 1)
    old = ctx.tab._rev_worker
    ctx.sql("UPDATE time_logs_24h SET main_code = 'NPT-L' WHERE main_code = 'NPT-Z'")
    gate.set()
    old.wait(5000)                                   # its result is now posted to the GUI thread
    ctx.tab.refresh_now()                            # cycle 2 supersedes cycle 1
    ctx.idle()
    _deliver_late(ctx, old.ticket, before)           # and once more, explicitly
    after = ctx.revision("C")
    assert before != after
    assert before not in ctx.painted[1:], "the superseded revision was painted"
    assert ctx.tab._data_rev == after and ctx.npt()[0] == {"NPT-L": 7.0} and updated(ctx)


# ---- 9: database errors ------------------------------------------------------
@scenario
def revision_error_is_explicit_and_not_cached(ctx):
    from sqlalchemy.exc import OperationalError
    ctx.hook.fail[0] = OperationalError("SELECT 1", {}, Exception("synthetic"))
    ctx.well("C")
    assert "read data revision (OperationalError)" in ctx.status() and "Error" in ctx.status()
    assert ctx.tab._data_rev is None and not updated(ctx)
    ctx.tab.auto_update_data()                       # next tick recovers by itself
    ctx.idle()
    assert updated(ctx) and ctx.tab._data_rev == ctx.revision("C")


@scenario
def verify_error_is_explicit(ctx):
    from sqlalchemy.exc import OperationalError
    ctx.hook.fail[1] = OperationalError("SELECT 1", {}, Exception("synthetic"))
    ctx.well("C")
    assert "verify data revision (OperationalError)" in ctx.status(), ctx.status()
    assert not updated(ctx)


# ---- 10: disposal -----------------------------------------------------------
@scenario
def tab_closed_with_active_worker_joins_it(ctx):
    ctx.hook.gate(0)                                 # honours cancellation, like the 512-row poll
    ctx.well("A", wait=False)
    assert until(lambda: len(ctx.hook.calls) == 1)
    worker = ctx.tab._rev_worker
    ctx.tab.cleanup()
    assert worker.isFinished() and not worker.isRunning(), "cleanup left a running thread"
    assert ctx.hook.cancelled == [0]
    assert until(lambda: not w12._LIVE_REVISION_WORKERS)
    assert ctx.painted == []


@scenario
def page_destroyed_while_worker_blocked_is_safe(ctx):
    gate = ctx.hook.gate(0, honour_cancel=False)
    ctx.well("A", wait=False)
    assert until(lambda: len(ctx.hook.calls) == 1)
    worker = ctx.tab._rev_worker
    ctx.tab.hide()
    ctx.tab.deleteLater()                            # no cleanup(): worst case
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    assert worker in w12._LIVE_REVISION_WORKERS     # kept alive: never destroyed while running
    gate.set()
    assert worker.wait(5000)
    assert until(lambda: not w12._LIVE_REVISION_WORKERS)
    assert ctx.delivered == [], "a destroyed page received the late result"
    ctx.tab = w12.AnalysisWidget(db_manager=ctx.db)  # Ctx.close() needs a live page


@scenario
def page_destroyed_while_verify_worker_blocked_is_safe(ctx):
    # Since M51 the first revision of a cycle runs inside the snapshot worker; the
    # verify revision after the paint is a RevisionWorker and must be kept alive too.
    ctx.well("C")
    start = len(ctx.hook.calls)
    gate = ctx.hook.gate(start + 1, honour_cancel=False)      # the verify revision blocks
    ctx.tab.refresh_now()
    assert until(lambda: len(ctx.hook.calls) == start + 2)
    worker = ctx.tab._rev_worker
    assert type(worker) is w12.RevisionWorker, type(worker)
    delivered = len(ctx.delivered)
    ctx.tab.hide()
    ctx.tab.deleteLater()                            # no cleanup(): worst case
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    assert worker in w12._LIVE_REVISION_WORKERS     # kept alive: never destroyed while running
    gate.set()
    assert worker.wait(5000)
    assert until(lambda: not w12._LIVE_REVISION_WORKERS)
    assert len(ctx.delivered) == delivered, "a destroyed page received the late result"
    ctx.tab = w12.AnalysisWidget(db_manager=ctx.db)  # Ctx.close() needs a live page


# ---- 11: concurrent edits between revision and load --------------------------
def _edit_during_paint(ctx, codes):
    """After the NPT step of each paint, commit an edit (a concurrent writer)."""
    real_npt = ctx.tab.update_npt_data
    pending = list(codes)

    def npt_then_edit():
        real_npt()
        if pending:
            ctx.sql("UPDATE time_logs_24h SET main_code = :new WHERE is_npt = 1 AND report_id IN "
                    "(SELECT id FROM daily_reports WHERE well_id = :w)", new=pending.pop(0),
                    w=ctx.ids["C"])
    ctx.tab.update_npt_data = npt_then_edit


@scenario
def concurrent_edit_between_revision_and_load_is_reloaded(ctx):
    ctx.well("C")
    painted_before = len(ctx.painted)
    _edit_during_paint(ctx, ["NPT-K"])
    ctx.tab.auto_update_data()
    ctx.idle()
    assert ctx.tab.concurrent_changes == 1
    assert len(ctx.painted) - painted_before == 2, ctx.painted
    assert ctx.npt()[0] == {"NPT-K": 7.0} and updated(ctx), (ctx.npt(), ctx.status())
    assert ctx.tab._data_rev == ctx.revision("C")


@scenario
def repeated_concurrent_edits_are_never_reported_as_updated(ctx):
    ctx.well("C")
    painted_before = len(ctx.painted)
    _edit_during_paint(ctx, ["NPT-1", "NPT-2", "NPT-3", "NPT-4"])
    ctx.tab.auto_update_data()
    ctx.idle()
    assert ctx.tab.concurrent_changes == 3 and len(ctx.painted) - painted_before == 3
    assert "kept changing" in ctx.status() and not updated(ctx), ctx.status()
    ctx.tab.refresh_now()                            # the user's retry converges
    ctx.idle()
    assert updated(ctx) and ctx.npt()[0] == {"NPT-4": 7.0}


# ---- 12: parity with the M49 synchronous page --------------------------------
@scenario
def async_page_matches_synchronous_page(ctx):
    for key in ("A", "B", "C"):
        ctx.well(key)
        ctx.cost_text()
        async_view = ctx.snapshot()
        assert ctx.tab._data_rev == ctx.revision(key) and updated(ctx)
        ctx.tab._uses_revision_worker = lambda: False
        ctx.tab.refresh_now()
        sync_view = ctx.snapshot()
        del ctx.tab._uses_revision_worker
        assert async_view == sync_view, key
    async_calls = [c for c in ctx.hook.calls if c[0] != MAIN_THREAD]
    assert len(async_calls) >= 6                     # before + verify for each well


@scenario
def revision_is_never_computed_on_the_gui_thread(ctx):
    ctx.well("A")
    ctx.well("B")
    ctx.tab.refresh_now()
    ctx.idle()
    ctx.tab.auto_update_data()
    ctx.idle()
    assert ctx.hook.calls and ctx.off_main_thread(), ctx.hook.calls
    # M47 ownership: each worker read through its own engine, never the GUI's.
    assert all(bind is not ctx.db.engine for bind in ctx.hook.binds)
    assert len({id(bind) for bind in ctx.hook.binds}) == len(ctx.hook.binds)


@scenario
def section_change_mid_hash_restarts_the_cycle(ctx):
    ctx.well("C")
    start = len(ctx.hook.calls)
    gate = ctx.hook.gate(start, honour_cancel=False)
    ctx.tab.auto_update_data()
    assert until(lambda: len(ctx.hook.calls) == start + 1)
    ticket = ctx.tab._rev_worker.ticket
    ctx.tab.on_section_changed(None, {})             # scope change; no cancel of the worker
    painted_before = len(ctx.painted)
    gate.set()
    ctx.idle()
    # The result requested before the change is not painted: a new cycle
    # (before + verify) runs for the new scope.
    assert len(ctx.hook.calls) == start + 3, ctx.hook.calls[start:]
    assert len(ctx.painted) == painted_before + 1 and updated(ctx)
    assert ctx.tab._rev_seq > ticket[1]


@scenario
def generation_change_without_cancel_is_never_painted(ctx):
    # Since M51 every scope change also cancels the running cycle as soon as a view
    # asks for a value, so the scenario above no longer reaches the generation check
    # behind the sequence check.  A generation change that cancels and requests
    # nothing must still never paint the earlier result; a new cycle runs.
    ctx.well("C")
    start = len(ctx.hook.calls)
    gate = ctx.hook.gate(start, honour_cancel=False)
    ctx.tab.auto_update_data()
    assert until(lambda: len(ctx.hook.calls) == start + 1)
    ticket = ctx.tab._rev_worker.ticket
    ctx.tab._generation += 1                         # scope changed; no cancel, no request
    gate.set()
    ctx.idle()
    assert ticket in [t for t, _, _ in ctx.delivered], "the earlier result was not delivered"
    assert len(ctx.hook.calls) == start + 3, ctx.hook.calls[start:]     # old + new cycle (before, verify)
    assert any(t[0] == ctx.tab._generation and t[2] == "before" for t, _, _ in ctx.delivered)
    assert updated(ctx)


# ---- cyclic GC never runs on a worker thread (core/qt_gc.py) -----------------
@scenario
def cyclic_gc_never_runs_on_a_worker_thread(ctx):
    import gc
    threads = []

    def record(phase, info):
        if phase == "start":
            threads.append(threading.get_ident())
    old_threshold = gc.get_threshold()
    gc.callbacks.append(record)
    gc.set_threshold(50, 5, 5)       # automatic GC would now fire constantly, in any thread
    try:
        for key in ("A", "B", "C", "A"):
            ctx.well(key)
            ctx.tab.refresh_now()
            ctx.idle()
        until(lambda: any(ident == MAIN_THREAD for ident in threads), 3000)
    finally:
        gc.callbacks.remove(record)
        gc.set_threshold(*old_threshold)
    worker_collections = [ident for ident in threads if ident != MAIN_THREAD]
    assert worker_collections == [], f"{len(worker_collections)} collections on worker threads"
    assert ctx.off_main_thread() and len(ctx.hook.calls) >= 8


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
        print("M50RESULT " + json.dumps(result), flush=True)


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
