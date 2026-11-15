"""M215: adversarial checks of the DDR scalar correction (``ddr-scalar-correction-v1``) on a real imported report.

Concurrency (two operators applying the same previewed correction), a report that changed or moved after the
preview, a target record deleted after the preview, a token from before a reopen, identity columns, and a foreign
well at apply time. Every refusal leaves the item open and the canonical value unchanged.
"""
from __future__ import annotations

import threading

import pytest

from core import review_scalar_correction as rsc
from core.ddr_continuation import ACCEPTED, DEFERRED_UNRESOLVED
from tests.test_m173_scalar_correction import _item, _mud, imported  # noqa: F401  (fixture)


def test_two_operators_applying_the_same_preview_give_exactly_one_correction(imported, monkeypatch):  # noqa: F811
    db, (well, _), report_id, items = imported
    oil = items["mud_report.oil_percent"]
    token = rsc.preview_correction(db, oil["id"], well, "5")["token"]
    paused, resume = threading.Event(), threading.Event()
    original = rsc.resolve_target

    def slow_resolve(session, item):
        target = original(session, item)
        if threading.current_thread().name == "operator-A":
            paused.set()
            resume.wait(2.0)                # B runs here; with the claim B waits for A's transaction instead
        return target

    monkeypatch.setattr(rsc, "resolve_target", slow_resolve)
    outcome = {}

    def operator(name, value):
        try:
            outcome[name] = rsc.apply_correction(db, oil["id"], well, value, reason=name, confirmed=True,
                                                 token=token)["new"]
        except Exception as exc:          # a refusal or "database is locked" - either way nothing was written
            outcome[name] = exc

    a = threading.Thread(target=operator, args=("A", "5"), name="operator-A")
    a.start()
    assert paused.wait(10)
    b = threading.Thread(target=operator, args=("B", "7"), name="operator-B")
    b.start()
    b.join(1.0)
    resume.set()
    a.join(60)
    b.join(60)
    assert outcome["A"] == 5.0, outcome
    assert isinstance(outcome["B"], Exception), outcome
    history = _item(db, well, oil["id"])["decision_history"]
    assert [h["action"] for h in history] == ["CORRECTED"] and history[0]["new"] == 5.0
    assert _mud(db, report_id, "oil_percent") == 5.0


def test_target_record_deleted_after_the_preview_is_refused(imported):  # noqa: F811
    from core.database import MudReport
    db, (well, _), report_id, items = imported
    oil = items["mud_report.oil_percent"]
    token = rsc.preview_correction(db, oil["id"], well, "5")["token"]
    with db.session_scope() as session:
        session.query(MudReport).filter_by(report_id=report_id).delete()
    with pytest.raises(rsc.CorrectionRefused, match="no mud_reports record"):
        rsc.apply_correction(db, oil["id"], well, "5", reason="r", confirmed=True, token=token)
    assert _item(db, well, oil["id"])["state"] == DEFERRED_UNRESOLVED


def _move_report(db, report_id, well_id):
    """A raw writer moves the report (the ORM ownership listener would refuse it - this is the adversarial case)."""
    import sqlite3
    with sqlite3.connect(db.db_path) as connection:
        connection.execute("UPDATE daily_reports SET well_id = ? WHERE id = ?", (well_id, report_id))


def test_a_report_moved_to_another_well_after_the_preview_is_refused(imported):  # noqa: F811
    db, (well, other), report_id, items = imported
    oil = items["mud_report.oil_percent"]
    token = rsc.preview_correction(db, oil["id"], well, "5")["token"]
    _move_report(db, report_id, other)
    with pytest.raises(rsc.CorrectionRefused, match="no longer belongs to its well"):
        rsc.apply_correction(db, oil["id"], well, "5", reason="r", confirmed=True, token=token)
    with pytest.raises(rsc.CorrectionRefused, match="selected well"):
        rsc.apply_correction(db, oil["id"], other, "5", reason="r", confirmed=True, token=token)
    _move_report(db, report_id, well)
    assert _mud(db, report_id, "oil_percent") is None and _item(db, well, oil["id"])["state"] == DEFERRED_UNRESOLVED


def test_a_changed_report_value_and_a_token_from_before_a_reopen_are_refused(imported):  # noqa: F811
    from core.database import MudReport
    db, (well, _), report_id, items = imported
    oil = items["mud_report.oil_percent"]
    old_token = rsc.preview_correction(db, oil["id"], well, "5")["token"]
    done = rsc.preview_correction(db, oil["id"], well, "5")["token"]
    rsc.apply_correction(db, oil["id"], well, "5", reason="first", confirmed=True, token=done)
    rsc.reopen_item(db, oil["id"], well, "re-check")
    with pytest.raises(rsc.CorrectionRefused, match="preview again"):
        rsc.apply_correction(db, oil["id"], well, "6", reason="stale", confirmed=True, token=old_token)
    with db.session_scope() as session:                         # the report was edited in the Mud tab
        session.query(MudReport).filter_by(report_id=report_id).one().oil_percent = 4.0
    fresh = rsc.preview_correction(db, oil["id"], well, "6")
    assert fresh["conflict"] and fresh["current_value"] == 4.0
    with pytest.raises(rsc.CorrectionRefused, match="changed since"):
        rsc.apply_correction(db, oil["id"], well, "6", reason="r", confirmed=True, token=fresh["token"])
    assert _mud(db, report_id, "oil_percent") == 4.0


@pytest.mark.parametrize("field", ["daily_report.report_date", "daily_report.report_number", "well_info.name",
                                   "well_info.code", "mud_report.report_id", "daily_report.well_id"])
def test_identity_columns_are_never_corrected(imported, field):  # noqa: F811
    from core.database import ImportReviewItem
    db, (well, _), report_id, items = imported
    oil = items["mud_report.oil_percent"]
    with db.session_scope() as session:
        session.get(ImportReviewItem, oil["id"]).target_field = field
    with pytest.raises(rsc.CorrectionRefused, match="identity column"):
        rsc.preview_correction(db, oil["id"], well, "x")
    with pytest.raises(rsc.CorrectionRefused, match="identity column"):
        rsc.apply_correction(db, oil["id"], well, "x", reason="r", confirmed=True, token="t")
    assert _item(db, well, oil["id"])["state"] == DEFERRED_UNRESOLVED


def test_after_the_claim_a_second_apply_sees_the_decision(imported):  # noqa: F811
    db, (well, _), _report_id, items = imported
    kcl = items["mud_report.kcl"]
    token = rsc.preview_correction(db, kcl["id"], well, "3")["token"]
    assert rsc.apply_correction(db, kcl["id"], well, "3", reason="r", confirmed=True, token=token)["state"] == ACCEPTED
    with pytest.raises(rsc.CorrectionRefused, match="already decided"):
        rsc.apply_correction(db, kcl["id"], well, "3", reason="r", confirmed=True, token=token)


def test_two_mud_records_on_the_report_make_the_target_ambiguous(imported):  # noqa: F811
    from core.database import MudReport
    db, (well, _), report_id, items = imported
    oil = items["mud_report.oil_percent"]
    with db.session_scope() as session:
        first = session.query(MudReport).filter_by(report_id=report_id).one()
        session.add(MudReport(well_id=well, report_id=report_id, report_date=first.report_date, oil_percent=9.0))
    with pytest.raises(rsc.CorrectionRefused, match="ambiguous"):
        rsc.preview_correction(db, oil["id"], well, "5")
    assert _item(db, well, oil["id"])["state"] == DEFERRED_UNRESOLVED


def test_an_audit_failure_leaves_no_partial_correction(imported, monkeypatch):  # noqa: F811
    db, (well, _), report_id, items = imported
    oil = items["mud_report.oil_percent"]
    before_value = _mud(db, report_id, "oil_percent")
    token = rsc.preview_correction(db, oil["id"], well, "5")["token"]

    def failing_audit(*_a, **_k):
        raise RuntimeError("SYNTHETIC audit store failure")

    monkeypatch.setattr(db, "_add_mandatory_audit", failing_audit)
    with pytest.raises(RuntimeError, match="SYNTHETIC"):
        rsc.apply_correction(db, oil["id"], well, "5", reason="r", confirmed=True, token=token)
    item = _item(db, well, oil["id"])
    assert item["state"] == DEFERRED_UNRESOLVED and item["decision_history"] in (None, [])
    assert _mud(db, report_id, "oil_percent") == before_value


def test_an_undecided_item_cannot_be_reopened(imported):  # noqa: F811
    db, (well, _), _report_id, items = imported
    oil = items["mud_report.oil_percent"]
    with pytest.raises(rsc.CorrectionRefused, match="Only an accepted, rejected or ignored item"):
        rsc.reopen_item(db, oil["id"], well, "no decision to reopen")
    assert _item(db, well, oil["id"])["state"] == DEFERRED_UNRESOLVED


def _race(pause_in, operator_a, operator_b):
    """A pauses where ``pause_in`` is reached in thread A; B decides meanwhile; returns both outcomes.

    With the M215 claim A holds the write lock while paused, so B waits and then reads A's decision (or gives up
    on the lock); without it B decides on the same open item and both decisions are written.
    """
    paused, resume, outcome = threading.Event(), threading.Event(), {}

    def hook():
        if threading.current_thread().name == "operator-A":
            paused.set()
            resume.wait(2.0)

    def run(name, call):
        try:
            outcome[name] = call()
        except Exception as exc:          # a refusal or "database is locked" - either way nothing was written
            outcome[name] = exc

    pause_in(hook)
    a = threading.Thread(target=run, args=("A", operator_a), name="operator-A")
    a.start()
    assert paused.wait(10)
    b = threading.Thread(target=run, args=("B", operator_b), name="operator-B")
    b.start()
    b.join(1.0)
    resume.set()
    a.join(60)
    b.join(60)
    return outcome


def test_two_operators_resolving_the_same_queue_item_give_exactly_one_decision(imported, monkeypatch):  # noqa: F811
    from core import ddr_continuation
    db, (well, _), report_id, _items = imported
    item = next(i for i in db.get_import_review_items(well) if i["review_type"] == "continuation" and i["eligible"]
                and i.get("detected_table", "time_logs_24h") == "time_logs_24h")
    original = ddr_continuation.attach_text

    def pause_in(hook):
        def slow_attach(*args, **kwargs):
            hook()                                  # A has read the item as open
            return original(*args, **kwargs)
        monkeypatch.setattr(ddr_continuation, "attach_text", slow_attach)

    outcome = _race(pause_in, lambda: db.resolve_import_review_item(item["id"], well, "ATTACH_CONTINUATION"),
                    lambda: db.resolve_import_review_item(item["id"], well, "REJECT"))
    assert not isinstance(outcome["A"], Exception), outcome
    assert isinstance(outcome["B"], Exception), outcome
    history = _item(db, well, item["id"])["decision_history"]
    assert len(history) == 1, history


def test_two_operators_reopening_the_same_item_give_exactly_one_reopen(imported, monkeypatch):  # noqa: F811
    db, (well, _), report_id, items = imported
    oil = items["mud_report.oil_percent"]
    db.resolve_import_review_item(oil["id"], well, "REJECT")
    original = rsc._item

    def pause_in(hook):
        def slow_item(session, item_id, well_id):
            found = original(session, item_id, well_id)
            hook()                                  # A has read the item as decided
            return found
        monkeypatch.setattr(rsc, "_item", slow_item)

    outcome = _race(pause_in, lambda: rsc.reopen_item(db, oil["id"], well, "A reopens"),
                    lambda: rsc.reopen_item(db, oil["id"], well, "B reopens"))
    assert not isinstance(outcome["A"], Exception), outcome
    assert isinstance(outcome["B"], Exception), outcome
    history = _item(db, well, oil["id"])["decision_history"]
    assert [h["action"] for h in history].count("REOPENED") == 1, history
    assert _item(db, well, oil["id"])["state"] == DEFERRED_UNRESOLVED
