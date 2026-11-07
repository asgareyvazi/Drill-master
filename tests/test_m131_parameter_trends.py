"""M131: drilling-parameter trend workspace (D48).

D48: the W12 Performance chart drew ROP and WOB as lines with ``connect="finite"``, so two DDR records three
days apart were joined across the days without a DDR - the line showed values nobody recorded. It now draws
markers only; the new trend workspace shows recorded ranges as bars and never joins two records.

Fixture (synthetic): DDRs on 1, 2 and 5 March for the main bore, 6 March for a sidetrack; one MSE run linked to
the 1 March DDR with MD 1100 m, one legacy MSE run with no lineage.
"""
from __future__ import annotations

import csv
import os
from datetime import date, datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

from core import parameter_trends as pt  # noqa: E402
from core.database import DailyReport, DrillingParameters, MSECalculationRecord, Wellbore  # noqa: E402
from core.repositories.mse_repository import LEGACY_LABEL, MSECalculationRepository  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402

D = {1: date(2026, 3, 1), 2: date(2026, 3, 2), 5: date(2026, 3, 5), 6: date(2026, 3, 6)}
MSE_INPUTS = {"wob_lbf": 25000.0, "rpm": 120.0, "torque_ft_lbf": 8000.0, "rop_ft_hr": 50.0, "bit_diameter_in": 8.5}


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def env(tmp_path, monkeypatch):
    manager = _open(tmp_path / "m131.sqlite", tmp_path, monkeypatch)
    well, bore = _seed(manager)["A"]
    out = {"manager": manager, "well": well, "bore": bore, "rows": {}, "reports": {}}
    with manager.session_scope() as s:
        st = Wellbore(well_id=well, name="SYN-A ST1", wellbore_type="sidetrack")
        s.add(st)
        s.flush()
        out["sidetrack"] = st.id
        for day, bore_id in ((1, bore), (2, bore), (5, bore), (6, st.id)):
            r = DailyReport(well_id=well, wellbore_id=bore_id, report_date=D[day], report_number=day)
            s.add(r)
            s.flush()
            out["reports"][day] = r.id
        values = {
            1: dict(avg_rop=12.0, wob_min=10.0, wob_max=20.0, rpm_min=120.0, rpm_max=140.0, depth_out=1100.0),
            2: dict(avg_rop=None, wob_min=25.0, wob_max=15.0, rpm_min=None, rpm_max=150.0, depth_out=None),
            5: dict(avg_rop=20.0, wob_min=18.0, wob_max=22.0, rpm_min=-5.0, rpm_max=130.0, depth_out=1300.0),
            6: dict(avg_rop=8.0, depth_out=950.0),
        }
        for day, kw in values.items():
            row = DrillingParameters(well_id=well, report_id=out["reports"][day], report_date=D[day], bit_no="1", **kw)
            s.add(row)
            s.flush()
            out["rows"][day] = row.id
        legacy = MSECalculationRecord(well_id=well, label="SYN legacy", method="Teale", snapshot_schema_version=1,
                                      input_snapshot_json={"parameters": MSE_INPUTS}, mse_psi=127997.67,
                                      created_at=datetime(2026, 3, 7, 12, 0))
        s.add(legacy)
        s.flush()
        out["legacy"] = legacy.id
    out["linked"] = MSECalculationRepository(manager).save_run(
        inputs=MSE_INPUTS, result_values={"mse_psi": 127997.67}, method="Teale", label="SYN linked", well_id=well,
        wellbore_id=bore, report_id=out["reports"][1], md_value=1100.0, md_unit="m")
    yield out
    manager.close()


def _src(row_id):
    return f"drilling_parameters #{row_id}"


def test_time_axis_places_recorded_values_and_lists_every_gap(env):
    r = pt.load(env["manager"], env["well"], pt.AXIS_TIME, env["bore"])
    rop, wob, rpm = r.series["rop"], r.series["wob"], r.series["rpm"]
    assert [(p.x, p.low) for p in rop.points] == [(D[1], 12.0), (D[5], 20.0)]
    assert rop.missing == [(D[2], _src(env["rows"][2]))]                 # never 0, never interpolated
    assert [(p.x, p.low, p.high) for p in wob.points] == [(D[1], 10.0, 20.0), (D[5], 18.0, 22.0)]
    assert wob.invalid == [(D[2], _src(env["rows"][2]), "min 25 > max 15")]
    assert [(p.x, p.low, p.high, p.note) for p in rpm.points] == [(D[1], 120.0, 140.0, ""),
                                                                  (D[2], None, 150.0, "only max recorded")]
    assert rpm.invalid and rpm.invalid[0][1] == _src(env["rows"][5])  # a negative min is not a value
    assert r.series["torque"].points == [] and len(r.series["torque"].missing) == 3


def test_depth_axis_never_guesses_a_depth(env):
    r = pt.load(env["manager"], env["well"], pt.AXIS_DEPTH, env["bore"])
    assert [(p.x, p.low) for p in r.series["rop"].points] == [(1100.0, 12.0), (1300.0, 20.0)]
    assert r.series["rpm"].not_placed == [(D[2], _src(env["rows"][2]), "depth out not recorded")]
    assert r.axis_label == "Depth out (m MD, DDR)"


def test_mse_is_discrete_and_placed_only_by_its_recorded_lineage(env):
    timed = pt.load(env["manager"], env["well"], pt.AXIS_TIME)
    assert [(p.x, p.source) for p in timed.mse.points] == [(D[1], f"mse_calculations #{env['linked']}")]
    (_day, source, reason), = timed.mse.not_placed
    assert source == f"mse_calculations #{env['legacy']}" and "the save time is not a drilling time" in reason
    assert LEGACY_LABEL in reason
    deep = pt.load(env["manager"], env["well"], pt.AXIS_DEPTH)
    assert [p.x for p in deep.mse.points] == [1100.0]
    assert deep.mse.not_placed[0][2] == f"no recorded MD ({LEGACY_LABEL})"
    assert pt.MSE_LABEL.startswith("MSE — discrete")


def test_a_wellbore_view_uses_only_that_wellbore(env):
    r = pt.load(env["manager"], env["well"], pt.AXIS_TIME, env["sidetrack"])
    assert [(p.x, p.low) for p in r.series["rop"].points] == [(D[6], 8.0)] and r.rows == 1
    assert r.mse.points == [] and {src for _d, src, _w in r.excluded_mse} == {
        f"mse_calculations #{env['linked']}", f"mse_calculations #{env['legacy']}"}


def test_an_unknown_axis_is_refused():
    with pytest.raises(ValueError):
        pt.build([], "speed")


def test_the_panel_draws_markers_and_ranges_only(app, env):
    import pyqtgraph as pg

    from tabs.parameter_trend_panel import ParameterTrendPanel

    panel = ParameterTrendPanel(env["manager"])
    try:
        assert panel.scope_label.text().startswith("NOT ASSESSED") and not panel.export_btn.isEnabled()
        panel.set_scope(env["well"], env["bore"])
        assert panel.wait()                       # background read (M103 runner)
        panel.parameter_combo.setCurrentIndex(pt.PARAMETER_KEYS.index("wob"))
        items = panel.plot.getPlotItem().listDataItems()
        markers = [i for i in items if i.opts["pen"] is None]
        bars = [i for i in items if i.opts.get("connect") == "pairs"]
        assert len(markers) == 1 and len(bars) == 1 and len(items) == 2         # nothing else is drawn
        xs, ys = bars[0].getData()
        assert len(xs) == 4 and xs[0] == xs[1] and xs[2] == xs[3] and list(ys) == [10.0, 20.0, 18.0, 22.0]
        assert isinstance(panel.plot.getPlotItem().getAxis("bottom"), pg.DateAxisItem)
        states = {panel.gap_table.item(i, 1).text() for i in range(panel.gap_table.rowCount())}
        assert {"INVALID", "excluded (scope)"} <= states                  # WOB inverted; legacy MSE not this bore
        panel.axis_combo.setCurrentIndex(list(pt.AXIS_LABELS).index(pt.AXIS_DEPTH))
        assert panel.wait()                       # background read (M103 runner)
        assert panel.result.axis == pt.AXIS_DEPTH
        assert not isinstance(panel.plot.getPlotItem().getAxis("bottom"), pg.DateAxisItem)
        assert panel.plot.getPlotItem().getAxis("bottom").labelText == "Depth out (m MD, DDR)"
    finally:
        panel.deleteLater()


def test_the_export_lists_placed_missing_invalid_and_not_placed_rows(app, env, tmp_path):
    from tabs.parameter_trend_panel import ParameterTrendPanel

    panel = ParameterTrendPanel(env["manager"])
    try:
        panel.set_scope(env["well"], env["bore"])
        assert panel.wait()                       # background read (M103 runner)
        panel.axis_combo.setCurrentIndex(list(pt.AXIS_LABELS).index(pt.AXIS_DEPTH))   # row 2 has no depth out
        assert panel.wait()                       # background read (M103 runner)
        path = tmp_path / "trends.csv"
        assert panel.export_to(str(path)) > 0
    finally:
        panel.deleteLater()
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert rows[0] == ["Drilling-parameter trends", pt.TREND_METHOD]
    states = {r[2] for r in rows[6:] if len(r) > 2}
    assert {"placed", "missing", "INVALID", "not placed"} <= states
    rop_missing = [r for r in rows if r[:3] == ["ROP (average)", "m/h", "missing"]]
    assert rop_missing and rop_missing[0][4] == "" and rop_missing[0][-1] == _src(env["rows"][2])


def test_w12_hosts_the_trends_and_the_performance_chart_draws_no_line(app, env, monkeypatch):
    from tabs.parameter_trend_panel import ParameterTrendPanel
    from tabs.w12_Analysis import AnalysisWidget

    tab = AnalysisWidget(db_manager=env["manager"])
    try:
        assert isinstance(tab.trend_panel, ParameterTrendPanel)
        tab.on_well_changed(env["well"], {"name": "SYN-A"})
        assert tab.trend_panel.wait()
        assert tab.trend_panel.well_id == env["well"] and tab.trend_panel.result is not None
        tab.on_selection_cleared()
        assert tab.trend_panel.result is None
        tab.current_well_id, tab.current_well_name = env["well"], "SYN-A"
        monkeypatch.setattr(tab, "_uses_revision_worker", lambda: False)
        tab.update_performance_data()
        items = tab.performance_plot.getPlotItem().listDataItems()
        assert items and all(i.opts["pen"] is None for i in items)            # D48: markers only
        recs = [dict(date=f"2026-01-0{i}", bit_run="1", depth=d, rop=r, wob=20.0, rpm=120.0, bit_size=12.25)
                for i, (d, r) in enumerate(((1500.0, 12.0), (1450.0, 15.0)), start=1)]
        tab.update_dexponent_data(recs)                                     # synthetic, out of depth order
        dx = tab.dexponent_plot.getPlotItem()
        assert dx.listDataItems() and all(i.opts["pen"] is None for i in dx.listDataItems())  # D47
        assert "bit run" not in dx.titleLabel.text                            # D47: one point per DDR record
    finally:
        tab.cleanup()
        tab.deleteLater()


def test_trends_are_read_on_a_worker_and_a_newer_axis_wins(app, env, monkeypatch):
    """M51/M103: no GUI-thread SQL; the first (slow) read is superseded by the axis change and never drawn."""
    import threading

    from tabs import parameter_trend_panel
    from tabs.parameter_trend_panel import ParameterTrendPanel

    gate, entered, calls, real = threading.Event(), threading.Event(), [], pt.load

    def slow(db, well, axis, bore=None):
        calls.append((axis, threading.current_thread() is threading.main_thread()))
        if len(calls) == 1:
            entered.set()
            gate.wait(10)
        return real(db, well, axis, bore)

    monkeypatch.setattr(parameter_trend_panel.pt, "load", slow)
    panel = ParameterTrendPanel(env["manager"])
    try:
        panel.set_scope(env["well"], env["bore"])
        assert panel.jobs.synchronous is False and panel.jobs.busy and panel.result is None
        assert entered.wait(10)                                # the first worker is inside the read
        panel.axis_combo.setCurrentIndex(list(pt.AXIS_LABELS).index(pt.AXIS_DEPTH))
        gate.set()
        assert panel.wait()
        assert [main for _axis, main in calls] == [False, False]
        assert panel.result is not None and panel.result.axis == pt.AXIS_DEPTH
        assert panel.jobs.rejected["superseded"] == 1
    finally:
        gate.set()
        panel.shutdown(5000)
        panel.deleteLater()
