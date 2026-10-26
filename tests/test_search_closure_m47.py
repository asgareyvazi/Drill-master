"""M47: search highlight contract, FTS5 tokenizer parity, link-note policy.

P3-A  Highlight spans follow the query GROUPS (``parse_query``), the same
      semantics as the FTS5 expression and the fallback scan: an identifier
      or quoted phrase is one adjacent-token match; single words are word
      prefixes. M46 passed a flat token list, so ``SYN-DEV-01`` highlighted
      ``SYN`` inside ``SYNTHETIC`` and the ``01`` of ``SYN-DEV-012``.
P3-B  The comparison form (fallback scan, highlighter) mirrors the real FTS5
      ``unicode61 remove_diacritics 2`` tokenizer, probed here through
      ``fts5vocab`` with a corpus built at run time. Only the probes skip when
      this SQLite has no FTS5.
P3-C  ``DocumentLink.note``: ``None``/``""``/whitespace-only -> NULL on every
      write path, one policy for non-empty notes, audited and atomic.

SYNTHETIC data only. The widget test runs under QT_QPA_PLATFORM=offscreen; it
is not native Windows desktop testing.
"""
from __future__ import annotations

import itertools
import json
import os
import sqlite3
import unicodedata

import pytest

from core import search_normalization as sn
from core.document_library import DocumentLibrary
from core.document_links import NOTE_MAX_LENGTH, DocumentLinkError, DocumentLinkService, normalize_note
from document_link_fixtures import build_link_world, import_documents, without_session_user, write_documents
from test_scope_attribution import _mgr

ZWNJ = "\u200c"


def _texts(text, query):
    return [text[s:e] for s, e in sn.find_spans(text, sn.parse_query(query))]


def _fts5_available():
    try:
        sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE t USING fts5(body)")
        return True
    except sqlite3.OperationalError:
        return False


needs_fts5 = pytest.mark.skipif(not _fts5_available(), reason="this SQLite build has no FTS5 (tokenizer probe only)")


# ---------------------------------------------------------------- P3-A spans

def test_an_identifier_highlights_only_the_whole_adjacent_phrase():
    text = "SYNTHETIC log: SYN-DEV-01 drilled; SYN-DEV-012 planned; later syn-dev-01 again."
    assert _texts(text, "SYN-DEV-01") == ["SYN-DEV-01", "syn-dev-01"]     # exact original characters
    spans = sn.find_spans(text, sn.parse_query("SYN-DEV-01"))
    assert all(not (s <= text.index("SYNTHETIC") < e) for s, e in spans)   # never SYN inside SYNTHETIC
    assert text.index("SYN-DEV-012") not in [s for s, _ in spans]          # SYN-DEV-012 is not a hit


def test_a_quoted_phrase_is_one_match_across_any_separator():
    text = "SYNTHETIC casing shoe\nset; casing  shoe; casing-shoe; casings shoe"
    assert _texts(text, '"casing shoe"') == ["casing shoe", "casing  shoe", "casing-shoe"]


def test_a_prefix_query_keeps_its_contract():
    text = "SYNTHETIC Cement job; cementing done; precement check"
    assert _texts(text, "cem") == ["Cem", "cem"]                             # word starts only


def test_half_space_spans_cover_the_original_word_with_its_zwnj():
    text = f"SYNTHETIC گزارش ثبت می{ZWNJ}شود و می شود"
    for query in ("می شود", f"می{ZWNJ}شود", "میشود"):
        spans = _texts(text, query)
        assert f"می{ZWNJ}شود" in spans, query
    assert _texts(text, "میشود") == [f"می{ZWNJ}شود"]                     # the spaced pair is two words


def test_overlapping_duplicate_and_reordered_groups_give_one_deterministic_result():
    text = "SYNTHETIC SYN-DEV-01 note"
    queries = ["SYN-DEV-01 SYN", "SYN SYN-DEV-01", "SYN-DEV-01 SYN-DEV-01 syn"]
    results = {tuple(sn.find_spans(text, sn.parse_query(q))) for q in queries}
    assert len(results) == 1
    (spans,) = results
    assert [text[s:e] for s, e in spans] == ["SYN", "SYN-DEV-01"]           # merged, sorted, no overlap
    for groups in itertools.permutations(sn.parse_query("syn dev 01")):
        assert sn.find_spans(text, list(groups)) == sn.find_spans(text, sn.parse_query("syn dev 01"))


def test_case_variants_map_back_to_the_stored_characters():
    text = "SYNTHETIC Syn-Dev-01 / sYN-dEV-01"
    assert _texts(text, "SYN-DEV-01") == ["Syn-Dev-01", "sYN-dEV-01"]


def test_plain_string_terms_keep_their_group_meaning():
    text = "SYNTHETIC SYN-DEV-01 SYNTHETIC"
    assert [text[s:e] for s, e in sn.find_spans(text, ["SYN-DEV-01"])] == ["SYN-DEV-01"]
    assert [text[s:e] for s, e in sn.find_spans(text, ["syn"])] == ["SYN", "SYN", "SYN"]


def test_utf16_offsets_for_qt_positions():
    text = "a\U0001d412b SYN"
    assert sn.utf16_offset(text, 0) == 0 and sn.utf16_offset(text, 2) == 3
    assert sn.utf16_offset(text, text.index("SYN")) == len(text[:text.index("SYN")].encode("utf-16-le")) // 2


@pytest.fixture
def library(tmp_path):
    with without_session_user():
        db = _mgr()
        library = DocumentLibrary(db)
        pages = {
            "syn_id.txt": "SYNTHETIC drilling log\nSYN-DEV-01 reached 1250 m\nSYN-DEV-012 is another well",
            "syn_other.txt": "SYNTHETIC only SYN-DEV-012 here\nand SYNTHETIC text",
            "syn_fold.txt": "SYNTHETIC \u1e9btation report with ǡlpha and café",
            "syn_fa.txt": f"SYNTHETIC گزارش می{ZWNJ}شود در عمق ۱۲۵۰ متر",
        }
        from core.document_library import extract_document
        for name, content in pages.items():
            path = tmp_path / name
            path.write_text(content, encoding="utf-8")
            outcome = library.import_reviewed(extract_document(path))
            assert outcome.status == "imported", outcome.message
        yield library
        library.close()
        db.engine.dispose()


def _search(library, query, monkeypatch=None, fallback=False):
    if fallback:
        monkeypatch.setattr(library, "_ensure_index", lambda: None)
    return library.search(query)


@needs_fts5
@pytest.mark.parametrize("query", ["SYN-DEV-01", "SYN-DEV-012", "sta", "\u1e9bta", "ǡlpha", "cafe", "می شود",
                                   "1250", "۱۲۵۰", '"drilling log"'])
def test_fts5_and_fallback_return_the_same_hits_snippets_and_lines(library, monkeypatch, query):
    fts = _search(library, query)
    assert fts["method"].startswith("SQLite FTS5")
    scan = _search(library, query, monkeypatch, fallback=True)
    assert scan["method"].startswith("Substring scan")
    key = lambda r: sorted((h["file_name"], h["page_no"], h["line_no"], h["match_count"], h["snippet"])  # noqa: E731
                           for h in r["hits"])
    assert key(fts) == key(scan) and fts["groups"] == scan["groups"]
    assert all(h["match_count"] >= 1 and h["line_no"] for h in fts["hits"]), query


@needs_fts5
def test_the_identifier_search_highlights_only_the_identifier(library):
    result = library.search("SYN-DEV-01")
    assert [h["file_name"] for h in result["hits"]] == ["syn_id.txt"]        # SYN-DEV-012 page is not a hit
    (hit,) = result["hits"]
    assert hit["match_count"] == 1 and hit["line_no"] == 2
    assert "[SYN-DEV-01]" in hit["snippet"] and "[SYN" not in hit["snippet"].replace("[SYN-DEV-01]", "")


# ---------------------------------------------------------------- P3-B tokenizer parity

def test_comparison_form_rules_without_fts5():
    assert sn.NORMALIZATION_VERSION == 3
    assert sn._fold("\u1e9b") == "s" and sn._fold("\u017f") == "s" and sn._fold("S") == "s"
    assert sn._fold("ß") == "ß" and sn._fold("\u1e9e") == "ß"                # simple folding, no expansion
    assert sn._fold("\u0149") == "\u0149" and sn._fold("\u1e9a") == "\u1e9a"
    assert sn.normalize("ǡǠ") == "ǡǠ" and sn.normalize("Ǟé") == "Ae"
    assert len(sn._fold("Straße ẞ ſ ẛ")) == len("Straße ẞ ſ ẛ")             # positions stay aligned


def _probe_characters():
    chars = {ord(c) for c in "sS\u017f\u1e9b\u1e9eß\u0149\u1e9aǠǡ"}
    for low, high in ((0x00C0, 0x0250), (0x1E00, 0x1F00), (0x0600, 0x0700), (0x0750, 0x0780),
                      (0xFB50, 0xFE00), (0xFE70, 0xFF00)):
        chars.update(range(low, high))
    return sorted(c for c in chars if sn._TOKEN.fullmatch("q" + chr(c) + "q"))


@needs_fts5
def test_the_comparison_form_matches_the_real_fts5_tokenizer():
    """Corpus built at run time: one page per character; the token FTS5 stores
    (``fts5vocab``) must equal the token the fallback and highlighter compare."""
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE VIRTUAL TABLE t USING fts5(body, tokenize='unicode61 remove_diacritics 2')")
    connection.execute("CREATE VIRTUAL TABLE v USING fts5vocab(t, 'instance')")
    chars = _probe_characters()
    connection.executemany("INSERT INTO t(rowid, body) VALUES (?, ?)",
                           [(i + 1, sn.normalize("q" + chr(c) + "q")) for i, c in enumerate(chars)])
    stored = {}
    for term, doc, _col, _offset in connection.execute("SELECT term, doc, col, offset FROM v"):
        stored.setdefault(doc, []).append(term)
    mismatches = []
    for i, c in enumerate(chars):
        ours = sn._TOKEN.findall(sn._fold(sn.normalize("q" + chr(c) + "q")))
        if ours != stored.get(i + 1, []):
            mismatches.append(f"U+{c:04X} {unicodedata.name(chr(c), '?')}: {ours} != {stored.get(i + 1)}")
    assert len(chars) > 1000 and not mismatches, mismatches[:20]


@needs_fts5
def test_long_s_with_dot_is_found_and_highlighted_identically():
    page = "SYNTHETIC \u1e9btation"
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE VIRTUAL TABLE t USING fts5(body, tokenize='unicode61 remove_diacritics 2')")
    connection.execute("INSERT INTO t(rowid, body) VALUES (1, ?)", (sn.normalize(page),))
    for query in ("sta", "STA", "\u1e9bta", "\u017fta", "station"):
        groups = sn.parse_query(query)
        fts = connection.execute("SELECT rowid FROM t WHERE t MATCH ?", (sn.fts_match_expression(groups),)).fetchall()
        assert (fts == [(1,)]) == sn.text_matches(page, groups), query
        assert bool(fts) == bool(sn.find_spans(page, groups)), query
    assert _texts(page, "sta") == ["\u1e9bta"]


# ---------------------------------------------------------------- P3-C notes

@pytest.mark.parametrize("raw, stored", [
    (None, None), ("", None), ("   ", None), ("\t\t", None), ("\r\n", None), ("\n \t\r", None),
    ("\u00a0\u2003\u3000", None), ("\u2028\u2029", None), ("\u0085", None),
    ("  SYNTHETIC note \t", "SYNTHETIC note"), ("\tline one\nline two\r\n", "line one\nline two"),
    ("یادداشت مصنوعی\u00a0", "یادداشت مصنوعی"), ("a" * 250, "a" * NOTE_MAX_LENGTH),
    (" " * 5 + "b" * 199 + " x", "b" * 199),
])
def test_note_policy(raw, stored):
    assert normalize_note(raw) == stored


@pytest.fixture
def links(tmp_path):
    with without_session_user():
        db = _mgr()
        ids = build_link_world(db)
        ids["docs"] = import_documents(db, write_documents(tmp_path / "docs"))
        yield db, ids, DocumentLinkService(db)
        db.engine.dispose()


def _raw_notes(db):
    session = db.create_session()
    try:
        from sqlalchemy import text
        return [row[0] for row in session.execute(text("SELECT note FROM document_links ORDER BY id"))]
    finally:
        session.close()


def _link_audits(db):
    session = db.create_session()
    try:
        from sqlalchemy import text
        return [(r[0], json.loads(r[1])) for r in session.execute(text(
            "SELECT action, details FROM audit_logs WHERE action LIKE 'document_link%' ORDER BY id"))]
    finally:
        session.close()


def test_blank_notes_are_stored_as_null_and_text_is_normalised(links):
    db, ids, service = links
    docs = ids["docs"]
    service.create_link(docs["alpha"], ids["alpha"], note=" \t\r\n\u00a0")
    service.create_link(docs["twin"], ids["twin_1"], note="")
    service.create_link(docs["arabic"], ids["persian"], note="  SYNTHETIC kept\ttext  ")
    service.create_link(docs["unrelated"], ids["alpha"])
    assert _raw_notes(db) == [None, None, "SYNTHETIC kept\ttext", None]     # raw SQLite values: NULL, not ""
    assert [a[1]["note_chars"] for a in _link_audits(db)] == [0, 0, len("SYNTHETIC kept\ttext"), 0]


def test_a_note_only_change_follows_the_unchanged_audit_and_atomic_rules(links, monkeypatch):
    db, ids, service = links
    link_id = service.create_link(ids["docs"]["alpha"], ids["alpha"], ids["report_1"], page_no=1, note="SYNTHETIC")
    for same in ("SYNTHETIC", "  SYNTHETIC\n", ):
        with pytest.raises(DocumentLinkError) as error:
            service.update_link(link_id, ids["alpha"], ids["report_1"], page_no=1, note=same)
        assert error.value.code == "unchanged"
    service.update_link(link_id, ids["alpha"], ids["report_1"], page_no=1, note="SYNTHETIC revised")
    service.update_link(link_id, ids["alpha"], ids["report_1"], page_no=1, note="   ")
    assert _raw_notes(db) == [None]
    with pytest.raises(DocumentLinkError) as error:                         # NULL vs blank: unchanged
        service.update_link(link_id, ids["alpha"], ids["report_1"], page_no=1, note="\t")
    assert error.value.code == "unchanged"
    changes = [a for a in _link_audits(db) if a[0] == "document_link_change"]
    assert [(c[1]["from"]["note_chars"], c[1]["to"]["note_chars"]) for c in changes] == [(9, 17), (17, 0)]
    before = (_raw_notes(db), _link_audits(db))
    monkeypatch.setattr(db, "_add_mandatory_audit",
                        lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError("SYNTHETIC audit failure")))
    with pytest.raises(DocumentLinkError) as error:
        service.update_link(link_id, ids["alpha"], ids["report_1"], page_no=1, note="SYNTHETIC lost")
    assert error.value.code == "audit_failed"
    assert (_raw_notes(db), _link_audits(db)) == before                     # nothing partial


def test_a_legacy_empty_note_reads_as_none_and_is_written_back_as_null(links):
    db, ids, service = links
    link_id = service.create_link(ids["docs"]["alpha"], ids["alpha"])
    session = db.create_session()
    try:
        from sqlalchemy import text
        session.execute(text("UPDATE document_links SET note = '' WHERE id = :i"), {"i": link_id})
        session.commit()
    finally:
        session.close()
    assert _raw_notes(db) == [""]
    (row,) = service.links_for_well(ids["alpha"])
    assert row["note"] is None                                              # the UI sees one "no note"
    with pytest.raises(DocumentLinkError) as error:                         # "" vs NULL is unchanged
        service.update_link(link_id, ids["alpha"], note=None)
    assert error.value.code == "unchanged"
    service.update_link(link_id, ids["alpha"], ids["report_1"])             # any real change normalises it
    assert _raw_notes(db) == [None]


def test_a_note_change_is_denied_to_a_read_only_principal_without_writing(tmp_path):
    """Real authenticated users on a file database (no fabricated principal)."""
    from core.permissions import permissions, session_user
    from synthetic_operations import make_file_database

    db = make_file_database(tmp_path / "notes_auth_m47.db")
    previous = permissions.user
    try:
        engineer = session_user(db.authenticate_user("engineer", "Synthetic-Eng-1!"))
        viewer = session_user(db.authenticate_user("viewer", "Synthetic-View-1!"))
        permissions.set_user(engineer)
        db.enforce_authorization(permissions)
        ids = build_link_world(db)
        doc = import_documents(db, {"twin": write_documents(tmp_path / "d")["twin"]})["twin"]
        service = DocumentLinkService(db)
        link_id = service.create_link(doc, ids["twin_1"], note="SYNTHETIC")
        before_notes, before_audits = _raw_notes(db), _link_audits(db)
        permissions.set_user(viewer)
        with pytest.raises(DocumentLinkError) as error:
            service.update_link(link_id, ids["twin_1"], note="SYNTHETIC by viewer")
        assert error.value.code == "denied"
        assert (_raw_notes(db), _link_audits(db)) == (before_notes, before_audits)
    finally:
        permissions.set_user(previous)
        db.engine.dispose()


def test_a_duplicate_target_is_refused_even_with_a_note_change(links):
    db, ids, service = links
    service.create_link(ids["docs"]["alpha"], ids["alpha"], ids["report_1"])
    second = service.create_link(ids["docs"]["alpha"], ids["alpha"], ids["report_2"])
    with pytest.raises(DocumentLinkError) as error:
        service.update_link(second, ids["alpha"], ids["report_1"], note="SYNTHETIC")
    assert error.value.code == "duplicate"
    assert _raw_notes(db) == [None, None]


# ---------------------------------------------------------------- widget (Qt offscreen)

def test_documents_tab_highlights_the_identifier_after_a_non_bmp_character(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from core.document_library import extract_document
    from core.permissions import permissions
    from tabs.documents_tab import DocumentsTab

    app = QApplication.instance() or QApplication([])
    path = tmp_path / "syn_astral.txt"
    path.write_text("SYNTHETIC \U0001d412\U0001d412 marker SYN-DEV-012 and SYN-DEV-01 end", encoding="utf-8")
    with without_session_user():
        db = _mgr()
        library = DocumentLibrary(db)
        assert library.import_reviewed(extract_document(path)).status == "imported"
        library.close()
        previous = permissions.user
        permissions.set_user({"username": "syn-engineer", "role": "engineer"})
        widget = DocumentsTab(db)
        widget.show_dialogs = False
        try:
            widget.search_edit.setText("SYN-DEV-01")
            widget.run_search()
            assert widget.results.count() == 1
            widget.results.setCurrentRow(0)
            app.processEvents()
            highlighted = [s.cursor.selectedText() for s in widget.viewer.extraSelections()]
            assert highlighted == ["SYN-DEV-01"]                            # not SYN of SYNTHETIC, not -012
        finally:
            widget.cleanup()
            widget.deleteLater()
            permissions.set_user(previous)
            db.engine.dispose()
