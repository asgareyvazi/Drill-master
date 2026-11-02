"""M71: DDR preparation runs in a worker; the dialog stays responsive, cancellable and safe to close.

Offscreen Qt (Linux). Synthetic files only: the M54 synthetic PDFs and the
SYNTHETIC workbook fixtures. ``_do_import`` and the preview are replaced in the
dialog tests so nothing is written to a database; the preparation itself is real.
"""
from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402

from core import ddr_import_pipeline as pipe  # noqa: E402
from core.ddr_import_queue import CANCELLED  # noqa: E402
from core.ddr_import_service import DDRImportService  # noqa: E402
from core.ddr_report_profiles import profile_from_dict  # noqa: E402
from core.import_adapters import pdf_generic_tables as g  # noqa: E402
from core.import_router import route_file  # noqa: E402
from test_m54_pdf_generic_tables import scanned_pdf, text_pdf  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
SERVICE = DDRImportService()
PROFILE = profile_from_dict({"key": "syn-rig", "version": 2, "name": "SYN rig format",
                             "aliases": {"Hrs": "time_logs_24h.duration", "Activity": "time_logs_24h.activity_description",
                                         "From": "time_logs_24h.time_from"}})
OTHER = profile_from_dict({"key": "syn-other", "version": 1, "name": "SYN other",
                           "aliases": {"Code": "time_logs_24h.code"}})


def _meaningful(extracted):
    from dialogs.excel_import_dialog import has_meaningful_canonical_data
    return has_meaningful_canonical_data(extracted)


def _prepare(source, **overrides):
    kwargs = dict(route=route_file, template_matcher=SERVICE._auto_match_template,
                  extract_file=SERVICE.extract_file, meaningful=_meaningful)
    kwargs.update(overrides)
    return pipe.prepare_import(str(source), **kwargs)


# ---- the worker entry point (no Qt, no database) --------------------------------------------------
def test_a_workbook_is_prepared_into_a_plain_dto(tmp_path):
    source = tmp_path / "SYN_normal.xlsx"
    shutil.copy(FIXTURES / "normal_ddr.xlsx", source)
    out = _prepare(source)
    assert out.ok and out.stage == "validation" and out.error is None
    assert out.extracted["daily_report"] and out.import_report["pipeline_version"] == pipe.PIPELINE_VERSION


def test_failures_keep_their_stage_and_are_returned_not_raised(tmp_path):
    corrupt = tmp_path / "SYN_corrupt.xlsx"
    corrupt.write_bytes(b"PK\x03\x04 not a workbook")
    unsupported = tmp_path / "SYN_notes.bin"
    unsupported.write_bytes(bytes(range(64)))
    assert _prepare(corrupt).stage == "mapping" and _prepare(corrupt).extracted is None
    out = _prepare(unsupported)
    assert out.stage == "open" and isinstance(out.error, ValueError) and not out.ok


def test_cancel_takes_effect_at_the_next_step_and_nothing_is_returned(tmp_path):
    source = tmp_path / "SYN_normal.xlsx"
    shutil.copy(FIXTURES / "normal_ddr.xlsx", source)
    calls = []

    def cancel_after_open():
        calls.append(1)
        return len(calls) > 2              # route, open pass; mapping is refused
    out = _prepare(source, should_cancel=cancel_after_open)
    assert out.cancelled and out.extracted is None and out.stage == "open"
    assert _prepare(source, should_cancel=lambda: True).stage == "route"


def test_a_text_pdf_reports_every_column_and_an_explained_profile_suggestion(tmp_path):
    source = tmp_path / "SYN_text.pdf"
    text_pdf(str(source))
    pdf_route = lambda s, template_matcher=None: SimpleNamespace(  # noqa: E731
        engine="mineru", fallback_engine="pdf_fallback", reason="")
    out = _prepare(source, route=pdf_route, profiles=[OTHER, PROFILE])
    mapping = out.import_report["column_mapping"]
    assert mapping["columns"] == len(mapping["rows"]) >= 5
    headers = [row["header"] for row in mapping["rows"]]
    assert {"From", "To", "Hrs", "Code", "Activity"} <= set(headers)
    assert set(mapping["unmapped"]) == {row["header"] for row in mapping["rows"] if not row["field"]}
    assert out.ok and out.extracted["metadata"]["column_mapping"] == mapping      # kept with the evidence
    best = out.import_report["profile_suggestions"][0]
    assert best["key"] == "syn-rig" and best["matched"] == 3 and set(best["matched_headers"]) == {"From", "Hrs", "Activity"}
    assert best["total"] == len(headers) and "Code" in best["unmatched_headers"]


def test_a_scanned_pdf_stops_at_the_ocr_boundary_and_guesses_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "ocr_status", lambda: "unavailable")
    source = tmp_path / "SYN_scan.pdf"
    scanned_pdf(str(source))
    pdf_route = lambda s, template_matcher=None: SimpleNamespace(  # noqa: E731
        engine="mineru", fallback_engine="pdf_fallback", reason="")
    out = _prepare(source, route=pdf_route)
    assert out.extracted is None and out.stage == "open" and "OCR unavailable" in str(out.error)


def test_suggestions_ignore_profiles_without_own_alias_hits_and_never_apply_themselves():
    assert pipe.suggest_profiles([OTHER], ["Depth", "Remarks"]) == []
    assert pipe.suggest_profiles([PROFILE], []) == []
    from dialogs.excel_import_dialog import ImportPreviewDialog
    report = {"column_mapping": {"columns": 3, "mapped": 2, "unmapped": ["Remarks"]},
              "profile_suggestions": [{"key": "syn-rig", "version": 2, "name": "SYN rig format", "matched": 2,
                                       "total": 3, "matched_headers": ["Hrs", "From"]}]}
    text = ImportPreviewDialog.column_summary(report)
    assert "3 read, 2 mapped" in text and "Remarks" in text and "Suggested profile: SYN rig format v2" in text
    assert "Suggested" not in ImportPreviewDialog.column_summary(report, "syn-rig")   # already active


def test_the_preview_shows_the_ocr_note_from_the_real_report_keys():
    from dialogs.excel_import_dialog import ImportPreviewDialog
    report = {"fallback_diagnostics": {"fallback": {"scanned_pages": [2], "ocr": "unavailable"}}}
    assert "page(s) 2" in ImportPreviewDialog.pdf_extraction_note(report)


# ---- the dialog: worker, responsiveness, cancel, shutdown, well guard ------------------------------
class Preview:
    def __init__(self, *args):
        self.confirmed = True

    def exec(self):
        return QtWidgets.QDialog.Accepted

    def apply_review_changes(self, payload):
        pass


@pytest.fixture
def dialog(monkeypatch, tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import dialogs.excel_import_dialog as module

    dlg = module.ExcelImportDialog(db_manager=SimpleNamespace(), well_id=1)
    persisted, seen = [], {}
    monkeypatch.setattr(dlg, "_do_import", lambda extracted, refresh_ui=False: persisted.append(extracted) or {
        "status": "ACCEPT", "details": ["ok"], "imported": 1, "failed": 0})
    monkeypatch.setattr(module, "ImportPreviewDialog", Preview)
    monkeypatch.setattr(module.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(dlg, "accept", lambda: None)
    real_extract = dlg.extract_file

    def slow_extract(path):
        seen.setdefault("threads", []).append(threading.current_thread() is threading.main_thread())
        time.sleep(0.6)
        return real_extract(path)
    monkeypatch.setattr(dlg, "extract_file", slow_extract)
    emitted = []
    dlg.import_completed.connect(emitted.append)
    files = []
    for name in ("SYN_a.xlsx", "SYN_b.xlsx"):
        shutil.copy(FIXTURES / "normal_ddr.xlsx", tmp_path / name)
        files.append(str(tmp_path / name))
    (tmp_path / "SYN_b.xlsx").write_bytes((tmp_path / "SYN_b.xlsx").read_bytes() + b"\0")   # distinct bytes
    yield dlg, files, persisted, emitted, seen
    dlg._prepare_worker = dlg._mineru_worker = None
    dlg.deleteLater()
    app.processEvents()


def _run(dlg, files):
    dlg._set_import_busy(True)
    dlg._start_import_batch(files)


def test_extraction_runs_off_the_gui_thread_while_the_event_loop_keeps_running(dialog):
    dlg, files, persisted, emitted, seen = dialog
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start(20)
    _run(dlg, files[:1])
    timer.stop()
    assert seen["threads"] == [False]                       # never on the GUI thread
    assert len(ticks) >= 10                                 # the GUI loop ran during the 0.6 s extraction
    assert len(persisted) == 1 and emitted[0][0]["status"] == "ACCEPT"
    assert dlg._prepare_worker is None and not dlg._import_busy


def test_cancel_during_preparation_saves_nothing_and_cancels_the_rest(dialog):
    dlg, files, persisted, emitted, _seen = dialog
    QTimer.singleShot(150, dlg._queue_cancel)
    _run(dlg, files)
    assert persisted == []
    statuses = [r.get("queue_status") for r in emitted[0]]
    assert statuses == [CANCELLED, CANCELLED]
    assert "cancelled during" in emitted[0][0]["details"][0]


def test_closing_while_a_worker_runs_is_refused_and_cancels_instead(dialog):
    dlg, files, persisted, emitted, _seen = dialog
    dlg.show()
    state = {}

    def try_close():
        state["running"] = dlg._workers_running()
        dlg.reject()
        state["visible_after_reject"] = dlg.isVisible()
    QTimer.singleShot(150, try_close)
    _run(dlg, files[:1])
    assert state == {"running": True, "visible_after_reject": True}
    assert "Cancelling" in dlg.import_status.text() or emitted
    assert persisted == [] and not dlg._workers_running()
    dlg.reject()
    assert not dlg.isVisible()                              # closes once no worker runs


def test_a_late_result_cannot_be_saved_for_another_well(dialog):
    dlg, files, persisted, emitted, _seen = dialog
    QTimer.singleShot(150, lambda: setattr(dlg, "well_id", 2))
    _run(dlg, files[:1])
    assert persisted == []
    assert emitted[0][0]["failed"] == 1 and "target well changed" in emitted[0][0]["error"]
