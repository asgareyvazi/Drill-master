"""User-confirmed links between library documents and wells/daily reports (M45).

A link says "this stored document belongs to well W (and, optionally, to its
daily report R)".  Links are created, changed and removed only by an explicit
user action through :class:`DocumentLinkService`; nothing is linked
automatically.  :meth:`DocumentLinkService.suggest_wells` only *proposes*
wells whose name or code appears in the stored text, with the page it was
found on, for the user to confirm.

Integrity (each mutation is ONE transaction; any failure leaves no partial
link and no audit row):

* the document, the well and the report must exist, and the report must
  belong to the well (also enforced by the ownership guard in
  ``core.database`` for every report-scoped well model);
* an anchor page, when given, must be a stored page of the document;
* the same (document, well, report) link cannot exist twice (service check
  plus unique constraint/partial unique index);
* permission ``can_import`` (document library curation) is enforced by the
  data-layer policy on ``document_links``;
* a mandatory audit record (``document_link`` / ``document_link_change`` /
  ``document_unlink``) is written in the same transaction; an audit failure
  rolls the change back and is reported as ``audit_failed``.

Deletion policy: a link leaves with its document (ORM cascade, counted in the
``document_delete`` audit), its well (ON DELETE CASCADE inside the audited
well delete) or its report (the report-child sweep of the audited report
delete).  The document itself is never deleted by a link operation, and the
audit trail keeps the link history.  Original text, file name and import
review decisions are never touched.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from core.search_normalization import normalize, tokens

logger = logging.getLogger(__name__)

SCOPE_WELL = "well"
SCOPE_REPORT = "report"

ERROR_TEXT = {
    "document_missing": "The document no longer exists.",
    "well_missing": "The selected well no longer exists.",
    "report_missing": "The selected daily report no longer exists.",
    "report_well_mismatch": "The selected report belongs to a different well.",
    "page_missing": "The anchor page is not a stored page of this document.",
    "duplicate": "This document is already linked to that well/report.",
    "link_missing": "The link no longer exists.",
    "unchanged": "The link already points to that well/report.",
    "denied": "You do not have permission to change document links.",
    "audit_failed": "The audit record could not be written; nothing was changed.",
    "failed": "The link could not be saved; nothing was changed.",
}


class DocumentLinkError(Exception):
    """A refused or failed link operation; ``code`` is a key of ERROR_TEXT."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        super().__init__(ERROR_TEXT.get(code, code) + (f" ({detail})" if detail else ""))


@dataclass(frozen=True)
class WellSuggestion:
    """A well whose name/code occurs in the stored text - never a decision."""
    well_id: int
    well_name: str
    well_code: Optional[str]
    matched: str            # "name" or "code"
    page_no: int
    location: str
    occurrences: int


def _principal_name():
    from core.permissions import permissions
    user = permissions.user
    if isinstance(user, dict):
        return user.get("username")
    return getattr(user, "username", None)


def _phrase_tokens(value) -> list:
    return [t.casefold() for t in tokens(str(value or ""))]


def _distinctive(parts) -> bool:
    """A name is suggested only if it cannot match by accident: at least
    three letters/digits in total and not a bare number."""
    joined = "".join(parts)
    return len(joined) >= 3 and not joined.isdigit()


def _count_phrase(haystack: list, needle: list) -> int:
    n = len(needle)
    return sum(1 for i in range(len(haystack) - n + 1) if haystack[i:i + n] == needle) if n else 0


class DocumentLinkService:
    """Create, change, remove and list document links."""

    def __init__(self, db_manager):
        self.db = db_manager

    # ----------------------------------------------------------- pickers
    def well_choices(self, text: str = "") -> list:
        """Wells for the picker with the fields that tell same-name wells
        apart (code, field, project, company, rig, spud date, report count)."""
        from sqlalchemy import func

        from core.database import Company, DailyReport, Project, Well
        session = self.db.create_session()
        try:
            counts = dict(session.query(DailyReport.well_id, func.count(DailyReport.id))
                          .group_by(DailyReport.well_id).all())
            rows = (session.query(Well, Project.name, Company.name)
                    .outerjoin(Project, Well.project_id == Project.id)
                    .outerjoin(Company, Project.company_id == Company.id)
                    .order_by(Well.name, Well.id).all())
            needle = normalize(text).casefold().strip()
            out = []
            for well, project, company in rows:
                item = {"id": well.id, "name": well.name, "code": well.code, "field": well.field_name,
                        "project": project, "company": company, "rig": well.rig_name,
                        "spud_date": well.spud_date, "reports": counts.get(well.id, 0)}
                haystack = normalize(" ".join(str(v) for v in (well.name, well.code, well.field_name, project,
                                                                company, well.rig_name) if v)).casefold()
                if needle and needle not in haystack:
                    continue
                out.append(item)
            names = [w["name"] for w in out]
            for item in out:
                item["ambiguous_name"] = names.count(item["name"]) > 1
            return out
        finally:
            session.close()

    def report_choices(self, well_id: int) -> list:
        from core.database import DailyReport, Section
        session = self.db.create_session()
        try:
            rows = (session.query(DailyReport, Section.name)
                    .outerjoin(Section, DailyReport.section_id == Section.id)
                    .filter(DailyReport.well_id == well_id)
                    .order_by(DailyReport.report_date.desc(), DailyReport.id.desc()).all())
            return [{"id": r.id, "report_number": r.report_number, "report_date": r.report_date,
                     "section": section, "depth": r.depth_2400, "status": r.status, "well_id": r.well_id}
                    for r, section in rows]
        finally:
            session.close()

    # ------------------------------------------------------------ queries
    def _link_rows(self, session, *criteria):
        from core.database import DailyReport, Document, DocumentLink, Well
        query = (session.query(DocumentLink, Document.file_name, Document.kind, Well.name, Well.code,
                               DailyReport.report_number, DailyReport.report_date)
                 .join(Document, DocumentLink.document_id == Document.id)
                 .join(Well, DocumentLink.well_id == Well.id)
                 .outerjoin(DailyReport, DocumentLink.report_id == DailyReport.id)
                 .filter(*criteria)
                 .order_by(Document.file_name, DocumentLink.id))
        return [{"id": link.id, "document_id": link.document_id, "file_name": file_name, "kind": kind,
                 "well_id": link.well_id, "well_name": well_name, "well_code": well_code,
                 "report_id": link.report_id, "report_number": number, "report_date": report_date,
                 "scope": SCOPE_REPORT if link.report_id else SCOPE_WELL, "page_no": link.page_no,
                 "note": link.note, "linked_at": link.linked_at, "linked_by": link.linked_by}
                for link, file_name, kind, well_name, well_code, number, report_date in query]

    def links_for_document(self, document_id: int) -> list:
        from core.database import DocumentLink
        session = self.db.create_session()
        try:
            return self._link_rows(session, DocumentLink.document_id == document_id)
        finally:
            session.close()

    def links_for_well(self, well_id: int, include_report_links: bool = True) -> list:
        from core.database import DocumentLink
        session = self.db.create_session()
        try:
            criteria = [DocumentLink.well_id == well_id]
            if not include_report_links:
                criteria.append(DocumentLink.report_id.is_(None))
            return self._link_rows(session, *criteria)
        finally:
            session.close()

    def links_for_report(self, report_id: int) -> list:
        from core.database import DocumentLink
        session = self.db.create_session()
        try:
            return self._link_rows(session, DocumentLink.report_id == report_id)
        finally:
            session.close()

    def link_counts(self) -> dict:
        """{document_id: number of links} for the library list."""
        from sqlalchemy import func

        from core.database import DocumentLink
        session = self.db.create_session()
        try:
            return dict(session.query(DocumentLink.document_id, func.count(DocumentLink.id))
                        .group_by(DocumentLink.document_id).all())
        finally:
            session.close()

    def unlinked_document_ids(self) -> list:
        from core.database import Document, DocumentLink
        session = self.db.create_session()
        try:
            linked = session.query(DocumentLink.document_id)
            return [row[0] for row in session.query(Document.id).filter(~Document.id.in_(linked))
                    .order_by(Document.id)]
        finally:
            session.close()

    # -------------------------------------------------------- suggestions
    def suggest_wells(self, document_id: int) -> list:
        """Wells whose name or code appears in the document's stored text.

        Comparison uses the search normalisation (Arabic/Persian letter
        forms, digits, half-space) on whole tokens, so "SYN-DEV-01" matches
        "syn dev 01" but never "SYN-DEV-012".  The first page with a match is
        reported.  This is a suggestion list only; it never creates a link.
        """
        from core.database import DocumentPage, Well
        session = self.db.create_session()
        try:
            pages = (session.query(DocumentPage.page_no, DocumentPage.location, DocumentPage.text)
                     .filter(DocumentPage.document_id == document_id).order_by(DocumentPage.page_no).all())
            wells = session.query(Well.id, Well.name, Well.code).order_by(Well.id).all()
        finally:
            session.close()
        page_tokens = [(page_no, location, _phrase_tokens(text)) for page_no, location, text in pages]
        suggestions = []
        for well_id, name, code in wells:
            best = None
            for matched, value in (("code", code), ("name", name)):
                needle = _phrase_tokens(value)
                if not needle or not _distinctive(needle):
                    continue
                total, first = 0, None
                for page_no, location, haystack in page_tokens:
                    count = _count_phrase(haystack, needle)
                    if count and first is None:
                        first = (page_no, location)
                    total += count
                if total and best is None:
                    best = WellSuggestion(well_id, name, code, matched, first[0], first[1], total)
            if best is not None:
                suggestions.append(best)
        suggestions.sort(key=lambda s: (-s.occurrences, s.well_name, s.well_id))
        return suggestions

    # ---------------------------------------------------------- mutations
    def _validate_target(self, session, document_id, well_id, report_id, page_no):
        from core.database import DailyReport, Document, DocumentPage, Well
        document = session.get(Document, document_id) if document_id is not None else None
        if document is None:
            raise DocumentLinkError("document_missing")
        well = session.get(Well, well_id) if well_id is not None else None
        if well is None:
            raise DocumentLinkError("well_missing")
        report = None
        if report_id is not None:
            report = session.get(DailyReport, report_id)
            if report is None:
                raise DocumentLinkError("report_missing")
            if report.well_id != well.id:
                raise DocumentLinkError("report_well_mismatch")
        if page_no is not None and session.query(DocumentPage.id).filter(
                DocumentPage.document_id == document_id, DocumentPage.page_no == page_no).first() is None:
            raise DocumentLinkError("page_missing")
        return document, well, report

    @staticmethod
    def _describe(well, report, page_no) -> dict:
        return {"well_id": well.id, "well": well.name, "report_id": report.id if report else None,
                "report_number": report.report_number if report else None,
                "report_date": report.report_date.isoformat() if report is not None and report.report_date else None,
                "page_no": page_no}

    @staticmethod
    def _duplicate(session, document_id, well_id, report_id, exclude_id=None) -> bool:
        from core.database import DocumentLink
        query = session.query(DocumentLink.id).filter(
            DocumentLink.document_id == document_id, DocumentLink.well_id == well_id,
            DocumentLink.report_id.is_(None) if report_id is None else DocumentLink.report_id == report_id)
        if exclude_id is not None:
            query = query.filter(DocumentLink.id != exclude_id)
        return query.first() is not None

    def _audit(self, session, action, document, details):
        try:
            self.db._add_mandatory_audit(session, action, "document", document.id, document.file_name,
                                         json.dumps(details, ensure_ascii=False, sort_keys=True, default=str))
        except Exception as exc:
            from core.authorization import AuthorizationError
            if isinstance(exc, AuthorizationError):
                raise
            raise DocumentLinkError("audit_failed", type(exc).__name__) from exc

    def _run(self, operation):
        """Run ``operation(session)`` in one transaction; classify failures."""
        from sqlalchemy.exc import IntegrityError

        from core.authorization import AuthorizationError
        try:
            with self.db.session_scope() as session:
                return operation(session)
        except DocumentLinkError:
            raise
        except AuthorizationError as exc:
            raise DocumentLinkError("denied") from exc
        except IntegrityError as exc:            # lost a race against the unique constraints
            if re.search(r"UNIQUE", str(exc.orig), flags=re.IGNORECASE):
                raise DocumentLinkError("duplicate") from exc
            raise DocumentLinkError("failed", type(exc).__name__) from exc
        except Exception as exc:
            logger.error("Document link operation rolled back: %s", type(exc).__name__)
            raise DocumentLinkError("failed", type(exc).__name__) from exc

    def create_link(self, document_id: int, well_id: int, report_id: Optional[int] = None,
                    page_no: Optional[int] = None, note: Optional[str] = None) -> int:
        """Link a document to a well (and optionally a report); returns the link id."""
        from core.database import DocumentLink

        def operation(session):
            document, well, report = self._validate_target(session, document_id, well_id, report_id, page_no)
            if self._duplicate(session, document_id, well_id, report_id):
                raise DocumentLinkError("duplicate")
            link = DocumentLink(document_id=document_id, well_id=well_id, report_id=report_id, page_no=page_no,
                                note=(note or None) and note.strip()[:200], linked_by=_principal_name())
            session.add(link)
            session.flush()
            link_id = link.id
            self._audit(session, "document_link", document,
                        {"link_id": link_id, **self._describe(well, report, page_no)})
            return link_id
        return self._run(operation)

    def update_link(self, link_id: int, well_id: int, report_id: Optional[int] = None,
                    page_no: Optional[int] = None) -> None:
        """Point an existing link at another well/report/page (audited with before and after)."""
        from core.database import DailyReport, DocumentLink, Well

        def operation(session):
            link = session.get(DocumentLink, link_id)
            if link is None:
                raise DocumentLinkError("link_missing")
            document, well, report = self._validate_target(session, link.document_id, well_id, report_id, page_no)
            if (link.well_id, link.report_id, link.page_no) == (well_id, report_id, page_no):
                raise DocumentLinkError("unchanged")
            if self._duplicate(session, link.document_id, well_id, report_id, exclude_id=link.id):
                raise DocumentLinkError("duplicate")
            before = self._describe(session.get(Well, link.well_id),
                                    session.get(DailyReport, link.report_id) if link.report_id else None,
                                    link.page_no)
            link.well_id, link.report_id, link.page_no = well_id, report_id, page_no
            session.flush()
            self._audit(session, "document_link_change", document,
                        {"link_id": link.id, "from": before, "to": self._describe(well, report, page_no)})
        self._run(operation)

    def remove_link(self, link_id: int) -> None:
        from core.database import DailyReport, Document, DocumentLink, Well

        def operation(session):
            link = session.get(DocumentLink, link_id)
            if link is None:
                raise DocumentLinkError("link_missing")
            document = session.get(Document, link.document_id)
            before = self._describe(session.get(Well, link.well_id),
                                    session.get(DailyReport, link.report_id) if link.report_id else None,
                                    link.page_no)
            session.delete(link)
            session.flush()
            self._audit(session, "document_unlink", document, {"link_id": link_id, **before})
        self._run(operation)
