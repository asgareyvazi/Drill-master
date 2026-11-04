"""M114: document search follows the scope - no cross-well leak in a well-scoped view, the limit applies after
the restriction, a well switch or a deletion never keeps stale hits, page citations, offline, honest "no text
layer". Links stay manual (suggestions are proposals only).

SYNTHETIC documents only (tests/document_link_fixtures.py); in-memory SQLite; offscreen Qt (not a Windows
desktop test).
"""
from __future__ import annotations

import os
import socket
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.document_library import DocumentLibrary, extract_document  # noqa: E402
from core.document_links import DocumentLinkService  # noqa: E402
from document_link_fixtures import build_link_world, import_documents, without_session_user, write_documents  # noqa: E402
from test_document_library import _pdf  # noqa: E402
from test_scope_attribution import _mgr  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def world(app, tmp_path):
    with without_session_user():
        db = _mgr()
        ids = build_link_world(db)
        ids["docs"] = import_documents(db, write_documents(tmp_path / "docs"))
        links = DocumentLinkService(db)
        links.create_link(ids["docs"]["alpha"], ids["alpha"], page_no=2)
        links.create_link(ids["docs"]["twin"], ids["twin_1"])
        yield db, ids, links
        db.engine.dispose()


@pytest.fixture
def tab(world):
    from tabs.documents_tab import DocumentsTab
    db, ids, links = world
    widget = DocumentsTab(db)
    widget.show_dialogs = False
    try:
        yield widget, db, ids, links
    finally:
        widget.cleanup()
        widget.deleteLater()


def _docs(result):
    return {hit["document_id"] for hit in result["hits"]}


def _select_filter(widget, key):
    widget.filter_combo.setCurrentIndex(next(i for i in range(widget.filter_combo.count())
                                             if widget.filter_combo.itemData(i) == key))


@pytest.mark.parametrize("fts", [True, False])
def test_a_scoped_search_returns_only_documents_in_scope(world, monkeypatch, fts):
    db, ids, _links = world
    library = DocumentLibrary(db)
    if not fts:
        monkeypatch.setattr(library, "_ensure_index", lambda: None)          # substring-scan fallback
    everything = library.search("SYNTHETIC")
    assert {ids["docs"]["alpha"], ids["docs"]["twin"], ids["docs"]["unrelated"]} <= _docs(everything)
    assert everything["scope"] == "whole library"
    alpha = library.search("SYNTHETIC", document_ids={ids["docs"]["alpha"]})
    assert _docs(alpha) == {ids["docs"]["alpha"]} and alpha["scope"] == "1 document(s) in scope"
    nothing = library.search("SYNTHETIC", document_ids=set())                    # empty scope: nothing
    assert nothing["hits"] == [] and nothing["status"] == "no_matches"
    assert library.search("pump pressure", document_ids={ids["docs"]["alpha"]})["status"] == "no_matches"
    assert _docs(library.search("pump pressure")) == {ids["docs"]["twin"]}
    library.close()


@pytest.mark.parametrize("fts", [True, False])
def test_the_limit_applies_after_the_restriction(world, monkeypatch, fts):
    db, ids, _links = world
    library = DocumentLibrary(db)
    if not fts:
        monkeypatch.setattr(library, "_ensure_index", lambda: None)
    top = library.search("SYNTHETIC", limit=1)
    assert len(top["hits"]) == 1
    other = ({ids["docs"]["alpha"], ids["docs"]["twin"], ids["docs"]["unrelated"]} - _docs(top)).pop()
    scoped = library.search("SYNTHETIC", limit=1, document_ids={other})
    assert len(scoped["hits"]) == 1 and _docs(scoped) == {other}
    library.close()


def test_the_well_scoped_view_searches_only_that_well_and_follows_the_switch(tab):
    widget, _db, ids, _links = tab
    widget.on_context_changed(SimpleNamespace(well_id=ids["alpha"]))
    _select_filter(widget, "selected_well")
    widget.search_edit.setText("SYNTHETIC")
    widget.run_search()
    assert _docs(widget.last_search) == {ids["docs"]["alpha"]}
    assert "Scope: documents linked to the selected well" in widget.search_info.text()
    widget.on_context_changed(SimpleNamespace(well_id=ids["twin_1"]))          # switch: re-run, never stale
    assert _docs(widget.last_search) == {ids["docs"]["twin"]}
    texts = [widget.results.item(i).text() for i in range(widget.results.count())]
    assert texts and all("syn_alpha" not in t for t in texts)
    widget.on_context_changed(SimpleNamespace(well_id=ids["twin_2"]))          # same name, other well: no links
    assert widget.results.count() == 0 and widget.last_search["hits"] == []
    widget.on_context_changed(SimpleNamespace(well_id=None))                   # no well: no hits at all
    assert widget.results.count() == 0 and "Select a well" in widget.search_info.text()


def test_the_list_filters_and_the_search_agree(tab):
    widget, _db, ids, _links = tab
    widget.search_edit.setText("SYNTHETIC")
    widget.run_search()
    assert "Scope: whole library" in widget.search_info.text()
    assert ids["docs"]["alpha"] in _docs(widget.last_search)
    _select_filter(widget, "unlinked")                                          # re-runs the open search
    assert ids["docs"]["alpha"] not in _docs(widget.last_search)
    assert ids["docs"]["unrelated"] in _docs(widget.last_search)
    assert "Scope: documents not linked to a well" in widget.search_info.text()
    _select_filter(widget, "linked")
    assert _docs(widget.last_search) == {ids["docs"]["alpha"], ids["docs"]["twin"]}
    listed = {widget.table.item(r, 0).data(0x0100) for r in range(widget.table.rowCount())}   # Qt.UserRole
    assert _docs(widget.last_search) <= listed


def test_deleting_a_document_removes_its_hits_from_the_open_search(tab):
    widget, db, ids, _links = tab
    widget.search_edit.setText("SYNTHETIC")
    widget.run_search()
    assert ids["docs"]["alpha"] in _docs(widget.last_search)
    library = DocumentLibrary(db)
    assert library.delete_document(ids["docs"]["alpha"])
    library.close()
    widget.refresh()                                                            # what the tab does after a delete
    assert ids["docs"]["alpha"] not in _docs(widget.last_search)
    assert all("syn_alpha" not in widget.results.item(i).text() for i in range(widget.results.count()))


def test_hits_cite_file_and_page_and_suggestions_never_link(world):
    db, ids, links = world
    library = DocumentLibrary(db)
    hits = library.search("mud weight", document_ids={ids["docs"]["alpha"]})["hits"]
    assert hits and all(h["file_name"] == "syn_alpha_daily.txt" and h["page_no"] >= 1 and h["location"]
                        for h in hits)
    before = links.link_counts()
    suggestions = links.suggest_wells(ids["docs"]["unrelated"]) + links.suggest_wells(ids["docs"]["alpha"])
    assert links.link_counts() == before                                        # proposals only
    assert all(s.page_no >= 1 and s.location for s in suggestions)              # every proposal cites a page
    assert ids["alpha"] in {s.well_id for s in links.suggest_wells(ids["docs"]["alpha"])}
    library.close()


def test_delete_and_reindex_remove_the_document_from_every_scope(world):
    db, ids, links = world
    library = DocumentLibrary(db)
    assert library.delete_document(ids["docs"]["alpha"])
    assert ids["docs"]["alpha"] not in _docs(library.search("SYNTHETIC"))
    assert library.search("SYNTHETIC", document_ids={ids["docs"]["alpha"]})["hits"] == []
    assert links.links_for_well(ids["alpha"]) == []                             # the link left with it
    info = library.rebuild_index()
    assert info["pages"] is None or info["pages"] >= 1
    assert ids["docs"]["alpha"] not in _docs(library.search("SYNTHETIC"))
    library.close()


def test_no_text_layer_is_stated_and_search_is_offline(world, tmp_path, monkeypatch):
    db, _ids, _links = world
    scanned = extract_document(_pdf(tmp_path / "syn_scan.pdf", [""]))
    assert all(not p.text.strip() for p in scanned.pages)
    library = DocumentLibrary(db)

    def no_network(*args, **kwargs):
        raise AssertionError("document search must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    result = library.search("nonexistentsyntheticterm")
    assert result["status"] == "no_matches" and "pages without a text layer" in result["message"]
    library.close()
