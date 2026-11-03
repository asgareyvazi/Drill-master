"""M102: full selection context through the real MainWindow (offscreen Qt, SYNTHETIC file database).

The well "SYN-ALPHA-01" is seeded with alpha-only marks in every kind of data a
tab can show: report dates, summaries, activities and NPT, survey stations, a
survey revision, a plan, a case, an architecture revision, a cost record, a
form field and a linked document.  After switching to another well (or after a
clear), no tab, nested panel, model view, spin box, date edit, group title,
tab label or plot may still show any of them.  Positive controls prove that
the probe sees each data kind while the alpha well is selected.
Offscreen Qt on Linux; not Windows desktop acceptance.
"""
from __future__ import annotations

import os
import time
from datetime import date, time as dtime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QSettings  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractItemView, QAbstractSpinBox, QApplication, QComboBox, QDateEdit, QDateTimeEdit, QGroupBox, QLabel,
    QLineEdit, QListWidget, QPlainTextEdit, QTabBar, QTableWidget, QTextEdit, QTreeWidget,
)

from core.selection_manager import SelectionManager  # noqa: E402

PORTFOLIO = {"HomeTab", "DocumentsTab"}      # portfolio-wide by design (Documents: default filter "All documents")
ALPHA_DATES = (date(2031, 7, 19), date(2031, 7, 20))
MARKS = {
    "identity": ("SYN-ALPHA-01", "SYN-A1", "SYN RIG 1", "SYN FIELD", "SYN 12 1/4"),
    "report date": ("2031-07-19", "2031-07-20", "19/07/2031", "20/07/2031", "07/19/2031", "07/20/2031"),
    "description": ("SYNALPHA-SUMMARY", "SYNALPHA-ACTIVITY", "SYNALPHA-OBJECTIVE"),
    "npt": ("SYNALPHA-NPT",),
    "station": ("1777.77", "1,777.77"),
    "plan": ("SYNALPHA-PLAN",),
    "case": ("SYNALPHA-CASE",),
    "architecture": ("SYNALPHA-ARCH",),
    "cost": ("SYNALPHA-COST", "98765.43", "98,765.43"),
    "document": ("syn_alpha_daily",),
}


def _pump(seconds=0.2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def _seed_alpha(db, ids, work):
    from sqlalchemy import text

    from core import calculation_cases as cc
    from core import directional_plans as dp
    from core import survey_revisions as sr
    from core import well_architecture as wa
    from core.database import CostRecord, TimeLog24H, Wellbore
    from core.document_links import DocumentLinkService
    from document_link_fixtures import import_documents, write_documents

    alpha, r1, r2 = ids["alpha"], ids["report_1"], ids["report_2"]
    with db.session_scope() as session:
        bore = Wellbore(well_id=alpha, name="SYN-ALPHA-01 OH", wellbore_type="original")
        session.add(bore)
        session.flush()
        ids["bore"] = bore.id
    with db.session_scope() as session:
        session.execute(text("UPDATE daily_reports SET report_date=:d, summary=:s WHERE id=:i"),
                        {"d": ALPHA_DATES[0], "s": "SYNALPHA-SUMMARY day one", "i": r1})
        session.execute(text("UPDATE daily_reports SET report_date=:d, summary=:s WHERE id=:i"),
                        {"d": ALPHA_DATES[1], "s": "SYNALPHA-SUMMARY day two", "i": r2})
        session.execute(text("UPDATE wells SET objectives='SYNALPHA-OBJECTIVE target' WHERE id=:i"), {"i": alpha})
        session.add(TimeLog24H(report_id=r1, time_from=dtime(0, 0), time_to=dtime(20, 0), duration=20.0,
                               main_phase="DRILLING", main_code="DRL", is_npt=False,
                               activity_description="SYNALPHA-ACTIVITY drilling ahead"))
        session.add(TimeLog24H(report_id=r1, time_from=dtime(20, 0), time_to=dtime(23, 59), duration=4.0,
                               main_phase="DRILLING", main_code="NPT", is_npt=True, npt_category="Rig repair",
                               activity_description="SYNALPHA-NPT top drive repair"))
        session.add(CostRecord(well_id=alpha, category="Rig", description="SYNALPHA-COST rig day rate",
                               actual_cost=98765.43, currency="USD", cost_date=ALPHA_DATES[0]))
    stations = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 600.0, "inc": 0.0, "azi": 0.0},
                {"md": 1200.0, "inc": 18.0, "azi": 135.0}, {"md": 1777.77, "inc": 31.0, "azi": 140.0}]
    db.save_survey_records([dict(s, well_id=alpha, report_id=r2, tool="MWD") for s in stations],
                           replace_scope=(alpha, r2))
    sr.save_revision(db, alpha, stations, depth_datum="RKB", azimuth_reference="true")
    dp.save_plan(db, well_id=alpha, name="SYNALPHA-PLAN option A", inputs=dp.plan_inputs(
        [{"type": "hold", "length": 600.0}, {"type": "curve", "inc": 30.0, "azi": 135.0, "dls": 3.0}]))
    cc.save_case(db, calculator="Quick Calc", name="SYNALPHA-CASE kill check", inputs={"a": 1}, results={"r": 1},
                 well_id=alpha)
    wa.save_revision(db, alpha, [
        {"kind": "section", "name": "SYNALPHA-ARCH 12-1/4 hole", "top_md": 0, "bottom_md": 1500, "hole_in": 12.25},
        {"kind": "casing", "name": "SYNALPHA-ARCH 9-5/8 csg", "top_md": 0, "bottom_md": 1500, "od_in": 9.625,
         "id_in": 8.681, "hole_in": 12.25, "grade": "SYN-80", "weight_ppf": 47},
    ])
    paths = write_documents(work / "docs")
    docs = import_documents(db, paths)
    DocumentLinkService(db).create_link(docs["alpha"], alpha, None)
    ids["alpha_doc"] = docs["alpha"]


@pytest.fixture(scope="module")
def window(tmp_path_factory):
    from core.permissions import permissions, session_user
    from document_link_fixtures import build_link_world
    from synthetic_operations import make_file_database

    app = QApplication.instance() or QApplication([])
    work = tmp_path_factory.mktemp("m102_window")
    mp = pytest.MonkeyPatch()
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(work),
                       "DRILLMASTER_LOG_DIR": str(work / "logs"), "DRILLMASTER_BACKUP_DIR": str(work / "backups"),
                       "DRILLMASTER_AI_IMPORT": "0"}.items():
        mp.setenv(key, value)
    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(work / "settings"))
    db = make_file_database(work / "m102.db")
    ids = build_link_world(db)
    _seed_alpha(db, ids, work)
    previous = permissions.user
    user = session_user(db.authenticate_user("admin", "Synthetic-Admin-1!"))
    permissions.set_user(user)
    db.enforce_authorization(permissions)
    import tabs.w2_Daily_Report as w2
    mp.setattr(w2.QMessageBox, "question", staticmethod(lambda *a, **k: w2.QMessageBox.No))
    from main_window import MainWindow
    win = MainWindow(db_manager=db, user=user, startup_result=None)
    win.show()
    _pump(0.5)
    yield win, db, ids
    end = time.monotonic() + 10
    while win._hierarchy_worker is not None and time.monotonic() < end:
        _pump(0.05)
    SelectionManager().clear()
    win._close_confirmed = True
    win.close()
    _pump(0.2)
    permissions.set_user(previous)
    db.engine.dispose()
    mp.undo()
    del app


# ---- probe -------------------------------------------------------------------------------------
def _model_texts(view, limit=300):
    model = view.model()
    if model is None:
        return []
    out = []
    for r in range(min(model.rowCount(), limit)):
        for c in range(model.columnCount()):
            value = model.index(r, c).data()
            if value is not None:
                out.append(str(value))
    return out


def _plot_texts(widget):
    out = []
    try:
        import pyqtgraph as pg
    except ImportError:          # silent-ok: pyqtgraph is optional; without it nothing is plotted
        return out
    for plot in widget.findChildren(pg.PlotWidget):
        for item in plot.getPlotItem().listDataItems():
            xs, ys = item.getData()
            for series in (xs, ys):
                if series is not None:
                    out += [f"{float(v):.2f}" for v in series]
        out.append(str(plot.getPlotItem().titleLabel.text))
    return out


def _combo_popup(view):
    """A combo box's drop-down list (a picker of wells/records); its shown value is probed as currentText."""
    parent = QObject.parent(view)            # unbound: some tabs shadow ``parent`` with an attribute
    while parent is not None:
        if isinstance(parent, QComboBox):
            return True
        parent = QObject.parent(parent)
    return False


def _texts(root):
    out = []
    for w in root.findChildren(QLineEdit):
        out.append(w.text())
    for w in root.findChildren(QLabel):
        out.append(w.text())
    for w in root.findChildren(QComboBox):
        out.append(w.currentText())
    for w in root.findChildren(QTextEdit):
        out.append(w.toPlainText()[:20000])
    for w in root.findChildren(QPlainTextEdit):
        out.append(w.toPlainText()[:20000])
    for w in root.findChildren(QAbstractSpinBox):
        out.append(w.text())
    for w in root.findChildren(QDateEdit) + root.findChildren(QDateTimeEdit):
        out.append(w.date().toString("yyyy-MM-dd"))
    for w in root.findChildren(QGroupBox):
        out.append(w.title())
    for w in root.findChildren(QTabBar):
        out += [w.tabText(i) for i in range(w.count())]
    for w in root.findChildren(QTableWidget):
        out += [w.item(r, c).text() for r in range(min(w.rowCount(), 300)) for c in range(w.columnCount())
                if w.item(r, c)]
    for w in root.findChildren(QListWidget):
        out += [w.item(i).text() for i in range(min(w.count(), 300))]
    for w in root.findChildren(QTreeWidget):
        stack = [w.invisibleRootItem()]
        while stack:
            item = stack.pop()
            out += [item.text(c) for c in range(w.columnCount())]
            stack += [item.child(i) for i in range(item.childCount())]
    for w in root.findChildren(QAbstractItemView):
        if not isinstance(w, (QTableWidget, QListWidget, QTreeWidget)) and not _combo_popup(w):
            out += _model_texts(w)
    out += _plot_texts(root)
    return [t for t in out if t]


def _found(root):
    texts = _texts(root)
    return {kind: sorted({m for m in marks for t in texts if m in t})
            for kind, marks in MARKS.items() if any(m in t for m in marks for t in texts)}


def _tabs(win):
    return [win.tab_widget.widget(i) for i in range(win.tab_widget.count())]


def _visit(win, tabs, seconds=0.35):
    for tab in tabs:
        win.tab_widget.setCurrentWidget(tab)
        _pump(seconds)


def _select_alpha(win, ids):
    win.navigate_to({"type": "daily_report", "id": ids["report_2"], "report_id": ids["report_2"],
                     "well_id": ids["alpha"], "section_id": None})
    _pump(0.5)


def _scoped(win):
    return [t for t in _tabs(win) if type(t).__name__ not in PORTFOLIO]


def _leaks(win):
    return {type(t).__name__: found for t in _scoped(win) if (found := _found(t))}


def _architecture_rows(win):
    from tabs.w3b_wellbore_schematic_tab import WellboreSchematicTab
    tab = next(t for t in _tabs(win) if isinstance(t, WellboreSchematicTab))
    win.tab_widget.setCurrentWidget(tab)
    _pump(0.3)
    return tab.architecture_panel.table.rowCount()


def test_positive_controls_every_data_kind_is_visible_for_alpha(window):
    win, _db, ids = window
    _select_alpha(win, ids)
    _visit(win, _tabs(win))
    per_tab = {type(t).__name__: _found(t) for t in _tabs(win)}
    seen = {kind for found in per_tab.values() for kind in found}
    expected = set(MARKS) - {"architecture"}       # architecture: names are not listed (see the row-count test)
    assert expected <= seen, f"probe blind to {sorted(expected - seen)}"
    showing = [name for name, found in per_tab.items() if found and name not in PORTFOLIO]
    assert len(showing) >= 10, showing
    assert per_tab["DailyReportWidget"].get("description") == ["SYNALPHA-SUMMARY"]
    assert "report date" in per_tab["DailyReportWidget"]
    assert per_tab["TrajectoryWidget"].get("station")
    assert per_tab["AnalysisWidget"].get("npt") == ["SYNALPHA-NPT"]
    assert per_tab["CostManagementWidget"].get("cost")
    assert per_tab["CalculationHistoryTab"].get("plan") and per_tab["CalculationHistoryTab"].get("case")
    assert _architecture_rows(win) == 1


def test_switch_to_another_well_leaves_no_alpha_value_anywhere(window):
    win, _db, ids = window
    _select_alpha(win, ids)
    _visit(win, _tabs(win))
    assert _leaks(win)                              # control: alpha is on screen before the switch
    win.navigate_to({"type": "well", "id": ids["twin_1"]})
    _pump(0.5)
    _visit(win, _tabs(win))
    assert _leaks(win) == {}
    assert _architecture_rows(win) == 0


def test_clear_after_a_loaded_report_leaves_no_alpha_value(window):
    win, _db, ids = window
    _select_alpha(win, ids)
    _visit(win, _tabs(win))
    assert "DailyReportWidget" in _leaks(win)
    SelectionManager().clear()
    _pump(0.5)
    _visit(win, _tabs(win))
    assert _leaks(win) == {}
    assert win.context_path_label.text() == "No well selected"


def test_switching_back_shows_alpha_again(window):
    win, _db, ids = window
    win.navigate_to({"type": "well", "id": ids["twin_1"]})
    _pump(0.4)
    _select_alpha(win, ids)
    _visit(win, _tabs(win))
    leaks = _leaks(win)
    assert leaks["DailyReportWidget"].get("description") == ["SYNALPHA-SUMMARY"]
    assert "2031-07-20" in leaks["DailyReportWidget"]["report date"]
    assert leaks["TrajectoryWidget"].get("station")


def test_every_tab_receives_the_full_context(window):
    from core.base_tab import DrillTabBase
    win, _db, ids = window
    _select_alpha(win, ids)
    snap = SelectionManager().snapshot()
    assert (snap.well_id, snap.report_id, snap.report_number, snap.report_date) == (
        ids["alpha"], ids["report_2"], 2, "2031-07-20")
    tabs = _tabs(win)
    assert len(tabs) == 21
    for tab in tabs:
        if isinstance(tab, DrillTabBase):
            assert tab.current_context == snap, type(tab).__name__
    assert win.calculation_history_tab.current_context == snap
    assert win.documents_tab.context_well_id == ids["alpha"]
    win.navigate_to({"type": "well", "id": ids["twin_1"]})
    _pump(0.3)
    twin = SelectionManager().snapshot()
    assert twin.report_id is None and twin.report_date is None and twin.well_id == ids["twin_1"]
    assert all(t.current_context == twin for t in tabs if isinstance(t, DrillTabBase))


def test_status_bar_shows_the_resolved_context_path(window):
    win, _db, ids = window
    _select_alpha(win, ids)
    text = win.context_path_label.text()
    assert text.startswith("SYNTHETIC LINK CO › SYNTHETIC PROJECT EAST › SYN-ALPHA-01 (rig SYN RIG 1)"), text
    assert text.endswith("Report #2 2031-07-20"), text
    SelectionManager().select_period(date(2031, 7, 1), date(2031, 7, 31))
    _pump(0.1)
    assert win.context_path_label.text().endswith("|  period 2031-07-01 – 2031-07-31")
    SelectionManager().select_period(None, None)
    _pump(0.1)
    assert "period" not in win.context_path_label.text()


def test_wellbore_reaches_every_tab_and_resets_on_a_well_switch(window):
    from core.base_tab import DrillTabBase
    win, _db, ids = window
    win.navigate_to({"type": "wellbore", "well_id": ids["alpha"], "wellbore_id": ids["bore"]})
    _pump(0.3)
    snap = SelectionManager().snapshot()
    assert (snap.wellbore_id, snap.wellbore_name) == (ids["bore"], "SYN-ALPHA-01 OH")
    assert "› SYN-ALPHA-01 OH" in win.context_path_label.text()
    dtb = [t for t in _tabs(win) if isinstance(t, DrillTabBase)]
    assert all(t.current_wellbore_id == ids["bore"] for t in dtb)
    win.navigate_to({"type": "well", "id": ids["twin_1"]})
    _pump(0.3)
    assert all(t.current_wellbore_id is None for t in dtb)
    assert "OH" not in win.context_path_label.text()


def test_documents_selected_well_filter_follows_the_selection(window):
    win, _db, ids = window
    tab = win.documents_tab
    _select_alpha(win, ids)
    win.tab_widget.setCurrentWidget(tab)
    tab.filter_combo.setCurrentIndex(tab.filter_combo.findData("selected_well"))
    _pump(0.3)
    try:
        assert tab.table.rowCount() == 1
        assert "syn_alpha_daily" in tab.table.item(0, 0).text()
        win.navigate_to({"type": "well", "id": ids["twin_1"]})
        _pump(0.3)
        assert "syn_alpha_daily" not in " ".join(_texts(tab))
        SelectionManager().clear()
        _pump(0.3)
        assert tab.table.rowCount() == 0
        assert tab.library_info.text() == "Select a well to list the documents linked to it."
    finally:
        tab.filter_combo.setCurrentIndex(tab.filter_combo.findData("all"))
        _pump(0.2)
    assert tab.table.rowCount() >= 1          # the default view stays portfolio-wide
