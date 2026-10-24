"""M44: one failing workbook never stops a DDR import batch.

Real routing and real canonical extraction of the committed SYNTHETIC
fixtures, through the real ExcelImportDialog batch loop (offscreen Qt; not
native Windows testing).  The preview is auto-confirmed and persistence is
replaced by a recorder; persistence atomicity is covered by the existing
import-service tests.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6 import QtWidgets

FIXTURES = Path(__file__).parent / "fixtures"


class AutoConfirmPreview:
    def __init__(self, source, extracted, report, parent=None):
        self.confirmed = True

    def exec(self):
        return QtWidgets.QDialog.Accepted

    def apply_review_changes(self, extracted):
        pass


@pytest.fixture
def dialog(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import dialogs.excel_import_dialog as module

    dlg = module.ExcelImportDialog(db_manager=SimpleNamespace(), well_id=1)
    persisted = []
    monkeypatch.setattr(dlg, "_do_import", lambda extracted, refresh_ui=False: persisted.append(extracted) or {
        "status": "ACCEPT", "details": ["ok"], "imported": 1, "failed": 0})
    monkeypatch.setattr(module, "ImportPreviewDialog", AutoConfirmPreview)
    monkeypatch.setattr(module.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    emitted = []
    dlg.import_completed.connect(emitted.append)
    yield dlg, persisted, emitted
    dlg.deleteLater()
    app.processEvents()


def test_failing_files_are_reported_and_the_batch_continues(dialog, tmp_path):
    dlg, persisted, emitted = dialog
    corrupt = tmp_path / "SYN_corrupt.xlsx"
    corrupt.write_bytes(b"PK\x03\x04 not really a workbook")
    good = tmp_path / "SYN_normal.xlsx"
    shutil.copy(FIXTURES / "normal_ddr.xlsx", good)
    unsupported = tmp_path / "SYN_notes.bin"
    unsupported.write_bytes(bytes(range(256)))
    no_template = tmp_path / "SYN_multi_header.xlsx"          # no canonical template -> validation failure
    shutil.copy(FIXTURES / "multi_header_ddr.xlsx", no_template)
    last = tmp_path / "SYN_golden_a.xlsx"
    shutil.copy(FIXTURES / "synthetic_ddr_golden_a.xlsx", last)

    files = [str(corrupt), str(good), str(unsupported), str(no_template), str(last)]
    dlg._set_import_busy(True)                       # as the Import click does before the pipeline
    dlg._run_import_pipeline(files, {})

    (results,) = emitted
    assert [Path(r["file"]).name for r in results] == [Path(f).name for f in files]
    by_name = {Path(r["file"]).name: r for r in results}
    stages = {name: r.get("diagnostics", [{}])[0].get("stage") for name, r in by_name.items()}
    assert stages["SYN_corrupt.xlsx"] == "import.mapping"
    assert stages["SYN_notes.bin"] == "import.open"
    assert stages["SYN_multi_header.xlsx"] == "validation.meaningful_data"
    assert all(by_name[n]["failed"] == 1 for n in ("SYN_corrupt.xlsx", "SYN_notes.bin", "SYN_multi_header.xlsx"))
    assert by_name["SYN_normal.xlsx"]["status"] == "ACCEPT"
    assert by_name["SYN_golden_a.xlsx"]["status"] == "ACCEPT"     # after three failures
    assert len(persisted) == 2                       # only the good files reached the save boundary
    summary = dlg.batch_summary.toPlainText()
    assert "Batch completed: 5 files" in summary and "Successful: 2" in summary and "Failed: 3" in summary
    assert dlg._import_busy is False                 # guard released for the next batch
