"""M216: the import target cannot change under a running DDR import.

The batch target well is fixed when the batch starts. A switch while the worker extracts, or while the
operator looks at the modal preview, saves nothing and says why; an unchanged context still saves.
Offscreen Qt; synthetic fixtures (the M71 dialog fixture: real routing and extraction in the worker,
``_do_import`` replaced).
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402

from core.ddr_import_queue import FAILED  # noqa: E402
from test_m71_ddr_background import Preview, _run, dialog  # noqa: E402,F401  (fixture reused)


def test_a_well_switch_during_extraction_saves_nothing(dialog):  # noqa: F811
    dlg, files, persisted, emitted, _seen = dialog
    QTimer.singleShot(150, lambda: setattr(dlg, "well_id", 2))   # while the 0.6 s worker extraction runs
    _run(dlg, files[:1])
    assert persisted == []
    result = emitted[0][0]
    assert result["failed"] == 1 and "changed during preparation" in result["details"][0]
    assert dlg._queue().find(files[0]).status == FAILED


class SwitchingPreview(Preview):
    """The selected well changes while the modal preview is open (e.g. a navigation signal)."""
    dialog = None

    def exec(self):
        self.dialog.well_id = 2
        return QtWidgets.QDialog.Accepted


def test_a_well_switch_during_the_preview_is_refused_before_the_save(dialog, monkeypatch):  # noqa: F811
    import dialogs.excel_import_dialog as module
    dlg, files, persisted, emitted, _seen = dialog
    SwitchingPreview.dialog = dlg
    monkeypatch.setattr(module, "ImportPreviewDialog", SwitchingPreview)
    _run(dlg, files[:1])
    assert persisted == []
    result = emitted[0][0]
    assert result["failed"] == 1 and "target well changed" in result["details"][0]
    assert result["diagnostics"][0]["stage"] == "import.file_identity"


def test_an_unchanged_context_is_still_saved(dialog):  # noqa: F811
    dlg, files, persisted, emitted, _seen = dialog
    _run(dlg, files[:1])
    assert len(persisted) == 1 and emitted[0][0]["status"] == "ACCEPT" and dlg.well_id == 1


def test_a_file_routed_to_another_well_does_not_retarget_the_rest_of_the_batch(dialog, monkeypatch):  # noqa: F811
    dlg, files, persisted, emitted, _seen = dialog
    targets = []

    def import_into_source_well(extracted, refresh_ui=False):
        targets.append(dlg.well_id)
        persisted.append(extracted)
        dlg.well_id = 7                       # what DDRImportService does after an explicit CHOOSE_SOURCE
        return {"status": "ACCEPT", "details": ["ok"], "imported": 1, "failed": 0, "well_id": 7}

    monkeypatch.setattr(dlg, "_do_import", import_into_source_well)
    _run(dlg, files[:2])
    assert targets == [1, 1] and len(persisted) == 2 and dlg.well_id == 1
    assert [r["status"] for r in emitted[0]] == ["ACCEPT", "ACCEPT"]
