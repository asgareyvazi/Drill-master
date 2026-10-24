"""M44 Documents tab widgets (offscreen Qt; NOT native Windows desktop testing).

Real widgets, a real in-memory SQLite database and real extraction of
generated SYNTHETIC files; OCR uses a fake engine object.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.document_library import extract_document  # noqa: E402
from test_document_library import FakeOcr, _pdf  # noqa: E402
from test_scope_attribution import _mgr  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def files(tmp_path):
    bad = tmp_path / "syn_broken.pdf"
    bad.write_bytes(b"%PDF-1.4 broken")
    return {
        "report": _pdf(tmp_path / "syn_report.pdf", [
            "SYNTHETIC casing tally: 9 5/8 in shoe set at 1250 m. Cement returns observed.", "",
            "SYNTHETIC mud weight increased to 1.25 sg after a gas peak."]),
        "scanned": _pdf(tmp_path / "syn_scan.pdf", [""]),
        "bad": bad,
    }


@pytest.fixture
def engineer():
    from core.permissions import permissions
    previous = permissions.user
    permissions.set_user({"username": "engineer", "role": "engineer"})   # no id: empty DB has no users
    yield
    permissions.set_user(previous)


def _tab(db=None):
    from tabs.documents_tab import DocumentsTab
    tab = DocumentsTab(db or _mgr())
    tab.show_dialogs = False
    return tab


def test_empty_library_and_offline_ocr_message(app):
    tab = _tab()
    assert tab.table.rowCount() == 0
    assert "No documents yet" in tab.library_info.text()
    assert tab.ocr_label.text().startswith("OCR: not available") and "requirements-optional" in tab.ocr_label.text()
    tab.search_edit.setText("casing")
    tab.run_search()
    assert tab.results.count() == 0 and "No matching text" in tab.search_info.text()


def test_review_dialog_approval_edit_and_skip(app, files):
    from tabs.documents_tab import DocumentReviewDialog
    tab = _tab()
    extracts = [extract_document(files["report"]), extract_document(files["scanned"], ocr_engine=FakeOcr()),
                extract_document(files["bad"])]
    dialog = DocumentReviewDialog(extracts, tab.library)
    assert dialog.file_list.count() == 3 and 2 in dialog.blocked and "Not a readable PDF" in dialog.blocked[2]
    # text PDF: pages 1 and 3 pre-approved, page 2 (no text) not checkable
    states = [dialog.page_table.item(r, 0).checkState() for r in range(3)]
    assert states == [Qt.Checked, Qt.Unchecked, Qt.Checked]
    assert not dialog.page_table.item(1, 0).flags() & Qt.ItemIsUserCheckable
    # OCR file: unapproved until the reviewer checks it
    dialog.file_list.setCurrentRow(1)
    item = dialog.page_table.item(0, 0)
    assert item.checkState() == Qt.Unchecked and "OCR text" in dialog.page_table.item(0, 4).text()
    assert "ocr · 0.95" in dialog.page_table.item(0, 3).text()
    item.setCheckState(Qt.Checked)
    dialog.editor.setPlainText("SYNTHETIC reviewed scan text: casing shoe 1250 m")
    # skip the first file after all
    dialog.file_list.setCurrentRow(0)
    dialog.skip_check.setChecked(True)
    dialog.file_list.setCurrentRow(2)
    assert not dialog.skip_check.isEnabled() and dialog.skip_check.isChecked() and dialog.page_table.rowCount() == 0
    selected, excluded = dialog.results()
    assert [x.file_name for x, _d in selected] == ["syn_scan.pdf"]
    decisions = selected[0][1]
    assert decisions[1].approved and decisions[1].text.startswith("SYNTHETIC reviewed scan text")
    assert [(x.file_name, reason) for x, reason in excluded][0] == ("syn_report.pdf", "skipped")
    assert excluded[1][0].file_name == "syn_broken.pdf"

    outcomes = tab.import_reviewed(selected, excluded)
    assert [o.status for o in outcomes] == ["imported", "skipped", "not_importable"]
    assert tab.table.rowCount() == 1 and tab.table.item(0, 0).text() == "syn_scan.pdf"
    assert "1 of 3 file(s) imported" in tab.search_info.text()
    pages = tab.library.pages(outcomes[0].document_id)
    assert pages[0]["review_status"] == "edited" and pages[0]["method"] == "ocr"


def test_duplicate_is_blocked_in_review(app, files):
    from tabs.documents_tab import DocumentReviewDialog
    tab = _tab()
    tab.library.import_reviewed(extract_document(files["report"]))
    dialog = DocumentReviewDialog([extract_document(files["report"])], tab.library)
    assert "Duplicate of 'syn_report.pdf'" in dialog.blocked[0]
    assert dialog.results()[0] == []


def test_search_result_opens_the_stored_source_page(app, files):
    tab = _tab()
    tab.library.import_reviewed(extract_document(files["report"]))
    tab.refresh()
    tab.search_edit.setText("mud weight")
    tab.run_search()
    assert tab.results.count() == 1 and "syn_report.pdf — page 3" in tab.results.item(0).text()
    assert "SQLite FTS5" in tab.search_info.text()
    tab.results.setCurrentRow(0)
    assert "syn_report.pdf" in tab.viewer_title.text() and "page 3" in tab.viewer_title.text()
    assert "extracted" in tab.viewer_title.text()
    assert tab.viewer.toPlainText().startswith("SYNTHETIC mud weight")
    assert tab.page_combo.currentText() == "page 3" and tab.page_combo.count() == 2      # pages 1 and 3 stored
    assert len(tab.viewer.extraSelections()) == 2                                         # "mud", "weight"
    tab.page_combo.setCurrentIndex(0)
    assert tab.viewer.toPlainText().startswith("SYNTHETIC casing")


def test_worker_extracts_off_the_ui_thread_and_delete(app, files, engineer):
    tab = _tab()
    assert tab.import_button.isEnabled()
    tab.start_import([str(files["report"]), str(files["bad"])])
    worker = tab.worker
    assert worker is not None and not tab.import_button.isEnabled()
    assert worker.wait(30000)
    QApplication.processEvents()
    assert tab.worker is None and tab.import_button.isEnabled()
    assert [x.status for x in tab.pending_extracts] == ["partial", "corrupt"]
    tab.import_reviewed([(tab.pending_extracts[0], None)])
    assert tab.table.rowCount() == 1
    tab.table.selectRow(0)
    assert tab.delete_button.isEnabled()
    tab.delete_selected()
    assert tab.table.rowCount() == 0 and tab.viewer.toPlainText() == ""


def test_worker_cancel_stops_before_the_next_file(app, files):
    from tabs.documents_tab import ExtractionWorker
    worker = ExtractionWorker([str(files["report"])] * 3, use_ocr=False)
    received = []
    worker.extracted.connect(received.append)
    worker.cancel()
    worker.start()
    assert worker.wait(30000)
    QApplication.processEvents()
    assert received == [[]]


def test_import_button_follows_permission(app, monkeypatch):
    from core.permissions import permissions
    monkeypatch.setattr(permissions, "can_import", lambda: False)
    tab = _tab()
    assert not tab.import_button.isEnabled() and "cannot import" in tab.import_button.toolTip()
