"""M286 / M272: the new insert-only event tables under the enforced data-layer policy.

Archive marks and DDR value states are written by report editors and never updated. A value state leaves with its
report: a supervisor who can delete reports but not edit them can still delete a report that has value states.
"""
from __future__ import annotations

import pytest

from core import calculation_cases as cc
from core import calculation_history as ch
from core import calculation_workbench as wb
from core import ddr_value_states as vs
from core.authorization import DELETE_REPORTS, DELETE_WELL, EDIT, NOBODY, TABLE_POLICY, AuthorizationError
from test_data_layer_authorization import IDS, _count, db_for, seeded_template  # noqa: F401  (fixtures)


def test_policies_are_insert_only_events():
    for table in ("calculation_archive_marks", "ddr_value_states"):
        assert TABLE_POLICY[table].write == (NOBODY,) and TABLE_POLICY[table].insert == (EDIT,)
    assert TABLE_POLICY["ddr_value_states"].delete == (DELETE_REPORTS, DELETE_WELL)
    assert TABLE_POLICY["calculation_archive_marks"].delete == (DELETE_WELL,)


def test_an_editor_records_value_states_and_a_viewer_cannot(db_for):  # noqa: F811
    open_as, path = db_for
    editor = open_as("engineer")
    vs.record(editor, IDS["report"], "wob", vs.UNKNOWN, note="SYN: sensor out")
    assert _count(path, "SELECT COUNT(*) FROM ddr_value_states") == 1
    viewer = open_as("viewer")
    with pytest.raises(AuthorizationError):
        vs.record(viewer, IDS["report"], "rpm", vs.UNKNOWN)
    assert _count(path, "SELECT COUNT(*) FROM ddr_value_states") == 1


def test_a_report_with_value_states_is_deleted_by_a_report_deleter(db_for):  # noqa: F811
    open_as, path = db_for
    vs.record(open_as("engineer"), IDS["report"], "wob", vs.UNKNOWN)
    supervisor = open_as("supervisor", permissions={"can_edit_reports": False})
    assert supervisor.delete_daily_report(IDS["report"])
    assert _count(path, "SELECT COUNT(*) FROM ddr_value_states") == 0


def test_an_editor_archives_and_restores_a_case_and_a_viewer_cannot(db_for):  # noqa: F811
    open_as, path = db_for
    editor = open_as("engineer")
    case = cc.save_case(editor, calculator="SYN calculator", name="SYN authz case", inputs={"a_ft": 1.0},
                        results={"b_ft": 2.0}, well_id=IDS["well"])
    entry = {(e.table, e.record_id): e for e in ch.load_history(editor, well_id=IDS["well"])}[
        ("calculation_cases", case["id"])]
    with pytest.raises(AuthorizationError):
        wb.archive(open_as("viewer"), entry, "SYN: not allowed")
    wb.archive(editor, entry, "SYN: superseded")
    wb.restore(editor, entry, "SYN: still needed")
    assert _count(path, "SELECT COUNT(*) FROM calculation_archive_marks") == 2
    assert wb.state(editor, entry) == wb.ACTIVE


def test_m365_a_viewer_is_refused_before_the_record_is_read(db_for):  # noqa: F811
    """The workbench refuses first, so a viewer cannot probe which ids exist (no 'does not exist' answer)."""
    import dataclasses

    open_as, path = db_for
    editor = open_as("engineer")
    case = cc.save_case(editor, calculator="SYN calculator", name="SYN authz probe", inputs={"a_ft": 1.0},
                        results={"b_ft": 2.0}, well_id=IDS["well"])
    entry = {(e.table, e.record_id): e for e in ch.load_history(editor, well_id=IDS["well"])}[
        ("calculation_cases", case["id"])]
    ghost = dataclasses.replace(entry, record_id=case["id"] + 1000)
    with pytest.raises(AuthorizationError):
        wb.archive(open_as("viewer"), ghost, "SYN: probing")
    with pytest.raises(wb.WorkbenchError, match="does not exist"):
        wb.archive(editor, ghost, "SYN: editor sees the real answer")
