"""M320-E (M288): offline citation record of a Knowledge Assistant answer, with exact re-verification.

An answer is ephemeral in the assistant. ``build_record`` freezes it into a portable record. The record holds the
question, the shown answer text, its mode, the citation-check label (always with "Not semantically verified") and,
for every cited passage, the document id and file name, the page id and number, the exact character span, the
SHA-256 of the stored page text and the quoted text itself.

``verify_record`` re-checks every citation against the library **now**, read-only:

* ``EXACT``              – same document, same page, the page text has the recorded SHA-256 and the span is the quote;
* ``PAGE_CHANGED``       – the page text changed since the answer (re-reviewed / edited); the span is not trusted;
* ``SPAN_MISMATCH``      – the page hash still matches but the span does not hold the quote (a corrupt record);
* ``PAGE_MISSING``       – the document exists but that page is no longer stored;
* ``DOCUMENT_MISSING``   – the document was deleted;
* ``UNREADABLE``         – the record entry lacks a required field.

Nothing is repaired, re-anchored or searched for elsewhere. A changed source is reported and the user asks again.
Record files are UTF-8 JSON (``.citations.json``) and readable Markdown, written locally, with no network use.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

RECORD_VERSION = "M320-E citation record v1"
EXACT, PAGE_CHANGED, SPAN_MISMATCH, PAGE_MISSING, DOCUMENT_MISSING, UNREADABLE = (
    "EXACT", "PAGE_CHANGED", "SPAN_MISMATCH", "PAGE_MISSING", "DOCUMENT_MISSING", "UNREADABLE")
REQUIRED = ("label", "document_id", "page_id", "page_no", "start", "end", "text_version", "quote")


class CitationRecordError(ValueError):
    """The answer cannot be recorded (no answer, nothing cited) or the file is not a citation record."""


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def build_record(answer, question: str) -> Dict[str, Any]:
    from core import knowledge_answer as ka

    if answer is None or getattr(answer, "state", None) != "ready" or not getattr(answer, "text", ""):
        raise CitationRecordError("There is no ready answer to record.")
    check = answer.check
    cited = set(check.cited) if check is not None else set()
    used = [e for e in answer.evidence if e.label in cited] if cited else list(answer.evidence)
    if not used:
        raise CitationRecordError("The answer cites no passage; there is nothing to record.")
    return {
        "record_version": RECORD_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "question": question,
        "answer": answer.text,
        "mode": answer.mode,
        "citation_label": check.label if check is not None else ka.CITATION_FAILED_LABEL,
        "semantic_label": ka.SEMANTIC_LABEL,
        "problems": list(check.problems) if check is not None else [],
        "notes": list(answer.notes),
        "citations": [{"label": e.label, "document_id": e.document_id, "file_name": e.file_name,
                       "page_id": e.page_id, "page_no": e.page_no, "location": e.location, "start": e.start,
                       "end": e.end, "text_version": e.text_version, "quote": e.text,
                       "review_status": e.review_status, "method": e.method,
                       "instruction_like": bool(e.instruction_like)} for e in used],
    }


def verify_record(db, record: Dict[str, Any]) -> List[Dict[str, Any]]:
    from core.database import Document, DocumentPage

    if not isinstance(record, dict) or record.get("record_version") != RECORD_VERSION:
        raise CitationRecordError("This is not a DrillMaster citation record (unknown or missing record_version).")
    out: List[Dict[str, Any]] = []
    with db.session_scope() as session:
        for entry in record.get("citations") or []:
            missing = [k for k in REQUIRED if not isinstance(entry, dict) or entry.get(k) is None]
            if missing:
                out.append({"label": (entry or {}).get("label") if isinstance(entry, dict) else None,
                            "status": UNREADABLE, "reason": f"missing {', '.join(missing)}"})
                continue
            base = {"label": entry["label"], "file_name": entry.get("file_name"), "page_no": entry["page_no"]}
            if session.get(Document, int(entry["document_id"])) is None:
                out.append({**base, "status": DOCUMENT_MISSING,
                            "reason": f"document {entry['document_id']} is no longer in the library"})
                continue
            page = session.get(DocumentPage, int(entry["page_id"]))
            if page is None or page.document_id != int(entry["document_id"]):
                out.append({**base, "status": PAGE_MISSING,
                            "reason": f"page id {entry['page_id']} of document {entry['document_id']} is not stored"})
                continue
            text = page.text or ""
            if _sha(text) != entry["text_version"]:
                out.append({**base, "status": PAGE_CHANGED,
                            "reason": "the stored page text changed since the answer; the span is not trusted"})
                continue
            start, end = int(entry["start"]), int(entry["end"])
            if not (0 <= start < end <= len(text)) or text[start:end] != entry["quote"]:
                out.append({**base, "status": SPAN_MISMATCH,
                            "reason": "the page is unchanged but the recorded span does not hold the quote"})
                continue
            out.append({**base, "status": EXACT, "reason": f"characters {start}–{end} match the quote exactly"})
    return out


OPENABLE = (EXACT, PAGE_CHANGED)


def navigation(record: Dict[str, Any], results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """M334 (A-8): one navigation target per citation of a verified record (same order as ``verify_record``).

    * EXACT – the page opens with the recorded span highlighted (the quote is proven to be there);
    * PAGE_CHANGED – the page opens, but the viewer refuses to highlight and states the change (the span would
      point into other text);
    * SPAN_MISMATCH, PAGE_MISSING, DOCUMENT_MISSING, UNREADABLE – nothing opens: there is no page whose text holds
      the quote, and opening some other place would look like evidence.
    """
    citations = record.get("citations") or []
    if len(citations) != len(results):
        raise CitationRecordError("The verification results do not belong to this record.")
    out: List[Dict[str, Any]] = []
    for entry, result in zip(citations, results):
        target = {"label": result.get("label"), "status": result["status"], "reason": result.get("reason", ""),
                  "openable": result["status"] in OPENABLE, "file_name": result.get("file_name"),
                  "page_no": result.get("page_no")}
        if target["openable"]:
            target.update(document_id=int(entry["document_id"]), page_no=int(entry["page_no"]),
                          start=int(entry["start"]), end=int(entry["end"]), text_version=entry["text_version"])
        out.append(target)
    return out


def to_markdown(record: Dict[str, Any]) -> str:
    lines = [f"# Answer with citations ({record['record_version']})", "",
             f"- Question: {record['question']}", f"- Mode: {record['mode']}",
             f"- {record['citation_label']} — {record['semantic_label']}", f"- Recorded: {record['created_at']}", "",
             "## Answer", "", record["answer"], "", "## Citations", ""]
    for c in record["citations"]:
        lines += [f"### [{c['label']}] {c['file_name']}, {c['location']} (page {c['page_no']})", "",
                  f"- Document id {c['document_id']}, page id {c['page_id']}, characters {c['start']}–{c['end']}",
                  f"- Page text SHA-256 `{c['text_version']}`; review status {c['review_status']}; "
                  f"extraction {c['method']}" + ("; contains instruction-like text (treated as data)"
                                                 if c["instruction_like"] else ""), "",
                  "> " + c["quote"].replace("\n", "\n> "), ""]
    if record["problems"]:
        lines += ["## Citation-check problems", ""] + [f"- {p}" for p in record["problems"]] + [""]
    return "\n".join(lines)


def save(record: Dict[str, Any], path: str) -> List[str]:
    """Write ``<path>`` (JSON) and ``<path minus .json>.md``; return both paths."""
    if not path.endswith(".json"):
        path += ".citations.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2, sort_keys=True)
    md = path[:-5] + ".md"
    with open(md, "w", encoding="utf-8") as handle:
        handle.write(to_markdown(record))
    return [path, md]


def load(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, ValueError) as exc:
        raise CitationRecordError(f"The citation file cannot be read: {exc}") from exc
    if not isinstance(record, dict) or record.get("record_version") != RECORD_VERSION:
        raise CitationRecordError("This is not a DrillMaster citation record (unknown or missing record_version).")
    return record


def summary(results: List[Dict[str, Any]]) -> str:
    counts: Dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    state = "ALL EXACT" if results and counts.get(EXACT) == len(results) else "NOT ALL EXACT"
    return f"{state}: " + ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))
