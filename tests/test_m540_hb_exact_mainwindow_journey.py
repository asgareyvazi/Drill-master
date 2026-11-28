"""M540: real MainWindow journey — a user selects a well, opens W13 hydraulics, runs the exact laminar HB annulus
(M538) through its toolbar entry point, saves the case under the selected well and replays it from Calculation
History (MATCH). Switching wells moves the next dialog to the other well.

SYNTHETIC data only; Linux offscreen Qt (this is not Windows or desktop acceptance).
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_m70_selection_audit import _pump, window  # noqa: E402,F401  (module fixture reused)

INPUTS = {"hole_id_in": 12.25, "pipe_od_in": 2.875, "length_ft": 1000.0, "flow_rate_gpm": 300.0, "density_ppg": 10.0,
          "tau0_lbf_100ft2": 8.0, "k_lbf_sn_100ft2": 0.5, "n_index": 0.6}


def _tab(win, name):
    for i in range(win.tab_widget.count()):
        widget = win.tab_widget.widget(i)
        if type(widget).__name__ == name:
            win.tab_widget.setCurrentWidget(widget)
            _pump(0.3)
            return widget
    raise LookupError(name)


def test_exact_annulus_journey_saves_under_the_selected_well_and_replays(window, monkeypatch):  # noqa: F811
    import PySide6.QtWidgets as qw

    from core import calculation_history as ch
    from core import hydraulics_hb_annulus_exact as ex
    from core.database import CalculationCase
    from core.selection_manager import SelectionManager

    # selecting a well without sections makes the Daily Report tab ask to create one; decline (not under test)
    monkeypatch.setattr(qw.QMessageBox, "question", staticmethod(lambda *a, **k: qw.QMessageBox.No))
    win, db, ids = window
    well, other = ids["alpha"], ids["twin_1"]
    manager = SelectionManager()
    manager.select_well(well, {"id": well, "name": "SYN-ALPHA-01"}, force=True)
    win._targeted_refresh(well, None, None)
    _pump(0.4)
    w13 = _tab(win, "EngineeringCalculatorTab")
    assert w13.current_well_id == well

    dialog = w13.hy_hb_exact_dialog()
    try:
        assert dialog.well_id == well
        for key, value in INPUTS.items():
            dialog.set_value(key, value)
        dialog.run_btn.click()
        _pump(0.1)
        assert dialog.result["status"] == ex.COMPUTED and dialog.result["regime"] == ex.LAMINAR
        assert dialog.save_btn.isEnabled()
        dialog.save_btn.click()
        _pump(0.1)
        case = dialog.saved_case
        assert case is not None
    finally:
        dialog.close()
        dialog.deleteLater()
    with db.session_scope() as session:
        stored = session.get(CalculationCase, case["id"])
        assert stored.well_id == well and stored.method == ex.METHOD_ID
        assert stored.method_version == ex.METHOD_VERSION
    entry = next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case["id"])
    assert ch.recalculate_entry(entry, db)["status"] == "MATCH"

    manager.select_well(other, {"id": other, "name": "SYN-TWIN-01"}, force=True)
    win._targeted_refresh(other, None, None)
    _pump(0.4)
    assert w13.current_well_id == other
    second = w13.hy_hb_exact_dialog()
    try:
        assert second.well_id == other
    finally:
        second.close()
        second.deleteLater()
    _pump(0.1)
