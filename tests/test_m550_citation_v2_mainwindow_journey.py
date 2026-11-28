"""M550 (U4): real MainWindow journey — a user opens a v1 ``.citations.json`` on the Documents tab, saves the
content-addressed v2 copy through the file dialog, opens the v2 copy and reaches the cited passage. The v1 file is
unchanged. SYNTHETIC documents; Linux offscreen Qt (not Windows or desktop acceptance).
"""
from __future__ import annotations

import json

from core import citation_record as cr
from core import citation_record_v2 as cr2
from test_m70_selection_audit import _pump, window  # noqa: F401  (module fixture reused)
from test_m472_citation_mainwindow_journey import QUOTE, _tab, record_path  # noqa: F401


def test_documents_tab_writes_and_opens_a_v2_record(window, record_path, tmp_path, monkeypatch):  # noqa: F811
    import PySide6.QtWidgets as qw

    win, _db, _ids = window
    tab = _tab(win, "DocumentsTab")
    before = record_path.read_bytes()
    monkeypatch.setattr(qw.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(record_path), "")))
    tab.open_citation_file_button.click()
    _pump(0.2)
    assert [t["status"] for t in tab.citation_file_targets] == [cr.EXACT]
    target = tmp_path / "journey-v2.citations.json"
    monkeypatch.setattr(qw.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    tab.save_citation_v2_button.click()
    _pump(0.2)
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["record_version"] == cr2.RECORD_VERSION
    assert saved["citations"][0]["verification_state"] == cr2.VERIFIED_EXACT
    assert record_path.read_bytes() == before
    monkeypatch.setattr(qw.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(target), "")))
    tab.open_citation_file_button.click()
    _pump(0.2)
    assert [t["status"] for t in tab.citation_file_targets] == [cr.EXACT]
    tab.open_citation_passage_button.click()
    _pump(0.2)
    assert [s.cursor.selectedText() for s in tab.viewer.extraSelections()] == [QUOTE]
