"""M296: value states of the numeric DDR header fields at the import boundary - contract ``ddr-import-value-states-v1``.

The Excel import (and every route that goes through ``DDRImportService``) used to normalize these fields with the
general :class:`core.value_normalizer.ValueNormalizer`. That normalizer reads ``"1,500"`` as 1500 and strips known
unit suffixes (``"12.5 ppg"`` -> 12.5). That is right for many columns, but D86 says a numeric DDR header value is
never interpreted silently. For the 11 fields of :data:`core.ddr_value_states.FIELDS`, the import therefore
classifies the value that is about to be persisted (after preview decisions and review stripping):

* ``NUMBER``: a finite number (an Excel numeric cell, or text that :func:`parse_authored` reads unambiguously).
  It is stored; its state stays implicit (REPORTED, or ZERO for 0).
* ``BLANK``: empty or absent. The stored value stays None and the state stays implicit (NOT_REPORTED); no event
  is written, so a blank cell is never turned into an explicit, asserted state.
* ``TOKEN``: an explicit word (``N/A``, ``?``, ``unknown``, ``NR`` ...). The stored value stays None, and the
  state (NOT_APPLICABLE / UNKNOWN / NOT_REPORTED) is recorded in the import transaction with one mandatory audit
  record. It is never recorded over an existing state (operator or earlier import), and never when it would
  contradict the stored value (a report the import did not create). That case is reported, never repaired.
* ``AMBIGUOUS``: anything else (a comma, a unit suffix, other text, NaN, infinity, a boolean, a date). The value
  is **not stored**. A review item (``review_type = "value_state"``, decision DEFER) carries the original text
  into the persisted review queue, where the operator corrects it with the strict M173 correction contract or
  leaves it pending. The import status becomes REVIEW_REQUIRED through the existing review count.

M297 (PDF routes: the native PDF fallback and an externally configured MinerU, both through
``ddr_import_pipeline.mineru_extracted``): the same classification runs on ``metadata.mineru_provenance``. In
addition, a mapped header cell read as blank is a BLANK_EXTRACTION review item and never becomes NOT_REPORTED
automatically. A value read by OCR always goes to review, because OCR stays gated by P4/P5. A field fed by several
different source cells is AMBIGUOUS.

Excel route source: the extractor keeps the original cell text in ``metadata.field_provenance``; when the value
about to be persisted is exactly the extractor's normalization of that text, the source text is classified.

Everything is written in the import's single session, so a failure anywhere (including the audit) rolls the
states back with the report.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional

from core import ddr_value_states as vs

CONTRACT = "ddr-import-value-states-v1"
NUMBER, BLANK, TOKEN, AMBIGUOUS = "NUMBER", "BLANK", "TOKEN", "AMBIGUOUS"
AUDIT_ACTION = "ddr_import_value_state"
NOTE_PREFIX = "import "                                 # DdrValueState.note of an import event
KEPT_EXISTING_STATE = "KEPT_EXISTING_STATE"
NOT_RECORDED_CONTRADICTION = "NOT_RECORDED_CONTRADICTS_STORED_VALUE"
RECORDED = "RECORDED"


def classify(raw: Any) -> Dict[str, Any]:
    """``{"outcome", "value", "state", "reason"}`` for one source value of a numeric header field."""
    if raw is None:
        return {"outcome": BLANK, "value": None, "state": vs.NOT_REPORTED, "reason": ""}
    if isinstance(raw, bool) or isinstance(raw, (date, datetime)):
        return {"outcome": AMBIGUOUS, "value": None, "state": None,
                "reason": f"{type(raw).__name__} {raw!r} is not a number"}
    if isinstance(raw, (int, float, Decimal)):
        number = float(raw)
        if not math.isfinite(number):
            return {"outcome": AMBIGUOUS, "value": None, "state": None, "reason": f"{raw!r} is not a finite number"}
        return {"outcome": NUMBER, "value": number, "state": vs.ZERO if number == 0 else vs.REPORTED, "reason": ""}
    if not isinstance(raw, str):
        return {"outcome": AMBIGUOUS, "value": None, "state": None,
                "reason": f"{type(raw).__name__} is not a number or text"}
    if not raw.strip():
        return {"outcome": BLANK, "value": None, "state": vs.NOT_REPORTED, "reason": ""}
    try:
        value, state = vs.parse_authored(raw)
    except vs.ValueStateError as exc:
        return {"outcome": AMBIGUOUS, "value": None, "state": None, "reason": str(exc)}
    if value is None:
        return {"outcome": TOKEN, "value": None, "state": state, "reason": ""}
    return {"outcome": NUMBER, "value": value, "state": state, "reason": ""}


_NO_SOURCE = object()


def _same(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) \
            and not isinstance(b, bool):
        return float(a) == float(b)
    return a == b


def _source_text(provenance: Any, current: Any) -> Any:
    """The extractor's original text for ``current``, or ``_NO_SOURCE`` when ``current`` is not its normalization.

    A value the operator changed in the preview no longer equals ``normalized_value``; it is classified as it is.
    """
    if not isinstance(provenance, Mapping) or "original_value" not in provenance:
        return _NO_SOURCE
    if not _same(provenance.get("normalized_value"), current):
        return _NO_SOURCE
    return provenance.get("original_value")


_CONFLICT = object()
BLANK_EXTRACTION = "BLANK_EXTRACTION"
REVIEW_OUTCOMES = (AMBIGUOUS, BLANK_EXTRACTION)


def _needs_review(outcome: str, reason: str) -> Dict[str, Any]:
    return {"outcome": outcome, "value": None, "state": None, "reason": reason}


def _provenance_map(metadata: Mapping[str, Any]) -> Dict[str, Any]:
    """field path -> provenance entry (``_CONFLICT`` when a PDF field has several different source texts)."""
    excel = metadata.get("field_provenance")
    if isinstance(excel, Mapping):
        return dict(excel)
    out: Dict[str, Any] = {}
    for entry in metadata.get("mineru_provenance") or ():
        if not isinstance(entry, Mapping) or not str(entry.get("canonical_field") or "").startswith("daily_report."):
            continue
        key = entry["canonical_field"]
        if key in out and (out[key] is _CONFLICT or out[key].get("original_value") != entry.get("original_value")):
            out[key] = _CONFLICT
        elif key not in out:
            out[key] = entry
    return out


def _ocr(prov: Any) -> bool:
    return isinstance(prov, Mapping) and "ocr" in str(prov.get("extraction_method") or "").lower()


def _location(prov: Any, cell: Any) -> Dict[str, Any]:
    """Review-row location (sheet / cell / row / page) from the provenance entry and the mapped cell."""
    prov = prov if isinstance(prov, Mapping) else {}
    cell = cell if isinstance(cell, Mapping) else {}
    page = prov.get("source_page", cell.get("page"))
    row = prov.get("source_row", cell.get("row"))
    column = prov.get("source_column", cell.get("column"))
    token = prov.get("source_cell") or (f"page {page} row {row} column {column}" if page is not None else "")
    return {"sheet": str(prov.get("source_sheet") or ""), "source_cell": str(token or ""),
            "row": row if isinstance(row, int) else None, "page": page if isinstance(page, int) else None}


def _undecided_review(metadata: Mapping[str, Any], target: str) -> bool:
    """True when a review row for ``target`` is still undecided (not ACCEPT/CONFIRMED)."""
    for row in metadata.get("review_matrix") or ():
        if not isinstance(row, Mapping):
            continue
        if target not in (row.get("target_field"), row.get("canonical_field")):
            continue
        if str(row.get("decision") or "REVIEW").strip().upper() not in ("ACCEPT", "CONFIRMED"):
            return True
    return False


def _review_id(field: str, raw: Any) -> str:
    key = json.dumps([CONTRACT, field, str(raw)], ensure_ascii=False)
    return "vs-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def prepare(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """Classify the header fields of ``extracted`` in place, before persistence; returns the plan.

    NUMBER values are replaced by the parsed float (a source number never replaces a normalized value), BLANK and
    TOKEN values by None, and values that need review (AMBIGUOUS, BLANK_EXTRACTION) are removed, never stored.
    For each of those a review row (``metadata.review_matrix``) and a deferred review decision
    (``metadata.review_decisions``, persisted as an import review item) are added.

    Routes: the Excel route keeps ``metadata.field_provenance`` (path -> original/normalized value). The PDF
    routes (native fallback and MinerU, M297) keep ``metadata.mineru_provenance`` (a list) and map blank cells in
    ``daily_report._source_cells``. On a PDF route, a mapped header cell read as blank is a BLANK_EXTRACTION
    (never NOT_REPORTED automatically), a value read by OCR always goes to review (OCR stays gated, P4/P5), and a
    field fed by several different source cells is AMBIGUOUS.
    """
    report = extracted.get("daily_report")
    plan: Dict[str, Any] = {"contract": CONTRACT, "fields": {}, "tokens": [], "ambiguous": [], "route": "excel"}
    if not isinstance(report, dict):
        return plan
    metadata = extracted.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        return plan
    pdf = isinstance(metadata.get("mineru_provenance"), list)
    plan["route"] = "pdf" if pdf else "excel"
    ocr_document = str(metadata.get("method") or "").strip().lower() == "ocr"
    cells = report.get("_source_cells") if isinstance(report.get("_source_cells"), Mapping) else {}
    provenance = _provenance_map(metadata)
    for field, label in vs.FIELDS.items():
        target = f"daily_report.{field}"
        prov = provenance.get(target)
        if field not in report:
            # Absent: stripped as an undecided review proposal (that review item stays the authority), left out by
            # the extractor because it normalized to nothing (N/A, ?, 1,5 ...), or a blank PDF cell.
            if _undecided_review(metadata, target):
                continue
            normalized_to_nothing = isinstance(prov, Mapping) and "original_value" in prov \
                and prov.get("normalized_value") is None
            if not (normalized_to_nothing or prov is _CONFLICT or (pdf and target in cells)):
                continue
            current = None
        else:
            current = report[field]
        raw, outcome = current, classify(current)
        if prov is _CONFLICT:
            outcome = _needs_review(AMBIGUOUS, "several different source cells feed this field")
        else:
            source = _source_text(prov, current)
            if source is not _NO_SOURCE:
                from_source = classify(source)
                if from_source["outcome"] in (TOKEN, AMBIGUOUS) or (pdf and from_source["outcome"] == BLANK):
                    # The extractor normalized this text ("1,500" -> 1500.0, "12.5 ppg" -> 12.5, "N/A" -> None):
                    # the source text decides. A source *number* never replaces the normalized value, which may
                    # carry a unit conversion.
                    raw, outcome = source, from_source
            if pdf and outcome["outcome"] != AMBIGUOUS and (ocr_document or _ocr(prov)):
                outcome = _needs_review(AMBIGUOUS, "read by OCR; OCR values are never stored without review "
                                                   "(OCR is not approved: P4/P5)")
            if pdf and outcome["outcome"] == BLANK:
                outcome = _needs_review(BLANK_EXTRACTION, "the PDF cell was read as blank; NOT_REPORTED is not "
                                                          "assumed (the extraction may have missed the value)")
        plan["fields"][field] = {"outcome": outcome["outcome"], "state": outcome["state"],
                                 "original": None if raw is None else str(raw), "reason": outcome["reason"]}
        if outcome["outcome"] in REVIEW_OUTCOMES:
            report.pop(field, None)
            location = _location(prov, cells.get(target))
            row = {
                "review_id": _review_id(field, raw), "review_type": "value_state", "target_field": target,
                "canonical_field": target, "field": target, "entity": "daily_report", "detected_table": "scalar",
                "decision": "DEFER", "status": "REVIEW_REQUIRED",
                "classification": "value-state-blank-extraction" if outcome["outcome"] == BLANK_EXTRACTION
                else "value-state-ambiguous",
                "mapping_method": CONTRACT, "original_value": "" if raw is None else str(raw),
                "source_value": "" if raw is None else str(raw),
                "reason": f"{label}: {outcome['reason']} - not stored; correct it in the review queue",
                "contract": CONTRACT, **location,
            }
            metadata.setdefault("review_matrix", []).append(dict(row))
            metadata.setdefault("review_decisions", []).append(dict(row))
            plan["ambiguous"].append(field)
        else:
            report[field] = outcome["value"]
            if outcome["outcome"] == TOKEN:
                plan["tokens"].append(field)
    return plan


def record_import_states(db, session, report_id: int, plan: Mapping[str, Any], *,
                         fingerprint: str = "") -> List[Dict[str, Any]]:
    """Record the TOKEN states of ``plan`` for ``report_id`` inside the import ``session`` (no commit here).

    Returns one entry per TOKEN field: RECORDED, KEPT_EXISTING_STATE (an earlier state of that field is never
    superseded by an import) or NOT_RECORDED_CONTRADICTS_STORED_VALUE (the stored value is not empty, e.g. the
    import attached to an existing report; nothing is repaired).
    """
    from core.database import DailyReport, DdrValueState

    outcomes: List[Dict[str, Any]] = []
    if not plan.get("tokens"):
        return outcomes
    report = session.get(DailyReport, report_id)
    if report is None:
        raise vs.ValueStateError(f"daily report {report_id} does not exist")
    existing = vs._latest(session, report_id)
    for field in plan["tokens"]:
        state = plan["fields"][field]["state"]
        entry = {"field": field, "state": state, "original": plan["fields"][field]["original"]}
        if field in existing:
            entry.update(outcome=KEPT_EXISTING_STATE, kept=existing[field].state,
                         reason="an earlier recorded state is never superseded by an import")
        else:
            why = vs.contradiction(state, getattr(report, field))
            if why:
                entry.update(outcome=NOT_RECORDED_CONTRADICTION, reason=why)
            else:
                row = DdrValueState(report_id=report_id, field=field, state=state, method=None,
                                    note=f"{NOTE_PREFIX}{fingerprint[:16]}: source text {entry['original']!r}"[:500],
                                    created_by=None)
                session.add(row)
                session.flush()
                db._add_mandatory_audit(session, AUDIT_ACTION, "daily_reports", report_id, vs.FIELDS[field],
                                        f"{CONTRACT}: {field} = {state} from source text {entry['original']!r}")
                entry.update(outcome=RECORDED, id=row.id)
        outcomes.append(entry)
    return outcomes


def pending_review_fields(session, report_id: int) -> Dict[str, str]:
    """Header fields of one report with a pending value-state review item: field -> original source text."""
    from core.database import ImportReviewItem
    from core.import_review_queue import PENDING_STATES

    rows = (session.query(ImportReviewItem)
            .filter(ImportReviewItem.report_id == report_id, ImportReviewItem.review_type == "value_state",
                    ImportReviewItem.state.in_(PENDING_STATES)).all())
    out: Dict[str, str] = {}
    for row in rows:
        field = str(row.target_field or "").split(".", 1)[-1]
        if field in vs.FIELDS:
            out[field] = row.original_text or ""
    return out


def is_import_event(row: Any) -> bool:
    """True for a value-state event written by an import (no user, note with the import prefix)."""
    return getattr(row, "created_by", None) is None and str(getattr(row, "note", "") or "").startswith(NOTE_PREFIX)


def summary(plan: Mapping[str, Any], outcomes: List[Mapping[str, Any]]) -> Optional[str]:
    """One result line for the import details, or None when no header field had a value state to report."""
    if not plan.get("tokens") and not plan.get("ambiguous"):
        return None
    recorded = sum(1 for entry in outcomes if entry.get("outcome") == RECORDED)
    kept = sum(1 for entry in outcomes if entry.get("outcome") == KEPT_EXISTING_STATE)
    conflict = sum(1 for entry in outcomes if entry.get("outcome") == NOT_RECORDED_CONTRADICTION)
    return (f"🔢 Header value states: {recorded} recorded, {kept} existing state(s) kept, {conflict} not recorded "
            f"(contradicts the stored value), {len(plan.get('ambiguous') or [])} value(s) kept for review, not stored "
            "(ambiguous, OCR-read or blank PDF extraction)")
