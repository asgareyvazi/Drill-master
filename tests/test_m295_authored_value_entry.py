"""M295: what an operator types for a numeric DDR field reaches storage through ``parse_authored`` (D86 kept).

SYNTHETIC fixture (tests/synthetic_operations.py). The path under test is the production one: the W2 Daily Report
tab opens the value-states dialog for the open report; the operator types into the "Typed entry" column; the
dialog saves through ``ddr_value_states.record_authored``; the tab reloads its form from storage; a following
Save Report keeps the typed value. "1,5" never becomes 15, "1,500" is never interpreted, NaN/inf/other text is
refused with a readable reason, and a refused entry writes nothing.
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
    db = make_file_database(tmp_path / "m295.db")
    ids = build_synthetic_operations(db)
    with db.engine.begin() as conn:                         # the fixture submits day 1; an operator edits a draft
        conn.execute(text("UPDATE daily_reports SET status = 'Draft' WHERE id = :id"), {"id": ids["reports"][1]})
    yield db, ids["reports"][1]                             # day 1: 0 -> 300 m, WOB empty
    db.engine.dispose()


def _stored(db, report_id, field):
    with db.session_scope() as session:
        return getattr(session.get(DailyReport, report_id), field)


def _counts(db):
    with db.session_scope() as session:
        return (session.query(DdrValueState).count(),
                session.query(AuditLog).filter(AuditLog.action == vs.AUTHORED_AUDIT_ACTION).count())


@pytest.mark.parametrize("typed, value, state", [
    ("312.5", 312.5, vs.REPORTED), (" 0 ", 0.0, vs.ZERO), ("N/A", None, vs.NOT_APPLICABLE),
    ("?", None, vs.UNKNOWN), ("NR", None, vs.NOT_REPORTED), ("-3", -3.0, vs.REPORTED),
])
def test_a_typed_entry_writes_value_and_state_together_with_one_audit(world, typed, value, state):
    db, day1 = world
    result = vs.record_authored(db, day1, "depth_2400", typed)
    assert (result["value"], result["state"], result["previous"]) == (value, state, 300.0)
    assert _stored(db, day1, "depth_2400") == value
    entry = vs.states(db, day1)["depth_2400"]
    assert (entry["state"], entry["recorded"], entry["consistent"]) == (state, True, True)
    with db.session_scope() as session:
        audit = session.query(AuditLog).filter(AuditLog.action == vs.AUTHORED_AUDIT_ACTION).one()
        assert "300.0 -> " in audit.details and state in audit.details and audit.entity_id == day1


@pytest.mark.parametrize("typed, reason", [
    ("1,5", "commas are refused"), ("1,500", "commas are refused"), ("nan", "not a finite number"),
    ("inf", "not a finite number"), ("-inf", "not a finite number"), ("12 m", "neither a number"),
    ("abc", "neither a number"),
])
def test_a_refused_entry_writes_nothing_and_says_why(world, typed, reason):
    db, day1 = world
    before = _counts(db)
    with pytest.raises(vs.ValueStateError) as exc:
        vs.record_authored(db, day1, "wob", typed)
    assert reason in str(exc.value) and str(exc.value).startswith("WOB: ")
    assert _stored(db, day1, "wob") is None and _counts(db) == before


def test_comma_entries_never_become_another_number(world):
    db, day1 = world
    for typed in ("1,5", "1,500", "15,0"):
        with pytest.raises(vs.ValueStateError):
            vs.record_authored(db, day1, "depth_2400", typed)
    assert _stored(db, day1, "depth_2400") == 300.0          # neither 15, 1.5, 1500 nor 150


def test_calculated_needs_a_number_and_records_the_method(world):
    db, day1 = world
    with pytest.raises(vs.ValueStateError, match="needs a typed number"):
        vs.record_authored(db, day1, "rop_meter", "N/A", calculated_method="depth / hours")
    result = vs.record_authored(db, day1, "rop_meter", "12.5", calculated_method="depth / hours")
    assert result["state"] == vs.CALCULATED
    assert vs.states(db, day1)["rop_meter"]["method"] == "depth / hours"


def test_unknown_field_and_locked_report_are_refused(world):
    db, day1 = world
    with pytest.raises(vs.ValueStateError, match="not a numeric DDR header field"):
        vs.record_authored(db, day1, "summary", "1")
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE daily_reports SET status = 'Approved' WHERE id = :id"), {"id": day1})
    before = _counts(db)
    with pytest.raises(vs.ValueStateError, match="Approved and cannot be edited"):
        vs.record_authored(db, day1, "wob", "12")
    assert _stored(db, day1, "wob") is None and _counts(db) == before


def test_an_audit_failure_rolls_back_value_and_state(world, monkeypatch):
    db, day1 = world
    before = _counts(db)

    def broken(*_a, **_k):
        raise RuntimeError("SYN: audit store unavailable")

    monkeypatch.setattr(db, "_add_mandatory_audit", broken)
    with pytest.raises(RuntimeError, match="audit store unavailable"):
        vs.record_authored(db, day1, "depth_2400", "999")
    assert _stored(db, day1, "depth_2400") == 300.0 and _counts(db) == before


def _tab(db, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from core.permissions import permissions
    from tabs.w2_Daily_Report import DailyReportWidget

    permissions.set_user({"id": 1, "username": "m295-synthetic", "role": "engineer"})  # conftest restores
    app = QApplication.instance() or QApplication([])
    for name in ("warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    return app, DailyReportWidget(db)


def test_w2_typed_entry_reaches_storage_reloads_the_form_and_survives_save_report(world, monkeypatch):
    db, day1 = world
    app, tab = _tab(db, monkeypatch)
    try:
        assert tab.load_report_by_id(day1) is not False
        assert tab.depth_2400.value() == 300.0 and not tab._has_unsaved_edits()
        dialog = tab.value_states_dialog()
        assert dialog.allow_typed_values
        dialog.set_typed("depth_2400", "312.5")
        dialog.set_typed("wob", "N/A")
        dialog.set_typed("rpm", "1,5")
        result = dialog.save()
        assert sorted(result["saved"]) == ["depth_2400", "wob"] and result["values_changed"]
        assert [field for field, _reason in result["refused"]] == ["rpm"]
        assert "commas are refused" in dialog.status.text()
        assert _stored(db, day1, "depth_2400") == 312.5 and _stored(db, day1, "rpm") is None
        assert vs.states(db, day1)["wob"]["state"] == vs.NOT_APPLICABLE
        tab.after_value_states(dialog)                   # what the button handler does after exec()
        assert tab.depth_2400.value() == 312.5 and not tab._has_unsaved_edits()
        dialog.deleteLater()
        assert tab.save_report() is not False
        assert _stored(db, day1, "depth_2400") == 312.5  # the form did not write a stale 300 back
        assert vs.states(db, day1)["depth_2400"]["state"] == vs.REPORTED
    finally:
        tab.deleteLater()
        del app


def test_w2_with_unsaved_edits_disables_typed_entries(world, monkeypatch):
    db, day1 = world
    app, tab = _tab(db, monkeypatch)
    try:
        tab.load_report_by_id(day1)
        tab.depth_0600.setValue(150.0)                     # an unsaved form edit
        assert tab._has_unsaved_edits()
        dialog = tab.value_states_dialog()
        assert not dialog.allow_typed_values
        dialog.set_typed("depth_2400", "999")
        assert dialog.typed_pending() == []
        result = dialog.save()
        assert result["saved"] == [] and not result["values_changed"]
        assert _stored(db, day1, "depth_2400") == 300.0
        tab.after_value_states(dialog)
        assert tab.depth_0600.value() == 150.0             # no reload: the unsaved edit is kept
        dialog.deleteLater()
    finally:
        tab.deleteLater()
        del app
