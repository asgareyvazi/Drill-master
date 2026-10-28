"""Hybrid retrieval over REVIEWED document pages (M49 Knowledge Assistant).

Pipeline (each step is tested in tests/test_m49_knowledge_retrieval.py)::

    read_corpus(db)            stored pages (only reviewer-approved pages are
                               ever stored, see DocumentLibrary.import_reviewed)
                               + user-confirmed links -> CorpusSnapshot
    chunk_page()               paragraph/sentence chunks with exact character
                               offsets into the stored page text
    KnowledgeIndex.retrieve()  1. scope filter (all / well / report / document)
                                  BEFORE ranking - out-of-scope text is never
                                  ranked, returned or shown;
                               2. ranked lists: FTS5 bm25 (OR of the content
                                  terms), bilingual glossary expansion, char
                                  trigram TF-IDF cosine, optional embeddings;
                               3. Reciprocal Rank Fusion, deduplicated;
                               4. sufficiency (IDF-weighted term coverage) and
                                  numeric-conflict detection.

Reciprocal Rank Fusion (Cormack, Clarke & Buettcher, SIGIR 2009):
``score(c) = sum over lists L containing c of 1 / (RRF_K + rank_L(c))`` with
``rank`` starting at 1 and ``RRF_K = 60``.  Ties are broken by chunk id so the
order is reproducible.

Everything here is Qt-free and touches the database only in ``read_corpus``
(called on the thread that owns the session); a worker gets the snapshot.
"""
from __future__ import annotations

import array
import difflib
import hashlib
import math
import re
import sqlite3
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from core.search_normalization import NORMALIZATION_VERSION, normalize, tokens

CHUNKER_VERSION = 1
RETRIEVAL_VERSION = 4            # 2: size designations must match (M49 mutation review)
                                 # 3: entity-code context, expected answer types, size-aware conflicts (M50)
                                 # 4: well identity is a hard constraint, topic-only sufficiency, absent-term
                                 #    veto, heading / file-name context, glossary concepts (M51)
RRF_K = 60
CHUNK_TARGET_CHARS = 700
LIST_DEPTH = 50                 # candidates taken from each ranked list
SUFFICIENT_COVERAGE = 0.6       # IDF-weighted share of the question's content terms
MIN_HIT_COVERAGE = 0.2          # passages below this are not shown as evidence
SUGGESTION_LIMIT = 6            # refinement terms offered after insufficient evidence (M51 §7)
SPELLING_CUTOFF = 0.8           # difflib ratio for an in-scope spelling of a question word
SIZE_MISMATCH_CAP = 0.5         # a passage lacking a size the question names is never sufficient
ANSWER_TYPE_CAP = 0.5           # ... or lacking the kind of quantity the question asks for
IDENTITY_CAP = 0.5              # ... or from a document that is not about the well the question names (M51)
ABSENT_TERM_CAP = 0.5           # ... or when a question word occurs nowhere in scope (partial overlap, M51)
HEADING_MAX_CHARS = 100         # a short first paragraph is the page heading (context for its chunks)
# Generic nouns for the thing an entity code names: covered once the code's identity is established.
ENTITY_NOUNS = frozenset({"well", "wellbore", "چاه"})
# Words that name WHICH ASPECT of a quantity is asked ("size", "result", "average", a unit name) rather
# than the topic: a passage may state the value without them, so their absence from the scope never
# vetoes an answer (they still count in coverage).  Curated, explicit - not semantic.
ATTRIBUTE_WORDS = frozenset("""
size sizes large big small result results value amount achieved obtained reached reading readings average
mean cause causes reason time times metres meters metre meter feet foot inches unit units
اندازه نتیجه علت دلیل میانگین متوسط زمان واحد
""".split())
APPROVED_STATUSES = frozenset({"extracted", "approved", "edited"})

SCOPE_ALL, SCOPE_WELL, SCOPE_REPORT, SCOPE_DOCUMENT = "all", "well", "report", "document"
SCOPES = (SCOPE_ALL, SCOPE_WELL, SCOPE_REPORT, SCOPE_DOCUMENT)

# Function words that carry no retrieval signal (English + Persian).  Kept
# short on purpose: domain words are never stop words.
STOPWORDS = frozenset("""
a an and are as at be by can could did do does for from had has have how i if in into is it its of on or
should than that the their there these this to was were what when where which who why will with would you
your about any all much many according document documents page pages say says said tell me please show give
apply applies applied applying use used using recorded occur occurs occurred happen happened value values
between during after before within through since until each other same also only just been being
از به با در که این آن را برای تا یا و است بود شد شود می‌شود میشود هست نیست چه چی چیست کدام کجا چرا
چگونه چطور آیا هم نیز یک های ها بر روی طبق بنابر مطابق گفته شده سند اسناد صفحه چقدر چند مقدار
داشته دارد دارند داشت بوده کرد کرده کردند شدند گردید گردیده انجام میشوند
بین طی هنگام مورد درباره
""".split())

# Bilingual drilling glossary (English <-> Persian, plus common abbreviations).
# Each line is one concept; a question containing any form also searches the
# others.  This is a curated, explicit list - not "semantic" retrieval.
GLOSSARY_LINES = """
stuck pipe | pipe sticking | differential sticking | گیر لوله | گیرکردن لوله | گیر کردن لوله | گیر کردن رشته
lost circulation | mud losses | loss of circulation | losses | هرزروی | هرز روی گل | هرزروی گل
mud weight | mud density | MW | وزن گل | وزن گل حفاری | چگالی گل
kick | influx | well control | فوران | ورود سیال | کنترل چاه
blowout preventer | BOP | فوران گیر | فورانگیر | بی او پی | بیاوپی
casing | casing shoe | لوله جداری | جداری | کفشک جداری
cement | cementing | سیمان | سیمانکاری
drill bit | bit | مته
rate of penetration | ROP | سرعت حفاری | نرخ نفوذ | سرعت نفوذ
weight on bit | WOB | وزن روی مته
torque | گشتاور
tripping | trip | مانور
pressure test | تست فشار | آزمایش فشار
kick tolerance | تحمل فوران | تحمل ضربه | تحمل کیک
formation | سازند
shale | شیل
mud pump | پمپ گل
repair | تعمیر
duration | مدت | طول کشید
daily report | گزارش روزانه
standpipe pressure | SPP | فشار لوله ایستاده | فشار استندپایپ | فشار لوله عمودی
flow rate | pump rate | circulation rate | دبی | دبی پمپ | دبی جریان | نرخ جریان | نرخ پمپاژ
pump pressure | فشار پمپ
maximum allowable annular surface pressure | MAASP | حداکثر فشار مجاز سطحی حلقوی | فشار مجاز سطحی حلقوی
leak-off test | LOT | تست نشت | آزمایش نشت
formation integrity test | FIT | تست یکپارچگی سازند | آزمایش یکپارچگی سازند
equivalent circulating density | ECD | چگالی معادل در گردش | چگالی معادل گردشی
total depth | final depth | TD | عمق نهایی | عمق کل
depth | عمق
midnight | نیمه شب | نیمهشب
trip tank | مخزن تریپ | تریپ تانک | مخزن مانور
top drive | تاپ درایو | تاپدرایو
working pressure | فشار کاری
function test | تست عملکرد | آزمایش عملکرد
rotary speed | سرعت دورانی | سرعت چرخش | دور میز دوار
drill string | رشته حفاری
vibration | ارتعاش | لرزش
frequency | فرکانس | بسامد
liner | لاینر
slurry | دوغاب
top of cement | cement top | TOC | بالای سیمان | سر سیمان
volume | حجم
hose | شیلنگ
replacement | replaced | changed | تعویض
freed | free | آزاد
procedure | روش اجرا | روش
section | مقطع | بخش
average | mean | میانگین | متوسط
""".strip().splitlines()

_SENTENCE_END = re.compile(r"(?<=[.!?؟۔;؛])\s+|\n+")
_PARAGRAPH = re.compile(r"\n\s*\n")
_NUMBER = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)(?:\s*-\s*\d+/\d+)?")
_PAGE_REF = re.compile(r"(?:\bpage|\bp\.|صفحه)\s*(\d{1,4})", re.IGNORECASE)
UNITS = ("ppg", "sg", "g/cc", "psi", "bar", "kpa", "m", "ft", "in", "bbl", "m3", "klb", "rpm", "%",
         "متر", "پوند", "بشکه")


def fold(text: str) -> str:
    """Search-normalised, case-folded text with Persian decimal/thousands marks
    as ASCII ('۱٫۲۵' -> '1.25'), for matching and number comparison only."""
    return normalize(text or "").replace("\u066b", ".").replace("\u066c", "").casefold()


def words(text: str) -> list:
    return tokens(fold(text))


# ----------------------------------------------------------------- snapshot
@dataclass(frozen=True)
class PageRecord:
    page_id: int
    document_id: int
    file_name: str
    page_no: int
    location: str
    text: str
    method: str
    review_status: str
    text_sha: str                 # sha256 of the stored page text = text version id


@dataclass
class CorpusSnapshot:
    pages: dict                                   # page_id -> PageRecord
    doc_wells: dict                               # document_id -> {well_id}
    doc_reports: dict                             # document_id -> {report_id}
    signature: tuple
    documents: dict = field(default_factory=dict)  # document_id -> file name
    excluded_pages: int = 0                        # stored pages refused by the approval rule
    well_names: dict = field(default_factory=dict)  # well_id -> (name, code): identity of linked wells (M51)

    def documents_in_scope(self, scope: str, target: Optional[int]) -> set:
        docs = set(self.documents)
        if scope == SCOPE_ALL:
            return docs
        if target is None:
            return set()
        if scope == SCOPE_DOCUMENT:
            return {target} & docs
        if scope == SCOPE_WELL:
            return {d for d in docs if target in self.doc_wells.get(d, ())}
        if scope == SCOPE_REPORT:
            return {d for d in docs if target in self.doc_reports.get(d, ())}
        raise ValueError(f"Unknown scope {scope!r}")


def _begin_read(session) -> None:
    """Run every following query of ``session`` in ONE SQLite read transaction.

    pysqlite does not BEGIN for SELECT statements, so two queries of one
    session can otherwise see two database states; the signature and the
    snapshot of a corpus must describe the same state (M51).  Ended by the
    session's close (rollback)."""
    raw = session.connection().connection.dbapi_connection
    if getattr(raw, "in_transaction", True) is False:
        raw.execute("BEGIN")


def _page_rows(session):
    from core.database import Document, DocumentPage
    return (session.query(DocumentPage.id, DocumentPage.document_id, Document.file_name, DocumentPage.page_no,
                          DocumentPage.location, DocumentPage.text, DocumentPage.method,
                          DocumentPage.review_status)
            .join(Document, DocumentPage.document_id == Document.id)
            .order_by(DocumentPage.document_id, DocumentPage.page_no, DocumentPage.id).all())


def _well_rows(session) -> dict:
    from core.database import Well
    return {well_id: (name or "", code or "") for well_id, name, code in
            session.query(Well.id, Well.name, Well.code).order_by(Well.id).all()}


def _content_digest(rows, documents, wells=None) -> str:
    """Digest of every stored page's identity, position, method, review status
    and text version, of every document name and of every well name / code
    (M51; well identity is a retrieval constraint).  A same-length text edit, a
    review-status change, a delete + re-import that reuses ids with different
    text or a well rename all change it; identical content gives the same digest."""
    digest = hashlib.blake2b(digest_size=16)
    for page_id, doc_id, _name, page_no, location, text, method, status in rows:
        digest.update(repr((page_id, doc_id, page_no, location, method, status)).encode("utf-8"))
        digest.update(hashlib.sha256((text or "").encode("utf-8")).digest())
    digest.update(repr(sorted(documents.items())).encode("utf-8"))
    digest.update(repr(sorted((wells or {}).items())).encode("utf-8"))
    return digest.hexdigest()


def corpus_signature(db_manager, session=None, content=None) -> tuple:
    """Fingerprint of everything an answer depends on.

    Counts / max page id / total length, the latest ``document_*`` audit id
    (imports and deletes write one in the same transaction), a digest of every
    link (create / change / remove) and - M51 - a digest of the content itself
    (``_content_digest``): text version, review status, position and document
    name of every stored page.  It reads every page, so it runs off the GUI
    thread (``tabs/knowledge_assistant.py`` workers).  ``session`` /
    ``content``: computed inside ``read_corpus``'s read transaction from the
    rows it already read (no second read).
    """
    from sqlalchemy import func

    from core.database import AuditLog, Document, DocumentLink, DocumentPage
    own = session is None
    if own:
        session = db_manager.create_session()
    try:
        if own:
            _begin_read(session)
        pages = tuple(session.query(func.count(DocumentPage.id), func.max(DocumentPage.id),
                                    func.sum(func.length(DocumentPage.text))).one())
        audit = session.query(func.max(AuditLog.id)).filter(AuditLog.entity_type == "document").scalar()
        links = session.query(DocumentLink.id, DocumentLink.document_id, DocumentLink.well_id,
                              DocumentLink.report_id).order_by(DocumentLink.id).all()
        link_digest = hashlib.blake2b(repr([tuple(r) for r in links]).encode(), digest_size=12).hexdigest()
        if content is None:
            content = _content_digest(_page_rows(session), dict(session.query(Document.id, Document.file_name).all()),
                                      _well_rows(session))
        return (NORMALIZATION_VERSION, CHUNKER_VERSION, RETRIEVAL_VERSION) + pages + (audit, link_digest, content)
    finally:
        if own:
            session.close()


def read_corpus(db_manager) -> CorpusSnapshot:
    """All stored pages that pass the approval rule, with their links.

    The signature and every row come from ONE read transaction (M51), so the
    snapshot is coherent even while another connection writes."""
    from core.database import Document, DocumentLink
    session = db_manager.create_session()
    try:
        _begin_read(session)
        rows = _page_rows(session)
        links = session.query(DocumentLink.document_id, DocumentLink.well_id, DocumentLink.report_id).all()
        documents = dict(session.query(Document.id, Document.file_name).all())
        wells = _well_rows(session)
        signature = corpus_signature(db_manager, session=session, content=_content_digest(rows, documents, wells))
    finally:
        session.close()
    pages, excluded = {}, 0
    for page_id, doc_id, name, page_no, location, text, method, status in rows:
        if status not in APPROVED_STATUSES:
            excluded += 1
            continue
        text = text or ""
        pages[page_id] = PageRecord(page_id, doc_id, name, page_no, location, text, method, status,
                                    hashlib.sha256(text.encode("utf-8")).hexdigest())
    doc_wells, doc_reports = defaultdict(set), defaultdict(set)
    for doc_id, well_id, report_id in links:
        doc_wells[doc_id].add(well_id)
        if report_id is not None:
            doc_reports[doc_id].add(report_id)
    return CorpusSnapshot(pages, dict(doc_wells), dict(doc_reports), signature, documents, excluded, wells)


# ----------------------------------------------------------------- chunking
@dataclass(frozen=True)
class Chunk:
    chunk_id: str                 # "p<page_id>:<start>-<end>" - stable for a text version
    page_id: int
    start: int                    # character offsets into PageRecord.text
    end: int
    text: str
    text_sha: str                 # page text version
    chunk_sha: str                # sha256(chunker version + chunk text) - embedding cache key


def _spans(text: str, pattern, start: int, end: int):
    position = start
    for match in pattern.finditer(text, start, end):
        if match.start() > position:
            yield position, match.start()
        position = match.end()
    if position < end:
        yield position, end


def _trim(text: str, start: int, end: int):
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def chunk_page(page: PageRecord, target: int = CHUNK_TARGET_CHARS) -> list:
    """Paragraphs, split at sentence ends when longer than ``target``.

    ``chunk.text == page.text[chunk.start:chunk.end]`` always holds, so a
    citation opens and highlights the exact stored passage.
    """
    text, out = page.text, []
    for p_start, p_end in _spans(text, _PARAGRAPH, 0, len(text)):
        p_start, p_end = _trim(text, p_start, p_end)
        if p_end <= p_start:
            continue
        if p_end - p_start <= target:
            pieces = [(p_start, p_end)]
        else:
            pieces, current = [], None
            for s_start, s_end in _spans(text, _SENTENCE_END, p_start, p_end):
                s_start, s_end = _trim(text, s_start, s_end)
                if s_end <= s_start:
                    continue
                if current and s_end - current[0] > target:
                    pieces.append(current)
                    current = None
                current = (current[0], s_end) if current else (s_start, s_end)
            if current:
                pieces.append(current)
        for c_start, c_end in pieces:
            body = text[c_start:c_end]
            if not any(ch.isalnum() for ch in body):
                continue
            chunk_sha = hashlib.sha256(f"{CHUNKER_VERSION}\x00{body}".encode("utf-8")).hexdigest()
            out.append(Chunk(f"p{page.page_id}:{c_start}-{c_end}", page.page_id, c_start, c_end, body,
                             page.text_sha, chunk_sha))
    return out


# ---------------------------------------------------------------- the query
def content_terms(question: str) -> list:
    """Normalised question tokens without function words (order kept, unique)."""
    seen, out = set(), []
    for token in words(question):
        if token in STOPWORDS or (len(token) < 2 and not token.isdigit()):
            continue
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def _glossary():
    concepts = []
    for line in GLOSSARY_LINES:
        forms = [words(form) for form in line.split("|")]
        concepts.append([f for f in forms if f])
    return concepts


GLOSSARY = _glossary()


def _contains(seq: list, sub: list) -> bool:
    n = len(sub)
    return any(seq[i:i + n] == sub for i in range(len(seq) - n + 1))


def identifier_terms(question: str) -> frozenset:
    """Question tokens that name something exactly: numbers, codes written
    with digits or hyphens (SYN-ZZ-99, 9-5/8, QX7) and all-capital
    abbreviations (BOP, LCM).  A missing identifier is a hard miss; a missing
    ordinary word may just be phrased differently."""
    out = set()
    for piece in (question or "").split():
        parts = words(piece)
        raw = piece.strip(".,;:!?؟()[]\"'«»")
        if any(ch.isdigit() for ch in raw) or ("-" in raw and len(parts) > 1) or \
                (len(raw) >= 2 and raw.isascii() and raw.isalpha() and raw.isupper()):
            out.update(parts)
    return frozenset(out)


def code_label(code: tuple) -> str:
    """'syn', 'kg', '07' -> 'SYN-KG-07' (display only)."""
    return "-".join(code).upper()


def entity_codes(question: str) -> tuple:
    """Codes that name one entity, as token tuples: hyphenated words that mix
    letters and digits ("SYN-KE-05" -> ("syn", "ke", "05")).  Size
    designations (no letters) and plain numbers are not entity codes.

    A page names its well once - often in a header paragraph or only in the
    file name - while the facts sit in another chunk.  The parts of an entity
    code therefore also count as covered for a chunk when the WHOLE code
    occurs on the same page or in the document's file name (lexical
    "contextual chunk headers").  Numbers and ordinary words are never
    inherited: a value elsewhere on the page is not evidence for this chunk.
    """
    out = []
    for piece in (question or "").split():
        raw = piece.strip(".,;:!?؟()[]\"'«»،")
        if "-" in raw and any(c.isdigit() for c in raw) and any(c.isalpha() for c in raw):
            parts = tuple(words(raw))
            if len(parts) > 1 and parts not in out:
                out.append(parts)
    return tuple(out)


@dataclass(frozen=True)
class AnswerType:
    """A kind of quantity a question asks for, and how a passage shows it.

    ``frames`` (regexes over the folded question, e.g. "how long") ask for the
    quantity without naming it; their ``frame_words`` ("long", "take") are
    then not content terms.  ``nouns`` name it ("temperature").  A passage
    that has neither a noun nor a ``units`` match cannot answer the question
    and is capped below sufficiency (``ANSWER_TYPE_CAP``) - the counterpart of
    the size rule.  Conservative: only quantities with unambiguous units.
    """
    name: str
    frames: tuple
    frame_words: frozenset
    nouns: tuple
    units: re.Pattern


_TIME_UNITS = r"(?:s|sec|secs|seconds?|min|mins|minutes?|h|hr|hrs|hours?|days?|weeks?|ثانیه|دقیقه|ساعت|روز|هفته)"
ANSWER_TYPES = (
    AnswerType("duration",
               (r"\bhow long\b", r"\bhow much time\b", r"\bhow many (?:seconds|minutes|hours|days|weeks)\b",
                r"چه مدت", r"چقدر طول", r"چند (?:ثانیه|دقیقه|ساعت|روز|هفته)"),
               frozenset("long take takes took taken last lasts lasted time seconds minutes hours days weeks "
                         "طول کشید کشیده ثانیه دقیقه ساعت روز هفته".split()),
               (("duration",), ("مدت",)),
               re.compile(r"\d\s*" + _TIME_UNITS + r"(?![\w/])")),
    AnswerType("frequency", (r"\bhow often\b", r"هر چند"), frozenset({"often", "هر", "تکرار"}),
               (("frequency",), ("interval",)),
               re.compile(r"\bevery\b|\bper\b|\bonce\b|(?<!\w)هر\s")),
    AnswerType("depth", (r"\bhow deep\b", r"چه عمقی", r"\bhow many (?:metres|meters|feet)\b", r"چند متر(?! مکعب)"),
               frozenset({"deep", "عمقی", "متر", "metres", "meters", "feet"}), (("depth",), ("عمق",)),
               re.compile(r"\d\s*(?:m|ft|feet|metres?|meters?|متر|فوت)(?![\w/])")),
    AnswerType("density", (r"\bhow heavy\b",), frozenset({"heavy"}),
               (("density",), ("چگالی",), ("mud", "weight"), ("وزن", "گل")),
               re.compile(r"\d\s*(?:sg|ppg|g/cc|kg/m3)(?![\w/])")),
    AnswerType("temperature", (r"\bhow hot\b", r"چند درجه"), frozenset({"hot", "درجه"}),
               (("temperature",), ("دما",), ("دمای",), ("حرارت",)),
               re.compile(r"°|\bdeg(?:rees?|c|f)?\b|celsius|fahrenheit|درجه|سانتیگراد")),
    AnswerType("pressure", (), frozenset(), (("pressure",), ("فشار",)),
               re.compile(r"\d\s*(?:psi|bar|kpa|mpa)(?![\w/])")),
    AnswerType("volume", (r"\bhow many (?:barrels|bbl)\b", r"چند بشکه"), frozenset({"barrels", "bbl", "بشکه"}),
               (("volume",), ("حجم",)),
               re.compile(r"\d\s*(?:bbl|m3|litres?|liters?|gal|بشکه|لیتر|متر مکعب|مترمکعب)(?![\w/])")),
    AnswerType("power", (), frozenset(), (("power",), ("horsepower",), ("توان",)),
               re.compile(r"\d\s*(?:hp|kw)(?![\w/])")),
    AnswerType("torque", (), frozenset(), (("torque",), ("گشتاور",)),
               re.compile(r"\d\s*(?:kft\.?lbf|ft\.?lbf|lbf\.?ft|kn\.?m|n\.m)")),
)
_SIZE_UNIT_WORDS = frozenset({"inch", "inches", "اینچ"})
# Nouns a size designation names ("the 16 in SECTION"): part of the designation phrase.
DESIGNATED_NOUNS = frozenset("section hole casing shoe liner bit string بخش مقطع حفره جداری لوله کفشک".split())


def answer_types(question: str, terms: list) -> tuple:
    """(types the question asks for, terms without frame words).

    Frame words leave the terms only when their frame is present ("how long
    did ... take"); if that would leave no term, the terms are kept."""
    folded = fold(question or "")
    found, frame_words = [], set()
    for kind in ANSWER_TYPES:
        framed = any(re.search(pattern, folded) for pattern in kind.frames)
        if framed:
            frame_words |= kind.frame_words
        if framed or any(phrase_in(terms, list(noun)) for noun in kind.nouns):
            found.append(kind)
    kept = [t for t in terms if t not in frame_words]
    return tuple(found), (kept or terms)


def answer_type_shown(kind: AnswerType, toks: list, folded_text: str) -> bool:
    return any(phrase_in(toks, list(noun)) for noun in kind.nouns) or bool(kind.units.search(folded_text))


_VULGAR = {"½": "-1/2", "¼": "-1/4", "¾": "-3/4", "⅛": "-1/8", "⅜": "-3/8", "⅝": "-5/8", "⅞": "-7/8"}
_INCH = r'(?:in\b|inch(?:es)?\b|"|″|اینچ)'
# "17-1/2", "12 1/4", "9-5/8" (a fraction makes it a size even without a unit),
# or a whole number of at most two digits followed by an inch unit ("6 in").
_SIZE_FRACTION = re.compile(r"(?<![\d./-])(\d{1,2})(?:\s*-\s*|\s)(\d{1,2}/\d{1,2})(?![\d/])")
_SIZE_WHOLE = re.compile(r"(?<![\d./-])(\d{1,2})\s*-?\s*" + _INCH)


def size_designations(text: str) -> frozenset:
    """Normalised size designations in ``text`` ("17-1/2", "6").

    A question that names a hole/casing size asks about THAT size: a passage
    about another size (12-1/4 in vs 17-1/2 in) must never be sufficient,
    although its loose tokens ("1", "2") may occur in it.  Conservative on
    purpose: whole numbers count only with an inch unit and at most two
    digits, and never as the tail of a decimal or a longer number.
    """
    folded = fold(text or "")
    for char, fraction in _VULGAR.items():
        folded = folded.replace(char, fraction)
    found = {f"{whole}-{fraction}" for whole, fraction in _SIZE_FRACTION.findall(folded)}
    covered = {m.span() for m in _SIZE_FRACTION.finditer(folded)}
    for match in _SIZE_WHOLE.finditer(folded):
        start = match.start()
        if not any(a <= start < b for a, b in covered):
            found.add(match.group(1))
    return frozenset(found)


_EN_SUFFIXES = ("ing", "ed", "es", "s")


def _en_stem(word: str) -> str:
    """Strip one English inflection ('rating' / 'rated' -> 'rat', 'pumps' -> 'pump'); index-only."""
    if word.isascii() and word.isalpha():
        for suffix in _EN_SUFFIXES:
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                return word[:-len(suffix)]
    return word


def _term_matches(term: str, word: str) -> bool:
    """Exact; word starts with the term (>= 3 chars); the same English stem
    after one inflection ('rating' ~ 'rated', 'pumps' ~ 'pump', M51); or a
    shared stem of ``max(4, len(term) - 2)`` characters for terms of 5+
    characters ('tolerate' ~ 'tolerance', 'drilled' ~ 'drilling').  Digits
    match exactly."""
    if word == term:
        return True
    if term.isdigit() or word.isdigit():
        return False
    if len(term) >= 3 and word.startswith(term):
        return True
    if _en_stem(term) == _en_stem(word) != term:
        return True
    stem = max(4, len(term) - 2)
    return len(term) >= 5 and len(word) >= stem and word[:stem] == term[:stem]


def phrase_in(toks: list, form: list) -> bool:
    """``form`` occurs as consecutive tokens, each matched by ``_term_matches``
    ('pressure test' ~ 'pressure tested')."""
    n = len(form)
    if n == 1:
        return any(_term_matches(form[0], w) for w in toks)
    return any(all(_term_matches(f, w) for f, w in zip(form, toks[i:i + n])) for i in range(len(toks) - n + 1))


def concept_units(terms: list) -> dict:
    """{term: all forms of its concept} for multi-word glossary forms that
    occur, in order, in the question's content terms."""
    units = {}
    for forms in GLOSSARY:
        for form in forms:
            if len(form) > 1 and _contains(terms, form):
                for word in form:
                    units.setdefault(word, forms)
    return units


def glossary_expansions(question: str) -> list:
    """Alternative phrasings (token lists) of glossary concepts in the question."""
    toks = words(question)
    joined = "".join(toks)
    out = []
    for forms in GLOSSARY:
        if any(_contains(toks, form) or (len(form) > 1 and "".join(form) in joined) for form in forms):
            out.extend(form for form in forms if not _contains(toks, form))
    return out


def requested_page(question: str) -> Optional[int]:
    """'page 7' / 'صفحه ۷' in the question restricts evidence to that page number."""
    match = _PAGE_REF.search(fold(question))
    return int(match.group(1)) if match else None


def _fts_quote(token: str) -> str:
    return '"' + token.replace('"', '""') + '"'


def _trigrams(text: str) -> Counter:
    grams = Counter()
    for word in tokens(text):
        padded = f" {word} "
        if len(padded) <= 3:
            grams[padded] += 1
            continue
        for i in range(len(padded) - 2):
            grams[padded[i:i + 3]] += 1
    return grams


def _cosine(a: dict, b: dict, norm_a: float, norm_b: float) -> float:
    if not norm_a or not norm_b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return sum(w * b.get(k, 0.0) for k, w in a.items()) / (norm_a * norm_b)


def rrf_fuse(ranked_lists: dict, k: int = RRF_K) -> list:
    """[(chunk_id, score, {list_name: rank})] sorted by score desc, then id."""
    scores, ranks = defaultdict(float), defaultdict(dict)
    for name, ids in ranked_lists.items():
        for rank, chunk_id in enumerate(ids, start=1):
            if name in ranks[chunk_id]:
                continue            # a list may not vote twice for one chunk
            ranks[chunk_id][name] = rank
            scores[chunk_id] += 1.0 / (k + rank)
    return sorted(((cid, scores[cid], ranks[cid]) for cid in scores), key=lambda item: (-item[1], item[0]))


# ------------------------------------------------------------ embeddings
STORE_TABLES = frozenset({"vectors", "builds"})


class EmbeddingStore:
    """Vectors keyed by (model, dimensions, chunker version, chunk sha).

    A changed page has new chunk shas, so its old vectors are never used;
    another model or dimension count never collides.  ``complete`` is written
    only after every chunk of a corpus signature has a vector, so a cancelled
    or crashed build is never reported ready.  The file lives in the user-data
    folder next to the database (never in the repository).
    """

    def __init__(self, path: str = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        foreign = {name for (name,) in self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")} - STORE_TABLES
        if foreign:
            # Never create cache tables inside another database (for example
            # the application database): the store owns its file exclusively.
            self._conn.close()
            raise ValueError(f"Refusing to use {Path(path).name!r} as the embedding cache: it holds other tables")
        self._conn.executescript(
            "CREATE TABLE IF NOT EXISTS vectors (model TEXT NOT NULL, dims INTEGER NOT NULL, chunker INTEGER NOT NULL,"
            " chunk_sha TEXT NOT NULL, vector BLOB NOT NULL, PRIMARY KEY (model, dims, chunker, chunk_sha));"
            "CREATE TABLE IF NOT EXISTS builds (model TEXT NOT NULL, chunker INTEGER NOT NULL, signature TEXT NOT NULL,"
            " dims INTEGER NOT NULL, chunks INTEGER NOT NULL, PRIMARY KEY (model, chunker, signature));")
        self._conn.commit()

    def get(self, model: str, chunk_shas: list, dims: Optional[int] = None) -> dict:
        """{chunk_sha: (dims, vector)}; with ``dims`` only vectors of that size."""
        out = {}
        with self._lock:
            for i in range(0, len(chunk_shas), 500):
                part = chunk_shas[i:i + 500]
                marks = ",".join("?" * len(part))
                for sha, d, blob in self._conn.execute(
                        f"SELECT chunk_sha, dims, vector FROM vectors WHERE model=? AND chunker=? AND chunk_sha IN ({marks})",
                        [model, CHUNKER_VERSION, *part]):
                    vector = array.array("f")
                    vector.frombytes(blob)
                    if len(vector) == d and (dims is None or d == dims):
                        out[sha] = (d, vector)
        return out

    def put(self, model: str, items: list) -> None:
        """items: [(chunk_sha, vector)] - committed per batch (idempotent)."""
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO vectors (model, dims, chunker, chunk_sha, vector) VALUES (?, ?, ?, ?, ?)",
                [(model, len(v), CHUNKER_VERSION, sha, array.array("f", v).tobytes()) for sha, v in items])
            self._conn.commit()

    def mark_complete(self, model: str, signature: str, dims: int, chunks: int) -> None:
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO builds VALUES (?, ?, ?, ?, ?)",
                               (model, CHUNKER_VERSION, signature, dims, chunks))
            self._conn.commit()

    def is_complete(self, model: str, signature: str) -> bool:
        return self.build_dims(model, signature) is not None

    def build_dims(self, model: str, signature: str) -> Optional[int]:
        """Vector size of the complete build for (model, signature), or None."""
        with self._lock:
            row = self._conn.execute("SELECT dims FROM builds WHERE model=? AND chunker=? AND signature=?",
                                     (model, CHUNKER_VERSION, signature)).fetchone()
        return None if row is None else int(row[0])

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def default_embedding_store_path(db_manager) -> str:
    db_path = getattr(db_manager, "db_path", ":memory:")
    if not db_path or db_path == ":memory:":
        return ":memory:"
    return str(Path(db_path).expanduser().resolve().parent / "knowledge_cache" / "embeddings-v1.sqlite")


# ---------------------------------------------------------------- results
@dataclass
class RetrievedChunk:
    chunk: Chunk
    page: PageRecord
    score: float
    ranks: dict                   # list name -> rank in that list
    coverage: float               # IDF-weighted share of question terms in this chunk
    entities: tuple = ()          # entity codes (token tuples) the chunk's document is about (M51 verifier)


@dataclass
class Conflict:
    quantity: str                 # the shared term, e.g. "mud weight"
    unit: str
    values: list                  # [(value, chunk_id)]


@dataclass
class RetrievalResult:
    status: str                   # ok | no_evidence | empty_scope | no_documents | no_page | invalid_query
    question: str
    scope: str
    target: Optional[int]
    hits: list                    # [RetrievedChunk]
    terms: list
    expansions: list
    lists_used: list              # names of the ranked lists that ran
    unavailable: list             # [(component, reason)]
    best_coverage: float = 0.0
    missing_terms: list = field(default_factory=list)
    absent_terms: list = field(default_factory=list)   # in NO passage of the scope (checked, no_evidence only)
    conflicts: list = field(default_factory=list)
    scope_documents: int = 0
    scope_pages: int = 0
    page_filter: Optional[int] = None
    corpus_signature: tuple = ()
    strict_terms: frozenset = frozenset()
    entity_codes: tuple = ()      # codes whose parts may be covered by page / file-name context
    answer_types: tuple = ()      # names of the quantity kinds the question asks for
    topic_terms: list = field(default_factory=list)    # terms without entity-code parts: sufficiency (M51)
    constraints: list = field(default_factory=list)    # [(rule, [labels])] hard rules that blocked an answer:
    #   ("identity", ["SYN-KH-08"]) no document in scope is about the named entity;
    #   ("absent", [term, ...])     question words that occur in no passage in scope (partial overlap)
    #   ("other_entity", ["SYN-KH-08"]) a passage would answer, but it is not about the named entity


# ------------------------------------------------------------------ index
class KnowledgeIndex:
    """In-memory retrieval structures for one corpus snapshot."""

    def __init__(self, snapshot: CorpusSnapshot, *, embedding_store: Optional[EmbeddingStore] = None,
                 embed_model: Optional[str] = None):
        self.snapshot = snapshot
        self.signature = snapshot.signature
        self.chunks = {}
        self.page_chunks = defaultdict(list)
        for page in snapshot.pages.values():
            for chunk in chunk_page(page):
                self.chunks[chunk.chunk_id] = chunk
                self.page_chunks[page.page_id].append(chunk.chunk_id)
        self._norm_tokens = {cid: words(c.text) for cid, c in self.chunks.items()}
        self._folded = {cid: fold(c.text) for cid, c in self.chunks.items()}
        self._page_tokens = {pid: words(page.text) for pid, page in snapshot.pages.items()}
        self._name_tokens = {pid: words(page.file_name) for pid, page in snapshot.pages.items()}
        self._doc_pages = defaultdict(list)
        for pid, page in snapshot.pages.items():
            self._doc_pages[page.document_id].append(pid)
        self._context_words = {pid: self._page_context_words(page) for pid, page in snapshot.pages.items()}
        # Chunks that are only the page heading (a short first paragraph followed by more text).
        self._heading_chunks = {cids[0] for cids in self.page_chunks.values()
                                if len(cids) > 1 and len(self.chunks[cids[0]].text) <= HEADING_MAX_CHARS}
        self._chunk_codes = {cid: entity_codes(c.text) for cid, c in self.chunks.items()}
        self._well_labels = {wid: [words(label) for label in labels if label]
                             for wid, labels in snapshot.well_names.items()}
        self._identity_cache = {}
        self._size_cache = {}
        self._lock = threading.Lock()
        self._fts = self._build_fts()
        document_frequency = Counter()
        for toks in self._norm_tokens.values():
            document_frequency.update(set(toks))
        self._df = document_frequency
        self._n = max(1, len(self.chunks))
        idfs = sorted(math.log((self._n + 1) / (df + 0.5)) for df in document_frequency.values())
        self._median_idf = idfs[len(idfs) // 2] if idfs else 1.0
        self._grams, self._gram_norm, self._gram_idf = self._build_trigrams()
        self.embedding_store = embedding_store
        self.embed_model = embed_model or None

    # ------------------------------------------------------------ building
    def _build_fts(self):
        connection = sqlite3.connect(":memory:", check_same_thread=False)
        try:
            connection.execute("CREATE VIRTUAL TABLE chunk_fts USING fts5(body, chunk UNINDEXED, document UNINDEXED,"
                               " tokenize='unicode61 remove_diacritics 2')")
        except sqlite3.OperationalError:
            connection.close()
            return None
        connection.executemany("INSERT INTO chunk_fts(body, chunk, document) VALUES (?, ?, ?)",
                               ((" ".join(self._norm_tokens[cid]), cid, self.snapshot.pages[c.page_id].document_id)
                                for cid, c in self.chunks.items()))
        connection.commit()
        return connection

    def _build_trigrams(self):
        grams = {cid: _trigrams(" ".join(toks)) for cid, toks in self._norm_tokens.items()}
        df = Counter()
        for g in grams.values():
            df.update(g.keys())
        idf = {gram: math.log((1 + self._n) / (1 + count)) + 1.0 for gram, count in df.items()}
        weighted, norms = {}, {}
        for cid, g in grams.items():
            vector = {gram: (1 + math.log(count)) * idf[gram] for gram, count in g.items()}
            weighted[cid] = vector
            norms[cid] = math.sqrt(sum(w * w for w in vector.values()))
        return weighted, norms, idf

    def close(self):
        with self._lock:
            if self._fts is not None:
                self._fts.close()
                self._fts = None

    # -------------------------------------------------------------- scope
    def candidate_chunks(self, scope: str, target: Optional[int], page_no: Optional[int] = None) -> list:
        documents = self.snapshot.documents_in_scope(scope, target)
        out = []
        for cid, chunk in self.chunks.items():
            page = self.snapshot.pages[chunk.page_id]
            if page.document_id in documents and (page_no is None or page.page_no == page_no):
                out.append(cid)
        return out

    # ------------------------------------------------------ ranked lists
    def _idf(self, term: str, strict: frozenset = frozenset()) -> float:
        """IDF over chunks (prefix-aware for 4+ characters).  A term found in no
        chunk weighs the corpus median - unless it is an identifier, which
        keeps the maximum weight, so an unknown code or number pulls coverage
        down hard.  This is a weight, not a veto: when the rest of a question
        matches strongly ("BOP test pressure QX9") a passage can still be
        sufficient - the answer then cites its document and page, and a well
        is meant to be chosen with the scope selector.  Size designations are
        a hard rule instead (see ``size_designations``)."""
        df = sum(count for word, count in self._df.items() if word.startswith(term)) if len(term) >= 4 else \
            self._df.get(term, 0)
        if df == 0 and term not in strict and not term.isdigit():
            return self._median_idf
        return math.log((self._n + 1) / (df + 0.5))

    def _lexical(self, terms: list, allowed: set) -> list:
        if not terms:
            return []
        if self._fts is None:
            return self._scan(terms, allowed)
        expression = " OR ".join(_fts_quote(t) + ("*" if len(t) >= 3 and not t.isdigit() else "") for t in terms)
        with self._lock:
            rows = self._fts.execute("SELECT chunk FROM chunk_fts WHERE chunk_fts MATCH ? ORDER BY bm25(chunk_fts)",
                                     (expression,)).fetchall()
        return [cid for (cid,) in rows if cid in allowed][:LIST_DEPTH]

    def _scan(self, terms: list, allowed: set) -> list:
        scored = []
        for cid in allowed:
            toks = self._norm_tokens[cid]
            score = sum(self._idf(t) for t in terms if any(w.startswith(t) for w in toks))
            if score > 0:
                scored.append((-score, cid))
        return [cid for _, cid in sorted(scored)][:LIST_DEPTH]

    def _phrases(self, phrases: list, allowed: set) -> list:
        scored = []
        for cid in allowed:
            toks = self._norm_tokens[cid]
            hits = sum(1 for phrase in phrases if phrase_in(toks, phrase))
            if hits:
                scored.append((-hits, cid))
        return [cid for _, cid in sorted(scored)][:LIST_DEPTH]

    def _ngram(self, question: str, allowed: set) -> list:
        grams = _trigrams(fold(question))
        query = {g: (1 + math.log(c)) * self._gram_idf[g] for g, c in grams.items() if g in self._gram_idf}
        norm = math.sqrt(sum(w * w for w in query.values()))
        scored = [(-_cosine(query, self._grams[cid], norm, self._gram_norm[cid]), cid) for cid in allowed]
        return [cid for score, cid in sorted(scored) if score < -0.05][:LIST_DEPTH]

    def semantic_state(self) -> tuple:
        """(available, reason)."""
        if self.embedding_store is None or not self.embed_model:
            return False, "Semantic retrieval unavailable: no local embedding model configured"
        if not self.embedding_store.is_complete(self.embed_model, repr(self.signature)):
            return False, "Semantic retrieval unavailable: the semantic index is not built for the current documents"
        return True, ""

    def _semantic(self, query_vector: Optional[list], allowed: set) -> list:
        if query_vector is None:
            return []
        shas = {self.chunks[cid].chunk_sha: cid for cid in allowed}
        stored = self.embedding_store.get(self.embed_model, list(shas), dims=len(query_vector))
        q_norm = math.sqrt(sum(x * x for x in query_vector)) or 1.0
        scored = []
        for sha, (dims, vector) in stored.items():
            if dims != len(query_vector):
                continue
            v_norm = math.sqrt(sum(x * x for x in vector)) or 1.0
            scored.append((-sum(a * b for a, b in zip(query_vector, vector)) / (q_norm * v_norm), shas[sha]))
        return [cid for _, cid in sorted(scored)][:LIST_DEPTH]

    # ----------------------------------------------------------- coverage
    @staticmethod
    def _page_context_words(page: PageRecord) -> list:
        """Tokens a page states for all of its chunks: its heading (a short first
        paragraph followed by more text) and its document's file name ("SYN-KG-07
        daily report.pdf").  Tokens with digits are replaced by a separator -
        numbers are never inherited - and the parts are separated so that no
        phrase spans two of them (M51 contextual chunk headers)."""
        text = page.text or ""
        paragraphs = [p.strip() for p in _PARAGRAPH.split(text) if p.strip()]
        heading = paragraphs[0] if len(paragraphs) > 1 and len(paragraphs[0]) <= HEADING_MAX_CHARS else ""
        out = []
        for part in (heading, page.file_name or ""):
            out.extend("\x00" if any(ch.isdigit() for ch in tok) else tok for tok in words(part))
            out.append("\x00")
        return out

    def identity_established(self, document_id: int, code: tuple) -> bool:
        """The document is about the entity ``code`` names: the whole code occurs in
        one of its approved pages or its file name, or the document is linked to a
        well whose name or code contains it (M51: explicit identity is a hard
        constraint, checked per document because a page states its well once)."""
        key = (document_id, code)
        cached = self._identity_cache.get(key)
        if cached is None:
            sub = list(code)
            cached = any(_contains(self._page_tokens.get(pid, []), sub) or _contains(self._name_tokens.get(pid, []), sub)
                         for pid in self._doc_pages.get(document_id, ())) or \
                any(_contains(label, sub) for wid in self.snapshot.doc_wells.get(document_id, ())
                    for label in self._well_labels.get(wid, ()))
            self._identity_cache[key] = cached
        return cached

    def document_entities(self, document_id: int) -> tuple:
        """Entity codes a document is about: written in one of its approved pages or
        its file name, or the name / code of a well it is linked to (sorted)."""
        key = ("entities", document_id)
        cached = self._identity_cache.get(key)
        if cached is None:
            found = set()
            for pid in self._doc_pages.get(document_id, ()):
                page = self.snapshot.pages[pid]
                found.update(entity_codes(page.text))
                found.update(entity_codes(page.file_name or ""))
            for wid in self.snapshot.doc_wells.get(document_id, ()):
                for label in self.snapshot.well_names.get(wid, ()):
                    found.update(entity_codes(label or ""))
            cached = self._identity_cache[key] = tuple(sorted(found))
        return cached

    def names_other_entity(self, chunk_id: str, codes: tuple) -> bool:
        """The passage itself names another entity of the same family (or another
        known well) and not the asked one - e.g. a SYN-KG-07 sentence for a
        SYN-KH-08 question inside a document that mentions both."""
        found = self._chunk_codes.get(chunk_id, ())
        if not found or any(_contains(self._norm_tokens[chunk_id], list(code)) for code in codes):
            return False
        families = {code[0] for code in codes}
        labels = [label for wid_labels in self._well_labels.values() for label in wid_labels]
        return any(other not in codes and (other[0] in families or any(_contains(label, list(other)) for label in labels))
                   for other in found)

    def identity_ok(self, chunk_id: str, codes: tuple) -> bool:
        if not codes:
            return True
        document_id = self.snapshot.pages[self.chunks[chunk_id].page_id].document_id
        return all(self.identity_established(document_id, code) for code in codes) and \
            not self.names_other_entity(chunk_id, codes)

    def chunk_context(self, chunk_id: str, terms: list, codes: tuple = (), kinds: tuple = (),
                      sizes: frozenset = frozenset()) -> tuple:
        """(extra tokens, covered terms) a chunk inherits (M51).

        * page heading and file-name words (``_page_context_words``);
        * entity-code parts, and generic entity nouns ("well", "چاه"), once the
          document's identity is established;
        * the single-word noun of an asked quantity kind when the chunk shows a
          value of that kind ("power" / 1600 hp);
        * the noun of a size designation ("hole", "section") when the chunk
          names the asked size.
        """
        page_id = self.chunks[chunk_id].page_id
        covered = set(self.context_covered(page_id, codes)) if codes else set()
        if codes and self.identity_ok(chunk_id, codes):
            covered.update(part for code in codes for part in code)
            covered.update(t for t in terms if t in ENTITY_NOUNS)
        for kind in kinds:
            if kind.units.search(self._folded[chunk_id]):
                covered.update(noun[0] for noun in kind.nouns if len(noun) == 1)
        if sizes and sizes <= self._sizes(chunk_id):
            covered.update(t for t in terms if t in DESIGNATED_NOUNS)
        return self._context_words.get(page_id, []), frozenset(covered)

    def context_covered(self, page_id: int, codes: tuple) -> frozenset:
        """Parts of the entity ``codes`` whose whole code occurs, as exact
        consecutive tokens, in the page text or the document file name."""
        out = set()
        for code in codes:
            if _contains(self._page_tokens.get(page_id, []), list(code)) or \
                    _contains(self._name_tokens.get(page_id, []), list(code)):
                out.update(code)
        return frozenset(out)

    def coverage(self, terms: list, expansions_by_term: dict, chunk_id: str, strict: frozenset = frozenset(),
                 codes: tuple = (), kinds: tuple = (), sizes: frozenset = frozenset()) -> tuple:
        extra, context = self.chunk_context(chunk_id, terms, codes, kinds, sizes)
        return self.text_coverage(terms, expansions_by_term, self._norm_tokens[chunk_id] + ["\x00"] + extra, strict,
                                  context)

    def text_coverage(self, terms: list, expansions_by_term: dict, toks: list,
                      strict: frozenset = frozenset(), context: frozenset = frozenset()) -> tuple:
        """(IDF-weighted share of ``terms`` present in ``toks``, missing terms).

        A multi-word glossary concept written in the question ("mud weight")
        is one unit: its words count only where one of the concept's forms
        occurs as a phrase, so the "weight" of "weight on bit" does not cover it.
        ``context`` holds entity-code parts already established by the page or
        file name (see :meth:`context_covered`); they count as present.
        """
        units = concept_units(terms)
        total, covered, missing = 0.0, 0.0, []
        for term in terms:
            weight = max(self._idf(term, strict), 0.1)
            forms = units[term] if term in units else [[term]] + expansions_by_term.get(term, [])
            hit = term in context or any(phrase_in(toks, form) for form in forms)
            if hit:
                covered += weight
            elif term in ATTRIBUTE_WORDS and len(terms) > 1:
                missing.append(term)    # reported, but names an aspect ("size", "average") a passage may
                continue                # state the value without: not counted against coverage
            else:
                missing.append(term)
            total += weight
        return (covered / total if total else 0.0), missing

    def _sizes(self, chunk_id: str) -> frozenset:
        cached = self._size_cache.get(chunk_id)
        if cached is None:
            cached = self._size_cache[chunk_id] = size_designations(self.chunks[chunk_id].text)
        return cached

    def answer_type_missing(self, kinds: tuple, chunk_id: str) -> list:
        """Names of the asked-for quantity kinds the chunk does not show.  A page
        heading names a subject, never its value: it must show the unit (M51)."""
        if chunk_id in self._heading_chunks:
            return [k.name for k in kinds if not k.units.search(self._folded[chunk_id])]
        return [k.name for k in kinds
                if not answer_type_shown(k, self._norm_tokens[chunk_id], self._folded[chunk_id])]

    def absent_terms(self, terms: list, expansions_by_term: dict, allowed: set, codes: tuple = (),
                     kinds: tuple = (), sizes: frozenset = frozenset()) -> list:
        """Question terms that occur in no passage of ``allowed`` - checked
        with the same matching rule and context as :meth:`coverage`, so an
        insufficient-evidence message never claims a word is missing when some
        passage in scope contains it."""
        present = set()
        for cid in allowed:
            _cov, missing = self.coverage(terms, expansions_by_term, cid, codes=codes, kinds=kinds, sizes=sizes)
            present.update(t for t in terms if t not in missing)
            if len(present) == len(terms):
                break
        return [t for t in terms if t not in present]

    # ----------------------------------------------------------- retrieve
    def retrieve(self, question: str, scope: str = SCOPE_ALL, target: Optional[int] = None, *, top_k: int = 6,
                 query_vector: Optional[list] = None, use_ngram: bool = True, use_glossary: bool = True,
                 cancelled: Callable[[], bool] = lambda: False) -> RetrievalResult:
        if scope not in SCOPES:
            raise ValueError(f"Unknown scope {scope!r}")
        terms = content_terms(question)
        page_filter = requested_page(question)
        if page_filter is not None:
            terms = [t for t in terms if t not in ("page", "صفحه", str(page_filter))]
        result = RetrievalResult("ok", question, scope, target, [], terms, [], [], [], page_filter=page_filter,
                                 corpus_signature=self.signature)
        if not self.snapshot.pages:
            result.status = "no_documents"
            return result
        scoped_docs = self.snapshot.documents_in_scope(scope, target)
        scoped = self.candidate_chunks(scope, target)
        result.scope_documents = len(scoped_docs)
        result.scope_pages = len({self.chunks[c].page_id for c in scoped})
        if not scoped:
            result.status = "empty_scope"
            return result
        if page_filter is not None:
            scoped = [c for c in scoped if self.snapshot.pages[self.chunks[c].page_id].page_no == page_filter]
            if not scoped:
                result.status = "no_page"
                return result
        if not terms:
            result.status = "invalid_query"
            return result
        allowed = set(scoped)
        sizes = size_designations(question)
        if sizes:   # the size rule enforces "12-1/4 in"; the unit word itself is not a content term
            terms = [t for t in terms if t not in _SIZE_UNIT_WORDS] or terms
        kinds, terms = answer_types(question, terms)
        codes = entity_codes(question)
        result.terms, result.entity_codes, result.answer_types = terms, codes, tuple(k.name for k in kinds)
        strict = identifier_terms(question)
        result.strict_terms = strict
        expansions = glossary_expansions(question) if use_glossary else []
        result.expansions = [" ".join(e) for e in expansions]
        lists = {"lexical": self._lexical(terms, allowed)}
        if expansions:
            lists["glossary"] = self._phrases(expansions, allowed)
        if use_ngram and not cancelled():
            lists["ngram"] = self._ngram(question, allowed)
        semantic_ok, reason = self.semantic_state()
        if semantic_ok and query_vector is not None:
            built = self.embedding_store.build_dims(self.embed_model, repr(self.signature))
            if built != len(query_vector):
                reason = (f"Semantic retrieval unavailable: the index was built with {built}-dimensional vectors, "
                          f"the model now returns {len(query_vector)}; rebuild the semantic index")
                semantic_ok, query_vector = False, None
        if semantic_ok and query_vector is not None:
            lists["semantic"] = self._semantic(query_vector, allowed)
        elif not semantic_ok:
            result.unavailable.append(("semantic", reason))
        else:
            result.unavailable.append(("semantic", "Semantic retrieval unavailable: the question could not be embedded"))
        if self._fts is None:
            result.unavailable.append(("fts5", "SQLite FTS5 unavailable; lexical retrieval uses a scan"))
        result.lists_used = [name for name, ids in lists.items() if ids is not None]
        fused = rrf_fuse(lists)
        # Every fused id came from the allowed set; assert it anyway (scope is a security boundary).
        fused = [item for item in fused if item[0] in allowed]
        fused = self._with_heading_siblings(fused, allowed)
        expansions_by_term = self._expansions_by_term(terms, expansions)
        # M51: an entity code the question names is a hard constraint checked on its own (identity_ok),
        # so sufficiency is measured on the TOPIC terms - a passage that only shares the well code with
        # the question can no longer reach the threshold through the code's high IDF weight.
        code_parts = {part for code in codes for part in code}
        topic = [t for t in terms if t not in code_parts] or terms
        topic_strict = frozenset(strict - code_parts) if topic is not terms else strict
        result.topic_terms = topic
        # Partial overlap: a question word that occurs in no passage in scope (glossary forms and
        # context included) means no passage can answer it, however well the other words match.
        absent_topic = [t for t in self.absent_terms(topic, expansions_by_term, allowed, codes, kinds, sizes)
                        if not t.isdigit() and t not in ATTRIBUTE_WORDS]   # sizes have their own rule
        if absent_topic:
            result.constraints.append(("absent", absent_topic))
        identity_failed = 0
        candidates = []
        for chunk_id, score, ranks in fused:
            cov, _missing = self.coverage(topic, expansions_by_term, chunk_id, topic_strict, codes, kinds, sizes)
            if sizes and not sizes <= self._sizes(chunk_id):
                cov = min(cov, SIZE_MISMATCH_CAP)   # about another size: shown as closest, never sufficient
            if kinds and self.answer_type_missing(kinds, chunk_id):
                cov = min(cov, ANSWER_TYPE_CAP)     # shows no quantity of the asked kind: never sufficient
            if codes and not self.identity_ok(chunk_id, codes):
                if cov >= SUFFICIENT_COVERAGE:
                    identity_failed += 1            # would answer - but it is about another entity
                cov = min(cov, IDENTITY_CAP)        # not about the named well: shown as closest, never sufficient
            if absent_topic:
                cov = min(cov, ABSENT_TERM_CAP)
            if cov < MIN_HIT_COVERAGE:
                continue            # n-gram noise: shares letters but none of the question's terms
            candidates.append((chunk_id, score, ranks, cov))
        # Sufficiency tiers: a passage that can answer is never pushed out of the top k by passages
        # that cannot (e.g. a header naming only the well); fused order is kept inside each tier.
        candidates.sort(key=lambda c: c[3] < SUFFICIENT_COVERAGE)
        hits, seen_pages = [], Counter()
        for chunk_id, score, ranks, cov in candidates:
            chunk = self.chunks[chunk_id]
            if seen_pages[chunk.page_id] >= 2:
                continue            # dedupe: at most two passages per page
            page = self.snapshot.pages[chunk.page_id]
            hits.append(RetrievedChunk(chunk, page, score, ranks, cov, self.document_entities(page.document_id)))
            seen_pages[chunk.page_id] += 1
            if len(hits) >= top_k:
                break
        result.hits = hits
        if hits:
            result.best_coverage = max(h.coverage for h in hits)
            # Explain from the best passage ABOUT the named entity when there is one: the other well's
            # passage is never usable, so its gaps are not the reason (M51).
            best = max(hits, key=lambda h: (self.identity_ok(h.chunk.chunk_id, codes), h.coverage))
            result.missing_terms = self.coverage(topic, expansions_by_term, best.chunk.chunk_id, topic_strict, codes,
                                                 kinds, sizes)[1] + \
                [f"{s} in" for s in sorted(sizes - self._sizes(best.chunk.chunk_id))] + \
                [f"({name})" for name in self.answer_type_missing(kinds, best.chunk.chunk_id)] + \
                [code_label(code) for code in codes if not self.identity_ok(best.chunk.chunk_id, (code,))]
        if identity_failed:
            result.constraints.append(("other_entity", [code_label(code) for code in codes]))
        if codes:
            unmet = [code_label(code) for code in codes
                     if not any(self.identity_established(self.snapshot.pages[self.chunks[cid].page_id].document_id,
                                                          code) for cid in allowed)]
            if unmet:
                result.constraints.append(("identity", unmet))
        if not hits or result.best_coverage < SUFFICIENT_COVERAGE:
            result.status = "no_evidence"
            result.absent_terms = absent_topic + \
                [f"{s} in" for s in sorted(sizes) if not any(s in self._sizes(cid) for cid in allowed)] + \
                dict(result.constraints).get("identity", [])
        result.conflicts = find_conflicts([h for h in hits if h.coverage >= SUFFICIENT_COVERAGE], terms,
                                          expansions)
        return result

    # -------------------------------------------------------- refinement
    def suggest_terms(self, retrieval: RetrievalResult, limit: int = SUGGESTION_LIMIT) -> list:
        """The suggested terms only (see :meth:`refinement`)."""
        return self.refinement(retrieval, limit)[0]

    def refinement(self, retrieval: RetrievalResult, limit: int = SUGGESTION_LIMIT) -> tuple:
        """Technical terms to retry an insufficient-evidence question with (M51 §7).

        Lexical only: glossary alternatives of the question words that blocked
        the answer, and close spellings of them.  A suggestion is offered only
        when it occurs in a passage of the SAME scope (it can never point
        outside it), and never contains a number or an entity code - it can
        refine the wording, not change which well, report or value is asked
        about.  The scope itself is not part of a suggestion.

        Returns ``(suggestions, replaces)``: ``replaces`` are the question
        words the suggestions stand in for (never numbers or code parts)."""
        if retrieval.status != "no_evidence":
            return [], []
        allowed = self.candidate_chunks(retrieval.scope, retrieval.target, retrieval.page_filter)
        if not allowed:
            return [], []
        code_parts = {part for code in retrieval.entity_codes for part in code}
        asked = words(retrieval.question)
        blocked = [t for t in dict.fromkeys([*retrieval.absent_terms, *retrieval.missing_terms])
                   if t in retrieval.terms and len(t) >= 3 and not any(ch.isdigit() for ch in t)
                   and t not in code_parts]                         # question words only, never type labels
        scoped_toks = [self._norm_tokens[cid] for cid in allowed]
        vocabulary = sorted({w for toks in scoped_toks for w in toks if len(w) >= 4 and w.isalpha()})
        out, replaces = [], []

        def offer(form: list, term: str) -> None:
            label = " ".join(form)
            if (len(out) < limit and label not in out and not _contains(asked, form)
                    and not any(ch.isdigit() for ch in label) and not any(w in code_parts for w in form)
                    and any(phrase_in(toks, form) for toks in scoped_toks)):
                out.append(label)
                if term not in replaces:
                    replaces.append(term)

        for term in blocked:
            for forms in GLOSSARY:
                # The concept is about this word: a one-word form of it, or a form the question contains.
                if any(any(_term_matches(term, w) for w in form) and (len(form) == 1 or phrase_in(asked, form))
                       for form in forms):
                    for form in forms:
                        offer(form, term)
            for word in difflib.get_close_matches(term, vocabulary, n=2, cutoff=SPELLING_CUTOFF):
                if word != term:
                    offer([word], term)
        return out, replaces

    def _with_heading_siblings(self, fused: list, allowed: set) -> list:
        """A retrieved page heading ("BOP pressure test procedure") brings the
        other chunks of its page right after it: the facts sit under the
        heading and need not repeat its words (M51).  Same page only, scope
        kept (``allowed``); each sibling is marked with a ``heading`` rank."""
        seen = {cid for cid, _s, _r in fused}
        out = []
        for chunk_id, score, ranks in fused:
            out.append((chunk_id, score, ranks))
            if chunk_id in self._heading_chunks:
                best_rank = min(ranks.values()) if ranks else 0
                for sibling in self.page_chunks[self.chunks[chunk_id].page_id]:
                    if sibling not in seen and sibling in allowed:
                        seen.add(sibling)
                        out.append((sibling, score, {"heading": best_rank}))
        return out

    @staticmethod
    def _expansions_by_term(terms: list, expansions: list) -> dict:
        """A question term is also covered by the glossary forms of its concept."""
        out = {}
        for forms in GLOSSARY:
            flat = {w for form in forms for w in form}
            for term in terms:
                if term in flat:
                    out.setdefault(term, []).extend(form for form in forms if form != [term])
        return out


# -------------------------------------------------------------- conflicts
def _number(text: str) -> Optional[float]:
    try:
        return float(text.replace(",", "."))
    except ValueError:  # silent-ok: not a number - None is this helper's documented result
        return None


_DESIGNATED = re.compile(r"\s*(?:" + "|".join(sorted(DESIGNATED_NOUNS)) + r")\b")


def quantities(text: str, phrases: list, with_sizes: bool = False) -> list:
    """[(phrase, value, unit)] for ``<phrase> ... <number> <unit>`` in one sentence; with ``with_sizes``
    each tuple also carries the size designations that sentence names."""
    out = []
    normalized = fold(text)
    for sentence in re.split(r"[.!?؟\n;؛]+\s", normalized + " "):
        toks = tokens(sentence)
        for phrase in phrases:
            if not phrase or not _contains(toks, phrase):
                continue
            joined = " ".join(phrase)
            index = sentence.find(joined) if joined in sentence else 0
            tail = sentence[index:index + 120]
            # (?<![\d/.-]) skips the "4" of a size designation such as 12-1/4 in.
            for match in re.finditer(r"(?<![\d/.-])(\d+(?:[.,]\d+)?)\s*(" + "|".join(re.escape(u) for u in UNITS)
                                     + r")(?![\w/])", tail):
                if match.group(2) == "in" and _DESIGNATED.match(tail, match.end()):
                    continue        # "the 16 in section": names the section, it is not the quantity
                value = _number(match.group(1))
                if value is not None:
                    out.append((joined, value, match.group(2), size_designations(sentence)) if with_sizes
                               else (joined, value, match.group(2)))
                    break
    return out


def find_conflicts(hits: list, terms: list, expansions: list) -> list:
    """Different values for the same quantity+unit in different DOCUMENTS, for the same hole/casing
    size: 1.08 sg for the 16 in section and 1.25 sg for the 12-1/4 in section do not disagree."""
    phrases = [list(e) for e in expansions] + [[t] for t in terms if not t.isdigit()]
    for forms in GLOSSARY:
        if any(_contains(terms, form) or (len(form) == 1 and form[0] in terms) for form in forms):
            phrases.extend(forms)
    phrases = sorted({tuple(p) for p in phrases if p}, key=len, reverse=True)
    by_key = defaultdict(list)
    for hit in hits:
        for phrase, value, unit, sizes in quantities(hit.chunk.text, [list(p) for p in phrases if len(p) > 1] or [],
                                                     with_sizes=True):
            by_key[(phrase, unit, sizes)].append((value, hit.chunk.chunk_id, hit.page.document_id))
    conflicts = []
    for (phrase, unit, _sizes), values in by_key.items():
        documents = {doc for _, _, doc in values}
        distinct = {value for value, _, _ in values}
        if len(documents) > 1 and len(distinct) > 1:
            conflicts.append(Conflict(phrase, unit, [(value, cid) for value, cid, _ in values]))
    return conflicts


# --------------------------------------------------------- semantic build
def build_semantic_index(index: KnowledgeIndex, adapter, store: EmbeddingStore, *, cancel=None,
                         progress: Callable[[int, int], None] = lambda done, total: None, batch: int = 16) -> dict:
    """Embed every chunk that has no vector for ``adapter.embed_model`` yet.

    Vectors are committed per batch (a rebuild after a crash or cancel
    resumes and is idempotent); the build is marked complete for the corpus
    signature only after the last chunk has a vector, so ``semantic_state``
    never reports a partial index as ready.  Raises LocalLLMError on model
    failures (the caller shows the state; nothing is marked complete).
    """
    model = adapter.embed_model
    chunks = list(index.chunks.values())
    if not chunks:
        return {"state": "empty", "done": 0, "total": 0}
    # Probe the model's current vector size: vectors of another size (an older
    # model under the same name) are never mixed in.
    current = len(adapter.embed(["dimension probe"], cancel)[0])
    have = store.get(model, [c.chunk_sha for c in chunks], dims=current)
    todo = [c for c in chunks if c.chunk_sha not in have]
    dims = {current}
    done = len(chunks) - len(todo)
    progress(done, len(chunks))
    for i in range(0, len(todo), batch):
        if cancel is not None and cancel.cancelled:
            return {"state": "cancelled", "done": done, "total": len(chunks)}
        part = todo[i:i + batch]
        vectors = adapter.embed([c.text for c in part], cancel)
        dims.update(len(v) for v in vectors)
        if len(dims) > 1:
            raise ValueError(f"Embedding model returned different dimensions {sorted(dims)}; index not marked ready")
        store.put(model, [(c.chunk_sha, v) for c, v in zip(part, vectors)])
        done += len(part)
        progress(done, len(chunks))
    store.mark_complete(model, repr(index.signature), dims.pop() if dims else 0, len(chunks))
    index.embedding_store, index.embed_model = store, model
    return {"state": "complete", "done": done, "total": len(chunks)}
