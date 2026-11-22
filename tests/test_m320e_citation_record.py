"""M320-E (M288): an answer frozen as an offline citation record and re-verified exactly (SYNTHETIC corpus).

The quote of every citation must be the exact slice of the stored page text; re-verification reports a changed,
removed or corrupted source and never re-anchors or repairs anything.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from core import citation_record as cr
from core import knowledge_answer as ka
from core import knowledge_retrieval as kr
from core.database import Document, DocumentPage
from m49_knowledge_fixtures import corpus_db

KICK = "What is the kick tolerance for the 8-1/2 in section?"


@pytest.fixture
def world():
    db, ids = corpus_db()
    index = kr.KnowledgeIndex(kr.read_corpus(db))
    answer = ka.answer_question(index, KICK)
    yield db, ids, answer
    index.close()
    db.engine.dispose()


def _page(db, page_id):
    with db.session_scope() as s:
        p = s.get(DocumentPage, page_id)
        return p.text


def test_record_quotes_are_exact_slices_of_the_stored_page(world):
    db, _ids, answer = world
    record = cr.build_record(answer, KICK)
    assert record["record_version"] == cr.RECORD_VERSION and record["semantic_label"] == ka.SEMANTIC_LABEL
    assert record["citation_label"] in (ka.CITATION_PASSED_LABEL, ka.CITATION_FAILED_LABEL)
    assert "50 bbl" in record["answer"]
    for c in record["citations"]:
        text = _page(db, c["page_id"])
        assert text[c["start"]:c["end"]] == c["quote"]
        assert hashlib.sha256(text.encode("utf-8")).hexdigest() == c["text_version"]
        assert f"[{c['label']}]" in record["answer"]
    results = cr.verify_record(db, record)
    assert [r["status"] for r in results] == [cr.EXACT] * len(record["citations"])
    assert cr.summary(results).startswith("ALL EXACT")


def test_changed_page_is_reported_never_re_anchored(world):
    db, _ids, answer = world
    record = cr.build_record(answer, KICK)
    page_id = record["citations"][0]["page_id"]
    with db.engine.begin() as conn:                       # an edit behind the library (simulates a re-review)
        conn.exec_driver_sql("UPDATE document_pages SET text = 'SYN replaced' || text WHERE id = ?", (page_id,))
    results = cr.verify_record(db, record)
    assert results[0]["status"] == cr.PAGE_CHANGED and "not trusted" in results[0]["reason"]
    assert cr.summary(results).startswith("NOT ALL EXACT")


def test_corrupted_span_missing_page_and_missing_document(world):
    db, _ids, answer = world
    record = cr.build_record(answer, KICK)
    bad = json.loads(json.dumps(record))
    bad["citations"][0]["start"] += 1
    assert cr.verify_record(db, bad)[0]["status"] == cr.SPAN_MISMATCH
    gone_page = json.loads(json.dumps(record))
    gone_page["citations"][0]["page_id"] = 987654
    assert cr.verify_record(db, gone_page)[0]["status"] == cr.PAGE_MISSING
    gone_doc = json.loads(json.dumps(record))
    gone_doc["citations"][0]["document_id"] = 987654
    assert cr.verify_record(db, gone_doc)[0]["status"] == cr.DOCUMENT_MISSING
    broken = json.loads(json.dumps(record))
    del broken["citations"][0]["quote"]
    assert cr.verify_record(db, broken)[0]["status"] == cr.UNREADABLE


def test_deleted_document_is_document_missing(world):
    db, _ids, answer = world
    record = cr.build_record(answer, KICK)
    doc_id = record["citations"][0]["document_id"]
    with db.engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        conn.exec_driver_sql("DELETE FROM document_pages WHERE document_id = ?", (doc_id,))
        conn.exec_driver_sql("DELETE FROM documents WHERE id = ?", (doc_id,))
    with db.session_scope() as s:
        assert s.get(Document, doc_id) is None
    assert cr.verify_record(db, record)[0]["status"] == cr.DOCUMENT_MISSING


def test_save_and_load_round_trip_with_markdown(world, tmp_path):
    db, _ids, answer = world
    record = cr.build_record(answer, KICK)
    json_path, md_path = cr.save(record, str(tmp_path / "kick"))
    assert json_path.endswith(".citations.json") and md_path.endswith(".citations.md")
    assert cr.load(json_path) == record
    md = open(md_path, encoding="utf-8").read()
    assert ka.SEMANTIC_LABEL in md and record["citations"][0]["text_version"] in md
    assert "> " + record["citations"][0]["quote"].split("\n")[0] in md
    (tmp_path / "other.json").write_text(json.dumps({"x": 1}), encoding="utf-8")
    with pytest.raises(cr.CitationRecordError):
        cr.load(str(tmp_path / "other.json"))
    with pytest.raises(cr.CitationRecordError):
        cr.load(str(tmp_path / "missing.json"))
    with pytest.raises(cr.CitationRecordError):
        cr.verify_record(db, {"record_version": "other"})


def test_no_ready_answer_cannot_be_recorded(world):
    db, _ids, _answer = world
    index = kr.KnowledgeIndex(kr.read_corpus(db))
    try:
        none = ka.answer_question(index, "What is the mud motor bend angle for SYN-ZZ-99?")
    finally:
        index.close()
    with pytest.raises(cr.CitationRecordError):
        cr.build_record(none, "bend angle")
    with pytest.raises(cr.CitationRecordError):
        cr.build_record(None, "x")


# ---- UI: Documents › Knowledge Assistant › "Export with citations…" / "Verify citation file…" --------------------
def test_assistant_exports_and_verifies_through_the_buttons(world, tmp_path, monkeypatch):
    from PySide6 import QtWidgets
    from PySide6.QtWidgets import QFileDialog

    from tabs import knowledge_assistant as kat

    db, _ids, answer = world
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    panel = kat.KnowledgeAssistantPanel(db)
    target = str(tmp_path / "kick.citations.json")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (target, ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (target, ""))
    try:
        assert not panel.export_citations_button.isEnabled()
        # The citation row must not widen the panel (Windows CI: M49 keeps minimumSizeHint < 1300 px). The header
        # row with "Open source in library" sets the width; the citation row stays at or below it.
        evidence_layout = panel.evidence_table.parentWidget().layout()
        rows = [evidence_layout.itemAt(i).layout() for i in range(evidence_layout.count())
                if evidence_layout.itemAt(i).layout() is not None]

        def _holding(widget):
            return next(r for r in rows if any(r.itemAt(i).widget() is widget for i in range(r.count())))

        header, citation = _holding(panel.open_source_button), _holding(panel.export_citations_button)
        assert header is not citation
        assert citation.minimumSize().width() <= header.minimumSize().width()
        panel.question_edit.blockSignals(True)
        panel.question_edit.setPlainText(KICK)
        panel.question_edit.blockSignals(False)
        panel.show_answer(answer)
        assert panel.export_citations_button.isEnabled()
        panel.export_citations_button.click()
        assert "Exported" in panel.citation_status.text() and ka.SEMANTIC_LABEL in panel.citation_status.text()
        assert cr.load(target)["question"] == KICK
        panel.verify_citations_button.click()
        assert panel.citation_status.text().startswith("ALL EXACT")
        page_id = cr.load(target)["citations"][0]["page_id"]
        with db.engine.begin() as conn:
            conn.exec_driver_sql("UPDATE document_pages SET text = text || ' SYN' WHERE id = ?", (page_id,))
        panel.verify_citations_button.click()
        assert panel.citation_status.text().startswith("NOT ALL EXACT") and "PAGE_CHANGED" in panel.citation_status.text()
        (tmp_path / "bad.json").write_text("{}", encoding="utf-8")
        assert panel.verify_citation_file(str(tmp_path / "bad.json")) is None
        assert panel.citation_status.text().startswith("Not verified")
    finally:
        panel.cleanup()
        panel.deleteLater()
        app.processEvents()


def test_a_page_of_another_document_is_page_missing(world):
    db, _ids, answer = world
    record = cr.build_record(answer, KICK)
    cited = record["citations"][0]
    with db.session_scope() as s:
        foreign = s.query(DocumentPage).filter(DocumentPage.document_id != int(cited["document_id"])).first().id
    moved = json.loads(json.dumps(record))
    moved["citations"][0]["page_id"] = foreign
    assert cr.verify_record(db, moved)[0]["status"] == cr.PAGE_MISSING
