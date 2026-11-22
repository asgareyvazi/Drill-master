"""M302: read-only value-lineage UI, reached through the real dialogs (SYNTHETIC golden workbook import).

Navigation 1: W2 Daily Report tab -> value-states dialog (the same factory the toolbar button uses) -> select a
header field -> "🧬 Lineage…". Navigation 2: Import review dialog -> select one item -> "🧬 Lineage…" after a
correction. The lineage dialog must show the check, stages, corrections, expected and stored values, and must not
change anything: no input widget, no editable cell, and the database row counts and the report are unchanged.
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QAbstractItemView, QLineEdit, QSpinBox, QTableWidget, QTextEdit

from core import import_value_lineage as ivl
from test_m300_m301_value_lineage import _import  # noqa: F401  (real Excel-route import helper)


def _counts(db):
    from core.database import AuditLog, DailyReport, DdrValueState, ImportReviewItem
    with db.session_scope() as session:
        report = session.query(DailyReport).order_by(DailyReport.id.desc()).first()
        return (session.query(AuditLog).count(), session.query(DdrValueState).count(),
                session.query(ImportReviewItem).count(), report.updated_at, report.depth_0000)


def _assert_read_only(dialog):
    assert not dialog.findChildren(QLineEdit) and not dialog.findChildren(QTextEdit)
    assert not dialog.findChildren(QSpinBox)
    for table in dialog.findChildren(QTableWidget):
        assert table.editTriggers() == QAbstractItemView.NoEditTriggers
        for r in range(table.rowCount()):
            for c in range(table.columnCount()):
                item = table.item(r, c)
                assert item is None or not (item.flags() & item.flags().__class__.ItemIsEditable)


@pytest.fixture
def imported(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from core.permissions import permissions

    permissions.set_user({"id": 1, "username": "m302-synthetic", "role": "engineer"})     # conftest restores
    for name in ("warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: QMessageBox.Ok)
    app = QApplication.instance() or QApplication([])
    db, well, report, items = _import(tmp_path, cells={"R9": "1,500"})
    yield app, db, well, report, items
    db.close()


def test_w2_value_states_dialog_opens_the_lineage_of_the_selected_field(imported):
    from tabs.w2_Daily_Report import DailyReportWidget

    _app, db, _well, report, _items = imported
    tab = DailyReportWidget(db)
    try:
        assert tab.load_report_by_id(report) is not False
        states = tab.value_states_dialog()
        assert states.lineage_button.objectName() == "ddr_value_states_lineage"
        assert states.open_lineage() is None and "Select a field" in states.status.text()   # nothing selected
        before = _counts(db)
        states.table.selectRow(states.fields.index("depth_2400"))
        states.lineage_button.click()                                                        # the real button
        lineage = states.lineage_dialog
        assert lineage is not None and lineage.isVisible() and lineage.objectName() == "value_lineage_dialog"
        assert lineage.lineage["check"] == ivl.MATCH and "MATCH" in lineage.check_label.text()
        stages = lineage.stages
        assert [stages.item(r, 0).text() for r in range(stages.rowCount())] == list(ivl.STAGES)
        assert stages.item(4, 1).text() == "IMPORTED_WITHOUT_REVIEW"
        summary = {lineage.summary.item(r, 0).text(): lineage.summary.item(r, 1).text()
                   for r in range(lineage.summary.rowCount())}
        assert summary["Stored now"] == "225.0" and summary["Expected value"] == "225.0"
        assert summary["Identity"].startswith(f"iv:{report}:daily_report.depth_2400:")
        _assert_read_only(lineage)
        lineage.close()
        # A field kept for review points to its review item instead of guessing.
        states.table.selectRow(states.fields.index("depth_0000"))
        states.lineage_button.click()
        pending = states.lineage_dialog
        assert pending.lineage["check"] == ivl.NOT_APPLICABLE and "Review item" in [
            pending.summary.item(r, 0).text() for r in range(pending.summary.rowCount())]
        pending.close()
        assert _counts(db) == before                                                         # nothing written
        states.deleteLater()
    finally:
        tab.deleteLater()


def test_import_review_dialog_opens_the_lineage_with_the_correction(imported):
    from core.review_scalar_correction import apply_correction, preview_correction
    from dialogs.import_review_dialog import ImportReviewDialog

    _app, db, well, report, _items = imported
    item = next(i for i in db.get_import_review_items(well, report_id=report)
                if i["review_type"] == "value_state" and i["target_field"] == "daily_report.depth_0000")
    token = preview_correction(db, item["id"], well, "1500")["token"]
    apply_correction(db, item["id"], well, "1500", reason="SYN: read from paper", confirmed=True, token=token)
    dialog = ImportReviewDialog(db, well, report_id=report)
    try:
        dialog.state_filter.setCurrentIndex(dialog.state_filter.findText("All"))
        row = next(r for r, shown in enumerate(dialog.visible) if shown["id"] == item["id"])
        dialog.table.selectRow(row)
        before = _counts(db)
        dialog.lineage_btn.click()
        lineage = dialog.lineage_dialog
        assert lineage is not None and lineage.isVisible()
        assert lineage.lineage["check"] == ivl.MATCH and lineage.lineage["expected_basis"] == "the latest correction"
        assert lineage.corrections.rowCount() == 1
        assert (lineage.corrections.item(0, 1).text(), lineage.corrections.item(0, 3).text()) == \
            ("1500.0", "SYN: read from paper")
        _assert_read_only(lineage)
        lineage.close()
        assert _counts(db) == before
    finally:
        dialog.deleteLater()
