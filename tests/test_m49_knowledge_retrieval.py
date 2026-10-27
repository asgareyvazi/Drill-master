"""M49 - retrieval over reviewed pages: approval, provenance, scope, fusion, caches.

SYNTHETIC corpus: tests/m49_knowledge_fixtures.py (real reviewed-import path).
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import knowledge_retrieval as kr  # noqa: E402
from core.document_library import DocumentLibrary  # noqa: E402
from core.local_llm import CancelToken  # noqa: E402
from m49_knowledge_fixtures import DOCS, EDITED_TEXT, _extract, corpus_db, make_db  # noqa: E402


@pytest.fixture
def corpus():
    db, ids = corpus_db()
    yield db, ids
    db.engine.dispose()


def _index(db, **kw):
    return kr.KnowledgeIndex(kr.read_corpus(db), **kw)


def _sql(db, statement, **params):
    s = db.create_session()
    try:
        s.execute(text(statement), params)
        s.commit()
    finally:
        s.close()


def _pages(result):
    return [(h.page.document_id, h.page.page_no) for h in result.hits]


# --------------------------------------------------------------- chunking
def test_every_chunk_is_the_exact_stored_span(corpus):
    db, _ids = corpus
    snapshot = kr.read_corpus(db)
    index = kr.KnowledgeIndex(snapshot)
    assert index.chunks
    for chunk in index.chunks.values():
        page = snapshot.pages[chunk.page_id]
        assert page.text[chunk.start:chunk.end] == chunk.text
        assert chunk.chunk_id == f"p{page.page_id}:{chunk.start}-{chunk.end}"
        assert chunk.text_sha == page.text_sha


def test_long_paragraphs_split_at_sentence_ends_and_keep_offsets():
    body = " ".join(f"Sentence {i} about the SYN casing run number {i}." for i in range(60))
    page = kr.PageRecord(1, 1, "syn.pdf", 1, "page 1", body, "pdf-text", "extracted", "sha")
    chunks = kr.chunk_page(page, target=200)
    assert len(chunks) > 5
    for chunk in chunks:
        assert body[chunk.start:chunk.end] == chunk.text and len(chunk.text) <= 200
        assert chunk.text.endswith(".")
    covered = "".join(body[c.start:c.end] for c in chunks).replace(" ", "")
    assert covered == body.replace(" ", "")


def test_chunk_sha_changes_with_text_and_chunker_version(monkeypatch):
    page = kr.PageRecord(1, 1, "syn.pdf", 1, "page 1", "SYN mud weight 1.25 sg.", "pdf-text", "extracted", "a")
    edited = kr.PageRecord(1, 1, "syn.pdf", 1, "page 1", "SYN mud weight 1.26 sg.", "pdf-text", "edited", "b")
    first, = kr.chunk_page(page)
    assert kr.chunk_page(edited)[0].chunk_sha != first.chunk_sha
    monkeypatch.setattr(kr, "CHUNKER_VERSION", kr.CHUNKER_VERSION + 1)
    assert kr.chunk_page(page)[0].chunk_sha != first.chunk_sha


# --------------------------------------------------- approval & provenance
def test_rejected_ocr_page_is_never_stored_or_retrievable(corpus):
    db, ids = corpus
    snapshot = kr.read_corpus(db)
    ocr_pages = sorted(p.page_no for p in snapshot.pages.values() if p.document_id == ids["ocr"])
    assert ocr_pages == [1]
    approved, = [p for p in snapshot.pages.values() if p.document_id == ids["ocr"]]
    assert (approved.method, approved.review_status) == ("ocr", "approved")
    result = kr.KnowledgeIndex(snapshot).retrieve("UNAPPROVED-QX7 calibration factor gas detector", top_k=20)
    assert result.status == "no_evidence"
    assert all("QX7" not in h.chunk.text for h in result.hits)


def test_a_stored_page_with_an_unknown_review_status_is_excluded(corpus):
    """Defence in depth: only extracted/approved/edited pages are answerable."""
    db, ids = corpus
    _sql(db, "INSERT INTO document_pages (document_id, page_no, location, text, method, review_status) "
             "VALUES (:d, 7, 'page 7', 'SYN-PENDING-ZX9 secret pending text', 'ocr', 'pending')", d=ids["program"])
    snapshot = kr.read_corpus(db)
    assert snapshot.excluded_pages == 1
    assert all("ZX9" not in p.text for p in snapshot.pages.values())
    result = kr.KnowledgeIndex(snapshot).retrieve("SYN-PENDING-ZX9 secret pending text")
    assert result.status == "no_evidence" and all("ZX9" not in h.chunk.text for h in result.hits)


def test_reviewer_edited_text_is_the_only_version_and_keeps_its_provenance(corpus):
    db, ids = corpus
    result = _index(db).retrieve("How deep was the 9-5/8 in casing run in the casing tally?")
    hit, = [h for h in result.hits if h.page.document_id == ids["tally"]]
    assert hit.page.review_status == "edited" and hit.page.text == EDITED_TEXT
    assert "1795" in hit.chunk.text
    assert all("1790" not in h.chunk.text for h in result.hits)


# ------------------------------------------------------------------ scope
@pytest.mark.parametrize("scope, target, allowed", [
    ("document", "program", {"program"}),
    ("well", "well_a", {"program", "mud_rev2", "note_a"}),           # well + its reports' links
    ("well", "well_c", {"lessons", "note_c"}),
    ("report", "report_a1", {"note_a"}),                              # strictly the report's links
    ("report", "report_a2", {"mud_rev2"}),
])
def test_scope_filter_is_applied_before_ranking(corpus, scope, target, allowed):
    db, ids = corpus
    index = _index(db)
    allowed_ids = {ids[r] for r in allowed}
    for question in ("mud weight 12-1/4 in section", "pump liner", "stuck pipe", "casing shoe depth",
                     "kick tolerance", "SYNTHETIC"):
        result = index.retrieve(question, scope, ids[target], top_k=50)
        assert {d for d, _ in _pages(result)} <= allowed_ids, (question, scope)
    assert {index.snapshot.pages[index.chunks[c].page_id].document_id
            for c in index.candidate_chunks(scope, ids[target])} == allowed_ids


def test_same_file_name_in_two_wells_never_crosses_scope(corpus):
    db, ids = corpus
    index = _index(db)
    a = index.retrieve("pump liner size", "well", ids["well_a"])
    c = index.retrieve("pump liner size", "well", ids["well_c"])
    assert {d for d, _ in _pages(a)} == {ids["note_a"]} or ids["note_c"] not in {d for d, _ in _pages(a)}
    assert ids["note_a"] not in {d for d, _ in _pages(c)} and ids["note_c"] in {d for d, _ in _pages(c)}
    assert DOCS["note_a"][0] == DOCS["note_c"][0]


def test_scope_states(corpus):
    db, ids = corpus
    index = _index(db)
    assert index.retrieve("pump liner", "well", ids["well_d"]).status == "empty_scope"
    assert index.retrieve("pump liner", "well", None).status == "empty_scope"
    assert index.retrieve("pump liner", "document", 999999).status == "empty_scope"
    with pytest.raises(ValueError):
        index.retrieve("pump liner", "company", 1)


def test_empty_library_is_no_documents():
    db = make_db()
    try:
        result = _index(db).retrieve("mud weight")
        assert result.status == "no_documents" and result.hits == []
    finally:
        db.engine.dispose()


def test_requested_page_restricts_evidence_and_reports_a_missing_page(corpus):
    db, ids = corpus
    index = _index(db)
    assert index.retrieve("What is on page 9 of the drilling program?", "document", ids["program"]).status == "no_page"
    result = index.retrieve("kick tolerance on page 2", "document", ids["program"])
    assert result.status == "ok" and set(_pages(result)) == {(ids["program"], 2)}
    assert kr.requested_page("متن صفحه ۳ چیست") == 3


# ------------------------------------------------------- language handling
@pytest.mark.parametrize("question", ["توصيه براي هرزروي چيست؟", "توصیه برای هرزروی چیست؟",
                                      "lost circulation در عمق ۱۸۵۰ متر"])
def test_persian_arabic_letters_and_glossary_find_the_persian_page(corpus, question):
    db, ids = corpus
    result = _index(db).retrieve(question)
    assert result.status == "ok" and _pages(result)[0] == (ids["fa_program"], 1)


def test_glossary_bridges_abbreviations(corpus):
    db, ids = corpus
    result = _index(db).retrieve("BOP pressure test")
    assert _pages(result)[0] == (ids["program"], 2) and "blowout preventer" in result.expansions


def test_persian_decimal_mark_is_folded_for_numbers():
    assert kr.fold("۱٫۱۸ sg") == "1.18 sg" and kr.words("۱٬۲۵۰ متر") == ["1250", "متر"]


# -------------------------------------------------------------- sufficiency
def test_unknown_identifier_is_insufficient_but_a_generic_missing_word_is_not(corpus):
    db, ids = corpus
    index = _index(db)
    assert index.retrieve("What is the mud motor bend angle for SYN-ZZ-99?").status == "no_evidence"
    assert index.retrieve("What is the liner hanger setting pressure for SYN-KB-02?").status == "no_evidence"
    ok = index.retrieve("pump liner size", "well", ids["well_c"])
    assert ok.status == "ok" and "size" in ok.missing_terms
    assert kr.identifier_terms("SYN-ZZ-99 BOP size 9-5/8 in") >= {"syn", "zz", "99", "bop", "9", "5", "8"}
    assert "size" not in kr.identifier_terms("SYN-ZZ-99 BOP size 9-5/8 in")


# ------------------------------------------------------------------ fusion
def test_rrf_matches_hand_computed_scores():
    fused = kr.rrf_fuse({"lexical": ["c1", "c2", "c3"], "ngram": ["c3", "c1"], "glossary": ["c3"]}, k=60)
    expected = {"c1": 1 / 61 + 1 / 62, "c2": 1 / 62, "c3": 1 / 63 + 1 / 61 + 1 / 61}
    assert [cid for cid, _s, _r in fused] == ["c3", "c1", "c2"]
    for cid, score, ranks in fused:
        assert score == pytest.approx(expected[cid], abs=1e-12)
    assert dict((cid, r) for cid, _s, r in fused)["c3"] == {"lexical": 3, "ngram": 1, "glossary": 1}


def test_rrf_ties_break_by_id_and_a_list_cannot_vote_twice():
    fused = kr.rrf_fuse({"a": ["x", "y"], "b": ["y", "x"]})
    assert [cid for cid, _s, _r in fused] == ["x", "y"]
    single = kr.rrf_fuse({"a": ["x", "x", "y"]})
    assert dict((c, s) for c, s, _ in single)["x"] == pytest.approx(1 / 61)


def test_results_are_deduplicated_per_page(corpus):
    db, _ids = corpus
    result = _index(db).retrieve("SYNTHETIC mud weight casing section", top_k=20)
    ids = [h.chunk.chunk_id for h in result.hits]
    assert len(ids) == len(set(ids))
    per_page = {}
    for h in result.hits:
        per_page[h.page.page_id] = per_page.get(h.page.page_id, 0) + 1
    assert max(per_page.values()) <= 2


# --------------------------------------------------------------- conflicts
def test_conflicting_values_across_documents_are_reported(corpus):
    db, ids = corpus
    result = _index(db).retrieve("What is the planned mud weight for the 12-1/4 in section?")
    conflict, = result.conflicts
    assert (conflict.quantity, conflict.unit) == ("mud weight", "sg")
    assert sorted(v for v, _ in conflict.values) == [1.25, 1.32]
    scoped = _index(db).retrieve("mud weight 12-1/4 in section", "document", ids["program"])
    assert scoped.conflicts == []


def test_size_designations_are_not_read_as_values():
    found = kr.quantities("The planned mud weight for the 12-1/4 in section is 1.25 sg.", [["mud", "weight"]])
    assert found == [("mud weight", 1.25, "sg")]


# ------------------------------------------------- signatures / freshness
def test_signature_changes_on_delete_link_and_reimport_with_reused_ids(corpus):
    db, ids = corpus
    base = kr.corpus_signature(db)
    assert kr.corpus_signature(db) == base
    _sql(db, "INSERT INTO document_links (document_id, well_id, report_id, linked_by, linked_at) "
             "VALUES (:d, :w, NULL, 'syn', CURRENT_TIMESTAMP)", d=ids["inject"], w=ids["well_d"])
    linked = kr.corpus_signature(db)
    assert linked != base
    library = DocumentLibrary(db)
    try:
        from document_link_fixtures import without_session_user
        with without_session_user():
            assert library.delete_document(ids["tally"])
            after_delete = kr.corpus_signature(db)
            assert after_delete != linked
            # Same page count, same total length, page id reused by SQLite:
            extract = _extract("tally")
            extract.sha256 = "0" * 64
            assert library.import_reviewed(extract).status == "imported"
        assert kr.corpus_signature(db) != after_delete
    finally:
        library.close()


def test_deleted_document_leaves_no_evidence_in_a_rebuilt_index(corpus):
    db, ids = corpus
    from document_link_fixtures import without_session_user
    library = DocumentLibrary(db)
    with without_session_user():
        assert library.delete_document(ids["inject"])
    library.close()
    result = _index(db).retrieve("cement slurry density 9-5/8 in casing", top_k=20)
    assert all(h.page.document_id != ids["inject"] for h in result.hits)


def test_library_search_index_is_rebuilt_after_delete_and_same_size_reimport():
    """M44 DocumentLibrary._signature missed a delete + re-import that reuses
    the page id with the same text length (M49 fix: + document audit id)."""
    from core.document_library import PAGE_OK, READY, DocumentExtract, PageExtract
    from document_link_fixtures import without_session_user
    db = make_db()
    library = DocumentLibrary(db)

    def doc(word, sha):
        return DocumentExtract(path="/syn", file_name=f"syn-{word}.txt", size_bytes=10, sha256=sha * 64, kind="text",
                               page_count=1, status=READY,
                               pages=[PageExtract(1, "lines 1-1", f"SYNTHETIC {word} note", "text-file", PAGE_OK)])
    try:
        with without_session_user():
            first = library.import_reviewed(doc("alphax", "a")).document_id
            assert library.search("alphax")["hits"]
            library.delete_document(first)
            library.import_reviewed(doc("betayz", "b"))
        assert library.search("betayz")["hits"], "stale index: the re-imported page is not found"
        assert not library.search("alphax")["hits"], "stale index: the deleted text is still found"
    finally:
        library.close()
        db.engine.dispose()


# -------------------------------------------------------------- embeddings
class _Embedder:
    """Stub of the EXTERNAL embedding model: deterministic bag-of-letters vectors."""

    def __init__(self, dims=8, model="syn-embed"):
        self.dims, self.embed_model, self.calls = dims, model, 0

    def embed(self, texts, cancel=None):
        self.calls += 1
        out = []
        for t in texts:
            v = [0.0] * self.dims
            for ch in kr.fold(t):
                if ch.isalnum():
                    v[ord(ch) % self.dims] += 1.0
            out.append(v)
        return out


def test_semantic_index_is_ready_only_when_complete_and_resumes_after_cancel(corpus):
    db, _ids = corpus
    store = kr.EmbeddingStore()
    index = _index(db, embedding_store=store, embed_model="syn-embed")
    assert index.semantic_state()[0] is False
    token = CancelToken()
    seen = []

    def progress(done, total):
        seen.append(done)
        if done >= 4:
            token.cancel()
    first = kr.build_semantic_index(index, _Embedder(), store, cancel=token, progress=progress, batch=4)
    assert first["state"] == "cancelled" and first["done"] < first["total"]
    assert index.semantic_state()[0] is False and not store.is_complete("syn-embed", repr(index.signature))
    second = kr.build_semantic_index(index, _Embedder(), store, batch=4)
    assert second == {"state": "complete", "done": len(index.chunks), "total": len(index.chunks)}
    assert index.semantic_state() == (True, "")
    result = index.retrieve("mud weight", query_vector=_Embedder().embed(["mud weight"])[0])
    assert "semantic" in result.lists_used and not result.unavailable


def test_semantic_cache_never_mixes_models_dimensions_or_text_versions(corpus):
    db, ids = corpus
    store = kr.EmbeddingStore()
    index = _index(db, embedding_store=store, embed_model="syn-embed")
    kr.build_semantic_index(index, _Embedder(dims=8), store)
    sha = next(iter(index.chunks.values())).chunk_sha
    assert set(store.get("syn-embed", [sha])) == {sha}
    assert store.get("other-model", [sha]) == {}
    assert store.get("syn-embed", [sha], dims=16) == {}
    # Same model name, new vector size: a rebuild re-embeds everything at 16.
    again = kr.build_semantic_index(index, _Embedder(dims=16), store)
    assert again["state"] == "complete" and store.build_dims("syn-embed", repr(index.signature)) == 16
    # A query vector of the old size is refused with a reason, not silently empty.
    result = index.retrieve("mud weight", query_vector=[1.0] * 8)
    assert "semantic" not in result.lists_used and "rebuild" in result.unavailable[0][1]
    # A changed corpus (new signature) is not "complete" until rebuilt.
    _sql(db, "DELETE FROM document_links WHERE document_id = :d", d=ids["note_c"])
    fresh = _index(db, embedding_store=store, embed_model="syn-embed")
    assert fresh.semantic_state()[0] is False


def test_without_embeddings_lexical_works_and_semantic_is_reported_unavailable(corpus):
    db, ids = corpus
    result = _index(db).retrieve("kick tolerance")
    assert result.status == "ok" and _pages(result)[0] == (ids["program"], 2)
    assert result.unavailable[0][0] == "semantic" and "unavailable" in result.unavailable[0][1]


def test_without_fts5_a_scan_keeps_lexical_retrieval_working(corpus, monkeypatch):
    db, ids = corpus
    monkeypatch.setattr(kr.KnowledgeIndex, "_build_fts", lambda self: None)
    result = _index(db).retrieve("kick tolerance")
    assert result.status == "ok" and _pages(result)[0] == (ids["program"], 2)
    assert ("fts5", "SQLite FTS5 unavailable; lexical retrieval uses a scan") in result.unavailable


def test_embedding_store_path_is_user_data_not_the_repository(tmp_path):
    class Db:
        db_path = str(tmp_path / "data" / "drill.db")
    path = Path(kr.default_embedding_store_path(Db()))
    assert path == (tmp_path / "data" / "knowledge_cache" / "embeddings-v1.sqlite").resolve()

    class Mem:
        db_path = ":memory:"
    assert kr.default_embedding_store_path(Mem()) == ":memory:"


def test_embedding_store_refuses_the_application_database(tmp_path):
    """The cache owns its file: pointed at a database with the application's
    schema it raises and leaves that database byte-for-byte unchanged; an
    existing cache file still reopens with its vectors."""
    import sqlite3

    from sqlalchemy import create_engine

    from core.database import Base
    app_db = tmp_path / "drill.db"
    engine = create_engine(f"sqlite:///{app_db}")
    Base.metadata.create_all(engine)
    engine.dispose()
    before = app_db.read_bytes()
    with pytest.raises(ValueError, match="holds other tables"):
        kr.EmbeddingStore(str(app_db))
    assert app_db.read_bytes() == before
    conn = sqlite3.connect(app_db)
    try:
        names = {n for (n,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()                       # a context manager would not close it (Windows file lock)
    assert not names & kr.STORE_TABLES

    cache = tmp_path / "knowledge_cache" / "embeddings-v1.sqlite"
    store = kr.EmbeddingStore(str(cache))
    store.put("m", [("sha1", [0.5, 0.25])])
    store._conn.close()
    reopened = kr.EmbeddingStore(str(cache))
    assert set(reopened.get("m", ["sha1"])) == {"sha1"}
    reopened._conn.close()


def test_knowledge_corpus_signature_changes_after_delete_and_same_size_reimport():
    """The knowledge index cache key must see a delete + re-import that reuses
    the page id with the same text length and leaves the links unchanged
    (page count / max id / total length alone collide - M44 defect class)."""
    from core.document_library import PAGE_OK, READY, DocumentExtract, PageExtract
    from document_link_fixtures import without_session_user
    db = make_db()
    library = DocumentLibrary(db)

    def doc(word, sha):
        return DocumentExtract(path="/syn", file_name=f"syn-{word}.txt", size_bytes=10, sha256=sha * 64, kind="text",
                               page_count=1, status=READY,
                               pages=[PageExtract(1, "lines 1-1", f"SYNTHETIC {word} note", "text-file", PAGE_OK)])
    try:
        with without_session_user():
            first = library.import_reviewed(doc("alphax", "a")).document_id
            before = kr.corpus_signature(db)
            library.delete_document(first)
            library.import_reviewed(doc("betayz", "b"))
        after = kr.corpus_signature(db)
        assert before[3:6] == after[3:6], "precondition: count / max page id / total length collide"
        assert after != before
        index = kr.KnowledgeIndex(kr.read_corpus(db))
        assert index.retrieve("betayz").status == "ok" and index.retrieve("alphax").status != "ok"
    finally:
        library.close()
        db.engine.dispose()


def test_one_long_page_contributes_at_most_two_passages():
    """Dedupe: a page with many matching paragraphs must not flood the
    evidence list and push other documents out."""
    from core.document_library import PAGE_OK, READY, DocumentExtract, PageExtract
    from document_link_fixtures import without_session_user
    db = make_db()
    library = DocumentLibrary(db)
    long_text = "\n\n".join(f"SYNTHETIC paragraph {i}: the kick tolerance review for interval {i} is recorded."
                            for i in range(1, 9))
    try:
        with without_session_user():
            long_id = library.import_reviewed(DocumentExtract(
                path="/syn", file_name="syn-long.txt", size_bytes=10, sha256="c" * 64, kind="text", page_count=1,
                status=READY, pages=[PageExtract(1, "lines 1-8", long_text, "text-file", PAGE_OK)])).document_id
            other_id = library.import_reviewed(DocumentExtract(
                path="/syn", file_name="syn-other.txt", size_bytes=10, sha256="d" * 64, kind="text", page_count=1,
                status=READY, pages=[PageExtract(1, "lines 1-1", "SYNTHETIC kick tolerance note for the rig crew.",
                                                 "text-file", PAGE_OK)])).document_id
        index = kr.KnowledgeIndex(kr.read_corpus(db))
        assert len(index.page_chunks) == 2 and max(len(v) for v in index.page_chunks.values()) == 8   # precondition
        result = index.retrieve("kick tolerance review", top_k=6)
        per_page = Counter(hit.page.page_id for hit in result.hits)
        assert per_page and max(per_page.values()) <= 2
        assert {hit.page.document_id for hit in result.hits} == {long_id, other_id}
    finally:
        library.close()
        db.engine.dispose()
