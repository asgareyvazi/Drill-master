"""One continuation contract for every DDR import route (M148).

A *continuation* is narrative text that belongs to another activity row: a source row that carries an
activity description and nothing else (no From/To, no duration, no code, no phase, no NPT mark). It is never a
separate timed operation, and no time, duration, code, NPT class or depth is ever invented for it.

The contract only *proposes* a parent. A row is ELIGIBLE for attachment only when all of these hold:

1. it is in the same extracted report (one ``extracted`` mapping is one report);
2. it is in the same table/section as the parent (same collection, sheet, page and table identity);
3. the source order is preserved (source rows strictly increase along the chain, when they are known);
4. the preceding anchor row is a timed activity (both From and To parse);
5. there is exactly one candidate parent - the run of narrative rows after one timed row;
6. no page, table or report boundary lies between parent and row;
7. the report profile permits continuation (``ReportProfile.continuation``);
8. no competing candidate exists (a preceding row that is itself incomplete makes the parent ambiguous);
9. the text is kept in full (attachment appends it with a line break, nothing is trimmed away);
10. the source location and lineage stay recorded on the parent (``_continuations``) and on the review item.

An eligible row is attached only by an explicit operator decision (``ATTACH_CONTINUATION``); it is never
auto-accepted. Everything else stays visible for review with the reason it is not eligible.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

CONTINUATION_CONTRACT_VERSION = "ddr-continuation-v1"

# Review decisions (operator vocabulary) and the persisted review states (M149).
ATTACH_CONTINUATION = "ATTACH_CONTINUATION"
DEFER = "DEFER"

ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"
IGNORED = "IGNORED"
SAFELY_ATTACHED_CONTINUATION = "SAFELY_ATTACHED_CONTINUATION"
DEFERRED_UNRESOLVED = "DEFERRED_UNRESOLVED"
VALIDATION_ERROR = "VALIDATION_ERROR"
REVIEW_STATES = (ACCEPTED, REJECTED, IGNORED, SAFELY_ATTACHED_CONTINUATION, DEFERRED_UNRESOLVED, VALIDATION_ERROR)

_DECISION_STATE = {
    "ACCEPT": ACCEPTED, "CONFIRMED": ACCEPTED,
    "REJECT": REJECTED,
    "IGNORED": IGNORED, "IGNORE": IGNORED,
    ATTACH_CONTINUATION: SAFELY_ATTACHED_CONTINUATION,
    DEFER: DEFERRED_UNRESOLVED, "REVIEW": DEFERRED_UNRESOLVED, "": DEFERRED_UNRESOLVED,
}


def review_state_for(decision: Any) -> str:
    """Map an operator decision to a persisted review state; anything unknown stays unresolved."""
    return _DECISION_STATE.get(str(decision or "").strip().upper(), DEFERRED_UNRESOLVED)


# Fields whose presence means the row is (part of) an activity of its own, not narrative.
ACTIVITY_FIELDS = ("time_from", "time_to", "duration", "main_code", "sub_code", "main_phase", "npt_category",
                   "depth_from", "depth_to", "md")
DESCRIPTION_FIELD = "activity_description"

# Text that is a repeated table header, a page footer or a total line - never narrative.
_HEADER_FOOTER = re.compile(
    r"^\s*(?:(?:from|to|hrs?|hours|duration|code|sub\s*code|phase|description|activity|status)\b[\s:/|.-]*){2,}$"
    r"|^\s*page\s+\d+(?:\s*(?:of|/)\s*\d+)?\s*$|^\s*(?:total|sub[\s-]?total)\b",
    re.IGNORECASE,
)

ELIGIBLE = "eligible"
NOT_NARRATIVE = "not-narrative"


@dataclass
class RowAnalysis:
    """What the contract decided about one source row of a time-log collection."""
    index: int
    kind: str                      # "timed" | "continuation" | "incomplete"
    review_id: str = ""
    eligible: bool = False
    parent_index: Optional[int] = None
    reason: str = ""
    text: str = ""
    location: Dict[str, Any] = field(default_factory=dict)

    def parent_payload(self, rows: Sequence[Mapping]) -> Optional[Dict[str, Any]]:
        if self.parent_index is None:
            return None
        parent = rows[self.parent_index]
        return {"index": self.parent_index, "row": parent.get("_source_row"),
                "time_from": _text(parent.get("time_from")), "time_to": _text(parent.get("time_to")),
                "description": _text(parent.get(DESCRIPTION_FIELD))}


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or value is False


def _time_ok(value: Any) -> bool:
    from core.value_normalizer import ValueNormalizer
    return not _blank(value) and ValueNormalizer.to_time(value) is not None


def source_location(row: Mapping, collection: str) -> Dict[str, Any]:
    """Sheet / page / table / row of a record, from whatever provenance its route attached."""
    location = dict(row.get("_source_location") or {}) if isinstance(row.get("_source_location"), Mapping) else {}
    page = row.get("_source_page", location.get("page"))
    if page in (None, ""):
        cells = row.get("_source_cells")
        if isinstance(cells, Mapping):
            pages = {cell.get("page") for cell in cells.values() if isinstance(cell, Mapping) and cell.get("page")}
            page = pages.pop() if len(pages) == 1 else None
    return {
        "collection": collection,
        "file": _text(row.get("_source_file") or location.get("file")),
        "sheet": _text(row.get("_source_sheet") or location.get("sheet")),
        "page": page,
        "table": _text(row.get("_source_table") or location.get("table")),
        "row": row.get("_source_row", location.get("row", row.get("source_row"))),
    }


def _group(location: Mapping) -> tuple:
    return (location.get("collection"), location.get("file"), location.get("sheet"), location.get("table"))


def review_id_for(location: Mapping, index: int, text: str) -> str:
    """Stable identity of one proposal: location AND position AND text, so repeated text is never ambiguous."""
    key = json.dumps([CONTINUATION_CONTRACT_VERSION, location.get("collection"), location.get("file"),
                      location.get("sheet"), location.get("page"), location.get("table"), location.get("row"),
                      index, text], ensure_ascii=False, default=str)
    return "cont-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def is_narrative_only(row: Mapping) -> bool:
    """Only a description: every activity field is blank (an NPT flag alone also disqualifies)."""
    if _blank(row.get(DESCRIPTION_FIELD)):
        return False
    if row.get("is_npt") is True:
        return False
    return all(_blank(row.get(name)) for name in ACTIVITY_FIELDS)


def analyse_time_rows(rows: Sequence[Mapping], *, collection: str = "time_logs_24h",
                      continuation_allowed: bool = True) -> List[RowAnalysis]:
    """Classify every row in source order; propose a parent only when the ten conditions hold."""
    rows = [row if isinstance(row, Mapping) else {} for row in rows or ()]
    out: List[RowAnalysis] = []
    for index, row in enumerate(rows):
        location = source_location(row, collection)
        if _time_ok(row.get("time_from")) and _time_ok(row.get("time_to")):
            out.append(RowAnalysis(index, "timed", location=location))
            continue
        if not is_narrative_only(row):
            out.append(RowAnalysis(index, "incomplete", location=location,
                                   reason="Row has activity fields but no valid From/To; it is not narrative"))
            continue
        text = _text(row.get(DESCRIPTION_FIELD))
        analysis = RowAnalysis(index, "continuation", review_id=review_id_for(location, index, text), text=text,
                               location=location)
        analysis.reason = _eligibility(rows, out, analysis, continuation_allowed)
        analysis.eligible = analysis.reason == ELIGIBLE
        out.append(analysis)
    return out


def _eligibility(rows, done: List[RowAnalysis], analysis: RowAnalysis, allowed: bool) -> str:
    if not allowed:
        return "The report profile does not permit continuation rows"
    if _HEADER_FOOTER.search(analysis.text):
        return "Text looks like a repeated header, a page footer or a total line"
    if not done:
        return "No preceding activity row: the parent cannot be identified"
    # Walk back over the run of narrative rows to the anchor row.
    chain = [analysis]
    position = len(done) - 1
    while position >= 0 and done[position].kind == "continuation":
        chain.append(done[position])
        position -= 1
    if position < 0:
        return "No timed activity precedes this narrative run: the parent cannot be identified"
    anchor = done[position]
    if anchor.kind != "timed":
        return "The preceding row is itself incomplete: more than one parent is possible"
    for later, earlier in zip(chain, chain[1:] + [anchor]):
        if _group(later.location) != _group(earlier.location):
            return "A table or sheet boundary separates this row from the candidate parent"
        if later.location.get("page") != earlier.location.get("page"):
            return "A page boundary separates this row from the candidate parent"
        a, b = later.location.get("row"), earlier.location.get("row")
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in (a, b)):
            return "Source row numbers are missing or not comparable; order cannot be proven"
        if a <= b:
            return "Source order is not preserved between this row and the candidate parent"
    analysis.parent_index = anchor.index
    return ELIGIBLE


def continuation_review_rows(rows: Sequence[Mapping], *, collection: str = "time_logs_24h",
                             continuation_allowed: bool = True, sheet: str = "") -> List[Dict[str, Any]]:
    """Review payloads (ReviewItem keyword sets) for every continuation candidate of a collection."""
    rows = list(rows or ())
    section = "time_log_morning" if collection == "time_logs_morning" else "time_log"
    payloads = []
    for item in analyse_time_rows(rows, collection=collection, continuation_allowed=continuation_allowed):
        if item.kind != "continuation":
            continue
        parent = item.parent_payload(rows)
        payloads.append({
            "review_id": item.review_id,
            "review_type": "continuation",
            "record_index": item.index,
            "eligible": item.eligible,
            "parent": parent,
            "sheet": item.location.get("sheet") or sheet,
            "page": item.location.get("page"),
            "row": item.location.get("row") or 0,
            "detected_table": collection,
            "original_value": item.text,
            "normalized_value": item.text,
            "target_field": f"{section}.continuation",
            "confidence": 0.8,
            "decision": "REVIEW",
            "classification": "continuation",
            "transform": ("Continuation candidate: attach to the parent activity by an explicit decision"
                          if item.eligible else "Continuation text kept for review; no time is invented"),
            "reason": ("Eligible: one unambiguous parent activity in the same table"
                       if item.eligible else item.reason),
        })
    return payloads


def attach_text(parent: Dict[str, Any], text: str, lineage: Mapping[str, Any]) -> None:
    """Append the full text to the parent description with a line break and record its lineage."""
    current = _text(parent.get(DESCRIPTION_FIELD))
    parent[DESCRIPTION_FIELD] = f"{current}\n{text}" if current.strip() else text
    parent.setdefault("_continuations", []).append(dict(lineage))


def apply_continuation_decisions(extracted: Dict[str, Any], review_items: Iterable[Any],
                                 *, continuation_allowed: bool = True) -> List[Dict[str, Any]]:
    """Apply ATTACH / REJECT / IGNORE / DEFER decisions of continuation review rows.

    Ownership is re-proven from the current rows (same review id at the same index); an attachment is done only
    when the row is still eligible with the same parent. Decided and deferred continuation rows leave the
    canonical collection (a continuation is never a time log); their outcomes are returned and recorded under
    ``metadata.continuation_outcomes`` for the persisted review queue and the audit.
    """
    outcomes: List[Dict[str, Any]] = []
    by_collection: Dict[str, List[Dict[str, Any]]] = {}
    existing = extracted.get("metadata") if isinstance(extracted.get("metadata"), dict) else {}
    # Idempotent: an identity that already has an outcome was applied before (its row left the collection).
    done_ids = {str(o.get("review_id")) for o in existing.get("continuation_outcomes") or () if isinstance(o, dict)}
    for item in review_items or ():
        payload = item.to_dict() if hasattr(item, "to_dict") else item
        if not isinstance(payload, dict) or payload.get("review_type") != "continuation":
            continue
        if str(payload.get("review_id") or "") in done_ids:
            continue
        by_collection.setdefault(str(payload.get("detected_table") or "time_logs_24h"), []).append(payload)
    for collection, payloads in by_collection.items():
        rows = extracted.get(collection)
        if not isinstance(rows, list):
            continue
        analysis = {a.review_id: a for a in analyse_time_rows(rows, collection=collection,
                                                               continuation_allowed=continuation_allowed)
                    if a.kind == "continuation"}
        remove = set()
        for payload in sorted(payloads, key=lambda p: int(p.get("record_index") or 0)):
            current = analysis.get(str(payload.get("review_id") or ""))
            index = payload.get("record_index")
            if current is None or current.index != index:
                payload["decision"], payload["review_state"] = "REVIEW", "unreviewed"
                payload["reason"] = "Row ownership is not proven (the row changed); kept for review"
                continue
            decision = str(payload.get("decision") or "REVIEW").strip().upper()
            if decision in {"ACCEPT", "CONFIRMED"}:
                # A continuation is attached or rejected - never accepted as a time log of its own.
                payload["decision"], payload["review_state"] = "REVIEW", "unreviewed"
                payload["reason"] = ("A continuation cannot be accepted as a time log; attach it to its parent, "
                                     "reject or ignore it, or keep it for review")
                decision = "REVIEW"
            state = review_state_for(decision)
            outcome = {"review_id": current.review_id, "state": state, "text": current.text,
                       "location": current.location, "eligible": current.eligible,
                       "reason": current.reason, "collection": collection, "record_index": index,
                       "contract": CONTINUATION_CONTRACT_VERSION}
            if state == SAFELY_ATTACHED_CONTINUATION:
                if not current.eligible or current.parent_index is None:
                    payload["decision"], payload["review_state"] = "REVIEW", "unreviewed"
                    payload["reason"] = f"Not attachable: {current.reason}"
                    outcome["state"] = DEFERRED_UNRESOLVED
                else:
                    parent = rows[current.parent_index]
                    attach_text(parent, current.text, {"review_id": current.review_id,
                                                       "location": current.location,
                                                       "contract": CONTINUATION_CONTRACT_VERSION})
                    outcome["parent_index"] = current.parent_index
                    outcome["parent_row"] = parent.get("_source_row")
                    payload["review_state"] = "accepted"
            elif state in (REJECTED, IGNORED):
                payload["review_state"] = "rejected"
            outcome["parent"] = current.parent_payload(rows)
            remove.add(index)
            outcomes.append(outcome)
        if remove:
            kept = [row for position, row in enumerate(rows) if position not in remove]
            # Parents of deferred rows keep their identity after the removal: remap their index.
            remap = {old: new for new, old in enumerate(p for p in range(len(rows)) if p not in remove)}
            for outcome in outcomes:
                if outcome["collection"] == collection and outcome.get("parent_index") is not None:
                    outcome["parent_index"] = remap.get(outcome["parent_index"])
                parent = outcome.get("parent")
                if outcome["collection"] == collection and parent and parent.get("index") is not None:
                    parent["index"] = remap.get(parent["index"])
            rows[:] = kept
    metadata = extracted.setdefault("metadata", {}) if isinstance(extracted.get("metadata", {}), dict) else {}
    if outcomes:
        metadata.setdefault("continuation_outcomes", []).extend(outcomes)
    return outcomes


def defer_undecided_continuations(extracted: Dict[str, Any], *, continuation_allowed: bool = True,
                                  collections: Sequence[str] = ("time_logs_24h", "time_logs_morning"),
                                  ) -> List[Dict[str, Any]]:
    """Keep every continuation row that nobody decided as a DEFERRED_UNRESOLVED review outcome.

    Used at the persistence boundary so every route (preview or headless) ends with the same result: a
    continuation row is never stored as a time log, never dropped, and never attached without a decision.
    """
    outcomes: List[Dict[str, Any]] = []
    for collection in collections:
        rows = extracted.get(collection)
        if not isinstance(rows, list) or not rows:
            continue
        pending = continuation_review_rows(rows, collection=collection, continuation_allowed=continuation_allowed)
        for payload in pending:
            payload["decision"] = DEFER
        outcomes.extend(apply_continuation_decisions(extracted, pending, continuation_allowed=continuation_allowed))
    return outcomes


def preserve_line_breaks(text: Any) -> str:
    """Collapse spaces inside each line but keep the line structure of an attached continuation."""
    lines = (" ".join(line.split()) for line in _text(text).splitlines())
    return "\n".join(line for line in lines if line)
