"""M334 (A-8): open a passage cited by a saved citation record (offscreen Qt, SYNTHETIC M50 corpus).

Real Documents tab + assistant panel. A verified EXACT citation opens its page with exactly the quote highlighted;
a changed page opens without a highlight and states the change; a broken span or a missing document opens nothing.
"""
from __future__ import annotations

import json

import pytest

from core import citation_record as cr
from test_m50_citation_navigation import QUESTION, _ask, _edit_page, _selected, app, world  # noqa: F401


def _verified(tmp_path, app, panel):  # noqa: F811
    _ask(app, panel, QUESTION)
    path = str(tmp_path / "answer.citations.json")
    assert panel.export_citations(path)
    return path


def test_exact_citation_opens_its_page_with_the_quote_highlighted(tmp_path, app, world):  # noqa: F811
    tab, panel, _ids, _db = world
    path = _verified(tmp_path, app, panel)
    assert panel.record_navigation.isHidden()
    results = panel.verify_citation_file(path)
    assert results and all(r["status"] == cr.EXACT for r in results)
    assert not panel.record_navigation.isHidden()
    assert panel.record_citation_combo.count() == len(results)
    assert panel.record_citation_combo.itemText(0).startswith(f"[{results[0]['label']}] EXACT")
    assert panel.open_record_citation_button.isEnabled()
    record = cr.load(path)
    panel.open_record_citation_button.click()
    first = record["citations"][0]
    assert _selected(tab) == [first["quote"]]
    assert tab.cited_span == (first["document_id"], first["page_no"], first["start"], first["end"])


def test_changed_page_opens_without_a_highlight_and_says_so(tmp_path, app, world):  # noqa: F811
    tab, panel, _ids, db = world
    path = _verified(tmp_path, app, panel)
    first = cr.load(path)["citations"][0]
    _edit_page(db, first["page_id"], lambda text: "SYN inserted. " + text)
    results = panel.verify_citation_file(path)
    assert results[0]["status"] == cr.PAGE_CHANGED
    assert panel.open_record_citation_button.isEnabled()          # the page can be read, the span is not trusted
    assert panel.open_record_citation(0) is True
    assert tab.cited_span is None and _selected(tab) == []
    assert "has changed" in tab.viewer_title.text()


def test_broken_span_and_missing_document_open_nothing(tmp_path, app, world):  # noqa: F811
    tab, panel, _ids, _db = world
    path = _verified(tmp_path, app, panel)
    record = cr.load(path)
    bad = json.loads(json.dumps(record))
    bad["citations"][0]["start"] += 1
    shifted = tmp_path / "shifted.citations.json"
    shifted.write_text(json.dumps(bad), encoding="utf-8")
    assert panel.verify_citation_file(str(shifted))[0]["status"] == cr.SPAN_MISMATCH
    assert not panel.open_record_citation_button.isEnabled()
    assert "Not openable" in panel.open_record_citation_button.toolTip()
    seen = []
    panel.open_evidence_requested.connect(lambda *a: seen.append(a))
    assert panel.open_record_citation(0) is False and seen == []
    assert "not opened – SPAN_MISMATCH" in panel.citation_status.text()
    assert tab.library.delete_document(record["citations"][0]["document_id"])
    results = panel.verify_citation_file(path)
    assert results[0]["status"] == cr.DOCUMENT_MISSING
    assert panel.open_record_citation(0) is False and seen == []


def test_an_unreadable_file_clears_the_previous_record_targets(tmp_path, app, world):  # noqa: F811
    _tab, panel, _ids, _db = world
    path = _verified(tmp_path, app, panel)
    panel.verify_citation_file(path)
    assert panel.record_targets
    (tmp_path / "bad.json").write_text("{}", encoding="utf-8")
    assert panel.verify_citation_file(str(tmp_path / "bad.json")) is None
    assert panel.record_targets == [] and panel.record_navigation.isHidden()


def test_navigation_refuses_results_of_another_record():
    record = {"citations": [{"label": "1"}]}
    with pytest.raises(cr.CitationRecordError):
        cr.navigation(record, [])
    targets = cr.navigation({"citations": [{"label": "1"}]},
                            [{"label": "1", "status": cr.UNREADABLE, "reason": "missing quote"}])
    assert targets[0]["openable"] is False and "document_id" not in targets[0]


def test_the_navigation_row_never_widens_the_panel(tmp_path, app, world):  # noqa: F811
    """A-9: the record row is narrower than the header row that sets the panel width (Windows M49 < 1300 px)."""
    tab, panel, _ids, _db = world
    tab.sections.setCurrentWidget(panel)
    tab.show()                                   # unshown size hints are stale (M352): measure a shown panel
    app.processEvents()
    assert panel.isVisible()
    before = panel.minimumSizeHint().width()
    panel._show_record_targets([{"label": "1", "status": cr.EXACT, "reason": "", "openable": True,
                                 "file_name": "SYN " + "very long file name " * 6 + ".pdf", "page_no": 12,
                                 "document_id": 1, "start": 0, "end": 5, "text_version": "x"}])
    app.processEvents()
    assert panel.record_navigation.isVisible()
    header = panel.open_source_button.parentWidget().layout()
    assert panel.record_navigation.minimumSizeHint().width() <= panel.minimumSizeHint().width()
    assert panel.minimumSizeHint().width() == before
    assert header is not panel.record_navigation.layout()
    tab.hide()
