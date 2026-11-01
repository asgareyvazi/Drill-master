"""M54 DDR workflow: save-time time-log validation, report timeline, duplicate-for-review.

Real DailyReportWidget on offscreen Qt (not Windows desktop testing) with a
temporary file SQLite database of synthetic operations data. No real DDR content.
"""
from __future__ import annotations

from datetime import date, time, timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from synthetic_operations import build_synthetic_operations, make_file_database  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _log(t_from, t_to, description="Synthetic activity"):
    return SimpleNamespace(time_from=t_from, time_to=t_to, duration=0, main_phase="DRL", main_code="DRL",
                           sub_code="", status="Normal", is_npt=False, activity_description=description,
                           contractor="")


@pytest.fixture
def widget(app):
    from tabs.w2_Daily_Report import DailyReportWidget
    w = DailyReportWidget(db_manager=None)
    w.time_24_table.setRowCount(0)
    w.morning_table.setRowCount(0)
    yield w
    w.close()
    w.deleteLater()
    app.processEvents()


def _fill(table, w, rows):
    table.setRowCount(0)
    for t_from, t_to in rows:
        w.add_time_log_row(table, _log(t_from, t_to))


# ---- time-log validation (canonical TimeLogValidator rules) --------------------------------------
def test_a_contiguous_day_ending_at_2400_has_no_issues(widget):
    _fill(widget.time_24_table, widget, [(time(0, 0), time(6, 0)), (time(6, 0), time(18, 0)), (time(18, 0), "24:00")])
    assert widget.time_log_issues() == ([], [])


def test_overlapping_rows_block_and_name_both_intervals(widget):
    _fill(widget.time_24_table, widget, [(time(0, 0), time(8, 0)), (time(7, 0), time(12, 0)), (time(12, 0), "24:00")])
    blocking, _notes = widget.time_log_issues()
    assert len(blocking) == 1
    assert "overlap" in blocking[0].lower() and "00:00" in blocking[0] and "07:00" in blocking[0]


def test_a_gap_is_a_note_not_a_blocker(widget):
    _fill(widget.time_24_table, widget, [(time(0, 0), time(6, 0)), (time(8, 0), "24:00")])
    blocking, notes = widget.time_log_issues()
    assert blocking == [] and len(notes) == 1 and "120 minutes" in notes[0]


def test_the_morning_log_checks_overlap_but_not_gaps(widget):
    _fill(widget.morning_table, widget, [(time(0, 0), time(2, 0))])
    assert widget.time_log_issues() == ([], [])            # 02:00-24:00 uncovered is by design
    _fill(widget.morning_table, widget, [(time(0, 0), time(3, 0)), (time(2, 0), time(6, 0))])
    blocking, _ = widget.time_log_issues()
    assert len(blocking) == 1 and blocking[0].startswith("Morning log")


def test_an_unreadable_time_blocks_with_its_row_number(widget):
    _fill(widget.time_24_table, widget, [(time(0, 0), time(6, 0)), ("bad", time(9, 0))])
    blocking, _ = widget.time_log_issues()
    assert blocking == ["24-hour log row 2 has a missing or invalid time"]


def test_a_midnight_crossing_row_overlaps_the_early_morning(widget):
    _fill(widget.time_24_table, widget, [(time(22, 0), time(2, 0)), (time(1, 0), time(22, 0))])
    blocking, _ = widget.time_log_issues()
    assert len(blocking) == 1 and "overlap" in blocking[0].lower()


# ---- database-backed workflow -----------------------------------------------------------------------
@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    db = make_file_database(tmp_path_factory.mktemp("m54ddr") / "synthetic-m54-ddr.db")
    ids = build_synthetic_operations(db, end_date=date.today() - timedelta(days=1))
    yield db, ids
    db.engine.dispose()


@pytest.fixture
def db_widget(app, synthetic):
    from core.permissions import permissions
    from tabs.w2_Daily_Report import DailyReportWidget
    permissions.set_user({"id": 1, "username": "m54-synthetic", "role": "engineer"})  # conftest restores
    w = DailyReportWidget(db_manager=synthetic[0])
    yield w
    w.close()
    w.deleteLater()
    app.processEvents()


def _ordered(db, well_id):
    reports = db.get_daily_reports_by_well(well_id)
    reports.sort(key=lambda r: (r["report_date"], r["report_number"] or -1, r["id"]))
    return reports


def _time_log_rows(db, report_id):
    from core.database import TimeLog24H
    with db.session_scope() as session:
        return sorted((r.time_from, r.time_to) for r in session.query(TimeLog24H).filter_by(report_id=report_id))


def test_save_is_blocked_by_an_overlap_and_nothing_is_written(db_widget, synthetic):
    db, ids = synthetic
    report = _ordered(db, ids["dev"])[0]
    db_widget.load_report_by_id(report["id"])
    before = _time_log_rows(db, report["id"])
    errors = []
    db_widget.status_manager.show_error = lambda _src, message: errors.append(message)
    _fill(db_widget.time_24_table, db_widget, [(time(0, 0), time(10, 0)), (time(9, 0), "24:00")])
    assert db_widget.save_report() is False
    assert errors and errors[-1].startswith("Report not saved — fix the time log:")
    assert _time_log_rows(db, report["id"]) == before


def test_a_valid_time_log_saves_and_a_gap_is_reported(db_widget, synthetic):
    db, ids = synthetic
    report = _ordered(db, ids["dev"])[1]
    db_widget.load_report_by_id(report["id"])
    successes = []
    db_widget.status_manager.show_success = lambda _src, message: successes.append(message)
    _fill(db_widget.time_24_table, db_widget, [(time(0, 0), time(6, 0)), (time(7, 0), "24:00")])
    db_widget.morning_table.setRowCount(0)
    assert db_widget.save_report() is True
    assert _time_log_rows(db, report["id"]) == [(time(0, 0), time(6, 0)), (time(7, 0), time(0, 0))]
    assert "Gap detected: 60 minutes" in successes[-1]


def test_the_timeline_lists_reports_oldest_first_and_tracks_the_open_report(db_widget, synthetic):
    db, ids = synthetic
    reports = _ordered(db, ids["dev"])
    db_widget.current_well_id = ids["dev"]
    db_widget.refresh_report_timeline()
    table = db_widget.report_timeline
    assert table.rowCount() == len(reports) == 6
    assert [table.item(r, 0).text() for r in range(table.rowCount())] == [str(r["report_date"]) for r in reports]
    assert db_widget.report_timeline_status.text() == "6 report(s), oldest first."
    db_widget.load_report_by_id(reports[3]["id"])
    assert [i.row() for i in table.selectionModel().selectedRows()] == [3]


def test_timeline_double_click_respects_the_unsaved_edit_guard(db_widget, synthetic, monkeypatch):
    db, ids = synthetic
    reports = _ordered(db, ids["dev"])
    db_widget.current_well_id = ids["dev"]
    db_widget.refresh_report_timeline()
    db_widget.load_report_by_id(reports[0]["id"])
    monkeypatch.setattr(db_widget, "_has_unsaved_edits", lambda: True)
    monkeypatch.setattr(db_widget, "confirm_discard_edits", lambda: False)
    assert db_widget._timeline_activated(db_widget.report_timeline.item(2, 0)) is False
    assert db_widget.current_report_id == reports[0]["id"]
    monkeypatch.setattr(db_widget, "confirm_discard_edits", lambda: True)
    assert db_widget._timeline_activated(db_widget.report_timeline.item(2, 0)) is True
    assert db_widget.current_report_id == reports[2]["id"]


def test_timeline_without_a_well_is_explicit(db_widget):
    db_widget.current_well_id = None
    db_widget.refresh_report_timeline()
    assert db_widget.report_timeline.rowCount() == 0
    assert db_widget.report_timeline_status.text() == "Select a well to list its reports."


def test_duplicate_prepares_an_unsaved_draft_and_persists_nothing(db_widget, synthetic):
    db, ids = synthetic
    reports = _ordered(db, ids["done"])
    source = reports[-1]
    source_full = db.get_daily_report_by_id(source["id"])
    count = len(reports)
    target = source["report_date"] + timedelta(days=1)
    assert db_widget.duplicate_report_for_review(source["id"], options={
        "target_date": target, "report_number": 99, "copy_time_log": False,
        "copy_morning_log": False, "copy_summary": False, "carry_depth": True,
    }) is True
    assert len(db.get_daily_reports_by_well(ids["done"])) == count          # nothing persisted
    assert db_widget.current_report_id is None and db_widget.current_report is None
    assert db_widget.report_date.date().toPython() == target
    assert db_widget.report_number.value() == 99
    assert db_widget.depth_0000.value() == pytest.approx(source_full["depth_2400"])
    assert db_widget.depth_2400.value() == -1 and db_widget.depth_0600.value() == -1
    assert db_widget.status_combo.currentText() == "Draft"
    assert db_widget.summary_text.toPlainText() == ""
    assert db_widget._has_unsaved_edits() is True                           # guarded until saved
    # the user reviews, then saves explicitly: a NEW report, the source untouched
    db_widget.time_24_table.setRowCount(0)
    db_widget.add_time_log_row(db_widget.time_24_table, _log(time(0, 0), "24:00"))
    db_widget.morning_table.setRowCount(0)
    assert db_widget.save_report() is True
    after = db.get_daily_reports_by_well(ids["done"])
    assert len(after) == count + 1
    created = [r for r in after if r["report_date"] == target]
    assert len(created) == 1 and created[0]["id"] != source["id"] and created[0]["report_number"] == 99
    assert db.get_daily_report_by_id(source["id"])["report_date"] == source["report_date"]


def test_duplicate_can_copy_the_time_log_for_editing(db_widget, synthetic):
    db, ids = synthetic
    source = _ordered(db, ids["dev"])[2]
    db_widget.load_report_by_id(source["id"])
    rows = db_widget.time_24_table.rowCount()
    assert rows >= 1
    db_widget.duplicate_report_for_review(source["id"], options={
        "target_date": source["report_date"] + timedelta(days=30), "report_number": 77,
        "copy_time_log": True, "copy_morning_log": False, "copy_summary": True, "carry_depth": False,
    })
    assert db_widget.time_24_table.rowCount() == rows
    assert db_widget.depth_0000.value() == -1


def test_duplicate_without_a_saved_report_is_refused(db_widget):
    errors = []
    db_widget.status_manager.show_error = lambda _src, message: errors.append(message)
    db_widget.current_report_id = None
    assert db_widget.duplicate_report_for_review() is False
    assert errors == ["Open a saved report to duplicate it."]


def test_new_report_keeps_unsaved_edits_unless_confirmed(db_widget, synthetic, monkeypatch):
    db, ids = synthetic
    report = _ordered(db, ids["dev"])[0]
    db_widget.load_report_by_id(report["id"])
    monkeypatch.setattr(db_widget, "_has_unsaved_edits", lambda: True)
    monkeypatch.setattr(db_widget, "confirm_discard_edits", lambda: False)
    assert db_widget.new_report() is False and db_widget.current_report_id == report["id"]
    monkeypatch.setattr(db_widget, "confirm_discard_edits", lambda: True)
    db_widget.new_report()
    assert db_widget.current_report_id is None


# ---- review dialog ------------------------------------------------------------------------------------
def test_duplicate_dialog_review_is_explicit_and_warns_on_an_existing_date(app):
    from dialogs.ddr_duplicate_dialog import DuplicateReportDialog, default_duplicate_options
    source = {"report_number": 4, "report_date": date(2026, 1, 10)}
    assert default_duplicate_options(source)["target_date"] == date(2026, 1, 11)
    assert default_duplicate_options(source)["report_number"] == 5
    dialog = DuplicateReportDialog(source, existing_dates={date(2026, 1, 11)})
    text = "\n".join(dialog.review_lines())
    assert "Nothing is saved until you review the form and press Save Report." in text
    assert "WARNING: this well already has a report dated 2026-01-11." in text
    assert "Mud, bit, cost and other tab records are NOT duplicated." in text
    dialog.copy_time_log.setChecked(True)
    assert "24-hour time log: copied for editing." in dialog.review_label.text()
    dialog.date_edit.setDate(dialog.date_edit.date().addDays(1))
    assert "WARNING" not in dialog.review_label.text()
    assert dialog.options()["copy_time_log"] is True
    dialog.deleteLater()
