"""M415-M427: R-HYD-2 HB slot annulus, quasi-steady surge/swab, fitted drill-off, CCI case field, IADC dull grade.

INDEPENDENT golden values (input class: SYNTHETIC). Every expected number below comes from a closed form or a numerical
procedure written in this file - never from the production modules:

* Plane Poiseuille (Newtonian slot): dp/dx = 12 mu V / H^2, H = (Do - Di)/2.
* Power-law slot: tau_w = K ((2n+1) V / (n h))^n with h = H/2; dp/dx = tau_w / h.
* Bingham slot (Buckingham form): V = tau_w h / (3 mu) (1 - 3/2 xi + 1/2 xi^3), xi = tau0 / tau_w (bisection here).
* Herschel-Bulkley slot: mean velocity by Simpson quadrature of V = (1/h) int_0^h y gamma(y) dy, gamma from
  tau(y) = tau_w y / h (numerical, not the closed form of the module), then bisection on tau_w.
* Exact concentric annulus (Newtonian): Q = pi G / (8 mu) [ro^4 - ri^4 - (ro^2 - ri^2)^2 / ln(ro/ri)].
* Colebrook: the implicit equation's residual at the module's factor; Moody value f_D(Re 1e5, smooth) = 0.0180 (2 sf).
* Couette-Poiseuille closed-end surge (Newtonian slot, wall moving at v_p): dp/dx = 12 mu (V_f + v_p / 2) / H^2, i.e.
  the Burkhardt clinging constant 0.5 is exact for a Newtonian laminar slot.
* Drill-off: data constructed on an exact hinge (slopes 4 and 0.4 ft/h/klbf, break 22.5 klbf).
Unit factors are exact definitions (in 0.0254 m, ft 0.3048 m, US gal 3.785411784 L, lbf 4.4482216152605 N).
"""
from __future__ import annotations

import copy
import dataclasses
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import bit_dull_grade as dg  # noqa: E402
from core import calculation_history as ch  # noqa: E402
from core import drilloff_fitted as df  # noqa: E402
from core import history_replay as hr  # noqa: E402
from core import hydraulics_hb_slot as hb  # noqa: E402
from core import surge_swab as ss  # noqa: E402
from tests.test_m73_contracts_history import db  # noqa: E402,F401

IN, FT = 0.0254, 0.3048
GPM = 3.785411784e-3 / 60.0
PPG = 3.785411784e-3 ** -1 * 0.45359237                # kg/m3 per ppg
LBF = 4.4482216152605
HBU = LBF / (100.0 * FT ** 2)                          # Pa per lbf/100 ft2
PSI = LBF / IN ** 2


def base(**over):
    values = {"hole_id_in": 8.5, "pipe_od_in": 5.0, "length_ft": 10000.0, "flow_rate_gpm": 300.0,
              "density_ppg": 10.0, "tau0_lbf_100ft2": 8.0, "k_lbf_sn_100ft2": 1.2, "n_index": 0.6,
              "roughness_in": 0.0018, "transition_criterion": "founargiotakis-2008"}
    values.update(over)
    return values


def _geometry(do_in=8.5, di_in=5.0, q_gpm=300.0):
    gap = (do_in - di_in) / 2 * IN
    area = math.pi / 4 * ((do_in * IN) ** 2 - (di_in * IN) ** 2)
    return gap, q_gpm * GPM / area


def _psi(gradient_pa_m, length_ft=10000.0):
    return gradient_pa_m * length_ft * FT / PSI


def _bisect(f, lo, hi, it=200):
    for _ in range(it):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
    return 0.5 * (lo + hi)


def _hb_quadrature_velocity(tau_w, tau0, k, n, h, m=4000):
    """Mean slot velocity by Simpson quadrature (independent of the module's closed form)."""
    def gamma(y):
        tau = tau_w * y / h
        return ((tau - tau0) / k) ** (1 / n) if tau > tau0 else 0.0
    step = h / m
    total = gamma(0) * 0 + h * gamma(h)
    for i in range(1, m):
        y = i * step
        total += (4 if i % 2 else 2) * y * gamma(y)
    return total * step / 3 / h


# ---- M416 / M417: R-HYD-2 -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("q", [50.0, 250.0, 380.0])
def test_newtonian_laminar_equals_plane_poiseuille(q):
    mu = 0.060                                                        # Pa s (Re_G < 2100 up to ~450 gpm here)
    r = hb.evaluate(base(flow_rate_gpm=q, tau0_lbf_100ft2=0.0, k_lbf_sn_100ft2=mu / HBU, n_index=1.0))
    gap, v = _geometry(q_gpm=q)
    assert r["regime"] == hb.LAMINAR and r["n_prime"] == pytest.approx(1.0, abs=1e-9)
    assert r["pressure_loss_psi"] == pytest.approx(_psi(12 * mu * v / gap ** 2), rel=1e-9)


def test_power_law_laminar_equals_the_closed_form():
    k_pa, n = 0.9, 0.55
    r = hb.evaluate(base(tau0_lbf_100ft2=0.0, k_lbf_sn_100ft2=k_pa / HBU, n_index=n))
    gap, v = _geometry()
    h = gap / 2
    tau_w = k_pa * ((2 * n + 1) * v / (n * h)) ** n
    assert r["regime"] == hb.LAMINAR and r["n_prime"] == pytest.approx(n, rel=1e-9)
    assert r["pressure_loss_psi"] == pytest.approx(_psi(tau_w / h), rel=1e-9)


def test_bingham_laminar_equals_the_buckingham_slot_form():
    mu, tau0 = 0.025, 6.0                                             # Pa s, Pa
    r = hb.evaluate(base(tau0_lbf_100ft2=tau0 / HBU, k_lbf_sn_100ft2=mu / HBU, n_index=1.0, flow_rate_gpm=250.0))
    gap, v = _geometry(q_gpm=250.0)
    h = gap / 2
    tau_w = _bisect(lambda t: t * h / (3 * mu) * (1 - 1.5 * tau0 / t + 0.5 * (tau0 / t) ** 3) - v, tau0, 1e4)
    assert r["regime"] == hb.LAMINAR
    assert r["pressure_loss_psi"] == pytest.approx(_psi(tau_w / h), rel=1e-8)


@pytest.mark.parametrize("tau0_u,k_u,n,q", [(8.0, 1.2, 0.6, 400.0), (15.0, 0.4, 0.75, 200.0), (3.0, 3.0, 0.35, 120.0)])
def test_herschel_bulkley_laminar_equals_numerical_quadrature(tau0_u, k_u, n, q):
    tau0, k = tau0_u * HBU, k_u * HBU
    r = hb.evaluate(base(tau0_lbf_100ft2=tau0_u, k_lbf_sn_100ft2=k_u, n_index=n, flow_rate_gpm=q))
    gap, v = _geometry(q_gpm=q)
    h = gap / 2
    tau_w = _bisect(lambda t: _hb_quadrature_velocity(t, tau0, k, n, h) - v, tau0 * (1 + 1e-12), 1e4, it=80)
    assert r["regime"] == hb.LAMINAR
    assert r["pressure_loss_psi"] == pytest.approx(_psi(tau_w / h), rel=2e-5)
    assert r["re_generalised"] == pytest.approx(12 * 10.0 * PPG * v ** 2 / tau_w, rel=2e-5)


def test_the_slot_idealisation_bound_holds_and_wide_annuli_are_refused():
    for kappa in (0.3, 0.5, 0.7):
        ro, ri = 1.0, kappa
        exact = math.pi / 8 * (ro ** 4 - ri ** 4 - (ro ** 2 - ri ** 2) ** 2 / math.log(ro / ri))
        slot = math.pi * (ro + ri) * (ro - ri) ** 3 / 12
        assert abs(slot / exact - 1) < 0.025                          # the docstring's stated < 2.5 % at kappa >= 0.3
    r = hb.evaluate(base(hole_id_in=17.5, pipe_od_in=5.0))          # kappa 0.286
    assert r["status"] == hb.NOT_ASSESSED and "narrow-slot" in r["reason"]


def test_turbulent_newtonian_uses_colebrook_on_the_hydraulic_diameter():
    mu = 0.002
    r = hb.evaluate(base(tau0_lbf_100ft2=0.0, k_lbf_sn_100ft2=mu / HBU, n_index=1.0, flow_rate_gpm=800.0))
    gap, v = _geometry(q_gpm=800.0)
    dh = 2 * gap
    re = 10.0 * PPG * v * dh / mu
    assert r["regime"] == hb.TURBULENT and r["re_generalised"] == pytest.approx(re, rel=1e-9)
    fd = r["colebrook_darcy"]
    residual = 1 / math.sqrt(fd) + 2 * math.log10(0.0018 * IN / dh / 3.7 + 2.51 / (re * math.sqrt(fd)))
    assert abs(residual) < 1e-9 and r["fanning_friction"] == pytest.approx(fd / 4, rel=1e-12)
    assert r["pressure_loss_psi"] == pytest.approx(_psi(2 * (fd / 4) * 10.0 * PPG * v ** 2 / dh), rel=1e-9)
    smooth, _it = hb.colebrook_darcy(1e5, 0.0)
    assert smooth == pytest.approx(0.0180, abs=5e-5)                 # Moody chart, smooth pipe


def test_transition_bands_match_the_published_equations_and_blend_linearly():
    assert hb.transition_band("founargiotakis-2008", 0.5, 0.6) == pytest.approx((2675.0, 3575.0))
    re1 = 2100 * 0.3 ** 0.331 * (1 + 1.402 * 0.5 - 0.977 * 0.25)
    assert hb.transition_band("erge-2015", 0.3, 0.5) == pytest.approx((re1, 2900 * 0.3 ** (-0.039 * re1 ** 0.307)))
    mu = 0.020                                                        # Newtonian: Re1 2100, Re2 3000
    for q in (160.0, 180.0, 200.0):
        r = hb.evaluate(base(tau0_lbf_100ft2=0.0, k_lbf_sn_100ft2=mu / HBU, n_index=1.0, flow_rate_gpm=q))
        if r["regime"] == hb.TRANSITIONAL:
            gap, v = _geometry(q_gpm=q)
            re = 10.0 * PPG * v * 2 * gap / mu
            fd, _ = hb.colebrook_darcy(3000.0, 0.0018 * IN / (2 * gap))
            expected = 24 / 2100 + (fd / 4 - 24 / 2100) * (re - 2100) / 900
            assert r["fanning_friction"] == pytest.approx(expected, rel=1e-9)
            assert any("< 4000" in w for w in r["warnings"])
            break
    else:
        pytest.fail("no transitional point in the sweep")


def test_zero_missing_and_invalid_inputs_are_never_guessed():
    r = hb.evaluate(base(flow_rate_gpm=0.0))
    assert r["regime"] == hb.NO_FLOW and r["pressure_loss_psi"] == 0.0
    assert r["yield_onset_psi"] == pytest.approx(_psi(4 * 8.0 * HBU / (3.5 * IN)), rel=1e-12)
    assert hb.evaluate(base(tau0_lbf_100ft2=None))["status"] == hb.NOT_ASSESSED
    assert hb.evaluate(base(transition_criterion=None))["status"] == hb.NOT_ASSESSED
    assert hb.evaluate(base(n_index=1.2))["status"] == hb.NOT_ASSESSED
    for bad in (dict(flow_rate_gpm=float("nan")), dict(density_ppg=float("inf")), dict(pipe_od_in=9.0),
                dict(length_ft=0.0), dict(transition_criterion="api-13d")):
        with pytest.raises(ValueError):
            hb.evaluate(base(**bad))
    r = hb.evaluate(base(n_index=0.3, transition_criterion="erge-2015", flow_rate_gpm=700.0))
    assert r["status"] == hb.NOT_ASSESSED and "fitted only" in r["reason"]


def test_no_duplicate_hb_solver_and_the_page_engine_still_refuses_hb():
    import inspect

    from core import hydraulics_engine, w13_hydraulics

    for module in (hydraulics_engine, w13_hydraulics):
        src = inspect.getsource(module)
        assert "colebrook" not in src.lower() and "slot_velocity" not in src
    assert "unsupported" in inspect.getsource(hydraulics_engine.AdvancedHydraulicsEngine).lower()


# ---- M420 / M421: surge / swab ------------------------------------------------------------------------------------
def ss_inputs(**over):
    values = {"trip_speed_ft_min": 60.0, "clinging_constant": 0.5, "density_ppg": 10.0, "tau0_lbf_100ft2": 0.0,
              "k_lbf_sn_100ft2": 0.020 / HBU, "n_index": 1.0, "roughness_in": 0.0, "tvd_ft": 10000.0,
              "transition_criterion": "founargiotakis-2008", "pipe_end": "closed"}
    values.update(over)
    return values


SECTIONS = [{"hole_id_in": 8.5, "pipe_od_in": 5.0, "length_ft": 6000.0},
            {"hole_id_in": 8.5, "pipe_od_in": 6.5, "length_ft": 600.0}]


def test_closed_end_newtonian_surge_equals_couette_poiseuille_at_kc_half():
    r = ss.evaluate(ss_inputs(), SECTIONS)
    vp = 60.0 * FT / 60.0
    total = 0.0
    for sec in SECTIONS:
        do, di = sec["hole_id_in"] * IN, sec["pipe_od_in"] * IN
        gap = (do - di) / 2
        vf = vp * di ** 2 / (do ** 2 - di ** 2)
        total += _psi(12 * 0.020 * (vf + vp / 2) / gap ** 2, sec["length_ft"])
    assert r["status"] == ss.COMPUTED and r["surge_psi"] == pytest.approx(total, rel=1e-9)
    assert r["swab_psi"] == r["surge_psi"]
    delta = total / (0.052 * 10000.0)
    assert r["surge_emw_ppg"] == pytest.approx(10.0 + delta, rel=1e-3)        # 0.052 is the rounded field constant
    assert r["swab_emw_ppg"] == pytest.approx(10.0 - delta, rel=1e-3)
    assert {row["regime"] for row in r["sections"]} == {hb.LAMINAR}


def test_surge_refusals_open_end_partial_sections_and_no_tvd():
    assert ss.evaluate(ss_inputs(pipe_end="open"), SECTIONS)["status"] == ss.NOT_ASSESSED
    assert ss.evaluate(ss_inputs(pipe_end=None), SECTIONS)["status"] == ss.NOT_ASSESSED
    partial = [SECTIONS[0], {"hole_id_in": 8.5, "pipe_od_in": None, "length_ft": 600.0}]
    r = ss.evaluate(ss_inputs(), partial)
    assert r["status"] == ss.NOT_ASSESSED and "partial sum is not a total" in r["reason"]
    wide = [SECTIONS[0], {"hole_id_in": 17.5, "pipe_od_in": 5.0, "length_ft": 600.0}]       # kappa 0.286
    r = ss.evaluate(ss_inputs(), wide)
    assert r["status"] == ss.NOT_ASSESSED and r.get("surge_psi") is None
    assert "section 2" in r["reason"] and "partial sum is not a total" in r["reason"]
    r = ss.evaluate(ss_inputs(tvd_ft=None), SECTIONS)
    assert r["status"] == ss.COMPUTED and r["surge_emw_ppg"] is None and "no TVD" in r["emw_reason"]
    r = ss.evaluate(ss_inputs(trip_speed_ft_min=0.0), SECTIONS)
    assert r["surge_psi"] == 0.0
    for bad in (dict(clinging_constant=1.5), dict(trip_speed_ft_min=-5.0), dict(tvd_ft=0.0)):
        with pytest.raises(ValueError):
            ss.evaluate(ss_inputs(**bad), SECTIONS)
    assert "quasi-steady" in ss.LABEL.lower() and "no transient" in ss.LABEL.lower()


# ---- M423 / M424: fitted drill-off --------------------------------------------------------------------------------
WOBS = (10.0, 15.0, 20.0, 25.0, 30.0, 35.0)


def _hinge(w):
    return 4 * w if w <= 22.5 else 90 + 0.4 * (w - 22.5)


DF_PARAMS = {"rpm_tolerance_rpm": 5.0, "slope_ratio": 0.5}


def _steps(fn=_hinge, wobs=WOBS, rpm=120.0):
    return [{"wob_klbf": w, "rpm": rpm, "rop_ft_hr": fn(w)} for w in wobs]


def test_the_fit_recovers_an_exact_hinge():
    r = df.evaluate(DF_PARAMS, _steps())
    assert r["founder_status"] == df.FOUNDER
    assert r["breakpoint_wob_klbf"] == pytest.approx(22.5, abs=1e-6)
    assert r["slope_below"] == pytest.approx(4.0, abs=1e-9) and r["slope_above"] == pytest.approx(0.4, abs=1e-9)
    assert r["sse"] == pytest.approx(0.0, abs=1e-12) and r["r_squared"] == pytest.approx(1.0)


def test_linear_data_has_no_founder_and_m372_is_untouched():
    from core import mse_drilloff

    r = df.evaluate(DF_PARAMS, _steps(lambda w: 3 * w + 5, WOBS[:5]))
    assert r["founder_status"] == df.NO_FOUNDER
    assert mse_drilloff.METHOD_ID == "m372.mse_drilloff" and df.METHOD_ID != mse_drilloff.METHOD_ID
    assert mse_drilloff.METHOD_VERSION.startswith("M372")


def test_an_outlier_is_flagged_not_removed_and_bad_tests_are_refused():
    wobs = (8.0, 12.0, 16.0, 20.0, 24.0, 28.0, 32.0, 36.0, 40.0, 44.0)
    knee = lambda w: 4 * w if w <= 26 else 104 + 0.4 * (w - 26)  # noqa: E731
    steps = _steps(knee, wobs)
    steps[7]["rop_ft_hr"] += 15.0
    r = df.evaluate(DF_PARAMS, steps)
    assert r["flagged_wob_klbf"] == [36.0] and r["steps_used"] == 10                  # flagged, still in the fit
    assert r["residuals"][7] == pytest.approx(12.0, abs=1e-6)
    gross = _steps(knee, wobs)
    gross[2]["rop_ft_hr"] += 40.0                                    # stated limitation: least squares is not robust
    assert abs(df.evaluate(DF_PARAMS, gross)["fitted_breakpoint_wob_klbf"] - 26.0) > 5.0
    assert df.evaluate(DF_PARAMS, _steps(wobs=WOBS[:4]))["status"] == df.NOT_ASSESSED
    varied = _steps()
    varied[3]["rpm"] = 140.0
    assert "not a drill-off test" in df.evaluate(DF_PARAMS, varied)["reason"]
    with pytest.raises(ValueError):
        df.evaluate(DF_PARAMS, _steps(wobs=(10.0, 10.0, 20.0, 25.0, 30.0)))
    with pytest.raises(ValueError):
        df.evaluate(dict(DF_PARAMS, slope_ratio=1.0), _steps())
    assert df.evaluate({"rpm_tolerance_rpm": None, "slope_ratio": 0.5}, _steps())["status"] == df.NOT_ASSESSED


# ---- M427: dull grade -----------------------------------------------------------------------------------------------
GRADE = dict(bit_no="3", bit_type="fixed-cutter", inner="1", outer="2", dull_char="WT", location="S", bearings="X",
             gauge="I", other_char="CT", reason_pulled="TD", depth_in_m=1000.0, depth_out_m=1800.0,
             bit_size_in=8.5, date_out="2026-01-05")


def test_dull_grade_validation_follows_the_iadc_code_set():
    r = dg.evaluate(GRADE)
    assert r["status"] == dg.VALID and r["grade"] == "1-2-WT-S-X-I-CT-TD" and r["footage_m"] == 800.0
    cone = dg.evaluate(dict(GRADE, bit_type="roller-cone", location="M", bearings="E", dull_char="BC", gauge="2"))
    assert cone["status"] == dg.VALID
    for bad, text in ((dict(inner="9"), "0-8"), (dict(dull_char="BC"), "roller-cone bits only"),
                      (dict(bearings="E"), "graded X"), (dict(gauge="17"), "1-16"), (dict(reason_pulled="XX"), "reason"),
                      (dict(depth_out_m=900.0), "shallower"), (dict(date_out="5/1/26"), "YYYY-MM-DD"),
                      (dict(other_char="ZZ"), "not an IADC")):
        r = dg.evaluate(dict(GRADE, **bad))
        assert r["status"] == dg.INVALID and text in r["reason"], bad
    assert dg.evaluate(dict(GRADE, gauge=None))["status"] == dg.NOT_ASSESSED
    assert dg.evaluate(dict(GRADE, depth_out_m=None))["footage_m"] is None
    assert "NOT IMPLEMENTED" in " ".join(dg.summary_lines(dg.evaluate(GRADE)))


def test_dull_grade_needs_a_well_and_the_trend_orders_by_depth(db):  # noqa: F811
    with pytest.raises(ValueError, match="no well"):
        dg.save_case(db, dg.evaluate(GRADE), well_id=None)
    well = db.test_well_id
    shallow = dg.save_case(db, dg.evaluate(GRADE), well_id=well)                  # saved first ...
    deep = dg.save_case(db, dg.evaluate(dict(GRADE, bit_no="4", depth_in_m=1800.0, depth_out_m=2600.0)), well_id=well)
    # ... so newest-first (the case list order) would put the deep run first: the trend orders by depth out
    rows = [r for r in dg.trend(db, well) if r["case_id"] in (deep["id"], shallow["id"])]
    assert [r["case_id"] for r in rows] == [shallow["id"], deep["id"]]


# ---- registration, replay and tampering (all four services) ------------------------------------------------------
CASES = {
    "hb": (hb, lambda: hb.evaluate(base()), "pressure_loss_psi"),
    "ss": (ss, lambda: ss.evaluate(ss_inputs(), SECTIONS), "surge_psi"),
    "df": (df, lambda: df.evaluate(DF_PARAMS, _steps()), "fitted_breakpoint_wob_klbf"),
    "dg": (dg, lambda: dg.evaluate(GRADE), "footage_m"),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_saved_cases_replay_match_and_tampering_is_caught(db, name):  # noqa: F811
    module, run, field = CASES[name]
    case = module.save_case(db, run(), well_id=db.test_well_id)
    assert case["method"] == module.METHOD_ID and hr.handles(module.METHOD_ID)
    entry = next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case["id"])
    assert ch.recalculate_entry(entry, db)["status"] == "MATCH"
    changed = copy.deepcopy(entry.results)
    changed[field]["value"] = changed[field]["value"] + 1.0
    out = ch.recalculate_entry(dataclasses.replace(entry, results=changed), db)
    assert out["status"] == "DIFFERENT" and [d["field_id"] for d in out["differences"]] == [field]
    tampered = copy.deepcopy(entry.inputs)
    key = next(k for k, v in tampered.items() if k != "inputs_sha256" and isinstance(v.get("value"), (int, float))
               and not isinstance(v.get("value"), bool))
    tampered[key]["value"] = tampered[key]["value"] + 1.0
    out = ch.recalculate_entry(dataclasses.replace(entry, inputs=tampered), db)
    assert out["status"] == "UNREADABLE" and "SHA-256" in out["detail"]
    old = ch.recalculate_entry(dataclasses.replace(entry, version="v0"), db)
    assert old["status"] == "NOT_REPRODUCIBLE"
    for key in changed:
        assert hr._unit_of(module.METHOD_ID, key) in hr.FIELD_TOLERANCES


def test_the_catalogue_lists_the_new_services_unapproved():
    from core import method_catalogue as mc

    entries = {e.method_id: e for e in mc.catalogue()}
    for module in (hb, ss, df, dg):
        entry = entries[module.METHOD_ID]
        assert entry.version == module.METHOD_VERSION and "APPROVED" not in entry.label.replace("NOT APPROVED",
                                                                                                         "")


# ---- M422: CCI as a stored case field ----------------------------------------------------------------------------
def test_cci_provenance_is_stored_in_v2_and_v1_cases_still_replay(db):  # noqa: F811
    from PySide6 import QtWidgets

    from core import hydraulics_workflow as hw
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab
    from tests.test_m366_hydraulics_workflow import _fill

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tab = EngineeringCalculatorTab(db)
    try:
        _fill(tab)
        values = tab._hy_values()
    finally:
        tab.deleteLater()
        app.processEvents()
    result = hw.evaluate(values)
    assert result["status"] == "COMPUTED"
    hc = result["base"]["hole_cleaning"]
    _inputs, results = hw.case_payload(result)
    assert results["base_cci"]["value"] == pytest.approx(hc["cci"]) if hc["cci"] is not None else True
    for key in ("base_cci_n", "base_cci_k_equiv_cp", "base_cci_av_ft_min", "base_cci_mw_ppg", "base_cci_method",
                "base_cci_rheology_source", "base_cci_max_inclination_deg"):
        assert key in results
    assert results["base_cci_mw_ppg"]["unit"] == "ppg" and hr._unit_of(hw.METHOD_ID, "base_cci_k_equiv_cp") == "cP"
    _i1, v1 = hw.case_payload(result, hw.METHOD_VERSION_V1)
    assert "base_cci_n" not in v1 and "base_cci" in v1
    case = hw.save_case(db, result, well_id=None)
    entry = next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case["id"])
    assert ch.recalculate_entry(entry, db)["status"] == "MATCH"
    legacy = dataclasses.replace(entry, version=hw.METHOD_VERSION_V1, results=v1)
    assert ch.recalculate_entry(legacy, db)["status"] == "MATCH"


# ---- M418 / M421 / M423 / M427 dialogs from W13 (UI -> service -> case -> replay) -----------------------------------
def test_w13_dialogs_run_save_and_replay_through_the_services(db):  # noqa: F811
    from PySide6 import QtWidgets
    from PySide6.QtCore import QCoreApplication, QEvent

    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tab = EngineeringCalculatorTab(db)
    well = db.test_well_id
    dialogs = []
    try:
        tab.on_well_changed(well, {"name": "SYN-C-01"})
        hbd = tab.hy_hb_slot_dialog()
        dialogs.append(hbd)
        empty = hbd.run()
        assert empty["status"] == hb.NOT_ASSESSED and not hbd.save_btn.isEnabled()        # nothing defaulted
        assert all(empty["inputs"][key] is None for key in hb.UNITS)                   # empty = NOT ENTERED, not 0
        for key, value in base().items():
            hbd.set_value(key, value)
        assert hbd.run()["pressure_loss_psi"] == pytest.approx(hb.evaluate(base())["pressure_loss_psi"])
        assert hbd.save_btn.isEnabled() and hbd.save()["well_id"] == well
        hbd.set_value("flow_rate_gpm", "abc")
        assert hbd.run() is None and "Not run" in hbd.summary.text()

        ssd = tab.hy_surge_hb_dialog()
        dialogs.append(ssd)
        for key, value in ss_inputs().items():
            ssd.set_value(key, value)
        for row, sec in enumerate(SECTIONS):
            ssd.set_row(row, sec)
        assert ssd.run()["surge_psi"] == pytest.approx(ss.evaluate(ss_inputs(), SECTIONS)["surge_psi"])
        assert ssd.save()["method"] == ss.METHOD_ID

        tab.bit_wob.setValue(10.0)
        tab.bit_rpm.setValue(120.0)
        tab.bit_rop.setValue(40.0)
        dfd = tab.drilloff_fitted_dialog()
        dialogs.append(dfd)
        assert [dfd.table.item(0, c).text() for c in range(3)] == ["10", "120", "40"]   # page step copied
        for key, value in DF_PARAMS.items():
            dfd.set_value(key, value)
        for row, step in enumerate(_steps(), start=0):
            dfd.set_row(row, step)
        assert dfd.run()["breakpoint_wob_klbf"] == pytest.approx(22.5, abs=1e-6)
        assert dfd.save()

        tab.bit_od.setValue(8.5)
        dgd = tab.dull_grade_dialog()
        dialogs.append(dgd)
        assert dgd.edits["bit_size_in"].text() == "8.5" and dgd.combos["dull_char"].currentData() is None
        for key, value in GRADE.items():
            dgd.set_value(key, value)
        assert dgd.run()["status"] == dg.VALID
        case = dgd.save()
        assert case and any(r["case_id"] == case["id"] for r in dgd.refresh_trend())
        assert dgd.trend_table.rowCount() >= 1

        for dialog in dialogs:
            entry = next(e for e in ch.load_history(db, sources=["Calculation case"])
                         if e.record_id == dialog.saved_case["id"])
            assert ch.recalculate_entry(entry, db)["status"] == "MATCH"
    finally:
        for dialog in dialogs:
            dialog.deleteLater()
        tab.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


def test_m412_benchmark_table_is_reproduced_exactly():
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    out = subprocess.run([sys.executable, "tools/quality/benchmark_m412.py", "--check"], cwd=root,
                         capture_output=True, text=True, timeout=300,
                         env={**os.environ, "PYTHONPATH": str(root)})
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]
    assert "TOTAL 30 benchmark cases, 0 outside tolerance" in out.stdout
    assert "TOTAL 6 status checks, 0 failed" in out.stdout
