"""M134: NPT event reconciliation — register vs DDR time-log NPT, each event counted once.

Fixture (synthetic) and goldens by hand:

    report r1 (main bore, 1 Apr)   time log  L1 08:00-12:00 NPT 4 h, L2 12:00-14:00 NPT 2 h, L3 14:00-16:00
                                             productive, L4 20:00-22:00 NPT 2 h
                                   register  N1 08:00-14:00 6 h (= L1 ∪ L2 → MATCHED), N2 03:00-05:00 2 h
                                             (REGISTER ONLY)
    no report (1 Apr)              register  N4 20:30-21:00 0.5 h → overlaps L4 by date only → UNCERTAIN
    report r2 (sidetrack, 2 Apr)   time log  L6 09:30-11:00 NPT 1.5 h, L7 23:00-01:00 NPT 2 h (crosses midnight)
                                   register  N3 09:00-11:00 2.5 h (overlaps L6, differs → UNCERTAIN),
                                             N5 23:00-01:00 2 h (= L7 → MATCHED)

Naive sum of both sources = register 13 h + time log 11.5 h = 24.5 h (double counted). Reconciled whole well:
certain = 6 (N1/L1+L2, time-log hours) + 2 (N2) + 2 (N5/L7) = 10.0 h; UNCERTAIN N3/L6 2.5–4.0 h and N4/L4
2.0–2.5 h → 4.5–6.5 h not added. Main bore: N4 excluded (no report), L4 TIME-LOG ONLY → 6 + 2 + 2 = 10.0 h.
"""
from __future__ import annotations

import csv
import json
import os
import sqlite3
import threading
from datetime import date, time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

from core import npt_reconciliation as nr  # noqa: E402
from core.database import DailyReport, NPTReport, TimeLog24H, Wellbore  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402
from tests.test_m123_mse_lineage import _as_admin, _raw  # noqa: E402

D1, D2 = date(2026, 4, 1), date(2026, 4, 2)


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _log(s, rid, a, b, hours, npt, code=""):
    row = TimeLog24H(report_id=rid, time_from=time(*a), time_to=time(*b), duration=hours, is_npt=npt,
                     main_code=code)
    s.add(row)
    s.flush()
    return row.id


def _npt(s, well, rid, day, a, b, hours, code="RIG"):
    row = NPTReport(well_id=well, report_id=rid, npt_date=day, start_time=time(*a), end_time=time(*b),
                    duration_hours=hours, npt_category="Equipment", npt_code=code, npt_description="SYN event")
    s.add(row)
    s.flush()
    return row.id


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = tmp_path / "m134.sqlite"
    manager = _open(path, tmp_path, monkeypatch)
    ids = _seed(manager)
    well, bore = ids["A"]
    out = {"manager": manager, "well": well, "bore": bore, "path": path, "tmp": tmp_path}
    with manager.session_scope() as s:
        st = Wellbore(well_id=well, name="SYN-A ST1", wellbore_type="sidetrack")
        s.add(st)
        s.flush()
        r1 = DailyReport(well_id=well, wellbore_id=bore, report_date=D1, report_number=1)
        r2 = DailyReport(well_id=well, wellbore_id=st.id, report_date=D2, report_number=2)
        s.add_all([r1, r2])
        s.flush()
        out.update(sidetrack=st.id, r1=r1.id, r2=r2.id)
        out["L1"] = _log(s, r1.id, (8, 0), (12, 0), 4.0, True, "RIG")
        out["L2"] = _log(s, r1.id, (12, 0), (14, 0), 2.0, True, "RIG")
        out["L3"] = _log(s, r1.id, (14, 0), (16, 0), 2.0, False)
        out["L4"] = _log(s, r1.id, (20, 0), (22, 0), 2.0, True, "WAIT")
        out["L6"] = _log(s, r2.id, (9, 30), (11, 0), 1.5, True, "RIG")
        out["L7"] = _log(s, r2.id, (23, 0), (1, 0), 2.0, True, "RIG")
        out["N1"] = _npt(s, well, r1.id, D1, (8, 0), (14, 0), 6.0)
        out["N2"] = _npt(s, well, r1.id, D1, (3, 0), (5, 0), 2.0)
        out["N4"] = _npt(s, well, None, D1, (20, 30), (21, 0), 0.5, "WAIT")
        out["N3"] = _npt(s, well, r2.id, D2, (9, 0), (11, 0), 2.5)
        out["N5"] = _npt(s, well, r2.id, D2, (23, 0), (1, 0), 2.0)
    _as_admin(manager, path)
    yield out
    manager.close()


def _by_key(recon):
    return {(g.register_ids, g.log_ids): g for g in recon.groups}


def test_whole_well_statuses_and_hand_goldens(env):
    recon = nr.reconcile_scope(env["manager"], env["well"])
    groups = _by_key(recon)
    e = env
    assert groups[((e["N1"],), (e["L1"], e["L2"]))].status == nr.MATCHED
    assert groups[((e["N1"],), (e["L1"], e["L2"]))].counted_hours == 6.0
    assert groups[((e["N2"],), ())].status == nr.REGISTER_ONLY
    assert groups[((e["N5"],), (e["L7"],))].status == nr.MATCHED            # crosses midnight, still exact
    n3 = groups[((e["N3"],), (e["L6"],))]
    assert (n3.status, n3.counted_hours, n3.once_hours, n3.both_hours) == (nr.UNCERTAIN, None, 2.5, 4.0)
    n4 = groups[((e["N4"],), (e["L4"],))]
    assert n4.status == nr.UNCERTAIN and "date only" in " ".join(n4.notes)
    assert e["L3"] not in {lid for g in recon.groups for lid in g.log_ids}     # productive time is not NPT
    totals = recon.totals()
    assert totals["certain_hours"] == 10.0                                    # not the naive 24.5 h
    assert (totals["uncertain_low"], totals["uncertain_high"]) == (4.5, 6.5)
    assert "Reconciled NPT 10.00 h" in recon.summary() and "4.50–6.50 h more" in recon.summary()


def test_wellbore_scope_excludes_unlinked_register_events(env):
    bore = nr.reconcile_scope(env["manager"], env["well"], env["bore"])
    groups = _by_key(bore)
    assert groups[((), (env["L4"],))].status == nr.LOG_ONLY
    assert bore.totals()["certain_hours"] == 10.0 and bore.totals()["uncertain_groups"] == 0
    assert any(f"NPT #{env['N4']}" in line and "not attributed" in line for line in bore.excluded)
    side = nr.reconcile_scope(env["manager"], env["well"], env["sidetrack"])
    assert side.totals()["certain_hours"] == 2.0 and side.totals()["uncertain_groups"] == 1
    assert all(r.id not in (env["N1"], env["N2"]) for g in side.groups for r in g.register)


def test_a_shared_time_log_row_is_uncertain_and_differences_are_noted(env):
    with env["manager"].session_scope() as s:
        n6 = _npt(s, env["well"], env["r1"], D1, (13, 0), (14, 0), 1.0)       # overlaps L2 with N1
        s.get(NPTReport, env["N5"]).npt_code = "WOW"
        s.get(NPTReport, env["N5"]).duration_hours = 2.5
    groups = _by_key(nr.reconcile_scope(env["manager"], env["well"]))
    shared = groups[((env["N1"], n6), (env["L1"], env["L2"]))]
    assert shared.status == nr.UNCERTAIN and "2 register events overlap" in " ".join(shared.notes)
    n5 = groups[((env["N5"],), (env["L7"],))]
    assert n5.status == nr.MATCHED and n5.counted_hours == 2.0
    assert "durations differ" in " ".join(n5.notes) and "codes differ" in " ".join(n5.notes)


def test_an_unknown_duration_is_never_zero(env):
    with env["manager"].session_scope() as s:
        s.get(TimeLog24H, env["L7"]).duration = None
    recon = nr.reconcile_scope(env["manager"], env["well"])
    n5 = _by_key(recon)[((env["N5"],), (env["L7"],))]
    assert n5.status == nr.MATCHED and n5.counted_hours is None
    assert recon.totals()["certain_hours"] == 8.0 and recon.totals()["unknown_duration_groups"] == 1
    assert "without a valid duration are not added" in recon.summary()


def test_decisions_are_audited_append_only_and_go_stale(env):
    e, m = env, env["manager"]
    key = ((e["N3"],), (e["L6"],))
    with pytest.raises(nr.ReconciliationError, match="evidence"):
        nr.record_decision(m, e["well"], *key, decision=nr.SAME_EVENT, evidence=" ", reason="r")
    with pytest.raises(nr.ReconciliationError, match="already certain"):
        nr.record_decision(m, e["well"], (e["N1"],), (e["L1"], e["L2"]), decision=nr.SAME_EVENT,
                           evidence="SYN DDR", reason="r")
    with pytest.raises(nr.ReconciliationError, match="must be one of"):
        nr.record_decision(m, e["well"], *key, decision="MAYBE", evidence="x", reason="r")
    first = nr.record_decision(m, e["well"], *key, decision=nr.SAME_EVENT, evidence="SYN DDR r2 remarks",
                               reason="the register entry was rounded")
    recon = nr.reconcile_scope(m, e["well"])
    group = _by_key(recon)[key]
    assert group.status == nr.CONFIRMED_SAME and group.counted_hours == 1.5 and group.decision.id == first
    assert "admin" in " ".join(group.notes) and "rounded" in " ".join(group.notes)
    assert recon.totals()["certain_hours"] == 11.5
    assert (recon.totals()["uncertain_low"], recon.totals()["uncertain_high"]) == (2.0, 2.5)
    audit = _raw(e["path"], "SELECT details FROM audit_logs WHERE action='npt_event_decision'")
    assert len(audit) == 1 and json.loads(audit[0][0])["decision_id"] == first
    for sql in ("UPDATE npt_event_decisions SET reason='forged' WHERE id=?",
                "UPDATE npt_event_decisions SET decision='DIFFERENT_EVENTS' WHERE id=?",
                "DELETE FROM npt_event_decisions WHERE id=?"):
        with pytest.raises(sqlite3.DatabaseError):
            _raw(e["path"], sql, first)
    with m.session_scope() as s:                                 # the time log is edited after the decision
        s.get(TimeLog24H, e["L6"]).duration = 2.0
    group = _by_key(nr.reconcile_scope(m, e["well"]))[key]
    assert group.status == nr.UNCERTAIN and f"decision #{first} is STALE" in " ".join(group.notes)
    second = nr.record_decision(m, e["well"], *key, decision=nr.DIFFERENT_EVENTS, evidence="SYN crew log",
                                reason="two separate stoppages")
    group = _by_key(nr.reconcile_scope(m, e["well"]))[key]
    assert group.status == nr.CONFIRMED_DIFFERENT and group.counted_hours == 4.5 and group.decision.id == second
    assert _raw(e["path"], "SELECT COUNT(*) FROM npt_event_decisions")[0][0] == 2     # nothing overwritten


def test_a_decision_needs_an_identified_user_and_edit_rights(env, monkeypatch):
    from core.authorization import AuthorizationError
    from tests.test_m96_persistence_audit import _open as open_as

    env["manager"].close()
    viewer = open_as(env["path"], env["tmp"], monkeypatch, principal="viewer", permissions={})
    try:
        with pytest.raises((AuthorizationError, nr.ReconciliationError)):
            nr.record_decision(viewer, env["well"], (env["N3"],), (env["L6"],), decision=nr.SAME_EVENT,
                               evidence="x", reason="y")
    finally:
        viewer.close()
    assert _raw(env["path"], "SELECT COUNT(*) FROM npt_event_decisions")[0][0] == 0


def test_decisions_leave_with_their_well_only(env):
    nr.record_decision(env["manager"], env["well"], (env["N3"],), (env["L6"],), decision=nr.SAME_EVENT,
                       evidence="SYN", reason="r")
    assert env["manager"].delete_daily_report(env["r2"])            # a report delete keeps the decision
    assert _raw(env["path"], "SELECT COUNT(*) FROM npt_event_decisions")[0][0] == 1
    assert env["manager"].delete_well(env["well"])
    assert _raw(env["path"], "SELECT COUNT(*) FROM npt_event_decisions")[0][0] == 0


class _Owner:
    def __init__(self):
        self.opened = []

    def open_report_by_id(self, report_id):
        self.opened.append(report_id)
        return True


def test_the_panel_shows_drills_down_decides_and_exports(app, env, tmp_path):
    from tabs.npt_reconciliation_panel import STATUS_COLOUR, NptReconciliationPanel

    owner = _Owner()
    panel = NptReconciliationPanel(env["manager"], owner=owner)
    try:
        panel.set_scope(env["well"])
        assert panel.wait()                                          # background read (M103 runner)
        assert panel.table.rowCount() == 5 and "Reconciled NPT 10.00 h" in panel.totals_label.text()
        statuses = [panel.table.item(i, 0).text() for i in range(5)]
        index = statuses.index(nr.MATCHED)
        assert panel.table.item(index, 0).foreground().color().name() == STATUS_COLOUR[nr.MATCHED]
        panel.table.selectRow(index)
        assert not panel.decide_btn.isEnabled() and panel.decide_selected(nr.SAME_EVENT, "e", "r") is None
        assert panel.open_selected_report() and owner.opened == [env["r1"]]
        groups = panel.recon.groups
        uncertain = next(i for i, g in enumerate(groups) if g.register_ids == (env["N3"],))
        panel.table.selectRow(uncertain)
        assert panel.decide_btn.isEnabled()
        assert panel.decide_selected(nr.SAME_EVENT, "", "r") is None and "evidence" in panel.status.text()
        decision = panel.decide_selected(nr.SAME_EVENT, "SYN DDR", "rounded")
        assert decision and panel.wait() and "Reconciled NPT 11.50 h" in panel.totals_label.text()
        path = tmp_path / "npt.csv"
        assert panel.export_to(str(path)) == 5
        rows = list(csv.reader(path.open(encoding="utf-8")))
        flat = [c for r in rows for c in r]
        assert rows[0] == ["NPT event reconciliation", nr.RECON_METHOD] and nr.CONFIRMED_SAME in flat
        assert any("Reconciled NPT 11.50 h" in c for c in flat)
        panel.set_scope(env["well"], env["bore"])
        assert panel.wait() and "Excluded from this scope" in panel.excluded_label.text()
    finally:
        panel.shutdown()
        panel.deleteLater()


def test_reconciliation_runs_on_a_worker_and_a_late_result_is_never_shown(app, env, monkeypatch):
    from tabs import npt_reconciliation_panel
    from tabs.npt_reconciliation_panel import NptReconciliationPanel

    gate, entered, threads, real = threading.Event(), threading.Event(), [], nr.reconcile_scope

    def slow(db, well, bore=None):
        threads.append(threading.current_thread() is threading.main_thread())
        entered.set()
        gate.wait(10)
        return real(db, well, bore)

    monkeypatch.setattr(npt_reconciliation_panel.nr, "reconcile_scope", slow)
    panel = NptReconciliationPanel(env["manager"])
    try:
        panel.set_scope(env["well"])
        assert panel.jobs.synchronous is False and panel.jobs.busy
        assert entered.wait(10)
        panel.set_scope(None)
        gate.set()
        assert panel.wait()
        assert threads == [False] and panel.recon is None and panel.table.rowCount() == 0
        assert panel.jobs.rejected["superseded"] == 1 and panel.scope_label.text().startswith("NOT ASSESSED")
    finally:
        panel.shutdown()
        panel.deleteLater()


def test_w12_hosts_the_panel_follows_the_selection_and_cleans_up(app, env, monkeypatch):
    from tabs import w12_Analysis
    from tabs.npt_reconciliation_panel import NptReconciliationPanel

    tab = w12_Analysis.AnalysisWidget(db_manager=env["manager"])
    try:
        panel = tab.npt_reconciliation_panel
        assert isinstance(panel, NptReconciliationPanel) and panel.owner is tab
        tab.on_well_changed(env["well"], {"name": "SYN-A"})
        assert panel.wait() and panel.table.rowCount() == 5
        tab.on_wellbore_changed(env["sidetrack"], {"name": "SYN-A ST1"})
        assert panel.wait() and panel.table.rowCount() == 2
        tab.on_selection_cleared()
        assert panel.well_id is None and panel.table.rowCount() == 0
        calls = []
        # on the class: an instance attribute restored by monkeypatch would be a bound-method cycle (D49 / M50)
        monkeypatch.setattr(NptReconciliationPanel, "shutdown",
                            lambda _panel, timeout_ms=5000: calls.append(timeout_ms) or True)
    finally:
        tab.cleanup()
        tab.deleteLater()
    assert calls == [5000]


def test_an_unlinked_register_event_is_never_matched_even_when_its_interval_is_exact(env):
    """Same day, exactly the interval of one time-log row, but no daily report link: the date alone does not
    prove it is that DDR's event - UNCERTAIN, never MATCHED, never added to the certain hours."""
    with env["manager"].session_scope() as s:
        l8 = _log(s, env["r1"], (17, 0), (18, 0), 1.0, True, "RIG")
        n7 = _npt(s, env["well"], None, D1, (17, 0), (18, 0), 1.0)
    recon = nr.reconcile_scope(env["manager"], env["well"])
    group = _by_key(recon)[((n7,), (l8,))]
    assert group.status == nr.UNCERTAIN and group.counted_hours is None
    assert "date only" in " ".join(group.notes)
    assert (group.once_hours, group.both_hours) == (1.0, 2.0)
    assert recon.totals()["certain_hours"] == 10.0


@pytest.mark.parametrize("actor", [(None, "unknown"), (987654, "ghost")])
def test_a_decision_without_an_identified_user_of_this_database_is_refused(env, monkeypatch, actor):
    """Edit rights alone are not enough: the confirming user must be a user row of this database."""
    manager = env["manager"]
    monkeypatch.setattr(type(manager), "_audit_actor", lambda self: actor)     # class-level patch (M50)
    with pytest.raises(nr.ReconciliationError, match="identified user"):
        nr.record_decision(manager, env["well"], (env["N3"],), (env["L6"],), decision=nr.SAME_EVENT,
                           evidence="SYN DDR r2 remarks", reason="r")
    assert _raw(env["path"], "SELECT COUNT(*) FROM npt_event_decisions")[0][0] == 0
    assert _raw(env["path"], "SELECT COUNT(*) FROM audit_logs WHERE action='npt_event_decision'")[0][0] == 0
