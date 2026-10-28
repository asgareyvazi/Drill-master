"""M50 citation navigation (offscreen Qt; NOT native Windows desktop testing).

Real Documents tab + assistant panel on a real in-memory SQLite database with
the SYNTHETIC M50 corpus.  Every cited passage must open its exact page and
character span; a page that changed after the answer, or a deleted document,
must never be highlighted as if it were the cited text.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from m50_knowledge_fixtures import m50_corpus_db  # noqa: E402

QUESTION = "mud weight for the 16 in section of SYN-KE-05"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def world(app):
    from core.selection_manager import SelectionManager
    SelectionManager().clear()
    db, ids = m50_corpus_db()
    from tabs.documents_tab import DocumentsTab
    tab = DocumentsTab(db)
    tab.show_dialogs = False
    tab.resize(1300, 900)
    yield tab, tab.assistant, ids, db
    tab.cleanup()
    SelectionManager().clear()
    db.engine.dispose()


def _wait(app, condition, timeout=15.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    app.processEvents()
    return condition()


def _ask(app, panel, question):
    panel.question_edit.setPlainText(question)
    assert panel.ask()
    assert _wait(app, lambda: panel.worker is None and panel.current_state not in
                 ("searching", "retrieving", "generating")), panel.current_state


def _selected(tab):
    selections = tab.viewer.extraSelections()        # keep the list alive (PySide object lifetime)
    return [s.cursor.selectedText() for s in selections]


def _edit_page(db, page_id, transform):
    from core.database import DocumentPage
    session = db.create_session()
    try:
        page = session.get(DocumentPage, page_id)
        page.text = transform(page.text)
        session.commit()
        return page.text
    finally:
        session.close()


def test_every_citation_opens_its_exact_page_and_span(app, world):
    tab, panel, _ids, _db = world
    _ask(app, panel, QUESTION)
    evidence = panel.last_answer.evidence
    pages = [e.page_id for e in evidence]
    assert len(pages) != len(set(pages)), "needs two passages from one page"
    by_page_no = {}
    for e in evidence:
        by_page_no.setdefault(e.page_no, set()).add(e.document_id)
    assert any(len(docs) > 1 for docs in by_page_no.values()), "needs one page number in several documents"
    for row, item in enumerate(evidence):
        assert panel.open_evidence_row(row)
        assert tab.current_document_id == item.document_id and tab.page_combo.currentData() == item.page_no
        assert tab.cited_span == (item.document_id, item.page_no, item.start, item.end)
        assert _selected(tab) == [item.text], (row, item.label)


def test_changed_page_is_not_highlighted_as_the_cited_text(app, world):
    tab, panel, _ids, db = world
    _ask(app, panel, QUESTION)
    item = panel.last_answer.evidence[0]
    # Same length, span still in range - only the text version differs.
    _edit_page(db, item.page_id, lambda t: t.replace(" sg", " SG"))
    assert not panel.open_evidence_row(0) or tab.cited_span is None
    assert tab.cited_span is None and _selected(tab) == []
    assert "changed since the answer" in tab.viewer_title.text()


def test_reimported_changed_text_is_answered_not_a_stale_index(app, world):
    """Pages are immutable after import (core.knowledge_retrieval.corpus_signature); a changed text arrives
    by delete + re-import, which must reach the next answer and open at its new span."""
    from dataclasses import replace

    from core.document_library import PageDecision
    from m50_knowledge_fixtures import DOCS, _extract
    tab, panel, ids, _db = world
    _ask(app, panel, QUESTION)
    item = next(e for e in panel.last_answer.evidence if any(ids[r] == e.document_id for r in DOCS))
    role = next(r for r in DOCS if ids[r] == item.document_id)
    old = _extract(role)
    pages = [replace(page, text=page.text.replace(" sg", " SG")) for page in old.pages]
    changed = replace(old, pages=pages, sha256=hashlib.sha256(b"changed:" + old.sha256.encode()).hexdigest())
    assert tab.library.delete_document(item.document_id)
    outcome = tab.library.import_reviewed(changed, {p.page_no: PageDecision(approved=True) for p in pages})
    assert outcome.status == "imported", outcome.message
    _ask(app, panel, QUESTION)
    fresh = [e for e in panel.last_answer.evidence if e.document_id == outcome.document_id]
    assert fresh, "the re-imported document must be retrievable"
    for e in fresh:
        stored = next(p.text for p in pages if p.page_no == e.page_no)
        assert e.text_version == hashlib.sha256(stored.encode("utf-8")).hexdigest()
        assert e.text == stored[e.start:e.end]
    row = panel.last_answer.evidence.index(fresh[0])
    assert panel.open_evidence_row(row) and _selected(tab) == [fresh[0].text]
    # The answer from BEFORE the re-import cannot be opened on the new document's pages.
    assert tab.open_evidence(item.document_id, item.page_no, item.start, item.end, item.text_version) is False


def test_deleted_document_cannot_be_opened_from_an_old_citation(app, world):
    tab, panel, _ids, _db = world
    _ask(app, panel, QUESTION)
    item = panel.last_answer.evidence[0]
    assert tab.library.delete_document(item.document_id)
    assert tab.open_evidence(item.document_id, item.page_no, item.start, item.end, item.text_version) is False
    assert tab.cited_span is None


def test_failed_draft_is_escaped_and_lists_failed_dimensions():
    from core import knowledge_answer as ka
    from tabs.knowledge_assistant import render_failed_draft_html
    check = ka.CitationCheck()
    check.fail("units_match", "1.42 ppg is stated as 1.42 sg in the cited source(s)")
    html = render_failed_draft_html("<script>alert(1)</script> 1.42 ppg [S1]", check)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "MODEL DRAFT NOT USED" in html and "✗ Every value keeps the unit" in html
    assert "– Every citation names a retrieved passage" in html
