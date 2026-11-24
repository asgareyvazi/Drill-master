"""M375: one 35-step user journey through the real MainWindow, covering the M361-M400 engineering paths.

Select a well → W12 KPI cards carry their M374 structural specification → bit runs and a cost scenario → mud
evaluation → W13 Hydraulics: the M366 budget workflow is refused until the inputs are confirmed, then runs (pressure
budget, flow and nozzle sensitivity, plan vs actual SPP, M370 carrying-capacity index) and is saved → W13 Weight:
torque and drag on a pinned survey revision, friction-factor sensitivity, saved → W6 Trajectory 3D view: plan
overlay on the survey revision, M368 "Plan vs actual…" deviation, saved → Calculation History lists every case and
replays the M366 / M368 / M318 cases from their frozen snapshots (MATCH) → clone, clone-vs-source, archive and
restore with a reason (M365 identity) → W11 end-of-well package, verify → lock / unlock → Security Status → audit
trail → another well without records → clear → close with no worker running.

Every step drives the production widget through the API its buttons call. Seeded through services (not UI): the
synthetic world of ``tools/quality/ux_states_m138.build_world`` and one directional plan tied in to its survey
revision (the planner UI is covered by its own tests). Mocked: only the modal ``exec()`` of the Security Status
dialog and the reason prompt of archive/restore. SYNTHETIC data; offscreen Qt on Linux - NOT Windows desktop or
field acceptance.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "quality"))

import ux_states_m138 as ux  # noqa: E402

from core import analysis_evidence as ev  # noqa: E402
from core import directional_plans as dp  # noqa: E402
from core import hydraulics_workflow as hw  # noqa: E402
from core import survey_plan_deviation as spd  # noqa: E402
from core import survey_revisions as sr  # noqa: E402
from core import torque_drag_sensitivity as tds  # noqa: E402
from core.selection_manager import SelectionManager  # noqa: E402

ADMIN_PASSWORD = "Synthetic-Admin-1!"
STEPS = []
STEP_TIMES = []


def _pump(seconds=0.2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def step(title):
    STEPS.append(title)
    STEP_TIMES.append(time.monotonic())


def _open(win, page):
    win.tab_widget.setCurrentWidget(page)
    _pump(0.2)
    assert win.tab_widget.currentWidget() is page


@pytest.fixture(scope="module")
def window(tmp_path_factory):
    from core.permissions import permissions, session_user
    from synthetic_operations import make_file_database

    app = QApplication.instance() or QApplication([])
    work = tmp_path_factory.mktemp("m375_window")
    mp = pytest.MonkeyPatch()
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(work),
                       "DRILLMASTER_LOG_DIR": str(work / "logs"), "DRILLMASTER_BACKUP_DIR": str(work / "backups"),
                       "DRILLMASTER_AI_IMPORT": "0", "DRILLMASTER_SESSION_IDLE_MINUTES": ""}.items():
        mp.setenv(key, value)
    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(work / "settings"))
    db = make_file_database(work / "m375.db")
    world = ux.build_world(db)
    survey = sr.get_revision(db, world["survey"])
    world["plan"] = dp.save_plan(db, well_id=world["well"], wellbore_id=world["bore"], name="SYN M375 plan",
                                 inputs=dp.plan_inputs([{"type": "hold", "length": 300.0}],
                                                       tie_in=sr.tie_in_from_revision(survey, md=1000),
                                                       azimuth_reference="true", depth_datum="RKB",
                                                       targets=[{"name": "SYN T1", "north": 0.0, "east": 400.0,
                                                                 "tvd": 1200.0, "radius": 30.0}]))["id"]
    previous = permissions.user
    user = session_user(db.authenticate_user("admin", ADMIN_PASSWORD))
    permissions.set_user(user)
    db.enforce_authorization(permissions)
    import tabs.w2_Daily_Report as w2
    mp.setattr(w2.QMessageBox, "question", staticmethod(lambda *a, **k: w2.QMessageBox.No))
    from main_window import MainWindow
    win = MainWindow(db_manager=db, user=user, startup_result=None)
    win.show()
    _pump(0.5)
    yield win, db, world, work
    if win.isVisible():                                   # the journey closes it; this is only a safety net
        SelectionManager().clear()
        win._close_confirmed = True
        win.close()
        _pump(0.2)
    permissions.set_user(previous)
    db.engine.dispose()
    mp.undo()
    del app


def _rows(table):
    return [tuple(table.item(i, j).text() if table.item(i, j) else "" for j in range(table.columnCount()))
            for i in range(table.rowCount())]


def _audit_since(db, first_id):
    con = sqlite3.connect(db.db_path)
    try:
        return [row[0] for row in con.execute("SELECT action FROM audit_logs WHERE id > ? ORDER BY id", (first_id,))]
    finally:
        con.close()


def _select_case(history, case_id):
    rows = [i for i, e in enumerate(history.entries) if e.table == "calculation_cases" and e.record_id == case_id]
    assert rows, (case_id, [(e.table, e.record_id) for e in history.entries])
    history.select_rows(rows[:1])
    return history.entries[rows[0]]


def test_thirty_five_step_journey_through_the_real_window(window, monkeypatch):
    from tests.test_m127_weight_casing import _choose, _fill_weight
    from tests.test_m366_hydraulics_workflow import _fill as _fill_hydraulics

    win, db, world, work = window
    well = world["well"]
    w12, w11, w13 = win.analysis_widget, win.export_widget, win.engineering_calc_tab
    viewer = win.trajectory_widget.viewer_tab
    con = sqlite3.connect(db.db_path)
    first_audit = con.execute("SELECT COALESCE(MAX(id), 0) FROM audit_logs").fetchone()[0]
    con.close()

    step("1 the real main window is up with every tab")
    assert win.isVisible() and win.tab_widget.count() >= 20

    step("2 select the well in the hierarchy (navigate_to)")
    win.navigate_to({"type": "well", "id": well})
    _pump(0.3)
    assert SelectionManager().current_well_id == well

    step("3 W12 KPI cards state their structural definition (M374) in the tooltip")
    _open(win, w12)
    assert w12.kpi_cards
    for card in w12.kpi_cards:
        tip = card.toolTip()
        assert tip == ev.kpi_tooltip(card.metric_key) and len(tip.splitlines()) >= 3, tip

    step("4 the bit runs list the run read from the DDRs")
    bits = w12.bit_runs_panel
    assert bits.wait() and bits.well_id == well and bits.runs_table.rowCount() == 1

    step("5 compare and save a cost scenario (explicit currency)")
    bits.currency_edit.setText("usd")
    bits.bit_cost_edit.setText("15000")
    bits.rig_rate_edit.setText("48000")
    bits.trip_edit.setText("8")
    bits.compare()
    bits.runs_table.selectRow(0)
    bit_case = bits.save_selected()
    assert bit_case and bit_case["well_id"] == well

    step("6 mud evaluation from LAB-tagged readings, saved as a case")
    mud = w12.mud_panel
    assert mud.wait() and mud.samples_table.rowCount() == 1
    mud.select(0)
    mud.set_reading("t600", "50", "LAB", "SYN sheet 1")
    mud.set_reading("t300", "30", "LAB", "SYN sheet 1")
    assert mud.evaluate_selected() is not None
    mud_case = mud.save_selected()
    assert mud_case and mud_case["well_id"] == well

    step("7 W13 Hydraulics: the budget workflow is refused while the inputs are not confirmed")
    _open(win, w13)
    assert w13.current_well_id == well
    _fill_hydraulics(w13, confirm=False)
    assert w13.hy_workflow_dialog() is None and "confirm the displayed hydraulics inputs" in w13.hy_warn.text()

    step("8 confirm the inputs: the M366 dialog opens on a frozen copy of the page")
    w13.hy_confirm_defaults.setChecked(True)
    dialog = w13.hy_workflow_dialog()
    assert dialog is not None and dialog.well_id == well and dialog.values["confirmed"] is True

    step("9 run the budget with flow and nozzle sensitivity, observed SPP and a declared tolerance")
    dialog.flow_edit.setText("350, 450")
    dialog.nozzle_edit.setText("3x13")
    dialog.observed_edit.setText("2900")
    dialog.tolerance_edit.setText("200")
    hy_result = dialog.run()
    assert hy_result["status"] == "COMPUTED" and dialog.flow_table.rowCount() == 2
    assert dialog.budget_table.rowCount() == len(hw.GROUPS) + 1 and "Plan vs actual:" in dialog.summary.text()

    step("10 the summary states the M370 hole-cleaning screening and the case is saved")
    assert "CCI" in dialog.summary.text() or "carrying capacity" in dialog.summary.text().lower()
    hy_case = dialog.save()
    assert hy_case and hy_case["well_id"] == well and hy_case["method"] == hw.METHOD_ID
    dialog.close()
    dialog.deleteLater()

    step("11 W13 Weight: torque and drag on the pinned survey revision of this well")
    _fill_weight(w13)
    w13._wt_reload_survey_revisions()
    _choose(w13, world["survey"])
    w13._wt_calculate()
    assert w13._wt_last_td_run is not None

    step("12 friction-factor sensitivity with declared factors, saved as a case")
    w13.wt_ff_list.setText("0.1 0.2 0.3")
    w13.wt_ff_run_btn.click()
    assert tds.LABEL in w13.wt_ff_result.text() and w13.wt_ff_save_btn.isEnabled()
    td_case = w13.save_ff_sensitivity()
    assert td_case and td_case["well_id"] == well

    step("13 W6 Trajectory 3D view: the layer panel starts on the working survey")
    _open(win, win.trajectory_widget)
    win.trajectory_widget.show_viewer()
    layers = viewer.layers_panel
    assert layers.wait() and not layers.deviation_btn.isEnabled()

    step("14 overlay the plan on the survey revision: both drawn in one frame")
    layers.select(base=world["survey"], plan=world["plan"])
    assert layers.wait() and layers.layer_set is not None
    statuses = {r[0]: r[2] for r in _rows(layers.status_table)}
    assert "DRAWN" in statuses.values() and layers.deviation_btn.isEnabled()

    step("15 Plan vs actual (M368): the deviation is computed per surveyed station")
    layers.deviation_btn.click()
    deviation = layers.deviation_dialog
    deviation.tolerance_edit.setText("1")
    dev_result = deviation.run()
    assert dev_result["status"] == spd.COMPUTED and deviation.station_table.rowCount() == 2
    assert dev_result["max_distance_m"] is not None and deviation.target_table.rowCount() == 1

    step("16 save the deviation as a case")
    dev_case = deviation.save()
    assert dev_case and dev_case["well_id"] == well and dev_case["method"] == spd.METHOD_ID
    deviation.close()
    deviation.deleteLater()

    step("17 Calculation History lists every case saved on this journey")
    history = win.calculation_history_tab
    _open(win, history)
    history.set_well(well)
    ids = {e.record_id for e in history.entries if e.table == "calculation_cases"}
    assert {bit_case["id"], mud_case["id"], hy_case["id"], td_case["id"], dev_case["id"]} <= ids

    step("18 replay the M366 hydraulics case from its frozen snapshot: MATCH")
    _select_case(history, hy_case["id"])
    assert history.recalculate()["status"] == "MATCH"

    step("19 replay the M368 deviation case: MATCH")
    _select_case(history, dev_case["id"])
    assert history.recalculate()["status"] == "MATCH"

    step("20 replay the M318 friction-sensitivity case: MATCH")
    _select_case(history, td_case["id"])
    assert history.recalculate()["status"] == "MATCH"

    step("21 clone the hydraulics case (inputs and results copied, not recalculated)")
    _select_case(history, hy_case["id"])
    clone = history.clone_selected("SYN M375 clone")
    assert clone and clone["id"] != hy_case["id"] and "the original is unchanged" in history.status.text()

    step("22 clone vs source: the copy is verified against its source (M365 identity)")
    _select_case(history, clone["id"])
    comparison = history.clone_comparison()
    assert comparison["provenance"]["is_clone"] and "copy, not a rerun" in history.status.text()
    history.clone_dialog.close()

    step("23 archive the clone with a reason: nothing is deleted")
    monkeypatch.setattr(history, "ask_reason", lambda title: "SYN M375 journey")
    _select_case(history, clone["id"])
    assert history.archive_selected() and "Nothing was deleted or changed" in history.status.text()
    assert clone["id"] not in {e.record_id for e in history.entries if e.table == "calculation_cases"}

    step("24 show archived records and restore the clone")
    history.show_archived.setChecked(True)
    history.refresh()
    _select_case(history, clone["id"])
    assert history.restore_selected() and "Restored" in history.status.text()
    history.show_archived.setChecked(False)

    step("25 W11 end-of-well package for the selected well (no PDF)")
    _open(win, w11)
    package = w11.package_panel
    assert package.wait() and package.well_id == well
    out = work / "packages"
    out.mkdir()
    assert package.build_into(str(out), include_pdf=False) is not None
    assert package.wait() and package.final_dir and "manifest SHA-256" in package.status.text()

    step("26 verify the package: every file matches")
    package.verify(package.final_dir)
    assert package.wait() and package.status.text().startswith("VERIFIED")

    step("27 File › Lock Session; a wrong password keeps it locked")
    win.lock_session()
    _pump(0.1)
    controller = win.session_lock
    assert controller.locked and controller.overlay.isVisible()
    controller.dialog.password.setText("wrong")
    controller.dialog.unlock_btn.click()
    assert controller.locked and "1 failed attempt" in controller.dialog.message.text()

    step("28 the signed-in user's password unlocks")
    controller.dialog.password.setText(ADMIN_PASSWORD)
    controller.dialog.unlock_btn.click()
    _pump(0.1)
    assert not controller.locked and not controller.overlay.isVisible()

    step("29 Tools › Security Status states what is and is not provided")
    from dialogs import security_status_dialog as ssd
    shown = []
    monkeypatch.setattr(ssd.SecurityStatusDialog, "exec", lambda self: shown.append(self) or 0)
    win.show_security_status()
    rows = {area: status for area, status, _detail in shown[0].rows}
    assert rows["Encryption at rest"] == "NOT PROVIDED"
    shown[0].deleteLater()

    step("30 the audit trail holds the lock, the failed unlock, the unlock and the package; it refuses edits")
    actions = _audit_since(db, first_audit)
    for action in ("session_locked", "login_failed", "session_unlocked", "end_of_well_package"):
        assert action in actions, (action, actions)
    con = sqlite3.connect(db.db_path)
    try:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("UPDATE audit_logs SET action='edited' WHERE id = (SELECT MAX(id) FROM audit_logs)")
    finally:
        con.close()

    step("31 another well without records: the panels say so explicitly")
    win.navigate_to({"type": "well", "id": world["empty"]})
    _pump(0.3)
    for page in (w12, win.trajectory_widget, w11):
        _open(win, page)
    for panel in (bits, mud, layers, package):
        assert panel.wait()
    assert "No DDR row records a bit number." in bits.scope_label.text()
    assert _rows(layers.status_table)[0][2] == "NO DATA"

    step("32 nothing of the first well remains: no plan comparison, no package, no survey pin once W13 is opened")
    assert not layers.deviation_btn.isEnabled() and layers.plan_deviation_dialog() is None
    assert package.well_id == world["empty"] and package.final_dir is None
    _open(win, w13)                                     # a hidden tab loads the new well when shown (M102 / M153)
    assert w13.current_well_id == world["empty"] and w13.wt_survey_pin is None
    assert w13.wt_survey_combo.findData(world["survey"]) < 0

    step("33 History of the empty well lists none of the first well's cases")
    _open(win, history)
    history.set_well(world["empty"])
    assert not ({hy_case["id"], dev_case["id"]} & {e.record_id for e in history.entries
                                                    if e.table == "calculation_cases"})

    step("34 clear the selection: NOT ASSESSED everywhere")
    SelectionManager().clear()
    _pump(0.3)
    for label in (bits.scope_label, mud.scope_label, package.scope_label):
        assert "NOT ASSESSED: select a well" in label.text(), label.text()

    step("35 close the window: no worker is left running")
    end = time.monotonic() + 10
    while win._hierarchy_worker is not None and time.monotonic() < end:
        _pump(0.05)
    win._close_confirmed = True
    win.close()
    _pump(0.3)
    assert not win.isVisible() and win._hierarchy_worker is None
    for panel in (bits, mud, layers):
        assert panel.jobs.state != "LOADING"

    assert len(STEPS) == 35 and [s.split(" ", 1)[0] for s in STEPS] == [str(i) for i in range(1, 36)]
