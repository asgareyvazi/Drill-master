"""Import preview: operator decisions reach the canonical review payloads.

Three defects fixed together (M43 closure), all in ImportPreviewDialog:

* Rows were filled with sorting enabled, so Qt re-sorted each row as soon as
  its first cell was set and the remaining cells landed in another row; with
  N review items only one row showed its values.
* The row->payload link was a dict stored under Qt.UserRole. PySide6 stores
  a converted copy, so decisions and edits were written to the copy while
  confirm/apply read the canonical payloads: a review row could never be
  resolved and an operator REJECT never reached the import boundary.
* "Accept high" / "reject low" swallowed every exception, hiding a failure to
  record a decision. Only an unparseable confidence is skipped now.

Real Qt widgets (offscreen), synthetic review rows, no database.
"""

from __future__ import annotations

import pytest

from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

from core.import_quality import unresolved_review_items


@pytest.fixture
def preview():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from dialogs.excel_import_dialog import ImportPreviewDialog

    review = [
        {"source_cell": f"A{i}", "confidence": conf, "decision": "REVIEW",
         "review_state": "unreviewed", "target_field": f"field_{i}",
         "normalized_value": str(i)}
        for i, conf in enumerate([0.97, 0.80, 0.50, 0.99], start=1)
    ]
    report = {"review": review, "issues": [{"sheet": "S", "row": 3, "field": "f"}]}
    dlg = ImportPreviewDialog("synthetic.xlsx", {}, report)
    yield dlg, review
    dlg.deleteLater()
    app.processEvents()


def _rows(dlg):
    return {dlg.table.item(r, 3).text(): r for r in range(dlg.table.rowCount())}


def _decision(dlg, row):
    return dlg.table.item(row, 9).text()


def test_every_review_row_is_rendered_with_its_own_values(preview):
    dlg, review = preview
    table = dlg.table
    assert table.rowCount() == len(review) + 1
    for r in range(table.rowCount()):
        assert all(table.item(r, c) is not None for c in range(10)), r
    rows = _rows(dlg)
    for i, item in enumerate(review, start=1):
        r = rows[f"A{i}"]
        assert table.item(r, 7).text() == f"field_{i}"
        assert table.item(r, 8).text() == f"{item['confidence']:.0%}"


def test_operator_decision_reaches_the_canonical_payload(preview):
    dlg, review = preview
    rows = _rows(dlg)
    assert len(unresolved_review_items(dlg._row_payloads)) == 4
    for i, decision in enumerate(["ACCEPT", "REJECT", "REJECT", "ACCEPT"], start=1):
        dlg.table.setItem(rows[f"A{i}"], 9, QTableWidgetItem(decision))
    dlg.get_decisions()
    assert [p["decision"] for p in review] == ["ACCEPT", "REJECT", "REJECT", "ACCEPT"]
    assert review[1]["review_state"] == "rejected"
    assert unresolved_review_items(dlg._row_payloads) == []


def test_payload_link_survives_a_user_sort_and_issue_rows_get_none(preview):
    dlg, review = preview
    dlg.table.sortByColumn(8, Qt.AscendingOrder)  # by confidence text
    rows = _rows(dlg)
    assert rows["A3"] != 2 or rows["A4"] != 3  # the order really changed
    assert dlg._payload_for_row(rows["A3"]) is review[2]
    assert dlg._payload_for_row(rows["Row 3"]) is None
    dlg._set_decision(rows["A3"], "REJECT")
    assert review[2]["review_state"] == "rejected"
    assert [p["review_state"] for i, p in enumerate(review) if i != 2] == ["unreviewed"] * 3


def test_accept_high_sets_only_numeric_high_rows(preview):
    dlg, review = preview
    rows = _rows(dlg)
    # A reviewer-edited, non-numeric confidence on an otherwise high row.
    dlg.table.setItem(rows["A4"], 8, QTableWidgetItem("n/a"))
    dlg._accept_high()
    assert _decision(dlg, rows["A1"]) == "ACCEPT"
    assert review[0]["review_state"] == "accepted"
    assert _decision(dlg, rows["A2"]) == "REVIEW"
    assert _decision(dlg, rows["A4"]) == "REVIEW"  # non-numeric: left for manual review
    assert review[3]["review_state"] == "unreviewed"


def test_reject_low_sets_only_numeric_low_rows(preview):
    dlg, review = preview
    rows = _rows(dlg)
    dlg.table.setItem(rows["A1"], 8, QTableWidgetItem("n/a"))
    dlg._reject_low()
    assert _decision(dlg, rows["A3"]) == "REJECT"
    assert review[2]["review_state"] == "rejected"
    assert _decision(dlg, rows["A2"]) == "REVIEW"
    assert _decision(dlg, rows["A1"]) == "REVIEW"


@pytest.mark.parametrize("action", ["_accept_high", "_reject_low"])
def test_failure_to_record_a_decision_is_not_swallowed(preview, monkeypatch, action):
    dlg, _review = preview

    def broken(row, decision):
        raise RuntimeError("decision store failed")

    monkeypatch.setattr(dlg, "_set_decision", broken)
    with pytest.raises(RuntimeError, match="decision store failed"):
        getattr(dlg, action)()
