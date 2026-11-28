"""M536-M540: exact laminar Herschel-Bulkley concentric annulus (method m538.hb_annulus_exact).

Expected values are independent of the engine: the Newtonian Lamb (1932) closed form, a Bingham velocity-profile
formulation written out here in closed form (u(x) piecewise, plug continuity solved by its own bisection, flow by
dense trapezoidal integration of u r), the HB parallel-plate closed form for kappa -> 1, and the power-law scale
law Q ~ G^(1/n). SYNTHETIC inputs only. Linux offscreen Qt is not desktop acceptance.
"""
from __future__ import annotations

import inspect
import math
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import calculation_history as ch  # noqa: E402
from core import history_replay as hr  # noqa: E402
from core import hydraulics_hb_annulus_exact as ex  # noqa: E402
from core import hydraulics_hb_slot as hb  # noqa: E402
from core import method_catalogue as mc  # noqa: E402
from tests.test_m73_contracts_history import db  # noqa: E402,F401

BASE = {"hole_id_in": 12.25, "pipe_od_in": 2.875, "length_ft": 1000.0, "flow_rate_gpm": 300.0, "density_ppg": 10.0,
        "tau0_lbf_100ft2": 8.0, "k_lbf_sn_100ft2": 0.5, "n_index": 0.6}


# ---- independent references ------------------------------------------------------------------------------------
def lamb_newtonian(g, ro, kappa, mu):
    ri = kappa * ro
    return math.pi * g / (8 * mu) * (ro ** 4 - ri ** 4 - (ro ** 2 - ri ** 2) ** 2 / math.log(ro / ri))


def bingham_reference(g, ro, kappa, tau0, mu, points=400_001):
    """Bingham annulus from closed-form velocity branches (independent of the engine's shear-rate quadrature)."""
    t = g * ro / 2.0

    def u_out(x, lam2):
        return ro / mu * (t * ((1 - x * x) / 2 + lam2 * np.log(x)) - tau0 * (1 - x))

    def u_in(x, lam2):
        return ro / mu * (t * (lam2 * np.log(x / kappa) - (x * x - kappa * kappa) / 2) - tau0 * (x - kappa))

    def edges(lam2):
        b = tau0 / (2 * t)
        return math.sqrt(b * b + lam2) - b, math.sqrt(b * b + lam2) + b

    lo, hi = kappa * kappa + kappa * tau0 / t, 1 - tau0 / t
    for _ in range(300):
        mid = 0.5 * (lo + hi)
        xm, xp = edges(mid)
        if u_out(xp, mid) - u_in(xm, mid) > 0:
            lo = mid
        else:
            hi = mid
    lam2 = 0.5 * (lo + hi)
    xm, xp = edges(lam2)
    x = np.linspace(kappa, 1.0, points)
    u = np.where(x <= xm, u_in(x, lam2), np.where(x >= xp, u_out(x, lam2), u_out(xp, lam2)))
    f = u * x
    return 2 * math.pi * ro ** 2 * float(np.sum((f[1:] + f[:-1]) * np.diff(x)) / 2), lam2


def hb_parallel_plates(g, ro, kappa, tau0, k, n):
    """HB slot of gap Ro - Ri and width pi (Ro + Ri), closed form (half-gap H, plug half-width tau0 / G)."""
    h = ro * (1 - kappa) / 2
    m = (n + 1) / n
    a = g * h - tau0
    per_width = 2 * n / ((n + 1) * g * k ** (1 / n)) * (h * a ** m - a ** (m + 1) / (g * (m + 1)))
    return per_width * math.pi * ro * (1 + kappa)


# ---- M537 independent cases ------------------------------------------------------------------------------------
@pytest.mark.parametrize("kappa", [0.01, 0.1, 0.3, 0.5, 0.8, 0.95])
def test_newtonian_limit_matches_lamb(kappa):
    assert ex.annulus_flow_rate(1500.0, 0.1, kappa, 0.0, 0.03, 1.0) == pytest.approx(
        lamb_newtonian(1500.0, 0.1, kappa, 0.03), rel=1e-9)


@pytest.mark.parametrize("kappa,tau0", [(0.05, 4.0), (0.2, 8.0), (0.5, 3.0), (0.7, 6.0)])
def test_bingham_matches_closed_form_velocity_reference(kappa, tau0):
    g, ro, mu = 2500.0, 0.1, 0.02
    expected, lam2 = bingham_reference(g, ro, kappa, tau0, mu)
    state = ex.flow_state(g, ro, kappa, tau0, mu, 1.0)
    assert state["lambda2"] == pytest.approx(lam2, rel=1e-9)
    assert state["q"] == pytest.approx(expected, rel=1e-7)


@pytest.mark.parametrize("n", [0.3, 0.6, 1.0])
def test_narrow_annulus_tends_to_the_hb_parallel_plate_solution(n):
    g, ro, kappa, tau0, k = 4.0e5, 0.1, 0.995, 2.0, 0.4
    assert ex.annulus_flow_rate(g, ro, kappa, tau0, k, n) == pytest.approx(
        hb_parallel_plates(g, ro, kappa, tau0, k, n), rel=2e-4)


@pytest.mark.parametrize("n", [0.25, 0.5, 0.8])
def test_power_law_flow_scales_as_gradient_to_one_over_n(n):
    q1 = ex.annulus_flow_rate(1000.0, 0.1, 0.25, 0.0, 0.5, n)
    q2 = ex.annulus_flow_rate(8000.0, 0.1, 0.25, 0.0, 0.5, n)
    assert q2 / q1 == pytest.approx(8.0 ** (1 / n), rel=1e-9)


def test_flow_vanishes_at_the_yield_onset_and_increases_monotonically():
    ro, kappa, tau0 = 0.1, 0.4, 5.0
    onset = 2 * tau0 / (ro * (1 - kappa))
    assert ex.annulus_flow_rate(onset * 0.999, ro, kappa, tau0, 0.3, 0.7) == 0.0
    qs = [ex.annulus_flow_rate(onset * f, ro, kappa, tau0, 0.3, 0.7) for f in (1.001, 1.01, 1.1, 2.0, 10.0)]
    assert qs[0] > 0 and all(b > a for a, b in zip(qs, qs[1:]))


def test_solve_gradient_inverts_the_flow_rate():
    g = ex.solve_gradient(0.01, 0.12, 0.2, 4.0, 0.4, 0.55)
    assert ex.annulus_flow_rate(g, 0.12, 0.2, 4.0, 0.4, 0.55) == pytest.approx(0.01, rel=1e-10)


def test_agrees_with_m416_slot_in_its_narrow_laminar_range_and_m416_is_unchanged():
    """Cross-hydraulics consistency (laminar): the slot approximation approaches the exact solution as kappa -> 1."""
    gaps = []
    for kappa in (0.3, 0.6, 0.9):
        case = {**BASE, "hole_id_in": 10.0, "pipe_od_in": 10.0 * kappa, "flow_rate_gpm": 150.0}
        exact = ex.evaluate(case)
        slot = hb.evaluate({**case, "roughness_in": 0.0, "transition_criterion": "founargiotakis-2008"})
        assert exact["regime"] == ex.LAMINAR and slot["regime"] == "LAMINAR"
        gaps.append(abs(exact["gradient_psi_ft"] / slot["gradient_psi_ft"] - 1))
    assert gaps[0] < 0.03 and gaps[1] < gaps[0] and gaps[2] < 1e-3
    assert hb.METHOD_ID == "m416.hb_slot_annulus" and hb.KAPPA_MIN == 0.3


def test_wide_annulus_refused_by_m416_is_computed_here():
    slot = hb.evaluate({**BASE, "roughness_in": 0.0, "transition_criterion": "founargiotakis-2008"})
    assert slot["status"] != "COMPUTED"
    result = ex.evaluate(BASE)
    assert result["status"] == ex.COMPUTED and result["regime"] == ex.LAMINAR
    assert result["kappa"] == pytest.approx(2.875 / 12.25)
    assert result["plug_inner_radius_in"] < result["zero_shear_radius_in"] < result["plug_outer_radius_in"]
    assert 2.875 / 2 < result["plug_inner_radius_in"] and result["plug_outer_radius_in"] < 12.25 / 2
    tau_w = result["wall_shear_mean_lbf_100ft2"]
    assert tau_w > BASE["tau0_lbf_100ft2"]
    # psi/ft from the mean wall shear (force balance) - independent unit path
    assert result["gradient_psi_ft"] == pytest.approx(4 * tau_w / 100 / 144 / ((12.25 - 2.875) / 12) / 12 * 12,
                                                      rel=1e-9)


# ---- refusals ----------------------------------------------------------------------------------------------------
def test_turbulent_or_transitional_flow_is_not_assessed():
    result = ex.evaluate({**BASE, "hole_id_in": 8.5, "pipe_od_in": 5.0, "flow_rate_gpm": 900.0,
                          "tau0_lbf_100ft2": 1.0, "k_lbf_sn_100ft2": 0.02})
    assert result["status"] == ex.NOT_ASSESSED and "laminar only" in result["reason"]
    assert "pressure_loss_psi" not in result


@pytest.mark.parametrize("change,needle", [({"n_index": 1.2}, "flow index"), ({"n_index": 0.05}, "flow index"),
                                           ({"pipe_od_in": 12.2}, "diameter ratio"),
                                           ({"pipe_od_in": 0.1}, "diameter ratio"),
                                           ({"density_ppg": None}, "missing")])
def test_out_of_range_or_missing_inputs_are_not_assessed(change, needle):
    result = ex.evaluate({**BASE, **change})
    assert result["status"] == ex.NOT_ASSESSED and needle in result["reason"]


@pytest.mark.parametrize("change", [{"pipe_od_in": 12.25}, {"pipe_od_in": 13.0}, {"length_ft": 0.0},
                                    {"flow_rate_gpm": -1.0}, {"tau0_lbf_100ft2": -0.1}, {"k_lbf_sn_100ft2": 0.0},
                                    {"density_ppg": float("nan")}, {"n_index": True}, {"hole_id_in": "abc"}])
def test_invalid_inputs_are_refused(change):
    with pytest.raises(ex.AnnulusError):
        ex.evaluate({**BASE, **change})


def test_unknown_inputs_are_refused():
    with pytest.raises(ex.AnnulusError):
        ex.evaluate({**BASE, "eccentricity": 0.5})


def test_zero_flow_is_zero_loss_with_the_onset_reported_separately():
    result = ex.evaluate({**BASE, "flow_rate_gpm": 0.0})
    assert result["status"] == ex.COMPUTED and result["regime"] == ex.NO_FLOW and result["pressure_loss_psi"] == 0.0
    expected_onset = 4 * 8.0 / 100 / 144 * 1000 / ((12.25 - 2.875) / 12)
    assert result["yield_onset_psi"] == pytest.approx(expected_onset, rel=1e-9)


# ---- M538 contract, persistence, replay ----------------------------------------------------------------------------
def test_contract_catalogue_and_units():
    assert ex.METHOD_ID == "m538.hb_annulus_exact" and ex.METHOD_ID in hr.SERVICE_MODULES
    entry = next(e for e in mc.catalogue() if e.method_id == ex.METHOD_ID)
    assert entry.version == ex.METHOD_VERSION and "Laminar only" in entry.limits
    for key, unit in ex.RESULT_FIELDS:
        assert hr._unit_of(ex.METHOD_ID, key) == unit and unit in hr.FIELD_TOLERANCES
    assert "COMPLETE" not in ex.LABEL and "APPROVED" not in ex.LABEL and "SCREENING" in ex.LABEL
    assert "save_case" in dir(ex) and "well_id" in inspect.signature(ex.save_case).parameters


def test_save_and_replay_match_and_tamper_is_refused(db):  # noqa: F811
    result = ex.evaluate(BASE)
    case = ex.save_case(db, result, well_id=db.test_well_id)
    entry = next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case["id"])
    assert ch.recalculate_entry(entry, db)["status"] == "MATCH"
    inputs, _results = ex.case_payload(result)
    inputs["flow_rate_gpm"]["value"] = 301.0
    with pytest.raises(ex.IntegrityError):
        ex.replay_results(inputs)


def test_not_assessed_results_are_not_saved(db):  # noqa: F811
    with pytest.raises(ValueError):
        ex.save_case(db, ex.evaluate({**BASE, "n_index": 2.0}), well_id=db.test_well_id)


def test_w13_exact_annulus_dialog_runs_saves_and_replays(db):  # noqa: F811
    from PySide6 import QtWidgets
    from PySide6.QtCore import QCoreApplication, QEvent

    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tab = EngineeringCalculatorTab(db)
    dialog = None
    try:
        tab.on_well_changed(db.test_well_id, {"name": "SYN-C-01"})
        dialog = tab.hy_hb_exact_dialog()
        assert dialog.findChild(QtWidgets.QLabel, "m538_banner") is not None
        assert all(not edit.text() for edit in dialog.edits.values())                  # nothing is defaulted
        assert "roughness_in" not in dialog.edits and not dialog.combos
        first = dialog.run()
        assert first["status"] == ex.NOT_ASSESSED and not dialog.save_btn.isEnabled()
        for key, value in BASE.items():
            dialog.set_value(key, value)
        result = dialog.run()
        assert result["regime"] == ex.LAMINAR and "exact concentric-annulus" in dialog.summary.text()
        case = dialog.save()
        entry = next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case["id"])
        assert ch.recalculate_entry(entry, db)["status"] == "MATCH"
        dialog.set_value("pipe_od_in", 13.0)
        assert dialog.run() is None and "Not run" in dialog.summary.text()
    finally:
        if dialog is not None:
            dialog.deleteLater()
        tab.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


def test_w13_handler_holds_no_formula():
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab

    src = inspect.getsource(EngineeringCalculatorTab.hy_hb_exact_dialog)
    assert 'well_id=getattr(self, "current_well_id", None)' in src
    assert "math." not in src and "**" not in src
