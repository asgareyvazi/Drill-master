"""M227: the read-only Data Quality workspace in the real MainWindow (Tools > Data Quality Workspace).

Synthetic issues of every category are created through the application (a report without depth / section, an open
DDR review item, a section carried forward and not confirmed, a survey station without azimuth). The workspace must
list each one with its source record, open that record through the main window, stay scoped to the selected well,
and change nothing in the database.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing

from core import data_quality_workspace as dqw
from core import ddr_carry_forward as carry
from tests.test_m70_selection_audit import _pump, window  # noqa: F401  (module fixture)


def _dump(path) -> list:
    with closing(sqlite3.connect(path)) as raw:
        return list(raw.iterdump())


def _seed(db, ids):
    from core.database import ImportReviewItem, LogisticsPersonnel, SurveyPoint
    with db.session_scope() as session:
        session.add(SurveyPoint(well_id=ids["alpha"], report_id=ids["report_2"], md=500.0, inc=1.5, azi=None))
        session.add(ImportReviewItem(well_id=ids["alpha"], report_id=ids["report_1"], review_id="SYN-M227-1",
                                     review_type="field", target_field="mud_report.mw",
                                     state="DEFERRED_UNRESOLVED", original_text="SYN"))
        session.add(LogisticsPersonnel(well_id=ids["alpha"], report_id=ids["report_1"], name="SYN PERSON"))
    with db.session_scope() as session:
        carry.apply(session, ids["report_1"], ids["report_2"], ["personnel"], confirmed=True)


def test_every_category_is_listed_with_its_source_and_nothing_is_written(window):  # noqa: F811
    win, db, ids = window
    _seed(db, ids)
    before = _dump(db.db_path)
    issues = dqw.collect(db, ids["alpha"])
    by_category = {i.category: i for i in issues}
    assert set(by_category) == {dqw.CATEGORY_REVIEW, dqw.CATEGORY_CARRIED, dqw.CATEGORY_SURVEY}
    assert by_category[dqw.CATEGORY_SURVEY].source_table == "survey_points"
    assert "azimuth" in by_category[dqw.CATEGORY_SURVEY].message
    assert by_category[dqw.CATEGORY_CARRIED].report_id == ids["report_2"]
    assert "Personnel on board" in by_category[dqw.CATEGORY_CARRIED].message
    assert by_category[dqw.CATEGORY_REVIEW].target["type"] == "import_review"
    twin = dqw.collect(db, ids["twin_1"])                       # the other well: only its own report
    assert [(i.category, i.source_id) for i in twin] == [(dqw.CATEGORY_REPORT, ids["twin_report"])]
    assert "depth_2400" in twin[0].message and "section" in twin[0].message
    assert _dump(db.db_path) == before


def test_the_workspace_opens_the_source_record_through_the_main_window(window, monkeypatch):  # noqa: F811
    from core.selection_manager import SelectionManager
    from test_m153_context_blocked_autosave import _no_modal_dialogs, _tab
    _no_modal_dialogs(monkeypatch)
    win, db, ids = window
    SelectionManager().select_well(ids["alpha"], {"id": ids["alpha"], "name": "SYN-ALPHA-01"}, force=True)
    win._targeted_refresh(ids["alpha"], None, None)          # what a hierarchy-tree click on the well does
    _pump(0.5)
    assert win.current_well and win.current_well.get("id") == ids["alpha"]
    before = _dump(db.db_path)
    dialog = win.open_data_quality()
    _pump(0.2)
    try:
        assert dialog is not None and dialog.table.rowCount() == 3
        assert all(f"{c}: 1" in dialog.summary.text()
                   for c in (dqw.CATEGORY_REVIEW, dqw.CATEGORY_CARRIED, dqw.CATEGORY_SURVEY))
        assert not dialog.open_button.isEnabled()               # nothing selected yet
        rows = {dialog.shown[r].category: r for r in range(len(dialog.shown))}
        dialog.table.selectRow(rows[dqw.CATEGORY_CARRIED])
        assert dialog.open_button.isEnabled()
        dialog.open_selected()
        _pump(0.5)
        daily = _tab(win, "DailyReportWidget")
        assert win.tab_widget.currentIndex() == 2 and daily.current_report_id == ids["report_2"], \
            (win.tab_widget.currentIndex(), daily.current_report_id)
        dialog.table.selectRow(rows[dqw.CATEGORY_REVIEW])
        review = dialog.open_selected()
        _pump(0.3)
        assert review is not None and review.table.rowCount() >= 1
        review.close()
        dialog.category_filter.setCurrentIndex(dialog.category_filter.findData(dqw.CATEGORY_SURVEY))
        assert [i.category for i in dialog.shown] == [dqw.CATEGORY_SURVEY]
        from PySide6.QtCore import Qt
        assert all(not (dialog.table.item(0, c).flags() & Qt.ItemIsEditable) for c in range(dialog.table.columnCount()))
        from PySide6.QtWidgets import QAbstractItemView
        assert dialog.table.editTriggers() == QAbstractItemView.NoEditTriggers
    finally:
        dialog.close()
        _pump(0.2)
    assert _dump(db.db_path) == before                          # opening and navigating wrote nothing
