"""M70.7: selection context through the real MainWindow (offscreen, SYNTHETIC file database).

Checks the consumers added in M61-M69 and the trajectory tab: well switches,
hidden-tab staleness, wellbore attribution, report well labels and the state
after the selected well is deleted. Offscreen Qt on Linux, not Windows desktop.
"""
from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core import calculation_cases as cc  # noqa: E402
from core import directional_plans as dp  # noqa: E402
from core.permissions import permissions, session_user  # noqa: E402
from core.selection_manager import SelectionManager  # noqa: E402
from document_link_fixtures import build_link_world  # noqa: E402
from synthetic_operations import make_file_database  # noqa: E402

INPUTS = dp.plan_inputs([{"type": "hold", "length": 300.0}, {"type": "curve", "inc": 20.0, "azi": 90.0, "dls": 3.0}])


def _pump(seconds=0.2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


@pytest.fixture(scope="module")
def window(tmp_path_factory):
    app = QApplication.instance() or QApplication([])
    work = tmp_path_factory.mktemp("m70_window")
    mp = pytest.MonkeyPatch()
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(work),
                       "DRILLMASTER_LOG_DIR": str(work / "logs"), "DRILLMASTER_BACKUP_DIR": str(work / "backups"),
                       "DRILLMASTER_AI_IMPORT": "0"}.items():
        mp.setenv(key, value)
    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(work / "settings"))
    db = make_file_database(work / "window.db")
    ids = build_link_world(db)
    from core.database import Wellbore
    with db.session_scope() as session:
        bore = Wellbore(well_id=ids["alpha"], name="SYN-ALPHA-01 OH", wellbore_type="original")
        session.add(bore)
        session.flush()
        ids["bore"] = bore.id
    for well in (ids["alpha"], ids["twin_1"]):
        dp.save_plan(db, well_id=well, name=f"plan {well}", inputs=INPUTS)
        cc.save_case(db, calculator="Quick Calc", name=f"case {well}", inputs={"a": 1}, results={"r": 1},
                     well_id=well)
    previous = permissions.user
    user = session_user(db.authenticate_user("admin", "Synthetic-Admin-1!"))
    permissions.set_user(user)
    db.enforce_authorization(permissions)
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


def _wells_of(tab):
    return {e.well_id for e in tab.entries}


def test_history_follows_well_switches_and_a_hidden_tab_reloads_when_shown(window):
    win, _db, ids = window
    sel, history = SelectionManager(), win.calculation_history_tab
    win.tab_widget.setCurrentWidget(history)
    sel.select_well(ids["alpha"], {"id": ids["alpha"], "name": "SYN-ALPHA-01"})
    _pump()
    assert history.entries and _wells_of(history) == {ids["alpha"]}
    sel.select_well(ids["twin_1"], {"id": ids["twin_1"], "name": "SYN-TWIN"})
    _pump()
    assert _wells_of(history) == {ids["twin_1"]}
    win.tab_widget.setCurrentWidget(win.trajectory_widget)
    sel.select_well(ids["alpha"], {"id": ids["alpha"], "name": "SYN-ALPHA-01"})
    _pump()
    assert history.entries == [] and history.table.rowCount() == 0        # no stale twin rows while hidden
    win.tab_widget.setCurrentWidget(history)
    _pump()
    assert _wells_of(history) == {ids["alpha"]}


def test_reports_carry_the_records_own_well_label(window):
    win, _db, ids = window
    sel, history = SelectionManager(), win.calculation_history_tab
    win.tab_widget.setCurrentWidget(history)
    sel.select_well(ids["alpha"], {"id": ids["alpha"], "name": "SYN-ALPHA-01"})
    _pump()
    history.select_rows([0])
    assert f"SYN-ALPHA-01 (id {ids['alpha']})" in history.report_html()


def test_new_plans_and_cases_record_the_selected_wellbore_of_their_well_only(window):
    win, db, ids = window
    sel = SelectionManager()
    win.tab_widget.setCurrentWidget(win.trajectory_widget)
    sel.select_well(ids["alpha"], {"id": ids["alpha"], "name": "SYN-ALPHA-01"})
    sel.select_wellbore(ids["bore"], {"id": ids["bore"], "well_id": ids["alpha"]})
    _pump()
    designer = win.trajectory_widget.viewer_tab.plan_designer
    assert designer.well_id == ids["alpha"] and designer._selected_wellbore() == ids["bore"]
    assert sel.wellbore_for(ids["twin_1"]) is None
    designer.add_segment("hold", 200.0, None, None, None)
    plan = designer.save_new_plan("SYN wellbore plan")
    assert plan is not None and plan["wellbore_id"] == ids["bore"] and plan["well_id"] == ids["alpha"]
    sel.select_well(ids["twin_1"], {"id": ids["twin_1"], "name": "SYN-TWIN"})
    _pump()
    assert sel.current_wellbore_id is None and designer._selected_wellbore() is None


def test_deleting_the_selected_well_clears_every_m61_m69_consumer(window):
    win, db, ids = window
    sel, history = SelectionManager(), win.calculation_history_tab
    win.tab_widget.setCurrentWidget(win.trajectory_widget)
    sel.select_well(ids["twin_1"], {"id": ids["twin_1"], "name": "SYN-TWIN"})
    _pump()
    viewer = win.trajectory_widget.viewer_tab
    assert viewer.well_id == ids["twin_1"] and viewer.plan_designer.plan_combo.count() == 1
    assert db.delete_hierarchy_entity("well", ids["twin_1"]) is True
    sel.clear()
    _pump()
    assert viewer.well_id is None and viewer.plan_designer.well_id is None
    assert viewer.plan_designer.plan_combo.count() == 0 and not viewer.plan_designer.save_new_btn.isEnabled()
    assert win.trajectory_widget.current_well_id is None
    win.tab_widget.setCurrentWidget(history)
    _pump()
    assert history.entries == [] and "Select a well" in history.status.text()
    history.well_only.setChecked(False)
    history.refresh()
    assert ids["twin_1"] not in _wells_of(history) and ids["alpha"] in _wells_of(history)
    history.well_only.setChecked(True)
    assert win.engineering_calc_tab.case_bar._well_id() is None
