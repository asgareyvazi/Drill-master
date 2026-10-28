"""M51 §4: the Knowledge Assistant corpus is read off the GUI thread and is never stale.

Real Documents tab + assistant panel on a temporary FILE SQLite database
(``DatabaseManager.initialize``) with the SYNTHETIC M50 corpus, so the panel
takes its production path: the corpus signature and snapshot are read by a
worker through ``core.export_jobs.worker_database`` (own read-only connection,
one read transaction).  A statement probe on the GUI engine counts every SQL
statement executed on the GUI thread.  The embedder object stands in for the
EXTERNAL local model server only in the semantic-build threading test
(isolation; no real model was run - NOT RUN, none installed).  Offscreen Qt
on Linux, not Windows desktop testing.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication  # noqa: E402
from sqlalchemy import event  # noqa: E402

from core import knowledge_retrieval as kr  # noqa: E402
from core import local_llm as ll  # noqa: E402

QUESTION = "mud weight for the 16 in section of SYN-KE-05"
MAIN = threading.get_ident()


class ScriptedEmbedder:
    """Stand-in for the external embedding server (deterministic letter-count vectors)."""

    embed_model = "syn-embed"
    chat_model = ""

    def embed(self, texts, cancel=None):
        out = []
        for value in texts:
            vector = [0.0] * 8
            for ch in kr.fold(value):
                if ch.isalnum():
                    vector[ord(ch) % 8] += 1.0
            out.append(vector)
        return out

    def status(self):
        return ll.ModelStatus(ll.NOT_CONFIGURED, "No local answer model chosen", "test", None, "syn-embed",
                              local_models=["syn-embed"], rejected_models=[])


class KeywordOnly:
    """The panel's adapter with no model configured (keyword retrieval only; nothing external)."""

    embed_model = ""
    chat_model = ""


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def world(app, tmp_path, monkeypatch):
    data = tmp_path / "data"
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(data),
                       "DRILLMASTER_DB_PATH": str(data / "synthetic-m51-knowledge.db"),
                       "DRILLMASTER_BACKUP_DIR": str(data / "backups"), "DRILLMASTER_AI_IMPORT": "0"}.items():
        monkeypatch.setenv(key, value)
    from core.database import DatabaseManager
    from core.selection_manager import SelectionManager
    from document_link_fixtures import without_session_user
    from m50_knowledge_fixtures import build_m50_corpus
    SelectionManager().clear()
    db = DatabaseManager()
    assert db.initialize(), db.last_diagnostic
    with without_session_user():
        ids = build_m50_corpus(db)
    from tabs.documents_tab import DocumentsTab
    tab = DocumentsTab(db)
    tab.show_dialogs = False
    panel = tab.assistant
    monkeypatch.setattr(panel, "_adapter", lambda: KeywordOnly())
    probe = []

    def on_execute(conn, cursor, statement, parameters, context, executemany):
        if threading.get_ident() == MAIN:
            probe.append(" ".join(statement.split())[:60])
    event.listen(db.engine, "before_cursor_execute", on_execute)
    yield tab, panel, ids, db, probe
    event.remove(db.engine, "before_cursor_execute", on_execute)
    tab.cleanup()
    SelectionManager().clear()
    db.close()


def _wait(app, condition, timeout=20.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return condition()


def _ask(app, panel, question=QUESTION):
    panel.question_edit.setPlainText(question)
    assert panel.ask()
    assert panel.current_state == "searching"                 # visible loading state while the worker reads
    assert _wait(app, lambda: panel.worker is None and panel.current_state not in
                 ("searching", "retrieving", "generating")), panel.current_state
    return panel.last_answer


def _external_sql(db, statement, **params):
    """A write by another program: its own connection, no ORM, no signal to the panel."""
    con = sqlite3.connect(db.db_path)
    try:
        con.execute(statement, params)
        con.commit()
    finally:
        con.close()


def _external_read(db, statement, **params):
    """The test's own reads use their own connection, so the GUI-engine probe sees only the panel."""
    con = sqlite3.connect(db.db_path)
    try:
        row = con.execute(statement, params).fetchone()
        return row[0] if row else None
    finally:
        con.close()


def _page_id(db, doc_id, page_no):
    return _external_read(db, "SELECT id FROM document_pages WHERE document_id = :d AND page_no = :p",
                          d=doc_id, p=page_no)


def _set_scope(panel, scope, target=None):
    panel.scope_combo.setCurrentIndex(panel.scope_combo.findData(scope))
    if target is not None:
        panel.target_combo.setCurrentIndex(panel.target_combo.findData(target))
    assert panel.current_scope() == (scope, target)


# ---- the GUI thread never reads the corpus ---------------------------------------------
def test_ask_reads_the_corpus_on_a_worker_with_its_own_connection(app, world, monkeypatch):
    _tab, panel, _ids, db, probe = world
    reads = []
    real = kr.read_corpus

    def recording(manager):
        reads.append((threading.get_ident(), manager.engine is db.engine))
        return real(manager)
    monkeypatch.setattr(kr, "read_corpus", recording)
    probe.clear()
    first = _ask(app, panel)
    second = _ask(app, panel)                                  # unchanged corpus: index reused
    assert first.state == "ready" and second.state == "ready"
    assert probe == [], probe[:5]
    assert reads and all(ident != MAIN and not gui_engine for ident, gui_engine in reads), reads
    assert len(reads) == 2                                     # one read per question, no second snapshot read


# ---- same-length edits and review status -----------------------------------------------
def test_same_length_text_edit_is_never_answered_from_the_old_passage(app, world):
    _tab, panel, ids, db, probe = world
    answer = _ask(app, panel)
    assert any("1.08 sg" in e.text for e in answer.evidence if e.document_id == ids["ke_program"]), \
        [e.text for e in answer.evidence]
    page = _page_id(db, ids["ke_program"], 1)
    before = kr.corpus_signature(db)
    _external_sql(db, "UPDATE document_pages SET text = replace(text, '1.08 sg', '1.18 sg') WHERE id = :p", p=page)
    after = kr.corpus_signature(db)
    # Precondition: every pre-M51 component (versions, count, max id, total length,
    # audit id, link digest) is unchanged - only the content digest sees the edit.
    assert before[:8] == after[:8] and before != after
    probe.clear()
    answer = _ask(app, panel)
    texts = [e.text for e in answer.evidence if e.document_id == ids["ke_program"]]
    assert any("1.18 sg" in t for t in texts) and not any("1.08 sg" in t for t in texts), texts
    new_text = _external_read(db, "SELECT text FROM document_pages WHERE id = :p", p=page)
    for e in answer.evidence:
        if e.page_id == page:
            assert e.text_version == hashlib.sha256(new_text.encode("utf-8")).hexdigest()
    assert "1.08" not in answer.text
    assert probe == []


def test_review_status_change_removes_and_restores_a_page(app, world):
    _tab, panel, ids, db, _probe = world
    page = _page_id(db, ids["ke_program"], 1)
    assert any(e.page_id == page for e in _ask(app, panel).evidence)
    _external_sql(db, "UPDATE document_pages SET review_status = 'needs_review' WHERE id = :p", p=page)
    answer = _ask(app, panel)
    assert all(e.page_id != page for e in answer.evidence), "an unapproved page was cited"
    _external_sql(db, "UPDATE document_pages SET review_status = 'extracted' WHERE id = :p", p=page)
    assert any(e.page_id == page for e in _ask(app, panel).evidence)


def _trip_sheet(volume):
    from core.document_library import PAGE_OK, READY, DocumentExtract, PageExtract
    body = f"SYNTHETIC trip sheet for SYN-KE-05. The trip tank volume is {volume} m3."
    return DocumentExtract(path="/synthetic/m51/trip", file_name="SYN-KE-05 trip sheet.txt", size_bytes=len(body),
                           sha256=hashlib.sha256(body.encode()).hexdigest(), kind="text", page_count=1,
                           status=READY, pages=[PageExtract(1, "lines 1-1", body, "text-file", PAGE_OK)])


def test_delete_and_reimport_reusing_ids_with_same_length_text(app, world):
    from core.document_library import PageDecision
    from document_link_fixtures import without_session_user
    tab, panel, _ids, db, _probe = world
    question = "trip tank volume SYN-KE-05"
    with without_session_user():
        first = tab.library.import_reviewed(_trip_sheet("4.2"), {1: PageDecision(approved=True)})
    assert first.status == "imported"
    old_page = _page_id(db, first.document_id, 1)
    assert any("4.2 m3" in e.text for e in _ask(app, panel, question).evidence)
    with without_session_user():
        assert tab.library.delete_document(first.document_id)
        second = tab.library.import_reviewed(_trip_sheet("4.7"), {1: PageDecision(approved=True)})
    assert second.status == "imported"
    # Precondition: SQLite reused the document and page ids (newest rows deleted), same text length.
    assert (second.document_id, _page_id(db, second.document_id, 1)) == (first.document_id, old_page)
    texts = [e.text for e in _ask(app, panel, question).evidence]
    assert any("4.7 m3" in t for t in texts) and not any("4.2 m3" in t for t in texts), texts


# ---- links: create / change / remove, scope never broadened ---------------------------
def test_link_create_change_and_remove_reach_the_next_answer_without_broadening(app, world):
    _tab, panel, ids, db, probe = world
    _set_scope(panel, kr.SCOPE_WELL, ids["well_e"])
    probe.clear()               # the scope combo's target list (well choices) is filled on the GUI thread
    answer = _ask(app, panel)
    assert (answer.retrieval.scope, answer.retrieval.target) == (kr.SCOPE_WELL, ids["well_e"])
    assert any(e.document_id == ids["ke_program"] for e in answer.evidence)
    # remove the link: the document leaves the well scope (no fallback to "all documents")
    _external_sql(db, "DELETE FROM document_links WHERE document_id = :d AND well_id = :w",
                  d=ids["ke_program"], w=ids["well_e"])
    answer = _ask(app, panel)
    allowed = {ids["ke_mud_rev"], ids["ke_daily_fa"], ids["equip"]}       # still linked to well_e
    assert all(e.document_id in allowed for e in answer.evidence), [e.document_id for e in answer.evidence]
    assert (answer.retrieval.scope, answer.retrieval.target) == (kr.SCOPE_WELL, ids["well_e"])
    # change it to another well: it is found there, not under well_e
    _external_sql(db, "INSERT INTO document_links (document_id, well_id, report_id, linked_by, linked_at) "
                      "VALUES (:d, :w, NULL, 'synthetic', CURRENT_TIMESTAMP)", d=ids["ke_program"], w=ids["well_f"])
    asks_sql = list(probe)
    _set_scope(panel, kr.SCOPE_WELL, ids["well_f"])
    probe.clear()
    answer = _ask(app, panel)
    assert any(e.document_id == ids["ke_program"] for e in answer.evidence)
    assert all(e.document_id in {ids["ke_program"], ids["kf_plan"]} for e in answer.evidence)
    assert asks_sql == [] and probe == [], (asks_sql[:3], probe[:3])


# ---- errors, cancellation, library change ----------------------------------------------
def test_read_error_on_the_worker_is_an_error_not_no_documents_and_retry_works(app, world, monkeypatch):
    _tab, panel, _ids, _db, _probe = world
    real = kr.read_corpus

    def broken(manager):
        raise sqlite3.OperationalError("synthetic read failure")
    monkeypatch.setattr(kr, "read_corpus", broken)
    panel.question_edit.setPlainText(QUESTION)
    assert panel.ask()
    assert _wait(app, lambda: panel.worker is None)
    assert panel.current_state == "error" and "could not be read" in panel.state_label.text()
    assert panel.last_answer is None and "No documents" not in panel.state_label.text()
    monkeypatch.setattr(kr, "read_corpus", real)
    assert _ask(app, panel).state == "ready"


def test_cancel_while_the_worker_reads_shows_nothing(app, world, monkeypatch):
    _tab, panel, _ids, _db, _probe = world
    real = kr.read_corpus
    entered, release = threading.Event(), threading.Event()

    def slow(manager):
        entered.set()
        release.wait(5)
        return real(manager)
    monkeypatch.setattr(kr, "read_corpus", slow)
    panel.question_edit.setPlainText(QUESTION)
    assert panel.ask()
    assert entered.wait(5)
    panel.cancel()
    release.set()
    assert _wait(app, lambda: not panel._old_workers)
    app.processEvents()
    assert panel.current_state == "cancelled" and panel.last_answer is None
    assert panel.answer_view.toPlainText() == ""


def test_library_change_is_checked_off_thread_and_only_a_real_change_invalidates(app, world):
    _tab, panel, ids, db, probe = world
    assert _ask(app, panel).state == "ready"
    probe.clear()
    panel.library_changed()                                    # nothing changed
    assert _wait(app, lambda: panel.check_worker is None)
    assert panel.current_state == "ready" and panel.last_answer is not None
    page = _page_id(db, ids["ke_program"], 1)
    _external_sql(db, "UPDATE document_pages SET text = replace(text, '1.08 sg', '1.28 sg') WHERE id = :p", p=page)
    panel.library_changed()
    assert _wait(app, lambda: panel.check_worker is None)
    assert panel.current_state == "stale" and panel.last_answer is None
    assert probe == [], probe[:5]


def test_semantic_build_reads_the_corpus_on_its_worker(app, world, monkeypatch):
    _tab, panel, _ids, _db, probe = world
    store = kr.EmbeddingStore(":memory:")
    monkeypatch.setattr(panel, "_adapter", lambda: ScriptedEmbedder())
    monkeypatch.setattr(panel, "_embedding_store", lambda: store)
    probe.clear()
    panel.build_semantic_index()
    assert _wait(app, lambda: panel.semantic_worker is None)
    assert panel.semantic_label.text().startswith("Semantic retrieval ready"), panel.semantic_label.text()
    assert panel._index is not None and panel._semantic_signature == panel._index.signature
    assert probe == [], probe[:5]
    store.close()


# ---- core: one read transaction ------------------------------------------------------------
def test_snapshot_and_signature_describe_one_database_state(world, monkeypatch):
    _tab, _panel, ids, db, _probe = world
    from core.export_jobs import worker_database
    before = kr.corpus_signature(db)
    real_rows = kr._page_rows

    def rows_then_external_write(session):
        rows = real_rows(session)
        # Another program links a document after the pages were read and
        # before the links / signature queries of the same snapshot run.
        _external_sql(db, "INSERT INTO document_links (document_id, well_id, report_id, linked_by, linked_at) "
                          "VALUES (:d, :w, NULL, 'synthetic', CURRENT_TIMESTAMP)", d=ids["equip"], w=ids["well_f"])
        return rows
    monkeypatch.setattr(kr, "_page_rows", rows_then_external_write)
    with worker_database(db) as reader:
        snapshot = kr.read_corpus(reader)
    monkeypatch.setattr(kr, "_page_rows", real_rows)
    assert snapshot.signature == before, "signature mixed two database states"
    assert ids["well_f"] not in snapshot.doc_wells.get(ids["equip"], set())
    assert kr.corpus_signature(db) != before                   # the write is seen by the next snapshot
