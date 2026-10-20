"""Saving a well whose validation only warns must save and show the warning.

Regression (M43 Phase 4): `tabs/w1_well_info.py` called `show_warning_message`
without importing it. The wildcard Qt imports hid the undefined name from the
F821 gate, so pressing Save on a well without a well type raised NameError,
which the broad handler turned into an error popup and an unsaved well.
The test imports the real module (no injected namespace), so a missing import
fails here.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication


class _RecordingMessageBox:
    Warning, Information, Critical, Ok = "warning", "information", "critical", 1
    shown: list[tuple[str, str]] = []

    def __init__(self, parent=None):
        self._icon = None
        self._text = ""

    def setIcon(self, icon):
        self._icon = icon

    def setWindowTitle(self, title):
        pass

    def setText(self, text):
        self._text = text

    def setStandardButtons(self, buttons):
        pass

    def exec(self):
        type(self).shown.append((self._icon, self._text))
        return self.Ok


def test_well_with_only_validation_warnings_is_saved_and_warned(monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("DRILLMASTER_AI_IMPORT", "0")
    utils = importlib.import_module("ui.utils")
    module = importlib.import_module("tabs.w1_well_info")
    _RecordingMessageBox.shown = []
    monkeypatch.setattr(utils, "QMessageBox", _RecordingMessageBox)

    saved = []
    form = {"name": "Synthetic well", "code": "SYN-1", "well_type": "", "target_depth": 1200.0}
    tab = module.WellInfoTab.__new__(module.WellInfoTab)
    tab.current_well = {"id": 7, "name": "Synthetic well"}
    tab._loaded_form_values = dict(form)
    tab._form_touched = ()
    tab.get_form_data = lambda: dict(form)
    tab.db = SimpleNamespace(save_well=lambda data: saved.append(data) or True)
    tab.main_window = None
    tab.data_saved = SimpleNamespace(emit=lambda: None)

    assert tab.save_data(show_popup=True) is True
    assert len(saved) == 1 and saved[0]["id"] == 7
    icons = [icon for icon, _ in _RecordingMessageBox.shown]
    assert icons == ["warning", "information"], _RecordingMessageBox.shown
    assert "Well type is missing" in _RecordingMessageBox.shown[0][1]
