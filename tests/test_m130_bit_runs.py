"""M130: bit run workbench (D47).

D47: the W12 "Bit Run Cost Comparison" treated every daily drilling-parameter row as a bit run, so a
three-day run was costed three times (each with the whole bit cost and trip time) against its cumulative
depth-in-to-depth-out of that day, and "best" compared those rows; it seeded a rig rate of 40 000 /day, a trip
of 6 h and a bit cost of 2 000 in no stated currency, and runs without depths or hours silently disappeared.

Goldens (by hand, independent of the code): bit 1 = 100 + 150 m drilled in 10 + 12 h; bit 2 = depth 350 →
520 m (daily drilled incomplete) in 8 + 6 h. Scenario USD, bit cost 15 000, rig 48 000 /day (2 000 /h),
trip 8 h: bit 1 = (15 000 + 2 000 x 30) / 250 = 300.00 USD/m; bit 2 = (15 000 + 2 000 x 22) / 170 = 347.06.
"""
from __future__ import annotations

import csv
import os
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

from core import analysis_evidence as ev  # noqa: E402
from core import bit_runs as br  # noqa: E402
from core import calculation_history as ch  # noqa: E402
from core import operational_analysis as oa  # noqa: E402
from core.database import DailyReport, DrillingParameters, Wellbore  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402

D = [date(2026, 3, d) for d in (1, 2, 3, 4, 5)]
SCENARIO = {"currency": "USD", "bit_cost": 15000.0, "rig_rate_per_day": 48000.0, "trip_hours": 8.0}


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _param(s, well, rid, day, bit, size, d_in, d_out, drilled, hours, rerun=1):
    row = DrillingParameters(well_id=well, report_id=rid, report_date=day, bit_no=bit, bit_rerun=rerun,
                             bit_size=size, bit_type="PDC", depth_in=d_in, depth_out=d_out, bit_drilled=drilled,
                             hours_on_bottom=hours)
    s.add(row)
    s.flush()
    return row.id


@pytest.fixture
def env(tmp_path, monkeypatch):
    manager = _open(tmp_path / "m130.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    well, bore = ids["A"]
    out = {"manager": manager, "well": well, "bore": bore, "other": ids["B"][0], "path": tmp_path / "m130.sqlite"}
    with manager.session_scope() as s:
        st = Wellbore(well_id=well, name="SYN-A ST1", wellbore_type="sidetrack")
        s.add(st)
        s.flush()
        out["sidetrack"] = st.id
        reports = []
        for n, (day, wb) in enumerate(((D[0], bore), (D[1], bore), (D[2], bore), (D[3], bore), (D[4], st.id)), 1):
            r = DailyReport(well_id=well, wellbore_id=wb, report_date=day, report_number=n)
            s.add(r)
            s.flush()
            reports.append(r.id)
        out["reports"] = reports
        r1, r2, r3, r4, r5 = reports
        out["rows"] = [
            _param(s, well, r1, D[0], "1", 12.25, 100, 200, 100, 10),
            _param(s, well, r2, D[1], "1", 12.25, 100, 350, 150, 12),
            _param(s, well, r3, D[2], "2", 12.25, 350, 470, 120, 8),
            _param(s, well, r4, D[3], "2", 12.25, 350, 520, None, 6),     # drilled not recorded
            _param(s, well, r4, D[3], "4", 12.25, 520, 530, 10, None),    # same-day bit change, hours unknown
            _param(s, well, r5, D[4], "ST-1", 8.5, 900, 980, 80, 5),      # sidetrack, 16 m/h: fastest of all
        ]
    yield out
    manager.close()


def _runs(env, wellbore=None):
    return {r.key: r for r in br.load_runs(env["manager"], env["well"], wellbore)}


def test_runs_lifecycle_and_completeness_from_the_ddr_rows(env):
    runs = _runs(env, env["bore"])
    one, two, four = runs["1 / rerun 1"], runs["2 / rerun 1"], runs["4 / rerun 1"]
    assert (one.footage, one.footage_basis, one.hours) == (250.0, "sum of daily drilled", 22.0)
    assert one.rop == pytest.approx(250 / 22) and one.complete
    assert (two.footage, two.footage_basis, two.hours) == (170.0, "depth out - depth in", 14.0) and two.complete
    assert four.footage == 10.0 and four.hours is None and not four.complete and four.rop is None
    assert any("hours on bottom" in m for m in four.missing)
    assert one.lifecycle == br.SUPERSEDED and "bit 2 (rerun 1) is recorded from 2026-03-03" in one.lifecycle_detail
    assert two.lifecycle == br.SUPERSEDED and "bit 4" in two.lifecycle_detail          # same-day change, later row
    assert four.lifecycle == br.OPEN and "last reported 2026-03-04" in four.lifecycle_detail
    assert "ST-1 / rerun 1" not in runs                                                 # another wellbore's DDR
    assert one.reports == (env["reports"][0], env["reports"][1]) and one.rows == tuple(env["rows"][:2])


def test_whole_well_scope_includes_the_sidetrack_and_wellbore_scope_does_not(env):
    whole, side = _runs(env), _runs(env, env["sidetrack"])
    assert set(side) == {"ST-1 / rerun 1"} and "ST-1 / rerun 1" in whole and len(whole) == 4


def test_operational_analysis_uses_the_same_runs(env):
    result = oa.analyze(env["manager"], ev.AnalysisScope(well_id=env["well"], wellbore_id=env["bore"]))
    columns, rows = result.tables["bit_runs"]
    by_bit = {r[0]: dict(zip(columns, r)) for r in rows}
    for key, run in _runs(env, env["bore"]).items():
        row = by_bit[run.bit_no]
        assert (row["Footage (m)"], row["Hours on bottom"], row["ROP (m/h)"], row["Footage basis"]) == \
               (run.footage, run.hours, run.rop, run.footage_basis)


def test_cost_per_metre_goldens_and_like_for_like_ranking(env):
    runs = list(_runs(env, env["bore"]).values())
    outcomes = {r.key: br.cost_per_length(r.figures(), missing=r.missing, **SCENARIO) for r in runs}
    assert outcomes["1 / rerun 1"].total_cost == 75000.0 and outcomes["1 / rerun 1"].cost_per_m == 300.0
    assert outcomes["2 / rerun 1"].total_cost == 59000.0 and outcomes["2 / rerun 1"].cost_per_m == 347.06
    four = outcomes["4 / rerun 1"]
    assert four.status == br.NOT_ASSESSED and four.cost_per_m is None
    assert any(reason.startswith("run incomplete: hours on bottom") for reason in four.reasons)
    rows = {r["run"]: r for r in br.compare(runs, outcomes)}
    assert rows["1 / rerun 1"]["best_cost"] and not rows["2 / rerun 1"]["best_cost"]
    assert rows["2 / rerun 1"]["best_rop"] and not rows["1 / rerun 1"]["best_rop"]       # 12.14 > 11.36 m/h
    assert not rows["4 / rerun 1"]["best_cost"] and not rows["4 / rerun 1"]["best_rop"]
    assert rows["4 / rerun 1"]["data"] == br.INCOMPLETE


def test_a_single_run_of_a_size_is_not_ranked(env):
    runs = list(_runs(env).values())
    outcomes = {r.key: br.cost_per_length(r.figures(), missing=r.missing, **SCENARIO) for r in runs}
    rows = {r["run"]: r for r in br.compare(runs, outcomes)}
    side = rows["ST-1 / rerun 1"]                     # the fastest run overall, but the only 8.5 in run
    assert side["cost_status"] == br.ASSESSED and not side["best_cost"] and not side["best_rop"]
    assert rows["2 / rerun 1"]["best_rop"] and rows["1 / rerun 1"]["best_cost"]      # 12.25 in ranked alone


def test_only_an_assessed_scenario_can_be_saved(env):
    run = _runs(env, env["bore"])["4 / rerun 1"]
    outcome = br.cost_per_length(run.figures(), missing=run.missing, **SCENARIO)
    with pytest.raises(ValueError, match="Only an assessed cost scenario"):
        br.save_scenario(env["manager"], run, outcome, well_id=env["well"])


@pytest.mark.parametrize("change, reason", [
    ({"currency": ""}, "currency not entered"),
    ({"currency": "usd"}, "currency not entered"),
    ({"bit_cost": None}, "bit cost not entered"),
    ({"rig_rate_per_day": None}, "rig rate per day not entered"),
    ({"trip_hours": None}, "trip time not entered"),
    ({"bit_cost": -1.0}, "bit cost cannot be negative"),
])
def test_nothing_is_costed_without_every_scenario_value(env, change, reason):
    run = _runs(env, env["bore"])["1 / rerun 1"]
    outcome = br.cost_per_length(run.figures(), **{**SCENARIO, **change})
    assert outcome.status == br.NOT_ASSESSED and outcome.cost_per_m is None
    assert any(r.startswith(reason) for r in outcome.reasons)


def test_the_panel_lists_every_run_and_has_no_seeded_scenario(app, env):
    from tabs.bit_run_panel import BitRunWorkbench

    opened = []
    owner = type("Owner", (), {"open_report_by_id": lambda self, rid: opened.append(rid) or True})()
    panel = BitRunWorkbench(env["manager"], owner)
    try:
        assert panel.scope_label.text().startswith("NOT ASSESSED") and not panel.compare_btn.isEnabled()
        panel.set_scope(env["well"], env["bore"])
        assert panel.wait()                       # background read (M103 runner)
        assert panel.runs_table.rowCount() == 3 and "1 incomplete" in panel.scope_label.text()
        data_col = br.RUN_COLUMNS.index("Data")
        assert [panel.runs_table.item(i, data_col).text() for i in range(3)] == ["COMPLETE", "COMPLETE", "INCOMPLETE"]
        assert all(not e.text() for e in (panel.currency_edit, panel.bit_cost_edit, panel.rig_rate_edit,
                                          panel.trip_edit))
        rows = panel.compare()
        assert all(r["cost_status"] == br.NOT_ASSESSED for r in rows)
        assert "currency not entered" in panel.status.text() and "bit cost not entered" in panel.status.text()
        panel.runs_table.selectRow(0)
        assert panel.detail_table.rowCount() == 2
        panel.detail_table.selectRow(1)
        assert panel.open_btn.isEnabled() and panel.open_selected_report() and opened == [env["reports"][1]]
    finally:
        panel.deleteLater()


def _fill(panel):
    panel.currency_edit.setText("usd")                     # typed lower case; the code is upper-cased
    panel.bit_cost_edit.setText("15000")
    panel.rig_rate_edit.setText("48000")
    panel.trip_edit.setText("8")


def test_the_panel_compares_saves_and_history_re_runs(app, env):
    from tabs.bit_run_panel import COMPARE_COLUMNS, BitRunWorkbench

    panel = BitRunWorkbench(env["manager"])
    try:
        panel.set_scope(env["well"], env["bore"])
        assert panel.wait()                       # background read (M103 runner)
        _fill(panel)
        panel.compare()
        cost_col = COMPARE_COLUMNS.index("Cost per m")
        assert [panel.compare_table.item(i, cost_col).text() for i in range(3)] == ["300.00", "347.06", "—"]
        assert "2 of 3 run(s) costed" in panel.status.text()
        panel.runs_table.selectRow(2)
        assert panel.save_selected() is None and "NOT ASSESSED" in panel.status.text()   # incomplete run
        panel.runs_table.selectRow(0)
        case = panel.save_selected()
        assert case and case["method"] == br.COST_METHOD and case["method_version"] == br.COST_VERSION
        assert case["wellbore_id"] == env["bore"] and case["results"]["cost_per_m"] == {"value": 300.0,
                                                                                         "unit": "USD/m"}
        assert case["inputs"]["run"]["rows"] == env["rows"][:2]
    finally:
        panel.deleteLater()
    entries = [e for e in ch.load_history(env["manager"], well_id=env["well"]) if e.method == br.COST_METHOD]
    assert len(entries) == 1 and entries[0].scope == ch.BIT_RUN_SCOPE
    outcome = ch.recalculate_entry(entries[0], env["manager"])
    assert outcome["status"] == "MATCH" and "DDR rows unchanged since saving" in outcome["detail"]
    with env["manager"].session_scope() as s:                 # the DDR is edited after the scenario was saved
        s.get(DrillingParameters, env["rows"][1]).hours_on_bottom = 14.0
    outcome = ch.recalculate_entry(entries[0], env["manager"])
    assert outcome["status"] == "MATCH"                       # the frozen figures still give the stored cost
    assert "DDR SOURCE CHANGED" in outcome["detail"] and "hours 22.0 → 24.0" in outcome["detail"]
    rerun = ch.save_recalculation(env["manager"], entries[0], outcome)       # a NEW linked case, same method
    assert rerun["method"] == br.COST_METHOD and rerun["parent_id"] is None and rerun["id"] != case["id"]
    assert rerun["results"] == case["results"] and "DDR SOURCE CHANGED" in rerun["note"]
    again = [e for e in ch.load_history(env["manager"], well_id=env["well"]) if e.record_id == rerun["id"]][0]
    assert ch.recalculate_entry(again, env["manager"])["status"] == "MATCH"


def test_history_routes_the_bit_run_method():
    assert ch.BIT_RUN_METHOD == br.COST_METHOD


def test_an_unknown_method_version_is_not_reproducible(env):
    assert br.verify_case(env["manager"], {"run": {}}, {}, "M999 other")["status"] == "NOT_REPRODUCIBLE"
    assert br.verify_case(env["manager"], {"run": "x"}, {}, br.COST_VERSION)["status"] == "UNREADABLE"


def test_a_viewer_cannot_save_a_scenario(app, env, tmp_path, monkeypatch):
    from tabs.bit_run_panel import BitRunWorkbench
    from tests.test_m96_persistence_audit import _open as open_as

    env["manager"].close()
    viewer = open_as(env["path"], tmp_path, monkeypatch, principal="viewer", permissions={})
    panel = BitRunWorkbench(viewer)
    try:
        panel.set_scope(env["well"], env["bore"])
        assert panel.wait()                       # background read (M103 runner)
        _fill(panel)
        panel.runs_table.selectRow(0)
        assert panel.save_selected() is None and panel.status.text().startswith("Not saved:")
    finally:
        panel.deleteLater()
        viewer.close()


def test_export_carries_provenance_incomplete_runs_and_the_currency(app, env, tmp_path):
    from tabs.bit_run_panel import BitRunWorkbench

    panel = BitRunWorkbench(env["manager"])
    try:
        panel.set_scope(env["well"], env["bore"])
        assert panel.wait()                       # background read (M103 runner)
        _fill(panel)
        panel.compare()
        path = tmp_path / "bit_runs.csv"
        assert panel.export_to(str(path)) == 3
    finally:
        panel.deleteLater()
    rows = list(csv.reader(path.open(encoding="utf-8")))
    flat = [cell for row in rows for cell in row]
    assert rows[0] == ["Bit run workbench", br.RUN_METHOD] and br.COST_LABEL in flat and "USD" in flat
    assert "INCOMPLETE" in flat and any(c.startswith("Well #") and "wellbore" in c for c in flat)
    run_rows = [r for r in rows if r and r[0] == "4"]
    assert run_rows and run_rows[0][br.RUN_COLUMNS.index("Hours on bottom")] == ""      # unknown stays empty


def test_w12_hosts_the_workbench_and_the_seeded_comparison_is_gone(app, env):
    import inspect

    from tabs import w12_Analysis
    from tabs.bit_run_panel import BitRunWorkbench

    source = inspect.getsource(w12_Analysis)
    assert "cost_rig_rate" not in source and "_update_cost_comparison" not in source
    tab = w12_Analysis.AnalysisWidget(db_manager=env["manager"])
    try:
        assert isinstance(tab.bit_runs_panel, BitRunWorkbench) and tab.bit_runs_panel.owner is tab
        tab.on_well_changed(env["well"], {"name": "SYN-A"})              # follows the selected well
        assert tab.bit_runs_panel.wait()
        assert tab.bit_runs_panel.well_id == env["well"] and tab.bit_runs_panel.runs_table.rowCount() == 4
        tab.on_wellbore_changed(env["sidetrack"], {"name": "SYN-A ST1"})  # and an explicitly selected wellbore
        assert tab.bit_runs_panel.wait()
        assert tab.bit_runs_panel.wellbore_id == env["sidetrack"] and tab.bit_runs_panel.runs_table.rowCount() == 1
        tab.on_selection_cleared()
        assert tab.bit_runs_panel.well_id is None and tab.bit_runs_panel.runs_table.rowCount() == 0
    finally:
        tab.cleanup()
        tab.deleteLater()


def test_runs_are_read_on_a_worker_and_a_late_result_is_never_shown(app, env, monkeypatch):
    """M51/M103: no GUI-thread SQL; a result that arrives after the scope was cleared is rejected by state."""
    import threading

    from tabs import bit_run_panel
    from tabs.bit_run_panel import BitRunWorkbench

    gate, entered, threads, real = threading.Event(), threading.Event(), [], br.load_runs

    def slow(db, well, bore=None):
        threads.append(threading.current_thread() is threading.main_thread())
        entered.set()
        gate.wait(10)
        return real(db, well, bore)

    monkeypatch.setattr(bit_run_panel.br, "load_runs", slow)
    panel = BitRunWorkbench(env["manager"])
    try:
        panel.set_scope(env["well"], env["bore"])
        assert panel.jobs.synchronous is False and panel.jobs.busy and "loading" in panel.scope_label.text()
        assert entered.wait(10)                                # the worker is inside the read
        panel.set_scope(None)                                  # cleared while the worker still reads
        gate.set()
        assert panel.wait()
        assert threads == [False]                              # read on the worker thread
        assert panel.runs == [] and panel.runs_table.rowCount() == 0
        assert panel.jobs.rejected["superseded"] == 1 and panel.scope_label.text().startswith("NOT ASSESSED")
        panel.set_scope(env["well"], env["bore"])
        assert panel.wait() and panel.runs_table.rowCount() == 3
    finally:
        gate.set()
        panel.shutdown(5000)
        panel.deleteLater()
