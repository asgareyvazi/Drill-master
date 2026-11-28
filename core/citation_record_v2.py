"""M546-M550 (U4): citation record v2 — content-addressed passages on top of the v1 record.

A v1 record (``core/citation_record.py``, ``M320-E citation record v1``) identifies a passage by library-local ids,
the page-text SHA-256 and a character span. v2 adds, per citation:

* ``document_sha256`` — the SHA-256 of the imported source file's bytes, **copied from the library**
  (``Document.sha256``, computed at import from the real bytes). It is filled only when the citation verifies EXACT
  against the library at upgrade time; otherwise it is ``null``. A hash is never invented or recomputed from
  anything else;
* ``page_text_sha256`` — the page-text SHA-256 (same value as v1 ``text_version``, explicit name);
* ``quote_sha256`` — SHA-256 of the quoted text (UTF-8);
* ``offset_unit`` — the span is in Unicode code points of the stored page text;
* ``passage_id`` — SHA-256 over (document_sha256 or "", page_no, start, end, quote_sha256), so an edit of any of
  those fields is detected;
* ``verification_state`` — ``VERIFIED_EXACT`` (verified against the library at upgrade) or ``NOT_VERIFIED`` with
  the v1 status that prevented it (``state_reason``), and ``verified_at``.

``verify`` (read-only, offline) runs every v1 check and then:

* ``passage_id`` / ``quote_sha256`` / ``page_text_sha256`` that do not match the record's own fields → UNREADABLE
  (an edited record);
* a recorded ``document_sha256`` that differs from the library document's → ``DOCUMENT_CHANGED`` (not openable:
  the library holds another version of the file under that id);
* a ``null`` document hash → the v1 result, with the reason saying the content hash was not recorded.

v1 records stay readable and are verified exactly as before. ``upgrade`` writes nothing to the library.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core import citation_record as cr

RECORD_VERSION = "M546 citation record v2"
DOCUMENT_CHANGED = "DOCUMENT_CHANGED"
VERIFIED_EXACT, NOT_VERIFIED = "VERIFIED_EXACT", "NOT_VERIFIED"
OFFSET_UNIT = "unicode code points of the stored page text"
V2_FIELDS = ("page_text_sha256", "quote_sha256", "offset_unit", "passage_id", "verification_state")


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def passage_id(document_sha256: Optional[str], page_no: int, start: int, end: int, quote_sha256: str) -> str:
    payload = json.dumps([document_sha256 or "", int(page_no), int(start), int(end), quote_sha256],
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _library_hashes(db, document_ids) -> Dict[int, str]:
    if not document_ids:
        return {}
    from core.database import Document

    with db.session_scope() as session:
        rows = session.query(Document.id, Document.sha256).filter(Document.id.in_(sorted(document_ids))).all()
    return {int(i): h for i, h in rows}


def upgrade(db, record: Dict[str, Any], results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """A v2 record from a v1 record and its verification results (``citation_passage.verify``, same order).

    Only citations whose result is EXACT receive the library's document content hash; every other citation keeps
    ``document_sha256 = null`` and ``verification_state = NOT_VERIFIED`` with the reason."""
    if not isinstance(record, dict) or record.get("record_version") != cr.RECORD_VERSION:
        raise cr.CitationRecordError("Only a v1 citation record can be upgraded.")
    citations = record.get("citations") or []
    if len(citations) != len(results):
        raise cr.CitationRecordError("The verification results do not belong to this record.")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    exact_ids = {int(c["document_id"]) for c, r in zip(citations, results) if r.get("status") == cr.EXACT}
    hashes = _library_hashes(db, exact_ids)
    upgraded: List[Dict[str, Any]] = []
    for entry, result in zip(citations, results):
        if not isinstance(entry, dict) or result.get("status") == cr.UNREADABLE:
            continue                                   # an unreadable citation is not carried into v2
        exact = result.get("status") == cr.EXACT
        doc_hash = hashes.get(int(entry["document_id"])) if exact else None
        quote_hash = sha256_text(entry["quote"])
        upgraded.append({
            **entry,
            "document_sha256": doc_hash,
            "page_text_sha256": entry["text_version"],
            "quote_sha256": quote_hash,
            "offset_unit": OFFSET_UNIT,
            "passage_id": passage_id(doc_hash, entry["page_no"], entry["start"], entry["end"], quote_hash),
            "verification_state": VERIFIED_EXACT if exact and doc_hash else NOT_VERIFIED,
            "state_reason": "" if exact and doc_hash else f"{result.get('status')}: {result.get('reason', '')}",
            "verified_at": now,
        })
    if not upgraded:
        raise cr.CitationRecordError("No readable citation to carry into a v2 record.")
    return {**{k: v for k, v in record.items() if k != "citations"}, "record_version": RECORD_VERSION,
            "upgraded_from": cr.RECORD_VERSION, "upgraded_at": now, "citations": upgraded}


def integrity_problem(entry: Dict[str, Any]) -> str:
    """'' when the v2 fields agree with the citation's own fields, else the reason (an edited record)."""
    if entry.get("offset_unit") != OFFSET_UNIT:
        return "offset_unit is not the stored-page code-point unit"
    if entry.get("page_text_sha256") != entry.get("text_version"):
        return "page_text_sha256 differs from text_version"
    if entry.get("quote_sha256") != sha256_text(entry.get("quote") or ""):
        return "quote_sha256 does not match the quote"
    expected = passage_id(entry.get("document_sha256"), entry["page_no"], entry["start"], entry["end"],
                          entry["quote_sha256"])
    if entry.get("passage_id") != expected:
        return "passage_id does not match its fields (edited record)"
    state = entry.get("verification_state")
    if state not in (VERIFIED_EXACT, NOT_VERIFIED):
        return "verification_state is unknown"
    if state == VERIFIED_EXACT and not entry.get("document_sha256"):
        return "VERIFIED_EXACT without a document content hash"
    return ""


def content_check(db, entries: List[Dict[str, Any]], results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply the document-content check to v1-style results of well-formed v2 entries (same order)."""
    hashes = _library_hashes(db, {int(e["document_id"]) for e in entries if e.get("document_sha256")})
    out: List[Dict[str, Any]] = []
    for entry, result in zip(entries, results):
        recorded = entry.get("document_sha256")
        result = {**result, "passage_id": entry.get("passage_id"), "verification_state": entry.get("verification_state")}
        if result["status"] in (cr.DOCUMENT_MISSING, cr.UNREADABLE):
            out.append(result)
            continue
        if recorded is None:
            result["reason"] = f"{result.get('reason', '')}; document content hash not recorded (NOT VERIFIED)"
        elif hashes.get(int(entry["document_id"])) != recorded:
            result = {**result, "status": DOCUMENT_CHANGED,
                      "reason": "the library document with this id has different file content (SHA-256) from the "
                                "cited one; not opened"}
        out.append(result)
    return out
