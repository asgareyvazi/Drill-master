"""Mission 7 — Well Control kill-sheet canonical boundary tests.

These tests prove the relocated composite computation
(``core.engineering.well_control_kill_sheet``) is:

1. **Numerically identical** to the original ``_wc_calc_kill`` handler arithmetic
   (a faithful inline re-implementation is the independent oracle) — several
   cases, actual engine outputs (mission §18/§21).
2. **Canonical-unit correct** — the single unit-conversion owner applies each
   historical factor exactly once, no double/missing conversion (mission §8/§9).
3. **Deterministic** — same inputs -> byte-identical result dict, repeated and
   interleaved (mission §16).
4. **Immutable at the boundary** — frozen inputs cannot be mutated; the source
   pipe list is not aliased (mission §17).
5. **Round-trippable** — ``as_dict``/``from_dict`` reconstructs inputs 1:1
   (mission §18 optional round-trip; needed for future snapshotting).

All tests are Qt-free (no widgets) so they run in the shared interpreter.
"""
import math

import pytest

from core.hydraulics_engine import AdvancedHydraulicsEngine
from core.engineering.engines.well_control import WellControlEngine
from core.engineering.well_control_kill_sheet import (
    FT_PER_M,
    PCF_PER_PPG,
    PSI_PER_PPG_FT,
    CHOKE_SCHEDULE_INTERVALS,
    PipeSegment,
    WellControlKillSheetInputs,
    build_canonical_kill_sheet_inputs,
    compute_kill_sheet,
)


# --- independent oracle: the ORIGINAL handler arithmetic, verbatim ----------
def _oracle_kill_sheet(raw):
    """Re-implementation of the historical ``_wc_calc_kill`` inline math.

    Consumes RAW UI values (metres / pcf / psi/ft) exactly as the widgets
    provided them, so this is a genuine independent oracle for the refactor.
    """
    A = AdvancedHydraulicsEngine
    WC = WellControlEngine

    tvd_ft = raw["tvd_m"] * 3.28084
    shoe_tvd_ft = raw["shoe_tvd_m"] * 3.28084
    mw_pcf = raw["mw_pcf"]
    mw_ppg = mw_pcf / 7.48
    sidpp = raw["sidpp_psi"]
    sicp = raw["sicp_psi"]
    frac_grad = raw["frac_gradient_psi_ft"]
    pit_gain = raw["pit_gain_bbl"]
    scr1 = raw["scr1_psi"]
    pump_output = raw["pump_output_bbl_stk"]
    hole = raw["hole_size_in"]
    csg_id = raw["casing_id_in"]

    total_string_vol = 0.0
    total_ann_vol = 0.0
    for p in raw["pipes_m"]:
        od = p.get("od", 0)
        id_ = p.get("id", 0)
        L = p.get("length", 0)
        cap = A.calc_pipe_capacity_bbl_ft(id_) * (L * 3.28084)
        total_string_vol += cap
        if L > 0:
            ann_id_val = csg_id
            if ann_id_val > od:
                ann = A.calc_annular_capacity_bbl_ft(ann_id_val, od) * (L * 3.28084)
                total_ann_vol += ann

    kmw_r = WC.kill_mw(mw_ppg, sidpp, tvd_ft)
    kmw_ppg = kmw_r.value
    icp = scr1 + sidpp
    fcp = scr1 * (kmw_ppg / mw_ppg)
    maasp_r = WC.maasp(
        max_allowable_mw_ppg=frac_grad / 0.052 if frac_grad else None,
        current_mw_ppg=mw_ppg,
        shoe_tvd_ft=shoe_tvd_ft,
    )
    maasp = maasp_r.value

    stk_to_bit = total_string_vol / pump_output if pump_output > 0 else 0
    stk_annular = total_ann_vol / pump_output if pump_output > 0 else 0

    kick_height = 0.0
    last_pipe_od = raw["pipes_m"][-1].get("od", 5) if raw["pipes_m"] else 5
    ann_cap_ft = A.calc_annular_capacity_bbl_ft(hole, last_pipe_od)
    if pit_gain > 0 and ann_cap_ft > 0:
        kv = WC.kick_volume(
            pit_gain_bbl=pit_gain,
            annular_capacity_bbl_ft=ann_cap_ft,
            mw_ppg=mw_ppg,
            sidpp_psi=sidpp,
            sicp_psi=sicp,
        )
        if kv.success:
            kick_height = kv.values.get("kick_height_ft") or 0.0

    schedule = []
    intervals = 10
    if stk_to_bit > 0:
        step = stk_to_bit / intervals
        dp = (icp - fcp) / intervals
        for i in range(intervals + 1):
            strokes = round(i * step)
            pressure = round(icp - i * dp, 1)
            schedule.append((strokes, pressure, round(i / intervals * 100)))

    return {
        "kmw_ppg": kmw_ppg,
        "icp": icp,
        "fcp": fcp,
        "maasp": maasp,
        "total_string_vol": total_string_vol,
        "total_ann_vol": total_ann_vol,
        "stk_to_bit": stk_to_bit,
        "stk_annular": stk_annular,
        "kick_height": kick_height,
        "schedule": schedule,
    }


def _raw_to_kwargs(raw):
    return dict(
        tvd_m=raw["tvd_m"],
        md_m=raw["md_m"],
        shoe_tvd_m=raw["shoe_tvd_m"],
        hole_size_in=raw["hole_size_in"],
        casing_id_in=raw["casing_id_in"],
        casing_od_in=raw.get("casing_od_in"),
        mw_pcf=raw["mw_pcf"],
        frac_gradient_psi_ft=raw["frac_gradient_psi_ft"],
        sidpp_psi=raw["sidpp_psi"],
        sicp_psi=raw["sicp_psi"],
        pit_gain_bbl=raw["pit_gain_bbl"],
        scr1_psi=raw["scr1_psi"],
        scr1_spm=raw["scr1_spm"],
        scr2_psi=raw["scr2_psi"],
        scr2_spm=raw["scr2_spm"],
        pump_output_bbl_stk=raw["pump_output_bbl_stk"],
        method=raw["method"],
        well_type=raw["well_type"],
        pipes_m=raw["pipes_m"],
    )


CASES = [
    # (1) default-ish vertical well with 3-segment string + pit gain
    dict(
        tvd_m=3000, md_m=3200, shoe_tvd_m=2000, hole_size_in=8.5,
        casing_id_in=8.835, casing_od_in=9.625, mw_pcf=90.0,
        frac_gradient_psi_ft=0.8, sidpp_psi=500, sicp_psi=700, pit_gain_bbl=10,
        scr1_psi=800, scr1_spm=30, scr2_psi=600, scr2_spm=25,
        pump_output_bbl_stk=0.09, method="Wait & Weight", well_type="Vertical",
        pipes_m=[
            {"type": "DP", "od": 5.0, "id": 4.276, "length": 2800.0},
            {"type": "HWDP", "od": 5.0, "id": 3.0, "length": 200.0},
            {"type": "DC", "od": 6.5, "id": 2.8125, "length": 150.0},
        ],
    ),
    # (2) driller's method, heavier mud, big kick, deviated well
    dict(
        tvd_m=4200, md_m=4800, shoe_tvd_m=3500, hole_size_in=12.25,
        casing_id_in=12.415, casing_od_in=13.375, mw_pcf=112.0,
        frac_gradient_psi_ft=0.95, sidpp_psi=820, sicp_psi=1100, pit_gain_bbl=32,
        scr1_psi=1200, scr1_spm=40, scr2_psi=900, scr2_spm=32,
        pump_output_bbl_stk=0.117, method="Driller's", well_type="Deviated",
        pipes_m=[
            {"type": "DP", "od": 5.5, "id": 4.778, "length": 4400.0},
            {"type": "DC", "od": 8.0, "id": 3.0, "length": 220.0},
        ],
    ),
    # (3) no pit gain, single pipe (kick_volume skipped, MAASP present)
    dict(
        tvd_m=1500, md_m=1500, shoe_tvd_m=1200, hole_size_in=6.0,
        casing_id_in=6.276, casing_od_in=7.0, mw_pcf=75.0,
        frac_gradient_psi_ft=0.7, sidpp_psi=300, sicp_psi=300, pit_gain_bbl=0,
        scr1_psi=500, scr1_spm=20, scr2_psi=400, scr2_spm=18,
        pump_output_bbl_stk=0.05, method="Wait & Weight", well_type="Vertical",
        pipes_m=[
            {"type": "DP", "od": 3.5, "id": 2.764, "length": 1500.0},
        ],
    ),
    # (4) empty pipe list -> zero volumes / no schedule
    dict(
        tvd_m=2500, md_m=2500, shoe_tvd_m=2000, hole_size_in=8.5,
        casing_id_in=8.681, casing_od_in=9.625, mw_pcf=95.0,
        frac_gradient_psi_ft=0.85, sidpp_psi=450, sicp_psi=600, pit_gain_bbl=5,
        scr1_psi=700, scr1_spm=28, scr2_psi=520, scr2_spm=22,
        pump_output_bbl_stk=0.08, method="Driller's", well_type="Vertical",
        pipes_m=[],
    ),
]


@pytest.mark.parametrize("raw", CASES)
def test_matches_original_handler_math(raw):
    """Relocated computation == original inline arithmetic (exact)."""
    oracle = _oracle_kill_sheet(raw)
    inp = build_canonical_kill_sheet_inputs(**_raw_to_kwargs(raw))
    res = compute_kill_sheet(inp)
    assert res.success

    assert res.kill_mw_ppg == pytest.approx(oracle["kmw_ppg"], abs=0, rel=0)
    assert res.icp_psi == pytest.approx(oracle["icp"], abs=0, rel=0)
    assert res.fcp_psi == pytest.approx(oracle["fcp"], abs=0, rel=0)
    assert res.maasp_psi == pytest.approx(oracle["maasp"], abs=0, rel=0)
    assert res.total_string_vol_bbl == pytest.approx(oracle["total_string_vol"], abs=0, rel=0)
    assert res.total_ann_vol_bbl == pytest.approx(oracle["total_ann_vol"], abs=0, rel=0)
    assert res.stk_to_bit == pytest.approx(oracle["stk_to_bit"], abs=0, rel=0)
    assert res.stk_annular == pytest.approx(oracle["stk_annular"], abs=0, rel=0)
    assert res.kick_height_ft == pytest.approx(oracle["kick_height"], abs=0, rel=0)
    assert res.choke_schedule == oracle["schedule"]


def test_unit_conversion_single_owner():
    """Builder applies each historical factor exactly once (no double conv)."""
    raw = CASES[0]
    inp = build_canonical_kill_sheet_inputs(**_raw_to_kwargs(raw))
    assert inp.tvd_ft == pytest.approx(raw["tvd_m"] * FT_PER_M)
    assert inp.shoe_tvd_ft == pytest.approx(raw["shoe_tvd_m"] * FT_PER_M)
    assert inp.mw_ppg == pytest.approx(raw["mw_pcf"] / PCF_PER_PPG)
    # pipe lengths converted to feet exactly once
    for src, seg in zip(raw["pipes_m"], inp.pipes):
        assert seg.length_ft == pytest.approx(src["length"] * FT_PER_M)
    # frac gradient is NOT pre-converted here (engine consumes psi/ft->ppg)
    assert inp.frac_gradient_psi_ft == raw["frac_gradient_psi_ft"]


def test_deterministic_repeated_and_interleaved():
    a = compute_kill_sheet(build_canonical_kill_sheet_inputs(**_raw_to_kwargs(CASES[0])))
    b = compute_kill_sheet(build_canonical_kill_sheet_inputs(**_raw_to_kwargs(CASES[1])))
    a2 = compute_kill_sheet(build_canonical_kill_sheet_inputs(**_raw_to_kwargs(CASES[0])))
    b2 = compute_kill_sheet(build_canonical_kill_sheet_inputs(**_raw_to_kwargs(CASES[1])))
    assert a.as_dict() == a2.as_dict()
    assert b.as_dict() == b2.as_dict()
    assert a.as_dict() != b.as_dict()


def test_inputs_are_immutable_and_not_aliased():
    raw = CASES[0]
    src_pipes = [dict(p) for p in raw["pipes_m"]]
    inp = build_canonical_kill_sheet_inputs(**{**_raw_to_kwargs(raw), "pipes_m": src_pipes})
    # frozen dataclass -> cannot assign
    with pytest.raises(Exception):
        inp.mw_ppg = 99.0  # type: ignore[misc]
    with pytest.raises(Exception):
        inp.pipes[0].od_in = 1.0  # type: ignore[misc]
    # mutating the source list after build must not change the frozen snapshot
    src_pipes.append({"type": "X", "od": 1, "id": 0.5, "length": 100})
    assert len(inp.pipes) == len(raw["pipes_m"])


def test_round_trip_serialization():
    for raw in CASES:
        inp = build_canonical_kill_sheet_inputs(**_raw_to_kwargs(raw))
        again = WellControlKillSheetInputs.from_dict(inp.as_dict())
        assert again.as_dict() == inp.as_dict()
        # and it computes identically after a round trip
        assert compute_kill_sheet(again).as_dict() == compute_kill_sheet(inp).as_dict()


def test_zero_mud_weight_fails_via_engine():
    """Preserved behavior: kill_mw is called first and rejects MW<=0 at the
    engine, before the handler's own positive-MW guard is reached. We keep the
    original ordering, so the failure is classified ENGINE_FAILED."""
    raw = {**CASES[0], "mw_pcf": 0.0}
    inp = build_canonical_kill_sheet_inputs(**_raw_to_kwargs(raw))
    res = compute_kill_sheet(inp)
    assert not res.success
    assert "ENGINE_FAILED" in res.error


def test_missing_frac_gradient_fails_at_maasp():
    """Preserved behavior: without a fracture gradient MAASP cannot be computed,
    so the kill sheet legitimately fails rather than fabricating a value."""
    raw = {**CASES[0], "frac_gradient_psi_ft": 0.0}
    inp = build_canonical_kill_sheet_inputs(**_raw_to_kwargs(raw))
    res = compute_kill_sheet(inp)
    assert not res.success
    assert "ENGINE_FAILED" in res.error


def test_empty_string_has_no_schedule_and_zero_volumes():
    inp = build_canonical_kill_sheet_inputs(**_raw_to_kwargs(CASES[3]))
    res = compute_kill_sheet(inp)
    assert res.success
    assert res.total_string_vol_bbl == 0
    assert res.total_ann_vol_bbl == 0
    assert res.choke_schedule == []
