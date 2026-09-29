"""W13 fishing widgets must distinguish missing inputs from screening zero."""
from __future__ import annotations

import pytest


def test_w13_fishing_widgets_start_unknown_and_render_result_status():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # pragma: no cover - requires host Qt libraries
        pytest.skip(f"Qt runtime unavailable: {exc}")

    app = QApplication.instance() or QApplication([])
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab

    widget = EngineeringCalculatorTab()
    try:
        # The real inputs are untouched and therefore explicitly unrecorded;
        # illustrative engineering numbers are not preloaded as actuals.
        assert widget._wc_value(widget.stk_stretch_in) is None
        assert widget.stk_stretch_in.suffix() == " in"
        assert widget._wc_value(widget.stk_wt) is None
        assert widget._wc_value(widget.stk_pull) is None
        assert widget._wc_value(widget.stk_len_m) is None
        assert widget._wc_value(widget.stk_mw_pcf) is None
        assert widget._wc_value(widget.stk_pipe_od) is None
        assert widget._wc_value(widget.stk_pipe_id) is None
        assert widget._wc_value(widget.bo_stretch) is None
        assert widget._wc_value(widget.bo_pipe_wt) is None
        assert "NOT ASSESSED" in widget.stk_free_point.text()
        assert "NOT ASSESSED" in widget.stk_stretch.text()
        assert "NOT ASSESSED" in widget.stk_adj_wt.text()
        assert "NOT ASSESSED" in widget.bo_result.text()
        assert widget._wc_value(widget.bf_mw) is None
        assert widget._wc_value(widget.bf_csg_wt) is None
        assert widget._wc_value(widget.bf_csg_len) is None
        assert widget._wc_value(widget.bf_friction) is None
        assert "NOT ASSESSED" in widget.bf_result.text()

        widget._csg_calc_landing()
        assert widget.bf_result.text().startswith("NOT ASSESSED")
        assert "0.0" not in widget.bf_result.text()

        # An explicit measured zero is not the unrecorded sentinel. The engine
        # may validly produce a zero screening answer only after all inputs are
        # supplied; the failure path remains non-numeric.
        widget.stk_stretch_in.setValue(0)
        widget.stk_wt.setValue(19.5)
        widget.stk_pull.setValue(30000)
        assert widget.stk_free_point.text().startswith("SCREENING ≈ 0.0 ft")
        assert "SCREENING" in widget.stk_free_point.toolTip()

        widget.stk_pull.setValue(0)
        assert widget.stk_free_point.text().startswith("NOT ASSESSED")
        assert "0.0 ft" not in widget.stk_free_point.text()

        # The visible String Stretch inputs are metres and pcf; the adapter
        # converts them to the engine's ft/ppg contract before calculation.
        widget.stk_len_m.setValue(1000)
        widget.stk_mw_pcf.setValue(90)
        assert widget.stk_stretch.text().startswith("SCREENING ≈")
        assert "Legacy free-point/stretch" in widget.stk_stretch.toolTip()

        widget.stk_pipe_od.setValue(5.0)
        widget.stk_pipe_id.setValue(4.276)
        assert widget.stk_adj_wt.text().startswith("SCREENING ≈")

        widget.bo_stretch.setValue(2.5)
        widget.bo_pipe_wt.setValue(22)
        assert widget.bo_result.text().startswith("SCREENING ≈")
        assert "SCREENING" in widget.bo_result.toolTip()

        widget.bf_mw.setValue(90)
        widget.bf_csg_wt.setValue(47)
        widget.bf_csg_len.setValue(10000)
        widget.bf_friction.setValue(0)
        widget._csg_calc_landing()
        assert widget.bf_result.text().startswith("SCREENING — Buoyancy Factor:")
        assert "Simple buoyancy-factor card" in widget.bf_result.toolTip()

        # The nozzle optimizer may use its documented n=1 fallback, but that
        # path must not be indistinguishable from a measured two-point exponent.
        widget.opt_spp2.setValue(0)
        widget._bit_optimize()
        assert "ASSUMED fallback" in widget.opt_results.toPlainText()
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()
