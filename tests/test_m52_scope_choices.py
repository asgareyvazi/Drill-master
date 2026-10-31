"""M52 §2.2: the Knowledge Assistant scope pickers are read off the GUI thread.

Real Documents tab + assistant panel on a temporary FILE SQLite database with the
SYNTHETIC M50 corpus, so the panel takes its production path: the well, report and
document lists are read by ``ScopeChoicesWorker`` through
``core.export_jobs.worker_database`` (own read-only connection, plain dicts back).
A statement probe on the GUI engine records every SQL statement executed on the GUI
thread.  Read failures are injected by replacing the list reader (the database
itself is real).  Offscreen Qt on Linux, not Windows desktop testing.
"""
from __future__ import annotations

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

MAIN = threading.get_ident()
QUESTION = "mud weight for the 16 in section of SYN-KE-05"


class KeywordOnly:
    embed_model = ""
    chat_model = ""


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _environment(monkeypatch, tmp_path, name):
    data = tmp_path / "data"
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(data),
                       "DRILLMASTER_DB_PATH": str(data / name),
                       "DRILLMASTER_BACKUP_DIR": str(data / "backups"), "DRILLMASTER_AI_IMPORT": "0"}.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def world(app, tmp_path, monkeypatch):
    _environment(monkeypatch, tmp_path, "synthetic-m52-scope.db")
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


def _scope(panel, scope):
    panel.scope_combo.setCurrentIndex(panel.scope_combo.findData(scope))


def _items(combo):
    return [(combo.itemText(i), combo.itemData(i)) for i in range(combo.count())]


def _external_sql(db, statement, **params):
    con = sqlite3.connect(db.db_path)
    try:
        con.execute(statement, params)
        con.commit()
    finally:
        con.close()


def _recording_reader(monkeypatch, gate=None, fail=None):
    """Wrap the list reader: records (thread, kind, engine) and can hold or fail a kind."""
    import tabs.knowledge_assistant as ka_tab
    real = ka_tab._read_scope_rows
    calls = []

    def reader(manager, kind, *args, **kwargs):
        calls.append((threading.get_ident(), kind, manager.engine))
        if gate is not None and kind in gate:
            assert gate[kind].wait(20)
        if fail is not None and kind in fail:
            raise sqlite3.OperationalError("synthetic list read failure")
        return real(manager, kind, *args, **kwargs)
    monkeypatch.setattr(ka_tab, "_read_scope_rows", reader)
    return calls


# ---- no SQL on the GUI thread, same list as before ---------------------------------------
def test_well_list_is_read_on_a_worker_with_its_own_connection_and_matches_the_service(app, world, monkeypatch):
    _tab, panel, _ids, db, probe = world
    calls = _recording_reader(monkeypatch)
    probe.clear()
    _scope(panel, kr.SCOPE_WELL)
    assert panel.choices_state["targets"] == "loading"           # visible loading state, picker disabled
    assert not panel.target_combo.isEnabled() and "Loading wells" in panel.target_combo.placeholderText()
    assert _wait(app, panel.scope_choices_ready)
    gui_sql = list(probe)                       # before the test's own expected-value read below
    assert gui_sql == [], gui_sql[:5]
    assert calls and all(ident != MAIN and engine is not db.engine for ident, engine in
                         [(c[0], c[2]) for c in calls]), calls
    from core.document_links import DocumentLinkService
    expected = [(f"{w['name']}" + (f" ({w['code']})" if w.get("code") else ""), w["id"])
                for w in DocumentLinkService(db).well_choices()]
    assert _items(panel.target_combo) == expected and expected  # same rows, labels and order as before
    assert panel.choices_state["targets"] == "ready" and panel.target_combo.isEnabled()
    assert not panel.choices_retry_button.isVisible()


def test_document_and_report_lists_are_read_on_the_worker_too(app, world, monkeypatch):
    _tab, panel, ids, db, probe = world
    calls = _recording_reader(monkeypatch)
    probe.clear()
    _scope(panel, kr.SCOPE_DOCUMENT)
    assert _wait(app, panel.scope_choices_ready)
    documents = {panel.target_combo.itemData(i) for i in range(panel.target_combo.count())}
    assert ids["ke_program"] in documents
    _scope(panel, kr.SCOPE_REPORT)
    assert _wait(app, panel.scope_choices_ready)
    panel.target_combo.setCurrentIndex(panel.target_combo.findData(ids["well_e"]))
    assert _wait(app, panel.scope_choices_ready)
    gui_sql = list(probe)                       # before the test's own expected-value read below
    from core.document_links import DocumentLinkService
    expected = [r["id"] for r in DocumentLinkService(db).report_choices(ids["well_e"])]
    assert [panel.report_combo.itemData(i) for i in range(panel.report_combo.count())] == expected and expected
    assert gui_sql == [], gui_sql[:5]
    assert {kind for _ident, kind, _engine in calls} == {"documents", "wells", "reports"}
    assert all(ident != MAIN for ident, _kind, _engine in calls)


# ---- an unreadable list is an error, not "no wells" ---------------------------------------
def test_read_error_is_distinct_from_an_empty_list_and_retry_recovers(app, world, monkeypatch):
    _tab, panel, _ids, _db, _probe = world
    fail = {"wells"}
    _recording_reader(monkeypatch, fail=fail)
    _scope(panel, kr.SCOPE_WELL)
    assert _wait(app, panel.scope_choices_ready)
    assert panel.choices_state["targets"] == "error" and panel.choices_error["targets"] == "OperationalError"
    assert panel.target_combo.count() == 0 and not panel.target_combo.isEnabled()
    assert "could not be read" in panel.target_combo.placeholderText()
    assert "No wells" not in panel.target_combo.placeholderText()
    assert panel.choices_retry_button.isVisibleTo(panel)
    panel.question_edit.setPlainText(QUESTION)
    assert panel.ask() is False                                   # never "nothing in this scope"
    assert panel.current_state == "scope_unavailable" and panel.worker is None
    assert "could not be read" in panel.state_label.text()
    fail.clear()
    panel.choices_retry_button.click()
    assert _wait(app, panel.scope_choices_ready)
    assert panel.choices_state["targets"] == "ready" and panel.target_combo.count() > 0
    assert not panel.choices_retry_button.isVisibleTo(panel)


def test_a_database_without_wells_shows_the_empty_state_not_an_error(app, tmp_path, monkeypatch):
    _environment(monkeypatch, tmp_path, "synthetic-m52-empty.db")
    from core.database import DatabaseManager
    from core.selection_manager import SelectionManager
    SelectionManager().clear()
    db = DatabaseManager()
    assert db.initialize(), db.last_diagnostic
    _external_sql(db, "DELETE FROM wells")                         # initialize() seeds a default well
    from tabs.documents_tab import DocumentsTab
    tab = DocumentsTab(db)
    tab.show_dialogs = False
    panel = tab.assistant
    try:
        _scope(panel, kr.SCOPE_WELL)
        assert _wait(app, panel.scope_choices_ready)
        assert panel.choices_state["targets"] == "empty" and panel.choices_error["targets"] is None
        assert panel.target_combo.placeholderText() == "No wells"
        assert not panel.choices_retry_button.isVisibleTo(panel)
    finally:
        tab.cleanup()
        SelectionManager().clear()
        db.close()


def test_report_list_error_blocks_a_report_question(app, world, monkeypatch):
    _tab, panel, ids, _db, _probe = world
    _recording_reader(monkeypatch, fail={"reports"})
    _scope(panel, kr.SCOPE_REPORT)
    assert _wait(app, panel.scope_choices_ready)
    assert panel.choices_state == {"targets": "ready", "reports": "error"}
    panel.question_edit.setPlainText(QUESTION)
    assert panel.ask() is False and panel.current_state == "scope_unavailable"


# ---- late results and loading ------------------------------------------------------------
def test_a_late_well_list_never_overwrites_a_newer_scope(app, world, monkeypatch):
    _tab, panel, ids, _db, _probe = world
    gate = {"wells": threading.Event()}
    _recording_reader(monkeypatch, gate=gate)
    _scope(panel, kr.SCOPE_WELL)                                   # held on the worker
    assert panel.choices_state["targets"] == "loading"
    panel.question_edit.setPlainText(QUESTION)
    assert panel.ask() is False and panel.current_state == "scope_loading"
    _scope(panel, kr.SCOPE_DOCUMENT)                               # newer request owns the picker
    assert _wait(app, lambda: panel.choices_state["targets"] == "ready")
    documents = _items(panel.target_combo)
    gate["wells"].set()                                            # the old well list arrives now
    assert _wait(app, lambda: all(not w.isRunning() for w in panel._old_workers))
    for _ in range(20):
        app.processEvents()
        time.sleep(0.005)
    assert _items(panel.target_combo) == documents                # still the documents
    assert panel.current_scope()[0] == kr.SCOPE_DOCUMENT
    assert panel.current_scope()[1] in {data for _text, data in documents}


def test_a_library_refresh_keeps_the_chosen_well(app, world, monkeypatch):
    _tab, panel, ids, db, probe = world
    _scope(panel, kr.SCOPE_WELL)
    assert _wait(app, panel.scope_choices_ready)
    panel.target_combo.setCurrentIndex(panel.target_combo.findData(ids["well_f"]))
    _external_sql(db, "UPDATE wells SET name = name WHERE id = :w", w=ids["well_e"])
    probe.clear()
    panel.library_changed()
    assert _wait(app, panel.scope_choices_ready)
    assert panel.current_scope() == (kr.SCOPE_WELL, ids["well_f"])  # not moved to another well silently
    assert not [s for s in probe if "wells" in s.lower()], probe[:5]


def test_an_app_selection_change_still_follows_the_selected_well(app, world, monkeypatch):
    _tab, panel, ids, _db, _probe = world
    _scope(panel, kr.SCOPE_WELL)
    assert _wait(app, panel.scope_choices_ready)
    panel.target_combo.setCurrentIndex(panel.target_combo.findData(ids["well_f"]))
    monkeypatch.setattr(panel, "_current_selection", lambda: (ids["well_e"], None))
    panel._selection_changed()
    assert _wait(app, panel.scope_choices_ready)
    assert panel.current_scope() == (kr.SCOPE_WELL, ids["well_e"])
