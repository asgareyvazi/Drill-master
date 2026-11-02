"""M84: DDR batch import - file identity is re-checked just before the atomic save, and parser results of
files that never run are cleaned up.

Offscreen Qt; synthetic workbook fixtures; ``_do_import`` is replaced (nothing is written to a database)
while routing, extraction and validation run for real in the worker (the M71 dialog fixture).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

from core.ddr_import_queue import CANCELLED, FAILED, ImportQueue, file_fingerprint  # noqa: E402
from test_m71_ddr_background import Preview, _run, dialog  # noqa: E402,F401  (fixture reused)

FIXTURES = Path(__file__).parent / "fixtures"


def _file(tmp_path, name="SYN_id.xlsx"):
    path = tmp_path / name
    shutil.copy(FIXTURES / "normal_ddr.xlsx", path)
    return path


def test_verify_identity_detects_changed_and_vanished_files(tmp_path):
    path = _file(tmp_path)
    queue = ImportQueue()
    entry = queue.add([str(path)])[0]
    assert queue.start(entry) and entry.fingerprint == file_fingerprint(str(path))
    assert queue.verify_identity(entry) is None
    path.write_bytes(path.read_bytes() + b"\0")
    assert "changed after it was read" in queue.verify_identity(entry)
    path.unlink()
    assert "can no longer be read" in queue.verify_identity(entry)


class ChangingPreview(Preview):
    """The user confirms the preview while the file on disk is replaced by other bytes."""
    target = None

    def exec(self):
        Path(self.target).write_bytes(Path(self.target).read_bytes() + b"edited")
        return QtWidgets.QDialog.Accepted


def test_a_file_changed_during_preview_is_never_saved(dialog, monkeypatch):  # noqa: F811
    import dialogs.excel_import_dialog as module
    dlg, files, persisted, emitted, _seen = dialog
    ChangingPreview.target = files[0]
    monkeypatch.setattr(module, "ImportPreviewDialog", ChangingPreview)
    _run(dlg, files[:1])
    assert persisted == []
    result = emitted[0][0]
    assert result["queue_status"] == FAILED and "changed after it was read" in result["details"][0]
    assert result["diagnostics"][0]["stage"] == "import.file_identity"
    entry = dlg._queue().find(files[0])
    assert entry.status == FAILED and entry.result["details"] == result["details"]


def test_an_unchanged_file_is_still_saved(dialog):  # noqa: F811
    dlg, files, persisted, emitted, _seen = dialog
    _run(dlg, files[:1])
    assert len(persisted) == 1 and emitted[0][0]["status"] == "ACCEPT"


class FakeParse:
    def __init__(self):
        self.success, self.cleaned = True, 0

    def cleanup(self):
        self.cleaned += 1


def test_parser_results_of_files_that_never_run_are_cleaned_up(dialog):  # noqa: F811
    dlg, files, persisted, emitted, _seen = dialog
    queue = dlg._queue()
    queue.add(files)
    queue.cancel()                                   # cancelled while the external parser was running
    parses = {dlg._result_key(f): FakeParse() for f in files}
    dlg._run_import_pipeline_steps(files, parses)
    assert persisted == [] and [r["queue_status"] for r in emitted[0]] == [CANCELLED, CANCELLED]
    assert [p.cleaned for p in parses.values()] == [1, 1]
