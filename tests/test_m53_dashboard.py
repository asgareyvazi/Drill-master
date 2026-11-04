"""M53: Operations Dashboard - filters, extended KPIs, well detail, English/LTR UI.

Expected numbers are hand-derived from the documented SYNTHETIC fixtures
(tests/synthetic_operations.py + tests/synthetic_dashboard.py), not from the
implementation:

* SYN-DEV-01: six reports end-5..end, 300 m per day (0 -> 1800 m), 24 h logged
  per day; NPT 3.5 h (report 3, Rig repair), 1.5 h (report 4, Wait on
  weather), 2.0 h (report 5, Rig repair) -> 7.0 h of 144 h.
* Drilling parameters: 6 rows x (300 m, 15 h) -> weighted ROP 1800/90 = 20 m/h.
* Cost (USD, dated end-2): planned 120,000, actual 120,000 -> AFE used 100 %;
  cost per metre 120,000 / 1800 = 66.667 USD/m; NPT cost estimate
  120,000 x 7 / 144 = 5,833.33 USD.
* SYN-QA-03: one USD and one EUR record dated end-9 (outside 7 days).

Qt tests run with QT_QPA_PLATFORM=offscreen (Linux raster); they are not a
Windows desktop test.
"""
import re
from datetime import date, timedelta

import pytest

from core.operations_dashboard import (
    KPI_DEFINITIONS, KPI_GROUPS, KPI_SOURCES, DashboardFilter, build_snapshot, build_well_detail,
)
from synthetic_dashboard import build_dashboard_fixture
from synthetic_operations import make_file_database
from test_scope_attribution import _mgr

END = date(2026, 1, 15)
PERSIAN = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")


@pytest.fixture(scope="module")
def enriched(tmp_path_factory):
    db = make_file_database(tmp_path_factory.mktemp("m53") / "syn.db")
    ids = build_dashboard_fixture(db, END)
    yield db, ids
    db.engine.dispose()


# ------------------------------------------------------------------ model
def test_every_kpi_has_definition_source_group_and_freshness(enriched):
    db, _ids = enriched
    snapshot = build_snapshot(db, today=END)
    grouped = [key for _group, keys in KPI_GROUPS for key in keys]
    assert sorted(grouped) == sorted(KPI_DEFINITIONS) == sorted(KPI_SOURCES) == sorted(snapshot.kpis)
    for key, kpi in snapshot.kpis.items():
        assert kpi.definition == KPI_DEFINITIONS[key] and kpi.source == KPI_SOURCES[key], key
        assert kpi.as_of in (END,), key           # latest report date == today here


def test_extended_kpis_match_the_hand_derivation(enriched):
    db, _ids = enriched
    k = build_snapshot(db, today=END).kpis
    assert k["npt_window"].value == pytest.approx(7.0)
    assert k["npt_share"].value == pytest.approx(100 * 7.0 / 144.0)
    assert k["latest_depth"].value == 1800.0 and k["latest_depth"].note == "SYN-DEV-01"
    assert k["footage_window"].value == pytest.approx(1800.0)
    assert k["footage_window"].note == "6 of 6 reports measurable"
    assert k["rop_window"].value == pytest.approx(20.0) and k["rop_window"].unit == "m/h"
    assert k["survey_ready"].value == 1 and k["survey_ready"].note == "of 2 wells with surveys"
    assert k["survey_ready"].state == "warning"                      # QA needs review
    assert k["cost_actual"].value == pytest.approx(120_000.0) and k["cost_actual"].unit == "USD"
    assert k["afe_used"].value == pytest.approx(100.0)
    # Portfolio scope: per-metre and NPT cost are single-well figures only.
    for key in ("cost_per_metre", "npt_cost"):
        assert k[key].value is None and k[key].note == "Select a single well" and k[key].state == "no_data"


def test_single_well_cost_per_metre_and_npt_cost_estimate(enriched):
    db, ids = enriched
    k = build_snapshot(db, today=END, filters=DashboardFilter(well_id=ids["dev"])).kpis
    assert k["wells_total"].value == 1
    assert k["cost_per_metre"].value == pytest.approx(120_000.0 / 1800.0)
    assert k["cost_per_metre"].unit == "USD/m"
    assert k["npt_cost"].value == pytest.approx(120_000.0 * 7.0 / 144.0)
    assert k["npt_cost"].unit == "USD" and k["npt_cost"].note.startswith("Estimate")
    assert k["npt_cost"].label == "NPT cost (estimate)"


def test_mixed_currency_is_never_summed(enriched):
    db, ids = enriched
    k = build_snapshot(db, today=END, filters=DashboardFilter(well_id=ids["qa"], period_days=None)).kpis
    assert k["cost_actual"].value is None and k["cost_actual"].state == "warning"
    assert k["cost_actual"].note == "Multiple currencies — not summed"
    assert k["afe_used"].value is None
    assert k["cost_per_metre"].value is None and k["cost_per_metre"].note == "Multiple currencies — not summed"
    # All dates + all wells: DEV (USD) + QA (USD, EUR) -> still never one total.
    everything = build_snapshot(db, today=END, filters=DashboardFilter(period_days=None)).kpis
    assert everything["cost_actual"].value is None
    flags = {a.code for a in build_snapshot(db, today=END).attention if a.well_name == "SYN-QA-03"}
    assert "COST_CURRENCY" in flags


def test_unknown_is_never_zero_on_an_empty_database():
    k = build_snapshot(_mgr(), today=END).kpis
    for key in ("latest_depth", "footage_window", "rop_window", "survey_ready", "cost_actual", "afe_used",
                "cost_per_metre", "npt_cost"):
        assert k[key].value is None and k[key].state == "no_data", key
    assert k["documents_total"].value == 0          # a real count of nothing


def test_filters_scope_every_figure_consistently(enriched):
    db, ids = enriched
    full = build_snapshot(db, today=END)
    rig_b = build_snapshot(db, today=END, filters=DashboardFilter(rig="SYN-RIG-B"))
    assert {w.name for w in rig_b.wells} == {"SYN-VERT-02", "SYN-DONE-04"}
    assert rig_b.kpis["wells_total"].value == 2 and rig_b.kpis["reports_window"].value == 0
    assert rig_b.kpis["npt_window"].value is None and rig_b.npt_daily == [] and rig_b.npt_by_category == {}
    assert {a.well_name for a in rig_b.attention} <= {"SYN-VERT-02", "SYN-DONE-04"}
    assert all(r["well_name"] in {"SYN-VERT-02", "SYN-DONE-04"} for r in rig_b.recent_reports)
    active = build_snapshot(db, today=END, filters=DashboardFilter(status_group="active"))
    assert {w.name for w in active.wells} == {"SYN-DEV-01", "SYN-QA-03"}
    nobody = build_snapshot(db, today=END, filters=DashboardFilter(company="No such company"))
    assert nobody.empty and nobody.kpis["wells_total"].value == 0
    # Filter choices always come from ALL wells, whatever the filter.
    assert nobody.options == full.options and "SYN-RIG-A" in full.options["rigs"]
    assert (ids["dev"], "SYN-DEV-01") in full.options["wells"]
    assert rig_b.options == full.options and full.options["rigs"] == ["SYN-RIG-A", "SYN-RIG-B"]   # can switch rig


def test_period_widens_reports_npt_and_cost(enriched):
    db, _ids = enriched
    week = build_snapshot(db, today=END)
    month = build_snapshot(db, today=END, filters=DashboardFilter(period_days=30))
    assert week.kpis["reports_window"].value == 6
    # 30 days = end-29 .. end: QA end-9/end-8 enter; DONE (end-30) stays outside.
    assert month.kpis["reports_window"].value == 6 + 2
    assert build_snapshot(db, today=END, filters=DashboardFilter(period_days=31)).kpis["reports_window"].value == 9
    assert month.kpis["reports_window"].label == "Reports (30 d)"
    assert month.kpis["cost_actual"].value is None             # the EUR record of QA enters the period
    assert week.npt_by_category == {"Rig repair": pytest.approx(5.5), "Wait on weather": pytest.approx(1.5)}


def _report_well(db, depths_0000, depths_2400, logs=None, costs=()):
    """One synthetic Drilling well with consecutive reports ending at END."""
    from datetime import time
    from core.database import Company, CostRecord, DailyReport, Project, TimeLog24H, Well
    session = db.create_session()
    try:
        company = Company(name="SYNTHETIC EDGE CO", code="SYNE")
        session.add(company)
        session.flush()
        project = Project(name="SYNTHETIC EDGE FIELD", code="SYNEF", company_id=company.id)
        session.add(project)
        session.flush()
        well = Well(name="SYN-EDGE", code="SYN-EDGE", status="Drilling", project_id=project.id)
        session.add(well)
        session.flush()
        for index, (start, end) in enumerate(zip(depths_0000, depths_2400), 1):
            report = DailyReport(well_id=well.id, report_number=index, depth_0000=start, depth_2400=end,
                                 report_date=END - timedelta(days=len(depths_2400) - index))
            session.add(report)
            session.flush()
            for duration, npt in (logs or {}).get(index, ()):
                session.add(TimeLog24H(report_id=report.id, time_from=time(0), time_to=time(1),
                                       duration=duration, is_npt=npt, npt_category="SYN"))
        for planned, actual in costs:
            session.add(CostRecord(well_id=well.id, category="Rig", planned_cost=planned, actual_cost=actual,
                                   currency="USD", cost_date=END))
        session.commit()
        return well.id
    finally:
        session.close()


def test_footage_excludes_negative_and_unmeasurable_reports():
    db = _mgr()
    well_id = _report_well(db, [None, None, None, None], [100.0, 250.0, 200.0, None])
    k = build_snapshot(db, today=END, filters=DashboardFilter(well_id=well_id)).kpis
    # r1: no previous depth -> unmeasurable; r2: 250-100 = 150; r3: 200-250 < 0 -> excluded; r4: no depth.
    assert k["footage_window"].value == pytest.approx(150.0)
    assert k["footage_window"].note == "1 of 4 reports measurable"


def test_npt_and_cost_over_afe_alerts_are_deterministic_and_linked():
    db = _mgr()
    well_id = _report_well(db, [0.0], [10.0], logs={1: ((18.0, False), (6.0, True))},
                           costs=((100.0, 150.0),))
    snapshot = build_snapshot(db, today=END)
    flags = {a.code: a for a in snapshot.attention if a.well_id == well_id}
    assert flags["NPT_HIGH"].severity == "warning" and flags["NPT_HIGH"].target == "npt"
    assert "25.0%" in flags["NPT_HIGH"].message                     # 6 / 24 h
    assert flags["COST_OVER_AFE"].target == "cost" and "150.0%" in flags["COST_OVER_AFE"].message
    db2 = _mgr()
    calm = _report_well(db2, [0.0], [10.0], logs={1: ((20.0, False), (4.0, True))}, costs=((100.0, 100.0),))
    codes = {a.code for a in build_snapshot(db2, today=END).attention if a.well_id == calm}
    assert "NPT_HIGH" not in codes and "COST_OVER_AFE" not in codes  # 16.7 % NPT, 100 % AFE


def test_well_detail_series_come_from_stored_rows_only(enriched):
    db, ids = enriched
    detail = build_well_detail(db, ids["dev"])
    assert [d for _day, d in detail.depth_time] == [300.0, 600.0, 900.0, 1200.0, 1500.0, 1800.0]
    assert [r for _day, r in detail.rop] == [20.0] * 6
    assert [m for _day, m in detail.mud_weight] == [71.0, 72.0, 73.0, 74.0, 75.0, 76.0]
    assert detail.bit_runs == [("1", 900.0, pytest.approx(20.0)), ("2", 900.0, pytest.approx(20.0))]
    assert sorted(detail.cost_groups) == [("Mud", 20_000.0, 30_000.0), ("Rig", 100_000.0, 90_000.0)]
    assert detail.cost_currency == "USD" and [m for _t, m in detail.mse] == [25_000.0]
    assert detail.npt_by_category == {"Rig repair": pytest.approx(5.5), "Wait on weather": pytest.approx(1.5)}
    assert detail.trajectory_status == "READY" and len(detail.trajectory) > 2 and detail.closure is not None
    assert detail.ecd_available is False
    qa = build_well_detail(db, ids["qa"])
    assert qa.cost_status == "multi-currency" and qa.cost_groups == []    # never combined
    empty = build_well_detail(db, ids["vert"])
    assert (empty.depth_time, empty.rop, empty.mud_weight, empty.bit_runs, empty.mse, empty.trajectory) == \
        ([], [], [], [], [], [])
    assert empty.trajectory_status == "NO_DATA"
    assert build_well_detail(db, 999_999) is None


def test_activity_lists_types_never_labels_or_file_names(enriched):
    db, _ids = enriched
    snapshot = build_snapshot(db, today=END)
    texts = [a["text"] for a in snapshot.activity]
    assert "MSE calculation saved · SYN-DEV-01" in texts
    assert not any("SYNTHETIC MSE" in text for text in texts)              # the user's label stays private
    assert [a["when"] for a in snapshot.activity] == sorted((a["when"] for a in snapshot.activity), reverse=True)


# --------------------------------------------------------------------- UI
@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _home(db, today=END):
    from PySide6.QtWidgets import QApplication
    from tabs.home_tab import HomeTab
    home = HomeTab(db)
    home.refresh_timer.stop()
    home.today_provider = lambda: today
    QApplication.processEvents()
    home.wait_for_load()
    home.load_data()
    assert home.wait_for_load()
    QApplication.processEvents()
    return home


def _settle(app, home):
    for _ in range(3):
        assert home.wait_for_load()
        app.processEvents()


def test_dashboard_is_english_and_left_to_right_even_in_an_rtl_application(app, enriched):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QAbstractButton, QComboBox, QLabel, QListWidget, QTableWidget
    db, ids = enriched
    previous = app.layoutDirection()
    app.setLayoutDirection(Qt.RightToLeft)
    try:
        home = _home(db)
        home.focus_well(ids["dev"])
        _settle(app, home)
        assert home.layoutDirection() == Qt.LeftToRight
        assert home.wells_table.layoutDirection() == Qt.LeftToRight
        assert home.charts["depth"].layoutDirection() == Qt.LeftToRight
        texts = []
        texts += [w.text() for w in home.findChildren(QLabel)]
        texts += [w.text() for w in home.findChildren(QAbstractButton)]
        texts += [w.toolTip() for w in home.findChildren(QLabel)] + [c.toolTip() for c in home.kpi_cards.values()]
        for combo in home.findChildren(QComboBox):
            texts += [combo.itemText(i) for i in range(combo.count())]
        for table in home.findChildren(QTableWidget):
            texts += [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
            texts += [table.item(r, c).text() for r in range(table.rowCount()) for c in range(table.columnCount())
                      if table.item(r, c) is not None]
        for listing in home.findChildren(QListWidget):
            texts += [listing.item(i).text() for i in range(listing.count())]
        texts += [chart.unavailable for chart in home.charts.values()]
        offending = [text for text in texts if PERSIAN.search(text or "")]
        assert offending == [] and len(texts) > 150
        home.cleanup()
    finally:
        app.setLayoutDirection(previous)


def test_filter_change_updates_kpis_portfolio_alerts_and_scope(app, enriched):
    db, _ids = enriched
    home = _home(db)
    assert home.kpi_cards["wells_total"].value.text() == "5"
    home.set_filter(rig="SYN-RIG-B")
    _settle(app, home)
    assert home.filters.rig == "SYN-RIG-B" and home.snapshot.filters.rig == "SYN-RIG-B"
    assert home.kpi_cards["wells_total"].value.text() == "2"
    names = {home.wells_table.item(r, 0).text() for r in range(home.wells_table.rowCount())}
    assert names == {"SYN-VERT-02", "SYN-DONE-04"}
    alerts = [home.attention_list.item(i).text() for i in range(home.attention_list.count())]
    assert alerts and all("SYN-VERT-02" in a or "SYN-DONE-04" in a for a in alerts)
    assert "rig SYN-RIG-B" in home.scope_label.text()
    home.set_filter(company="No such company")
    _settle(app, home)
    assert not home.empty_panel.isHidden() and home.content.isHidden()
    assert home.empty_panel.title.text() == "No wells match the filters"
    home.reset_filters()
    _settle(app, home)
    assert home.kpi_cards["wells_total"].value.text() == "5" and home.content.isVisibleTo(home)
    home.cleanup()


def test_selecting_a_well_loads_its_charts_and_trajectory(app, enriched):
    db, ids = enriched
    home = _home(db)
    assert not home.charts["depth"].has_data and home.charts["depth"].unavailable.startswith("Select a well")
    assert home.focus_well(ids["dev"])
    _settle(app, home)
    assert home.detail is not None and home.detail.well_id == ids["dev"]
    for key in ("depth", "rop", "mw", "bits", "mse", "cost", "npt_cat"):
        assert home.charts[key].has_data, key
    # M123 (D6): saved MSE runs are discrete whole-well points by save time; the fixture run has no
    # recorded lineage, so it is drawn only in the legacy series.
    mse_chart = home.charts["mse"]
    assert mse_chart.kind == "points" and mse_chart.x_unit == "saved at (not depth)"
    assert [label for label, _pts, _c in mse_chart.series] == ["LEGACY — lineage unknown"]
    assert len(home.trajectory_preview.stations) == len(home.detail.trajectory) > 2
    assert home.selected_title.text() == "SYN-DEV-01"
    assert home.full_trajectory_btn.isEnabled()
    home.focus_well(ids["vert"])                       # no reports, no surveys
    _settle(app, home)
    assert not home.charts["depth"].has_data and home.charts["depth"].unavailable == "No reports with a 24:00 depth"
    assert home.trajectory_preview.stations == []
    assert home.trajectory_preview.message == "No survey stations stored for this well"
    home.focus_well(ids["qa"])
    _settle(app, home)
    assert home.charts["cost"].unavailable == "Cost records use several currencies; not combined"
    home.clear_focus()
    _settle(app, home)
    assert home.focus_well_id is None and home.selected_title.text().startswith("Select a well")
    home.cleanup()


def test_stale_results_are_discarded(app, enriched):
    db, ids = enriched
    home = _home(db)
    count = home.load_count
    old = home.filters
    snapshot = home.snapshot
    home.filters = DashboardFilter(rig="SYN-RIG-A")
    home._on_loaded((old, snapshot, None))              # a result computed for the previous filter
    assert home.load_count == count and home.stale_discarded == 1 and home._refresh_pending
    home._refresh_pending = False
    home.filters = old
    home.focus_well_id = ids["qa"]
    home._on_detail_loaded((ids["dev"], build_well_detail(db, ids["dev"])))
    assert home.detail is None or home.detail.well_id != ids["dev"]
    assert home.stale_discarded == 2
    home._detail_pending = False
    home.cleanup()


def test_kpi_cards_drill_down(app, enriched):
    db, ids = enriched
    home = _home(db)
    payloads = []
    home.navigate_requested.connect(payloads.append)
    home.drill_down(home.kpi_cards["wells_active"].kpi)
    _settle(app, home)
    assert home.filters.status_group == "active" and home.kpi_cards["wells_total"].value.text() == "2"
    home.drill_down(home.kpi_cards["wells_total"].kpi)            # back to all statuses
    _settle(app, home)
    assert home.filters.status_group is None and home.kpi_cards["wells_total"].value.text() == "5"
    home.drill_down(home.kpi_cards["latest_depth"].kpi)            # deepest well gets selected
    _settle(app, home)
    assert home.focus_well_id == ids["dev"]
    home.drill_down(home.kpi_cards["cost_actual"].kpi)
    assert payloads[-1] == {"type": "well_tab", "well_id": ids["dev"], "tab_title": "Cost"}
    tooltip = home.kpi_cards["cost_actual"].toolTip()
    assert tooltip.startswith(KPI_DEFINITIONS["cost_actual"]) and "Source: cost_records" in tooltip
    assert home.kpi_cards["cost_actual"].value.text() == "120,000.00 USD"
    home.cleanup()


def test_npt_and_cost_alerts_navigate_to_their_tabs(app):
    from PySide6.QtCore import Qt
    db = _mgr()
    well_id = _report_well(db, [0.0], [10.0], logs={1: ((18.0, False), (6.0, True))}, costs=((100.0, 150.0),))
    home = _home(db)
    payloads = []
    home.navigate_requested.connect(payloads.append)
    items = {home.attention_list.item(i).data(Qt.UserRole).code: home.attention_list.item(i)
             for i in range(home.attention_list.count())}
    home._attention_activated(items["NPT_HIGH"])
    home._attention_activated(items["COST_OVER_AFE"])
    assert payloads == [{"type": "well_tab", "well_id": well_id, "tab_title": "Analysis"},
                        {"type": "well_tab", "well_id": well_id, "tab_title": "Cost"}]
    home.cleanup()


def test_charts_paint_every_kind_and_unavailable_states(app):
    from datetime import datetime
    from tabs.dashboard_widgets import LIGHT, MiniChart, TrajectoryPreview
    days = [(END - timedelta(days=i), 100.0 * i) for i in range(5, 0, -1)]
    cases = (("line", [("d", days, "cyan")]), ("bar", [("b", [("1", 900.0), ("2", 450.0)], "amber")]),
             ("bar", [("p", [("Mud", 1.0)], "blue"), ("a", [("Mud", 2.0)], "amber")]),
             ("hbar", [("n", [("Rig repair", 5.5), ("Wait", 1.5)], "multi")]),
             ("line", [("m", [(datetime(2026, 1, 15, 12), 25_000.0)], "cyan")]))
    for kind, series in cases:
        chart = MiniChart()
        chart.resize(360, 220)
        chart.set_data(kind, series, "unit")
        assert chart.has_data and not chart.grab().isNull()
        assert chart._hits, kind                         # tooltips exist for every drawn value
    chart = MiniChart()
    chart.set_theme(LIGHT)
    chart.set_data("line", [("x", [], "cyan")], "u", unavailable="No mud reports with MW")
    assert not chart.has_data and chart.unavailable == "No mud reports with MW" and not chart.grab().isNull()
    preview = TrajectoryPreview()
    preview.resize(360, 200)
    preview.set_stations([(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)], "Fewer than two valid survey stations")
    assert not preview.grab().isNull()
    preview.set_stations([(i * 30.0, i * 29.0, i * 3.0, i * 4.0, i * 5.0, 1.0) for i in range(10)])
    assert not preview.grab().isNull()
