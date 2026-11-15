"""M217: day-by-day DDR authoring - carry-forward only with confirmation; NEW / CARRIED / CONFIRMED / IMPORTED /
DERIVED / MISSING per report section. Real database (core service) and the real Daily Report tab in the main window.

Before M217 the toolbar "Copy Previous" deleted the target day's rows in 23 tables and copied yesterday's
measurements (mud, drilling parameters, surveys, NPT, trip sheet, bulk movements) without asking or marking them.
"""
from __future__ import annotations

import json
import os
from datetime import date, time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import ddr_carry_forward as carry  # noqa: E402
from core.database import (AuditLog, BHAReport, DailyReport, FuelWaterInventory, LogisticsPersonnel,  # noqa: E402
                           MudReport, NPTReport, Section, SurveyPoint, TimeLog24H, TimeLogMorning, Well)
from test_cost_truth_boundary import memory_manager  # noqa: E402


def _seed(session, well, section_id, day_one, day_two):
    """Day 1 holds measurements and day-to-day state; day 2 already has its own personnel list."""
    session.add_all([
        MudReport(well_id=well, report_id=day_one, report_date=date(2026, 3, 1), mw=1.25),
        SurveyPoint(well_id=well, report_id=day_one, md=1000.0, inc=10.0, azi=90.0),
        NPTReport(well_id=well, report_id=day_one, npt_date=date(2026, 3, 1), start_time=time(1, 0),
                  end_time=time(3, 0), duration_hours=2.0, npt_category="SYN", npt_code="SYN",
                  npt_description="synthetic"),
        BHAReport(well_id=well, report_id=day_one, bha_name="BHA 7"),
        TimeLogMorning(report_id=day_one, time_from=time(0, 0), time_to=time(6, 0), duration=6.0,
                       activity_description="Drilling ahead"),
        FuelWaterInventory(well_id=well, report_id=day_one, section_id=section_id, report_date=date(2026, 3, 1),
                           fuel_stock=100.0, fuel_consumed=20.0, fuel_remaining=80.0, water_stock=None,
                           water_remaining=None),
        LogisticsPersonnel(well_id=well, report_id=day_one, name="Synthetic A"),
        LogisticsPersonnel(well_id=well, report_id=day_two, name="Synthetic B"),
    ])


@pytest.fixture
def world():
    db, well = memory_manager()
    with db.session_scope() as session:
        owner = session.get(Well, well)
        other = Well(name="M217-Other", code="M217-O", project_id=owner.project_id)
        session.add(other)
        session.flush()
        section = Section(well_id=well, name="M217 section")
        foreign_section = Section(well_id=other.id, name="M217 foreign")
        session.add_all([section, foreign_section])
        session.flush()
        one = DailyReport(well_id=well, section_id=section.id, report_date=date(2026, 3, 1), depth_2400=1250.0,
                          rig_day=4, summary="Day one summary", depth_0600=1300.0)
        two = DailyReport(well_id=well, section_id=section.id, report_date=date(2026, 3, 2))
        foreign = DailyReport(well_id=other.id, section_id=foreign_section.id, report_date=date(2026, 3, 2))
        session.add_all([one, two, foreign])
        session.flush()
        _seed(session, well, section.id, one.id, two.id)
        ids = {"well": well, "one": one.id, "two": two.id, "foreign": foreign.id}
    yield db, ids
    db.close()


def _counts(db, report_id):
    with db.session_scope() as session:
        return {key: carry._rows(session, s.model, report_id) for key, s in carry.ALL_SECTIONS.items()}


def _carry_records(db):
    with db.session_scope() as session:
        return session.query(AuditLog).filter_by(action=carry.CARRY_ACTION).count()


def test_the_plan_lists_carryable_state_and_never_carried_measurements_with_reasons(world):
    db, ids = world
    with db.session_scope() as session:
        plan = carry.plan(session, ids["one"], ids["two"])
    carryable = {c["key"]: c for c in plan["carryable"]}
    never = {n["key"]: n for n in plan["never_carried"]}
    assert carryable["bha"]["rows"] == 1 and not carryable["bha"]["blocked"]
    assert carryable["morning_log"]["rows"] == 1
    assert "never replaced" in carryable["personnel"]["blocked"]
    assert carryable["downhole_equipment"]["blocked"] == "nothing to carry"
    assert never["mud"]["rows"] == 1 and "measurement" in never["mud"]["reason"]
    assert never["surveys"]["rows"] == 1 and "duplicates" in never["surveys"]["reason"]
    assert never["npt"]["rows"] == 1 and "twice" in never["npt"]["reason"]
    assert set(carry.CARRYABLE).isdisjoint(carry.NEVER_CARRIED)
    assert plan["derived_header"] == {"depth_0000": 1250.0, "rig_day": 4}


@pytest.mark.parametrize("sections, kwargs, message", [
    (["bha"], {"confirmed": False}, "confirmation"),
    (["mud"], {"confirmed": True}, "never carried"),
    (["surveys"], {"confirmed": True}, "never carried"),
    (["npt", "bha"], {"confirmed": True}, "never carried"),
    (["personnel"], {"confirmed": True}, "never replaced"),
    (["bha", "personnel"], {"confirmed": True}, "never replaced"),
    (["nonsense"], {"confirmed": True}, "Unknown section"),
    ([], {"confirmed": True}, "No section"),
    ([], {"confirmed": True, "derive_header": ["summary"]}, "cannot be derived"),
])
def test_refusals_change_nothing(world, sections, kwargs, message):
    db, ids = world
    before, records = _counts(db, ids["two"]), _carry_records(db)
    with pytest.raises(carry.CarryForwardRefused, match=message):
        with db.session_scope() as session:
            carry.apply(session, ids["one"], ids["two"], sections, **kwargs)
    assert _counts(db, ids["two"]) == before and _carry_records(db) == records


@pytest.mark.parametrize("source, target, message", [
    ("two", "one", "earlier report"), ("one", "foreign", "same well"), ("one", "one", "two different")])
def test_wrong_direction_foreign_well_and_same_report_are_refused(world, source, target, message):
    db, ids = world
    with pytest.raises(carry.CarryForwardRefused, match=message):
        with db.session_scope() as session:
            carry.apply(session, ids[source], ids[target], ["bha"], confirmed=True)
    assert _carry_records(db) == 0


def test_a_confirmed_carry_copies_only_the_chosen_state_with_lineage_and_states(world):
    db, ids = world
    with db.session_scope() as session:
        record = carry.apply(session, ids["one"], ids["two"], ["bha", "morning_log", "fuel_water_opening"],
                             confirmed=True, derive_header=["depth_0000", "rig_day"],
                             actor={"username": "synthetic-operator"})
    assert record["sections"] == {"bha": 1, "morning_log": 1, "fuel_water_opening": 1}
    assert record["derived_header"] == {"depth_0000": 1250.0, "rig_day": 5}
    counts = _counts(db, ids["two"])
    assert counts["mud"] == counts["surveys"] == counts["npt"] == 0      # measurements never travel
    assert counts["personnel"] == 1                                       # today's own list kept
    with db.session_scope() as session:
        report = session.get(DailyReport, ids["two"])
        assert report.depth_0000 == 1250.0 and report.rig_day == 5
        assert report.depth_0600 is None and not report.summary           # never copied
        names = [p.name for p in session.query(LogisticsPersonnel).filter_by(report_id=ids["two"])]
        assert names == ["Synthetic B"]
        log = session.query(TimeLog24H).filter_by(report_id=ids["two"]).one()
        assert log.activity_description == "Drilling ahead"
        fuel = session.query(FuelWaterInventory).filter_by(report_id=ids["two"]).one()
        assert fuel.fuel_stock == fuel.fuel_remaining == 80.0 and fuel.water_stock is None
        assert fuel.fuel_consumed is None and fuel.fuel_received is None   # unknown today, never 0
        audit = session.query(AuditLog).filter_by(action=carry.CARRY_ACTION).one()
        lineage = json.loads(audit.details)
        assert audit.entity_id == ids["two"] and audit.username == "synthetic-operator"
        assert lineage["contract"] == carry.CARRY_FORWARD_CONTRACT and lineage["source_report_id"] == ids["one"]
        states = carry.section_states(session, ids["two"])
    assert states["bha"]["state"] == carry.CARRIED and states["bha"]["source_report_id"] == ids["one"]
    assert states["morning_log"]["state"] == carry.CARRIED
    assert states["personnel"]["state"] == carry.NEW
    assert states["mud"]["state"] == carry.MISSING
    assert states["header.depth_0000"]["state"] == carry.DERIVED
    assert states["header.rig_day"]["state"] == carry.DERIVED
    with db.session_scope() as session:
        assert carry.confirm(session, ids["two"], ["bha", "personnel"], note="checked on the rig") == ["bha"]
    with db.session_scope() as session:
        states = carry.section_states(session, ids["two"])
        assert states["bha"]["state"] == carry.CONFIRMED and states["morning_log"]["state"] == carry.CARRIED
        with pytest.raises(carry.CarryForwardRefused, match="waiting for confirmation"):
            carry.confirm(session, ids["two"], ["bha"])
    # a second carry of the same section is refused: today's (carried) rows are never replaced
    with pytest.raises(carry.CarryForwardRefused, match="never replaced"):
        with db.session_scope() as session:
            carry.apply(session, ids["one"], ids["two"], ["bha"], confirmed=True)


def test_an_edited_derived_header_is_no_longer_derived_and_an_imported_report_is_imported(world):
    db, ids = world
    with db.session_scope() as session:
        carry.apply(session, ids["one"], ids["two"], [], confirmed=True, derive_header=["depth_0000"])
    with db.session_scope() as session:
        session.get(DailyReport, ids["two"]).depth_0000 = 1251.0           # the operator corrected it
    with db.session_scope() as session:
        assert carry.section_states(session, ids["two"])["header.depth_0000"]["state"] == carry.NEW
        session.add(AuditLog(action="ddr_import", entity_type="daily_report", entity_id=ids["one"],
                             details=json.dumps({"fingerprint": "synthetic"})))
    with db.session_scope() as session:
        states = carry.section_states(session, ids["one"])
    assert states["mud"]["state"] == carry.IMPORTED and states["downhole_equipment"]["state"] == carry.MISSING
    assert states["header.rig_day"]["state"] == carry.IMPORTED


def test_a_derived_header_never_overwrites_a_value_already_entered(world):
    db, ids = world
    with db.session_scope() as session:
        session.get(DailyReport, ids["two"]).rig_day = 9
    with db.session_scope() as session:
        record = carry.apply(session, ids["one"], ids["two"], [], confirmed=True, derive_header=["rig_day"])
    assert record["derived_header"] == {}
    with db.session_scope() as session:
        assert session.get(DailyReport, ids["two"]).rig_day == 9


# ------------------------------------------------------------------ the real dialogs and the Daily Report tab
def test_the_dialog_preselects_nothing_disables_blocked_sections_and_needs_confirmation(world):
    from PySide6.QtWidgets import QApplication, QDialogButtonBox
    from dialogs.carry_forward_dialog import CarryForwardDialog, DayStatesDialog
    QApplication.instance() or QApplication([])
    db, ids = world
    with db.session_scope() as session:
        plan = carry.plan(session, ids["one"], ids["two"])
    dialog = CarryForwardDialog(plan)
    ok = dialog.buttons.button(QDialogButtonBox.Ok)
    assert dialog.selected_sections() == [] and dialog.selected_header() == [] and not ok.isEnabled()
    assert not dialog.section_boxes["personnel"].isEnabled()             # today already has rows
    assert not dialog.section_boxes["downhole_equipment"].isEnabled()    # nothing to carry
    dialog.section_boxes["bha"].setChecked(True)
    assert not ok.isEnabled()                                            # chosen but not confirmed
    dialog.confirm_box.setChecked(True)
    assert ok.isEnabled() and dialog.selected_sections() == ["bha"]
    dialog.section_boxes["personnel"].setChecked(True)                   # a disabled box is never returned
    assert dialog.selected_sections() == ["bha"]
    with db.session_scope() as session:
        states = carry.section_states(session, ids["two"])
    view = DayStatesDialog(states)
    assert view.table.rowCount() == len(states) and not view.confirm_button.isEnabled()
    dialog.deleteLater()
    view.deleteLater()


def test_the_never_carried_list_is_shown_with_reasons(world):
    from PySide6.QtWidgets import QApplication, QLabel
    from dialogs.carry_forward_dialog import CarryForwardDialog
    QApplication.instance() or QApplication([])
    db, ids = world
    with db.session_scope() as session:
        plan = carry.plan(session, ids["one"], ids["two"])
    dialog = CarryForwardDialog(plan)
    text = dialog.findChild(QLabel, "never_carried_label").text()
    assert "Mud properties" in text and "Survey stations" in text and "counted twice" in text
    assert "Downhole equipment" not in text
    dialog.deleteLater()


def test_the_toolbar_copy_previous_in_the_real_main_window_asks_carries_and_confirms(window, monkeypatch):  # noqa: F811
    from core.selection_manager import SelectionManager
    from dialogs import carry_forward_dialog
    from test_m153_context_blocked_autosave import _no_modal_dialogs, _tab
    from test_m70_selection_audit import _pump
    _no_modal_dialogs(monkeypatch)
    win, db, ids = window
    with db.session_scope() as session:
        section = Section(well_id=ids["alpha"], name="M217 UI section")
        session.add(section)
        session.flush()
        one = DailyReport(well_id=ids["alpha"], section_id=section.id, report_date=date(2026, 5, 1),
                          report_number=501, depth_2400=900.0)
        two = DailyReport(well_id=ids["alpha"], section_id=section.id, report_date=date(2026, 5, 2),
                          report_number=502)
        session.add_all([one, two])
        session.flush()
        session.add_all([BHAReport(well_id=ids["alpha"], report_id=one.id, bha_name="UI BHA"),
                         MudReport(well_id=ids["alpha"], report_id=one.id, report_date=date(2026, 5, 1), mw=1.1)])
        section_id, one_id, two_id = section.id, one.id, two.id
    daily = _tab(win, "DailyReportWidget")
    win.tab_widget.setCurrentWidget(daily)
    manager = SelectionManager()
    manager.select_well(ids["alpha"], {"name": "alpha"}, force=True)
    manager.select_section(section_id, {"name": "M217 UI section"}, force=True)
    manager.select_report(two_id, {}, force=True)
    win._targeted_refresh(ids["alpha"], section_id, two_id)   # what a hierarchy-tree click on the report does
    _pump(0.3)
    if daily.current_report_id != two_id:
        daily.load_report_by_id(two_id)
        _pump(0.2)
    assert daily.current_report_id == two_id and win.current_report_id == two_id
    asked = []
    monkeypatch.setattr(daily, "_ask_carry_forward", lambda plan: asked.append(plan) or None)
    win.copy_previous_from_toolbar()                         # the toolbar action
    assert asked and asked[0]["source_report_id"] == one_id
    assert _counts(db, two_id)["bha"] == 0 and _carry_records(db) == 0   # cancelled: nothing carried
    monkeypatch.setattr(daily, "_ask_carry_forward", lambda plan: (["bha"], ["depth_0000"]))
    assert daily.copy_previous_day() is True
    counts = _counts(db, two_id)
    assert counts["bha"] == 1 and counts["mud"] == 0
    assert daily.depth_0000.value() == 900.0                 # the derived header reached the open form
    shown = []

    def confirm_in_dialog(self):
        shown.append({self.table.item(r, 0).text(): self.table.item(r, 1).text()
                      for r in range(self.table.rowCount())})
        self._confirm()
        return 1

    monkeypatch.setattr(carry_forward_dialog.DayStatesDialog, "exec", confirm_in_dialog)
    assert daily.findChild(type(daily.day_states_btn), "day_states_btn") is daily.day_states_btn
    daily.day_states_btn.click()
    assert shown[0]["BHA in the hole"] == "CARRIED" and shown[0]["Mud properties"] == "MISSING"
    with db.session_scope() as session:
        states = carry.section_states(session, two_id)
    assert states["bha"]["state"] == carry.CONFIRMED and states["header.depth_0000"]["state"] == carry.DERIVED


from test_m70_selection_audit import window  # noqa: E402,F401,F811  (module-scoped real main window)


def test_the_new_daily_report_dialog_copies_nothing_by_itself(world, monkeypatch):
    """The "copy from previous day" box used to write yesterday's summary and a 06:00 depth into the new report."""
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QApplication, QMessageBox
    from core.permissions import permissions
    from dialogs.hierarchy_dialogs import NewDailyReportDialog
    QApplication.instance() or QApplication([])
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(permissions, "_user", {"role": "engineer"})
    db, ids = world
    with db.session_scope() as session:
        section_id = session.get(DailyReport, ids["one"]).section_id
        session.query(DailyReport).filter_by(id=ids["two"]).delete()     # day 2 is created by the dialog
    dialog = NewDailyReportDialog(db, None, section_id)
    dialog.date_edit.setDate(QDate(2026, 3, 2))
    dialog.copy_previous_cb.setChecked(True)
    monkeypatch.setattr(dialog, "accept", lambda: None)
    messages = []
    monkeypatch.setattr(dialog, "show_success", messages.append)       # modal QMessageBox.exec in the dialog
    monkeypatch.setattr(dialog, "show_error", lambda m: messages.append(f"ERROR {m}"))
    dialog.create_daily_report()
    assert not any(m.startswith("ERROR") for m in messages), messages
    created, previous = dialog.created_id, dialog.previous_report_id
    assert created and previous == ids["one"]
    with db.session_scope() as session:
        report = session.get(DailyReport, created)
        assert not report.summary and report.depth_0600 is None and report.depth_0000 is None
        assert carry._rows(session, "MudReport", created) == carry._rows(session, "BHAReport", created) == 0
        assert session.query(AuditLog).filter_by(action=carry.CARRY_ACTION).count() == 0
    with db.session_scope() as session:                                  # then the confirmed, chosen carry
        assert dialog._copy_all_report_data(session, previous, created, ["bha"], confirmed=True)
    assert _counts(db, created)["bha"] == 1 and _counts(db, created)["mud"] == 0
    dialog.deleteLater()
