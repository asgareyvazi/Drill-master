"""M61: report-profile behaviour that was stored but not applied, and the batch queue.

Synthetic documents only. Normalizer/queue tests are pure Python; the dialog
tests run the real ExcelImportDialog batch loop offscreen (not Windows desktop
testing) with the preview auto-confirmed and persistence replaced by a recorder.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import ddr_import_queue as q
from core.ddr_report_profiles import ReportProfile, validate_profile
from core.import_adapters.pdf_generic_tables import join_continuations
from core.mineru_engine import PROFILE_RULES_VERSION, DocumentNormalizer, DocumentTable, MinerUDocument, Provenance

FIXTURES = Path(__file__).parent / "fixtures"


def _profile(**overrides):
    base = dict(key="syn-m61", version=3, name="Synthetic M61", report_format="pdf",
                aliases={"Fluid Density": "mud_report.mw"}, units={"mud_report.mw": "ppg"},
                date_formats=("%d/%m/%Y",), table_rules={}, continuation=True, confidence_threshold=0.85)
    base.update(overrides)
    return ReportProfile(**base)


def _doc(headers, rows, name="daily report"):
    return MinerUDocument(source_file="synthetic.pdf", backend="pdf-native-fallback", method="pymupdf", tables=[
        DocumentTable(headers=headers, rows=rows, provenance=Provenance("synthetic.pdf", source_page=2), name=name)])


def _date_item(normalized):
    return next(p for p in normalized.provenance if p["canonical_field"] == "daily_report.report_date")


def _review(normalized, needle):
    return [w for w in normalized.warnings if needle in str(w.get("message", ""))]


# ---- date_formats ------------------------------------------------------------------------------
def test_the_first_and_only_matching_profile_format_sets_the_date():
    normalized = DocumentNormalizer(profile=_profile()).normalize(_doc(["Report Date"], [["03/04/2025"]]))
    item = _date_item(normalized)
    assert item["normalized_value"] == "2025-04-03"          # day-first, as declared
    assert item["original_value"] == "03/04/2025"
    assert not _review(normalized, "date formats")


def test_a_day_month_ambiguous_date_goes_to_review_with_both_readings():
    profile = _profile(date_formats=("%d/%m/%Y", "%m/%d/%Y"))
    normalized = DocumentNormalizer(profile=profile).normalize(_doc(["Report Date"], [["03/04/2025"]]))
    assert _date_item(normalized)["normalized_value"] is None
    (warning,) = _review(normalized, "ambiguous")
    assert "'03/04/2025'" in warning["message"]
    assert "2025-04-03 by %d/%m/%Y" in warning["message"] and "2025-03-04 by %m/%d/%Y" in warning["message"]
    assert "syn-m61 v3" in warning["message"]


def test_two_formats_that_agree_are_not_ambiguous():
    profile = _profile(date_formats=("%d/%m/%Y", "%m/%d/%Y"))
    normalized = DocumentNormalizer(profile=profile).normalize(_doc(["Report Date"], [["15/04/2025"]]))
    assert _date_item(normalized)["normalized_value"] == "2025-04-15"


def test_an_unmatched_date_keeps_the_original_string_for_review():
    normalized = DocumentNormalizer(profile=_profile()).normalize(_doc(["Report Date"], [["2025-04-03"]]))
    assert _date_item(normalized)["normalized_value"] is None
    (warning,) = _review(normalized, "matches none")
    assert warning["value"] == "2025-04-03" and "%d/%m/%Y" in warning["message"]


def test_profile_order_matters_and_no_profile_keeps_the_canonical_parser():
    iso = _profile(date_formats=("%Y-%m-%d", "%d/%m/%Y"))
    assert _date_item(DocumentNormalizer(profile=iso).normalize(
        _doc(["Report Date"], [["2025-04-03"]])))["normalized_value"] == "2025-04-03"
    plain = DocumentNormalizer().normalize(_doc(["Report Date"], [["2025-04-03"]]))
    assert not _review(plain, "date formats")


# ---- table_rules -------------------------------------------------------------------------------
def test_a_stop_marker_ignores_its_row_and_every_later_row_with_reasons():
    profile = _profile(table_rules={"stop_markers": ["Total"]})
    rows = [["10.1"], ["10.2"], ["Total 20.3"], ["10.9"]]
    normalized = DocumentNormalizer(profile=profile).normalize(_doc(["Fluid Density"], rows, name="mud report"))
    kept = [p["original_value"] for p in normalized.provenance if p["canonical_field"] == "mud_report.mw"]
    assert kept == ["10.1", "10.2"]
    ignored = [w for w in normalized.warnings if w.get("rule")]
    assert [w["source"]["source_row"] for w in ignored] == [3, 4]
    assert "stop marker 'Total'" in ignored[0]["rule"] and "after stop marker 'Total'" in ignored[1]["rule"]
    assert all(w["profile_rules_version"] == PROFILE_RULES_VERSION for w in ignored)
    assert ignored[1]["value"] == "10.9" and ignored[1]["source"]["source_page"] == 2


def test_skip_rows_ignore_only_matching_rows():
    profile = _profile(table_rules={"skip_rows_containing": ["carried forward"]})
    rows = [["10.1"], ["carried forward"], ["10.4"]]
    normalized = DocumentNormalizer(profile=profile).normalize(_doc(["Fluid Density"], rows, name="mud report"))
    kept = [p["original_value"] for p in normalized.provenance if p["canonical_field"] == "mud_report.mw"]
    assert kept == ["10.1", "10.4"]
    (ignored,) = [w for w in normalized.warnings if w.get("rule")]
    assert ignored["source"]["source_row"] == 2 and "skip rule 'carried forward'" in ignored["rule"]


def test_skip_tables_ignore_a_whole_table_and_say_how_many_rows():
    profile = _profile(table_rules={"skip_tables_containing": ["mud report"]})
    normalized = DocumentNormalizer(profile=profile).normalize(
        _doc(["Fluid Density"], [["10.1"], ["10.2"]], name="mud report"))
    assert not [p for p in normalized.provenance if p["canonical_field"] == "mud_report.mw"]
    (ignored,) = [w for w in normalized.warnings if w.get("rule")]
    assert "2 row(s)" in ignored["message"]


def test_skip_tables_rule_is_validated_and_rules_ride_in_metadata():
    assert validate_profile(_profile(table_rules={"skip_tables_containing": "x"}))
    normalized = DocumentNormalizer(profile=_profile(table_rules={"stop_markers": ["Total"]})).normalize(
        _doc(["Fluid Density"], [["10.1"]], name="mud report"))
    meta = normalized.metadata()
    assert meta["profile"]["key"] == "syn-m61" and meta["profile"]["table_rules"] == {"stop_markers": ["Total"]}
    assert meta["profile_rules_version"] == PROFILE_RULES_VERSION


# ---- continuation ------------------------------------------------------------------------------
def _page_tables():
    t = {"headers": ["A", "B"], "rows": [["1", "2"]]}
    return [(1, [dict(t)], True), (2, [dict(t, rows=[["3", "4"]])], True)]


def test_continuation_joins_and_a_profile_can_disable_it_keeping_page_provenance():
    joined = join_continuations(_page_tables())
    assert len(joined) == 1 and joined[0]["row_pages"] == [1, 2] and joined[0]["continued"]
    separate = join_continuations(_page_tables(), join=False)
    assert [t["pages"] for t in separate] == [[1], [2]] and not any(t.get("continued") for t in separate)


# ---- confidence_threshold ----------------------------------------------------------------------
def test_profile_threshold_drives_acceptance_bands_and_counts():
    from dialogs.excel_import_dialog import review_counts, review_thresholds

    assert review_thresholds(None) == (0.95, 0.70)
    assert review_thresholds({"confidence_threshold": 0.85}) == (0.85, 0.70)
    assert review_thresholds({"confidence_threshold": 0.6}) == (0.6, 0.6)
    rows = [{"confidence": 0.9}, {"confidence": 0.8}, {"confidence": 0.5}, {"confidence": None},
            {"confidence": 0.99, "validation_state": "needs_review"}]
    assert review_counts(rows, {"confidence_threshold": 0.85}) == {
        "eligible": 1, "review": 2, "low": 1, "not_assessed": 1, "threshold": 0.85}
    assert review_counts(rows, None)["eligible"] == 0          # 0.9 < default 0.95


# ---- queue core --------------------------------------------------------------------------------
def test_queue_states_remove_retry_cancel_and_in_batch_duplicates(tmp_path):
    a, b, c = (tmp_path / n for n in ("a.xlsx", "b.xlsx", "c.xlsx"))
    a.write_bytes(b"one")
    b.write_bytes(b"one")       # same bytes as a
    c.write_bytes(b"two")
    queue = q.ImportQueue()
    queue.add([str(a), str(b), str(c)])
    assert [e.status for e in queue.entries] == [q.QUEUED, q.DUPLICATE, q.QUEUED]
    assert "Same content as a.xlsx" in queue.entries[1].diagnostics[0]
    first = queue.entries[0]
    queue.start(first, "Synthetic M61 (v3)")
    assert not queue.remove(0)                                     # running
    assert queue.finish(first, {"status": "ACCEPT", "details": ["ok"]}) == q.SAVED
    assert not queue.remove(0)                                     # saved results are kept
    assert queue.cancel() == 1 and queue.entries[2].status == q.CANCELLED
    assert [e.path for e in queue.retry()] == [str(c)] and queue.entries[2].status == q.QUEUED
    assert not queue.cancel_requested
    assert queue.remove(1) and len(queue.entries) == 2
    counts = queue.counts()
    assert counts[q.SAVED] == 1 and counts[q.QUEUED] == 1
    assert "saved 1" in queue.summary_text() and "Synthetic" not in queue.summary_text().splitlines()[0]


@pytest.mark.parametrize("result, status", [
    ({"status": "ACCEPT"}, q.SAVED),
    ({"status": "REVIEW_REQUIRED"}, q.REVIEW_REQUIRED),
    ({"status": "ACCEPT", "reimport": True}, q.DUPLICATE),
    ({"skipped": 1, "imported": 0}, q.SKIPPED),
    ({"status": "VALIDATION_ERROR"}, q.FAILED),
    ({"status": "PERSISTENCE_ERROR"}, q.FAILED),
])
def test_results_map_to_distinct_statuses(result, status):
    assert q.status_from_result(result) == status


# ---- dialog integration (offscreen) ------------------------------------------------------------
class _Preview:
    confirm = True

    def __init__(self, source, extracted, report, parent=None):
        self.confirmed = _Preview.confirm

    def exec(self):
        from PySide6 import QtWidgets
        return QtWidgets.QDialog.Accepted if self.confirmed else QtWidgets.QDialog.Rejected

    def apply_review_changes(self, extracted):
        pass


@pytest.fixture
def dialog(monkeypatch):
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import dialogs.excel_import_dialog as module

    dlg = module.ExcelImportDialog(db_manager=SimpleNamespace(), well_id=1)
    saved = []
    monkeypatch.setattr(dlg, "_do_import", lambda extracted, refresh_ui=False: saved.append(extracted) or {
        "status": "ACCEPT", "details": ["ok"], "imported": 1, "failed": 0})
    monkeypatch.setattr(module, "ImportPreviewDialog", _Preview)
    monkeypatch.setattr(module.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    _Preview.confirm = True
    yield dlg, saved
    dlg.deleteLater()
    app.processEvents()


def test_batch_queue_shows_saved_duplicate_and_failed_rows(dialog, tmp_path):
    dlg, saved = dialog
    good = tmp_path / "SYN_a.xlsx"
    shutil.copy(FIXTURES / "normal_ddr.xlsx", good)
    twin = tmp_path / "SYN_b.xlsx"
    shutil.copy(FIXTURES / "normal_ddr.xlsx", twin)
    corrupt = tmp_path / "SYN_bad.xlsx"
    corrupt.write_bytes(b"PK\x03\x04 not a workbook")
    dlg._start_import_batch([str(good), str(twin), str(corrupt)])
    statuses = [e.status for e in dlg.import_queue.entries]
    assert statuses == [q.SAVED, q.DUPLICATE, q.FAILED]
    assert len(saved) == 1                                           # the twin never reached persistence
    assert dlg.queue_table.rowCount() == 3 and dlg.queue_table.item(1, 1).text() == q.DUPLICATE
    assert "duplicate 1" in dlg.batch_summary.toPlainText() and "failed 1" in dlg.batch_summary.toPlainText()


def test_preview_cancel_is_skipped_not_failed_and_retry_reruns_it(dialog, tmp_path):
    dlg, saved = dialog
    good = tmp_path / "SYN_a.xlsx"
    shutil.copy(FIXTURES / "normal_ddr.xlsx", good)
    _Preview.confirm = False
    dlg._start_import_batch([str(good)])
    assert dlg.import_queue.entries[0].status == q.SKIPPED and not saved
    _Preview.confirm = True
    dlg._queue_retry()
    entry = dlg.import_queue.entries[0]
    assert entry.status == q.SAVED and entry.attempts == 2 and len(saved) == 1


def test_cancel_marks_files_not_started_as_cancelled(dialog, tmp_path, monkeypatch):
    dlg, saved = dialog
    files = []
    for name in ("SYN_1.xlsx", "SYN_2.xlsx"):
        path = tmp_path / name
        shutil.copy(FIXTURES / "normal_ddr.xlsx", path)
        path.write_bytes(path.read_bytes() + name.encode())          # distinct bytes
        files.append(str(path))
    original = dlg._do_import

    def save_then_cancel(extracted, refresh_ui=False):
        dlg._queue_cancel()                                         # user presses Cancel during file 1
        return original(extracted, refresh_ui)

    monkeypatch.setattr(dlg, "_do_import", save_then_cancel)
    dlg._start_import_batch(files)
    assert [e.status for e in dlg.import_queue.entries] == [q.SAVED, q.CANCELLED]
    assert len(saved) == 1


def test_pdf_fallback_forwards_a_disabled_continuation(monkeypatch):
    import core.import_adapters.pdf_tables as pdf_tables
    from core.mineru_engine import MinerUOutputError, parse_pdf_native_fallback

    seen = []
    monkeypatch.setattr(pdf_tables, "extract_tables", lambda path, **kw: seen.append(kw) or {"tables": []})
    for flag in (True, False):
        with pytest.raises(MinerUOutputError):
            parse_pdf_native_fallback("synthetic.pdf", continuation=flag)
    assert seen == [{}, {"continuation": False}]


def test_preview_bulk_accept_follows_the_profile_and_skips_values_needing_review():
    from PySide6 import QtWidgets
    from dialogs.excel_import_dialog import ImportPreviewDialog

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    review = [{"confidence": 0.99, "validation_state": "needs_review", "target_field": "daily_report.report_date"},
              {"confidence": 0.90, "target_field": "mud_report.mw"},
              {"confidence": 0.50, "target_field": "mud_report.pv"}]
    dialogs = []
    try:
        for profile, expected in (({"confidence_threshold": 0.85}, ["REVIEW", "ACCEPT", "REVIEW"]),
                                  (None, ["REVIEW", "REVIEW", "REVIEW"])):
            dlg = ImportPreviewDialog("synthetic.pdf", {}, {"review": [dict(r) for r in review], "profile": profile})
            dialogs.append(dlg)
            dlg._accept_high()
            assert [dlg.table.item(r, 9).text() for r in range(3)] == expected
        assert dialogs[0].threshold_label.text() == (
            "Acceptance threshold 85%: 1 eligible, 1 need review, 1 low, 0 not scored.")
        dialogs[0]._reject_low()
        assert dialogs[0].table.item(2, 9).text() == "REJECT"
    finally:
        for dlg in dialogs:
            dlg.deleteLater()
        app.processEvents()
