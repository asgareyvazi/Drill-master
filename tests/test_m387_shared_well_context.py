"""M387: the M366 / M371 / M372 / M373 W13 workflows share the tab's well context.

A dialog takes the well selected when it opens, a case saved from it is attributed to that well (and listed under
it), a well change applies to the next dialog only (an open dialog keeps the well it was opened for - its inputs were
frozen for that well), and after the selection is cleared a new dialog carries no well. SYNTHETIC, offscreen Qt.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402

from core import calculation_cases as cc  # noqa: E402
from tests.test_m73_contracts_history import db  # noqa: E402,F401
from tests.test_m372_mse_drilloff import PARAMS, STEPS  # noqa: E402
from tests.test_m373_volumetric_method import BASE  # noqa: E402

OPENERS = ("csg_axial_loads_dialog", "mse_drilloff_dialog", "wc_volumetric_dialog",
           # M418 / M421 / M423 / M427 service dialogs
           "hy_hb_slot_dialog", "hy_surge_hb_dialog", "drilloff_fitted_dialog", "dull_grade_dialog")


def _fill_m373(dialog):
    for key, value in BASE.items():
        dialog.edits[key].setText(f"{value:g}")


def _fill_m372(dialog):
    for key, value in PARAMS.items():
        dialog.edits[key].setText(f"{value:g}")
    for row, step in enumerate(STEPS):
        dialog.set_step(row, step)


def test_dialogs_follow_the_selected_well_and_cases_are_attributed_to_it(db):  # noqa: F811
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab
    from tests.test_m366_hydraulics_workflow import _fill

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tab = EngineeringCalculatorTab(db)
    well = db.test_well_id
    try:
        tab.on_well_changed(well, {"name": "SYN-C-01"})
        _fill(tab)
        opened = [getattr(tab, name)() for name in OPENERS] + [tab.hy_workflow_dialog()]
        assert [d.well_id for d in opened] == [well] * (len(OPENERS) + 1)
        volumetric, drilloff = opened[2], opened[1]
        _fill_m373(volumetric)
        _fill_m372(drilloff)
        assert volumetric.run() and drilloff.run()
        tab.on_well_changed(None, {})                                 # the selection moves on ...
        cases = [volumetric.save(), drilloff.save()]                  # ... an open dialog keeps its frozen well
        assert [c["well_id"] for c in cases] == [well, well]
        listed = {c["id"] for c in cc.list_cases(db, well_id=well)}
        assert {c["id"] for c in cases} <= listed
        tab.on_well_changed(well, {"name": "SYN-C-01"})
        tab._on_selection_cleared_internal()
        tab.on_selection_cleared()
        fresh = [getattr(tab, name)() for name in OPENERS]
        assert [d.well_id for d in fresh] == [None] * len(OPENERS)
        _fill_m373(fresh[2])
        assert fresh[2].run() and fresh[2].save()["well_id"] is None
        for dialog in opened + fresh:
            dialog.deleteLater()
    finally:
        tab.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
