"""M269 (R-2): the kill-sheet annulus over a domain input table, checked against independent geometry.

Annular capacity is recomputed here from first principles - (D_outer^2 - D_pipe^2) / 1029.4 bbl/ft, lengths
converted with the exact 0.3048 m/ft - and summed zone by zone (cased above the shoe, open hole below it).
The engine's own helpers are not used for the expected values.

Rows (see docs/mission-reports/m261-m290-evidence/m269_kill_sheet_domain_table.md):
  known casing ID, shoe below surface ........ annulus = cased + open-hole sum
  shoe at surface, known casing ID ........... no cased zone: the whole annulus is open hole
  unknown casing ID (None) ................... refused by the builder (missing input)
  explicit casing ID 0, shoe below surface ... a cased zone exists and ID 0 cannot hold the pipe: not assessed
  missing shoe MD (None) ..................... annulus not located: not assessed, string volume still given
  shoe deeper than MD ........................ invalid input, refused
  casing ID <= pipe OD in the cased zone ..... impossible geometry: not assessed
  hole size <= pipe OD in the open hole ...... impossible geometry: not assessed
NOT pinned on purpose: shoe at MD 0 with an explicit casing ID 0 (the KS-unfilled-casing-id-assessed survivor).
There is no cased zone, so the casing ID enters no zone; refusing (current) and computing the open-hole annulus
(the mutant) are both geometrically defensible, and which one a kill sheet must do is an engineering / owner
decision (P11).  A test demanding either would decide it.
"""
from __future__ import annotations

import pytest

from core.engineering.well_control_kill_sheet import build_canonical_kill_sheet_inputs, compute_kill_sheet

M_TO_FT = 1 / 0.3048
PIPES = [
    {"type": "DP", "od": 5.0, "id": 4.276, "length": 2800.0},
    {"type": "HWDP", "od": 5.0, "id": 3.0, "length": 200.0},
    {"type": "DC", "od": 6.5, "id": 2.8125, "length": 200.0},
]
RAW = dict(
    tvd_m=3000, md_m=3200, shoe_tvd_m=2000, shoe_md_m=2000, hole_size_in=8.5,
    casing_id_in=8.835, casing_od_in=9.625, mw_pcf=90.0,
    frac_gradient_psi_ft=0.8, sidpp_psi=500, sicp_psi=700, pit_gain_bbl=10,
    scr1_psi=800, scr1_spm=30, scr2_psi=600, scr2_spm=25,
    pump_output_bbl_stk=0.09, method="Wait & Weight", well_type="Vertical", pipes_m=PIPES,
)


def _run(**overrides):
    raw = dict(RAW)
    raw.update(overrides)
    inp = build_canonical_kill_sheet_inputs(**raw)
    return inp, compute_kill_sheet(inp)


def _independent_annulus(shoe_m, casing_id, hole, pipes=PIPES):
    total, top = 0.0, 0.0
    for pipe in pipes:
        bottom = top + pipe["length"]
        cased = max(0.0, min(bottom, shoe_m) - top)
        open_ = max(0.0, bottom - max(top, shoe_m))
        total += (casing_id ** 2 - pipe["od"] ** 2) / 1029.4 * cased * M_TO_FT
        total += (hole ** 2 - pipe["od"] ** 2) / 1029.4 * open_ * M_TO_FT
        top = bottom
    return total


def _independent_string():
    return sum(p["id"] ** 2 / 1029.4 * p["length"] * M_TO_FT for p in PIPES)


def test_known_casing_id_and_shoe_below_surface_give_the_zone_sum():
    _inp, result = _run()
    assert result.success, result.error
    expected = _independent_annulus(2000.0, 8.835, 8.5)
    assert result.total_ann_vol_bbl == pytest.approx(expected, rel=1e-6)
    assert result.total_string_vol_bbl == pytest.approx(_independent_string(), rel=1e-6)
    # magnitude check by hand: DP in casing 2000 m x (8.835^2 - 25)/1029.4 = 0.051538 bbl/ft -> 338.17 bbl
    assert 338.0 < (8.835 ** 2 - 25) / 1029.4 * 2000 * M_TO_FT < 338.4


def test_shoe_at_surface_with_a_known_casing_id_is_all_open_hole():
    _inp, result = _run(shoe_md_m=0.0)
    assert result.success, result.error
    assert result.total_ann_vol_bbl == pytest.approx(_independent_annulus(0.0, 8.835, 8.5), rel=1e-6)
    assert result.total_ann_vol_bbl == pytest.approx(_independent_annulus(0.0, 99.0, 8.5), rel=1e-6), \
        "with no cased zone the casing ID must not enter the annulus"


def test_unknown_casing_id_is_refused_by_the_builder():
    inp, result = _run(casing_id_in=None)
    assert inp.missing_inputs == ("casing_id_in",)
    assert not result.success


def test_explicit_zero_casing_id_with_a_cased_zone_is_not_assessed():
    _inp, result = _run(casing_id_in=0.0)
    assert result.success, result.error
    assert result.total_ann_vol_bbl is None
    assert result.total_string_vol_bbl == pytest.approx(_independent_string(), rel=1e-6)


def test_missing_shoe_md_leaves_the_annulus_unlocated():
    _inp, result = _run(shoe_md_m=None)
    assert result.success, result.error
    assert result.total_ann_vol_bbl is None
    assert result.total_string_vol_bbl == pytest.approx(_independent_string(), rel=1e-6)


def test_a_shoe_deeper_than_md_is_refused():
    inp, result = _run(shoe_md_m=3300.0)
    assert inp.invalid_inputs
    assert not result.success


@pytest.mark.parametrize("casing_id", [5.0, 4.9])
def test_casing_id_not_larger_than_the_pipe_od_is_not_assessed(casing_id):
    _inp, result = _run(casing_id_in=casing_id)
    assert result.success, result.error
    assert result.total_ann_vol_bbl is None


def test_hole_not_larger_than_the_collar_od_is_not_assessed():
    _inp, result = _run(hole_size_in=6.5)
    assert result.success, result.error
    assert result.total_ann_vol_bbl is None


def test_hole_just_larger_than_the_collar_od_is_assessed():
    _inp, result = _run(hole_size_in=6.75)
    assert result.success, result.error
    assert result.total_ann_vol_bbl == pytest.approx(_independent_annulus(2000.0, 8.835, 6.75), rel=1e-6)
