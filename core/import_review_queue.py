"""M150: build the persisted DDR review queue of one import.

Three kinds of review evidence leave an import:

* continuation outcomes (``metadata.continuation_outcomes``, see :mod:`core.ddr_continuation`) - attached,
  rejected, ignored or deferred narrative rows, linked to the saved parent activity when it exists;
* field decisions taken in the preview (``metadata.review_decisions``) - accepted, rejected, ignored or deferred
  proposals; a deferred proposal is never canonical;
* persistence reviews - rows the persistence boundary could not store (e.g. a time log without both time anchors).

Every item gets a stable, unique identity and one of :data:`core.ddr_continuation.REVIEW_STATES`.
The module is free of Qt and of the database so the queue semantics are regression-tested directly.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping, Optional

from core.ddr_continuation import (
    ACCEPTED, DEFERRED_UNRESOLVED, IGNORED, REJECTED, SAFELY_ATTACHED_CONTINUATION, VALIDATION_ERROR,
    review_state_for,
)
from core.import_quality import FINAL_REVIEW_DECISIONS, review_row_identity

PENDING_STATES = (DEFERRED_UNRESOLVED, VALIDATION_ERROR)
CLOSED_STATES = (ACCEPTED, REJECTED, IGNORED)


def _digest(prefix: str, parts: Iterable[Any]) -> str:
    key = json.dumps(list(parts), ensure_ascii=False, sort_keys=True, default=str)
    return prefix + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def _saved_parent_id(extracted: Mapping[str, Any], outcome: Mapping[str, Any]) -> Optional[int]:
    """The stored 24-hour activity that owns a continuation outcome (only a 24-hour parent has a row id)."""
    if outcome.get("collection") != "time_logs_24h":
        return None
    index = outcome.get("parent_index")
    if index is None and isinstance(outcome.get("parent"), Mapping):
        index = outcome["parent"].get("index")
    rows = extracted.get("time_logs_24h")
    if not isinstance(index, int) or not isinstance(rows, list) or not 0 <= index < len(rows):
        return None
    row = rows[index]
    saved = row.get("_saved_id") if isinstance(row, Mapping) else None
    return saved if isinstance(saved, int) else None


def build_review_queue(extracted: Mapping[str, Any], *, persistence_reviews: Iterable[Mapping] = (),
                       counted_reviews: Iterable[Mapping] = ()) -> List[Dict[str, Any]]:
    """Queue items of one import; ``counted_reviews`` are review rows the import status already counts."""
    metadata = extracted.get("metadata") if isinstance(extracted.get("metadata"), Mapping) else {}
    counted = {review_row_identity(row) for row in counted_reviews or ()
               if isinstance(row, Mapping)
               and str(row.get("decision") or "REVIEW").upper() not in FINAL_REVIEW_DECISIONS}
    queue: List[Dict[str, Any]] = []

    for outcome in metadata.get("continuation_outcomes") or ():
        if not isinstance(outcome, Mapping):
            continue
        item = dict(outcome)
        item["review_type"] = "continuation"
        item["target_field"] = ("time_log_morning.continuation" if outcome.get("collection") == "time_logs_morning"
                                else "time_log.continuation")
        item["parent_time_log_id"] = _saved_parent_id(extracted, outcome)
        item["already_counted"] = False
        queue.append(item)

    for position, payload in enumerate(metadata.get("review_decisions") or ()):
        if not isinstance(payload, Mapping):
            continue
        state = review_state_for(payload.get("decision"))
        identity = review_row_identity(payload)
        item = dict(payload)
        item["review_id"] = str(payload.get("review_id") or _digest("rv-", [identity, position]))
        item["review_type"] = str(payload.get("review_type") or "field")
        item["state"] = state
        item["text"] = payload.get("original_value", payload.get("source_value"))
        item["location"] = {"sheet": payload.get("sheet"), "row": payload.get("row"),
                            "page": payload.get("page")}
        item["already_counted"] = identity in counted
        queue.append(item)

    for position, review in enumerate(persistence_reviews or ()):
        if not isinstance(review, Mapping):
            continue
        row = review.get("source_row", review.get("row"))
        item = dict(review)
        item["review_id"] = _digest("persist-", [review.get("classification"), review.get("field"), row,
                                                 review.get("original_value"), position])
        item["review_type"] = str(review.get("classification") or "persistence")
        item["target_field"] = review.get("target_field") or review.get("field") or review.get("record_type")
        item["state"] = VALIDATION_ERROR
        item["text"] = review.get("original_value")
        item["location"] = {"sheet": review.get("sheet"), "row": row if isinstance(row, int) else None}
        item["already_counted"] = True          # the import status counts persistence reviews itself
        queue.append(item)
    return queue


def queue_summary(queue: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    """Counts shown to the user; ``pending_not_counted`` is added to the import's review count."""
    items = [item for item in queue or () if isinstance(item, Mapping)]
    pending = [item for item in items if item.get("state") in PENDING_STATES]
    return {
        "total": len(items),
        "pending": len(pending),
        "attached": sum(1 for item in items if item.get("state") == SAFELY_ATTACHED_CONTINUATION),
        "closed": sum(1 for item in items if item.get("state") in CLOSED_STATES),
        "pending_not_counted": sum(1 for item in pending if not item.get("already_counted")),
    }
