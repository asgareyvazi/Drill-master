"""M52 DDR PDF report split (core/ddr_pdf_split.py).  Synthetic page texts and synthetic PDFs only."""
from __future__ import annotations

import pytest

from core import ddr_pdf_split as sp

FILLER = "Operations summary: drilled ahead with synthetic parameters, circulated, no losses observed.\n"


def page(number=None, date=None, well="SYN-WELL-1", body=FILLER):
    lines = ["DAILY DRILLING REPORT"]
    if well:
        lines.append(f"Well: {well}")
    if number is not None:
        lines.append(f"Report No: {number}")
    if date:
        lines.append(f"Report Date: {date}")
    return "\n".join(lines) + "\n" + body


CONT = "Time log continued\n" + FILLER * 2          # text page without a header
SCANNED = "   \n"                                     # no text layer


def test_one_report_over_several_pages_with_a_repeated_header_is_one_segment():
    result = sp.split_reports([page(12, "2026-03-04"), page(12, "2026-03-04"), page(12, "2026-03-04")])
    assert not result.multi_report and len(result.segments) == 1
    seg = result.segments[0]
    assert seg.pages == [1, 2, 3] and seg.report_number == 12 and seg.report_date == "2026-03-04"
    assert seg.confidence == "high" and seg.warnings == [] and seg.reasons == []


def test_several_reports_are_split_with_page_references():
    texts = [page(1, "2026-03-01"), CONT, page(2, "2026-03-02"), page(3, "2026-03-03"), CONT, CONT]
    result = sp.split_reports(texts)
    assert result.multi_report
    assert [(s.report_number, s.report_date, s.pages) for s in result.segments] == [
        (1, "2026-03-01", [1, 2]), (2, "2026-03-02", [3]), (3, "2026-03-03", [4, 5, 6])]
    assert result.segments[2].continuation_pages == [5, 6]
    assert any("pages 5, 6 have no report header" in w for w in result.segments[2].warnings)
    assert any(w.startswith("page 2 has no report header and is read as a continuation page")
               for w in result.segments[0].warnings)
    assert result.to_json()["segments"][0]["page_range"] == "1-2"


def test_a_scanned_page_is_flagged_and_assigned_by_position_only():
    result = sp.split_reports([page(7, "2026-04-01"), SCANNED, page(8, "2026-04-02")])
    first = result.segments[0]
    assert first.pages == [1, 2] and first.no_text_pages == [2]
    assert any("no text layer" in w and "OCR not run" in w for w in first.warnings)
    assert first.confidence != "high" and "pages without text" in first.reasons


def test_a_fully_scanned_pdf_reports_no_header_and_ocr_not_run_instead_of_an_empty_success():
    result = sp.split_reports([SCANNED, SCANNED])
    assert result.segments == [] and result.unassigned_pages == [1, 2]
    assert any("no report header found" in w and "OCR was not run" in w for w in result.warnings)


def test_pages_before_the_first_header_belong_to_no_report():
    result = sp.split_reports(["Cover sheet\n" + FILLER, page(4, "2026-05-05")])
    assert result.unassigned_pages == [1] and result.segments[0].pages == [2]
    assert any("before the first report header" in w for w in result.warnings)


def test_the_same_report_twice_is_an_explained_duplicate_on_both_segments():
    result = sp.split_reports([page(5, "2026-06-01"), page(6, "2026-06-02"), page(5, "2026-06-01")])
    assert len(result.segments) == 3
    first, last = result.segments[0], result.segments[2]
    assert any("duplicate of the report on pages 3" in w for w in first.warnings)
    assert any("duplicate of the report on pages 1" in w for w in last.warnings)
    assert first.confidence != "high" and not any("duplicate" in w for w in result.segments[1].warnings)


def test_one_report_number_with_two_dates_is_a_conflict():
    result = sp.split_reports([page(9, "2026-07-01"), page(9, "2026-07-02")])
    assert len(result.segments) == 2                # a different date is a different report
    assert all(any("also appears" in w and "another date" in w for w in s.warnings) for s in result.segments)


@pytest.mark.parametrize(("written", "iso", "problem"), [
    ("2026-03-04", "2026-03-04", None),
    ("25/03/2026", "2026-03-25", None),
    ("03/25/2026", "2026-03-25", None),
    ("05/05/2026", "2026-05-05", None),
    ("04/03/2026", None, "day/month order ambiguous"),
    ("31/02/2026", None, "not a calendar date"),
    ("4-Mar-2026", "2026-03-04", None),
    ("March 4, 2026", "2026-03-04", None),
])
def test_dates_are_read_without_guessing_day_month_order(written, iso, problem):
    info = sp.analyse_page(1, page(1, written))
    assert info.report_date == iso and info.date_problem == problem and info.date_text == written


def test_an_ambiguous_date_is_kept_as_written_and_warned():
    result = sp.split_reports([page(3, "04/03/2026")])
    seg = result.segments[0]
    assert seg.report_date is None and seg.date_text == "04/03/2026"
    assert any("ambiguous" in w for w in seg.warnings) and "report date not read" in seg.reasons


def test_a_different_well_is_a_suggestion_not_a_decision():
    result = sp.split_reports([page(1, "2026-03-01", well="SYN-WELL-2")], expected_well="syn well 1")
    seg = result.segments[0]
    assert any("differs from the selected well" in w and "suggestion only" in w for w in seg.warnings)
    assert seg.report_number == 1                  # nothing is dropped or re-assigned
    same = sp.split_reports([page(1, "2026-03-01", well="SYN-WELL-1")], expected_well="syn well 1")
    assert same.segments[0].warnings == [] and same.segments[0].confidence == "high"


def test_a_missing_well_name_lowers_confidence_with_the_reason():
    seg = sp.split_reports([page(1, "2026-03-01", well=None)]).segments[0]
    assert seg.confidence == "medium" and seg.reasons == ["no well name"]


def test_number_only_headers_group_and_a_date_only_header_starts_a_new_report():
    result = sp.split_reports([page(1, None), page(1, "2026-03-01"), page(None, "2026-03-02")])
    assert [s.pages for s in result.segments] == [[1, 2], [3]]
    assert result.segments[0].report_date == "2026-03-01"       # filled from the repeated header
    assert result.segments[1].report_number is None and "no report number" in result.segments[1].reasons


# ---- real (synthetic) PDF files ----------------------------------------------------------------------------
fitz = pytest.importorskip("fitz")


def make_pdf(path, texts):
    with fitz.open() as doc:
        for text in texts:
            pg = doc.new_page()
            if text.strip():
                pg.insert_text((50, 60), text, fontsize=9)
        doc.save(str(path))
    return path


def test_a_pdf_is_split_and_written_one_file_per_report_without_overwriting(tmp_path):
    src = make_pdf(tmp_path / "synthetic-ddr.pdf",
                   [page(1, "2026-03-01"), CONT, page(2, "2026-03-02"), SCANNED, page(3, "2026-03-03")])
    result = sp.analyse_pdf(src, expected_well="SYN-WELL-1")
    assert result.page_count == 5 and [s.pages for s in result.segments] == [[1, 2], [3, 4], [5]]
    out = tmp_path / "split"
    first = sp.write_segments(src, result.segments, out)
    second = sp.write_segments(src, result.segments, out)          # again: new names, nothing replaced
    assert [p.name for p in first] == ["synthetic-ddr_report-1_p1-2.pdf", "synthetic-ddr_report-2_p3-4.pdf",
                                      "synthetic-ddr_report-3_p5.pdf"]
    assert all(p.exists() for p in first + second) and not set(first) & set(second)
    with fitz.open(str(first[1])) as part:
        assert part.page_count == 2 and "Report No: 2" in part[0].get_text() and not part[1].get_text().strip()
    again = sp.analyse_pdf(first[0])
    assert [(s.report_number, s.pages) for s in again.segments] == [(1, [1, 2])]


def test_a_damaged_pdf_is_an_error_state_not_an_empty_split(tmp_path):
    bad = tmp_path / "damaged.pdf"
    bad.write_bytes(b"%PDF-1.4 this is not a pdf")
    with pytest.raises(sp.PdfSplitError, match="could not be read"):
        sp.analyse_pdf(bad)


# ---- import preview (real Qt widgets, offscreen; no database) ----------------------------------------------
@pytest.fixture
def qapp():
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _preview(qapp, path, report):
    from dialogs.excel_import_dialog import ImportPreviewDialog
    return ImportPreviewDialog(str(path), {}, report)


def test_the_preview_shows_the_split_and_blocks_a_mixed_import(qapp, tmp_path, monkeypatch):
    src = make_pdf(tmp_path / "synthetic-multi.pdf", [page(1, "2026-03-01"), page(2, "04/03/2026"), CONT])
    split = sp.analyse_pdf(src)
    dlg = _preview(qapp, src, {"review": [], "pdf_split": split.to_json()})
    try:
        table = dlg.pdf_split_table
        assert table.rowCount() == 2
        assert [table.item(r, 0).text() for r in range(2)] == ["1", "2-3"]
        assert table.item(1, 2).text() == "04/03/2026 (not read)" and "ambiguous" in table.item(1, 5).text()
        assert not dlg.confirm_btn.isEnabled() and "2 daily reports (pages 1, 2-3)" in dlg.confirm_btn.toolTip()
        assert ":disabled" in dlg.confirm_btn.styleSheet()     # the blocked button does not look enabled
        from dialogs import excel_import_dialog as eid
        warned = []
        monkeypatch.setattr(eid.QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
        dlg._confirm()                                       # even if the button were reached
        assert warned and not dlg.confirmed
        monkeypatch.setattr(eid.QMessageBox, "information", lambda *a, **k: None)
        monkeypatch.setattr(dlg, "choose_split_folder", lambda: str(tmp_path / "out"))
        written = dlg._save_split_pdfs()
        assert [p.name for p in written] == ["synthetic-multi_report-1_p1.pdf", "synthetic-multi_report-2_p2-3.pdf"]
        assert not dlg.confirmed                             # writing the split imports nothing
    finally:
        dlg.deleteLater()
        qapp.processEvents()


def test_a_single_report_pdf_is_not_blocked(qapp, tmp_path):
    src = make_pdf(tmp_path / "synthetic-one.pdf", [page(1, "2026-03-01"), CONT])
    dlg = _preview(qapp, src, {"review": [], "pdf_split": sp.analyse_pdf(src).to_json()})
    try:
        assert dlg.confirm_btn.isEnabled() and dlg.pdf_split_table.rowCount() == 1
        assert not hasattr(dlg, "save_split_btn")
    finally:
        dlg.deleteLater()
        qapp.processEvents()


def test_a_split_read_error_is_shown_as_not_assessed(qapp, tmp_path):
    from PySide6.QtWidgets import QLabel
    dlg = _preview(qapp, tmp_path / "x.pdf", {"review": [], "pdf_split_error": "PDF could not be read (FileDataError)"})
    try:
        texts = [w.text() for w in dlg.findChildren(QLabel)]
        assert any(t.startswith("Report split NOT ASSESSED: PDF could not be read") for t in texts)
        assert dlg.confirm_btn.isEnabled()                   # the existing review gates still apply
    finally:
        dlg.deleteLater()
        qapp.processEvents()


# ---- the real import batch loop (route/extraction seam as in test_import_dialog_reentrancy) ---------------
@pytest.fixture
def import_dialog(qapp, monkeypatch):
    from types import SimpleNamespace

    import dialogs.excel_import_dialog as module
    dlg = module.ExcelImportDialog(db_manager=SimpleNamespace(), well_id=1)
    persisted = []
    monkeypatch.setattr(dlg, "_do_import", lambda extracted, refresh_ui=False: persisted.append(extracted) or {
        "status": "ACCEPT", "details": ["ok"], "imported": 1, "failed": 0})
    monkeypatch.setattr(module.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    emitted = []
    dlg.import_completed.connect(emitted.append)
    yield module, dlg, persisted, emitted
    dlg.deleteLater()
    qapp.processEvents()


def test_the_batch_loop_hands_the_split_to_the_preview(import_dialog, tmp_path, monkeypatch):
    from types import SimpleNamespace
    module, dlg, persisted, emitted = import_dialog
    src = make_pdf(tmp_path / "synthetic-batch.pdf", [page(1, "2026-03-01"), page(2, "2026-03-02")])
    monkeypatch.setattr(module, "route_file", lambda source, template_matcher=None: SimpleNamespace(
        engine="excel_intelligence", fallback_engine=None, reason=""))
    extracted = {"daily_report": {"report_date": "2026-03-01", "report_number": 1},
                 "time_logs_24h": [{"time_from": "00:00", "time_to": "06:00", "duration": 6,
                                    "activity_description": "synthetic"}], "metadata": {"review_matrix": []}}
    monkeypatch.setattr(dlg, "extract_file", lambda path: (None, extracted))
    seen = []

    class Recorder:
        def __init__(self, source, extracted, report, parent=None):
            seen.append(report)
            self.confirmed = False

        def exec(self):
            return module.QDialog.Rejected

        def apply_review_changes(self, payload):
            pass
    monkeypatch.setattr(module, "ImportPreviewDialog", Recorder)
    dlg._set_import_busy(True)
    dlg._run_import_pipeline([str(src)], {})
    assert seen and seen[0]["pdf_split"]["multi_report"] is True
    assert [s["page_range"] for s in seen[0]["pdf_split"]["segments"]] == ["1", "2"]
    assert persisted == []


def test_a_multi_report_pdf_that_fails_extraction_still_says_it_holds_several_reports(import_dialog, tmp_path):
    module, dlg, persisted, emitted = import_dialog
    src = make_pdf(tmp_path / "synthetic-text-only.pdf", [page(1, "2026-03-01"), page(2, "2026-03-02")])
    dlg._set_import_busy(True)
    dlg._run_import_pipeline([str(src)], {})          # real routing and extraction: a text-only PDF fails
    (result,) = emitted[0]
    assert result["failed"] == 1 and persisted == []
    assert any("holds 2 daily reports (pages 1, 2)" in line for line in result["details"])
    assert result["pdf_split"]["multi_report"] is True
