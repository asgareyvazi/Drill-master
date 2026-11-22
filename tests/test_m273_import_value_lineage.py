"""M273: lineage of one imported DDR value - source, parsed, normalized, correction, accepted - over a real import.

Uses the M173 fixture: the SYNTHETIC golden workbook goes through the real pipeline, with every review row
deferred. The lineage is read-only. Its one new check is whether an accepted value is still the stored value.
"""
from __future__ import annotations

import pytest

from core import import_value_lineage as ivl
from core.ddr_continuation import ACCEPTED, DEFERRED_UNRESOLVED
from core.review_scalar_correction import apply_correction, preview_correction
from test_m173_scalar_correction import FIXTURE, imported  # noqa: F401  (fixture reused)


def _set_oil(db, report_id, value):
    from core.database import MudReport
    with db.session_scope() as session:
        session.query(MudReport).filter_by(report_id=report_id).one().oil_percent = value


def _correct(db, well, item_id, raw="5"):
    preview = preview_correction(db, item_id, well, raw)
    return apply_correction(db, item_id, well, raw, reason="value read from the SYN mud sheet", confirmed=True,
                            token=preview["token"])


def test_an_open_item_shows_source_parsed_normalized_and_no_acceptance(imported):  # noqa: F811
    db, (well, _other), _report_id, items = imported
    item = items["mud_report.oil_percent"]
    lineage = ivl.value_lineage(db, item["id"], well)
    assert [s["stage"] for s in lineage["stages"]] == list(ivl.STAGES)
    source, parsed, _normalized, correction, accepted = lineage["stages"]
    assert source["status"] == ivl.RECORDED and source["detail"]["sheet"] == item["source_sheet"]
    assert source["detail"]["file"] == item["source_file"]
    assert (parsed["status"], parsed["detail"]["original_text"]) == (ivl.RECORDED, "5")
    assert correction["status"] == "NONE"
    # M300: nothing accepted -> NOT_APPLICABLE (was NOT_CHECKED under M273), with the reason.
    assert accepted["status"] == DEFERRED_UNRESOLVED and lineage["check"] == ivl.NOT_APPLICABLE
    assert lineage["reason"] == f"no value was accepted (the item is {DEFERRED_UNRESOLVED})"


def test_an_accepted_correction_still_stored_is_a_match(imported):  # noqa: F811
    db, (well, _other), _report_id, items = imported
    item = items["mud_report.oil_percent"]
    _correct(db, well, item["id"])
    lineage = ivl.value_lineage(db, item["id"], well)
    correction, accepted = lineage["stages"][3], lineage["stages"][4]
    assert correction["status"] == "1 CORRECTION(S)"
    assert correction["detail"]["corrections"][0]["new"] == 5.0
    assert correction["detail"]["corrections"][0]["reason"] == "value read from the SYN mud sheet"
    assert accepted["status"] == ACCEPTED
    assert (lineage["check"], lineage["expected"], lineage["stored_now"]) == (ivl.MATCH, 5.0, 5.0)
    assert "MATCH" in ivl.summary_line(lineage)


def test_a_value_changed_after_acceptance_is_reported_not_repaired(imported):  # noqa: F811
    db, (well, _other), report_id, items = imported
    item = items["mud_report.oil_percent"]
    _correct(db, well, item["id"])
    _set_oil(db, report_id, 7.0)                              # another route edits the field later
    lineage = ivl.value_lineage(db, item["id"], well)
    assert (lineage["check"], lineage["expected"], lineage["stored_now"]) == (ivl.CHANGED_SINCE, 5.0, 7.0)
    assert "CHANGED SINCE ACCEPTANCE" in ivl.summary_line(lineage)
    again = ivl.value_lineage(db, item["id"], well)            # read-only: nothing was put back
    assert again["stored_now"] == 7.0 and again["stages"][4]["status"] == ACCEPTED


def test_another_wells_item_is_refused(imported):  # noqa: F811
    db, (well, other), _report_id, items = imported
    with pytest.raises(ivl.LineageError):
        ivl.value_lineage(db, items["mud_report.oil_percent"]["id"], other)
    with pytest.raises(ivl.LineageError):
        ivl.value_lineage(db, 987654, well)


def test_the_review_dialog_shows_the_lineage_of_the_selected_item(imported):  # noqa: F811
    from PySide6.QtWidgets import QApplication

    from dialogs.import_review_dialog import ALL, ImportReviewDialog

    db, (well, _other), _report_id, items = imported
    item = items["mud_report.oil_percent"]
    _correct(db, well, item["id"])
    app = QApplication.instance() or QApplication([])
    dialog = ImportReviewDialog(db, well)
    try:
        dialog.state_filter.setCurrentIndex(dialog.state_filter.findText(ALL))
        row = next(i for i, shown in enumerate(dialog.visible) if shown["id"] == item["id"])
        dialog.table.selectRow(row)
        text = dialog.detail.text()
        assert "Lineage: SOURCE RECORDED → PARSED RECORDED" in text
        assert "ACCEPTED ACCEPTED" in text and "MATCH" in text
    finally:
        dialog.deleteLater()
        del app


def test_fixture_is_the_synthetic_golden_workbook():
    assert FIXTURE.name.endswith(".xlsx")


def test_reopened_item_is_not_checked_and_the_latest_correction_is_the_expected_value(imported):  # noqa: F811
    from core.review_scalar_correction import reopen_item

    db, (well, _other), _report_id, items = imported
    item = items["mud_report.oil_percent"]
    _correct(db, well, item["id"], "5")
    reopen_item(db, item["id"], well, "SYN: value re-read")
    reopened = ivl.value_lineage(db, item["id"], well)
    # M300: a reopened item has no accepted value -> NOT_APPLICABLE (was NOT_CHECKED under M273).
    assert reopened["stages"][4]["status"] == DEFERRED_UNRESOLVED and reopened["check"] == ivl.NOT_APPLICABLE
    assert reopened["stages"][3]["detail"]["reopened"] == 1
    _correct(db, well, item["id"], "6")
    lineage = ivl.value_lineage(db, item["id"], well)
    assert lineage["stages"][3]["status"] == "2 CORRECTION(S)"
    assert (lineage["check"], lineage["expected"], lineage["stored_now"]) == (ivl.MATCH, 6.0, 6.0)


def test_a_corrupt_stored_payload_is_reported_unreadable_not_empty(imported):  # noqa: F811
    from core.database import ImportReviewItem

    db, (well, _other), _report_id, items = imported
    item_id = items["mud_report.oil_percent"]["id"]
    with db.session_scope() as session:
        session.get(ImportReviewItem, item_id).payload_json = "{not json"
    normalized = ivl.value_lineage(db, item_id, well)["stages"][2]
    assert normalized["status"] == ivl.UNREADABLE and normalized["detail"]["unreadable"]
