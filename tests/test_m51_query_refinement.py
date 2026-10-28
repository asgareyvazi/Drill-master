"""M51 §7: query refinement after insufficient evidence.

Core part: ``KnowledgeIndex.refinement`` / ``ka.refined_question`` on the
SYNTHETIC M51 corpus (in-memory), and a sweep over the NON-blind question sets
(M51 dev, M50 dev + spent held-out, M49).  The M51 held-out split is not read
here.  Panel part: the real Documents tab + assistant panel on a temporary
FILE SQLite (production worker path), keyword retrieval only - no model is
configured or run.  Offscreen Qt on Linux, not Windows desktop testing.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "quality"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from core import knowledge_answer as ka  # noqa: E402
from core import knowledge_retrieval as kr  # noqa: E402

TYPO_EN = "What is the standpipe presure in the 12-1/4 in section of SYN-KG-07?"
TYPO_FA = "فشار لوله ایستاد در مقطع ۱۲-۱/۴ اینچ چاه SYN-KG-07"


@pytest.fixture(scope="module")
def corpus():
    from m51_knowledge_fixtures import m51_corpus_db
    db, ids = m51_corpus_db()
    index = kr.KnowledgeIndex(kr.read_corpus(db))
    yield index, ids
    index.close()
    db.engine.dispose()


# ---- core -------------------------------------------------------------------------------
def test_a_misspelled_word_gets_an_in_scope_spelling_and_the_refined_search_answers(corpus):
    index, _ids = corpus
    first = ka.answer_question(index, TYPO_EN)
    assert first.state == "no_evidence" and first.suggestions == ["pressure"] and first.replaces == ["presure"]
    refined = ka.refined_question(TYPO_EN, first.suggestions, first.replaces)
    assert "presure" not in refined and "SYN-KG-07" in refined and "12-1/4" in refined   # hard rules kept
    answer = ka.answer_question(index, refined)
    assert answer.state == "ready" and "2650 psi" in answer.text and answer.citation_checks_passed


def test_a_persian_question_is_refined_with_the_english_glossary_term_found_in_scope(corpus):
    index, _ids = corpus
    first = ka.answer_question(index, TYPO_FA)
    assert first.state == "no_evidence" and "standpipe pressure" in first.suggestions
    assert first.replaces == ["ایستاد"]                       # a question word, never a type label like "(pressure)"
    answer = ka.answer_question(index, ka.refined_question(TYPO_FA, first.suggestions, first.replaces))
    assert answer.state == "ready" and "2650 psi" in answer.text


def test_suggestions_come_only_from_the_selected_scope(corpus):
    index, ids = corpus
    question = "What is the kick toleranse?"
    assert any(kr.phrase_in(index._norm_tokens[c], ["tolerance"]) for c in index.candidate_chunks("all", None))
    in_h = ka.answer_question(index, question, kr.SCOPE_WELL, ids["well_h"])
    assert in_h.state == "no_evidence" and in_h.suggestions == []         # "tolerance" exists only outside it
    narrow = ka.answer_question(index, TYPO_EN.replace(" of SYN-KG-07", ""), kr.SCOPE_WELL, ids["well_h"])
    allowed = index.candidate_chunks(kr.SCOPE_WELL, ids["well_h"])
    for term in narrow.suggestions:
        assert any(kr.phrase_in(index._norm_tokens[c], kr.words(term)) for c in allowed), term


def test_no_suggestion_when_nothing_in_scope_matches_and_none_for_answers_or_empty_scope(corpus):
    index, ids = corpus
    assert ka.answer_question(index, "How many dayz should the 12-1/4 in section of SYN-KG-07 take?").suggestions == []
    assert ka.answer_question(index, "What is the kick tolerance for the 12-1/4 in section of SYN-KG-07?"
                              ).suggestions == []
    empty = ka.answer_question(index, TYPO_EN, kr.SCOPE_WELL, ids["well_m"])
    assert empty.state == "empty_scope" and empty.suggestions == []


def test_refined_question_keeps_numbers_codes_and_unrelated_words():
    assert ka.refinement_terms(" pressure ,، standpipe pressure; pressure\n") == ["pressure", "standpipe pressure"]
    assert ka.refined_question("mud weight of SYN-KG-07", []) == "mud weight of SYN-KG-07"
    out = ka.refined_question("The presure at 2650 of SYN-KG-07?", ["pressure"], ["presure", "2650", "kg"])
    assert out == "The at 2650 of SYN-KG-07? pressure"
    assert len(ka.refined_question("q", ["x" * 500])) <= 2 + ka.REFINE_MAX_CHARS


def _sets():
    from m49_gold_questions import GOLD as GOLD_M49
    from m49_knowledge_fixtures import corpus_db
    from m50_gold_questions import GOLD_M50
    from m50_knowledge_fixtures import m50_corpus_db
    from m51_gold_questions import GOLD_M51
    from m51_knowledge_fixtures import m51_corpus_db
    return [([q for q in GOLD_M51 if q["split"] == "dev"], m51_corpus_db),     # held-out split never read
            (GOLD_M50, m50_corpus_db), (GOLD_M49, corpus_db)]


def test_refining_every_refused_non_blind_question_keeps_scope_and_never_answers_an_unanswerable_one():
    from knowledge_eval_m49 import _in_scope
    refused = offered = 0
    for questions, make in _sets():
        db, ids = make()
        index = kr.KnowledgeIndex(kr.read_corpus(db))
        session = db.create_session()
        try:
            for q in questions:
                target = ids[q["target"]] if q.get("target") else None
                first = ka.answer_question(index, q["question"], q["scope"], target)
                if first.state != "no_evidence":
                    continue
                refused += 1
                for term in first.suggestions:
                    assert not any(ch.isdigit() for ch in term), (q["id"], term)
                if not first.suggestions:
                    continue
                offered += 1
                answer = ka.answer_question(index, ka.refined_question(q["question"], first.suggestions,
                                                                       first.replaces), q["scope"], target)
                assert (answer.retrieval.scope, answer.retrieval.target) == (q["scope"], target)
                assert all(_in_scope(session, e.document_id, q["scope"], target) for e in answer.evidence)
                if q.get("expect", "ready") != "ready":
                    assert answer.state != "ready", q["id"]          # zero false answers after refinement
        finally:
            session.close()
            index.close()
            db.engine.dispose()
    assert refused >= 30 and offered >= 4, (refused, offered)


# ---- panel ------------------------------------------------------------------------------
class KeywordOnly:
    embed_model = ""
    chat_model = ""


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def world(app, tmp_path, monkeypatch):
    data = tmp_path / "data"
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(data),
                       "DRILLMASTER_DB_PATH": str(data / "synthetic-m51-refine.db"),
                       "DRILLMASTER_BACKUP_DIR": str(data / "backups"), "DRILLMASTER_AI_IMPORT": "0"}.items():
        monkeypatch.setenv(key, value)
    from core.database import DatabaseManager
    from core.selection_manager import SelectionManager
    from document_link_fixtures import without_session_user
    from m51_knowledge_fixtures import build_m51_corpus
    SelectionManager().clear()
    db = DatabaseManager()
    assert db.initialize(), db.last_diagnostic
    with without_session_user():
        ids = build_m51_corpus(db)
    from tabs.documents_tab import DocumentsTab
    tab = DocumentsTab(db)
    tab.show_dialogs = False
    panel = tab.assistant
    monkeypatch.setattr(panel, "_adapter", lambda: KeywordOnly())
    yield panel, ids, db
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


def _settled(app, panel):
    assert _wait(app, lambda: panel.worker is None and panel.current_state not in
                 ("searching", "retrieving", "generating")), panel.current_state
    return panel.last_answer


def _ask(app, panel, question):
    panel.question_edit.setPlainText(question)
    assert panel.ask()
    return _settled(app, panel)


def _set_scope(panel, scope, target=None):
    panel.scope_combo.setCurrentIndex(panel.scope_combo.findData(scope))
    if target is not None:
        panel.target_combo.setCurrentIndex(panel.target_combo.findData(target))
    assert panel.current_scope() == (scope, target)


def test_panel_shows_the_refinement_and_searches_again_in_the_same_scope(app, world):
    panel, ids, _db = world
    _set_scope(panel, kr.SCOPE_WELL, ids["well_g"])
    first = _ask(app, panel, TYPO_EN)
    assert first.state == "no_evidence"
    shown = panel.answer_view.toPlainText()
    for heading in ("Refine the question", "Searched scope", "Found in this scope", "Missing",
                    "Related but not sufficient", "Semantic search", "Suggested technical terms"):
        assert heading in shown, heading
    assert "presure" in shown and "Semantic retrieval unavailable" in shown
    assert panel.suggest_edit.text() == "pressure" and panel.suggest_button.isEnabled()
    assert panel.ask_refined()
    assert panel.current_state == "searching" and panel.answer_view.toPlainText() == ""   # stale result cleared
    assert not panel.suggest_button.isEnabled()                                           # busy
    answer = _settled(app, panel)
    assert answer.state == "ready" and "2650 psi" in answer.text
    assert (answer.retrieval.scope, answer.retrieval.target) == (kr.SCOPE_WELL, ids["well_g"])
    assert panel.current_scope() == (kr.SCOPE_WELL, ids["well_g"])
    assert panel.question_edit.toPlainText() == TYPO_EN                                   # the question is kept
    diagnostics = panel.diagnostics_view.toPlainText()
    assert "Refined search" in diagnostics and "replacing: presure" in diagnostics and "same scope" in diagnostics
    assert "Search terms" in diagnostics and "pressure" in diagnostics
    assert panel.suggest_edit.text() == "" and not panel.suggest_button.isEnabled()


def test_the_button_is_disabled_without_suggestions_and_uses_the_edited_terms(app, world):
    panel, _ids, _db = world
    _ask(app, panel, "How many dayz should the 12-1/4 in section of SYN-KG-07 take?")
    assert panel.suggest_edit.text() == "" and not panel.suggest_button.isEnabled()
    assert not panel.ask_refined()
    _ask(app, panel, TYPO_EN)
    assert panel.suggest_button.isEnabled()
    panel.suggest_edit.setText("  ")
    assert not panel.suggest_button.isEnabled()                 # nothing to search with
    panel.suggest_edit.setText("pressure test")                 # the user's own wording is what is searched
    assert panel.ask_refined()
    answer = _settled(app, panel)
    assert answer.retrieval.question.endswith("pressure test") and "presure" not in answer.retrieval.question


def test_changing_the_scope_or_question_withdraws_the_suggestions(app, world):
    panel, ids, _db = world
    _ask(app, panel, TYPO_EN)
    assert panel.suggest_button.isEnabled()
    _set_scope(panel, kr.SCOPE_WELL, ids["well_h"])
    assert not panel.suggest_button.isEnabled() and panel.suggest_edit.text() == ""
    assert not panel.ask_refined()
    _set_scope(panel, kr.SCOPE_ALL)
    _ask(app, panel, TYPO_EN)
    panel.question_edit.setPlainText(TYPO_EN + " now")
    assert not panel.suggest_button.isEnabled() and panel.current_state == "stale"


def test_a_refined_search_reads_the_current_corpus_and_retry_repeats_it(app, world):
    panel, ids, db = world
    _ask(app, panel, TYPO_EN)
    con = sqlite3.connect(db.db_path)                          # another program, same length: 2650 -> 2560
    try:
        con.execute("UPDATE document_pages SET text = replace(text, '2650 psi', '2560 psi') "
                    "WHERE document_id = ? AND page_no = 2", (ids["g_program"],))
        con.commit()
    finally:
        con.close()
    assert panel.ask_refined()
    panel.cancel()
    assert panel.current_state == "cancelled" and panel.retry_button.isEnabled()
    assert panel.retry()
    answer = _settled(app, panel)
    assert answer.state == "ready" and "2560 psi" in answer.text and "2650 psi" not in answer.text
    assert "presure" not in answer.retrieval.question                   # Retry kept the refined search
    assert "Refined search" in panel.diagnostics_view.toPlainText()


def test_persian_suggestions_and_terms_render_right_to_left_and_escaped(app, world):
    from tabs.knowledge_assistant import render_refinement_html
    panel, _ids, _db = world
    first = _ask(app, panel, TYPO_FA)
    assert "standpipe pressure" in panel.suggest_edit.text()
    panel.suggest_edit.setText("فشار لوله، standpipe pressure")
    assert panel.suggest_edit.alignment() & panel.suggest_edit.alignment().AlignRight
    page = render_refinement_html(first, "All <b>documents</b>")
    assert '<span dir="rtl">ایستاد</span>' in page and '<span dir="ltr">standpipe pressure</span>' in page
    assert "<b>documents</b>" not in page and "&lt;b&gt;documents&lt;/b&gt;" in page
    first.suggestions = ["<img src=x>"]
    assert "<img" not in render_refinement_html(first) and "&lt;img src=x&gt;" in render_refinement_html(first)
    ready = _ask(app, panel, "What is the kick tolerance for the 12-1/4 in section of SYN-KG-07?")
    assert ready.state == "ready" and render_refinement_html(ready) == ""
