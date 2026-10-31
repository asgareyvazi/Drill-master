"""Split a PDF that holds several daily drilling reports into one segment per report (M52).

A DDR PDF often holds many days.  Imported as one file it would be mapped to
ONE daily report and mix several days.  This module reads the text layer of
every page (PyMuPDF, already a dependency), finds report headers and groups
the pages:

* a page whose header states a report number and/or report date starts a new
  report unless it repeats the header of the report being read (multi-page
  reports often repeat it on every page);
* a page without a header continues the current report and says so;
* a page without a text layer (scanned) is flagged - OCR is not run here - and
  its assignment to the current report is marked as assumed;
* pages before the first header are unassigned;
* the same report (number and date) found twice is an explained duplicate; one
  number with two dates, or a date-format that cannot be read unambiguously,
  is a warning; a well name that differs from the selected well is reported as
  a suggestion only (document-to-well matching is never decided here).

Header rules are generic (labels such as "Report No", "Report Date", "Well").
No operator- or dataset-specific rules.  Every segment carries its page
numbers (1-based), what was found, warnings and a confidence with reasons.
Nothing is saved: the split is shown for review and the user writes one PDF
per report, each imported and confirmed on its own.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable, Optional, Sequence

SPLIT_VERSION = "M52 DDR PDF report split v1"
MIN_TEXT_CHARS = 40            # fewer characters on a page: treated as no text layer
HEADER_LINES = 25              # header labels are looked for in the first lines of a page

_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_NUMBER_RE = re.compile(
    r"\b(?:(?:daily\s+(?:drilling\s+)?)?report|ddr)\s*(?:no\.?|number|nr\.?|#)\s*[:.\-]?\s*(\d{1,5})\b", re.I)
_DATE_VALUE = (r"(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}|\d{1,2}[\s\-][A-Za-z]{3,9}[\s\-,]+\d{4}"
               r"|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})")
_DATE_RE = re.compile(r"\b(?:report\s+)?date\s*[:.\-]?\s*" + _DATE_VALUE, re.I)
_WELL_RE = re.compile(r"\bwell(?:\s+name)?\s*[:\-]\s*([A-Za-z0-9][A-Za-z0-9_\-/.#]*(?: [A-Za-z0-9_\-/.#]+){0,3})",
                      re.I)


class PdfSplitError(RuntimeError):
    """The PDF could not be read (a state, never an empty split)."""


@dataclass(frozen=True)
class PageInfo:
    number: int                        # 1-based page number
    has_text: bool
    report_number: Optional[int] = None
    report_date: Optional[str] = None  # ISO date, or None
    date_text: Optional[str] = None    # the date as written (kept when ambiguous or unreadable)
    date_problem: Optional[str] = None
    well: Optional[str] = None

    @property
    def is_header(self) -> bool:
        return self.report_number is not None or self.date_text is not None


@dataclass
class ReportSegment:
    pages: list
    report_number: Optional[int]
    report_date: Optional[str]
    well: Optional[str]
    date_text: Optional[str] = None
    continuation_pages: list = field(default_factory=list)
    no_text_pages: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    confidence: str = "high"
    reasons: list = field(default_factory=list)

    @property
    def page_range(self) -> str:
        return f"{self.pages[0]}" if len(self.pages) == 1 else f"{self.pages[0]}-{self.pages[-1]}"

    def to_json(self) -> dict:
        return {"pages": list(self.pages), "page_range": self.page_range, "report_number": self.report_number,
                "report_date": self.report_date, "date_text": self.date_text, "well": self.well,
                "continuation_pages": list(self.continuation_pages), "no_text_pages": list(self.no_text_pages),
                "warnings": list(self.warnings), "confidence": self.confidence, "reasons": list(self.reasons)}


@dataclass
class SplitResult:
    page_count: int
    segments: list
    unassigned_pages: list
    warnings: list
    version: str = SPLIT_VERSION

    @property
    def multi_report(self) -> bool:
        return len(self.segments) > 1

    def to_json(self) -> dict:
        return {"version": self.version, "page_count": self.page_count, "multi_report": self.multi_report,
                "segments": [s.to_json() for s in self.segments], "unassigned_pages": list(self.unassigned_pages),
                "warnings": list(self.warnings)}


# ---- page analysis ---------------------------------------------------------------------------------------
def _parse_date(text: str):
    """(iso or None, problem or None).  Day/month order is never guessed."""
    value = text.strip().rstrip(",")
    try:
        m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", value)
        if m:
            return date(int(m[1]), int(m[2]), int(m[3])).isoformat(), None
        m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})", value)
        if m:
            a, b, year = int(m[1]), int(m[2]), int(m[3])
            if a <= 12 and b <= 12 and a != b:
                return None, "day/month order ambiguous"
            day, month = (a, b) if a > 12 or a == b else (b, a)
            return date(year, month, day).isoformat(), None
        m = re.fullmatch(r"(\d{1,2})[\s\-]([A-Za-z]{3,9})[\s\-,]+(\d{4})", value)
        if m and m[2][:3].lower() in _MONTHS:
            return date(int(m[3]), _MONTHS[m[2][:3].lower()], int(m[1])).isoformat(), None
        m = re.fullmatch(r"([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})", value)
        if m and m[1][:3].lower() in _MONTHS:
            return date(int(m[3]), _MONTHS[m[1][:3].lower()], int(m[2])).isoformat(), None
    except ValueError:
        return None, "not a calendar date"
    return None, "unrecognised date format"


def analyse_page(number: int, text: str) -> PageInfo:
    text = text or ""
    if len(re.sub(r"\s+", "", text)) < MIN_TEXT_CHARS:
        return PageInfo(number=number, has_text=False)
    head = "\n".join(text.splitlines()[:HEADER_LINES])
    num = _NUMBER_RE.search(head)
    dat = _DATE_RE.search(head)
    well = _WELL_RE.search(head)
    iso, problem = _parse_date(dat[1]) if dat else (None, None)
    return PageInfo(number=number, has_text=True,
                    report_number=int(num[1]) if num else None,
                    report_date=iso, date_text=dat[1].strip() if dat else None, date_problem=problem,
                    well=well[1].strip() if well else None)


# ---- grouping --------------------------------------------------------------------------------------------
def _same_report(segment: ReportSegment, page: PageInfo) -> bool:
    """A header page repeats the current report: every field both state agrees, and one is shared."""
    shared = False
    if segment.report_number is not None and page.report_number is not None:
        if segment.report_number != page.report_number:
            return False
        shared = True
    seg_date = segment.report_date or segment.date_text
    page_date = page.report_date or page.date_text
    if seg_date is not None and page_date is not None:
        if seg_date != page_date:
            return False
        shared = True
    return shared


def _well_key(name: Optional[str]) -> str:
    return re.sub(r"[\s\-_./#]+", "", (name or "").casefold())


def _start(page: PageInfo) -> ReportSegment:
    segment = ReportSegment(pages=[page.number], report_number=page.report_number,
                            report_date=page.report_date, well=page.well, date_text=page.date_text)
    if page.date_problem:
        segment.warnings.append(f"page {page.number}: report date '{page.date_text}' not read ({page.date_problem})")
    return segment


def split_reports(texts: Sequence[str], *, expected_well: Optional[str] = None) -> SplitResult:
    pages = [analyse_page(i, t) for i, t in enumerate(texts, 1)]
    segments, unassigned, warnings = [], [], []
    current = None
    for page in pages:
        if page.has_text and page.is_header:
            if current is not None and _same_report(current, page):
                current.pages.append(page.number)          # the header repeated on a following page
                if current.well is None and page.well:
                    current.well = page.well
                if current.report_number is None and page.report_number is not None:
                    current.report_number = page.report_number
                if current.report_date is None and page.report_date is not None:
                    current.report_date = page.report_date
                continue
            current = _start(page)
            segments.append(current)
            continue
        if current is None:
            unassigned.append(page.number)
            continue
        current.pages.append(page.number)
        if page.has_text:
            current.continuation_pages.append(page.number)
        else:
            current.no_text_pages.append(page.number)
    if unassigned:
        warnings.append(_pages(unassigned, "come", "comes") + " before the first report header and "
                        + ("belong" if len(unassigned) > 1 else "belongs") + " to no report" + (" (no text layer - OCR not run)" if any(
                            not p.has_text for p in pages if p.number in unassigned) else ""))
    if not segments:
        no_text = sum(1 for p in pages if not p.has_text)
        warnings.append("no report header found" + (f"; {no_text} of {len(pages)} pages have no text layer "
                                                    "(scanned) and OCR was not run" if no_text else ""))
    _explain_duplicates(segments)
    for segment in segments:
        _finish(segment, expected_well)
    return SplitResult(page_count=len(pages), segments=segments, unassigned_pages=unassigned, warnings=warnings)


def _pages(numbers, verb_plural: str, verb_singular: str) -> str:
    """'page 3 has' / 'pages 5, 6 have'."""
    if len(numbers) == 1:
        return f"page {numbers[0]} {verb_singular}"
    return "pages " + ", ".join(map(str, numbers)) + f" {verb_plural}"


def _explain_duplicates(segments: list) -> None:
    for i, a in enumerate(segments):
        for b in segments[i + 1:]:
            same_number = a.report_number is not None and a.report_number == b.report_number
            a_date, b_date = a.report_date or a.date_text, b.report_date or b.date_text
            same_date = a_date is not None and a_date == b_date
            if same_number and (same_date or a_date is None or b_date is None):
                for x, y in ((a, b), (b, a)):
                    x.warnings.append(f"duplicate of the report on pages {y.page_range} (same report number"
                                      + (" and date" if same_date else "") + ") - review which one to keep")
            elif same_number:
                for x, y in ((a, b), (b, a)):
                    x.warnings.append(f"report number {x.report_number} also appears on pages {y.page_range} "
                                      f"with another date")
            elif same_date and a.report_number is None and b.report_number is None:
                for x, y in ((a, b), (b, a)):
                    x.warnings.append(f"same report date as pages {y.page_range} and no report number - "
                                      "possibly the same report")


def _finish(segment: ReportSegment, expected_well: Optional[str]) -> None:
    if segment.continuation_pages:
        many = len(segment.continuation_pages) > 1
        segment.warnings.append(_pages(segment.continuation_pages, "have", "has") + " no report header and "
                                + ("are read as continuation pages" if many else "is read as a continuation page"))
    if segment.no_text_pages:
        segment.warnings.append(_pages(segment.no_text_pages, "have", "has")
                                + " no text layer (scanned?) - OCR not run; assigned to this report by position")
    if expected_well and segment.well and _well_key(segment.well) != _well_key(expected_well):
        segment.warnings.append(f"well '{segment.well}' on the page differs from the selected well - "
                                "check before importing (suggestion only)")
    reasons = []
    if segment.report_number is None:
        reasons.append("no report number")
    if segment.report_date is None:
        reasons.append("report date not read" if segment.date_text else "no report date")
    if segment.well is None:
        reasons.append("no well name")
    if segment.no_text_pages:
        reasons.append("pages without text")
    if any("duplicate" in w or "another date" in w or "differs" in w for w in segment.warnings):
        reasons.append("conflict to review")
    segment.reasons = reasons
    if not reasons:
        segment.confidence = "high"
    elif segment.report_number is None and segment.report_date is None:
        segment.confidence = "low"
    elif len(reasons) == 1 and reasons[0] == "no well name":
        segment.confidence = "medium"
    else:
        segment.confidence = "medium" if len(reasons) <= 2 else "low"


# ---- PDF I/O ---------------------------------------------------------------------------------------------
def page_texts(pdf_path) -> list:
    """Text layer of every page.  Raises PdfSplitError when the file cannot be read."""
    try:
        import fitz
    except ImportError as exc:      # PyMuPDF is a locked dependency; absent only in a broken install
        raise PdfSplitError("PyMuPDF is not available") from exc
    try:
        with fitz.open(str(pdf_path)) as doc:
            return [page.get_text() for page in doc]
    except Exception as exc:        # fitz raises several private types for damaged files
        raise PdfSplitError(f"PDF could not be read ({type(exc).__name__})") from exc


def analyse_pdf(pdf_path, *, expected_well: Optional[str] = None) -> SplitResult:
    return split_reports(page_texts(pdf_path), expected_well=expected_well)


def _free_name(folder: Path, name: str) -> Path:
    target = folder / name
    stem, suffix, n = target.stem, target.suffix, 2
    while target.exists():
        target = folder / f"{stem} ({n}){suffix}"
        n += 1
    return target


def write_segments(pdf_path, segments: Iterable[ReportSegment], folder) -> list:
    """One PDF per report segment in ``folder``; existing files are never overwritten."""
    import fitz
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stem = Path(pdf_path).stem
    written = []
    with fitz.open(str(pdf_path)) as source:
        for index, segment in enumerate(segments, 1):
            label = f"report-{segment.report_number}" if segment.report_number is not None else f"part-{index}"
            target = _free_name(folder, f"{stem}_{label}_p{segment.page_range}.pdf")
            with fitz.open() as out:
                for number in segment.pages:
                    out.insert_pdf(source, from_page=number - 1, to_page=number - 1)
                out.save(str(target))
            written.append(target)
    return written


def expected_well_name(db_manager, well_id) -> Optional[str]:
    """Name of the selected well for the well-mismatch suggestion; None when unknown or unreadable."""
    if db_manager is None or not well_id:
        return None
    from core.database import Well
    try:
        with db_manager.session_scope() as session:
            well = session.get(Well, well_id)
            return well.name if well is not None else None
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Selected well name could not be read: %s", type(exc).__name__)
        return None
