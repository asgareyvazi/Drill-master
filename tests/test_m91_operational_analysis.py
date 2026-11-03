"""M91: Operational Analysis - footage, time-weighted ROP, activities, NPT timeline with sources, bit
runs, MSE points, cost per currency, plan vs actual; W12 page with drill-down and export.

Synthetic records only; expected numbers are hand arithmetic. Offscreen Qt.
"""
from __future__ import annotations

import csv
import glob
import os
from datetime import date, datetime, time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

from core import analysis_evidence as ev  # noqa: E402
from core import operational_analysis as oa  # noqa: E402
from core.database import (CostRecord, DailyReport, DrillingParameters, MSECalculationRecord, NPTReport,  # noqa: E402
                           TimeLog24H, Wellbore)
from tests.test_m70_integrity import _open, _seed  # noqa: E402

D = [date(2026, 1, d) for d in range(1, 6)]


def _log(s, rid, start, end, code, *, npt=False, duration="auto", category=None, text=""):
    hours = (end - start) if duration == "auto" else duration
    s.add(TimeLog24H(report_id=rid, time_from=time(start % 24), time_to=time(end % 24), duration=hours,
                     main_code=code, is_npt=npt, npt_category=category, activity_description=text))


@pytest.fixture
def env(tmp_path, monkeypatch):
    manager = _open(tmp_path / "m91.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    well, bore = ids["A"]
    out = {"well": well, "bore": bore, "other": ids["B"][0]}
    with manager.session_scope() as s:
        st = Wellbore(well_id=well, name="SYN-A ST1", wellbore_type="sidetrack")
        s.add(st)
        s.flush()
        out["sidetrack"] = st.id
        reports = []
        for day, d0, d1, wb in ((D[0], 1000, 1100, bore), (D[1], 1100, 1250, bore), (D[2], 1250, None, bore),
                                (D[3], 1300, 1290, bore), (D[4], 900, 960, st.id)):
            r = DailyReport(well_id=well, wellbore_id=wb, report_date=day, report_number=len(reports) + 1,
                            depth_0000=d0, depth_2400=d1)
            s.add(r)
            s.flush()
            reports.append(r.id)
        out["reports"] = reports
        r1, r2, r3, r4, r5 = reports
        _log(s, r1, 0, 10, "DRL")
        _log(s, r1, 10, 14, "CIR")
        _log(s, r1, 14, 18, "RPR", npt=True, category="Rig repair", text="SYN top drive repair")
        _log(s, r1, 18, 24, "DRL")
        _log(s, r2, 0, 12, "DRL")
        _log(s, r2, 12, 24, "", text="Trip out of hole")          # fuzzy match only
        _log(s, r3, 0, 6, "DRL")
        _log(s, r3, 6, 24, "XYZ")
        _log(s, r4, 0, 24, "DRL", duration=None)                     # unknown duration
        _log(s, r5, 0, 24, "DRL")
        s.add(NPTReport(well_id=well, report_id=r1, npt_date=D[0], start_time=time(2), end_time=time(4),
                        duration_hours=2.0, npt_category="Weather", npt_code="WOW", npt_description="SYN wind"))
        for rid, day, bit, d_in, d_out, drilled, hours in ((r1, D[0], "1", 1000, 1100, 100, 16),
                                                           (r2, D[1], "1", 1100, 1250, 150, 12),
                                                           (r3, D[2], "2", 1250, 1280, None, None)):
            s.add(DrillingParameters(well_id=well, report_id=rid, report_date=day, bit_no=bit, bit_rerun=1,
                                     bit_size=12.25, depth_in=d_in, depth_out=d_out, bit_drilled=drilled,
                                     hours_on_bottom=hours))
        s.add(MSECalculationRecord(well_id=well, label="SYN MSE", method="Teale", snapshot_schema_version=1,
                                   input_snapshot_json={"parameters": {"wob_lbf": 25000, "rpm": 120,
                                                                       "torque_ft_lbf": 8000, "rop_ft_hr": 50,
                                                                       "bit_diameter_in": 8.5}},
                                   mse_psi=127997.67, created_at=datetime(2026, 1, 2, 12, 0)))
        for currency, category, amount in (("USD", "Rig", 1000.0), ("EUR", "Services", 500.0), (None, "Misc", 200.0)):
            s.add(CostRecord(well_id=well, category=category, actual_cost=amount, currency=currency,
                             cost_date=D[0]))
        other = DailyReport(well_id=out["other"], report_date=D[0], report_number=1, depth_0000=0, depth_2400=500)
        s.add(other)
    yield manager, out
    manager.close()


def _analyze(manager, out, **kw):
    scope = ev.AnalysisScope(well_id=out["well"], wellbore_id=kw.pop("bore", None))
    return oa.analyze(manager, scope, **kw)


def test_daily_footage_rop_and_time_weighted_rop(env):
    manager, out = env
    result = _analyze(manager, out, bore=out["bore"])
    rows = result.tables["daily"][1]
    assert [r[4] for r in rows] == [100.0, 150.0, None, None]            # missing and decreasing depth: no footage
    assert rows[0][5] == 16.0 and rows[0][8] == pytest.approx(100 / 16)
    assert rows[1][5] == 12.0 and rows[1][8] == pytest.approx(150 / 12)
    assert "missing" in rows[2][9] and "INVALID footage: depth decreased by 10 m" in rows[3][9]
    assert rows[3][5] is None and rows[3][7] is None                     # unknown duration is not 0
    s = result.summary
    assert s["weighted_rop_m_h"] == pytest.approx(250 / 28) and s["weighted_rop_days"] == "2 of 4"
    assert s["footage_m"] is None and s["footage_known_m"] == 250.0      # an incomplete sum is not a total
    assert s["logged_hours"] is None and s["npt_hours"] == 4.0 and s["npt_percent"] is None
    assert result.report_ids["daily"] == out["reports"][:4]
    assert any("without a duration" in n for n in result.notes)


def test_activities_are_mapped_explainably(env):
    manager, out = env
    acts = {r[0]: r for r in _analyze(manager, out, bore=out["bore"]).tables["activities"][1]}
    assert acts["DRILLING"][3] == 34.0 and acts["DRILLING"][6] == 1      # 10+6+12+6 known, one unknown duration
    assert "exact" in acts["DRILLING"][2]
    assert acts["UNRESOLVED"][1] == "XYZ" and acts["UNRESOLVED"][3] == 18.0
    assert acts["RIG_REPAIR"][4] == 4.0
    assert acts["UNCERTAIN: TRIPPING_OUT"][3] == 12.0 and "fuzzy" in acts["UNCERTAIN: TRIPPING_OUT"][2]


def test_npt_timeline_keeps_sources_apart(env):
    manager, out = env
    result = _analyze(manager, out)
    npt = result.tables["npt"][1]
    assert [r[7].split(" ")[0] for r in npt] == ["npt_reports", "time_logs_24h"]          # sorted by date/time
    assert npt[0][3] == 2.0 and npt[1][3] == 4.0 and npt[1][4] == "Rig repair"
    assert result.summary["npt_register_hours"] == 2.0 and result.summary["npt_hours"] == 4.0   # never summed
    assert result.report_ids["npt"] == [out["reports"][0]] * 2


def test_bit_runs_mse_and_cost_per_currency(env):
    manager, out = env
    result = _analyze(manager, out)
    runs = {r[0]: r for r in result.tables["bit_runs"][1]}
    assert runs["1"][4:9] == [1000.0, 1250.0, 250.0, 28.0, pytest.approx(250 / 28)]
    assert runs["1"][9] == "sum of daily drilled" and runs["1"][10] == 2
    assert runs["2"][6] == 30.0 and runs["2"][9] == "depth out - depth in" and runs["2"][8] is None
    mse = result.tables["mse"][1]
    assert len(mse) == 1 and mse[0][2] == 127997.67 and mse[0][3] == 25000.0
    cost = {r[0]: r for r in result.tables["cost"][1]}
    assert set(cost) == {"EUR", "USD", "UNKNOWN"} and float(cost["USD"][3]) == 1000.0
    assert result.summary["cost_status"] == "unknown-currency" and result.summary["cost_actual"] is None
    assert [r[0] for r in result.tables["plan_vs_actual"][1]] == ["depth", "hours", "rop", "cost"]


def test_scope_and_date_range_never_leak(env):
    manager, out = env
    whole = _analyze(manager, out)
    assert len(whole.tables["daily"][1]) == 5                          # sidetrack report included for the well
    bore = _analyze(manager, out, bore=out["bore"])
    assert out["reports"][4] not in bore.report_ids["daily"]
    sidetrack = _analyze(manager, out, bore=out["sidetrack"])
    assert sidetrack.report_ids["daily"] == [out["reports"][4]] and sidetrack.tables["bit_runs"][1] == []
    assert sidetrack.tables["npt"][1] == []                             # register row belongs to the other bore
    one_day = _analyze(manager, out, start=D[1], end=D[1])
    assert [r[0] for r in one_day.tables["daily"][1]] == [D[1]]
    assert one_day.tables["cost"][1] == []                              # costs dated D[0]
    assert all(r[0] != date(2026, 1, 1) or r[4] != 500.0 for r in whole.tables["daily"][1])   # other well
    with pytest.raises(ValueError, match="start date is after"):
        _analyze(manager, out, start=D[2], end=D[1])
    with pytest.raises(ValueError, match="no well selected"):
        oa.analyze(manager, ev.AnalysisScope(well_id=None))


def test_export_writes_label_scope_and_blank_for_missing(env, tmp_path):
    manager, out = env
    result = _analyze(manager, out, bore=out["bore"])
    written = oa.export(result, str(tmp_path / "oa.csv"))
    assert len(written) == len(oa.COLUMNS)
    daily = next(p for p in written if p.endswith("_daily.csv"))
    rows = list(csv.reader(open(daily, encoding="utf-8")))
    meta = {r[0]: r[1] for r in rows if r and r[0].startswith("# ")}
    assert meta["# status"] == oa.LABEL and f"(wellbore #{out['bore']})" in meta["# scope"] and meta["# method"] == oa.OA_VERSION
    header = rows.index(list(oa.COLUMNS["daily"]))
    third = rows[header + 3]
    assert third[4] == "" and "missing" in third[9]                     # missing footage exported blank, not 0
    xlsx = oa.export(result, str(tmp_path / "oa.xlsx"))
    assert xlsx == [str(tmp_path / "oa.xlsx")] and os.path.getsize(xlsx[0]) > 0
    assert glob.glob(str(tmp_path / "oa_*.csv"))


def test_w12_page_refresh_drilldown_invalidation_and_export(env, tmp_path):
    from core.selection_manager import SelectionManager
    from tabs.w12_Analysis import AnalysisWidget

    manager, out = env
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tab = AnalysisWidget(db_manager=manager)
    try:
        titles = [tab.analysis_tabs.tabText(i) for i in range(tab.analysis_tabs.count())]
        assert "🧭 Operational Analysis" in titles
        panel = tab.operational_panel
        assert panel.refresh() is None and "Select a well" in panel.status.text()
        tab.current_well_id, tab.current_wellbore_id, tab.current_well_name = out["well"], out["bore"], "SYN-A"
        assert panel.refresh() is not None               # M103: a job id; the result arrives via the runner
        result = panel.wait()
        assert result is not None and f"{250 / 28:,.2f}" in panel.summary.text()
        assert panel.tables["daily"].item(2, 4).text() == "—"           # missing, not 0
        panel.tabs.setCurrentIndex(0)
        panel.tables["daily"].selectRow(1)
        assert panel.selected_report_id() == out["reports"][1] and panel.open_btn.isEnabled()
        assert panel.open_selected() is True
        assert SelectionManager().current_report_id == out["reports"][1]
        assert panel.result is not None                                   # same well and wellbore: kept
        assert len(panel.export(str(tmp_path / "ui.csv"))) == len(oa.COLUMNS)
        tab.current_wellbore_id = out["sidetrack"]
        panel.selection_changed()
        assert panel.result is None and panel.tables["daily"].rowCount() == 0
        tab.on_selection_cleared()
        assert "Select a well" in panel.status.text() and not panel.export_btn.isEnabled()
    finally:
        SelectionManager().clear()
        tab.deleteLater()
        app.processEvents()


def test_unclassified_npt_flag_is_unknown_not_zero(env):
    manager, out = env
    with manager.session_scope() as s:
        log = TimeLog24H(report_id=out["reports"][1], time_from=time(0), time_to=time(0), duration=0.5,
                         main_code="CIR")
        s.add(log)
        s.flush()
        # the ORM default writes False; imported / legacy rows can hold NULL
        s.query(TimeLog24H).filter(TimeLog24H.id == log.id).update({"is_npt": None})
    row = _analyze(manager, out, bore=out["bore"]).tables["daily"][1][1]
    assert row[6] is None and row[4] == 150.0                           # day NPT unknown; footage unaffected
