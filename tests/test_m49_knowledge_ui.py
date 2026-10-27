"""M49 Knowledge Assistant UI (offscreen Qt; NOT native Windows desktop testing).

Real widgets (Documents tab + assistant panel), a real in-memory SQLite
database with the SYNTHETIC corpus, real worker threads.  The local model,
where used, is the scripted stand-in for the EXTERNAL Ollama server
(tests/m49_fake_ollama.py) on 127.0.0.1.
"""
from __future__ import annotations

import os
import socket
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core import knowledge_retrieval as kr  # noqa: E402
from m49_fake_ollama import FakeOllama  # noqa: E402
from m49_knowledge_fixtures import corpus_db, make_db  # noqa: E402

KICK = "What is the kick tolerance for the 8-1/2 in section?"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def world(app):
    from core.selection_manager import SelectionManager
    SelectionManager().clear()
    db, ids = corpus_db()
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


def _ask(app, panel, question, *, wait=True):
    panel.question_edit.setPlainText(question)
    assert panel.ask()
    if wait:
        assert _wait(app, lambda: panel.worker is None and panel.current_state not in
                     ("searching", "retrieving", "generating")), panel.current_state


def _set_scope(panel, scope, target=None, report=None):
    panel.scope_combo.setCurrentIndex(panel.scope_combo.findData(scope))
    if target is not None:
        panel.target_combo.setCurrentIndex(panel.target_combo.findData(target))
    if report is not None:
        panel.report_combo.setCurrentIndex(panel.report_combo.findData(report))


def _closed_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ----------------------------------------------------------------- basics
def test_assistant_is_a_section_of_the_documents_tab(world):
    tab, panel, _ids, _db = world
    assert [tab.sections.tabText(i) for i in range(tab.sections.count())] == ["Library && Search",
                                                                              "Knowledge Assistant"]
    assert tab.sections.widget(1) is panel
    assert [panel.scope_combo.itemData(i) for i in range(panel.scope_combo.count())] == list(kr.SCOPES)
    assert panel.current_state == "idle" and not panel.cancel_button.isEnabled()
    assert not panel.use_model_check.isEnabled()          # no model checked yet


def test_empty_library_has_its_own_message(app):
    from tabs.documents_tab import DocumentsTab
    db = make_db()
    tab = DocumentsTab(db)
    try:
        _ask(app, tab.assistant, "mud weight")
        assert tab.assistant.current_state == "no_documents"
        assert "No reviewed documents are stored yet" in tab.assistant.answer_view.toPlainText()
    finally:
        tab.cleanup()
        db.engine.dispose()


def test_answer_with_citations_and_source_opens_the_exact_passage(app, world):
    tab, panel, ids, _db = world
    _ask(app, panel, KICK)
    assert panel.current_state == "ready" and "verified" in panel.state_label.text()
    text = panel.answer_view.toPlainText()
    assert "50 bbl" in text and "[S1]" in text and "Quoted from the documents" in text
    assert panel.evidence_table.rowCount() >= 1
    assert panel.evidence_table.item(0, 1).text() == "SYN-KA-01 drilling program.pdf"
    assert panel.evidence_table.item(0, 2).text().startswith("2 ")
    s1 = panel.last_answer.evidence[0]
    panel.answer_view.anchorClicked.emit(QUrl("cite:S1"))
    assert tab.sections.currentIndex() == 0
    assert tab.current_document_id == ids["program"] and tab.page_combo.currentData() == 2
    assert tab.cited_span == (ids["program"], 2, s1.start, s1.end)
    selections = tab.viewer.extraSelections()        # keep the list alive (PySide object lifetime)
    assert len(selections) == 1 and selections[0].cursor.selectedText() == s1.text
    assert tab.viewer.textCursor().selectedText() == s1.text


def test_multi_source_conflict_answer_lists_both_sources(app, world):
    _tab, panel, ids, _db = world
    _ask(app, panel, "What is the planned mud weight for the 12-1/4 in section?")
    docs = {e.document_id for e in panel.last_answer.evidence}
    assert {ids["program"], ids["mud_rev2"]} <= docs
    assert "1.25" in panel.answer_view.toPlainText() and "1.32" in panel.answer_view.toPlainText()
    assert "different values for mud weight" in panel.notes_label.text()


def test_insufficient_evidence_is_explicit(app, world):
    _tab, panel, _ids, _db = world
    _ask(app, panel, "What is the mud motor bend angle for SYN-ZZ-99?")
    assert panel.current_state == "no_evidence"
    text = panel.answer_view.toPlainText()
    assert "Insufficient evidence" in text
    absent = next(line for line in text.splitlines() if "No passage in this scope contains:" in line)
    assert "motor" in absent and "mud" not in absent.split(":", 1)[1].replace(" ", "").split(",")
    assert any("Occur in this scope" in line and "mud" in line for line in text.splitlines())
    assert panel.evidence_table.rowCount() == 0 and not panel.open_source_button.isEnabled()


# ---------------------------------------------------- no stale answers
def test_changing_the_question_or_scope_clears_the_answer(app, world):
    _tab, panel, ids, _db = world
    _ask(app, panel, KICK)
    assert panel.last_answer is not None
    panel.question_edit.setPlainText(KICK + " (edited)")
    assert panel.last_answer is None and panel.evidence_table.rowCount() == 0
    assert panel.answer_view.toPlainText() == "" and panel.current_state == "stale"
    _ask(app, panel, KICK)
    _set_scope(panel, kr.SCOPE_WELL, ids["well_c"])
    assert panel.last_answer is None and panel.current_state == "stale"
    # A scope change ALONE (the target list is refilled with signals blocked,
    # so no target change fires) must clear the answer too.
    _set_scope(panel, kr.SCOPE_ALL)
    _ask(app, panel, KICK)
    assert panel.last_answer is not None
    panel.scope_combo.setCurrentIndex(panel.scope_combo.findData(kr.SCOPE_DOCUMENT))
    assert panel.last_answer is None and panel.current_state == "stale"
    assert panel.answer_view.toPlainText() == "" and panel.evidence_table.rowCount() == 0


def test_scope_selection_limits_evidence_and_changing_well_resets(app, world):
    _tab, panel, ids, _db = world
    _set_scope(panel, kr.SCOPE_WELL, ids["well_c"])
    _ask(app, panel, "pump liner size")
    assert {e.document_id for e in panel.last_answer.evidence} == {ids["note_c"]}
    assert "5-1/2" in panel.answer_view.toPlainText()
    panel.target_combo.setCurrentIndex(panel.target_combo.findData(ids["well_a"]))
    assert panel.last_answer is None
    _ask(app, panel, "pump liner size")
    assert ids["note_c"] not in {e.document_id for e in panel.last_answer.evidence}
    assert "6 in" in panel.answer_view.toPlainText()
    _set_scope(panel, kr.SCOPE_REPORT, ids["well_a"], ids["report_a2"])
    assert panel.current_scope() == (kr.SCOPE_REPORT, ids["report_a2"])
    _ask(app, panel, "mud weight for the 12-1/4 in section")
    assert {e.document_id for e in panel.last_answer.evidence} == {ids["mud_rev2"]}


def test_app_selection_change_resets_a_well_scope(app, world):
    from core.selection_manager import SelectionManager
    _tab, panel, ids, _db = world
    _set_scope(panel, kr.SCOPE_WELL, ids["well_a"])
    _ask(app, panel, "pump liner size")
    assert panel.last_answer is not None
    SelectionManager().select_well(ids["well_c"], {"name": "SYN-KC-03"})
    app.processEvents()
    assert panel.last_answer is None and panel.current_scope() == (kr.SCOPE_WELL, ids["well_c"])


def test_library_change_clears_an_answer_from_a_deleted_document(app, world):
    from document_link_fixtures import without_session_user
    tab, panel, ids, _db = world
    _ask(app, panel, KICK)
    assert panel.last_answer is not None
    with without_session_user():
        assert tab.library.delete_document(ids["program"])
    tab.refresh()
    assert panel.last_answer is None and panel.current_state == "stale"
    _ask(app, panel, KICK)
    assert all(e.document_id != ids["program"] for e in panel.last_answer.evidence)


def test_read_error_is_an_error_state_not_no_evidence(app, world, monkeypatch):
    _tab, panel, _ids, _db = world

    def broken(_db):
        raise RuntimeError("synthetic read failure")
    monkeypatch.setattr(kr, "corpus_signature", broken)
    panel.question_edit.setPlainText(KICK)
    assert panel.ask() is False
    assert panel.current_state == "error" and "could not be read" in panel.state_label.text()
    assert "Insufficient" not in panel.answer_view.toPlainText()


# ------------------------------------------------------------ local model
def test_model_missing_state_with_setup_guidance(app, world):
    _tab, panel, _ids, _db = world
    with FakeOllama(models=[{"name": "other:latest"}, {"name": "big:cloud"}]) as fake:
        panel.model_url_edit.setText(fake.url)
        panel.chat_model_combo.setEditText("syn-chat")
        panel.check_model()
        assert _wait(app, lambda: panel.model_status is not None)
    text = panel.model_label.text()
    assert "not installed" in text and "ollama pull" in text and "OLLAMA_NO_CLOUD" in text
    assert "big:cloud" in text and not panel.use_model_check.isEnabled()
    assert "Semantic retrieval unavailable" in panel.semantic_label.text()


@pytest.mark.parametrize("url, expected", [("http://203.0.113.9:11434", "Only a model on this computer"),
                                           (None, "No local model server")])
def test_remote_url_and_stopped_server_are_reported(app, world, url, expected):
    _tab, panel, _ids, _db = world
    panel.model_url_edit.setText(url or f"http://127.0.0.1:{_closed_port()}")
    panel.chat_model_combo.setEditText("syn-chat")
    panel.model_status = None
    panel.check_model()
    assert _wait(app, lambda: panel.model_status is not None)
    assert expected in panel.model_label.text() and not panel.use_model_check.isEnabled()


def _model_ready(app, panel, fake):
    panel.model_url_edit.setText(fake.url)
    panel.chat_model_combo.setEditText("syn-chat")
    panel.model_status = None
    panel.check_model()
    assert _wait(app, lambda: panel.model_status is not None) and panel.use_model_check.isEnabled()
    panel.use_model_check.setChecked(True)


def test_generated_answer_is_verified_and_marked(app, world):
    _tab, panel, _ids, _db = world
    with FakeOllama() as fake:
        _model_ready(app, panel, fake)
        _ask(app, panel, KICK)
    assert panel.last_answer.mode == "generated" and panel.last_answer.verified
    assert "Written by the local model" in panel.answer_view.toPlainText()


def test_fabricated_citation_is_shown_as_not_verified(app, world):
    _tab, panel, _ids, _db = world
    chunks = [{"message": {"content": "Kick tolerance is 50 bbl [S9]."}, "done": False}, {"done": True, "message": {}}]
    with FakeOllama(chat_chunks=chunks) as fake:
        _model_ready(app, panel, fake)
        _ask(app, panel, KICK)
    text = panel.answer_view.toPlainText()
    assert "NOT VERIFIED" in text and "[S9]" in text and "Quoted from the documents instead" in text
    assert "NOT verified" in panel.state_label.text()


def test_model_error_keeps_evidence_and_says_so(app, world):
    _tab, panel, _ids, _db = world
    with FakeOllama(chat_status=500, chat_error="synthetic crash") as fake:
        _model_ready(app, panel, fake)
        _ask(app, panel, KICK)
    assert panel.current_state == "model_unavailable" and panel.retry_button.isEnabled()
    assert "Local model unavailable" in panel.answer_view.toPlainText() and "50 bbl" in panel.answer_view.toPlainText()
    assert panel.evidence_table.rowCount() >= 1


def test_generation_never_blocks_the_ui_and_cancel_works(app, world):
    _tab, panel, _ids, _db = world
    with FakeOllama(hold_after_first=20.0) as fake:
        _model_ready(app, panel, fake)
        panel.question_edit.setPlainText(KICK)
        started = time.monotonic()
        assert panel.ask()
        assert time.monotonic() - started < 1.0            # ask() returns at once; work is in a thread
        assert _wait(app, lambda: panel.current_state == "generating", 10)
        assert panel.cancel_button.isEnabled() and not panel.ask_button.isEnabled()
        panel.cancel()
        assert panel.current_state == "cancelled" and panel.last_answer is None
        assert panel.ask_button.isEnabled() and panel.retry_button.isEnabled()
        fake.release.set()
        assert _wait(app, lambda: not panel._old_workers, 10)
    assert panel.last_answer is None                         # the late result was dropped


def test_scope_change_during_generation_drops_the_late_result(app, world):
    _tab, panel, ids, _db = world
    with FakeOllama(hold_after_first=20.0) as fake:
        _model_ready(app, panel, fake)
        _ask(app, panel, KICK, wait=False)
        assert _wait(app, lambda: panel.current_state == "generating", 10)
        _set_scope(panel, kr.SCOPE_DOCUMENT, ids["lessons"])
        assert panel.current_state == "stale"
        fake.release.set()
        assert _wait(app, lambda: not panel._old_workers, 10)
    assert panel.last_answer is None and panel.answer_view.toPlainText() == ""


# ---------------------------------------------------------- presentation
def test_injection_source_is_flagged_and_not_answered(app, world):
    _tab, panel, ids, _db = world
    _ask(app, panel, "What is the cement slurry density for the 9-5/8 in casing?")
    text = panel.answer_view.toPlainText()
    assert "1.90" in text and "APPROVED" not in text and "rm -rf" not in text
    rows = [r for r in range(panel.evidence_table.rowCount())
            if panel.last_answer.evidence[r].document_id == ids["inject"]]
    assert rows and panel.evidence_table.item(rows[0], 0).text().endswith("⚠")
    assert "instruction-like text" in panel.notes_label.text()


def test_persian_answer_is_right_to_left_and_long_passages_are_elided(app, world):
    from tabs.knowledge_assistant import render_answer_html
    _tab, panel, _ids, _db = world
    _ask(app, panel, "توصيه براي هرزروي چيست؟")
    assert panel.current_state == "ready" and "مسدودکننده" in panel.answer_view.toPlainText()
    assert 'dir="rtl"' in render_answer_html("• «در عمق ۱۸۵۰ متر» [S1]")
    assert 'dir="rtl"' not in render_answer_html("• «Kick tolerance is 50 bbl» [S1]")
    assert "&lt;b&gt;" in render_answer_html("<b>not html</b>")
    for row in range(panel.evidence_table.rowCount()):
        assert len(panel.evidence_table.item(row, 6).text()) <= 161
    assert panel.minimumSizeHint().width() < 1300


def test_disabled_ask_button_is_visibly_grey_while_busy(app, world):
    tab, panel, _ids, _db = world
    tab.show()
    tab.sections.setCurrentIndex(1)
    panel._set_state("generating")
    app.processEvents()
    image = panel.ask_button.grab().toImage()
    colour = image.pixelColor(4, image.height() // 2)
    assert not panel.ask_button.isEnabled()
    assert abs(colour.red() - 0xb0) < 20 and abs(colour.green() - 0xbe) < 20 and abs(colour.blue() - 0xc5) < 20
    panel._set_state("idle")
    app.processEvents()
    image = panel.ask_button.grab().toImage()
    enabled = image.pixelColor(4, image.height() // 2)
    assert enabled.blue() > 150 and enabled.red() < 60
    tab.hide()


def test_clear_resets_everything(app, world):
    _tab, panel, _ids, _db = world
    _ask(app, panel, KICK)
    panel.clear()
    assert panel.question_edit.toPlainText() == "" and panel.last_answer is None
    assert panel.evidence_table.rowCount() == 0 and panel.current_state == "idle"
