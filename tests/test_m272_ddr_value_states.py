"""M272: explicit value states for numeric DDR header fields (SYNTHETIC fixture, tests/synthetic_operations.py).

States: REPORTED, ZERO, CALCULATED (method required), UNKNOWN, NOT_APPLICABLE and NOT_REPORTED. A missing state
never puts a number into the field, a contradicting state is refused, and a later edit that contradicts a recorded
state is reported as INCONSISTENT rather than repaired.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import text  # noqa: E402

from core import ddr_value_states as vs  # noqa: E402
from core.database import AuditLog, DailyReport, DdrValueState  # noqa: E402
from synthetic_operations import build_synthetic_operations, make_file_database  # noqa: E402


@pytest.fixture()
def world(tmp_path):
    db = make_file_database(tmp_path / "m272.db")
    ids = build_synthetic_operations(db)
    yield db, ids["reports"][1], ids["reports"][2]          # day 1: 0 -> 300 m; day 2: 300 -> 600 m
    db.engine.dispose()


@pytest.mark.parametrize("typed, expected", [
    (None, (None, vs.NOT_REPORTED)), ("", (None, vs.NOT_REPORTED)), ("  NR ", (None, vs.NOT_REPORTED)),
    ("not reported", (None, vs.NOT_REPORTED)), ("?", (None, vs.UNKNOWN)), ("Unknown", (None, vs.UNKNOWN)),
    ("N/A", (None, vs.NOT_APPLICABLE)), ("na", (None, vs.NOT_APPLICABLE)), ("0", (0.0, vs.ZERO)),
    ("0.0", (0.0, vs.ZERO)), (0, (0.0, vs.ZERO)), ("12.5", (12.5, vs.REPORTED)), ("1234", (1234.0, vs.REPORTED)),
    (-3.0, (-3.0, vs.REPORTED)),
])
def test_what_an_operator_types_maps_to_one_state(typed, expected):
    assert vs.parse_authored(typed) == expected


@pytest.mark.parametrize("typed", ["nan", "inf", "-inf", "abc", "12 m", float("nan"), "1,5", "1,500"])
def test_anything_else_is_refused_not_guessed(typed):
    with pytest.raises(vs.ValueStateError):
        vs.parse_authored(typed)


def test_implicit_states_follow_the_stored_values(world):
    db, day1, _day2 = world
    states = vs.states(db, day1)
    assert set(states) == set(vs.FIELDS)
    assert (states["depth_0000"]["value"], states["depth_0000"]["state"]) == (0.0, vs.ZERO)
    assert (states["depth_2400"]["value"], states["depth_2400"]["state"]) == (300.0, vs.REPORTED)
    assert (states["wob"]["value"], states["wob"]["state"]) == (None, vs.NOT_REPORTED)
    assert not any(entry["recorded"] for entry in states.values())


@pytest.mark.parametrize("field, state, method, reason", [
    ("depth_2400", vs.UNKNOWN, "", "needs an empty value"),
    ("depth_2400", vs.NOT_APPLICABLE, "", "needs an empty value"),
    ("depth_2400", vs.ZERO, "", "needs a stored 0"),
    ("wob", vs.REPORTED, "", "needs a stored non-zero number"),
    ("depth_0000", vs.REPORTED, "", "use ZERO for 0"),
    ("wob", vs.CALCULATED, "a method", "needs the calculated number"),
    ("depth_2400", vs.CALCULATED, "   ", "needs the calculation method"),
    ("depth_2400", "GUESSED", "", "unknown value state"),
])
def test_a_contradicting_state_is_refused_and_nothing_is_written(world, field, state, method, reason):
    db, day1, _day2 = world
    with pytest.raises(vs.ValueStateError, match=reason):
        vs.record(db, day1, field, state, method=method)
    with db.session_scope() as session:
        assert session.query(DdrValueState).count() == 0


def test_unknown_field_and_missing_report_are_refused(world):
    db, day1, _day2 = world
    with pytest.raises(vs.ValueStateError, match="not a numeric DDR header field"):
        vs.record(db, day1, "summary", vs.NOT_REPORTED)
    with pytest.raises(vs.ValueStateError, match="does not exist"):
        vs.record(db, 987654, "wob", vs.NOT_APPLICABLE)


def test_recorded_states_keep_the_value_missing_are_audited_and_the_latest_wins(world):
    db, day1, day2 = world
    vs.record(db, day1, "wob", vs.NOT_APPLICABLE, note="no rotation, SYN day 1")
    vs.record(db, day1, "rpm", vs.NOT_REPORTED)
    vs.record(db, day1, "rpm", vs.UNKNOWN)
    vs.record(db, day2, "depth_0000", vs.CALCULATED, method="previous report's 24:00 depth (M217 DERIVED rule)")
    one, two = vs.states(db, day1), vs.states(db, day2)
    assert (one["wob"]["state"], one["wob"]["value"], one["wob"]["note"]) == (
        vs.NOT_APPLICABLE, None, "no rotation, SYN day 1")
    assert one["rpm"]["state"] == vs.UNKNOWN and one["rpm"]["recorded"]
    assert (two["depth_0000"]["state"], two["depth_0000"]["value"]) == (vs.CALCULATED, 300.0)
    assert two["depth_0000"]["method"].startswith("previous report's 24:00 depth")
    with db.session_scope() as session:
        assert session.get(DailyReport, day1).wob is None and session.get(DailyReport, day1).rpm is None
        audit = session.query(AuditLog).filter(AuditLog.action == vs.AUDIT_ACTION).all()
        assert len(audit) == 4 and {a.entity_id for a in audit} == {day1, day2}


def test_a_later_edit_that_contradicts_the_state_is_reported_not_repaired(world):
    db, day1, _day2 = world
    vs.record(db, day1, "wob", vs.NOT_APPLICABLE)
    with db.session_scope() as session:
        session.get(DailyReport, day1).wob = 12.0
    entry = vs.states(db, day1)["wob"]
    assert entry["state"] == vs.INCONSISTENT and entry["recorded_state"] == vs.NOT_APPLICABLE
    assert not entry["consistent"] and "needs an empty value" in entry["reason"]
    with db.session_scope() as session:
        assert session.get(DailyReport, day1).wob == 12.0                     # the value is not touched
        assert session.query(DdrValueState).one().state == vs.NOT_APPLICABLE  # nor the recorded state


def test_value_state_events_are_insert_only(world):
    db, day1, _day2 = world
    vs.record(db, day1, "wob", vs.NOT_APPLICABLE)
    with db.engine.begin() as conn:
        row_id = conn.execute(text("SELECT id FROM ddr_value_states")).scalar_one()
    for statement in ("UPDATE ddr_value_states SET state = 'ZERO' WHERE id = :i",
                      "UPDATE ddr_value_states SET field = 'rpm' WHERE id = :i",
                      "DELETE FROM ddr_value_states WHERE id = :i"):
        with pytest.raises(Exception, match="ddr_value_states"):
            with db.engine.begin() as conn:
                conn.execute(text(statement), {"i": row_id})


def test_dialog_saves_valid_states_and_reports_refusals(world):
    from PySide6.QtWidgets import QApplication

    from dialogs.ddr_value_states_dialog import DdrValueStatesDialog

    db, day1, _day2 = world
    app = QApplication.instance() or QApplication([])
    dialog = DdrValueStatesDialog(db, day1)
    try:
        assert dialog.pending() == []                              # implicit states are not re-recorded
        dialog.set_state("wob", vs.NOT_APPLICABLE)
        dialog.set_state("rpm", vs.UNKNOWN)
        dialog.set_state("depth_2400", vs.UNKNOWN)                 # holds 300 m: refused
        outcome = dialog.save()
        assert sorted(outcome["saved"]) == ["rpm", "wob"]
        assert [field for field, _reason in outcome["refused"]] == ["depth_2400"]
        assert "Saved 2 state(s)" in dialog.status.text() and "needs an empty value" in dialog.status.text()
        row = dialog.fields.index("wob")
        assert dialog.table.item(row, 4).text() == "yes"
        assert dialog.table.cellWidget(row, 2).currentData() == vs.NOT_APPLICABLE
        assert dialog.table.item(dialog.fields.index("depth_2400"), 4).text() == "implicit"
        assert dialog.pending() == []
    finally:
        dialog.deleteLater()
        del app


def test_the_daily_report_tab_opens_the_dialog_for_the_open_report(world, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from tabs.w2_Daily_Report import DailyReportWidget

    db, day1, _day2 = world
    app = QApplication.instance() or QApplication([])
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]))
    tab = DailyReportWidget(db)
    try:
        assert tab.value_states_btn.objectName() == "value_states_btn"
        tab.current_report_id = None
        assert tab.value_states_dialog() is None and warnings == ["Open a saved report first"]
        tab.current_report_id = day1
        dialog = tab.value_states_dialog()
        assert dialog is not None and dialog.report_id == day1
        dialog.deleteLater()
    finally:
        tab.deleteLater()
        del app


@pytest.mark.parametrize("stored, expected", [
    (None, vs.NOT_REPORTED), (0.0, vs.ZERO), (2.5, vs.REPORTED), ("abc", vs.INCONSISTENT),
    (float("nan"), vs.INCONSISTENT), (True, vs.INCONSISTENT),
])
def test_implicit_state_never_calls_an_unreadable_stored_value_empty(stored, expected):
    assert vs.implicit_state(stored) == expected


def test_the_data_quality_workspace_lists_an_inconsistent_value_state(world):
    from core import data_quality_workspace as dqw

    db, report_id, _day2 = world
    with db.session_scope() as session:
        well_id = session.get(DailyReport, report_id).well_id
    vs.record(db, report_id, "wob", vs.UNKNOWN, note="SYN: sensor out")
    assert not [i for i in dqw.collect(db, well_id) if i.category == dqw.CATEGORY_VALUE_STATE]
    with db.session_scope() as session:
        session.get(DailyReport, report_id).wob = 12.0          # edited later, the UNKNOWN state is now wrong
    (issue,) = [i for i in dqw.collect(db, well_id) if i.category == dqw.CATEGORY_VALUE_STATE]
    assert issue.report_id == report_id and issue.severity == dqw.ERROR and "WOB" in issue.message.upper()
    assert issue.target["type"] == "daily_report"
