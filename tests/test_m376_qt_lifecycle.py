"""M376: Qt lifecycle of the M361-M400 dialogs - each is parented to the page that opened it and is destroyed with it.

The dialogs open non-modally (3D view) or modally (W13); either way the C++ object must not outlive its page, and the
layer panel's background job must be shut down (never terminated) before the panel goes. Offscreen Qt, SYNTHETIC.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shiboken6  # noqa: E402
from PySide6 import QtWidgets  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402

from tests.test_m368_survey_plan_deviation import env  # noqa: E402,F401
from tests.test_m73_contracts_history import db  # noqa: E402,F401


def _flush(app):
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_deviation_dialog_dies_with_the_layer_panel_and_the_job_is_shut_down(app, env):  # noqa: F811
    from tabs.trajectory_layers_panel import TrajectoryLayersPanel

    panel = TrajectoryLayersPanel(db_manager=env["manager"])
    panel.set_scope(env["well"], env["bore"])
    assert panel.wait()
    panel.select(base=env["survey"]["id"], plan=env["plan"]["id"])
    assert panel.wait()
    panel.deviation_btn.click()
    dialog = panel.deviation_dialog
    assert dialog.parent() is panel and dialog.isVisible()
    assert panel.shutdown() and panel.jobs.state != "LOADING"
    panel.deleteLater()
    _flush(app)
    assert not shiboken6.isValid(dialog) and not shiboken6.isValid(panel)


def test_w13_dialogs_are_parented_to_the_tab_and_die_with_it(app, db):  # noqa: F811
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab
    from tests.test_m366_hydraulics_workflow import _fill

    tab = EngineeringCalculatorTab(db)
    _fill(tab)
    hydraulics = tab.hy_workflow_dialog()
    casing = tab.csg_axial_loads_dialog()
    assert hydraulics.parent() is tab and casing.parent() is tab
    hydraulics.close()
    casing.close()
    tab.deleteLater()
    _flush(app)
    assert not shiboken6.isValid(hydraulics) and not shiboken6.isValid(casing) and not shiboken6.isValid(tab)


def test_reopening_creates_a_fresh_dialog_and_the_old_one_can_be_released(app, db):  # noqa: F811
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab

    tab = EngineeringCalculatorTab(db)
    try:
        first = tab.csg_axial_loads_dialog()
        first.deleteLater()
        _flush(app)
        second = tab.csg_axial_loads_dialog()
        assert not shiboken6.isValid(first) and shiboken6.isValid(second) and second.result is None
        second.deleteLater()
    finally:
        tab.deleteLater()
        _flush(app)
