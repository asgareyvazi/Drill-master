"""M139: one 30-step user journey through the real MainWindow and its production tabs and panels.

Select a well → W12 bit runs (compare, save a cost scenario) → parameter trends (time, then depth axis) → mud
evaluation (tagged readings, save) → NPT reconciliation (decide an UNCERTAIN group) → trajectory tab 3D layers
(working survey, then a survey revision) → W13 Buoyancy (run, save) → History (lists every saved case, re-runs
one) → W11 end-of-well package (build, verify, detect tampering) → File › Lock Session (wrong password, right
password) → Tools › Security Status → audit trail → another well without records (explicit empty states) →
clear (NOT ASSESSED everywhere) → close without a running worker.

Every step drives the production widget through the API its buttons call; nothing is mocked except the modal
``exec()`` of the Security Status dialog (the dialog itself is built by the real menu handler). SYNTHETIC data
(``tools/quality/ux_states_m138.build_world``); offscreen Qt on Linux - NOT Windows desktop or field acceptance.
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

from core import npt_reconciliation as nr  # noqa: E402
from core.selection_manager import SelectionManager  # noqa: E402

ADMIN_PASSWORD = "Synthetic-Admin-1!"
STEPS = []


def _pump(seconds=0.2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


def step(title):
    STEPS.append(title)


def _open(win, page):
    """Click the main tab that holds ``page``: hidden tabs apply the selection when shown (M102, by design)."""
    win.tab_widget.setCurrentWidget(page)
    _pump(0.2)
    assert win.tab_widget.currentWidget() is page


@pytest.fixture(scope="module")
def window(tmp_path_factory):
    from core.permissions import permissions, session_user
    from synthetic_operations import make_file_database

    app = QApplication.instance() or QApplication([])
    work = tmp_path_factory.mktemp("m139_window")
    mp = pytest.MonkeyPatch()
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(work),
                       "DRILLMASTER_LOG_DIR": str(work / "logs"), "DRILLMASTER_BACKUP_DIR": str(work / "backups"),
                       "DRILLMASTER_AI_IMPORT": "0", "DRILLMASTER_SESSION_IDLE_MINUTES": ""}.items():
        mp.setenv(key, value)
    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(work / "settings"))
    db = make_file_database(work / "m139.db")
    world = ux.build_world(db)
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


def test_thirty_step_journey_through_the_real_window(window, monkeypatch):
    win, db, world, work = window
    well = world["well"]
    w12, w11 = win.analysis_widget, win.export_widget
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

    step("3 open Analysis (W12): the bit runs list the run read from the DDRs")
    _open(win, w12)
    bits = w12.bit_runs_panel
    assert bits.wait() and bits.well_id == well and bits.runs_table.rowCount() == 1
    assert "1 run(s), 0 incomplete" in bits.scope_label.text()

    step("4 compare and save a cost scenario (explicit currency)")
    bits.currency_edit.setText("usd")
    bits.bit_cost_edit.setText("15000")
    bits.rig_rate_edit.setText("48000")
    bits.trip_edit.setText("8")
    bits.compare()
    bits.runs_table.selectRow(0)
    bit_case = bits.save_selected()
    assert bit_case and bit_case["well_id"] == well and "USD" in bits.status.text()

    step("5 parameter trends on the time axis, axes labelled with units")
    trends = w12.trend_panel
    assert trends.wait() and "2 DDR row(s)" in trends.scope_label.text()
    left = trends.plot.getPlotItem().getAxis("left").labelText
    assert "(" in left and left.endswith(")")

    step("6 switch the trends to the depth axis")
    trends.axis_combo.setCurrentIndex(trends.axis_combo.findData("depth"))
    assert trends.wait() and trends.result is not None and trends.result.axis == "depth"

    step("7 mud evaluation from LAB-tagged readings")
    mud = w12.mud_panel
    assert mud.wait() and mud.samples_table.rowCount() == 1
    mud.select(0)
    mud.set_reading("t600", "50", "LAB", "SYN sheet 1")
    mud.set_reading("t300", "30", "LAB", "SYN sheet 1")
    assert mud.evaluate_selected() is not None

    step("8 save the mud evaluation as a case")
    mud_case = mud.save_selected()
    assert mud_case and f"calculation case #{mud_case['id']}" in mud.status.text()

    step("9 NPT reconciliation shows a MATCHED and an UNCERTAIN group")
    npt = w12.npt_reconciliation_panel
    assert npt.wait() and npt.table.rowCount() == 2
    statuses = [g.status for g in npt.recon.groups]
    assert sorted(statuses) == sorted([nr.MATCHED, nr.UNCERTAIN])

    step("10 decide the UNCERTAIN group with evidence; the totals change")
    before = npt.totals_label.text()
    npt.table.selectRow(statuses.index(nr.UNCERTAIN))
    decision = npt.decide_selected(nr.SAME_EVENT, "SYN DDR 2 remarks", "same pump repair")
    assert decision and npt.wait() and npt.totals_label.text() != before

    step("11 trajectory tab: the 3D layer panel reports the working survey the viewer composed")
    _open(win, win.trajectory_widget)
    win.trajectory_widget.show_viewer()
    layers = viewer.layers_panel
    assert layers.wait()
    working = _rows(layers.status_table)[0]
    assert working[2] == "DRAWN" and working[3].startswith("4 station(s)")

    step("12 overlay the survey revision")
    layers.select(base=world["survey"])
    assert layers.wait() and layers.layer_set is not None
    assert any(r[0].startswith("Survey revision 1") and r[2] == "DRAWN" for r in _rows(layers.status_table))

    step("13 W13 Buoyancy: run the contract calculator")
    w13 = win.engineering_calc_tab
    win.tab_widget.setCurrentWidget(w13)
    assert w13.calculator_finder.open_path("CSG/CMT › Buoyancy")
    w13.bf_mw.setValue(74.8)
    w13.bf_csg_wt.setValue(40.0)
    w13.bf_csg_len.setValue(5000.0)
    w13.bf_friction.setValue(0.2)
    w13._csg_calc_landing()

    step("14 save the W13 case for the selected well")
    w13_case = w13.case_bar.save_case("SYN M139 buoyancy")
    assert w13_case and w13_case["well_id"] == well

    step("15 History lists the three saved cases of this well")
    history = win.calculation_history_tab
    win.tab_widget.setCurrentWidget(history)
    history.set_well(well)
    ids = {e.record_id for e in history.entries}
    assert {bit_case["id"], mud_case["id"], w13_case["id"]} <= ids

    step("16 re-run the W13 case from History: MATCH")
    history.select_rows([i for i, e in enumerate(history.entries) if e.record_id == w13_case["id"]][:1])
    outcome = history.recalculate()
    assert outcome and outcome["status"] == "MATCH" and "MATCH" in history.status.text()

    step("17 W11 end-of-well package follows the selected well")
    _open(win, w11)
    package = w11.package_panel
    assert package.wait() and package.well_id == well

    step("18 build the package (no PDF)")
    out = work / "packages"
    out.mkdir()
    assert package.build_into(str(out), include_pdf=False) is not None
    assert package.wait() and package.final_dir and "manifest SHA-256" in package.status.text()
    assert package.table.rowCount() > 0

    step("19 verify the package: every file matches, the audit record is found")
    package.verify(package.final_dir)
    assert package.wait() and package.status.text().startswith("VERIFIED")

    step("20 a changed file is detected")
    manifest = Path(package.final_dir) / "manifest.json"
    victim = next(p for p in Path(package.final_dir).iterdir() if p.is_file() and p != manifest)
    victim.write_text(victim.read_text(encoding="utf-8") + "\nSYN tamper", encoding="utf-8")
    package.verify(package.final_dir)
    assert package.wait() and package.status.text().startswith("NOT VERIFIED")

    step("21 File › Lock Session hides the work")
    win.lock_session()
    _pump(0.1)
    controller = win.session_lock
    assert controller.locked and controller.overlay.isVisible() and controller.dialog.isVisible()

    step("22 a wrong password keeps it locked")
    controller.dialog.password.setText("wrong")
    controller.dialog.unlock_btn.click()
    assert controller.locked and "1 failed attempt" in controller.dialog.message.text()

    step("23 the signed-in user's password unlocks")
    controller.dialog.password.setText(ADMIN_PASSWORD)
    controller.dialog.unlock_btn.click()
    _pump(0.1)
    assert not controller.locked and not controller.overlay.isVisible()

    step("24 Tools › Security Status states what is and is not provided")
    from dialogs import security_status_dialog as ssd
    shown = []
    monkeypatch.setattr(ssd.SecurityStatusDialog, "exec", lambda self: shown.append(self) or 0)
    win.show_security_status()
    rows = {area: status for area, status, _detail in shown[0].rows}
    assert rows["Audit log append-only (storage)"] == "PROVIDED" and rows["Encryption at rest"] == "NOT PROVIDED"
    shown[0].deleteLater()

    step("25 the audit trail holds the lock, the failed unlock, the unlock and the package")
    actions = _audit_since(db, first_audit)
    for action in ("session_locked", "login_failed", "session_unlocked", "end_of_well_package"):
        assert action in actions, (action, actions)

    step("26 the audit trail refuses to be rewritten")
    con = sqlite3.connect(db.db_path)
    try:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("UPDATE audit_logs SET action='edited' WHERE id = (SELECT MAX(id) FROM audit_logs)")
    finally:
        con.close()

    step("27 another well without records: every panel says so explicitly")
    win.navigate_to({"type": "well", "id": world["empty"]})
    _pump(0.3)
    for page in (w12, win.trajectory_widget, w11):
        _open(win, page)
    for panel in (bits, trends, mud, npt, layers, package):
        assert panel.wait()
    assert "No DDR row records a bit number." in bits.scope_label.text()
    assert "No drilling-parameter row is recorded in this scope" in trends.scope_label.text()
    assert "No mud report is recorded in this scope." in mud.scope_label.text()
    assert "No NPT register event or NPT time-log row is recorded in this scope." in npt.scope_label.text()
    assert _rows(layers.status_table)[0][2] == "NO DATA"

    step("28 nothing of the first well remains on the package panel")
    assert package.well_id == world["empty"] and package.table.rowCount() == 0 and package.final_dir is None

    step("29 clear the selection: NOT ASSESSED everywhere")
    SelectionManager().clear()
    _pump(0.3)
    for label in (bits.scope_label, trends.scope_label, mud.scope_label, npt.scope_label, package.scope_label):
        assert "NOT ASSESSED: select a well" in label.text(), label.text()

    step("30 close the window: no worker is left running")
    end = time.monotonic() + 10
    while win._hierarchy_worker is not None and time.monotonic() < end:
        _pump(0.05)
    win._close_confirmed = True
    win.close()
    _pump(0.3)
    assert not win.isVisible() and win._hierarchy_worker is None
    for panel in (bits, trends, mud, npt, layers):
        assert panel.jobs.state != "LOADING"

    assert len(STEPS) == 30 and [s.split(" ", 1)[0] for s in STEPS] == [str(i) for i in range(1, 31)]
