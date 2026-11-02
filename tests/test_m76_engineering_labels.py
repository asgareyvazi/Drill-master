"""M76: engineering scope labels stay honest where the user sees them.

Offscreen Qt for the W13 page. Nothing here validates a method; it pins the
labels that keep the scope visible (TRAINING AID / SCREENING / subset).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from core.engineering.engines.anti_collision import AntiCollisionEngine
from core.engineering.engines.casing import CasingEngine
from core.engineering.engines.torque_drag import TorqueDragEngine


def test_engine_method_labels_keep_their_scope():
    assert "SCREENING" in TorqueDragEngine.METHOD and "soft-string" in TorqueDragEngine.METHOD
    assert "screening" in AntiCollisionEngine.METHOD.lower()
    assert "subset" in CasingEngine.METHOD and "TR 5C3" in CasingEngine.METHOD
    assert "connection" not in CasingEngine.METHOD.lower()            # no connection rating is claimed


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_the_kill_sheet_page_shows_training_aid(app):
    from synthetic_operations import make_file_database
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab

    db = make_file_database(Path(tempfile.mkdtemp(prefix="m76-")) / "m76.db")
    tab = EngineeringCalculatorTab(db)
    try:
        assert tab.calculator_finder.open_path("Well Control › Kill Sheet")
        notice = tab.wc_training_notice.text()
        assert notice.startswith("TRAINING AID") and "not an operational kill sheet" in notice
    finally:
        tab.deleteLater()
        app.processEvents()
        db.engine.dispose()
