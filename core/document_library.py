"""Reviewable document import and local full-text search (M44).

Three separate steps, so nothing reaches the database without a decision:

1. ``extract_document(path)`` - Qt-free and database-free (safe in a worker).
   Detects the type from magic bytes, extracts text per page/location and
   flags every page: ``ok``, ``no_text``, ``needs_review`` (all OCR output)
   or ``error``.  Corrupt, encrypted, empty, oversized and unknown files get
   a document status and no pages.
2. A reviewer approves, edits or rejects pages (``PageDecision``).
3. ``DocumentLibrary.import_reviewed`` stores the document, its approved pages
   and a ``document_import`` audit row in ONE transaction; any failure rolls
   all of it back.  The file's SHA-256 prevents duplicates.

Search (``DocumentLibrary.search``) uses SQLite FTS5 in a private in-memory
index rebuilt from ``document_pages`` when the library changes, so the
operational schema holds only ordinary tables; without FTS5 it falls back to
a substring scan.  Every hit carries file, page/location, the line of the
first match and a snippet of the stored text it came from.  No network
access is used anywhere in this module.

M45: the index holds a *normalised copy* of each page
(``core.search_normalization``: Arabic/Persian yeh and kaf, digits,
half-space, harakat, tatweel) and queries are normalised the same way.  The
stored text is never rewritten; snippets and highlights are mapped back to
the original characters.  The normalisation version is part of the index
signature, so documents imported before a rule change are re-indexed from
their stored originals on the next search (``rebuild_index`` forces it).

OCR is optional (RapidOCR + onnxruntime, see requirements-optional.txt).  It
is imported lazily; when absent, scanned pages are reported as having no text
with an explicit message.  OCR confidence scores are engine scores, not
probabilities: wrong text can score above 0.9, so OCR pages are never stored
without explicit approval.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from core.search_normalization import (
    NORMALIZATION_VERSION, find_spans, fts_match_expression, line_of, make_snippet, normalize, parse_query,
    query_terms,
)

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_PAGES = 500
MIN_PAGE_CHARS = 10                 # fewer non-space characters -> "no text"
TEXT_LINES_PER_SECTION = 80
OCR_DPI = 200

# document statuses
READY, PARTIAL, NEEDS_REVIEW, NO_TEXT = "ready", "partial", "needs_review", "no_text"
UNSUPPORTED, CORRUPT, ENCRYPTED, EMPTY, TOO_LARGE, FAILED, CANCELLED = (
    "unsupported", "corrupt", "encrypted", "empty", "too_large", "error", "cancelled")
TERMINAL = {UNSUPPORTED, CORRUPT, ENCRYPTED, EMPTY, TOO_LARGE, FAILED, CANCELLED}
# page statuses
PAGE_OK, PAGE_NO_TEXT, PAGE_REVIEW, PAGE_ERROR = "ok", "no_text", "needs_review", "error"

IMAGE_KINDS = {"png", "jpeg", "tiff", "bmp"}
FILE_DIALOG_FILTER = ("Documents (*.pdf *.txt *.csv *.md *.log *.png *.jpg *.jpeg *.tif *.tiff *.bmp);;"
                      "All files (*)")


# ------------------------------------------------------------------ models
@dataclass
class PageExtract:
    page_no: int
    location: str
    text: str
    method: str                       # pdf-text | text-file | ocr
    status: str                       # ok | no_text | needs_review | error
    confidence: Optional[float] = None
    note: str = ""


@dataclass
class DocumentExtract:
    path: str
    file_name: str
    size_bytes: int = 0
    sha256: str = ""
    kind: str = "unknown"             # pdf | text | png | jpeg | tiff | bmp | unknown
    page_count: int = 0
    status: str = FAILED
    pages: list = field(default_factory=list)
    messages: list = field(default_factory=list)
    encoding: Optional[str] = None

    @property
    def importable(self) -> bool:
        return self.status not in TERMINAL and any(p.status in (PAGE_OK, PAGE_REVIEW) for p in self.pages)


@dataclass(frozen=True)
class PageDecision:
    approved: bool
    text: Optional[str] = None        # None keeps the extracted text


@dataclass
class ImportOutcome:
    file_name: str
    status: str                       # imported | duplicate | nothing_approved | not_importable | denied | failed
    document_id: Optional[int] = None
    stored_pages: int = 0
    skipped_pages: list = field(default_factory=list)
    message: str = ""


# ---------------------------------------------------------------- detection
def detect_kind(head: bytes) -> str:
    """File type from magic bytes (the extension is not trusted)."""
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if head.startswith(b"BM") and len(head) > 14:
        return "bmp"
    sample = head[:8192]
    if sample and b"\x00" not in sample and decode_text(sample)[1] is not None:
        return "text"
    return "unknown"


def decode_text(data: bytes):
    """(text, encoding); utf-8-sig, utf-8, then cp1256 (Persian/Arabic Windows)."""
    for encoding in ("utf-8-sig", "utf-8", "cp1256"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:  # silent-ok: try the next candidate encoding
            continue
    return "", None


def _meaningful(text: str) -> bool:
    return len(re.sub(r"\s+", "", text or "")) >= MIN_PAGE_CHARS


# ---------------------------------------------------------------------- OCR
class OcrUnavailable(RuntimeError):
    pass


class RapidOcrEngine:
    """Thin lazy adapter over RapidOCR (Apache-2.0); models ship in its wheel."""

    name = "RapidOCR"

    def __init__(self):
        try:
            from rapidocr import RapidOCR
        except ImportError as exc:  # optional dependency
            raise OcrUnavailable("RapidOCR is not installed (pip install -r requirements-optional.txt)") from exc
        import importlib.metadata
        self.version = importlib.metadata.version("rapidocr")
        self._engine = RapidOCR()

    def recognize(self, image_bytes: bytes):
        """(text, mean engine score or None).  Lines are rebuilt from boxes."""
        result = self._engine(image_bytes)
        texts = getattr(result, "txts", None)
        if not texts:
            return "", None
        scores = list(getattr(result, "scores", None) or [])
        boxes = getattr(result, "boxes", None)
        items = []
        for index, text in enumerate(texts):
            if boxes is not None and len(boxes) > index:
                ys = [float(point[1]) for point in boxes[index]]
                xs = [float(point[0]) for point in boxes[index]]
                items.append((sum(ys) / len(ys), max(ys) - min(ys), min(xs), str(text).strip()))
            else:
                items.append((float(index), 1.0, 0.0, str(text).strip()))
        items.sort()
        lines, current, last_y = [], [], None
        for y, height, x, text in items:
            if last_y is not None and abs(y - last_y) > max(height, 1.0) * 0.6:
                lines.append(" ".join(t for _x, t in sorted(current)))
                current = []
            current.append((x, text))
            last_y = y
        if current:
            lines.append(" ".join(t for _x, t in sorted(current)))
        score = sum(scores) / len(scores) if scores else None
        return "\n".join(line for line in lines if line), score


_OCR_STATE: dict = {}


def ocr_status() -> dict:
    """{'available': bool, 'engine': str|None, 'version': str|None, 'reason': str}; no download, no network."""
    if os.environ.get("DRILLMASTER_OCR", "").strip().lower() in ("0", "off", "false", "no"):
        return {"available": False, "engine": None, "version": None, "reason": "OCR disabled (DRILLMASTER_OCR=0)"}
    if "status" not in _OCR_STATE:
        try:
            import importlib.util
            if importlib.util.find_spec("rapidocr") is None or importlib.util.find_spec("onnxruntime") is None:
                raise OcrUnavailable("OCR engine not installed: scanned pages and images will be listed as "
                                     "having no text (optional: pip install -r requirements-optional.txt)")
            import importlib.metadata
            _OCR_STATE["status"] = {"available": True, "engine": "RapidOCR",
                                    "version": importlib.metadata.version("rapidocr"), "reason": ""}
        except OcrUnavailable as exc:
            _OCR_STATE["status"] = {"available": False, "engine": None, "version": None, "reason": str(exc)}
    return dict(_OCR_STATE["status"])


def default_ocr_engine():
    """A ready engine, or None when OCR is unavailable (reason in ``ocr_status``)."""
    if not ocr_status()["available"]:
        return None
    if "engine" not in _OCR_STATE:
        try:
            _OCR_STATE["engine"] = RapidOcrEngine()
        except Exception as exc:          # model/runtime load failure: degrade, keep the reason
            logger.warning("OCR engine could not start: %s", type(exc).__name__)
            _OCR_STATE["status"] = {"available": False, "engine": None, "version": None,
                                    "reason": f"OCR engine failed to start ({type(exc).__name__})"}
            _OCR_STATE["engine"] = None
    return _OCR_STATE["engine"]


# --------------------------------------------------------------- extraction
def _ocr_page(engine, image_bytes, page_no, location, note_prefix=""):
    try:
        text, score = engine.recognize(image_bytes)
    except Exception as exc:
        logger.warning("OCR failed on %s: %s", location, type(exc).__name__)
        return PageExtract(page_no, location, "", "ocr", PAGE_ERROR, note=f"OCR failed ({type(exc).__name__})")
    if not _meaningful(text):
        return PageExtract(page_no, location, text or "", "ocr", PAGE_NO_TEXT, score,
                           note=note_prefix + "OCR found no text")
    return PageExtract(page_no, location, text, "ocr", PAGE_REVIEW, score,
                       note=note_prefix + "OCR text: verify against the source before approving")


def _extract_pdf(data, result, ocr_engine, cancel, ocr_reason):
    try:
        import fitz
    except ImportError:
        result.status = FAILED
        result.messages.append("PyMuPDF is not installed; PDF text cannot be read")
        return
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        result.status = CORRUPT
        result.messages.append(f"Not a readable PDF ({type(exc).__name__})")
        return
    try:
        if document.needs_pass:
            result.status = ENCRYPTED
            result.messages.append("Password-protected PDF; open and re-save it without a password to import")
            return
        result.page_count = document.page_count
        if result.page_count == 0:
            result.status = EMPTY
            result.messages.append("PDF has no pages")
            return
        if result.page_count > MAX_PAGES:
            result.messages.append(f"Only the first {MAX_PAGES} of {result.page_count} pages are extracted")
        for index in range(min(result.page_count, MAX_PAGES)):
            if cancel and cancel():
                result.status = CANCELLED
                result.messages.append("Extraction cancelled")
                result.pages = []
                return
            page_no, location = index + 1, f"page {index + 1}"
            try:
                page = document.load_page(index)
                text = page.get_text("text") or ""
            except Exception as exc:
                result.pages.append(PageExtract(page_no, location, "", "pdf-text", PAGE_ERROR,
                                                note=f"Page could not be read ({type(exc).__name__})"))
                continue
            if _meaningful(text):
                result.pages.append(PageExtract(page_no, location, text.strip(), "pdf-text", PAGE_OK))
            elif ocr_engine is not None:
                try:
                    image = page.get_pixmap(dpi=OCR_DPI).tobytes("png")
                except Exception as exc:
                    result.pages.append(PageExtract(page_no, location, "", "ocr", PAGE_ERROR,
                                                    note=f"Page could not be rendered ({type(exc).__name__})"))
                    continue
                result.pages.append(_ocr_page(ocr_engine, image, page_no, location, "No text layer; "))
            else:
                result.pages.append(PageExtract(page_no, location, "", "pdf-text", PAGE_NO_TEXT,
                                                note="No text layer (scanned page?). " + ocr_reason))
    finally:
        document.close()


def _extract_text(data, result):
    text, encoding = decode_text(data)
    result.encoding = encoding
    lines = text.splitlines()
    if not _meaningful(text):
        result.page_count = 1
        result.pages.append(PageExtract(1, "whole file", text, "text-file", PAGE_NO_TEXT, note="File has no text"))
        return
    sections = [lines[i:i + TEXT_LINES_PER_SECTION] for i in range(0, len(lines), TEXT_LINES_PER_SECTION)]
    result.page_count = len(sections)
    for index, chunk in enumerate(sections[:MAX_PAGES]):
        first = index * TEXT_LINES_PER_SECTION + 1
        location = f"lines {first}-{first + len(chunk) - 1}"
        body = "\n".join(chunk).strip()
        status = PAGE_OK if _meaningful(body) else PAGE_NO_TEXT
        result.pages.append(PageExtract(index + 1, location, body, "text-file", status))


def extract_document(path, *, ocr_engine=None, cancel: Optional[Callable[[], bool]] = None) -> DocumentExtract:
    """Extract one file for review.  Never raises for bad input; see ``status``."""
    path = Path(path)
    result = DocumentExtract(path=str(path), file_name=path.name)
    ocr_reason = "" if ocr_engine is not None else ocr_status()["reason"] or "OCR not available."
    try:
        size = path.stat().st_size
        result.size_bytes = size
        if size == 0:
            result.status = EMPTY
            result.messages.append("File is empty")
            return result
        if size > MAX_FILE_BYTES:
            result.status = TOO_LARGE
            result.messages.append(f"File is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB")
            return result
        data = path.read_bytes()
    except OSError as exc:
        result.status = FAILED
        result.messages.append(f"File could not be read ({type(exc).__name__})")
        return result
    result.sha256 = hashlib.sha256(data).hexdigest()
    result.kind = detect_kind(data[:16384])
    result.status = ""                       # extractors set a terminal status on failure
    try:
        if result.kind == "pdf":
            _extract_pdf(data, result, ocr_engine, cancel, ocr_reason)
        elif result.kind == "text":
            _extract_text(data, result)
        elif result.kind in IMAGE_KINDS:
            result.page_count = 1
            if ocr_engine is None:
                result.pages.append(PageExtract(1, "image", "", "ocr", PAGE_NO_TEXT, note=ocr_reason))
            else:
                result.pages.append(_ocr_page(ocr_engine, data, 1, "image"))
        else:
            result.status = UNSUPPORTED
            result.messages.append("Unknown or unsupported file format")
            return result
    except Exception as exc:                 # one bad file must never stop a batch
        logger.warning("Extraction failed for %s: %s", path.name, type(exc).__name__)
        result.status = FAILED
        result.messages.append(f"Extraction failed ({type(exc).__name__})")
        result.pages = []
        return result
    if result.status:                        # terminal status from the extractor
        return result
    statuses = [p.status for p in result.pages]
    if not statuses:
        result.status = NO_TEXT
    elif PAGE_REVIEW in statuses:
        result.status = NEEDS_REVIEW
    elif all(s == PAGE_OK for s in statuses) and len(statuses) == min(result.page_count, MAX_PAGES):
        result.status = READY
    elif PAGE_OK in statuses:
        result.status = PARTIAL
    else:
        result.status = NO_TEXT
    return result


def extract_batch(paths, *, ocr_engine=None, cancel=None, progress=None):
    """Extract several files independently; a failure affects only its file."""
    results = []
    for index, path in enumerate(paths):
        if cancel and cancel():
            break
        results.append(extract_document(path, ocr_engine=ocr_engine, cancel=cancel))
        if progress:
            progress(index + 1, len(paths))
    return results


def default_decisions(extract: DocumentExtract) -> dict:
    """Text pages pre-approved; OCR pages unapproved until a person approves them."""
    return {p.page_no: PageDecision(approved=p.status == PAGE_OK) for p in extract.pages}


# ------------------------------------------------------------------ storage
def _principal():
    from core.permissions import permissions
    user = permissions.user
    if isinstance(user, dict):
        return user.get("id"), user.get("username")
    return getattr(user, "id", None), getattr(user, "username", None)


class DocumentLibrary:
    """Reviewed documents in the application database, plus local search."""

    def __init__(self, db_manager):
        self.db = db_manager
        self._index = None
        self._index_signature = None
        self.fts_available = None

    # ---------------------------------------------------------- queries
    def duplicate_of(self, sha256: str):
        from core.database import Document
        session = self.db.create_session()
        try:
            row = session.query(Document.id, Document.file_name).filter(Document.sha256 == sha256).first()
            return (row[0], row[1]) if row else None
        finally:
            session.close()

    def list_documents(self) -> list:
        from sqlalchemy import func

        from core.database import Document, DocumentPage
        session = self.db.create_session()
        try:
            from core.database import DocumentLink
            counts = dict(session.query(DocumentPage.document_id, func.count(DocumentPage.id))
                          .group_by(DocumentPage.document_id).all())
            links = dict(session.query(DocumentLink.document_id, func.count(DocumentLink.id))
                         .group_by(DocumentLink.document_id).all())
            return [{"id": d.id, "file_name": d.file_name, "kind": d.kind, "page_count": d.page_count,
                     "stored_pages": counts.get(d.id, 0), "status": d.status, "imported_at": d.imported_at,
                     "imported_by": d.imported_by, "size_bytes": d.size_bytes, "links": links.get(d.id, 0)}
                    for d in session.query(Document).order_by(Document.imported_at.desc(), Document.id.desc())]
        finally:
            session.close()

    def document(self, document_id: int):
        """{'id', 'file_name', 'kind', 'page_count'} or None (for viewers opened by id)."""
        from core.database import Document
        session = self.db.create_session()
        try:
            d = session.get(Document, document_id)
            return None if d is None else {"id": d.id, "file_name": d.file_name, "kind": d.kind,
                                           "page_count": d.page_count}
        finally:
            session.close()

    def pages(self, document_id: int) -> list:
        from core.database import DocumentPage
        session = self.db.create_session()
        try:
            return [{"id": p.id, "page_no": p.page_no, "location": p.location, "text": p.text, "method": p.method,
                     "review_status": p.review_status, "confidence": p.confidence}
                    for p in session.query(DocumentPage).filter(DocumentPage.document_id == document_id)
                    .order_by(DocumentPage.page_no)]
        finally:
            session.close()

    # ------------------------------------------------------------ import
    def import_reviewed(self, extract: DocumentExtract, decisions: Optional[dict] = None) -> ImportOutcome:
        """Store approved pages + audit atomically.  Never raises for data problems."""
        from core.authorization import AuthorizationError
        from core.database import AuditLog, Document, DocumentPage

        outcome = ImportOutcome(extract.file_name, "failed")
        if not extract.importable:
            outcome.status, outcome.message = "not_importable", (
                "; ".join(extract.messages) or f"Nothing to import ({extract.status})")
            return outcome
        existing = self.duplicate_of(extract.sha256)
        if existing:
            outcome.status, outcome.document_id = "duplicate", existing[0]
            outcome.message = f"Already in the library as '{existing[1]}' (same file content)"
            return outcome
        decisions = decisions if decisions is not None else default_decisions(extract)
        stored, skipped, edited, ocr_approved = [], [], [], []
        for page in extract.pages:
            decision = decisions.get(page.page_no, PageDecision(approved=False))
            if page.status not in (PAGE_OK, PAGE_REVIEW):
                skipped.append({"page": page.page_no, "reason": page.status})
                continue
            if not decision.approved:
                skipped.append({"page": page.page_no, "reason": "not approved"})
                continue
            text = page.text if decision.text is None else decision.text
            if not _meaningful(text):
                skipped.append({"page": page.page_no, "reason": "empty after review"})
                continue
            changed = decision.text is not None and decision.text != page.text
            review = "edited" if changed else ("approved" if page.method == "ocr" else "extracted")
            if changed:
                edited.append(page.page_no)
            if page.method == "ocr":
                ocr_approved.append(page.page_no)
            stored.append((page, text.strip(), review))
        outcome.skipped_pages = skipped
        if not stored:
            outcome.status, outcome.message = "nothing_approved", "No page was approved for import"
            return outcome
        user_id, username = _principal()
        session = self.db.create_session()
        try:
            document = Document(file_name=extract.file_name[:260], sha256=extract.sha256,
                                size_bytes=extract.size_bytes, kind=extract.kind, page_count=extract.page_count,
                                status=extract.status, imported_by=username)
            session.add(document)
            session.flush()
            document_id = document.id
            for page, text, review in stored:
                session.add(DocumentPage(document_id=document_id, page_no=page.page_no, location=page.location,
                                         text=text, method=page.method, review_status=review,
                                         confidence=page.confidence))
            details = {"sha256": extract.sha256, "kind": extract.kind, "extraction_status": extract.status,
                       "source_pages": extract.page_count, "stored_pages": [p.page_no for p, _t, _r in stored],
                       "skipped": skipped, "edited_pages": edited, "ocr_pages_approved": ocr_approved,
                       "encoding": extract.encoding}
            session.add(AuditLog(action="document_import", entity_type="document", entity_id=document_id,
                                 entity_name=extract.file_name[:200], user_id=user_id, username=username,
                                 details=json.dumps(details, ensure_ascii=False)))
            session.commit()
        except AuthorizationError:
            session.rollback()
            outcome.status, outcome.message = "denied", "You do not have permission to import documents"
            return outcome
        except Exception as exc:
            session.rollback()
            logger.error("Document import rolled back for %s: %s", extract.file_name, type(exc).__name__)
            outcome.status, outcome.message = "failed", f"Import rolled back ({type(exc).__name__})"
            return outcome
        finally:
            session.close()
        outcome.status, outcome.document_id, outcome.stored_pages = "imported", document_id, len(stored)
        outcome.message = f"{len(stored)} page(s) stored" + (f", {len(skipped)} skipped" if skipped else "")
        return outcome

    def delete_document(self, document_id: int) -> bool:
        from core.database import AuditLog, Document
        user_id, username = _principal()
        session = self.db.create_session()
        try:
            document = session.get(Document, document_id)
            if document is None:
                return False
            name, sha256 = document.file_name, document.sha256
            links_removed = len(document.links)
            session.delete(document)
            session.add(AuditLog(action="document_delete", entity_type="document", entity_id=document_id,
                                 entity_name=name[:200], user_id=user_id, username=username,
                                 details=json.dumps({"sha256": sha256, "links_removed": links_removed})))
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------------------------------------------------ search
    def _signature(self):
        from sqlalchemy import func

        from core.database import DocumentPage
        session = self.db.create_session()
        try:
            return (NORMALIZATION_VERSION,) + tuple(session.query(
                func.count(DocumentPage.id), func.max(DocumentPage.id), func.sum(func.length(DocumentPage.text))).one())
        finally:
            session.close()

    def _all_pages(self):
        from core.database import Document, DocumentPage
        session = self.db.create_session()
        try:
            return session.query(DocumentPage.id, DocumentPage.text).join(
                Document, DocumentPage.document_id == Document.id).all()
        finally:
            session.close()

    def _ensure_index(self):
        signature = self._signature()
        if self._index is not None and signature == self._index_signature:
            return self._index
        if self._index is not None:
            self._index.close()
            self._index = None
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute("CREATE VIRTUAL TABLE page_fts USING fts5(body, tokenize='unicode61 remove_diacritics 2')")
        except sqlite3.OperationalError:
            connection.close()
            self.fts_available = False
            return None
        self.fts_available = True
        # Normalised copy for matching only; the stored original is untouched.
        connection.executemany("INSERT INTO page_fts(rowid, body) VALUES (?, ?)",
                               ((page_id, normalize(text)) for page_id, text in self._all_pages()))
        connection.commit()
        self._index, self._index_signature = connection, signature
        return connection

    def rebuild_index(self) -> dict:
        """Drop and rebuild the search index from the stored originals."""
        if self._index is not None:
            self._index.close()
        self._index, self._index_signature = None, None
        index = self._ensure_index()
        pages = index.execute("SELECT count(*) FROM page_fts").fetchone()[0] if index is not None else None
        return {"pages": pages, "normalization_version": NORMALIZATION_VERSION, "fts": index is not None}

    @staticmethod
    def _terms(query: str) -> list:
        """Normalised query tokens (used for snippets and highlighting)."""
        return query_terms(query)

    def _page_details(self, ids):
        from core.database import Document, DocumentPage
        if not ids:
            return {}
        session = self.db.create_session()
        try:
            rows = (session.query(DocumentPage.id, DocumentPage.document_id, DocumentPage.page_no,
                                  DocumentPage.location, DocumentPage.method, DocumentPage.review_status,
                                  DocumentPage.text, Document.file_name)
                    .join(Document, DocumentPage.document_id == Document.id)
                    .filter(DocumentPage.id.in_(list(ids))).all())
            return {r[0]: r for r in rows}
        finally:
            session.close()

    def search(self, query: str, limit: int = 20) -> dict:
        """{'status', 'method', 'hits', 'message'}; each hit names its file and page."""
        groups = parse_query(query)
        terms = [t for group in groups for t in group]
        if not terms or sum(len(t) for t in terms) < 2:
            return {"status": "invalid_query", "method": None, "hits": [],
                    "message": "Enter at least two letters or digits"}
        index = self._ensure_index()
        if index is not None:
            rows = index.execute("SELECT rowid FROM page_fts WHERE page_fts MATCH ? ORDER BY bm25(page_fts) LIMIT ?",
                                 (fts_match_expression(groups), int(limit))).fetchall()
            method = "SQLite FTS5 (in-memory index of reviewed pages, Persian/Arabic-normalised)"
            order = [row[0] for row in rows]
        else:
            method = "Substring scan (FTS5 unavailable in this SQLite build, Persian/Arabic-normalised)"
            order = self._scan_search(terms, limit)
        details = self._page_details(order)
        hits = []
        for rowid in order:
            row = details.get(rowid)
            if row is None:
                continue
            original = row[6]
            spans = find_spans(original, terms)
            hits.append({"page_id": row[0], "document_id": row[1], "page_no": row[2], "location": row[3],
                         "method": row[4], "review_status": row[5], "file_name": row[7],
                         "line_no": line_of(original, spans[0][0]) if spans else None,
                         "match_count": len(spans), "snippet": make_snippet(original, terms)})
        return {"status": "matched" if hits else "no_matches", "method": method, "hits": hits,
                "terms": terms, "normalization_version": NORMALIZATION_VERSION,
                "message": (f"{len(hits)} page(s) match" if hits else
                            "No matching text. Only reviewed, stored text is searchable; pages without a "
                            "text layer or unapproved OCR are not indexed.")}

    def _scan_search(self, terms, limit):
        """Fallback without FTS5: pages where every term starts a word, using
        the same normalisation as the index."""
        hits = []
        for page_id, text in sorted(self._all_pages()):
            if all(find_spans(text, [term]) for term in terms):
                hits.append(page_id)
                if len(hits) >= int(limit):
                    break
        return hits

    def close(self):
        if self._index is not None:
            self._index.close()
            self._index = None

