"""M273: the lineage of one imported DDR value - source, parsed, normalized, correction, accepted.

Contract ``import-value-lineage-v1``. It is assembled from what the import and the review queue already store
(``import_review_items``: source file, fingerprint, sheet, page and row; the original text; the normalized proposal;
the append-only decision history). It adds the one check the queue does not make: whether an **accepted** value is
**still** the stored canonical value. If the field was changed later by another route, the lineage reports
CHANGED_SINCE with both values. Nothing is repaired and nothing is written.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

CONTRACT = "import-value-lineage-v1"
STAGES = ("SOURCE", "PARSED", "NORMALIZED", "CORRECTION", "ACCEPTED")
RECORDED, NOT_RECORDED, UNREADABLE = "RECORDED", "NOT_RECORDED", "UNREADABLE"
MATCH, CHANGED_SINCE, NOT_CHECKED = "MATCH", "CHANGED_SINCE", "NOT_CHECKED"


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
        check, stored_now, expected = NOT_CHECKED, None, None
        if item.state == ACCEPTED and corrections:
            expected = corrections[-1].get("new")
            try:
                target = rsc.resolve_target(session, item)
            except rsc.CorrectionRefused as exc:
                check = f"{NOT_CHECKED}: {exc}"
            else:
                stored_now = rsc._json_value(getattr(target.record, target.column))
                check = MATCH if stored_now == expected else CHANGED_SINCE
        stages.append({"stage": "ACCEPTED", "status": item.state,
                       "detail": {"expected": expected, "stored_now": stored_now, "check": check,
                                  "resolved_at": item.resolved_at, "resolved_by": item.resolved_by}})
        return {"contract": CONTRACT, "item_id": item.id, "target_field": item.target_field, "stages": stages,
                "check": check, "expected": expected, "stored_now": stored_now}


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
    return line
