"""M239: tests written for the survivors of the new mutation catalogue ``tools/quality/mutation_m231_m260.py``.

The first run of that catalogue (tree ``4df5c01``) left five realistic defects alive: an absent MSE headline
result stored as 0 psi, and four review-queue defects (persistence reviews and final decisions counted wrongly,
a negative or morning-report continuation linked to the wrong 24-hour activity). Pure functions, no Qt, no
database; SYNTHETIC values only.
"""
import math

from core.ddr_continuation import DEFERRED_UNRESOLVED, VALIDATION_ERROR
from core.engineering.mse_persistence import SUMMARY_KEYS, result_summary
from core.import_review_queue import build_review_queue, queue_summary


# ---- MSE: an unknown headline result stays unknown ------------------------------------------------------------
def test_absent_or_non_finite_mse_results_are_stored_as_unknown_not_zero():
    assert result_summary({}) == {key: None for key in SUMMARY_KEYS}
    summary = result_summary({"mse_psi": None, "axial_term_psi": math.nan, "rotary_term_psi": math.inf,
                              "bit_area_in2": 0.0})
    assert summary == {"mse_psi": None, "axial_term_psi": None, "rotary_term_psi": None, "bit_area_in2": 0.0}


# ---- review queue: counting ------------------------------------------------------------------------------------
def test_persistence_reviews_are_already_counted_by_the_import_status():
    queue = build_review_queue({}, persistence_reviews=[
        {"classification": "time_log_without_anchors", "field": "time_from", "source_row": 12, "sheet": "Ops"}])
    assert len(queue) == 1
    item = queue[0]
    assert item["state"] == VALIDATION_ERROR and item["already_counted"] is True
    assert queue_summary(queue) == {"total": 1, "pending": 1, "attached": 0, "closed": 0, "pending_not_counted": 0}


def test_a_counted_row_with_a_final_decision_does_not_hide_a_pending_proposal():
    proposal = {"sheet": "Ops", "row": 7, "field": "mud_weight", "decision": "REVIEW", "original_value": "10,2"}
    final = dict(proposal, decision="ACCEPT")
    pending = dict(proposal, decision="REVIEW")
    extracted = {"metadata": {"review_decisions": [proposal]}}
    assert build_review_queue(extracted, counted_reviews=[pending])[0]["already_counted"] is True
    item = build_review_queue(extracted, counted_reviews=[final])[0]
    assert item["state"] == DEFERRED_UNRESOLVED and item["already_counted"] is False
    assert queue_summary([item])["pending_not_counted"] == 1


# ---- review queue: continuation lineage ------------------------------------------------------------------------
def _extracted(outcome):
    return {"time_logs_24h": [{"_saved_id": 101}, {"_saved_id": 102}], "metadata": {"continuation_outcomes": [outcome]}}


def test_a_continuation_is_linked_only_to_the_24_hour_row_it_names():
    good = build_review_queue(_extracted({"collection": "time_logs_24h", "parent_index": 1}))[0]
    assert good["parent_time_log_id"] == 102 and good["target_field"] == "time_log.continuation"


def test_a_negative_parent_index_links_no_activity():
    item = build_review_queue(_extracted({"collection": "time_logs_24h", "parent_index": -1}))[0]
    assert item["parent_time_log_id"] is None


def test_a_morning_report_continuation_is_never_linked_to_a_24_hour_row():
    item = build_review_queue(_extracted({"collection": "time_logs_morning", "parent_index": 0}))[0]
    assert item["target_field"] == "time_log_morning.continuation"
    assert item["parent_time_log_id"] is None
