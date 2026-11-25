"""M472 (U2): real MainWindow journey. A user opens a saved ``.citations.json`` record on the Documents tab's
library page and reaches the cited passage. A record edited to point at another file is refused.

SYNTHETIC documents (``tests/document_link_fixtures.py``); Linux offscreen Qt (not Windows acceptance).
"""
from __future__ import annotations

import hashlib
import json

import pytest

from core import citation_record as cr
from test_m70_selection_audit import _pump, window  # noqa: F401  (module fixture reused)

QUOTE = "casing shoe set at 1250 m"


def _tab(win, name):
    for i in range(win.tab_widget.count()):
        widget = win.tab_widget.widget(i)
        if type(widget).__name__ == name:
            win.tab_widget.setCurrentWidget(widget)
            _pump(0.3)
            return widget
    raise LookupError(name)


@pytest.fixture
def record_path(window, tmp_path):  # noqa: F811
    _win, db, _ids = window
    from core.database import Document, DocumentPage
    from document_link_fixtures import import_documents, write_documents
    with db.session_scope() as s:
        existing = s.query(Document.id).filter(Document.file_name == "syn_alpha_daily.txt").first()
    if existing is None:
        import_documents(db, {"alpha": write_documents(tmp_path / "docs")["alpha"]})
    with db.session_scope() as s:
        doc = s.query(Document).filter(Document.file_name == "syn_alpha_daily.txt").one()
        page = next(p for p in s.query(DocumentPage).filter(DocumentPage.document_id == doc.id).all()
                    if QUOTE in (p.text or ""))
        start = page.text.index(QUOTE)
        citation = {"label": "S1", "document_id": doc.id, "file_name": doc.file_name, "page_id": page.id,
                    "page_no": page.page_no, "location": f"page {page.page_no}", "start": start,
                    "end": start + len(QUOTE), "text_version": hashlib.sha256(page.text.encode("utf-8")).hexdigest(),
                    "quote": QUOTE, "review_status": "approved", "method": "text", "instruction_like": False}
    record = {"record_version": cr.RECORD_VERSION, "created_at": "2026-10-13T00:00:00+00:00",
              "question": "SYN casing shoe?", "answer": "SYN answer [S1]", "mode": "extractive",
              "citation_label": "SYN", "semantic_label": "Not semantically verified", "problems": [], "notes": [],
              "citations": [citation]}
    path = tmp_path / "syn.citations.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def test_documents_tab_opens_a_record_passage_through_the_file_dialog(window, record_path, monkeypatch):  # noqa: F811
    import PySide6.QtWidgets as qw
    win, _db, _ids = window
    tab = _tab(win, "DocumentsTab")
    monkeypatch.setattr(qw.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(record_path), "")))
    tab.open_citation_file_button.click()
    _pump(0.2)
    assert [t["status"] for t in tab.citation_file_targets] == [cr.EXACT]
    tab.open_citation_passage_button.click()
    _pump(0.2)
    selections = tab.viewer.extraSelections()
    assert [s.cursor.selectedText() for s in selections] == [QUOTE]
    assert "cited passage" in tab.viewer_title.text() and "syn_alpha_daily.txt" in tab.viewer_title.text()


def test_documents_tab_refuses_a_record_pointing_at_another_file(window, record_path):  # noqa: F811
    from core import citation_passage as cp
    win, _db, _ids = window
    tab = _tab(win, "DocumentsTab")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["citations"][0]["file_name"] = "SYN-OTHER.pdf"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    results = tab.open_citation_file(str(record_path))
    assert results[0]["status"] == cp.IDENTITY_MISMATCH
    assert not tab.open_citation_passage_button.isEnabled()
    assert tab.open_citation_target(0) is False
