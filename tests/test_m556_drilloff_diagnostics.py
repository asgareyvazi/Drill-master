"""M556-M560: diagnostics of the M475 robust drill-off fit (uniqueness, flat interval, leave-one-out, leverage, warnings).

INDEPENDENT expected values (SYNTHETIC): the hinge each case is built on, a hand-derived L1 tie (null vector of the
hinge design), and leverage recomputed by QR. M475 results, stored case payload and replay must be unchanged.
"""
from __future__ import annotations

import copy
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import calculation_history as ch  # noqa: E402
from core import drilloff_diagnostics as dd  # noqa: E402
from core import drilloff_robust as dr  # noqa: E402
from tests.test_m475_drilloff_robust import PARAMS, WOBS, knee26, steps  # noqa: E402
from tests.test_m73_contracts_history import db  # noqa: E402,F401


def _fit(**kw):
    params = dict(PARAMS)
    params.update(kw.pop("params", {}))
    return dr.evaluate(params, steps(**kw))


def test_exact_hinge_is_unique_stable_and_only_warns_about_the_surface_basis():
    r = _fit()
    d = dd.diagnose(r)
    assert d["uniqueness"] == dd.UNIQUE and d["tied_optima"][0] == pytest.approx([0.0, 4.0, -3.6], abs=1e-9)
    assert d["max_loo_shift_klbf"] == pytest.approx(0.0, abs=1e-9) and d["loo_decision_flips_wob_klbf"] == []
    assert d["flat_interval_wob_klbf"] == pytest.approx([26.0, 26.0])
    assert d["warnings"] == ["WOB basis is surface: the founder WOB is a surface value, not downhole WOB"]
    down = dd.diagnose(_fit(params={"wob_basis": "downhole"}))
    assert down["warnings"] == []


def test_l1_tie_is_reported_not_unique():
    # design rows (1, x, max(x - 1.5, 0)) for x = 0..3 have the null vector (-1, 3, -3, 1): a bump at x = 0 ties the
    # fit through x = 1, 2, 3 (residual 4 at x = 0) with the fit through x = 0, 1, 2 (residual -4 x 1/1 at x = 3)
    xs = [0.0, 1.0, 2.0, 3.0]
    ys = [0.0 + 4.0, 2.0, 3.25, 3.75]
    optima = dd.tied_optima(xs, ys, 1.5)
    assert len(optima) == 2
    assert dd.tied_optima(xs, [0.0, 2.0, 3.25, 3.75], 1.5) == [pytest.approx([0.0, 2.0, -1.5])]

    crafted = {"status": dr.COMPUTED, "fitted_breakpoint_wob_klbf": 1.5, "founder_status": dr.FOUNDER,
               "wob_basis": "downhole", "flagged_wob_klbf": [],
               "inputs": {"slope_ratio": 0.5, "steps": [{"wob_klbf": x, "rpm": 120.0, "rop_ft_hr": y}
                                                         for x, y in zip(xs, ys)]}}
    d = dd.diagnose(crafted)
    assert d["uniqueness"] == dd.NON_UNIQUE
    assert "the L1 optimum is not unique (2 tied fits at the breakpoint)" in d["warnings"]


def test_straight_line_is_flat_over_the_whole_search_range():
    line = dr.evaluate(PARAMS, steps(fn=lambda w: 5 + 3 * w))
    d = dd.diagnose(line)
    assert d["flat_interval_wob_klbf"] == [WOBS[1], WOBS[-2]]
    assert any("weakly identified over 12-40 klbf" in line_ for line_ in dr.summary_lines(line))


def test_leverage_matches_an_independent_qr_projection():
    r = _fit()
    x = np.asarray(sorted(WOBS))
    q, _ = np.linalg.qr(np.column_stack([np.ones_like(x), x, np.maximum(x - 26.0, 0.0)]))
    assert dd.diagnose(r)["leverage"] == pytest.approx(list((q ** 2).sum(axis=1)), abs=1e-12)
    assert sum(dd.diagnose(r)["leverage"]) == pytest.approx(3.0)            # trace of a rank-3 projection


def test_high_leverage_step_is_warned():
    wobs = (8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 60.0)                   # one isolated far WOB step
    d = dd.diagnose(dr.evaluate(PARAMS, steps(fn=lambda w: 2 + 3 * w if w <= 12 else 38 + 0.3 * (w - 12),
                                              wobs=wobs)))
    assert 60.0 in d["high_leverage_wob_klbf"]
    assert any("high-leverage step(s) at WOB 60" in w for w in d["warnings"])


def test_outlier_case_reports_flag_and_leave_one_out_sensitivity():
    d = dd.diagnose(_fit(bumps={16.0: 40.0}))
    assert any("residuals flagged at WOB 16" in w for w in d["warnings"])
    assert d["max_loo_shift_klbf"] > 4.0                                     # more than one 4 klbf step
    assert any("leave-one-out moves the breakpoint" in w for w in d["warnings"])


def test_edge_and_few_steps_above_warnings():
    d = dd.diagnose(dr.evaluate(PARAMS, steps(fn=lambda w: 4 * w if w <= 13 else 52 + 0.4 * (w - 13))))
    assert any("search edge" in w for w in d["warnings"])
    d = dd.diagnose(dr.evaluate(PARAMS, steps(fn=lambda w: 4 * w if w <= 38 else 152 + 0.4 * (w - 38))))
    assert any("fewer than three steps beyond" in w for w in d["warnings"])


def test_not_computed_result_has_no_diagnostics():
    r = dr.evaluate(PARAMS, steps()[:4])
    assert r["status"] == dr.NOT_ASSESSED
    assert dd.diagnose(r)["status"] == "NOT ASSESSED" and dd.summary_lines(r) == []


def test_m475_results_payload_and_replay_are_unchanged(db):  # noqa: F811
    r = _fit(bumps={16.0: 40.0})
    snapshot = copy.deepcopy(r)
    dd.diagnose(r)
    assert r == snapshot                                                    # read-only
    inputs, results = dr.case_payload(r)
    assert not any("diagnos" in k or "leave" in k for k in list(inputs) + list(results))
    assert dr.METHOD_VERSION == "M475 drill-off founder, least-absolute-deviations two-segment line v1"
    case = dr.save_case(db, r, well_id=db.test_well_id)
    entry = next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case["id"])
    assert ch.recalculate_entry(entry, db)["status"] == "MATCH"
    assert knee26(26.0) == 104.0


def test_w13_dialog_shows_the_diagnostics(db):  # noqa: F811
    from PySide6 import QtWidgets
    from PySide6.QtCore import QCoreApplication, QEvent

    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tab = EngineeringCalculatorTab(db)
    dialog = None
    try:
        tab.on_well_changed(db.test_well_id, {"name": "SYN-C-01"})
        dialog = tab.drilloff_robust_dialog()
        dialog.set_value("rpm_tolerance_rpm", 5.0)
        dialog.set_value("slope_ratio", 0.5)
        dialog.set_value("wob_basis", "surface")
        for row, step in enumerate(steps(bumps={16.0: 40.0})):
            dialog.set_row(row, step)
        dialog.run()
        text = dialog.summary.text()
        assert "Diagnostics (M556 drill-off L1 diagnostics v1, not stored, recomputed)" in text
        assert "WARNING: leave-one-out moves the breakpoint" in text
    finally:
        if dialog is not None:
            dialog.deleteLater()
        tab.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
