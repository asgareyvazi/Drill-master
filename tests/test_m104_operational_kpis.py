"""M104: operational analysis scope, MSE lineage and the KPI register.

Synthetic data only.  MSE lineage (wellbore, report, input source) is recorded for new saves through an
additive migration; legacy runs stay unknown.  Plan vs actual and cost are assessed only where the stored
model supports the scope, otherwise "not assessed" with a reason.  Every KPI carries value, unit, scope,
source, quality and reason.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, time
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import analysis_evidence as ev  # noqa: E402
from core import operational_analysis as oa  # noqa: E402
from core.database import (CostRecord, DailyReport, DrillingParameters, MSECalculationRecord,  # noqa: E402
                           TimeLog24H, WellPlan, Wellbore)
from core.repositories.mse_repository import LINEAGE_VERSION, MANUAL_ENTRY, MSECalculationRepository  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402

D = [date(2026, 2, d) for d in range(1, 6)]
MSE_IN = {"wob_lbf": 25000.0, "rpm": 120.0, "torque_ft_lbf": 8000.0, "rop_ft_hr": 50.0, "bit_diameter_in": 8.5}
MSE_OUT = {"mse_psi": 127997.67, "axial_term_psi": 440.6, "rotary_term_psi": 127557.07, "bit_area_in2": 56.745}


@pytest.fixture
def env(tmp_path, monkeypatch):
    manager = _open(tmp_path / "m104.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    well, bore = ids["A"]
    out = {"well": well, "bore": bore, "other_well": ids["B"][0], "path": tmp_path / "m104.sqlite"}
    with manager.session_scope() as s:
        st = Wellbore(well_id=well, name="SYN-A ST1", wellbore_type="sidetrack")
        foreign = Wellbore(well_id=out["other_well"], name="SYN-B OH2", wellbore_type="original")
        s.add_all([st, foreign])
        s.flush()
        out["sidetrack"], out["foreign_bore"] = st.id, foreign.id
        reports = []
        for day, d0, d1, wb in ((D[0], 1000, 1100, bore), (D[1], 1100, 1250, bore), (D[2], 900, 960, st.id)):
            r = DailyReport(well_id=well, wellbore_id=wb, report_date=day, report_number=len(reports) + 1,
                            depth_0000=d0, depth_2400=d1)
            s.add(r)
            s.flush()
            reports.append(r.id)
        out["reports"] = reports
        for rid in reports:
            s.add(TimeLog24H(report_id=rid, time_from=time(0), time_to=time(12), duration=12.0, main_code="DRL",
                             is_npt=False))
        foreign_report = DailyReport(well_id=out["other_well"], report_date=D[0], report_number=1)
        s.add(foreign_report)
        s.flush()
        out["foreign_report"] = foreign_report.id
        # bit 7: depth out shallower than depth in, no drilled; bit 8: footage known, zero hours on bottom
        for rid, day, bit, d_in, d_out, drilled, hours in ((reports[0], D[0], "7", 1100, 1050, None, 5.0),
                                                           (reports[0], D[0], "8", 1000, 1100, 100.0, 0.0),
                                                           (reports[1], D[1], "8", 1100, 1250, 150.0, 0.0)):
            s.add(DrillingParameters(well_id=well, report_id=rid, report_date=day, bit_no=bit, bit_rerun=1,
                                     depth_in=d_in, depth_out=d_out, bit_drilled=drilled, hours_on_bottom=hours))
        # a legacy MSE run: saved before lineage (all lineage columns NULL)
        s.add(MSECalculationRecord(well_id=well, label="SYN legacy MSE", method="Teale", snapshot_schema_version=1,
                                   input_snapshot_json={"parameters": MSE_IN}, mse_psi=111.0,
                                   created_at=datetime(2026, 2, 1, 9, 0)))
        for currency, category, planned, actual in (("USD", "Rig", 900.0, 1000.0), ("EUR", "Services", 400.0, 500.0),
                                                    ("USD", "Fuel", 50.0, 70.0)):
            s.add(CostRecord(well_id=well, category=category, planned_cost=planned, actual_cost=actual,
                             currency=currency, cost_date=D[0]))
        s.add(WellPlan(well_id=well, plan_name="SYN PLAN", planned_final_depth=2000.0, is_active=True))
    repo = MSECalculationRepository(manager)
    out["mse_bore"] = repo.save_run(inputs=MSE_IN, result_values=MSE_OUT, method="Teale", label="SYN bore MSE",
                                    well_id=well, wellbore_id=bore, report_id=reports[1])
    out["mse_st"] = repo.save_run(inputs=MSE_IN, result_values=MSE_OUT, method="Teale", label="SYN st MSE",
                                  well_id=well, wellbore_id=out["sidetrack"])
    yield manager, out
    manager.close()


def _analyze(manager, out, **kw):
    return oa.analyze(manager, ev.AnalysisScope(well_id=out["well"], wellbore_id=kw.pop("bore", None)), **kw)


def _kpi(result, name):
    rows = {r[0]: r for r in result.tables["kpis"][1]}
    return dict(zip(oa.COLUMNS["kpis"], rows[name]))


# ---- MSE lineage -----------------------------------------------------------------------------------------
def test_new_mse_runs_record_lineage_and_legacy_runs_stay_unknown(env):
    manager, out = env
    saved = MSECalculationRepository(manager).get(out["mse_bore"])
    assert (saved.wellbore_id, saved.report_id, saved.input_source, saved.lineage_version) == (
        out["bore"], out["reports"][1], MANUAL_ENTRY, LINEAGE_VERSION)   # M123: v2 (+ explicit MD, units)
    whole = _analyze(manager, out)
    rows = {r[1]: dict(zip(oa.COLUMNS["mse"], r)) for r in whole.tables["mse"][1]}
    legacy = rows["SYN legacy MSE"]
    assert legacy["Wellbore"] == legacy["Report #"] == legacy["Input source"] == oa.LEGACY_LINEAGE
    assert rows["SYN bore MSE"]["Report #"] == 2 and rows["SYN bore MSE"]["Input source"] == MANUAL_ENTRY
    assert rows["SYN st MSE"]["Wellbore"] == "SYN-A ST1" and rows["SYN st MSE"]["Report #"] == ""
    by_label = dict(zip([r[1] for r in whole.tables["mse"][1]], whole.report_ids["mse"]))
    assert by_label == {"SYN legacy MSE": None, "SYN bore MSE": out["reports"][1], "SYN st MSE": None}
    kpi = _kpi(whole, "MSE calculations")
    assert kpi["Value"] == 3 and kpi["Quality"] == oa.PARTIAL and "1 saved before lineage" in kpi["Reason"]


def test_wellbore_scope_shows_only_that_wellbores_mse_runs(env):
    manager, out = env
    bore = _analyze(manager, out, bore=out["bore"])
    assert [r[1] for r in bore.tables["mse"][1]] == ["SYN bore MSE"]
    assert any("1 MSE calculation(s) without a recorded wellbore" in n for n in bore.notes)
    assert "1 without a wellbore not attributed" in _kpi(bore, "MSE calculations")["Reason"]
    sidetrack = _analyze(manager, out, bore=out["sidetrack"])
    assert [r[1] for r in sidetrack.tables["mse"][1]] == ["SYN st MSE"]


def test_lineage_refuses_relations_the_model_does_not_have(env):
    manager, out = env
    repo = MSECalculationRepository(manager)
    before = repo.count()
    cases = ({"well_id": out["well"], "wellbore_id": out["foreign_bore"]},
             {"well_id": out["well"], "report_id": out["foreign_report"]},
             {"well_id": out["well"], "wellbore_id": out["sidetrack"], "report_id": out["reports"][0]},
             {"well_id": None, "wellbore_id": out["bore"]},
             {"well_id": out["well"], "wellbore_id": 999999})
    for kwargs in cases:
        with pytest.raises(ValueError):
            repo.save_run(inputs=MSE_IN, result_values=MSE_OUT, method="Teale", **kwargs)
    assert repo.count() == before                       # nothing half-saved


def test_an_old_database_gains_the_lineage_columns_without_backfill(env):
    manager, out = env
    manager.close()
    lineage = ("wellbore_id", "report_id", "input_source", "lineage_version",
               "md_m", "md_entered_value", "md_entered_unit", "input_units_json")      # + M123 lineage v2
    with sqlite3.connect(out["path"]) as con:            # rebuild the table as it was before M104
        ddl = con.execute("SELECT sql FROM sqlite_master WHERE name='mse_calculations'").fetchone()[0]
        lines = [ln for ln in ddl.splitlines() if not any(c in ln for c in lineage)]
        old_ddl = "\n".join(lines).replace("CREATE TABLE mse_calculations", "CREATE TABLE mse_old")
        old_ddl = old_ddl.replace("(id),\n)", "(id)\n)").rstrip()
        keep = [r[1] for r in con.execute("PRAGMA table_info(mse_calculations)") if r[1] not in lineage]
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("DROP TABLE IF EXISTS mse_lineage_repairs")   # M123: did not exist before M104 either
        con.execute(old_ddl)
        con.execute(f"INSERT INTO mse_old ({', '.join(keep)}) SELECT {', '.join(keep)} FROM mse_calculations")
        con.execute("DROP TABLE mse_calculations")
        con.execute("ALTER TABLE mse_old RENAME TO mse_calculations")
        assert not set(lineage) & {r[1] for r in con.execute("PRAGMA table_info(mse_calculations)")}
    manager.initialize()
    with sqlite3.connect(out["path"]) as con:
        columns = {r[1] for r in con.execute("PRAGMA table_info(mse_calculations)")}
        assert set(lineage) <= columns                   # M104 and M123 columns are added back, never backfilled
        assert con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='mse_lineage_repairs'").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM mse_calculations WHERE md_m IS NOT NULL").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM mse_calculations WHERE lineage_version IS NOT NULL").fetchone()[0] == 0
        fks = {(r[2], r[3]) for r in con.execute("PRAGMA foreign_key_list(mse_calculations)")}
        assert {("wellbores", "wellbore_id"), ("daily_reports", "report_id")} <= fks
    rows = _analyze(manager, out).tables["mse"][1]
    assert len(rows) == 3 and all(r[10] == oa.LEGACY_LINEAGE for r in rows)   # every run is now legacy
    manager.initialize()                                  # idempotent
    assert len(_analyze(manager, out).tables["mse"][1]) == 3


def test_w13_records_the_selected_wellbore_and_report_of_the_same_well():
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab as Tab

    context = SimpleNamespace(well_id=5, report_id=41)
    tab = SimpleNamespace(current_well_id=5, current_wellbore_id=8, current_context=context)
    assert Tab._mse_lineage(tab) == {"wellbore_id": 8, "report_id": 41}
    tab.current_context = SimpleNamespace(well_id=6, report_id=41)       # a stale snapshot of another well
    assert Tab._mse_lineage(tab) == {"wellbore_id": 8, "report_id": None}
    assert Tab._mse_lineage(SimpleNamespace(current_well_id=None)) == {}


# ---- plan vs actual and cost scope -------------------------------------------------------------------------
def test_plan_vs_actual_is_assessed_only_for_the_whole_well_without_dates(env):
    manager, out = env
    whole = _analyze(manager, out)
    rows = {r[0]: dict(zip(oa.COLUMNS["plan_vs_actual"], r)) for r in whole.tables["plan_vs_actual"][1]}
    assert rows["depth"]["Unit"] == "m" and rows["depth"]["Planned"] == 2000.0
    assert rows["depth"]["Status"] != oa.NOT_ASSESSED and "whole well" in rows["depth"]["Reason"]
    for kwargs, reason in (({"bore": out["bore"]}, "per well, not per wellbore"),
                           ({"start": D[0], "end": D[1]}, "a date range selects only part")):
        narrow = _analyze(manager, out, **kwargs)
        for row in narrow.tables["plan_vs_actual"][1]:
            item = dict(zip(oa.COLUMNS["plan_vs_actual"], row))
            assert item["Status"] == oa.NOT_ASSESSED and reason in item["Reason"]
            assert item["Planned"] is item["Actual"] is item["Delta"] is None
        assert any(n.startswith("plan vs actual not assessed") for n in narrow.notes)


def test_cost_is_per_currency_and_not_assessed_for_a_wellbore(env):
    manager, out = env
    whole = _analyze(manager, out)
    assert _kpi(whole, "Actual cost (USD)")["Value"] == pytest.approx(1070.0)
    assert _kpi(whole, "Actual cost (EUR)")["Value"] == pytest.approx(500.0)
    assert _kpi(whole, "Actual cost (USD)")["Unit"] == "USD"
    assert not any(r[0] == "Actual cost" for r in whole.tables["kpis"][1])       # never a mixed total
    bore = _analyze(manager, out, bore=out["bore"])
    assert bore.tables["cost"][1] == [] and bore.summary["cost_actual"] is None
    kpi = _kpi(bore, "Actual cost")
    assert kpi["Value"] is None and kpi["Quality"] == oa.NOT_ASSESSED and "no wellbore" in kpi["Reason"]


# ---- footage / ROP edge cases and bit drill-down ------------------------------------------------------------
def test_bit_runs_explain_invalid_footage_and_zero_hours(env):
    manager, out = env
    result = _analyze(manager, out)
    runs = {r[0]: dict(zip(oa.COLUMNS["bit_runs"], r)) for r in result.tables["bit_runs"][1]}
    assert runs["7"]["Footage (m)"] is None and runs["7"]["Footage basis"].startswith("INVALID: depth out 1050")
    assert runs["7"]["ROP basis"] == "not assessed: footage unknown"
    assert runs["8"]["Footage (m)"] == 250.0 and runs["8"]["ROP (m/h)"] is None
    assert runs["8"]["ROP basis"] == "not assessed: no hours on bottom"


def test_bit_run_rows_drill_down_to_their_reports(env):
    manager, out = env
    result = _analyze(manager, out)
    rows = [dict(zip(oa.COLUMNS["bit_rows"], r)) for r in result.tables["bit_rows"][1]]
    assert [(r["Bit #"], r["Report #"]) for r in rows] == [("7", 1), ("8", 1), ("8", 2)]
    assert result.report_ids["bit_rows"] == [out["reports"][0], out["reports"][0], out["reports"][1]]
    assert "INVALID" in rows[0]["Notes"] and "drilled not recorded" in rows[0]["Notes"]
    assert rows[1]["ROP (m/h)"] is None and "no hours on bottom" in rows[1]["Notes"]
    one_day = _analyze(manager, out, start=D[1], end=D[1])
    assert [r[3] for r in one_day.tables["bit_rows"][1]] == [2]


# ---- KPI register ---------------------------------------------------------------------------------------------
def test_every_kpi_has_value_unit_scope_source_quality_and_reason(env):
    manager, out = env
    for kwargs in ({}, {"bore": out["bore"]}, {"start": D[0], "end": D[0]}):
        result = _analyze(manager, out, **kwargs)
        assert list(result.tables) == list(oa.COLUMNS) and list(result.tables)[0] == "kpis"
        for row in result.tables["kpis"][1]:
            item = dict(zip(oa.COLUMNS["kpis"], row))
            assert len(row) == len(oa.COLUMNS["kpis"])
            assert item["Unit"] and item["Source"] and result.scope_label in item["Scope"]
            assert item["Quality"] in (oa.COMPLETE, oa.PARTIAL, oa.NOT_ASSESSED)
            if item["Value"] is None:                    # unknown is never 0 and always explained
                assert item["Quality"] == oa.NOT_ASSESSED and item["Reason"]
    ranged = _analyze(manager, out, start=D[0], end=D[0])
    assert f"{D[0]} – {D[0]}" in _kpi(ranged, "Footage")["Scope"]


def test_partial_footage_is_not_a_total(env):
    manager, out = env
    with manager.session_scope() as s:
        s.get(DailyReport, out["reports"][1]).depth_2400 = None
    result = _analyze(manager, out, bore=out["bore"])
    footage = _kpi(result, "Footage")
    assert footage["Value"] is None and footage["Quality"] == oa.PARTIAL
    assert "unknown on 1 of 2 reports" in footage["Reason"] and "known sum 100 m" in footage["Reason"]
    rop = _kpi(result, "Time-weighted ROP")
    assert rop["Quality"] == oa.PARTIAL and rop["Value"] == pytest.approx(100 / 12)


def test_no_report_in_scope_is_not_assessed(env):
    manager, out = env
    empty = _analyze(manager, out, start=date(2030, 1, 1), end=date(2030, 1, 2))
    assert _kpi(empty, "Reports")["Quality"] == oa.NOT_ASSESSED
    assert _kpi(empty, "Footage")["Value"] is None and _kpi(empty, "Footage")["Reason"] == "no report in scope"
    assert _kpi(empty, "Time-weighted ROP")["Quality"] == oa.NOT_ASSESSED


def test_the_panel_shows_the_kpi_register_first(env):
    from PySide6.QtWidgets import QApplication

    from tabs import operational_analysis_panel as oap

    QApplication.instance() or QApplication([])
    manager, out = env
    owner = SimpleNamespace(db=manager, current_well_id=out["well"], current_wellbore_id=None,
                            _analysis_scope=lambda: ev.AnalysisScope(well_id=out["well"]),
                            open_report_by_id=lambda _rid: True)
    panel = oap.OperationalAnalysisPanel(owner)
    try:
        assert list(oap.TITLES) == list(oa.COLUMNS) and panel.tabs.tabText(0) == "KPI register"
        assert panel.refresh() is not None
        assert panel.wait() is not None
        table = panel.tables["kpis"]
        names = [table.item(r, 0).text() for r in range(table.rowCount())]
        assert names[0] == "Reports" and "Actual cost (USD)" in names
        panel.tabs.setCurrentIndex(panel.tabs.indexOf(panel.tables["bit_rows"]))
        panel.tables["bit_rows"].selectRow(2)
        assert panel.selected_report_id() == out["reports"][1]
    finally:
        panel.shutdown(5000)
        panel.deleteLater()
