"""M45 PySide6 tests: document link workflow, related documents, status bar.

Environment label: these run under QT_QPA_PLATFORM=offscreen (in the sandbox
also with stub GL/dbus/xkb shared libraries).  They drive real widgets - the
Documents tab, the link dialog, the Well Info / Daily Report pages and, in
the last group, a real ``MainWindow`` on a temporary SYNTHETIC database -
but they are NOT native Windows desktop testing (no real window manager,
mouse or screen).  Modal dialogs are driven through their test API
(``show_dialogs = False`` / ``pending_link_dialog``) instead of ``exec()``.
"""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QMessageBox  # noqa: E402

from core.document_links import DocumentLinkService  # noqa: E402
from core.permissions import permissions, session_user  # noqa: E402
from document_link_fixtures import (  # noqa: E402
    ARABIC_KAF, ARABIC_YEH, build_link_world, import_documents, without_session_user, write_documents,
)
from synthetic_operations import make_file_database  # noqa: E402
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
        yield db, ids
        db.engine.dispose()


@pytest.fixture
def tab(world):
    """Documents tab for a signed-in engineer (``can_import``).  The in-memory
    database has no user rows, so the principal carries a role but no id."""
    from tabs.documents_tab import DocumentsTab
    db, ids = world
    previous = permissions.user
    permissions.set_user({"username": "syn-engineer", "role": "engineer"})
    widget = DocumentsTab(db)
    widget.show_dialogs = False
    try:
        yield widget, db, ids
    finally:
        widget.cleanup()
        widget.deleteLater()
        permissions.set_user(previous)


def _row_of(table, document_id):
    from PySide6.QtCore import Qt
    for row in range(table.rowCount()):
        if table.item(row, 0).data(Qt.UserRole) == document_id:
            return row
    return None


def _select(widget, document_id):
    row = _row_of(widget.table, document_id)
    assert row is not None
    widget.table.selectRow(row)
    assert widget.current_document_id == document_id


# ------------------------------------------------------ link workflow (tab)
def test_link_dialog_suggests_but_links_only_after_confirmation(tab):
    widget, db, ids = tab
    _select(widget, ids["docs"]["alpha"])
    assert "Not linked" in widget.link_status.text() and widget.link_button.isEnabled()
    changes = []
    widget.links_changed.connect(lambda: changes.append(1))
    dialog = widget.link_selected()
    assert dialog is widget.pending_link_dialog
    suggestion = dialog.suggestion_list.item(0)
    assert "SYN-ALPHA-01" in suggestion.text() and "page 1" not in suggestion.text().split("—")[0]
    assert dialog.selected_well_id() is None                       # nothing pre-selected
    assert not dialog.buttons.button(QDialogButtonBox.Ok).isEnabled()
    dialog._suggestion_clicked(suggestion)                         # a click only selects the well
    assert dialog.selected_well_id() == ids["alpha"]
    assert DocumentLinkService(db).links_for_document(ids["docs"]["alpha"]) == []
    assert dialog.select_report(ids["report_1"]) and dialog.selected_report_id() == ids["report_1"]
    dialog.set_anchor_page(2)
    assert "report #1" in dialog.summary.text()
    link_id = widget.apply_link_dialog(dialog, True)
    (link,) = DocumentLinkService(db).links_for_document(ids["docs"]["alpha"])
    assert (link["id"], link["well_id"], link["report_id"], link["page_no"]) == (link_id, ids["alpha"],
                                                                                ids["report_1"], 2)
    assert widget.links_table.rowCount() == 1 and "Report #1" in widget.links_table.item(0, 1).text()
    assert "Linked" in widget.link_status.text() and changes == [1]
    assert widget.table.item(_row_of(widget.table, ids["docs"]["alpha"]), 6).text() == "1 link(s)"


def test_link_message_does_not_follow_another_document(tab):
    widget, db, ids = tab
    _select(widget, ids["docs"]["alpha"])
    dialog = widget.link_selected()
    dialog.select_well(ids["alpha"])
    widget.apply_link_dialog(dialog, True)
    assert widget.link_info.text() == "Document linked."                       # same document: kept
    assert widget.open_document(ids["docs"]["twin"]) is True
    assert widget.link_info.text() == "" and "Not linked" in widget.link_status.text()
    assert widget.open_document(ids["docs"]["alpha"]) is True
    assert widget.link_info.text() == "" and "Linked" in widget.link_status.text()


def test_cancelled_dialog_changes_nothing(tab):
    widget, db, ids = tab
    _select(widget, ids["docs"]["twin"])
    dialog = widget.link_selected()
    dialog.select_well(ids["twin_1"])
    assert widget.apply_link_dialog(dialog, False) is None
    assert "cancelled" in widget.link_info.text()
    assert DocumentLinkService(db).links_for_document(ids["docs"]["twin"]) == []


def test_same_name_wells_are_distinguishable_in_the_dialog(tab):
    widget, _db, ids = tab
    _select(widget, ids["docs"]["twin"])
    dialog = widget.link_selected()
    rows = {}
    for row in range(dialog.well_table.rowCount()):
        rows[int(dialog.well_table.item(row, 8).text())] = [dialog.well_table.item(row, c).text() for c in range(9)]
    for well in ("twin_1", "twin_2"):
        assert "same name as another well" in rows[ids[well]][0]
    assert rows[ids["twin_1"]][1:4] != rows[ids["twin_2"]][1:4]            # code / field / project differ
    assert "same name" not in rows[ids["alpha"]][0]
    assert {dialog.suggestion_list.item(i).data(0x0100) for i in range(dialog.suggestion_list.count())} == {
        ids["twin_1"], ids["twin_2"]}                                       # both offered, none chosen
    dialog.filter_edit.setText("SYN-T2")
    assert dialog.well_table.rowCount() == 1


def test_duplicate_change_and_remove_through_the_tab(tab):
    widget, db, ids = tab
    service = DocumentLinkService(db)
    _select(widget, ids["docs"]["alpha"])
    dialog = widget.link_selected()
    dialog.select_well(ids["alpha"])
    widget.apply_link_dialog(dialog, True)
    again = widget.link_selected()
    again.select_well(ids["alpha"])
    assert widget.apply_link_dialog(again, True) is None
    assert widget.last_link_error == "duplicate" and "already linked" in widget.link_info.text()
    widget.links_table.selectRow(0)
    change = widget.change_selected_link()
    assert change.current and change.selected_well_id() == ids["alpha"] and change.selected_report_id() is None
    change.select_report(ids["report_2"])
    widget.apply_link_dialog(change, True)
    (link,) = service.links_for_document(ids["docs"]["alpha"])
    assert link["report_id"] == ids["report_2"]
    widget.links_table.selectRow(0)
    assert widget.remove_selected_link() is True
    assert service.links_for_document(ids["docs"]["alpha"]) == [] and widget.links_table.rowCount() == 0
    assert widget.current_document_id == ids["docs"]["alpha"]               # the document stays


def test_unlinked_filter_and_open_document_clears_a_hiding_filter(tab):
    widget, db, ids = tab
    DocumentLinkService(db).create_link(ids["docs"]["alpha"], ids["alpha"])
    widget.refresh()
    widget.filter_combo.setCurrentIndex(1)                                   # unlinked only
    shown = {widget.table.item(r, 0).text() for r in range(widget.table.rowCount())}
    assert shown == {"syn_twin_note.txt", "syn_fa_arabic.txt", "syn_unrelated.txt"}
    assert "3 of 4 document(s) shown" in widget.library_info.text()
    widget.filter_combo.setCurrentIndex(2)                                   # linked only
    assert widget.table.rowCount() == 1
    widget.filter_combo.setCurrentIndex(1)
    assert widget.open_document(ids["docs"]["alpha"], 2) is True             # hidden by the filter
    assert widget.filter_combo.currentData() == "all"
    assert widget.page_combo.currentData() == 2 and widget.viewer_title.text().startswith("<b>syn_alpha_daily.txt")
    assert widget.open_document(999_999) is False


def test_search_result_opens_the_original_text_at_the_match(tab):
    widget, _db, ids = tab
    widget.search_edit.setText("مصنوعی کیسینگ")                              # Persian forms typed
    widget.run_search()
    (row,) = [r for r in range(widget.results.count())
              if widget.results.item(r).data(0x0100)["file_name"] == "syn_fa_arabic.txt"]
    assert "line 1" in widget.results.item(row).text()
    widget.results.setCurrentRow(row)
    text = widget.viewer.toPlainText()
    assert f"مصنوع{ARABIC_YEH}" in text and f"{ARABIC_KAF}{ARABIC_YEH}س{ARABIC_YEH}نگ" in text  # stored original
    highlighted = [s.cursor.selectedText() for s in widget.viewer.extraSelections()]
    assert highlighted == [f"مصنوع{ARABIC_YEH}", f"{ARABIC_KAF}{ARABIC_YEH}س{ARABIC_YEH}نگ"]
    assert "first match on line 1" in widget.viewer_title.text()
    widget.search_edit.setText("mud weight")
    widget.run_search()
    widget.results.setCurrentRow(0)
    assert widget.current_document_id == ids["docs"]["alpha"] and widget.page_combo.currentData() == 2
    assert widget.viewer.textCursor().selectedText() == "mud"
    dialog = widget.link_selected()                                          # result page is the default anchor
    assert dialog.page_combo.currentData() == 2


def test_rebuild_index_reports_pages_and_version(tab):
    widget, _db, _ids = tab
    info = widget.rebuild_index()
    assert info["pages"] == 5 and "normalisation v1" in widget.search_info.text()


def test_link_buttons_follow_the_role(tmp_path, app):
    from tabs.documents_tab import DocumentsTab
    db = make_file_database(tmp_path / "roles.db")
    previous = permissions.user
    try:
        permissions.set_user(session_user(db.authenticate_user("engineer", "Synthetic-Eng-1!")))
        db.enforce_authorization(permissions)
        import_documents(db, {"twin": write_documents(tmp_path / "d")["twin"]})
        permissions.set_user(session_user(db.authenticate_user("viewer", "Synthetic-View-1!")))
        widget = DocumentsTab(db)
        widget.table.selectRow(0)
        assert not widget.link_button.isEnabled()
        assert widget.link_button.toolTip() == "Your role cannot change document links"
        widget.cleanup()
    finally:
        permissions.set_user(previous)
        db.engine.dispose()


def test_related_documents_panel_lists_and_opens(world):
    from tabs.related_documents import RelatedDocumentsPanel
    db, ids = world
    service = DocumentLinkService(db)
    service.create_link(ids["docs"]["alpha"], ids["alpha"], page_no=2)
    service.create_link(ids["docs"]["arabic"], ids["alpha"], report_id=ids["report_1"])
    well_panel, report_panel = RelatedDocumentsPanel(db, "well"), RelatedDocumentsPanel(db, "report")
    assert "Select a well" in well_panel.status_label.text()
    well_panel.set_well(ids["alpha"])
    assert well_panel.table.rowCount() == 2 and "2 document(s) linked to this well" in well_panel.status_label.text()
    report_panel.set_report(ids["report_1"])
    assert [report_panel.table.item(0, c).text() for c in range(3)] == ["syn_fa_arabic.txt", "Report #1 · 2026-01-02",
                                                                        "—"]
    report_panel.set_report(ids["report_2"])
    assert report_panel.table.rowCount() == 0 and "No documents" in report_panel.status_label.text()
    opened = []
    well_panel.open_requested.connect(lambda doc, page: opened.append((doc, page)))
    row = next(r for r in range(2) if well_panel.table.item(r, 0).text() == "syn_alpha_daily.txt")
    well_panel.open_row(row)
    assert opened == [(ids["docs"]["alpha"], 2)]
    well_panel.set_well(None)
    assert well_panel.table.rowCount() == 0 and not well_panel.open_button.isEnabled()


# ------------------------------------------------------- real MainWindow
def _pump(seconds=0.2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)


@pytest.fixture(scope="module")
def window(app, tmp_path_factory):
    """One real MainWindow on a SYNTHETIC file database (admin session)."""
    work = tmp_path_factory.mktemp("m45_window")
    mp = pytest.MonkeyPatch()
    for key, value in {"DRILLMASTER_ENV": "test", "DRILLMASTER_DATA_DIR": str(work),
                       "DRILLMASTER_LOG_DIR": str(work / "logs"), "DRILLMASTER_BACKUP_DIR": str(work / "backups"),
                       "DRILLMASTER_AI_IMPORT": "0"}.items():
        mp.setenv(key, value)
    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(work / "settings"))
    db = make_file_database(work / "window.db")
    ids = build_link_world(db)
    previous = permissions.user
    user = session_user(db.authenticate_user("admin", "Synthetic-Admin-1!"))
    permissions.set_user(user)
    db.enforce_authorization(permissions)
    ids["docs"] = import_documents(db, write_documents(work / "docs"))
    service = DocumentLinkService(db)
    service.create_link(ids["docs"]["alpha"], ids["alpha"], page_no=2)
    service.create_link(ids["docs"]["arabic"], ids["alpha"], report_id=ids["report_1"])
    from main_window import MainWindow
    win = MainWindow(db_manager=db, user=user, startup_result=None)
    win.show()
    _pump(0.5)
    yield win, db, ids
    end = time.monotonic() + 10
    while win._hierarchy_worker is not None and time.monotonic() < end:
        _pump(0.05)
    win._close_confirmed = True                     # skip the modal exit prompt
    win.close()
    _pump(0.2)
    permissions.set_user(previous)
    db.engine.dispose()
    mp.undo()


def _well(ids, key, name):
    return ids[key], {"id": ids[key], "name": name}


def test_status_bar_label_follows_the_selected_well(window):
    win, _db, ids = window
    label = win.current_well_label
    win.sel_manager.clear()
    assert label.text() == "🛢️ No well selected"
    win.sel_manager.select_well(*_well(ids, "alpha", "SYN-ALPHA-01"))
    assert label.text() == "🛢️ Well: SYN-ALPHA-01" and win.sel_manager.current_well_id == ids["alpha"]
    for page in (win.documents_tab, win.well_info_tab, win.home_tab):        # switching pages keeps it
        win.tab_widget.setCurrentWidget(page)
        _pump(0.05)
        assert label.text() == "🛢️ Well: SYN-ALPHA-01"
    win.sel_manager.select_well(*_well(ids, "twin_2", "SYN-TWIN"))
    assert label.text() == "🛢️ Well: SYN-TWIN" and win.sel_manager.current_well_id == ids["twin_2"]
    win.sel_manager.clear()                                                  # no selection -> no stale name
    assert label.text() == "🛢️ No well selected" and win.sel_manager.current_well_id is None
    win.sel_manager.select_well(*_well(ids, "persian", "چاه نمونه ۷"))       # a new selection after clearing
    assert label.text() == "🛢️ Well: چاه نمونه ۷"
    win.sel_manager.select_well(None, None)
    assert label.text() == "🛢️ No well selected"
    win.sel_manager.select_well(ids["twin_1"], {})                           # no name in the payload
    assert label.text() == f"🛢️ Well: id {ids['twin_1']}"


def test_deleting_the_current_report_does_not_leave_a_stale_well(window, monkeypatch):
    win, db, ids = window
    report_id = ids["twin_report"]
    win.sel_manager.select_well(*_well(ids, "twin_1", "SYN-TWIN"))
    win.sel_manager.select_report(report_id, {"id": report_id, "well_id": ids["twin_1"]})
    assert win.sel_manager.current_report_id == report_id
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    win.delete_daily_report(report_id)
    _pump(0.3)
    assert db.get_daily_report_by_id(report_id) is None
    assert win.sel_manager.current_well_id is None
    assert win.current_well_label.text() == "🛢️ No well selected"


def test_well_page_lists_linked_documents_and_opens_them(window):
    win, _db, ids = window
    assert win.well_info_tab.load_well_by_id(ids["alpha"])
    panel = win.well_info_tab.related_documents
    assert {panel.table.item(r, 0).text() for r in range(panel.table.rowCount())} == {
        "syn_alpha_daily.txt", "syn_fa_arabic.txt"}
    row = next(r for r in range(panel.table.rowCount()) if panel.table.item(r, 0).text() == "syn_alpha_daily.txt")
    panel.table.selectRow(row)
    panel.open_button.click()
    assert win.tab_widget.currentWidget() is win.documents_tab
    assert win.documents_tab.current_document_id == ids["docs"]["alpha"]
    assert win.documents_tab.page_combo.currentData() == 2                   # the link's anchor page
    assert "SYN-ALPHA-01 mud weight" in win.documents_tab.viewer.toPlainText()


def test_report_page_lists_its_documents_and_follows_link_changes(window):
    win, db, ids = window
    assert win.daily_report_tab.load_report_by_id(ids["report_1"]) is not False
    panel = win.daily_report_tab.related_documents
    assert [panel.table.item(r, 0).text() for r in range(panel.table.rowCount())] == ["syn_fa_arabic.txt"]
    panel.open_row(0)
    assert win.tab_widget.currentWidget() is win.documents_tab
    assert win.documents_tab.current_document_id == ids["docs"]["arabic"]
    # A link made in the Documents tab appears on the report page at once.
    docs_tab = win.documents_tab
    docs_tab.show_dialogs = False
    try:
        assert docs_tab.open_document(ids["docs"]["unrelated"])
        dialog = docs_tab.link_selected()
        dialog.select_well(ids["alpha"])
        dialog.select_report(ids["report_1"])
        docs_tab.apply_link_dialog(dialog, True)
    finally:
        docs_tab.show_dialogs = True
    assert sorted(panel.table.item(r, 0).text() for r in range(panel.table.rowCount())) == [
        "syn_fa_arabic.txt", "syn_unrelated.txt"]
    win.daily_report_tab.new_report()
    assert panel.table.rowCount() == 0
