"""M147-M152: DDR continuation rows - reproduction, one contract, review states, partial import, review queue.

M147 reproduced the field report "Resolve every review row before import (34 pending)": every narrative-only
24-hour row became a ``time_log.continuation`` review at confidence 0.8 - between the auto-accept (>= 0.95) and
the reject (< 0.70) bands - so the preview could never be confirmed, and an "accepted" continuation wrote a
``continuation`` key onto an unrelated record instead of joining its parent. The synthetic reproduction below
builds the same shape (34 narrative rows after 17 timed rows); the user's own workbook is never opened.

All data are synthetic. Persistence tests use a fresh isolated database file; dialog tests use real Qt widgets.
"""
from __future__ import annotations

import copy
import json
from datetime import date, time

import pytest

from core.ddr_continuation import (
    DEFERRED_UNRESOLVED, REJECTED, REVIEW_STATES, SAFELY_ATTACHED_CONTINUATION, VALIDATION_ERROR,
    analyse_time_rows, apply_continuation_decisions, continuation_review_rows, defer_undecided_continuations,
    review_state_for,
)
from core.import_quality import (
    TimeLogValidator, apply_review_decisions, review_row_identity, unresolved_review_items,
)
from core.import_review_queue import build_review_queue, queue_summary


def _timed(hour, text, row, **extra):
    return {"time_from": f"{hour:02d}:00", "time_to": f"{hour + 1:02d}:00", "duration": 1.0,
            "main_code": "2", "sub_code": "2.1", "activity_description": text, "_source_row": row,
            "_source_sheet": "Time Log", **extra}


def _narrative(text, row, **extra):
    return {"activity_description": text, "_source_row": row, "_source_sheet": "Time Log", **extra}


def _field_report_shape():
    """17 timed activities, each followed by two narrative rows -> 34 continuation candidates."""
    rows, source_row = [], 10
    for hour in range(17):
        rows.append(_timed(hour, f"Activity {hour}", source_row))
        rows.append(_narrative(f"detail {hour}a", source_row + 1))
        rows.append(_narrative(f"detail {hour}b", source_row + 2))
        source_row += 3
    return rows


# ---- M147: reproduction ------------------------------------------------------------------------------------
def test_m147_reproduces_34_pending_continuation_reviews_with_unique_identities():
    rows = _field_report_shape()
    report = TimeLogValidator.validate_logs(rows, sheet="Time Logs 24H")
    reviews = [item.to_dict() for item in report.review.items if item.review_type == "continuation"]
    assert len(reviews) == 34
    assert len(unresolved_review_items(reviews)) == 34          # the blocking count the user saw
    assert {item["confidence"] for item in reviews} == {0.8}
    assert len({item["review_id"] for item in reviews}) == 34
    assert len({review_row_identity(item) for item in reviews}) == 34
    assert all(item["eligible"] and item["parent"]["description"].startswith("Activity") for item in reviews)
    # The false promise "will be merged" is gone; no row is reported against an invented spreadsheet row.
    assert not any("will be merged" in str(item.get("reason")) for item in reviews)
    assert {item["record_index"] for item in reviews} == {i for i in range(51) if i % 3}


def test_m147_old_accept_path_no_longer_writes_a_continuation_key_on_a_record():
    rows = _field_report_shape()
    extracted = {"time_logs_24h": rows, "metadata": {}}
    reviews = continuation_review_rows(rows)
    for item in reviews:
        item["decision"] = "ACCEPT"
    apply_review_decisions(extracted, reviews)
    assert not any("continuation" in row for row in extracted["time_logs_24h"])
    assert len(extracted["time_logs_24h"]) == 17                      # narrative rows never become time logs
    assert all(item["decision"] == "REVIEW" for item in reviews)       # ACCEPT is refused, not applied
    outcomes = extracted["metadata"]["continuation_outcomes"]
    assert {o["state"] for o in outcomes} == {DEFERRED_UNRESOLVED}
    assert [row["activity_description"] for row in extracted["time_logs_24h"]][:2] == ["Activity 0", "Activity 1"]


# ---- M148: one contract -----------------------------------------------------------------------------------
def test_m148_attach_keeps_full_text_line_breaks_lineage_and_never_invents_values():
    rows = _field_report_shape()
    before = copy.deepcopy(rows)
    extracted = {"time_logs_24h": rows, "metadata": {}}
    reviews = continuation_review_rows(rows)
    for item in reviews:
        item["decision"] = "ATTACH_CONTINUATION"
    apply_review_decisions(extracted, reviews)
    saved = extracted["time_logs_24h"]
    assert len(saved) == 17
    assert saved[0]["activity_description"] == "Activity 0\ndetail 0a\ndetail 0b"
    assert [entry["review_id"] for entry in saved[0]["_continuations"]] == [reviews[0]["review_id"],
                                                                              reviews[1]["review_id"]]
    for row, original in zip(saved, before[::3]):
        for key in ("time_from", "time_to", "duration", "main_code", "sub_code", "_source_row"):
            assert row[key] == original[key]                           # no time, code or row is invented
    assert {o["state"] for o in extracted["metadata"]["continuation_outcomes"]} == {SAFELY_ATTACHED_CONTINUATION}
    assert all(o["parent_index"] == i // 2 for i, o in enumerate(extracted["metadata"]["continuation_outcomes"]))


@pytest.mark.parametrize("second, reason", [
    (_narrative("x", 12, _source_sheet="Other"), "boundary"),
    (_narrative("x", 12, _source_table="T2"), "boundary"),
    (_narrative("x", 12, _source_page=2), "page boundary"),
    (_narrative("x", 9), "order"),
    (_narrative("Page 2 of 3", 12), "header"),
    (_narrative("Total", 12), "header"),
    (_narrative("x", None), "cannot be proven"),
    (_narrative("x", "row?"), "cannot be proven"),
])
def test_m148_boundaries_and_ambiguity_make_a_row_ineligible(second, reason):
    rows = [_timed(0, "Drill", 11, _source_page=1 if second.get("_source_page") else None), second]
    if rows[0]["_source_page"] is None:
        rows[0].pop("_source_page")
    [analysis] = [a for a in analyse_time_rows(rows) if a.kind == "continuation"]
    assert not analysis.eligible and reason in analysis.reason.lower()


def test_m148_incomplete_or_missing_parent_and_profile_rule_block_attachment():
    first_row = analyse_time_rows([_narrative("orphan", 2)])[0]
    assert first_row.kind == "continuation" and not first_row.eligible and first_row.parent_index is None
    incomplete = [_timed(0, "Drill", 2), {"duration": 2.0, "activity_description": "no anchors",
                                          "_source_row": 3, "_source_sheet": "Time Log"}, _narrative("tail", 4)]
    kinds = [a.kind for a in analyse_time_rows(incomplete)]
    assert kinds == ["timed", "incomplete", "continuation"]
    assert not analyse_time_rows(incomplete)[2].eligible
    disallowed = analyse_time_rows([_timed(0, "Drill", 2), _narrative("tail", 3)], continuation_allowed=False)
    assert not disallowed[1].eligible and "profile" in disallowed[1].reason
    # An NPT flag, a code or a depth makes a row an activity, never narrative.
    for extra in ({"is_npt": True}, {"main_code": "7"}, {"depth_to": 1200}):
        assert analyse_time_rows([_timed(0, "Drill", 2), _narrative("t", 3, **extra)])[1].kind == "incomplete"


def test_m148_repeated_identical_text_gets_distinct_identities():
    rows = [_timed(0, "Drill", 2), _narrative("same", 3), _narrative("same", 4), _timed(1, "Trip", 5),
            _narrative("same", 6)]
    ids = [p["review_id"] for p in continuation_review_rows(rows)]
    assert len(ids) == len(set(ids)) == 3
    assert ids == [p["review_id"] for p in continuation_review_rows(copy.deepcopy(rows))]   # stable


def test_m148_attach_on_ineligible_row_is_refused_and_kept_for_review():
    rows = [_timed(0, "Drill", 2), _narrative("other sheet", 3, _source_sheet="Remarks")]
    extracted = {"time_logs_24h": rows, "metadata": {}}
    [payload] = continuation_review_rows(rows)
    payload["decision"] = "ATTACH_CONTINUATION"
    apply_review_decisions(extracted, [payload])
    assert extracted["time_logs_24h"][0]["activity_description"] == "Drill"
    [outcome] = extracted["metadata"]["continuation_outcomes"]
    assert outcome["state"] == DEFERRED_UNRESOLVED and payload["decision"] == "REVIEW"
    assert "Not attachable" in payload["reason"]


def test_m148_changed_row_ownership_is_not_applied_and_application_is_idempotent():
    rows = [_timed(0, "Drill", 2), _narrative("tail", 3)]
    extracted = {"time_logs_24h": rows, "metadata": {}}
    [payload] = continuation_review_rows(rows)
    payload["decision"] = "ATTACH_CONTINUATION"
    stale = dict(payload, review_id="cont-not-the-same-row")
    apply_continuation_decisions(extracted, [stale])
    assert len(extracted["time_logs_24h"]) == 2 and stale["decision"] == "REVIEW"
    # Same id but a record index that contradicts it (a corrupted / stale decision payload): not applied.
    moved = dict(payload, record_index=payload["record_index"] + 1)
    apply_continuation_decisions(extracted, [moved])
    assert len(extracted["time_logs_24h"]) == 2 and moved["decision"] == "REVIEW"
    assert "ownership is not proven" in moved["reason"]
    apply_continuation_decisions(extracted, [payload])
    apply_continuation_decisions(extracted, [payload])                  # second application: no effect
    assert extracted["time_logs_24h"][0]["activity_description"] == "Drill\ntail"
    assert len(extracted["metadata"]["continuation_outcomes"]) == 1
    assert payload["decision"] == "ATTACH_CONTINUATION"


def test_m148_removed_rows_remap_parent_indexes_of_deferred_rows():
    rows = [_timed(0, "A", 2), _narrative("a1", 3), _timed(1, "B", 4), _narrative("b1", 5)]
    extracted = {"time_logs_24h": rows, "metadata": {}}
    outcomes = defer_undecided_continuations(extracted)
    assert [o["state"] for o in outcomes] == [DEFERRED_UNRESOLVED, DEFERRED_UNRESOLVED]
    assert [o["parent"]["index"] for o in outcomes] == [0, 1]
    assert [r["activity_description"] for r in extracted["time_logs_24h"]] == ["A", "B"]


def test_m149_states_and_decisions_map_one_to_one():
    assert set(REVIEW_STATES) == {"ACCEPTED", "REJECTED", "IGNORED", SAFELY_ATTACHED_CONTINUATION,
                                  DEFERRED_UNRESOLVED, VALIDATION_ERROR}
    assert review_state_for("ACCEPT") == "ACCEPTED" and review_state_for("CONFIRMED") == "ACCEPTED"
    assert review_state_for("REJECT") == REJECTED and review_state_for("IGNORED") == "IGNORED"
    assert review_state_for("ATTACH_CONTINUATION") == SAFELY_ATTACHED_CONTINUATION
    assert review_state_for("DEFER") == review_state_for("REVIEW") == review_state_for("?") == DEFERRED_UNRESOLVED


def test_m150_a_deferred_field_proposal_is_never_canonical_and_is_queued():
    extracted = {"time_logs_24h": [_timed(0, "Drill", 2, _source_cells={"time_log.main_code": "E2"})],
                 "metadata": {}}
    proposal = {"target_field": "time_log.main_code", "detected_table": "time_logs_24h", "row": 2,
                "sheet": "Time Log", "source_cell": "E2", "normalized_value": "2", "decision": "DEFER",
                "original_value": "2?"}
    apply_review_decisions(extracted, [proposal])
    assert "main_code" not in extracted["time_logs_24h"][0]
    queue = build_review_queue(extracted)
    assert [(q["review_type"], q["state"]) for q in queue] == [("field", DEFERRED_UNRESOLVED)]
    assert queue_summary(queue)["pending_not_counted"] == 1
    # Counted elsewhere already -> not counted twice.
    assert queue_summary(build_review_queue(extracted, counted_reviews=[proposal]))["pending_not_counted"] == 0


# ---- profile route ----------------------------------------------------------------------------------------
def test_m147_profile_route_keeps_narrative_rows_instead_of_merging_silently():
    from core.profile_import_engine import ProfileImportEngine

    engine = ProfileImportEngine(None)
    engine.cell_cache = {"Time Logs": {
        1: {1: "From", 2: "To", 3: "Hrs", 4: "Main Phase", 5: "Code", 6: "Sub", 8: "NPT", 9: "Rig Activity"},
        2: {1: "00:00", 2: "06:00", 3: 6, 4: "Drilling", 9: "Drill ahead"},
        3: {9: "to 1200 m with full returns"},
        4: {5: "7", 9: "has a code but no time"},
    }}
    logs = engine._extract_time_logs("Time Logs")
    assert [log["activity_description"] for log in logs] == [
        "Drill ahead", "to 1200 m with full returns", "has a code but no time"]
    assert logs[1]["_source_row"] == 3 and logs[1]["_source_sheet"] == "Time Logs"
    assert logs[0]["status"] == ""                                     # no status column: unknown, not "PLN"
    kinds = [a.kind for a in analyse_time_rows(logs)]
    assert kinds == ["timed", "continuation", "incomplete"]


# ---- persistence on a fresh isolated database --------------------------------------------------------------
@pytest.fixture
def db(tmp_path):
    from core.database import DatabaseManager

    manager = DatabaseManager()
    manager.db_path = str(tmp_path / "m150_review_queue.db")
    assert manager.initialize()
    yield manager
    manager.close()


def _payload(rows, **metadata):
    return {"daily_report": {"report_date": date(2026, 10, 1)}, "time_logs_24h": rows,
            "metadata": {"source_file": "synthetic.xlsx", **metadata}}


def _import(db, payload, well_id=1):
    from core.ddr_import_service import DDRImportService

    return DDRImportService(db, well_id).import_records(payload)


def test_m150_headless_import_saves_verified_rows_and_queues_continuations(db):
    from core.database import ImportReviewItem, TimeLog24H

    rows = [_timed(0, "Drill", 2), _narrative("first detail", 3), _narrative("second detail", 4),
            _timed(1, "Circulate", 5)]
    result = _import(db, _payload(rows))
    assert result["report_id"] and result["status"] == "REVIEW_REQUIRED", result
    assert result["review_queue"]["pending"] == 2 and result["review"] >= 2
    with db.session_scope() as session:
        logs = session.query(TimeLog24H).filter_by(report_id=result["report_id"]).order_by(TimeLog24H.id).all()
        assert [log.activity_description for log in logs] == ["Drill", "Circulate"]
        items = session.query(ImportReviewItem).filter_by(report_id=result["report_id"]).all()
        assert {item.state for item in items} == {DEFERRED_UNRESOLVED}
        assert {item.parent_time_log_id for item in items} == {logs[0].id}
        assert sorted(item.original_text for item in items) == ["first detail", "second detail"]
        assert all(item.eligible and item.review_id.startswith("cont-") for item in items)


def test_m150_preview_decisions_attach_and_reject_are_persisted_truthfully(db):
    from core.database import ImportReviewItem, TimeLog24H

    rows = [_timed(0, "Drill", 2), _narrative("attach me", 3), _timed(1, "Trip", 4), _narrative("noise", 5)]
    payload = _payload(rows)
    reviews = continuation_review_rows(rows)
    reviews[0]["decision"], reviews[1]["decision"] = "ATTACH_CONTINUATION", "REJECT"
    apply_review_decisions(payload, reviews)
    result = _import(db, payload)
    assert result["status"] == "ACCEPT", result
    assert result["review_queue"] == {"total": 2, "pending": 0, "attached": 1, "closed": 1,
                                      "pending_not_counted": 0}
    with db.session_scope() as session:
        logs = session.query(TimeLog24H).filter_by(report_id=result["report_id"]).order_by(TimeLog24H.id).all()
        assert [log.activity_description for log in logs] == ["Drill\nattach me", "Trip"]
        assert (logs[0].time_from, logs[0].time_to, logs[0].duration) == (time(0, 0), time(1, 0), 1.0)
        states = {item.original_text: item.state for item in session.query(ImportReviewItem).all()}
        assert states == {"attach me": SAFELY_ATTACHED_CONTINUATION, "noise": REJECTED}


def test_m149_queued_continuation_is_attached_later_with_audit_and_only_once(db):
    from core.database import AuditLog, TimeLog24H

    result = _import(db, _payload([_timed(0, "Drill", 2), _narrative("late detail", 3)]))
    [item] = db.get_import_review_items(1, report_id=result["report_id"])
    assert item["parent"]["description"] == "Drill" and item["state"] == DEFERRED_UNRESOLVED
    with pytest.raises(ValueError, match="selected well"):
        db.resolve_import_review_item(item["id"], 999, "ATTACH_CONTINUATION")
    with pytest.raises(ValueError, match="cannot be accepted"):
        db.resolve_import_review_item(item["id"], 1, "ACCEPT")
    assert db.resolve_import_review_item(item["id"], 1, "ATTACH_CONTINUATION")["state"] == \
        SAFELY_ATTACHED_CONTINUATION
    with pytest.raises(ValueError, match="already decided"):
        db.resolve_import_review_item(item["id"], 1, "REJECT")
    with db.session_scope() as session:
        assert session.get(TimeLog24H, item["parent_time_log_id"]).activity_description == "Drill\nlate detail"
        audit = session.query(AuditLog).filter_by(action="ddr_review_decision").all()
        assert len(audit) == 1
        details = json.loads(audit[0].details)
        assert details["before"] == DEFERRED_UNRESOLVED and details["parent"] == item["parent_time_log_id"]
    assert db.get_import_review_items(1, states=(DEFERRED_UNRESOLVED,)) == []


def test_m150_ineligible_and_invalid_rows_are_kept_and_can_only_be_closed(db):
    rows = [_timed(0, "Drill", 2), _narrative("other sheet", 3, _source_sheet="Remarks"),
            {"duration": 2.0, "activity_description": "no anchors", "_source_row": 4, "_source_sheet": "Time Log"}]
    result = _import(db, _payload(rows))
    items = {item["review_type"]: item for item in db.get_import_review_items(1, report_id=result["report_id"])}
    assert items["continuation"]["state"] == DEFERRED_UNRESOLVED and not items["continuation"]["eligible"]
    assert items["invalid_time_range"]["state"] == VALIDATION_ERROR
    with pytest.raises(ValueError, match="eligible continuation"):
        db.resolve_import_review_item(items["continuation"]["id"], 1, "ATTACH_CONTINUATION")
    assert db.resolve_import_review_item(items["invalid_time_range"]["id"], 1, "IGNORED")["state"] == "IGNORED"
    assert db.resolve_import_review_item(items["continuation"]["id"], 1, "DEFER")["state"] == DEFERRED_UNRESOLVED


def test_m150_saving_the_queue_twice_is_idempotent(db):
    result = _import(db, _payload([_timed(0, "Drill", 2), _narrative("tail", 3)]))
    [item] = db.get_import_review_items(1, report_id=result["report_id"])
    again = dict(item["payload"], state=DEFERRED_UNRESOLVED)
    assert db.save_import_review_items(result["report_id"], [again]) == 0
    with pytest.raises(ValueError, match="Unknown review state"):
        db.save_import_review_items(result["report_id"], [{"review_id": "x", "state": "MAYBE"}])


def test_m150_profile_disallowing_continuations_keeps_every_row_for_review(db):
    rows = [_timed(0, "Drill", 2), _narrative("tail", 3)]
    result = _import(db, _payload(rows, continuation_allowed=False))
    [item] = db.get_import_review_items(1, report_id=result["report_id"])
    assert not item["eligible"] and "profile" in item["reason"]


# ---- M151: real-Qt preview ---------------------------------------------------------------------------------
@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _preview(qapp, rows, threshold=None):
    from dialogs.excel_import_dialog import ImportPreviewDialog

    extracted = {"time_logs_24h": rows, "metadata": {}}
    reviews = [item.to_dict() for item in TimeLogValidator.validate_logs(rows).review.items]
    report = {"review": reviews, "issues": [], "errors": 0}
    if threshold is not None:
        report["profile"] = {"confidence_threshold": threshold}
    return ImportPreviewDialog("synthetic.xlsx", extracted, report), extracted


def test_m151_preview_attaches_only_eligible_rows_and_shows_the_parent(qapp):
    rows = [_timed(0, "Drill", 2), _narrative("ok", 3), _narrative("elsewhere", 4, _source_sheet="Remarks")]
    dlg, _extracted = _preview(qapp, rows)
    try:
        assert dlg.attach_eligible_continuations() == 1
        dlg.get_decisions()
        decisions = sorted(p["decision"] for p in dlg._row_payloads if p and p.get("review_type") == "continuation")
        assert decisions == ["ATTACH_CONTINUATION", "REVIEW"]
        eligible = next(p for p in dlg._row_payloads if p and p.get("eligible"))
        text = dlg.field_detail_text(eligible)
        assert "Parent activity (source row 2, 00:00-01:00): Drill" in text and "Attachable: yes" in text
        other = next(p for p in dlg._row_payloads
                     if p and p.get("review_type") == "continuation" and not p.get("eligible"))
        assert "Attachable: no - A table or sheet boundary" in dlg.field_detail_text(other)
    finally:
        dlg.deleteLater()


def test_m151_bulk_accept_never_accepts_a_continuation_even_with_a_low_threshold(qapp):
    dlg, _extracted = _preview(qapp, [_timed(0, "Drill", 2), _narrative("tail", 3)], threshold=0.5)
    try:
        dlg._accept_high()
        dlg.get_decisions()
        decisions = {p.get("review_type"): p["decision"] for p in dlg._row_payloads if p}
        assert decisions["continuation"] == "REVIEW"
        assert "ACCEPT" in decisions.values()            # the ordinary proposal above the threshold was accepted
    finally:
        dlg.deleteLater()


def test_m150_confirm_offers_partial_import_and_defers_only_on_explicit_choice(qapp, monkeypatch):
    rows = [_timed(0, "Drill", 2), _narrative("tail", 3)]
    dlg, extracted = _preview(qapp, rows)
    try:
        asked = []
        monkeypatch.setattr(dlg, "_ask_partial_import", lambda pending: asked.append(len(pending)) or False)
        dlg._confirm()
        # The continuation and the 24-hour total proposal are both undecided.
        assert asked == [2] and not dlg.confirmed                  # cancel keeps the preview open, nothing saved
        monkeypatch.setattr(dlg, "_ask_partial_import", lambda pending: True)
        dlg._confirm()
        assert dlg.confirmed and dlg.deferred_count == 2
        assert list(dlg.get_decisions().values()) == ["DEFER", "DEFER"]
        dlg.apply_review_changes(extracted)
        assert [r["activity_description"] for r in extracted["time_logs_24h"]] == ["Drill"]
        assert extracted["metadata"]["continuation_outcomes"][0]["state"] == DEFERRED_UNRESOLVED
    finally:
        dlg.deleteLater()


def test_m150_batch_summary_states_what_was_saved():
    from dialogs.excel_import_dialog import ExcelImportDialog

    assert ExcelImportDialog._saved_summary({"reimport": True}) == " - already imported, nothing new saved"
    assert ExcelImportDialog._saved_summary(
        {"report_id": 7, "review_queue": {"attached": 2, "pending": 3}}
    ) == " - report 7 saved, 2 continuation(s) attached, 3 item(s) kept for review"
    assert ExcelImportDialog._saved_summary({}) == ""


# ---- M151: review workspace (real Qt, real database) -------------------------------------------------------
def test_m151_review_workspace_filters_batch_decides_and_resumes_deferred(qapp, db):
    from PySide6.QtCore import QItemSelectionModel
    from dialogs.import_review_dialog import ALL, ImportReviewDialog, matches

    rows = [_timed(0, "Drill", 2), _narrative("attach me", 3), _narrative("wrong sheet", 4, _source_sheet="Notes"),
            {"duration": 2.0, "activity_description": "no anchors", "_source_row": 5, "_source_sheet": "Time Log"}]
    _import(db, _payload(rows))
    dlg = ImportReviewDialog(db, 1)
    try:
        assert len(dlg.visible) == 3 and "3 pending" in dlg.summary.text()
        dlg.type_filter.setCurrentText("continuation")
        assert len(dlg.visible) == 2
        dlg.text_filter.setText("attach")
        assert [item["original_text"] for item in dlg.visible] == ["attach me"]
        assert "Drill" in dlg.table.item(0, 7).text()                       # parent activity column
        dlg.text_filter.setText("")
        assert [item["original_text"] for item in dlg.eligible_visible()] == ["attach me"]
        assert dlg.decide(dlg.eligible_visible(), "ATTACH_CONTINUATION") == {"applied": 1, "refused": 0}
        dlg.type_filter.setCurrentText(ALL)
        assert len(dlg.visible) == 2                                       # the attached row left "pending"
        model = dlg.table.selectionModel()
        for row in range(dlg.table.rowCount()):
            model.select(dlg.table.model().index(row, 0),
                         QItemSelectionModel.Select | QItemSelectionModel.Rows)
        assert len(dlg.selected_items()) == 2
        counts = dlg.decide(dlg.selected_items(), "ATTACH_CONTINUATION")
        assert counts == {"applied": 0, "refused": 2}                      # neither is an eligible continuation
        assert dlg.decide(dlg.selected_items(), "REJECT") == {"applied": 2, "refused": 0}
        assert dlg.visible == []
        dlg.state_filter.setCurrentText(ALL)
        assert sorted(item["state"] for item in dlg.visible) == ["REJECTED", "REJECTED",
                                                                 SAFELY_ATTACHED_CONTINUATION]
        assert not matches({"state": "REJECTED"})                          # default filter = pending only
    finally:
        dlg.deleteLater()


def test_m151_review_workspace_never_decides_items_of_another_well(qapp, db):
    from dialogs.import_review_dialog import ImportReviewDialog

    _import(db, _payload([_timed(0, "Drill", 2), _narrative("tail", 3)]))
    [item] = db.get_import_review_items(1)
    dlg = ImportReviewDialog(db, 2)
    try:
        assert dlg.items == []
        assert dlg.decide([item], "REJECT") == {"applied": 0, "refused": 1}
        assert "selected well" in dlg.last_messages[0]
    finally:
        dlg.deleteLater()
    assert db.get_import_review_items(1)[0]["state"] == DEFERRED_UNRESOLVED


# ---- M152: the same semantics on every import route --------------------------------------------------------
def _sha(path):
    import hashlib
    from pathlib import Path

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _continuations(report):
    return [item for item in report["review"] if item.get("review_type") == "continuation"]


def test_m152_generic_excel_route_attaches_the_fixture_continuations_end_to_end(qapp, db, tmp_path):
    """Real workbook -> real pipeline -> preview decisions -> real atomic import; the source stays unchanged."""
    import shutil
    import warnings
    from pathlib import Path
    from core import ddr_import_pipeline as pipe
    from core.database import TimeLog24H
    from core.ddr_import_service import DDRImportService
    from core.import_router import route_file
    from dialogs.excel_import_dialog import has_meaningful_canonical_data

    source = tmp_path / "golden.xlsx"
    shutil.copyfile(Path(__file__).parent / "fixtures" / "synthetic_ddr_golden_a.xlsx", source)
    before = _sha(source)
    service = DDRImportService()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")              # openpyxl: "Data Validation extension is not supported"
        out = pipe.prepare_import(str(source), route=route_file, template_matcher=service._auto_match_template,
                                  extract_file=service.extract_file, meaningful=has_meaningful_canonical_data)
    assert out.import_report["pipeline_version"] == 2
    reviews = [item for item in _continuations(out.import_report) if item["detected_table"] == "time_logs_24h"]
    assert [item["parent"]["row"] for item in reviews] == [24, 27, 32]
    assert all(item["eligible"] for item in reviews)
    for item in _continuations(out.import_report):
        item["decision"] = "ATTACH_CONTINUATION"
    extracted = out.extracted
    apply_review_decisions(extracted, out.import_report["review"])
    from core.ddr_well_identity import CHOOSE_SELECTED, make_decision    # M175: explicit target decision
    extracted["metadata"]["well_identity_decision"] = make_decision(
        DDRImportService(db, 1).assess_well_identity(extracted["well_info"]), CHOOSE_SELECTED, "synthetic test")
    result = DDRImportService(db, 1).import_records(extracted)
    assert result["report_id"], result
    assert result["review_queue"]["attached"] == 4
    with db.session_scope() as session:
        texts = [row.activity_description for row in
                 session.query(TimeLog24H).filter_by(report_id=result["report_id"]).order_by(TimeLog24H.id)]
    assert texts[0].startswith("Cont. Drlg") and "\nDrlg Parameters: WOB: 5-10 klbs" in texts[0]
    assert sum("\n" in text for text in texts) == 3 and len(texts) == 7
    with db.session_scope() as session:
        from core.database import TimeLogMorning
        morning = [row.activity_description for row in session.query(TimeLogMorning).filter_by(
            report_id=result["report_id"])]
    assert sum("\n" in text for text in morning) == 1                # the morning continuation as well
    assert _sha(source) == before


def _mineru(headers, rows, continuation=True, page=2):
    from types import SimpleNamespace
    from core import ddr_import_pipeline as pipe
    from core.ddr_report_profiles import ReportProfile
    from core.mineru_engine import DocumentTable, MinerUDocument, Provenance

    document = MinerUDocument(source_file="synthetic.pdf", backend="pdf-native-fallback", method="pymupdf", tables=[
        DocumentTable(headers=headers, rows=rows, provenance=Provenance("synthetic.pdf", source_page=page),
                      name="24 hrs time log")])
    profile = ReportProfile(key="syn-m152", version=1, name="Synthetic", report_format="pdf", aliases={}, units={},
                            date_formats=(), table_rules={}, continuation=continuation, confidence_threshold=0.85)
    parsed = SimpleNamespace(document=document, success=True, diagnostics={}, error=None)
    extracted = pipe.mineru_extracted("synthetic.pdf", parsed, profile=profile)
    return extracted, pipe._validate("synthetic.pdf", extracted)


ROWS = [["00:00", "06:00", "6", "2", "Drill ahead"], ["", "", "", "", "with full returns"],
        ["06:00", "08:00", "2", "6", "POOH"]]


def test_m152_mineru_and_native_pdf_route_follow_the_same_contract_and_profile_rule():
    extracted, report = _mineru(["From", "To", "Hrs", "Code", "Rig Activity"], ROWS)
    [item] = _continuations(report)
    assert item["eligible"] and item["parent"]["description"] == "Drill ahead"
    assert item["record_index"] == 1 and extracted["metadata"]["continuation_allowed"] is True
    extracted, report = _mineru(["From", "To", "Hrs", "Code", "Rig Activity"], ROWS, continuation=False)
    [item] = _continuations(report)
    assert not item["eligible"] and "profile" in item["reason"]
    apply_review_decisions(extracted, [dict(item, decision="ATTACH_CONTINUATION")])
    assert [row.get("activity_description") for row in extracted["time_logs_24h"]] == ["Drill ahead", "POOH"]
    assert extracted["metadata"]["continuation_outcomes"][0]["state"] == DEFERRED_UNRESOLVED


def test_m152_smart_template_route_keeps_provenance_for_the_contract():
    from dialogs.smart_template_dialog import SmartTemplateDialog

    cells = {(5, 1): "00:00", (5, 2): "06:00", (5, 3): 6, (5, 4): "Drill ahead",
             (6, 4): "with full returns", (7, 1): "06:00", (7, 2): "08:00", (7, 3): 2, (7, 4): "POOH"}
    col_map = {"from": 1, "to": 2, "hrs": 3, "desc": 4}
    logs = SmartTemplateDialog._parse_time_table(object(), cells, 4, 7, col_map)
    assert [log.get("_source_row") for log in logs] == [5, 6, 7]
    assert logs[0]["status"] == ""                                     # unknown, no invented "PLN"
    [analysis] = [a for a in analyse_time_rows(logs) if a.kind == "continuation"]
    assert analysis.eligible and analysis.parent_index == 0
