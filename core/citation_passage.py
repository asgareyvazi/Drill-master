"""M469-M470: secure citation passage service — open a ``.citations.json`` passage from the Documents tab.

A citation record (``core/citation_record.py``, ``M320-E citation record v1``) is a file the user picks. It may come
from another machine or another library, and it may have been edited or crafted. This service is the one read path
for it in the UI: the Knowledge Assistant "Verify citation file…" and the Library page "Open citation file…" both
use it. It adds the following on top of ``citation_record.verify_record``, and never changes the library:

* **Bounded, strict read.** The file must be a regular file of at most ``MAX_FILE_BYTES``. It must be UTF-8 JSON
  with no duplicate keys (a second ``"start"`` cannot shadow the first), no ``NaN`` / ``Infinity``, and nesting no
  deeper than the parser allows. Anything else is refused as a whole, with the reason.
* **Schema** (``docs/engineering/schemas/citation_record_v1.schema.json``). The top level needs the record version
  and 1 to ``MAX_CITATIONS`` citations. A citation is checked field by field:
  * ids, page and span are non-negative integers (booleans and floats are refused);
  * ``start < end``, and the span and the quote are at most ``MAX_QUOTE_CHARS`` long (a quote that the span
    does not hold stays ``SPAN_MISMATCH``, from ``verify_record``);
  * the page hash is 64 lower-case hex digits;
  * the label is a short plain token;
  * the file name is a single line.

  A citation that fails is ``UNREADABLE`` with the field named. It is never passed on and never opened. The other
  citations are still verified.
* **Identity.** Document ids are local to a library. When the record names a file and the library document with
  that id has another file name, the citation is ``IDENTITY_MISMATCH`` and is not opened. Opening it would show an
  unrelated document as the cited source.
* **Read-only, offline.** Nothing is repaired, re-anchored, searched elsewhere, written or fetched.
* **M549 (U4).** A symbolic link is refused (the picked path itself must be a regular file, not a link to one).
  Citation record v2 (``core/citation_record_v2.py``, schema ``citation_record_v2.schema.json``) is read through the
  same path; its citations additionally need hex hashes, a bare file name (no directory part, no ``..``) and
  internally consistent ``passage_id`` / ``quote_sha256`` / ``page_text_sha256``; the library document's content
  SHA-256 is compared with the recorded one (``DOCUMENT_CHANGED``). v1 records are read exactly as before.

Opening is still done by the Documents tab viewer (``DocumentsTab.open_evidence``). The viewer re-checks the page
SHA-256 and highlights only an unchanged page.
"""
from __future__ import annotations

import json
import os
import re
import stat
from typing import Any, Dict, List, Tuple

from core import citation_record as cr
from core import citation_record_v2 as cr2

SERVICE_VERSION = "M469 citation passage service v1"
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_CITATIONS = 500
MAX_QUOTE_CHARS = 20000
MAX_ID = 2 ** 31 - 1
IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
LABEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.:#-]{0,31}")
SHA_PATTERN = re.compile(r"[0-9a-f]{64}")
INT_FIELDS = ("document_id", "page_id", "page_no", "start", "end")
TEXT_FIELDS = ("question", "answer", "mode", "citation_label", "semantic_label")
RECORD_VERSIONS = (cr.RECORD_VERSION, cr2.RECORD_VERSION)
V2_HASH_FIELDS = ("page_text_sha256", "quote_sha256", "passage_id")


class PassageError(cr.CitationRecordError):
    """The file is not a readable, well-formed citation record (refused as a whole)."""


def _no_duplicates(pairs):
    seen: Dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise PassageError(f"The citation file repeats the key {key!r}; it is refused.")
        seen[key] = value
    return seen


def _no_constant(name):
    raise PassageError(f"The citation file contains {name}, which is not valid JSON; it is refused.")


def read_record(path: str) -> Dict[str, Any]:
    """Bounded, strict read of a citation record file. Raises ``PassageError`` with the reason."""
    try:
        info = os.lstat(path)
    except (OSError, TypeError, ValueError) as exc:
        raise PassageError(f"The citation file cannot be read: {exc}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise PassageError("The citation file is a symbolic link; pick the file itself. It is refused.")
    if not stat.S_ISREG(info.st_mode):
        raise PassageError("The citation file is not a regular file; it is refused.")
    if info.st_size > MAX_FILE_BYTES:
        raise PassageError(f"The citation file is {info.st_size} bytes, more than the {MAX_FILE_BYTES} byte limit.")
    try:
        with open(path, "rb") as handle:
            raw = handle.read(MAX_FILE_BYTES + 1)
    except OSError as exc:
        raise PassageError(f"The citation file cannot be read: {exc}") from exc
    if len(raw) > MAX_FILE_BYTES:
        raise PassageError(f"The citation file is larger than the {MAX_FILE_BYTES} byte limit.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PassageError(f"The citation file is not UTF-8 text: {exc.reason}") from exc
    try:
        record = json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_no_constant)
    except PassageError:
        raise
    except RecursionError as exc:
        raise PassageError("The citation file is nested too deeply; it is refused.") from exc
    except ValueError as exc:
        raise PassageError(f"The citation file is not valid JSON: {exc}") from exc
    validate_record(record)
    return record


def validate_record(record: Any) -> None:
    """Top-level schema; raises ``PassageError``. Citation entries are checked one by one in ``citation_problem``."""
    if not isinstance(record, dict) or record.get("record_version") not in RECORD_VERSIONS:
        raise PassageError("This is not a DrillMaster citation record (unknown or missing record_version).")
    citations = record.get("citations")
    if not isinstance(citations, list) or not citations:
        raise PassageError("The citation record has no citations list.")
    if len(citations) > MAX_CITATIONS:
        raise PassageError(f"The citation record has {len(citations)} citations, more than {MAX_CITATIONS}.")
    for key in TEXT_FIELDS:
        if key in record and record[key] is not None and not isinstance(record[key], str):
            raise PassageError(f"The citation record field {key!r} is not text.")


def citation_problem(entry: Any, version: str = cr.RECORD_VERSION) -> str:
    """'' when the citation entry is well-formed, else the reason (the entry is then UNREADABLE)."""
    problem = _v1_problem(entry)
    if problem or version != cr2.RECORD_VERSION:
        return problem
    for key in V2_HASH_FIELDS:
        if not isinstance(entry.get(key), str) or not SHA_PATTERN.fullmatch(entry[key]):
            return f"{key} is not a SHA-256 hex digest"
    doc_hash = entry.get("document_sha256")
    if doc_hash is not None and (not isinstance(doc_hash, str) or not SHA_PATTERN.fullmatch(doc_hash)):
        return "document_sha256 is neither null nor a SHA-256 hex digest"
    name = entry.get("file_name")
    if name is not None and ("/" in name or "\\" in name or name in (".", "..") or ":" in name):
        return "file_name is not a bare file name (directory parts are refused)"
    return cr2.integrity_problem(entry)


def _v1_problem(entry: Any) -> str:
    if not isinstance(entry, dict):
        return "the entry is not an object"
    missing = [k for k in cr.REQUIRED if entry.get(k) is None]
    if missing:
        return f"missing {', '.join(missing)}"
    label = entry["label"]
    if not isinstance(label, str) or not LABEL_PATTERN.fullmatch(label):
        return "label is not a short plain token"
    for key in INT_FIELDS:
        value = entry[key]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_ID:
            return f"{key} is not a non-negative integer"
    start, end = entry["start"], entry["end"]
    if not start < end:
        return "start is not before end"
    if end - start > MAX_QUOTE_CHARS:
        return f"the span is longer than {MAX_QUOTE_CHARS} characters"
    if not isinstance(entry["quote"], str) or len(entry["quote"]) > MAX_QUOTE_CHARS:
        return f"quote is not text of at most {MAX_QUOTE_CHARS} characters"
    if not isinstance(entry["text_version"], str) or not SHA_PATTERN.fullmatch(entry["text_version"]):
        return "text_version is not a SHA-256 hex digest"
    name = entry.get("file_name")
    if name is not None and (not isinstance(name, str) or len(name) > 260
                             or any(ord(ch) < 32 or ord(ch) == 127 for ch in name)):
        return "file_name is not a single-line name"
    return ""


def verify(db, record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One result per citation, in record order: schema, then ``verify_record``, then document identity."""
    validate_record(record)
    version = record["record_version"]
    citations = record["citations"]
    problems = [citation_problem(entry, version) for entry in citations]
    valid = [entry for entry, problem in zip(citations, problems) if not problem]
    v1_view = {**record, "record_version": cr.RECORD_VERSION, "citations": valid}
    v1_results = cr.verify_record(db, v1_view) if valid else []
    if version == cr2.RECORD_VERSION:
        v1_results = cr2.content_check(db, valid, v1_results)
    checked = iter(v1_results)
    names = _library_names(db, {entry["document_id"] for entry in valid})
    out: List[Dict[str, Any]] = []
    for entry, problem in zip(citations, problems):
        if problem:
            label = entry.get("label") if isinstance(entry, dict) and isinstance(entry.get("label"), str) else None
            out.append({"label": label, "status": cr.UNREADABLE, "reason": problem,
                        "file_name": None, "page_no": None})
            continue
        result = next(checked)
        recorded = entry.get("file_name")
        stored = names.get(entry["document_id"])
        settled = result["status"] in (cr.DOCUMENT_MISSING, cr2.DOCUMENT_CHANGED)
        if not settled and recorded is not None and stored is not None \
                and recorded != stored:
            result = {**result, "status": IDENTITY_MISMATCH,
                      "reason": f"library document {entry['document_id']} is {stored!r}, the record cites "
                                f"{recorded!r}: a different document with the same id"}
        out.append(result)
    return out


def _library_names(db, document_ids) -> Dict[int, str]:
    if not document_ids:
        return {}
    from core.database import Document

    with db.session_scope() as session:
        rows = session.query(Document.id, Document.file_name).filter(Document.id.in_(sorted(document_ids))).all()
    return {int(i): name for i, name in rows}


def open_record(db, path: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(record, verification results, navigation targets) for a record file; raises ``PassageError``."""
    record = read_record(path)
    results = verify(db, record)
    return record, results, cr.navigation(record, results)
