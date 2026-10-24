"""M44 PySide6 widget tests: trajectory viewer, operations dashboard, routing.

Environment label: these run under QT_QPA_PLATFORM=offscreen (in the sandbox
also with stub GL/dbus/xkb shared libraries).  They exercise real widgets and
real SQLite databases but are NOT native Windows desktop testing.  The
``MainWindow`` routing tests call the real methods on a stub ``self`` (no full
window); the full window is exercised by tools/screenshots/capture_m44.py.
"""
import os
import subprocess
import sys
import threading
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QTabWidget, QWidget  # noqa: E402

from core.well_trajectory import ERROR, NO_DATA, READY, REVIEW_REQUIRED  # noqa: E402
from synthetic_operations import build_synthetic_operations, make_file_database  # noqa: E402
from test_scope_attribution import _mgr  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    db = make_file_database(tmp_path_factory.mktemp("ui") / "syn.db")
    ids = build_synthetic_operations(db, end_date=date.today() - timedelta(days=1))
    yield db, ids
    db.engine.dispose()


# ----------------------------------------------------- pyqtgraph globals
def test_analysis_tab_does_not_change_pyqtgraph_global_config():
    """w12 used to force useOpenGL=True and a dark theme for every plot in the app."""
    code = (
        "import pyqtgraph as pg\n"
        "before = {k: pg.getConfigOption(k) for k in ('useOpenGL', 'background', 'foreground', 'antialias')}\n"
        "from PySide6.QtWidgets import QApplication\n"
        "app = QApplication([])\n"
        "import tabs.w12_Analysis as w12\n"
        "widget = w12._analysis_plot_widget()\n"
        "after = {k: pg.getConfigOption(k) for k in before}\n"
        "assert before == after, (before, after)\n"
        "assert after['useOpenGL'] is False\n"
        "print('OK')\n"
    )
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True,
                            timeout=120)
    assert result.returncode == 0 and "OK" in result.stdout, result.stderr[-2000:]


def test_no_module_sets_pyqtgraph_global_options():
    offenders = []
    for folder in ("tabs", "core", "dialogs", "ui"):
        for path in (ROOT / folder).rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "pg.setConfigOption" in text or "pyqtgraph.setConfigOption" in text:
                offenders.append(str(path.relative_to(ROOT)))
    for name in ("main_window.py", "app.py"):
        if "setConfigOption" in (ROOT / name).read_text(encoding="utf-8", errors="replace"):
            offenders.append(name)
    assert offenders == []


# ------------------------------------------------------ trajectory viewer
def _viewer(db):
    from tabs.trajectory_viewer import TrajectoryViewerTab
    return TrajectoryViewerTab(db)


def _drawn_items(plot):
    return len(plot.listDataItems()) + sum(1 for item in plot.items() if type(item).__name__ == "ScatterPlotItem")


def test_viewer_ready_well_banner_table_and_selection(app, synthetic):
    db, ids = synthetic
    viewer = _viewer(db)
    viewer.set_context(ids["dev"], None)
    assert viewer.banner.property("status") == READY
    text = viewer.banner.text()
    assert "61 station(s) from 66 stored row(s)" in text and "VS azimuth 135.00° (closure)" in text
    assert viewer.table.rowCount() == 61 and _drawn_items(viewer.plan_plot) > 0
    assert _drawn_items(viewer.section_plot) > 0

    received = []
    viewer.station_selected.connect(received.append)
    viewer.select_station(60)
    assert received == [60] and viewer.selected_index == 60
    assert viewer.info_labels["MD"].text() == "1,800.00 m"
    assert viewer.info_labels["Inclination"].text() == "40.00°"
    assert viewer.info_labels["TVD"].text() == "1,612.06 m"
    assert viewer.info_labels["Vertical section"].text() == "586.74 m"
    assert viewer.info_labels["Source"].text() == f"report id(s) {ids['reports'][6]}"
    assert viewer.table.currentRow() == 60
    highlights = [i for i in viewer.section_plot.items() if getattr(i, "_m44_highlight", False)]
    assert len(highlights) == 1

    viewer.table.selectRow(10)
    assert viewer.selected_index == 10 and viewer.info_labels["MD"].text() == "300.00 m"


def test_viewer_unit_switch_keeps_selection_and_converts(app, synthetic):
    db, ids = synthetic
    viewer = _viewer(db)
    viewer.set_context(ids["dev"], None)
    viewer.select_station(60)
    viewer.unit_combo.setCurrentIndex(viewer.unit_combo.findData("ft"))
    assert viewer.selected_index == 60
    assert viewer.info_labels["MD"].text() == f"{1800 / 0.3048:,.2f} ft"           # 5,905.51 ft
    assert viewer.info_labels["DLS"].text().endswith("°/100 ft")
    assert viewer.table.horizontalHeaderItem(0).text() == "MD (ft)"
    assert viewer.table.horizontalHeaderItem(7).text() == "DLS (°/100 ft)"
    build_row = 25                                                                # MD 750 m, in the build
    assert viewer.table.item(build_row, 7).text() == f"{2.0 * 30.48 / 30:,.2f}"     # 2.03 deg/100 ft
    assert "Vertical section (ft)" in viewer.section_plot.getAxis("bottom").labelText


def test_viewer_custom_vs_azimuth(app, synthetic):
    db, ids = synthetic
    viewer = _viewer(db)
    viewer.set_context(ids["dev"], None)
    viewer.vs_mode_combo.setCurrentIndex(viewer.vs_mode_combo.findData("user"))
    assert viewer.vs_spin.isEnabled()
    viewer.vs_spin.setValue(45.0)
    viewer.reload()
    assert viewer.trajectory.vs_azimuth_source == "user" and "(custom)" in viewer.banner.text()
    # 90 deg off the 135 deg closure direction -> VS ~ 0 at TD
    assert abs(viewer.stations[-1].vs) < 0.05
    assert "@ 45.00°" in viewer.section_plot.getAxis("bottom").labelText


def test_viewer_scope_change_reloads_and_aspect_is_equal_by_default(app, synthetic):
    db, ids = synthetic
    viewer = _viewer(db)
    viewer.set_context(ids["dev"], ids["reports"][1])
    assert viewer.table.rowCount() == 61                          # whole-well scope by default
    viewer.scope_combo.setCurrentIndex(viewer.scope_combo.findData("report"))
    assert viewer.table.rowCount() == 11                          # 0..300 m of report 1, no explicit reload
    for plot in (viewer.plan_plot, viewer.section_plot):
        assert plot.getViewBox().state["aspectLocked"]            # equal axis scale
    viewer.aspect_check.setChecked(False)
    for plot in (viewer.plan_plot, viewer.section_plot):
        assert not plot.getViewBox().state["aspectLocked"]


def test_viewer_review_required_well_lists_issues(app, synthetic):
    db, ids = synthetic
    viewer = _viewer(db)
    viewer.set_context(ids["qa"], None)
    assert viewer.banner.property("status") == REVIEW_REQUIRED
    codes = [viewer.issue_list.item(i).data(Qt.UserRole) for i in range(viewer.issue_list.count())]
    assert {"CONFLICTING_DUPLICATE", "MISSING_ANGLE", "TIE_ON_ASSUMED"} <= set(codes)
    assert viewer.table.rowCount() == 2
    assert all(viewer.issue_list.item(i).toolTip() for i in range(viewer.issue_list.count()))


def test_viewer_states_without_a_drawable_path(app, synthetic, monkeypatch):
    db, ids = synthetic
    viewer = _viewer(db)
    viewer.set_context(None)
    assert viewer.banner.property("status") == NO_DATA and "Select a well" in viewer.banner.text()
    viewer.set_context(ids["vert"], None)                       # well without surveys
    assert viewer.banner.property("status") == NO_DATA
    assert viewer.table.rowCount() == 0 and _drawn_items(viewer.plan_plot) == 0
    assert _drawn_items(viewer.section_plot) == 0

    viewer.scope_combo.setCurrentIndex(viewer.scope_combo.findData("report"))
    viewer.set_context(ids["dev"], None)                        # report scope, no report chosen
    assert viewer.banner.property("status") == NO_DATA and "daily report" in viewer.banner.text()
    viewer.set_context(ids["dev"], ids["reports"][1])
    assert viewer.banner.property("status") == READY and viewer.table.rowCount() == 11

    def broken(**_kwargs):
        raise RuntimeError("synthetic read failure")
    monkeypatch.setattr(db, "load_survey_points", broken)
    viewer.reload()
    assert viewer.banner.property("status") == ERROR and "RuntimeError" in viewer.banner.text()
    assert viewer.table.rowCount() == 0 and _drawn_items(viewer.plan_plot) == 0


def test_viewer_single_station_is_listed_but_not_drawn(app):
    class OneStation:
        def load_survey_points(self, well_id=None, report_id=None):
            return [{"id": 1, "md": 100.0, "inc": 1.0, "azi": 10.0, "report_id": 1}]
    viewer = _viewer(OneStation())
    viewer.set_context(1, None)
    assert "Insufficient data" in viewer.banner.text()
    assert viewer.table.rowCount() == 1
    assert _drawn_items(viewer.plan_plot) == 0 and _drawn_items(viewer.section_plot) == 0


def test_trajectory_widget_hosts_viewer_first(app, synthetic):
    from tabs.w6_Trajectory_Widget import TrajectoryWidget
    db, ids = synthetic
    widget = TrajectoryWidget(db)
    assert widget.tab_widget.widget(0) is widget.viewer_tab
    assert widget.tab_widget.tabText(0) == "Well Trajectory Viewer"
    widget.tab_widget.setCurrentIndex(2)
    widget.show_viewer()
    assert widget.tab_widget.currentWidget() is widget.viewer_tab


# ------------------------------------------------------ dashboard widget
def _home(db, parent_window=None):
    """A HomeTab whose own deferred first load has completed (load_count == 1)."""
    from tabs.home_tab import HomeTab
    home = HomeTab(db)
    home.refresh_timer.stop()
    home.parent_window = parent_window
    QApplication.processEvents()                       # fires the deferred first load
    assert home.wait_for_load()
    QApplication.processEvents()
    assert home.load_count == 1
    return home


def _load(app, home):
    home.load_data()
    assert home.wait_for_load()
    app.processEvents()


def test_dashboard_empty_database_shows_empty_state_and_no_data(app):
    home = _home(_mgr())
    assert not home.empty_panel.isHidden() and home.content.isHidden()
    assert home.kpi_cards["latest_report"].value.text() == "No data"
    assert home.kpi_cards["npt_share"].value.text() == "No data"
    assert home.kpi_cards["wells_total"].value.text() == "0"
    assert home.kpi_cards["npt_window"].toolTip().startswith("Sum of 24-h time-log durations")


def test_dashboard_loads_in_worker_thread_for_file_database(app, synthetic, monkeypatch):
    from core import operations_dashboard
    from core.export_jobs import has_isolated_reader
    db, ids = synthetic
    assert has_isolated_reader(db)
    threads = []
    real = operations_dashboard.build_snapshot

    def spy(manager, today=None):
        threads.append(threading.get_ident())
        assert manager is not db                       # a read-only worker view, not the shared manager
        return real(manager, today=today)
    monkeypatch.setattr(operations_dashboard, "build_snapshot", spy)
    home = _home(db)
    assert threads and threads[0] != threading.get_ident()
    assert home.load_count == 1 and home.kpi_cards["wells_total"].value.text() == "5"
    assert home.wells_table.rowCount() == 5
    assert home.wells_table.item(0, 0).text() == "SYN-QA-03"
    assert home.attention_list.item(0).text().startswith("ERROR · SYN-QA-03")
    assert home.recent_table.rowCount() == 9
    assert "Updated" in home.state_label.text()


def test_dashboard_refresh_while_loading_is_queued_not_concurrent(app, synthetic):
    db, _ids = synthetic
    home = _home(db)
    home.load_data()
    first = home._worker
    assert first is not None
    home.load_data()                                   # queued
    assert home._worker is first and home._refresh_pending
    assert home.wait_for_load()
    app.processEvents()
    assert home.wait_for_load()                        # the queued reload
    app.processEvents()
    assert home.load_count == 3 and not home._refresh_pending and home._worker is None
    assert home.refresh_btn.isEnabled()


def test_dashboard_load_failure_keeps_previous_figures_marked_stale(app, monkeypatch):
    from core import operations_dashboard
    db = _mgr()
    home = _home(db)
    assert home.load_count == 1

    def broken(_db, today=None):
        raise RuntimeError("synthetic failure")
    monkeypatch.setattr(operations_dashboard, "build_snapshot", broken)
    _load(app, home)
    assert home.load_count == 1
    assert home.state_label.text().startswith("Load failed (RuntimeError)")
    assert "showing data from" in home.state_label.text()
    assert home.kpi_cards["wells_total"].value.text() == "0"
    assert home.refresh_btn.isEnabled()


def test_dashboard_drill_down_payloads(app, synthetic):
    db, ids = synthetic
    home = _home(db)
    payloads = []
    home.navigate_requested.connect(payloads.append)
    assert not home.open_well_btn.isEnabled()
    row = next(r for r in range(home.wells_table.rowCount()) if home.wells_table.item(r, 0).text() == "SYN-DEV-01")
    home.wells_table.selectRow(row)
    assert home.open_report_btn.isEnabled()
    home.open_well_btn.click()
    home.open_report_btn.click()
    home.open_trajectory_btn.click()
    assert payloads[0] == {"type": "well", "id": ids["dev"]}
    assert payloads[1]["type"] == "daily_report" and payloads[1]["report_id"] == ids["reports"][6]
    assert payloads[1]["well_id"] == ids["dev"] and payloads[1]["section_id"]
    assert payloads[2] == {"type": "well_tab", "well_id": ids["dev"], "tab_title": "Trajectory", "subtab": "viewer"}

    payloads.clear()
    home._attention_activated(home.attention_list.item(0))               # SURVEY_CONFLICT on QA
    assert payloads[-1]["type"] == "well_tab" and payloads[-1]["well_id"] == ids["qa"]
    depth_item = next(home.attention_list.item(i) for i in range(home.attention_list.count())
                      if "midnight depth" in home.attention_list.item(i).text())
    home._attention_activated(depth_item)
    assert payloads[-1]["type"] == "daily_report" and payloads[-1]["report_id"] == ids["qa_reports"][1]
    home._recent_activated(0, 0)
    assert payloads[-1]["report_id"] == ids["reports"][6]

    vert = next(r for r in range(home.wells_table.rowCount()) if home.wells_table.item(r, 0).text() == "SYN-VERT-02")
    home.wells_table.selectRow(vert)
    assert home.open_well_btn.isEnabled() and not home.open_report_btn.isEnabled()


def test_dashboard_system_panel_reports_real_backup_and_autosave_state(app, tmp_path):
    from core.managers import AutoSaveManager
    db = _mgr()
    unrelated = tmp_path / "unrelated.db"
    unrelated.write_bytes(b"\0" * 4096)
    db.db_path = str(unrelated)                     # configured path exists but is not the engine's DB
    manager = AutoSaveManager()
    holder = QWidget()
    manager.enable_for_widget("synthetic", holder, interval_minutes=5)
    parent = SimpleNamespace(backup_service=SimpleNamespace(list_backups=lambda deep=False: []),
                             auto_save_manager=manager, _autosave_managers=lambda: [manager])
    home = _home(db, parent)
    assert home.system_labels["Last verified backup"].text() == "No verified backup found"
    assert home.system_labels["Autosave"].text() == "1 editor timer(s) running"
    # The configured db_path may name an unrelated file; the engine is in memory.
    assert home.system_labels["Database"].text() == "In-memory database"

    parent.backup_service = SimpleNamespace(
        list_backups=lambda deep=False: [(tmp_path / "b.db", {"created_utc": "2026-01-15T10:00:00"})])
    manager.set_enabled(False)
    _load(app, home)
    assert home.system_labels["Last verified backup"].text() == "2026-01-15 10:00:00 UTC"
    assert home.system_labels["Autosave"].text() == "Paused"

    def unreadable(deep=False):
        raise PermissionError("synthetic")
    parent.backup_service = SimpleNamespace(list_backups=unreadable)
    _load(app, home)
    assert home.system_labels["Last verified backup"].text() == "Could not read backups (PermissionError)"

    home.parent_window = None
    _load(app, home)
    assert home.system_labels["Last verified backup"].text() == "Backup service not available"
    assert home.system_labels["Autosave"].text() == "Unknown"


def test_dashboard_database_size_uses_file(app, synthetic):
    db, _ids = synthetic
    home = _home(db)
    text = home.system_labels["Database"].text()
    assert text.startswith("syn.db · ") and (text.endswith(" KB") or text.endswith(" MB"))


# ------------------------------------------------- worker reader guard
def test_isolated_reader_only_for_the_engines_own_file(synthetic, tmp_path):
    from core.export_jobs import has_isolated_reader, worker_database
    db, _ids = synthetic
    assert has_isolated_reader(db)
    memory = _mgr()
    memory.db_path = str(tmp_path / "unrelated.db")         # configured path != the in-memory engine
    assert not has_isolated_reader(memory)
    with worker_database(memory) as view:
        assert view is memory                                # never redirected to an unrelated file
    memory.db_path = ":memory:"
    assert not has_isolated_reader(memory)
    original = db.db_path
    try:
        db.db_path = str(tmp_path / "different-file.db")   # file engine, but not this file
        assert not has_isolated_reader(db)
    finally:
        db.db_path = original
    assert has_isolated_reader(db)


# ----------------------------------------- MainWindow routing (stub self)
class _Selection:
    def __init__(self):
        self.calls = []

    def select_well(self, well_id, data):
        self.calls.append(("well", well_id))

    def select_section(self, section_id, data):
        self.calls.append(("section", section_id))

    def select_report(self, report_id, data):
        self.calls.append(("report", report_id))


def _stub_window():
    from main_window import MainWindow
    tabs = QTabWidget()
    for title in ("🏠 Home", "🛢️ Well Info", "📋 Daily Report", "📈 Trajectory"):
        page = QWidget()
        tabs.addTab(page, title)
    shown = []
    tabs.widget(3).show_viewer = lambda: shown.append(True)
    stub = SimpleNamespace(
        tab_widget=tabs, sel_manager=_Selection(), current_well_label=QLabel(),
        db_manager=SimpleNamespace(get_well_by_id=lambda wid: {"id": wid, "name": f"SYN-{wid}"},
                                   get_sections_by_well=lambda wid: [{"id": 7, "name": "s"}]),
        _select_wellbore_from_payload=lambda data, well_id: None)
    stub.navigate_to = lambda data: MainWindow.navigate_to(stub, data)
    return MainWindow, stub, shown


def test_navigate_to_routes_dashboard_payloads(app):
    MainWindow, stub, shown = _stub_window()
    assert MainWindow.navigate_to(stub, {"type": "well", "id": 3}) is True
    assert stub.sel_manager.calls[-1] == ("well", 3) and stub.tab_widget.currentIndex() == 1
    assert MainWindow.navigate_to(stub, {"type": "daily_report", "id": 9, "report_id": 9,
                                         "section_id": 7, "well_id": 3}) is True
    assert stub.sel_manager.calls[-3:] == [("well", 3), ("section", 7), ("report", 9)]
    assert stub.tab_widget.currentIndex() == 2
    assert MainWindow.navigate_to(stub, {"type": "well_tab", "well_id": 3, "tab_title": "Trajectory",
                                         "subtab": "viewer"}) is True
    assert stub.tab_widget.currentIndex() == 3 and shown == [True]
    assert MainWindow.navigate_to(stub, {"type": "company", "id": 1}) is False
    assert MainWindow.navigate_to(stub, None) is False


def test_tree_click_toggles_non_navigable_nodes_only(app):
    from PySide6.QtWidgets import QTreeWidgetItem
    MainWindow, stub, _shown = _stub_window()
    from PySide6.QtWidgets import QTreeWidget
    tree = QTreeWidget()
    company = QTreeWidgetItem(["SYN company"])
    tree.addTopLevelItem(company)
    company.setData(0, Qt.UserRole, {"type": "company", "id": 1})
    company.addChild(QTreeWidgetItem(["child"]))
    MainWindow.on_tree_item_clicked(stub, company, 0)
    assert company.isExpanded()
    well = QTreeWidgetItem(["SYN well"])
    tree.addTopLevelItem(well)
    well.setData(0, Qt.UserRole, {"type": "well", "id": 4})
    well.addChild(QTreeWidgetItem(["child"]))
    MainWindow.on_tree_item_clicked(stub, well, 0)
    assert not well.isExpanded() and stub.sel_manager.calls[-1] == ("well", 4)


def test_status_bar_well_label_follows_selection(app):
    MainWindow, stub, _shown = _stub_window()
    MainWindow._show_selected_well(stub, 4, {"name": "SYN-DEV-01"})
    assert stub.current_well_label.text().endswith("Well: SYN-DEV-01")
    MainWindow._show_selected_well(stub, 5, None)
    assert stub.current_well_label.text().endswith("Well: id 5")
