"""M46: the FTS5 index, the fallback scan and the highlighter agree.

Defects found by the M46 audit (normalisation v1):

* without FTS5 the fallback matched every query word as a word prefix, so the
  identifier ``SYN-DEV-01`` also found ``SYN-DEV-012`` (FTS5 matches it as an
  exact phrase), and a half-space word typed with a space was not found;
* FTS5 (``unicode61 remove_diacritics 2``) splits ``_`` and folds Latin
  diacritics, the Python tokenizer did neither: such FTS5 hits had no
  highlight and no line to open.

SYNTHETIC text only; no network.
"""
import random
import sqlite3

import pytest

from core import search_normalization as sn
from test_search_normalization import _files, corpus  # noqa: F401  (fixture)

QUERIES = [
    "SYN-DEV-01", "SYN-DEV-012", "syn dev", '"فشار 2500"', "2500 psi", "۲۵۰۰", "می شود", "میشود", "می",
    "مصنوعی کیسینگ", "مصنوعي كيسينگ", "pump pressure", "pump", "کیس", "SYNTHETIC", "عمق 1250", "شود",
]


def _fallback(library, monkeypatch, query):
    with monkeypatch.context() as patch:
        patch.setattr(library, "_ensure_index", lambda: None)
        result = library.search(query)
    assert result["method"].startswith("Substring scan")
    return result


def test_fallback_keeps_identifier_precision(corpus, monkeypatch):  # noqa: F811
    _db, library, _ids = corpus
    assert _files(library.search("SYN-DEV-01")) == ["syn_well_id.txt"]
    assert _files(_fallback(library, monkeypatch, "SYN-DEV-01")) == ["syn_well_id.txt"]   # v1: + syn_other_id
    assert _files(_fallback(library, monkeypatch, "SYN-DEV-012")) == ["syn_other_id.txt"]


def test_fallback_finds_a_half_space_word_typed_with_a_space(corpus, monkeypatch):  # noqa: F811
    _db, library, _ids = corpus
    fts = _files(library.search("بررسی می شود"))
    assert fts == ["syn_half_space.txt"]
    assert _files(_fallback(library, monkeypatch, "بررسی می شود")) == fts                   # v1: []


def test_index_and_fallback_return_the_same_pages_and_every_hit_has_a_location(corpus, monkeypatch):  # noqa: F811
    _db, library, _ids = corpus
    for query in QUERIES:
        fts = library.search(query)
        scan = _fallback(library, monkeypatch, query)
        assert [h["page_id"] for h in sorted(fts["hits"], key=lambda h: h["page_id"])] == \
               [h["page_id"] for h in scan["hits"]], query
        for hit in fts["hits"]:
            assert hit["match_count"] >= 1 and hit["line_no"] is not None, (query, hit["file_name"])


def test_underscore_and_latin_diacritics_follow_the_fts_tokenizer():
    text = "SYNTHETIC café note on SYN_DEV_01, Ñandú naïve"
    def shown(terms):
        return [text[s:e] for s, e in sn.find_spans(text, terms)]
    assert shown(["cafe"]) == ["café"]
    assert shown(["naive"]) == ["naïve"]
    assert shown(["nandu"]) == ["Ñandú"]
    assert shown(["dev"]) == ["DEV"]                                     # "_" separates tokens
    assert sn.parse_query("SYN_DEV_01") == [["SYN", "DEV", "01"]]          # an identifier, like SYN-DEV-01
    assert sn.text_matches(text, sn.parse_query("SYN-DEV-01"))
    assert not sn.text_matches(text, sn.parse_query("SYN-DEV-012"))
    # Arabic-script letters are never folded by the Latin rule.
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ؤ", "و"), ("ئ", "ی")):
        assert sn.normalize(a) != sn.normalize(b)
    original = "e\u0301cole"                                             # decomposed accent is removed too
    normalised, origin = sn.normalize_with_map(original)
    assert normalised == "ecole" and [original[i] for i in origin] == list("ecole")


def test_hostile_and_degenerate_queries_are_plain_words(corpus):  # noqa: F811
    _db, library, _ids = corpus
    for query in ['" OR NEAR(a b) *', "SYNTHETIC\x00\u202e)", "'; DROP TABLE documents; --", "AND OR NOT",
                  "\u200c\u200c", "*" * 50, "x" * 20000]:
        result = library.search(query)
        assert result["status"] in ("matched", "no_matches", "invalid_query"), query
    assert library.search("'; DROP TABLE documents; --")["status"] == "no_matches"
    assert library.search("SYNTHETIC\x00\u202e)")["status"] == "matched"   # control characters separate words
    assert len(sn.query_terms(" ".join(["w"] * 5000))) == sn.MAX_TERMS
    assert len(library.list_documents()) == 7                             # nothing was executed as SQL


def test_a_v1_index_is_rebuilt_under_v2(corpus):  # noqa: F811
    _db, library, _ids = corpus
    library.search("SYNTHETIC")
    current = library._index_signature
    assert current[0] == sn.NORMALIZATION_VERSION == 2
    stale = library._index
    library._index_signature = (1,) + tuple(current[1:])                  # what a v1 build had cached
    library.search("SYNTHETIC")
    assert library._index is not stale and library._index_signature == current


def _fts5_available():
    try:
        sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE t USING fts5(body)")
        return True
    except sqlite3.OperationalError:
        return False


@pytest.mark.skipif(not _fts5_available(), reason="this SQLite build has no FTS5")
def test_generated_corpus_parity_between_fts5_and_the_scan():
    """Deterministic generated SYNTHETIC corpus: for every query the FTS5
    index and ``text_matches`` select the same pages, and every selected page
    has at least one highlight span in its original text."""
    rng = random.Random(46)
    vocab = ["SYN", "DEV", "01", "012", "1250", "۱۲۵۰", "٢٥٠٠", "2500", "psi", "Casing", "café", "naïve", "SYN_X",
             "مصنوعی", "مصنوعي", "کیسینگ", "كيسينگ", "می\u200cشود", "می", "شود", "میشود", "آب", "اب", "أب",
             "كِتَاب", "بـــزرگ", "pump", "pressure", "13-3/8", "9 5/8", "SYN-DEV-01", "SYN-DEV-012"]
    seps = [" ", "  ", "\n", ", ", "؛ ", " - ", "\u200f"]
    pages = ["".join(rng.choice(vocab) + rng.choice(seps) for _ in range(rng.randint(3, 14))) for _ in range(250)]
    con = sqlite3.connect(":memory:")
    con.execute("CREATE VIRTUAL TABLE t USING fts5(body, tokenize='unicode61 remove_diacritics 2')")
    con.executemany("INSERT INTO t(rowid, body) VALUES (?, ?)", ((i, sn.normalize(p)) for i, p in enumerate(pages)))
    queries = vocab + [" ".join(rng.sample(vocab, 2)) for _ in range(120)] + \
        ['"' + " ".join(rng.sample(vocab, 2)) + '"' for _ in range(60)]
    checked = 0
    for query in queries:
        groups = sn.parse_query(query)
        if not groups:
            continue
        fts = sorted(r[0] for r in con.execute("SELECT rowid FROM t WHERE t MATCH ?", (sn.fts_match_expression(groups),)))
        scan = [i for i, p in enumerate(pages) if sn.text_matches(p, groups)]
        assert fts == scan, query
        terms = [t for g in groups for t in g]
        assert all(sn.find_spans(pages[i], terms) for i in fts), query
        checked += 1
    assert checked > 200
