"""Import dialog: one batch at a time, preview cancel persists nothing (M43 closure).

Before the guard, a second click while MinerU was parsing (or while
processEvents() repainted during the pipeline) started another batch: it
overwrote the pending file list, so the first batch was silently dropped and
the second one ran twice. Real Qt widgets (offscreen); persistence is replaced
by a recorder, no database is touched.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from PySide6 import QtWidgets


@pytest.fixture
def dialog(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import dialogs.excel_import_dialog as module

    dlg = module.ExcelImportDialog(db_manager=SimpleNamespace(), well_id=1)
    persisted = []
    monkeypatch.setattr(dlg, "_do_import", lambda extracted, refresh_ui=False: persisted.append(extracted) or {
        "status": "ACCEPT", "details": ["ok"], "imported": 1, "failed": 0})
    monkeypatch.setattr(module.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    dlg._persisted = persisted
    yield module, dlg
    dlg.deleteLater()
    app.processEvents()


class FakeWorker:
    instances = []

    def __init__(self, function, sources, parent=None):
        self.sources = list(sources)
        self.result_ready = SimpleNamespace(connect=lambda slot: setattr(self, "on_ready", slot))
        self.failed = SimpleNamespace(connect=lambda slot: setattr(self, "on_failed", slot))
        FakeWorker.instances.append(self)

    def start(self):
        pass  # the test decides when the "thread" finishes

    def deleteLater(self):
        pass


def test_second_click_while_mineru_parses_is_refused_and_batch_is_kept(dialog, monkeypatch):
    module, dlg = dialog
    FakeWorker.instances = []
    picks = iter([(["/tmp/first.pdf"], ""), (["/tmp/second.pdf"], "")])
    monkeypatch.setattr(module.QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: next(picks)))
    monkeypatch.setattr(module, "route_file", lambda source, template_matcher=None: SimpleNamespace(
        engine="mineru", fallback_engine=None, reason=""))
    monkeypatch.setattr(module, "FunctionWorker", FakeWorker)
    ran = []
    monkeypatch.setattr(dlg, "_run_import_pipeline_steps", lambda files, results: ran.append(list(files)))

    dlg._unified_import()
    assert dlg._import_busy and not dlg._import_btn.isEnabled()
    dlg._unified_import()  # second click while the worker is still parsing
    assert len(FakeWorker.instances) == 1, "no second batch may start"
    assert dlg._pending_import_files == ["/tmp/first.pdf"]
    assert "already running" in dlg.import_status.text()

    FakeWorker.instances[0].on_ready([])
    assert ran == [["/tmp/first.pdf"]]
    assert not dlg._import_busy and dlg._import_btn.isEnabled()


def test_guard_is_released_when_the_pipeline_raises(dialog, monkeypatch):
    module, dlg = dialog
    monkeypatch.setattr(module.QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: (["/tmp/a.xlsx"], "")))
    monkeypatch.setattr(module, "route_file", lambda source, template_matcher=None: SimpleNamespace(
        engine="excel_intelligence", fallback_engine=None, reason=""))

    def boom(files, results):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(dlg, "_run_import_pipeline_steps", boom)
    with pytest.raises(RuntimeError):
        dlg._unified_import()
    assert not dlg._import_busy and dlg._import_btn.isEnabled()


def test_no_file_selected_leaves_the_dialog_idle(dialog, monkeypatch):
    module, dlg = dialog
    monkeypatch.setattr(module.QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: ([], "")))
    dlg._unified_import()
    assert not dlg._import_busy and dlg._import_btn.isEnabled()


@pytest.mark.parametrize("confirmed,expected_persisted", [(False, 0), (True, 1)])
def test_preview_cancel_persists_nothing(dialog, monkeypatch, confirmed, expected_persisted):
    module, dlg = dialog
    monkeypatch.setattr(module, "route_file", lambda source, template_matcher=None: SimpleNamespace(
        engine="excel_intelligence", fallback_engine=None, reason=""))
    extracted = {"daily_report": {"report_date": "2026-01-02", "report_number": 1},
                 "time_logs_24h": [{"time_from": "00:00", "time_to": "06:00", "duration": 6,
                                    "activity_description": "synthetic"}],
                 "metadata": {"review_matrix": []}}
    monkeypatch.setattr(dlg, "extract_file", lambda path: (None, extracted))

    class Preview:
        def __init__(self, *args):
            self.confirmed = confirmed

        def exec(self):
            return module.QDialog.Accepted if confirmed else module.QDialog.Rejected

        def apply_review_changes(self, payload):
            pass

    monkeypatch.setattr(module, "ImportPreviewDialog", Preview)
    emitted = []
    dlg.import_completed.connect(emitted.append)
    dlg._set_import_busy(True)
    dlg._run_import_pipeline(["/tmp/synthetic.xlsx"], {})
    assert len(dlg._persisted) == expected_persisted
    assert emitted and (emitted[0][0].get("skipped") == 1) is (not confirmed)
    assert not dlg._import_busy
