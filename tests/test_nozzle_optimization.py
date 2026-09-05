"""Nozzle-optimization canonical tests (P0).

Requirement: `W13 optimize_nozzles()` must be connected to the canonical
hydraulics engine (`AdvancedHydraulicsEngine.calc_bit_pressure_drop` /
`calc_tfa_from_pressure_drop`) with NO legacy `12031`-style constant.

- Test A — optimizer output is consistent with the canonical hydraulics
  engine (parasitic loss at the pump-test point, optimum-flow law).
- Test B — the optimized TFA equals calc_tfa_from_pressure_drop() at the
  optimum flow and the optimum bit-pressure budget.
- Test C — no legacy constant (12031 / 1086.31 / 10863.1 / 1932) remains in
  the W13 file or the canonical path.
- Test D — the W13 legacy wrapper delegates to (and returns identical dicts
  to) the canonical engine method.
"""
import math
import os
import re

import pytest

from core.hydraulics_engine import AdvancedHydraulicsEngine

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W13 = os.path.join(REPO, "tabs", "w13_Engineering_Calculator.py")

LEGACY_CONSTANTS = ["12031", "1086.31", "10863.1", "1932"]


def _expected_split(max_press, fr1, spp1, fr2, spp2, model):
    """Independent expected value of the parasitic-loss split (textbook)."""
    if fr2 > 0 and fr1 > 0 and spp1 > 0 and spp2 > 0:
        n = math.log10(spp1 / spp2) / math.log10(fr1 / fr2)
        n = n if n > 0 else 1.0
    else:
        n = 1.0
    if model == "HP":
        dpf_max = max_press / (n + 1.0)
    else:
        dpf_max = 2.0 * max_press / (n + 2.0)
    return n, dpf_max


def _load_w13_engine_class():
    """Load only the Qt-free DrillingCalculationEngine class from W13."""
    src = open(W13, encoding="utf-8").read()
    cs = src.index("class DrillingCalculationEngine:")
    ce = src.index("# ==================== UI TAB")
    ns = {}
    exec(compile(src[cs:ce], "<w13 engine class>", "exec"), ns)
    return ns["DrillingCalculationEngine"]


PARAMS = dict(hhp=1200.0, max_press=3500.0, fr1=400.0, spp1=2800.0,
              fr2=300.0, spp2=1700.0, prev_tfa=0.7, mw_ppg=12.0,
              n_nozzles=3, model="HP")


class TestNozzleOptimizationCanonical:
    def test_optimizer_consistent_with_canonical_bit_pressure_drop(self):
        """Test A: outputs consistent with calc_bit_pressure_drop()."""
        r = AdvancedHydraulicsEngine.optimize_nozzles(**PARAMS)

        # parasitic friction at the pump-test point (SPP minus bit ΔP)
        n, _ = _expected_split(max_press=PARAMS["max_press"], fr1=PARAMS["fr1"],
                                   spp1=PARAMS["spp1"], fr2=PARAMS["fr2"],
                                   spp2=PARAMS["spp2"], model="HP")
        dpf_1 = PARAMS["spp1"] - AdvancedHydraulicsEngine.calc_bit_pressure_drop(
            PARAMS["fr1"], PARAMS["mw_ppg"], PARAMS["prev_tfa"])
        a = dpf_1 / PARAMS["fr1"] ** n
        # optimum flow follows Q = (ΔP_par_max/a)^(1/n)
        dpf_max = _expected_split(max_press=PARAMS["max_press"], fr1=PARAMS["fr1"],
                                     spp1=PARAMS["spp1"], fr2=PARAMS["fr2"],
                                     spp2=PARAMS["spp2"], model="HP")[1]
        q_opt = (dpf_max / a) ** (1.0 / n)
        assert r["optimal_flow_rate_gpm"] == pytest.approx(q_opt, rel=1e-4)
        # the chosen TFA at q_opt reproduces the bit-pressure budget
        if r["optimal_tfa_in2"] > 0:
            dp_bit = PARAMS["max_press"] - dpf_max
            dp_check = AdvancedHydraulicsEngine.calc_bit_pressure_drop(
                r["optimal_flow_rate_gpm"], PARAMS["mw_ppg"],
                r["optimal_tfa_in2"])
            assert dp_check == pytest.approx(dp_bit, rel=2e-2)
        # flow rate never exceeds the pump-limited maximum
        assert r["max_flow_rate_gpm"] == pytest.approx(
            PARAMS["hhp"] * 1714.0 / PARAMS["max_press"], abs=0.06)
        assert r["optimal_flow_rate_gpm"] <= r["max_flow_rate_gpm"] + 1e-6

    def test_optimal_tfa_matches_calc_tfa_from_pressure_drop(self):
        """Test B: optimal TFA == calc_tfa_from_pressure_drop at Q_opt/ΔP_bit."""
        for model in ("HP", "IF"):
            params = dict(PARAMS, model=model)
            r = AdvancedHydraulicsEngine.optimize_nozzles(**params)
            n, dpf_max = _expected_split(
                max_press=params["max_press"], fr1=params["fr1"],
                spp1=params["spp1"], fr2=params["fr2"],
                spp2=params["spp2"], model=model)
            dp_bit = params["max_press"] - dpf_max
            expected = AdvancedHydraulicsEngine.calc_tfa_from_pressure_drop(
                r["optimal_flow_rate_gpm"], params["mw_ppg"], dp_bit)
            assert r["optimal_tfa_in2"] == pytest.approx(
                round(expected, 4), abs=5e-4)
            # nozzle search error is consistent with the canonical TFA
            if r["actual_tfa_in2"] > 0:
                assert r["tfa_error"] == pytest.approx(
                    abs(r["actual_tfa_in2"] - r["optimal_tfa_in2"]), abs=1e-3)

    def test_selected_nozzles_match_actual_tfa(self):
        """The returned nozzle combination reproduces actual_tfa_in2."""
        for model in ("HP", "IF"):
            r = AdvancedHydraulicsEngine.optimize_nozzles(**dict(PARAMS, model=model))
            if not r["selected_nozzles"]:
                continue
            area = sum(
                math.pi / 4 * (s / 32.0) ** 2 for s in r["selected_nozzles"])
            assert area == pytest.approx(r["actual_tfa_in2"], abs=5e-5)

    def test_legacy_constants_removed_from_w13(self):
        """Test C: no 12031 (or other legacy constants) in the W13 file."""
        src = open(W13, encoding="utf-8").read()
        for const in LEGACY_CONSTANTS:
            assert const not in src, f"legacy constant {const} still in W13"

    def test_legacy_constants_removed_from_canonical_engine(self):
        """Test C2: canonical engine has no legacy constants either."""
        src = open(os.path.join(REPO, "core", "hydraulics_engine.py"),
                   encoding="utf-8").read()
        for const in LEGACY_CONSTANTS:
            assert const not in src

    def test_wrapper_delegates_to_canonical_engine(self):
        """Test D: W13 wrapper is a pure delegate returning identical dicts."""
        Engine = _load_w13_engine_class()
        for model in ("HP", "IF"):
            legacy_params = {k: v for k, v in PARAMS.items() if k != "mw_ppg"}
            legacy_params["mw"] = PARAMS["mw_ppg"]
            wrapper = Engine.optimize_nozzles(**dict(legacy_params, model=model))
            canonical = AdvancedHydraulicsEngine.optimize_nozzles(
                **dict(PARAMS, model=model))
            assert wrapper == canonical
            assert wrapper["optimal_tfa_in2"] > 0
        # source-level: wrapper body must call the canonical method and must
        # not re-implement the formula (no math.sqrt / no combinations)
        src = open(W13, encoding="utf-8").read()
        cs = src.index("class DrillingCalculationEngine:")
        ce = src.index("# ==================== UI TAB")
        cls = src[cs:ce]
        opt = cls[cls.index("def optimize_nozzles"):cls.index("def calc_free_point")]
        assert "AdvancedHydraulicsEngine.optimize_nozzles" in opt
        assert "12031" not in opt
        assert "math.sqrt" not in opt
        assert "combinations_with_replacement" not in opt

    def test_invalid_pump_test_does_not_crash(self):
        """Guard regression: zero second SPP used to raise ZeroDivisionError."""
        bad = dict(PARAMS, spp2=0.0)
        r = AdvancedHydraulicsEngine.optimize_nozzles(**bad)
        assert r["optimal_tfa_in2"] > 0 or r["optimal_flow_rate_gpm"] >= 0
        bad2 = dict(PARAMS, fr1=0.0, spp1=0.0)
        r2 = AdvancedHydraulicsEngine.optimize_nozzles(**bad2)
        assert r2["optimal_flow_rate_gpm"] >= 0

    def test_legacy_parity_of_numbers(self):
        """The canonical result equals the formula the tab used to compute
        (same math, single implementation)."""
        r = AdvancedHydraulicsEngine.optimize_nozzles(**PARAMS)
        # legacy formula (numerically identical to canonical 10858):
        #   Q_opt_max = hhp*1714/max_press
        #   n = log10(spp1/spp2)/log10(fr1/fr2)
        n = math.log10(PARAMS["spp1"] / PARAMS["spp2"]) / math.log10(
            PARAMS["fr1"] / PARAMS["fr2"])
        dpf_max = PARAMS["max_press"] / (n + 1.0)
        dpf_1 = PARAMS["spp1"] - (PARAMS["mw_ppg"] * PARAMS["fr1"] ** 2) / (
            10858.0 * PARAMS["prev_tfa"] ** 2)
        a = dpf_1 / PARAMS["fr1"] ** n
        q_opt = (dpf_max / a) ** (1.0 / n)
        dp_bit = PARAMS["max_press"] - dpf_max
        tfa = math.sqrt(PARAMS["mw_ppg"] * q_opt ** 2 / (10858.0 * dp_bit))
        assert r["optimal_flow_rate_gpm"] == pytest.approx(round(q_opt, 1), abs=0.11)
        assert r["optimal_tfa_in2"] == pytest.approx(round(tfa, 4), abs=5e-4)
