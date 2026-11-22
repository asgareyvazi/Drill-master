"""M273: the lineage of one imported DDR value - source, parsed, normalized, correction, accepted.

Contract ``import-value-lineage-v1``. It is assembled from what the import and the review queue already store
(``import_review_items``: source file, fingerprint, sheet, page and row; the original text; the normalized proposal;
the append-only decision history). It adds the one check the queue does not make: whether an **accepted** value is
**still** the stored canonical value. If the field was changed later by another route, the lineage reports
CHANGED_SINCE with both values. Nothing is repaired and nothing is written.

M300: every review item gets one check outcome, never a guess:

* ``MATCH`` / ``CHANGED_SINCE``: an accepted item whose expected value is known, compared with the stored value now.
  The expected value is the latest correction; without a correction it is the value persisted when the import
  accepted the proposal (``payload.target_at_creation``, snapshotted in the import transaction, so it includes any
  conversion made at persistence); for older items without that snapshot it is the normalized proposal, but only
  when no unit conversion is declared.
* ``NOT_CHECKED`` (with the reason): accepted, but the expected value is unknown or the target cannot be resolved.
* ``UNREADABLE``: the stored payload or decision history cannot be read.
* ``NOT_APPLICABLE``: nothing was accepted (pending, rejected, ignored, continuation).

M301: :func:`imported_value_lineage` gives the same stages for an imported header value that never had a review
item, from the immutable ``ddr_import`` audit record (source snapshot with the extractor's provenance). Its identity
is stable (``iv:<report>:<field>:<fingerprint>``); no review item is created.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

CONTRACT = "import-value-lineage-v1"
STAGES = ("SOURCE", "PARSED", "NORMALIZED", "CORRECTION", "ACCEPTED")
RECORDED, NOT_RECORDED, UNREADABLE = "RECORDED", "NOT_RECORDED", "UNREADABLE"
MATCH, CHANGED_SINCE, NOT_CHECKED = "MATCH", "CHANGED_SINCE", "NOT_CHECKED"
NOT_APPLICABLE = "NOT_APPLICABLE"
CHECKS = (MATCH, CHANGED_SINCE, NOT_CHECKED, UNREADABLE, NOT_APPLICABLE)


class LineageError(LookupError):
    """The review item does not exist or belongs to another well."""


def _payload(item) -> Tuple[Dict[str, Any], bool]:
    """``(payload, readable)``: a corrupt stored payload is reported as UNREADABLE, never shown as empty."""
    if not item.payload_json:
        return {}, True
    try:
        data = json.loads(item.payload_json)
    except (TypeError, ValueError) as exc:
        return {"unreadable": str(exc)}, False
    return (data, True) if isinstance(data, dict) else ({"unreadable": "payload is not an object"}, False)


def value_lineage(db, item_id: int, well_id: int) -> Dict[str, Any]:
    """The five stages of one review item, and the stored-now check for an accepted correction."""
    from core import review_scalar_correction as rsc
    from core.database import ImportReviewItem
    from core.ddr_continuation import ACCEPTED

    with db.session_scope() as session:
        item = session.get(ImportReviewItem, item_id)
        if item is None or item.well_id != well_id:
            raise LineageError(f"review item {item_id} does not exist for well {well_id}")
        payload, readable = _payload(item)
        source = {"file": item.source_file, "fingerprint": item.source_fingerprint, "sheet": item.source_sheet,
                  "page": item.source_page, "row": item.source_row}
        has_source = any(v not in (None, "") for v in source.values())
        normalized = payload.get("normalized_value", payload.get("value"))
        history = rsc.history(item)
        corrections = [e for e in history if e.get("action") == "CORRECTED"]
        stages: List[Dict[str, Any]] = [
            {"stage": "SOURCE", "status": RECORDED if has_source else NOT_RECORDED, "detail": source},
            {"stage": "PARSED", "status": RECORDED if item.original_text not in (None, "") else NOT_RECORDED,
             "detail": {"original_text": item.original_text}},
            {"stage": "NORMALIZED",
             "status": UNREADABLE if not readable else RECORDED if normalized is not None else NOT_RECORDED,
             "detail": {"value": normalized, "reason": item.reason, "unreadable": payload.get("unreadable")}},
            {"stage": "CORRECTION", "status": f"{len(corrections)} CORRECTION(S)" if corrections else "NONE",
             "detail": {"corrections": [{"old": e.get("old"), "new": e.get("new"), "unit": e.get("unit"),
                                         "reason": e.get("reason"), "by": e.get("by"), "at": e.get("at")}
                                        for e in corrections],
                        "reopened": sum(1 for e in history if e.get("action") == "REOPENED")}},
        ]
        check, reason, stored_now, expected, basis = _check(session, rsc, item, payload, readable, history,
                                                           corrections, normalized, ACCEPTED)
        stages.append({"stage": "ACCEPTED", "status": item.state,
                       "detail": {"expected": expected, "expected_basis": basis, "stored_now": stored_now,
                                  "check": check, "reason": reason, "resolved_at": item.resolved_at,
                                  "resolved_by": item.resolved_by}})
        return {"contract": CONTRACT, "item_id": item.id, "target_field": item.target_field, "stages": stages,
                "check": check, "reason": reason, "expected": expected, "expected_basis": basis,
                "stored_now": stored_now, "identity": f"review:{item.id}"}


def _same_value(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return a == b


def _declares_conversion(payload: Dict[str, Any]) -> bool:
    source, unit = payload.get("source_unit"), payload.get("normalized_unit") or payload.get("unit")
    return bool(payload.get("conversion_rule")) or bool(source and unit and str(source) != str(unit))


def _check(session, rsc, item, payload, readable, history, corrections, normalized, accepted_state):
    """``(check, reason, stored_now, expected, basis)`` for one review item (M300)."""
    if not readable or any(e.get("action") == "UNREADABLE_HISTORY" for e in history):
        return UNREADABLE, "the stored review payload or decision history cannot be read", None, None, None
    if item.state != accepted_state:
        return NOT_APPLICABLE, f"no value was accepted (the item is {item.state})", None, None, None
    snapshot = payload.get("target_at_creation") if isinstance(payload.get("target_at_creation"), dict) else None
    if corrections:
        expected, basis = corrections[-1].get("new"), "the latest correction"
    elif snapshot is not None and snapshot.get("correctable") and "value" in snapshot:
        expected, basis = snapshot.get("value"), "the value persisted when the import accepted it"
    elif snapshot is not None and not snapshot.get("correctable"):
        return NOT_CHECKED, f"the target cannot be resolved: {snapshot.get('reason')}", None, None, None
    elif normalized is not None and not _declares_conversion(payload):
        expected, basis = normalized, "the accepted normalized value (no persisted snapshot)"
    else:
        return (NOT_CHECKED, "the accepted value is not recorded (no correction, no persisted snapshot, or a unit "
                "conversion without a snapshot)", None, None, None)
    try:
        target = rsc.resolve_target(session, item)
    except rsc.CorrectionRefused as exc:
        return NOT_CHECKED, f"the target cannot be resolved: {exc}", None, expected, basis
    stored_now = rsc._json_value(getattr(target.record, target.column))
    if _same_value(stored_now, expected):
        note = "" if expected is not None else "the accepted proposal carried no value and the field is still empty"
        return MATCH, note, stored_now, expected, basis
    return CHANGED_SINCE, "the stored value differs from the accepted value", stored_now, expected, basis


# ---- M301: imported values without a review item ---------------------------------------------------------------
def value_identity(report_id: int, target_field: str, fingerprint: str) -> str:
    """Stable identity of one imported value: the same report, field and source always give the same id."""
    return f"iv:{int(report_id)}:{target_field}:{str(fingerprint or '')[:16]}"


def _import_audit(session, report_id: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    from core.database import AuditLog

    rows = (session.query(AuditLog).filter(AuditLog.action == "ddr_import", AuditLog.entity_type == "daily_report",
                                           AuditLog.entity_id == report_id).order_by(AuditLog.id.asc()).all())
    if not rows:
        return None, "the report has no import record (entered by hand or imported before import audits)"
    try:
        data = json.loads(rows[-1].details)
    except (TypeError, ValueError) as exc:
        return None, f"the import record cannot be read: {exc}"
    return (data, None) if isinstance(data, dict) else (None, "the import record is not an object")


def _provenance_entry(metadata: Dict[str, Any], target_field: str) -> Tuple[Optional[Dict[str, Any]], str]:
    excel = metadata.get("field_provenance")
    if isinstance(excel, dict) and isinstance(excel.get(target_field), dict):
        return excel[target_field], "excel"
    entries = [e for e in metadata.get("mineru_provenance") or () if isinstance(e, dict)
               and e.get("canonical_field") == target_field]
    if len(entries) == 1:
        return entries[0], "pdf"
    if len(entries) > 1:
        return {"conflict": len(entries)}, "pdf"
    return None, ""


def imported_value_lineage(db, report_id: int, field: str) -> Dict[str, Any]:
    """Read-only lineage of one imported numeric header value (``core.ddr_value_states.FIELDS``) - M301."""
    from core import ddr_value_states as vs
    from core.database import AuditLog, DailyReport, ImportReviewItem

    if field not in vs.FIELDS:
        raise LineageError(f"{field!r} is not a numeric DDR header field")
    target_field = f"daily_report.{field}"
    with db.session_scope() as session:
        report = session.get(DailyReport, report_id)
        if report is None:
            raise LineageError(f"daily report {report_id} does not exist")
        stored_now = getattr(report, field)
        review = (session.query(ImportReviewItem.id).filter(ImportReviewItem.report_id == report_id,
                                                            ImportReviewItem.target_field == target_field)
                  .order_by(ImportReviewItem.id.desc()).first())
        later = [{"at": row.timestamp, "by": row.username, "details": row.details} for row in
                 session.query(AuditLog).filter(AuditLog.entity_type == "daily_reports",
                                                AuditLog.entity_id == report_id,
                                                AuditLog.entity_name == vs.FIELDS[field],
                                                AuditLog.action == vs.AUTHORED_AUDIT_ACTION)
                 .order_by(AuditLog.id.asc()).all()]
        audit, problem = _import_audit(session, report_id)
    base = {"contract": CONTRACT, "report_id": report_id, "target_field": target_field, "stored_now": stored_now,
            "review_item_id": review[0] if review else None, "later_changes": later}
    if audit is None:
        return {**base, "identity": None, "stages": [], "check": NOT_CHECKED if "cannot" not in problem
                else UNREADABLE, "reason": problem, "expected": None, "expected_basis": None}
    fingerprint = str(audit.get("fingerprint") or "")
    source = audit.get("source") if isinstance(audit.get("source"), dict) else {}
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    entry, route = _provenance_entry(metadata, target_field)
    identity = value_identity(report_id, target_field, fingerprint)
    if entry is None or "conflict" in entry:
        reason = ("the import kept no provenance for this field" if entry is None
                  else f"{entry['conflict']} different source cells were recorded for this field")
        return {**base, "identity": identity, "stages": [], "check": NOT_CHECKED, "reason": reason,
                "expected": None, "expected_basis": None}
    original, normalized = entry.get("original_value"), entry.get("normalized_value")
    stages = [
        {"stage": "SOURCE", "status": RECORDED, "detail": {
            "file": entry.get("source_file") or source.get("metadata", {}).get("source_file"), "route": route,
            "sheet": entry.get("source_sheet"), "cell": entry.get("source_cell"), "page": entry.get("source_page"),
            "row": entry.get("source_row"), "column": entry.get("source_column"), "fingerprint": fingerprint}},
        {"stage": "PARSED", "status": RECORDED if original not in (None, "") else NOT_RECORDED,
         "detail": {"original_text": original}},
        {"stage": "NORMALIZED", "status": RECORDED if normalized is not None else NOT_RECORDED,
         "detail": {"value": normalized, "method": entry.get("extraction_method")}},
        {"stage": "CORRECTION", "status": "NONE", "detail": {"corrections": [], "later_changes": later}},
    ]
    if review:
        check, reason, expected, basis = (NOT_APPLICABLE, f"this value has review item {review[0]}; its lineage is "
                                          "the review item's lineage", None, None)
    elif normalized is None:
        check, reason, expected, basis = (NOT_APPLICABLE, "no value was imported for this field", None, None)
    elif _declares_conversion(entry):
        check, reason, expected, basis = (NOT_CHECKED, "a unit conversion was applied and the persisted value was "
                                          "not recorded", None, None)
    else:
        expected, basis = normalized, "the normalized value the import stored (no review item)"
        check = MATCH if _same_value(stored_now, expected) else CHANGED_SINCE
        reason = "" if check == MATCH else "the stored value differs from the imported value" + (
            " (changed by a typed entry; see later changes)" if later else "")
    stages.append({"stage": "ACCEPTED", "status": "IMPORTED_WITHOUT_REVIEW" if not review else "SEE_REVIEW_ITEM",
                   "detail": {"expected": expected, "expected_basis": basis, "stored_now": stored_now,
                              "check": check, "reason": reason}})
    return {**base, "identity": identity, "stages": stages, "check": check, "reason": reason, "expected": expected,
            "expected_basis": basis}


def summary_line(lineage: Optional[Dict[str, Any]]) -> str:
    """One line for the review dialog: each stage's status, then the stored-now check."""
    if not lineage:
        return ""
    parts = [f"{s['stage']} {s['status']}" for s in lineage["stages"]]
    line = "Lineage: " + " → ".join(parts)
    if lineage["check"] == MATCH:
        line += f" | stored now {lineage['stored_now']!r} = accepted value: MATCH"
    elif lineage["check"] == CHANGED_SINCE:
        line += (f" | CHANGED SINCE ACCEPTANCE: stored now {lineage['stored_now']!r}, "
                 f"accepted {lineage['expected']!r}")
    elif lineage.get("reason"):
        line += f" | {lineage['check']}: {lineage['reason']}"
    return line
