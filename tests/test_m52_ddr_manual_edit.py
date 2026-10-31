"""M52 DDR manual editing: reorder time-log rows, safe row removal, report navigation.

Real DailyReportWidget, offscreen Qt (not Windows desktop testing); the
navigation and order round-trip cases use a temporary file SQLite database with
synthetic operations data.  No real DDR content.
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


def _log(t_from, t_to, description, npt=False, contractor="", status="Normal"):
    return SimpleNamespace(time_from=t_from, time_to=t_to, duration=0, main_phase="DRL",
                           main_code="NPT-B" if npt else "DRL", sub_code="", status=status, is_npt=npt,
                           activity_description=description, contractor=contractor)


@pytest.fixture
def widget(app):
    from tabs.w2_Daily_Report import DailyReportWidget
    w = DailyReportWidget(db_manager=None)
    table = w.time_24_table
    w.add_time_log_row(table, _log(time(6, 0), time(9, 0), "Synthetic A", npt=True, contractor="Syn Contractor"))
    w.add_time_log_row(table, _log(time(9, 0), time(12, 30), "Synthetic B", status="Delayed"))
    w.add_time_log_row(table, _log("bad-start", time(14, 0), "Synthetic C"))
    yield w
    w.close()
    w.deleteLater()
    app.processEvents()


def _descriptions(w):
    table = w.time_24_table
    return [table.cellWidget(r, 9).toPlainText() for r in range(table.rowCount())]


def test_move_down_and_up_swap_every_field(widget):
    table = widget.time_24_table
    before = [widget._time_row_state(table, r) for r in range(3)]
    table.setCurrentCell(0, 0)
    assert widget.move_time_log_row(table, 1)
    assert _descriptions(widget) == ["Synthetic B", "Synthetic A", "Synthetic C"]
    assert widget._time_row_state(table, 0) == before[1] and widget._time_row_state(table, 1) == before[0]
    assert table.currentRow() == 1
    assert table.cellWidget(1, 7).isChecked() and table.cellWidget(1, 4).currentIndex() == 1   # NPT moved with A
    assert not table.cellWidget(0, 7).isChecked() and table.cellWidget(0, 4).currentIndex() == 0
    assert widget.move_time_log_row(table, -1)
    assert [widget._time_row_state(table, r) for r in range(3)] == before


def test_moves_past_either_end_do_nothing(widget):
    table = widget.time_24_table
    table.setCurrentCell(0, 0)
    assert not widget.move_time_log_row(table, -1)
    table.setCurrentCell(2, 0)
    assert not widget.move_time_log_row(table, 1)
    assert _descriptions(widget) == ["Synthetic A", "Synthetic B", "Synthetic C"]


def test_an_invalid_time_moves_as_raw_text_and_stays_not_assessed(widget):
    table = widget.time_24_table
    table.setCurrentCell(2, 0)
    assert widget.move_time_log_row(table, -1)
    moved = table.cellWidget(1, 0)
    assert moved.get_display_string() == "bad-start" and table.cellWidget(1, 2).text() == "NOT ASSESSED"
    with pytest.raises(ValueError):
        moved.get_time()
    assert table.cellWidget(2, 0).get_time() == (9, 0, False)
    assert table.cellWidget(2, 2).text() not in ("NOT ASSESSED", "0.00")


def test_the_npt_tint_keeps_each_cell_style_through_toggles_and_moves(widget):
    """Pre-existing defect (baseline dbf8d50): the NPT tint replaced, then cleared, every cell stylesheet."""
    table = widget.time_24_table
    base = table.cellWidget(1, 9).styleSheet()
    assert "font-size: 11px" in base
    table.cellWidget(1, 7).setChecked(True)                    # B becomes NPT
    tinted = table.cellWidget(1, 9).styleSheet()
    assert "font-size: 11px" in tinted and widget.NPT_ROW_COLOUR in tinted
    table.cellWidget(1, 7).setChecked(False)
    assert table.cellWidget(1, 9).styleSheet() == base
    table.setCurrentCell(0, 0)                                 # A (NPT) and B swap: tint moves, style stays
    assert widget.move_time_log_row(table, 1)
    assert table.cellWidget(0, 9).styleSheet() == base
    assert widget.NPT_ROW_COLOUR in table.cellWidget(1, 9).styleSheet()
    assert "font-size: 11px" in table.cellWidget(1, 9).styleSheet()


def test_an_invalid_time_keeps_its_warning_colour_on_an_npt_row(widget):
    table = widget.time_24_table
    invalid = table.cellWidget(2, 0)
    assert invalid.is_invalid() and "#ffe0b2" in invalid.styleSheet()
    table.cellWidget(2, 7).setChecked(True)
    assert "#ffe0b2" in invalid.styleSheet()                   # the warning is not painted over
    assert widget.NPT_ROW_COLOUR in table.cellWidget(2, 1).styleSheet()   # the valid time is tinted
    table.cellWidget(2, 7).setChecked(False)
    assert "#ffe0b2" in invalid.styleSheet() and table.cellWidget(2, 1).styleSheet() == ""


def test_after_a_move_each_row_still_recalculates_itself(widget):
    table = widget.time_24_table
    table.setCurrentCell(0, 0)
    widget.move_time_log_row(table, 1)
    row0_duration = table.cellWidget(0, 2).text()
    table.cellWidget(1, 1).set_time(10, 0)                  # A now on row 1: 06:00 -> 10:00
    assert table.cellWidget(1, 2).text() == "4.00"
    assert table.cellWidget(0, 2).text() == row0_duration


def test_removing_a_row_keeps_the_rows_below_bound_to_their_own_row(widget):
    table = widget.time_24_table
    table.setCurrentCell(0, 0)
    widget.remove_time_log_row(table)
    assert _descriptions(widget) == ["Synthetic B", "Synthetic C"]
    table.cellWidget(0, 1).set_time(13, 0)                  # B: 09:00 -> 13:00 on row 0
    assert table.cellWidget(0, 2).text() == "4.00"
    assert table.cellWidget(1, 2).text() == "NOT ASSESSED"  # C untouched


# ---- database: order round trip and navigation ---------------------------------------------------
@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    db = make_file_database(tmp_path_factory.mktemp("m52ddr") / "synthetic-m52-ddr.db")
    ids = build_synthetic_operations(db, end_date=date.today() - timedelta(days=1))
    yield db, ids
    db.engine.dispose()


@pytest.fixture
def db_widget(app, synthetic):
    from tabs.w2_Daily_Report import DailyReportWidget
    w = DailyReportWidget(db_manager=synthetic[0])
    yield w
    w.close()
    w.deleteLater()
    app.processEvents()


def _ordered_report_ids(db, well_id):
    reports = db.get_daily_reports_by_well(well_id)
    reports.sort(key=lambda r: (r["report_date"], r["report_number"] or -1, r["id"]))
    return [r["id"] for r in reports]


def test_a_reordered_time_log_survives_save_and_reload(db_widget, synthetic):
    db, ids = synthetic
    report_id = _ordered_report_ids(db, ids["dev"])[0]
    table = db_widget.time_24_table
    table.setRowCount(0)
    db_widget.add_time_log_row(table, _log(time(0, 30), time(6, 0), "Synthetic first"))
    db_widget.add_time_log_row(table, _log(time(6, 0), time(12, 0), "Synthetic second"))
    db_widget.add_time_log_row(table, _log(time(12, 0), time(18, 0), "Synthetic third"))
    table.setCurrentCell(2, 0)
    db_widget.move_time_log_row(table, -1)
    db_widget.move_time_log_row(table, -1)                   # third is now first (an out-of-time order)
    db_widget.morning_table.setRowCount(0)
    db_widget.save_time_logs_to_db(report_id)
    db_widget.load_time_logs(report_id, table)
    assert _descriptions(db_widget) == ["Synthetic third", "Synthetic first", "Synthetic second"]


def test_previous_and_next_follow_date_order_and_stop_at_the_ends(db_widget, synthetic):
    db, ids = synthetic
    order = _ordered_report_ids(db, ids["dev"])
    assert len(order) >= 3
    assert db_widget.load_report_by_id(order[1]) is not False
    assert db_widget.navigate_report(1) == order[2] and db_widget.current_report_id == order[2]
    assert db_widget.navigate_report(-1) == order[1]
    db_widget.load_report_by_id(order[0])
    assert db_widget.navigate_report(-1) is None and db_widget.current_report_id == order[0]
    db_widget.load_report_by_id(order[-1])
    assert db_widget.navigate_report(1) is None and db_widget.current_report_id == order[-1]


def test_unsaved_edits_are_not_discarded_without_confirmation(db_widget, synthetic, monkeypatch):
    db, ids = synthetic
    order = _ordered_report_ids(db, ids["dev"])
    db_widget.load_report_by_id(order[0])
    monkeypatch.setattr(db_widget, "_has_unsaved_edits", lambda: True)
    asked = []
    monkeypatch.setattr(db_widget, "confirm_discard_edits", lambda: asked.append(1) or False)
    assert db_widget.navigate_report(1) is None and db_widget.current_report_id == order[0] and asked
    monkeypatch.setattr(db_widget, "confirm_discard_edits", lambda: True)
    assert db_widget.navigate_report(1) == order[1]


def test_a_report_list_read_error_is_reported_not_treated_as_empty(db_widget, synthetic, monkeypatch):
    db, ids = synthetic
    db_widget.current_well_id = ids["dev"]
    errors = []
    monkeypatch.setattr(db_widget.status_manager, "show_error", lambda *a, **k: errors.append(a))

    def broken(_well_id):
        raise OSError("synthetic read failure")
    monkeypatch.setattr(db, "get_daily_reports_by_well", broken)
    assert db_widget.navigate_report(1) is None and errors


def test_a_reorder_is_an_unsaved_edit_that_blocks_navigation_without_confirmation(db_widget, synthetic, monkeypatch):
    from core import editor_bindings
    db, ids = synthetic
    order = _ordered_report_ids(db, ids["dev"])
    editor_bindings.configure(db_widget)                    # the real dirty tracking, as the main window does
    db_widget.load_report_by_id(order[0])
    table = db_widget.time_24_table
    db_widget.add_time_log_row(table, _log(time(1, 0), time(2, 0), "Synthetic one"))
    db_widget.add_time_log_row(table, _log(time(2, 0), time(3, 0), "Synthetic two"))
    for section in db_widget._tracked_edit_sections:
        section.checkpoint()
    assert not db_widget._has_unsaved_edits()
    table.setCurrentCell(table.rowCount() - 1, 0)
    assert db_widget.move_time_log_row(table, -1)
    assert db_widget._has_unsaved_edits()
    asked = []
    monkeypatch.setattr(db_widget, "confirm_discard_edits", lambda: asked.append(1) or False)
    assert db_widget.navigate_report(1) is None and asked and db_widget.current_report_id == order[0]
