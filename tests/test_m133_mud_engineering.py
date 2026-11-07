"""M133: mud evaluation from the DDR mud reports (W12 Analysis › Mud evaluation).

Goldens by hand from the field formulae, independent of the code: MW 75 pcf / 7.48052 = 10.026 ppg; recorded
PV 20 cP / YP 10 lbf/100 ft² imply θ600 = 50, θ300 = 30, so n = 3.32 log10(50/30) = 0.7365 and
K = 510·30 / 511^0.7365 = 154.8 cP·s^(n−1); gels 12 / 6 = 2; retort 12 + 3 + 85 = 100 %; oil part of the
OWR 100·3 / 88 = 3.41 %; θ3 = 5, θ6 = 7 → LSRYP 2·5 − 7 = 3 lbf/100 ft².
"""
from __future__ import annotations

import math
import os
import re
import threading
from datetime import date, time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

from core import calculation_history as ch  # noqa: E402
from core import mud_engineering as me  # noqa: E402
from core.database import DailyReport, MudReport, Wellbore  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402

RECORDED = dict(mw=75.0, pv=20.0, yp=10.0, gel_10s=6.0, gel_10m=12.0, solid_percent=12.0, oil_percent=3.0,
                water_percent=85.0, fl=4.5, ph=9.5)


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def env(tmp_path, monkeypatch):
    manager = _open(tmp_path / "m133.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    well, bore = ids["A"]
    out = {"manager": manager, "well": well, "bore": bore, "other": ids["B"][0], "path": tmp_path / "m133.sqlite"}
    with manager.session_scope() as s:
        st = Wellbore(well_id=well, name="SYN-A ST1", wellbore_type="sidetrack")
        s.add(st)
        s.flush()
        r1 = DailyReport(well_id=well, wellbore_id=bore, report_date=date(2026, 4, 1), report_number=1)
        r2 = DailyReport(well_id=well, wellbore_id=st.id, report_date=date(2026, 4, 2), report_number=2)
        s.add_all([r1, r2])
        s.flush()
        m1 = MudReport(well_id=well, report_id=r1.id, report_date=date(2026, 4, 1), sample_time=time(6, 0),
                       mud_type="WBM", **RECORDED)
        m2 = MudReport(well_id=well, report_id=r2.id, report_date=date(2026, 4, 2), mud_type="WBM", mw=78.0)
        legacy = MudReport(well_id=well, report_id=None, report_date=date(2026, 3, 30), mw=74.0)
        foreign = MudReport(well_id=out["other"], report_id=None, report_date=date(2026, 4, 1), mw=70.0)
        s.add_all([m1, m2, legacy, foreign])
        s.flush()
        out.update(sidetrack=st.id, r1=r1.id, r2=r2.id, m1=m1.id, m2=m2.id, legacy=legacy.id, foreign=foreign.id)
    yield out
    manager.close()


def _sample(env, key="m1"):
    return me.load_sample(env["manager"], env[key])


def test_scope_whole_well_wellbore_and_legacy_rows(env):
    whole = me.load_samples(env["manager"], env["well"])
    assert [s.id for s in whole] == [env["legacy"], env["m1"], env["m2"]]          # another well's row is absent
    assert [s.link for s in whole] == [me.UNLINKED, me.LINKED, me.LINKED]
    assert [s.id for s in me.load_samples(env["manager"], env["well"], env["bore"])] == [env["m1"]]
    assert [s.id for s in me.load_samples(env["manager"], env["well"], env["sidetrack"])] == [env["m2"]]


def test_classes_and_hand_goldens_from_the_recorded_values(env):
    ev = me.evaluate(_sample(env).frozen())
    row = ev.row
    assert (row("mw").cls, row("mw").value, row("mw").unit) == (me.LAB, 75.0, "pcf")
    assert "DDR mud report #" in row("mw").source and f"DDR #{env['r1']}" in row("mw").source
    assert row("mw_ppg").cls == me.DERIVED and row("mw_ppg").value == pytest.approx(10.026, abs=5e-4)
    assert (row("t600_implied").value, row("t300_implied").value) == (50.0, 30.0)
    assert row("n").value == pytest.approx(0.7365, abs=1e-4) and row("n").cls == me.DERIVED
    assert row("k").value == pytest.approx(510 * 30 / 511 ** (3.32 * math.log10(50 / 30)), rel=1e-12)
    assert row("k").value == pytest.approx(154.8, abs=0.05)
    assert row("gel_ratio").value == 2.0 and row("pv_yp").value == 2.0
    assert row("retort_total").value == 100.0 and row("owr_oil").value == pytest.approx(3.409, abs=1e-3)
    # not recorded → UNKNOWN with no value (never 0); no dial reading is invented
    assert (row("chloride").cls, row("chloride").value) == (me.UNKNOWN, None)
    assert (row("t600").cls, row("t600").value) == (me.UNKNOWN, None)
    assert (row("lsryp").cls, row("lsryp").value) == (me.UNKNOWN, None)
    assert "NOT ASSESSED" in ev.notes[-1]


def test_unknown_mud_weight_is_not_zero_and_missing_rheology_is_unknown(env):
    ev = me.evaluate(_sample(env, "m2").frozen())
    assert ev.row("mw_ppg").value == pytest.approx(78 / 7.48052)
    assert (ev.row("n").cls, ev.row("n").value) == (me.UNKNOWN, None)
    assert (ev.row("retort_total").cls, ev.row("retort_total").value) == (me.UNKNOWN, None)
    blank = me.evaluate({**_sample(env, "m2").frozen(), "values": {}})
    assert (blank.row("mw_ppg").cls, blank.row("mw_ppg").value) == (me.UNKNOWN, None)


def test_typed_readings_carry_their_class_and_never_replace_recorded_values(env):
    readings = {"t600": {"value": "52", "class": me.LAB, "reference": "lab sheet 7"},
                "t300": {"value": 31, "class": me.ASSUMED},
                "t3": {"value": 5, "class": me.LAB, "reference": "lab sheet 7"},
                "t6": {"value": 7, "class": me.LAB, "reference": "lab sheet 7"}}
    ev = me.evaluate(_sample(env).frozen(), readings)
    assert ev.row("t600").cls == me.LAB and "lab sheet 7" in ev.row("t600").source
    assert ev.row("t300").cls == me.ASSUMED
    assert (ev.row("pv_readings").value, ev.row("yp_readings").value) == (21.0, 10.0)
    assert ev.row("pv_readings").cls == me.DERIVED_ASSUMED and ev.row("n").cls == me.DERIVED_ASSUMED
    assert ev.row("pv").value == 20.0 and ev.row("pv").cls == me.LAB                  # recorded value kept
    assert any("differs from the recorded PV (20)" in note for note in ev.notes)
    assert ev.row("t600_implied") is None                                           # readings, not PV/YP
    lsryp = ev.row("lsryp")
    assert (lsryp.value, lsryp.cls) == (3.0, me.DERIVED) and "NOT a Herschel-Bulkley" in lsryp.source


@pytest.mark.parametrize("entry, reason", [
    ({"value": 50}, "mark it LAB (measured) or ASSUMED"),
    ({"value": 50, "class": me.LAB}, "needs its lab reference"),
    ({"value": -1, "class": me.ASSUMED}, "cannot be negative"),
    ({"value": "abc", "class": me.ASSUMED}, "not a number"),
])
def test_an_untagged_or_unreferenced_reading_is_refused(env, entry, reason):
    with pytest.raises(me.MudEvaluationError, match=re.escape(reason)):
        me.evaluate(_sample(env).frozen(), {"t600": entry})


def test_hb_is_never_assessed_from_bingham_or_power_law(env):
    readings = {key: {"value": v, "class": me.ASSUMED} for key, v in
                (("t600", 52), ("t300", 31), ("t200", 24), ("t100", 16), ("t6", 7), ("t3", 5))}
    results = me.evaluate(_sample(env).frozen(), readings).results()
    assert results["hb"]["value"] is None and results["hb"]["source"] == me.HB_STATUS
    assert not any("herschel" in key.lower() or key.startswith("hb_") for key in results if key != "hb")


def test_save_checks_well_and_wellbore_and_history_re_runs(env):
    sample = _sample(env)
    with pytest.raises(me.MudEvaluationError, match="belongs to well"):
        me.save_evaluation(env["manager"], sample, well_id=env["other"])
    with pytest.raises(me.MudEvaluationError, match="not attributed"):
        me.save_evaluation(env["manager"], sample, well_id=env["well"], wellbore_id=env["sidetrack"])
    legacy = _sample(env, "legacy")
    with pytest.raises(me.MudEvaluationError, match="not attributed"):
        me.save_evaluation(env["manager"], legacy, well_id=env["well"], wellbore_id=env["bore"])
    case = me.save_evaluation(env["manager"], sample, well_id=env["well"], wellbore_id=env["bore"])
    assert (case["method"], case["method_version"], case["wellbore_id"]) == (me.MUD_METHOD, me.MUD_VERSION,
                                                                            env["bore"])
    assert case["inputs"]["sample"]["mud_report_id"] == env["m1"] and case["results"]["hb"]["class"] == me.UNKNOWN
    entries = [e for e in ch.load_history(env["manager"], well_id=env["well"]) if e.method == me.MUD_METHOD]
    assert len(entries) == 1 and entries[0].scope == ch.MUD_SCOPE
    outcome = ch.recalculate_entry(entries[0], env["manager"])
    assert outcome["status"] == "MATCH" and "mud report unchanged since saving" in outcome["detail"]
    with env["manager"].session_scope() as s:                  # the mud report is edited after saving
        s.get(MudReport, env["m1"]).pv = 22.0
    outcome = ch.recalculate_entry(entries[0], env["manager"])
    assert outcome["status"] == "MATCH" and "DDR SOURCE CHANGED: pv 20.0 → 22.0" in outcome["detail"]
    rerun = ch.save_recalculation(env["manager"], entries[0], outcome)        # a NEW linked case
    assert rerun["id"] != case["id"] and rerun["results"] == case["results"] and "SOURCE CHANGED" in rerun["note"]
    with env["manager"].session_scope() as s:
        s.delete(s.get(MudReport, env["m1"]))
    outcome = ch.recalculate_entry(entries[0], env["manager"])
    assert outcome["status"] == "MATCH" and "no longer exists" in outcome["detail"]


def test_history_routes_the_mud_method_and_versions_are_strict(env):
    assert ch.MUD_METHOD == me.MUD_METHOD
    assert me.verify_case(env["manager"], {"sample": {}}, {}, "M999")["status"] == "NOT_REPRODUCIBLE"
    assert me.verify_case(env["manager"], {"sample": "x"}, {}, me.MUD_VERSION)["status"] == "UNREADABLE"
    inputs = me.frozen_inputs(_sample(env), {}, well_id=env["well"], wellbore_id=None)
    results = me.evaluate(inputs["sample"]).results()
    results["n"]["value"] += 0.01                                # a tampered stored value is reported
    out = me.verify_case(env["manager"], inputs, results, me.MUD_VERSION)
    assert out["status"] == "DIFFERENT" and [d["field_id"] for d in out["differences"]] == ["n"]


class _Owner:
    def __init__(self):
        self.opened = []

    def open_report_by_id(self, report_id):
        self.opened.append(report_id)
        return True


def test_the_panel_lists_classifies_opens_the_ddr_and_saves(app, env):
    from tabs.mud_engineering_panel import CLASS_COLOUR, MudEvaluationPanel

    owner = _Owner()
    panel = MudEvaluationPanel(env["manager"], owner=owner)
    try:
        panel.set_scope(env["well"])
        assert panel.wait()                                      # background read (M103 runner)
        assert panel.samples_table.rowCount() == 3 and "1 without a DDR link" in panel.scope_label.text()
        panel.select(0)                                          # the legacy row: no DDR to open
        assert panel.evaluation is not None and not panel.open_btn.isEnabled()
        assert panel.open_selected_report() is False and owner.opened == []
        panel.select(1)
        rows = {panel.properties_table.item(i, 0).text(): i for i in range(panel.properties_table.rowCount())}
        mw_ppg = rows["Mud weight"] if panel.properties_table.item(rows["Mud weight"], 2).text() == "ppg" else None
        assert mw_ppg is not None and panel.properties_table.item(mw_ppg, 3).text() == me.DERIVED
        assert panel.properties_table.item(rows["Chloride"], 1).text() == "—"
        assert panel.properties_table.item(rows["Chloride"], 3).foreground().color().name() == \
            CLASS_COLOUR[me.UNKNOWN]
        assert me.HB_STATUS in panel.hb_label.text()
        assert panel.open_btn.isEnabled() and panel.open_selected_report() and owner.opened == [env["r1"]]
        panel.set_reading("t600", "52", None)                    # untagged → refused, nothing shown
        assert panel.evaluate_selected() is None and "mark it LAB" in panel.status.text()
        assert panel.properties_table.rowCount() == 0
        panel.set_reading("t600", "52", me.LAB, "sheet 7")
        panel.set_reading("t300", "31", me.ASSUMED)
        ev = panel.evaluate_selected()
        assert ev.row("n").cls == me.DERIVED_ASSUMED and "differs from the recorded PV" in panel.status.text()
        case = panel.save_selected()
        assert case and case["wellbore_id"] is None and case["inputs"]["readings"]["t300"]["class"] == me.ASSUMED
        assert f"calculation case #{case['id']}" in panel.status.text()
        panel.set_scope(env["well"], env["sidetrack"])
        assert panel.wait() and panel.samples_table.rowCount() == 1 and panel.properties_table.rowCount() == 0
    finally:
        panel.shutdown()
        panel.deleteLater()


def test_a_viewer_cannot_save_an_evaluation(app, env, tmp_path, monkeypatch):
    from tabs.mud_engineering_panel import MudEvaluationPanel
    from tests.test_m96_persistence_audit import _open as open_as

    env["manager"].close()
    viewer = open_as(env["path"], tmp_path, monkeypatch, principal="viewer", permissions={})
    panel = MudEvaluationPanel(viewer)
    try:
        panel.set_scope(env["well"], env["bore"])
        assert panel.wait()
        panel.select(0)
        assert panel.save_selected() is None and panel.status.text().startswith("Not saved:")
    finally:
        panel.shutdown()
        panel.deleteLater()
        viewer.close()


def test_samples_are_read_on_a_worker_and_a_late_result_is_never_shown(app, env, monkeypatch):
    """M51/M103: no GUI-thread SQL; a result that arrives after the scope was cleared is rejected by state."""
    from tabs import mud_engineering_panel
    from tabs.mud_engineering_panel import MudEvaluationPanel

    gate, entered, threads, real = threading.Event(), threading.Event(), [], me.load_samples

    def slow(db, well, bore=None):
        threads.append(threading.current_thread() is threading.main_thread())
        entered.set()
        gate.wait(10)
        return real(db, well, bore)

    monkeypatch.setattr(mud_engineering_panel.me, "load_samples", slow)
    panel = MudEvaluationPanel(env["manager"])
    try:
        panel.set_scope(env["well"])
        assert panel.jobs.synchronous is False and panel.jobs.busy and "loading" in panel.scope_label.text()
        assert entered.wait(10)
        panel.set_scope(None)                                    # cleared while the worker still reads
        gate.set()
        assert panel.wait()
        assert threads == [False] and panel.samples == [] and panel.samples_table.rowCount() == 0
        assert panel.jobs.rejected["superseded"] == 1 and panel.scope_label.text().startswith("NOT ASSESSED")
    finally:
        panel.shutdown()
        panel.deleteLater()


def test_w12_hosts_the_panel_follows_the_selection_and_cleans_up(app, env, monkeypatch):
    from tabs import w12_Analysis
    from tabs.mud_engineering_panel import MudEvaluationPanel

    tab = w12_Analysis.AnalysisWidget(db_manager=env["manager"])
    try:
        assert isinstance(tab.mud_panel, MudEvaluationPanel) and tab.mud_panel.owner is tab
        titles = [tab.analysis_tabs.tabText(i) for i in range(tab.analysis_tabs.count())]
        assert any("Mud evaluation" in t for t in titles)
        tab.on_well_changed(env["well"], {"name": "SYN-A"})
        assert tab.mud_panel.wait() and tab.mud_panel.samples_table.rowCount() == 3
        tab.on_wellbore_changed(env["bore"], {"name": "SYN-A"})
        assert tab.mud_panel.wait() and tab.mud_panel.samples_table.rowCount() == 1
        tab.on_selection_cleared()
        assert tab.mud_panel.well_id is None and tab.mud_panel.samples_table.rowCount() == 0
        calls = []
        # on the class: an instance attribute restored by monkeypatch would be a bound-method cycle (D49 / M50)
        monkeypatch.setattr(MudEvaluationPanel, "shutdown",
                            lambda _panel, timeout_ms=5000: calls.append(timeout_ms) or True)
    finally:
        tab.cleanup()
        tab.deleteLater()
    assert calls == [5000]
