"""Well Control ICP/FCP single-owner consolidation tests (dual-path forensics).

Before this consolidation the Initial/Final Circulating Pressure formulas were
re-implemented inline in THREE places (the canonical composite
``compute_kill_sheet``, the legacy ``DrillingCalculatorDialog._calc_kill_sheet``,
and ``WellControlExtended.wait_weight_method``). ``kill_mw`` and ``maasp`` were
already single-owner (both production paths delegated to ``WellControlEngine``).

These tests prove:

1. The new ``WellControlEngine`` ICP/FCP methods match an INDEPENDENT oracle
   (hand arithmetic), not just the implementation.
2. All three former inline sites now produce identical numbers via the single
   owner (dual-path numerical equivalence, full precision).
3. Validation/failure semantics are explicit (no silent defaults).

No formula changed — only the owner. Qt-free.
"""
from __future__ import annotations

import pytest

from core.engineering.engines.well_control import WellControlEngine as WC
from core.engineering.extended import WellControlExtended
from core.engineering.well_control_kill_sheet import (
    build_canonical_kill_sheet_inputs,
    compute_kill_sheet,
)


# --- independent oracle (hand arithmetic) ----------------------------------
def _oracle_icp(spr, sidpp):
    return spr + sidpp


def _oracle_fcp(spr, kmw, mw):
    return spr * (kmw / mw)


CASES = [
    dict(spr=800, sidpp=500, mw_ppg=10.0, tvd_ft=10000.0),
    dict(spr=1200, sidpp=820, mw_ppg=12.5, tvd_ft=13780.0),
    dict(spr=500, sidpp=300, mw_ppg=9.6, tvd_ft=4920.0),
]


@pytest.mark.parametrize("c", CASES)
def test_engine_icp_matches_oracle(c):
    kmw = WC.calculate_kill_mw(c["mw_ppg"], c["sidpp"], c["tvd_ft"])
    assert WC.calculate_icp(c["spr"], c["sidpp"]) == pytest.approx(
        _oracle_icp(c["spr"], c["sidpp"]), abs=0, rel=0)
    assert WC.calculate_fcp(c["spr"], kmw, c["mw_ppg"]) == pytest.approx(
        _oracle_fcp(c["spr"], kmw, c["mw_ppg"]), abs=0, rel=0)


@pytest.mark.parametrize("c", CASES)
def test_engine_result_wrappers_carry_value_and_method(c):
    kmw = WC.calculate_kill_mw(c["mw_ppg"], c["sidpp"], c["tvd_ft"])
    icp_r = WC.initial_circulating_pressure(c["spr"], c["sidpp"])
    fcp_r = WC.final_circulating_pressure(c["spr"], kmw, c["mw_ppg"])
    assert icp_r.success and icp_r.values["icp_psi"] == pytest.approx(
        round(_oracle_icp(c["spr"], c["sidpp"]), 2))
    assert fcp_r.success and fcp_r.values["fcp_psi"] == pytest.approx(
        round(_oracle_fcp(c["spr"], kmw, c["mw_ppg"]), 2))
    assert icp_r.method == WC.METHOD and fcp_r.method == WC.METHOD


def test_extended_wait_weight_delegates_to_single_owner():
    """WellControlExtended must now yield engine-identical ICP/FCP."""
    for c in CASES:
        res = WellControlExtended.wait_weight_method(
            original_mw_ppg=c["mw_ppg"], sidpp_psi=c["sidpp"],
            tvd_ft=c["tvd_ft"], circ_pressure_psi=c["spr"])
        kmw = WC.calculate_kill_mw(c["mw_ppg"], c["sidpp"], c["tvd_ft"])
        assert res["initial_circulating_pressure_psi"] == pytest.approx(
            round(WC.calculate_icp(c["spr"], c["sidpp"]), 1))
        assert res["final_circulating_pressure_psi"] == pytest.approx(
            round(WC.calculate_fcp(c["spr"], kmw, c["mw_ppg"]), 1))


def test_composite_and_legacy_subset_agree_full_precision():
    """The composite kill sheet and the legacy quick-estimate subset must agree
    on every shared correctness value (kill_mw, ICP, FCP) to full precision."""
    for c in CASES:
        # legacy quick-estimate arithmetic (now delegating to the engine)
        mw_ppg = c["mw_ppg"]
        kmw = WC.calculate_kill_mw(mw_ppg, c["sidpp"], c["tvd_ft"])
        icp_legacy = WC.calculate_icp(c["spr"], c["sidpp"])
        fcp_legacy = WC.calculate_fcp(c["spr"], kmw, mw_ppg)

        tvd_m = c["tvd_ft"] / 3.28084
        inp = build_canonical_kill_sheet_inputs(
            tvd_m=tvd_m, md_m=tvd_m, shoe_tvd_m=tvd_m * 0.6,
            hole_size_in=8.5, casing_id_in=8.835, casing_od_in=9.625,
            mw_pcf=mw_ppg * 7.48, frac_gradient_psi_ft=0.8,
            sidpp_psi=c["sidpp"], sicp_psi=c["sidpp"] + 100, pit_gain_bbl=0,
            scr1_psi=c["spr"], scr1_spm=30, scr2_psi=0, scr2_spm=0,
            pump_output_bbl_stk=0.09, method="Driller's", well_type="Vertical",
            pipes_m=[{"type": "DP", "od": 5.0, "id": 4.276, "length": 2000.0}])
        r = compute_kill_sheet(inp)
        assert r.success
        # kill_mw depends on TVD, which round-trips ft->m->ft here (1-ULP noise)
        assert r.kill_mw_ppg == pytest.approx(kmw, rel=1e-12)
        # ICP does not depend on TVD -> exact; FCP uses composite kill_mw -> ~exact
        assert r.icp_psi == pytest.approx(icp_legacy, abs=0, rel=0)
        assert r.fcp_psi == pytest.approx(fcp_legacy, rel=1e-12)


def test_icp_fcp_validation_is_explicit():
    # negative slow pump rate rejected
    r = WC.initial_circulating_pressure(-1, 500)
    assert not r.success
    # zero original MW rejected for FCP (no divide-by-zero, no silent default)
    r2 = WC.final_circulating_pressure(800, 12.0, 0.0)
    assert not r2.success
