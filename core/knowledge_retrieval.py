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
RETRIEVAL_VERSION = 3            # 2: size designations must match (M49 mutation review)
                                 # 3: entity-code context, expected answer types, size-aware conflicts (M50)
RRF_K = 60
CHUNK_TARGET_CHARS = 700
LIST_DEPTH = 50                 # candidates taken from each ranked list
SUFFICIENT_COVERAGE = 0.6       # IDF-weighted share of the question's content terms
MIN_HIT_COVERAGE = 0.2          # passages below this are not shown as evidence
SIZE_MISMATCH_CAP = 0.5         # a passage lacking a size the question names is never sufficient
ANSWER_TYPE_CAP = 0.5           # ... or lacking the kind of quantity the question asks for
APPROVED_STATUSES = frozenset({"extracted", "approved", "edited"})

SCOPE_ALL, SCOPE_WELL, SCOPE_REPORT, SCOPE_DOCUMENT = "all", "well", "report", "document"
SCOPES = (SCOPE_ALL, SCOPE_WELL, SCOPE_REPORT, SCOPE_DOCUMENT)

# Function words that carry no retrieval signal (English + Persian).  Kept
# short on purpose: domain words are never stop words.
STOPWORDS = frozenset("""
a an and are as at be by can could did do does for from had has have how i if in into is it its of on or
should than that the their there these this to was were what when where which who why will with would you
your about any all much many according document documents page pages say says said tell me please show give
از به با در که این آن را برای تا یا و است بود شد شود می‌شود میشود هست نیست چه چی چیست کدام کجا چرا
چگونه چطور آیا هم نیز یک های ها بر روی طبق بنابر مطابق گفته شده سند اسناد صفحه چقدر چند مقدار
""".split())

# Bilingual drilling glossary (English <-> Persian, plus common abbreviations).
# Each line is one concept; a question containing any form also searches the
# others.  This is a curated, explicit list - not "semantic" retrieval.
GLOSSARY_LINES = """
stuck pipe | pipe sticking | differential sticking | گیر لوله | گیرکردن لوله | گیر کردن رشته
lost circulation | mud losses | loss of circulation | هرزروی | هرز روی گل | هرزروی گل
mud weight | mud density | MW | وزن گل | وزن گل حفاری | چگالی گل
kick | influx | well control | فوران | ورود سیال | کنترل چاه
blowout preventer | BOP | فوران گیر | فورانگیر
casing | casing shoe | لوله جداری | جداری | کفشک جداری
cement | cementing | سیمان | سیمانکاری
drill bit | bit | مته
rate of penetration | ROP | سرعت حفاری | نرخ نفوذ
weight on bit | WOB | وزن روی مته
torque | گشتاور
tripping | trip | مانور
pressure test | تست فشار | آزمایش فشار
kick tolerance | تحمل فوران
formation | سازند
shale | شیل
mud pump | پمپ گل
repair | تعمیر
duration | مدت | طول کشید
daily report | گزارش روزانه
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


def corpus_signature(db_manager) -> tuple:
    """Cheap fingerprint that changes with any import, delete or link change.

    Pages are immutable after import (no page edit path exists); imports and
    deletes always write a ``document_*`` audit row in the same transaction,
    so ``max(audit id)`` catches a delete + re-import that reuses page ids.
    Links are few and are digested completely.
    """
    from sqlalchemy import func

    from core.database import AuditLog, DocumentLink, DocumentPage
    session = db_manager.create_session()
    try:
        pages = tuple(session.query(func.count(DocumentPage.id), func.max(DocumentPage.id),
                                    func.sum(func.length(DocumentPage.text))).one())
        audit = session.query(func.max(AuditLog.id)).filter(AuditLog.entity_type == "document").scalar()
        links = session.query(DocumentLink.id, DocumentLink.document_id, DocumentLink.well_id,
                              DocumentLink.report_id).order_by(DocumentLink.id).all()
        link_digest = hashlib.blake2b(repr([tuple(r) for r in links]).encode(), digest_size=12).hexdigest()
        return (NORMALIZATION_VERSION, CHUNKER_VERSION, RETRIEVAL_VERSION) + pages + (audit, link_digest)
    finally:
        session.close()


def read_corpus(db_manager) -> CorpusSnapshot:
    """All stored pages that pass the approval rule, with their links."""
    from core.database import Document, DocumentLink, DocumentPage
    signature = corpus_signature(db_manager)
    session = db_manager.create_session()
    try:
        rows = (session.query(DocumentPage.id, DocumentPage.document_id, Document.file_name, DocumentPage.page_no,
                              DocumentPage.location, DocumentPage.text, DocumentPage.method,
                              DocumentPage.review_status)
                .join(Document, DocumentPage.document_id == Document.id)
                .order_by(DocumentPage.document_id, DocumentPage.page_no).all())
        links = session.query(DocumentLink.document_id, DocumentLink.well_id, DocumentLink.report_id).all()
        documents = dict(session.query(Document.id, Document.file_name).all())
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
    return CorpusSnapshot(pages, dict(doc_wells), dict(doc_reports), signature, documents, excluded)


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
    AnswerType("frequency", (r"\bhow often\b", r"هر چند"), frozenset({"often"}), (("frequency",), ("interval",)),
               re.compile(r"\bevery\b|\bper\b|\bonce\b|(?<!\w)هر\s")),
    AnswerType("depth", (r"\bhow deep\b", r"چه عمقی"), frozenset({"deep", "عمقی"}), (("depth",), ("عمق",)),
               re.compile(r"\d\s*(?:m|ft|feet|metres?|meters?|متر|فوت)(?![\w/])")),
    AnswerType("density", (r"\bhow heavy\b",), frozenset({"heavy"}),
               (("density",), ("چگالی",), ("mud", "weight"), ("وزن", "گل")),
               re.compile(r"\d\s*(?:sg|ppg|g/cc|kg/m3)(?![\w/])")),
    AnswerType("temperature", (r"\bhow hot\b", r"چند درجه"), frozenset({"hot", "درجه"}),
               (("temperature",), ("دما",), ("دمای",), ("حرارت",)),
               re.compile(r"°|\bdeg(?:rees?|c|f)?\b|celsius|fahrenheit|درجه|سانتیگراد")),
    AnswerType("pressure", (), frozenset(), (("pressure",), ("فشار",)),
               re.compile(r"\d\s*(?:psi|bar|kpa|mpa)(?![\w/])")),
    AnswerType("volume", (), frozenset(), (("volume",), ("حجم",)),
               re.compile(r"\d\s*(?:bbl|m3|litres?|liters?|gal|بشکه|لیتر)(?![\w/])")),
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


def _term_matches(term: str, word: str) -> bool:
    """Exact; word starts with the term (>= 3 chars); or a shared stem of
    ``max(4, len(term) - 2)`` characters for terms of 5+ characters
    ('tolerate' ~ 'tolerance', 'drilled' ~ 'drilling').  Digits match exactly."""
    if word == term:
        return True
    if term.isdigit() or word.isdigit():
        return False
    if len(term) >= 3 and word.startswith(term):
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
                 codes: tuple = ()) -> tuple:
        context = self.context_covered(self.chunks[chunk_id].page_id, codes) if codes else frozenset()
        return self.text_coverage(terms, expansions_by_term, self._norm_tokens[chunk_id], strict, context)

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
            total += weight
            forms = units[term] if term in units else [[term]] + expansions_by_term.get(term, [])
            hit = term in context or any(phrase_in(toks, form) for form in forms)
            if hit:
                covered += weight
            else:
                missing.append(term)
        return (covered / total if total else 0.0), missing

    def _sizes(self, chunk_id: str) -> frozenset:
        cached = self._size_cache.get(chunk_id)
        if cached is None:
            cached = self._size_cache[chunk_id] = size_designations(self.chunks[chunk_id].text)
        return cached

    def answer_type_missing(self, kinds: tuple, chunk_id: str) -> list:
        """Names of the asked-for quantity kinds the chunk does not show."""
        return [k.name for k in kinds
                if not answer_type_shown(k, self._norm_tokens[chunk_id], self._folded[chunk_id])]

    def absent_terms(self, terms: list, expansions_by_term: dict, allowed: set, codes: tuple = ()) -> list:
        """Question terms that occur in no passage of ``allowed`` - checked
        with the same matching rule as :meth:`text_coverage` (entity-code
        context included), so an insufficient-evidence message never claims a
        word is missing when some passage in scope contains it."""
        present = set()
        for cid in allowed:
            context = self.context_covered(self.chunks[cid].page_id, codes) if codes else frozenset()
            _cov, missing = self.text_coverage(terms, expansions_by_term, self._norm_tokens[cid], context=context)
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
        expansions_by_term = self._expansions_by_term(terms, expansions)
        candidates = []
        for chunk_id, score, ranks in fused:
            cov, _missing = self.coverage(terms, expansions_by_term, chunk_id, strict, codes)
            if sizes and not sizes <= self._sizes(chunk_id):
                cov = min(cov, SIZE_MISMATCH_CAP)   # about another size: shown as closest, never sufficient
            if kinds and self.answer_type_missing(kinds, chunk_id):
                cov = min(cov, ANSWER_TYPE_CAP)     # shows no quantity of the asked kind: never sufficient
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
            hits.append(RetrievedChunk(chunk, self.snapshot.pages[chunk.page_id], score, ranks, cov))
            seen_pages[chunk.page_id] += 1
            if len(hits) >= top_k:
                break
        result.hits = hits
        if hits:
            best = max(hits, key=lambda h: h.coverage)
            result.best_coverage = best.coverage
            result.missing_terms = self.coverage(terms, expansions_by_term, best.chunk.chunk_id, strict, codes)[1] + \
                [f"{s} in" for s in sorted(sizes - self._sizes(best.chunk.chunk_id))] + \
                [f"({name})" for name in self.answer_type_missing(kinds, best.chunk.chunk_id)]
        if not hits or result.best_coverage < SUFFICIENT_COVERAGE:
            result.status = "no_evidence"
            result.absent_terms = self.absent_terms(terms, expansions_by_term, allowed, codes) + \
                [f"{s} in" for s in sorted(sizes) if not any(s in self._sizes(cid) for cid in allowed)]
        result.conflicts = find_conflicts([h for h in hits if h.coverage >= SUFFICIENT_COVERAGE], terms,
                                          expansions)
        return result

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
