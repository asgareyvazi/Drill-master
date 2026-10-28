"""M50 §6/§9: assistant states are never shown stronger than they are.

Offscreen Qt (NOT native Windows desktop testing), real Documents tab and
assistant on an in-memory SQLite database with the SYNTHETIC M50 corpus.  The
embedder and model status objects stand in for the EXTERNAL local model server
(isolation only; no real model was run - NOT RUN, none installed).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from core import knowledge_answer as ka  # noqa: E402
from core import knowledge_retrieval as kr  # noqa: E402
from core import local_llm as ll  # noqa: E402
from m50_knowledge_fixtures import m50_corpus_db  # noqa: E402

QUESTION = "mud weight for the 16 in section of SYN-KE-05"


class ScriptedEmbedder:
    """Stand-in for the external embedding model: deterministic bag-of-letters vectors."""

    embed_model = "syn-embed"
    chat_model = ""

    def embed(self, texts, cancel=None):
        out = []
        for text in texts:
            vector = [0.0] * 8
            for ch in kr.fold(text):
                if ch.isalnum():
                    vector[ord(ch) % 8] += 1.0
            out.append(vector)
        return out

    def status(self):
        return ll.ModelStatus(ll.NOT_CONFIGURED, "No local answer model chosen", "test", None, "syn-embed",
                              local_models=["syn-embed"], rejected_models=[])


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def world(app, monkeypatch):
    from core.selection_manager import SelectionManager
    SelectionManager().clear()
    db, ids = m50_corpus_db()
    from tabs.documents_tab import DocumentsTab
    tab = DocumentsTab(db)
    tab.show_dialogs = False
    panel = tab.assistant
    store = kr.EmbeddingStore(":memory:")
    monkeypatch.setattr(panel, "_adapter", lambda: ScriptedEmbedder())
    monkeypatch.setattr(panel, "_embedding_store", lambda: store)
    yield tab, panel, ids, db
    tab.cleanup()
    SelectionManager().clear()
    db.engine.dispose()


def _wait(app, condition, timeout=20.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return condition()


def _build(app, panel):
    panel.build_semantic_index()
    assert _wait(app, lambda: panel.semantic_worker is None)
    assert panel.semantic_label.text().startswith("Semantic retrieval ready"), panel.semantic_label.text()


def _ask(app, panel, question=QUESTION):
    panel.question_edit.setPlainText(question)
    assert panel.ask()
    assert _wait(app, lambda: panel.worker is None and panel.current_state not in
                 ("searching", "retrieving", "generating")), panel.current_state
    return panel.last_answer


def test_semantic_index_is_used_while_it_matches_the_documents(app, world):
    _tab, panel, _ids, _db = world
    _build(app, panel)
    answer = _ask(app, panel)
    assert "semantic" in answer.retrieval.lists_used, answer.retrieval.lists_used
    assert not any(name == "semantic" for name, _ in answer.retrieval.unavailable)


def test_library_change_marks_the_semantic_index_out_of_date(app, world):
    tab, panel, ids, _db = world
    _build(app, panel)
    assert tab.library.delete_document(ids["ke_mud_rev"] if "ke_mud_rev" in ids else _any_doc(panel, app))
    panel.library_changed()                        # what the Documents tab does after a delete
    assert panel.semantic_label.text().startswith("Semantic index out of date"), panel.semantic_label.text()
    answer = _ask(app, panel)
    assert "semantic" not in answer.retrieval.lists_used
    assert any(name == "semantic" and "not built for the current documents" in reason
               for name, reason in answer.retrieval.unavailable)


def test_change_made_elsewhere_is_noticed_at_the_next_question(app, world):
    from core.document_library import DocumentLibrary
    _tab, panel, _ids, db = world
    _build(app, panel)
    doc = _any_doc(panel, app)
    other = DocumentLibrary(db)                    # another window / import, no signal to this panel
    try:
        assert other.delete_document(doc)
    finally:
        other.close()
    assert panel.semantic_label.text().startswith("Semantic retrieval ready")   # nothing told the panel yet
    _ask(app, panel)
    assert panel.semantic_label.text().startswith("Semantic index out of date"), panel.semantic_label.text()


def _any_doc(panel, app):
    answer = _ask(app, panel)
    return answer.evidence[0].document_id


@pytest.mark.parametrize("state, expected", [
    (ll.NOT_RUNNING, "Local model unavailable"),
    (ll.MODEL_MISSING, "Local model unavailable"),
    (ll.REMOTE_REJECTED, "Local model unavailable"),
    (ll.NOT_CONFIGURED, "Local model unavailable"),
    (ll.TIMEOUT, "Local model unavailable"),
])
def test_generation_is_offered_only_when_the_local_model_is_ready(app, world, state, expected):
    _tab, panel, _ids, _db = world
    panel.apply_model_status(ll.ModelStatus(state, "scripted", "test", "syn-chat", None,
                                            local_models=[], rejected_models=["kimi-k2.6:cloud"]))
    assert panel.model_label.text().startswith(expected)
    assert "Refused (would run outside this computer): kimi-k2.6:cloud" in panel.model_label.text()
    assert not panel.use_model_check.isEnabled() and not panel.use_model_check.isChecked()
    assert "Semantic retrieval unavailable" in panel.semantic_label.text()
    ready = ll.ModelStatus(ll.READY, "Local answer model 'syn-chat' is available", "test", "syn-chat", None,
                           local_models=["syn-chat"], rejected_models=[])
    ready.embed_state = ll.NOT_CONFIGURED
    panel.apply_model_status(ready)
    assert panel.use_model_check.isEnabled()
    assert "no local embedding model configured" in panel.semantic_label.text()


# ------------------------------------------------------------------ §9 diagnostics
def _diag(panel):
    return panel.diagnostics_view.toPlainText()


def test_diagnostics_of_a_lexical_answer_name_methods_scope_validation_and_conflict(app, world):
    _tab, panel, _ids, _db = world
    answer = _ask(app, panel, "What is the planned mud weight for the 16 in section of SYN-KE-05?")
    text = _diag(panel)
    assert answer.state == "ready" and answer.retrieval.conflicts
    assert "extractive - quoted from the documents, no model used" in text
    assert "keywords (BM25)" in text and "semantic (local embeddings)" not in text
    # the scripted embedder is configured but nothing was embedded yet: that is the reason shown
    assert "Semantic retrieval unavailable: the semantic index is not built for the current documents" in text
    r = answer.retrieval
    assert f"{r.scope_documents} eligible document(s), {r.scope_pages} reviewed page(s)" in text
    assert f"Passages used\n{len(answer.evidence)}\n" in text
    assert "Citation checks passed · Not semantically verified" in text
    for conflict in r.conflicts:
        for value, _cid in conflict.values:
            assert f"{value:g} {conflict.unit}" in text
    assert "none detected" not in text


def test_diagnostics_show_semantic_use_only_when_it_ran(app, world):
    _tab, panel, _ids, _db = world
    _build(app, panel)
    _ask(app, panel)
    text = _diag(panel)
    assert "semantic (local embeddings)" in text and "Semantic retrieval\nused" in text.replace("\t", "\n")


def test_diagnostics_of_a_refusal_say_why_and_claim_no_validation(app, world):
    _tab, panel, _ids, _db = world
    answer = _ask(app, panel, "What is the planned mud weight for the 8-1/2 in section of SYN-KE-05?")
    text = _diag(panel)
    assert answer.state == "no_evidence" and answer.mode == "none"
    assert "no answer given" in text and "Insufficient evidence" in text and "8-1/2 in" in text
    assert "Closest passages examined (not enough to answer)" in text and "Passages used" not in text
    assert "not applicable - no answer was given" in text and "Citation checks passed" not in text
    assert "Missing: 8-1/2 in." in text                      # not "8, 2, 8-1/2 in"
    shown = panel.answer_view.toPlainText()
    assert "elsewhere in this scope): 8-1/2 in" in shown and ": 8, 2" not in shown


def test_display_terms_drops_only_number_fragments_of_a_listed_term():
    assert ka.display_terms(["8", "2", "8-1/2 in"]) == ["8-1/2 in"]
    assert ka.display_terms(["12", "mud weight"]) == ["12", "mud weight"]   # a lone number stays
    assert ka.display_terms([]) == []


def test_diagnostics_are_cleared_with_a_stale_answer(app, world):
    _tab, panel, _ids, _db = world
    _ask(app, panel)
    assert _diag(panel)
    panel.question_edit.setPlainText(QUESTION + " please")      # editing the question invalidates the answer
    app.processEvents()
    assert panel.last_answer is None and _diag(panel) == ""


def test_diagnostics_escape_document_and_model_text():
    from core import knowledge_answer as ka
    from tabs.knowledge_assistant import render_diagnostics_html
    answer = ka.Answer("no_evidence", "none", "<script>alert(1)</script>", [], None,
                       model_state="timeout", model_message="<img src=x onerror=alert(1)>")
    html_text = render_diagnostics_html(answer, "<b>scope</b>")
    assert "<script>" not in html_text and "<img" not in html_text
    assert "&lt;script&gt;" in html_text and "&lt;img" in html_text


def test_embedding_reason_is_not_misreported_when_the_server_is_down(app, world):
    """M50 screenshot review: with 'bge-m3' entered and no server, the label claimed no model was configured."""
    _tab, panel, _ids, _db = world
    panel.embed_model_combo.setEditText("bge-m3")
    panel.apply_model_status(ll.ModelStatus(ll.NOT_RUNNING, "No local model server is running", None))
    text = panel.semantic_label.text()
    assert "no local embedding model configured" not in text
    assert "embedding model 'bge-m3' could not be checked - No local model server is running" in text
    missing = ll.ModelStatus(ll.NOT_CONFIGURED, "No local answer model chosen", "test", None, "bge-m3",
                             local_models=[])
    missing.embed_state = ll.MODEL_MISSING
    panel.apply_model_status(missing)
    assert "embedding model 'bge-m3': model missing" in panel.semantic_label.text()
    panel.embed_model_combo.setEditText("")
    panel.apply_model_status(ll.ModelStatus(ll.NOT_RUNNING, "No local model server is running", None))
    assert "no local embedding model configured" in panel.semantic_label.text()
