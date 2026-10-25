"""M45: Persian/Arabic normalisation of the offline document search.

Normalisation applies to the index and the query only.  The stored text is
never rewritten and snippets/highlights are taken from the original text.
SYNTHETIC text only; no network.
"""
import sqlite3

import pytest
from sqlalchemy import text

from core import search_normalization as sn
from core.document_library import DocumentLibrary, extract_document
from document_link_fixtures import (
    ARABIC_KAF, ARABIC_TEXT, ARABIC_YEH, PERSIAN_KAF, PERSIAN_YEH, ZWNJ, without_session_user,
)
from test_scope_attribution import _mgr


# ------------------------------------------------------------- unit rules
def test_letter_forms_digits_and_marks_are_normalised():
    assert sn.normalize(f"{ARABIC_YEH}{ARABIC_KAF}\u0649") == f"{PERSIAN_YEH}{PERSIAN_KAF}{PERSIAN_YEH}"
    assert sn.normalize("۲۵۰۰ ٢٥٠٠ 2500") == "2500 2500 2500"
    assert sn.normalize(f"می{ZWNJ}شود") == "میشود"
    assert sn.normalize("كِتَاب") == "کتاب"                       # harakat removed, kaf normalised
    assert sn.normalize("بـــزرگ") == "بزرگ"                       # tatweel removed


def test_distinct_letters_are_not_merged():
    for a, b in (("آب", "اب"), ("ة", "ه"), ("أ", "ا"), ("ؤ", "و")):
        assert sn.normalize(a) != sn.normalize(b)
    assert sn.normalize("Casing SHOE") == "Casing SHOE"            # case is left to FTS5 (unicode61)


def test_origin_map_points_back_to_the_original_characters():
    original = f"ك{ZWNJ}ـي 7"
    normalised, origin = sn.normalize_with_map(original)
    assert normalised == "کی 7"
    assert [original[i] for i in origin] == ["ك", "ي", " ", "7"]


def test_find_spans_are_spans_of_the_original_text():
    original = f"گزارش مصنوع{ARABIC_YEH} و {ARABIC_KAF}{ARABIC_YEH}سینگ"
    spans = sn.find_spans(original, ["مصنوعی", "کیس"])
    assert [original[s:e] for s, e in spans] == [f"مصنوع{ARABIC_YEH}", f"{ARABIC_KAF}{ARABIC_YEH}س"]
    half = f"این روش می{ZWNJ}شود"
    (span,) = sn.find_spans(half, ["میشود"])
    assert half[span[0]:span[1]] == f"می{ZWNJ}شود"                  # the half-space stays in the span
    assert sn.find_spans("SYNTHETIC CASING", ["casing"]) == [(10, 16)]
    assert sn.find_spans("recasing", ["casing"]) == []               # word prefixes only (FTS semantics)
    assert sn.find_spans("", ["x"]) == [] and sn.find_spans("text", []) == []


def test_query_parsing_keeps_identifiers_and_phrases_together():
    assert sn.parse_query("SYN-DEV-01 فشار ۲۵۰۰") == [["SYN", "DEV", "01"], ["فشار"], ["2500"]]
    assert sn.parse_query('"casing shoe" test') == [["casing", "shoe"], ["test"]]
    assert sn.parse_query("  ") == [] and sn.parse_query("-- ++") == []
    assert len(sn.query_terms(" ".join(f"w{i}" for i in range(30)))) == sn.MAX_TERMS


def test_match_expression_adds_a_joined_alternative_only_for_persian_pairs():
    assert sn.fts_match_expression([["drill"], ["pipe"]]) == '"drill"* AND "pipe"*'
    assert sn.fts_match_expression([["SYN", "DEV", "01"]]) == '"SYN DEV 01"'          # exact phrase, no prefix
    expression = sn.fts_match_expression([["می"], ["شود"]])
    assert expression == '("می"* AND "شود"*) OR ("میشود"*)'
    assert sn.fts_match_expression([]) == ""


def test_snippet_shows_the_original_text_with_marked_matches():
    snippet = sn.make_snippet(ARABIC_TEXT, ["مصنوعی"])
    assert f"[مصنوع{ARABIC_YEH}]" in snippet and PERSIAN_YEH not in snippet
    assert sn.make_snippet("SYNTHETIC text", ["absent"]) == "SYNTHETIC text"
    assert sn.line_of("a\nb\nc", 4) == 3 and sn.line_of("abc", 0) == 1


# ------------------------------------------------------ library fixtures
CORPUS = {
    "syn_arabic_forms.txt": (ARABIC_TEXT, "cp1256"),
    "syn_persian_forms.txt": ("گزارش مصنوعی: کیسینگ ۹ ۵/۸ در عمق ۱۸۰۰ متر\nSYNTHETIC", "utf-8"),
    "syn_half_space.txt": (f"SYNTHETIC: فشار پمپ بررسی می{ZWNJ}شود و نتیجه ثبت می{ZWNJ}گردد", "utf-8"),
    "syn_well_id.txt": ("SYNTHETIC گزارش SYN-DEV-01 فشار 2500 psi در عمق 1250", "utf-8"),
    "syn_other_id.txt": ("SYNTHETIC گزارش SYN-DEV-012 فشار 2500 psi", "utf-8"),
    "syn_mixed.txt": ("SYNTHETIC: پمپ گل با pump pressure بالا کار می‌کند", "utf-8"),
    "syn_noise.txt": ("SYNTHETIC کیس ثبت شد؛ شود، می، کار", "utf-8"),
}


@pytest.fixture
def corpus(tmp_path):
    with without_session_user():
        db = _mgr()
        library = DocumentLibrary(db)
        ids = {}
        for name, (content, encoding) in CORPUS.items():
            path = tmp_path / name
            path.write_bytes(content.encode(encoding))
            outcome = library.import_reviewed(extract_document(path))
            assert outcome.status == "imported", outcome.message
            ids[name] = outcome.document_id
        yield db, library, ids
        library.close()
        db.engine.dispose()


def _files(result):
    return sorted({hit["file_name"] for hit in result["hits"]})


def test_arabic_letter_document_is_found_with_persian_forms_and_back(corpus):
    _db, library, _ids = corpus
    both = ["syn_arabic_forms.txt", "syn_persian_forms.txt"]
    assert _files(library.search("مصنوعی کیسینگ")) == both                     # Persian yeh/keheh typed
    assert _files(library.search(f"مصنوع{ARABIC_YEH} {ARABIC_KAF}{ARABIC_YEH}سینگ")) == both   # Arabic typed


def test_half_space_word_is_found_however_it_is_typed(corpus):
    _db, library, _ids = corpus
    for query in (f"می{ZWNJ}شود", "میشود", "می شود"):
        assert "syn_half_space.txt" in _files(library.search(query)), query


def test_phrase_with_well_id_and_number_is_precise(corpus):
    _db, library, _ids = corpus
    assert _files(library.search("SYN-DEV-01 فشار ۲۵۰۰")) == ["syn_well_id.txt"]   # not SYN-DEV-012
    assert _files(library.search("SYN-DEV-012")) == ["syn_other_id.txt"]
    assert _files(library.search("۱۸۰۰")) == ["syn_persian_forms.txt"]              # Persian digits find 1800
    assert _files(library.search('"pump pressure"')) == ["syn_mixed.txt"]


def test_english_word_inside_persian_text(corpus):
    _db, library, _ids = corpus
    result = library.search("pump")
    assert _files(result) == ["syn_mixed.txt"]
    assert "[pump]" in result["hits"][0]["snippet"]


def test_empty_and_unmatched_queries(corpus):
    _db, library, _ids = corpus
    assert library.search("")["status"] == "invalid_query"
    assert library.search("ـ")["status"] == "invalid_query"                         # only a tatweel
    assert library.search("ناموجود")["status"] == "no_matches"


def test_results_stay_precise(corpus):
    """A normalised word must not drag in pages that only share a fragment."""
    _db, library, _ids = corpus
    assert _files(library.search("کیسینگ")) == ["syn_arabic_forms.txt", "syn_persian_forms.txt"]  # not "کیس"
    assert _files(library.search("گزارش مصنوعی")) == ["syn_arabic_forms.txt", "syn_persian_forms.txt"]
    assert _files(library.search("بررسی")) == ["syn_half_space.txt"]


def test_hits_show_original_text_and_location(corpus):
    db, library, ids = corpus
    (hit,) = [h for h in library.search("مصنوعی کیسینگ")["hits"] if h["file_name"] == "syn_arabic_forms.txt"]
    assert (hit["document_id"], hit["page_no"], hit["line_no"]) == (ids["syn_arabic_forms.txt"], 1, 1)
    assert f"[مصنوع{ARABIC_YEH}]" in hit["snippet"] and f"[{ARABIC_KAF}{ARABIC_YEH}س{ARABIC_YEH}نگ]" in hit["snippet"]
    stored = library.pages(ids["syn_arabic_forms.txt"])[0]["text"]
    assert stored == ARABIC_TEXT                                                   # never rewritten
    assert library.search("SYNTHETIC")["hits"][0]["line_no"] is not None


def test_documents_indexed_before_the_normalisation_are_found_after_rebuild(corpus):
    """Simulate a pre-M45 index (raw text, old signature): the version in the
    signature forces a rebuild from the stored originals on the next search."""
    _db, library, _ids = corpus
    stale = sqlite3.connect(":memory:")
    stale.execute("CREATE VIRTUAL TABLE page_fts USING fts5(body, tokenize='unicode61 remove_diacritics 2')")
    stale.executemany("INSERT INTO page_fts(rowid, body) VALUES (?, ?)", library._all_pages())   # raw, like M44
    session = _db.create_session()
    try:                                       # the M44 signature, computed independently (no version)
        m44_signature = tuple(session.execute(text(
            "SELECT count(id), max(id), sum(length(text)) FROM document_pages")).one())
    finally:
        session.close()
    library._index, library._index_signature = stale, m44_signature
    assert stale.execute("SELECT count(*) FROM page_fts WHERE page_fts MATCH ?", ('"مصنوعی"',)).fetchone()[0] == 1
    assert _files(library.search("مصنوعی")) == ["syn_arabic_forms.txt", "syn_persian_forms.txt"]
    assert library._index is not stale
    info = library.rebuild_index()
    assert info == {"pages": len(CORPUS), "normalization_version": sn.NORMALIZATION_VERSION, "fts": True}


def test_fallback_scan_uses_the_same_normalisation(corpus, monkeypatch):
    _db, library, _ids = corpus
    monkeypatch.setattr(library, "_ensure_index", lambda: None)
    result = library.search("مصنوعی کیسینگ")
    assert result["method"].startswith("Substring scan")
    assert _files(result) == ["syn_arabic_forms.txt", "syn_persian_forms.txt"]
