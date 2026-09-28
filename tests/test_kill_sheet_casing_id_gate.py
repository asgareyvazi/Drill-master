"""Kill sheet: an absent casing ID must refuse, not silently drop the annulus.

Defect proven here (core/engineering/well_control_kill_sheet.py):

    ``casing_id_in`` is a *required* keyword of
    ``build_canonical_kill_sheet_inputs`` (no default, :215) and it is
    consumed by the composite computation (``csg_id = inp.casing_id_in``,
    :454, feeding the annular loop at :475-479), but it was absent from the
    builder's ``required_raw`` gate - whose own comment says it lists the
    inputs "the composite computation actually consumes" (:257).

    The kill-sheet widgets hand the builder ``None`` for their "not supplied"
    sentinel ("Read a kill-sheet input; the sentinel reads back as ``None``",
    tabs/w13_Engineering_Calculator.py:5227-5231), so an unfilled casing-ID
    field became ``0.0``; ``ann_id_val > od`` is then false, the annular
    volume silently disappeared from the sheet (and with it the annular
    displacement strokes derived from it) while every *gated* input refused.

The gate is the module's own refuse-instead mechanism ("A kill sheet computed
from absent kick data looks plausible and is wrong ... Refuse instead",
:436-443) - this fix only adds the consumed-but-ungated input to it.

Regression discipline: the first test fails on the pre-fix builder
(``success=True`` with ``casing_id_in=None``); the second guards against
over-refusal, and the third states that an *explicit* zero stays a supplied
value (only the unknown is gated).
"""

from core.engineering.well_control_kill_sheet import (
    build_canonical_kill_sheet_inputs,
    compute_kill_sheet,
)

# Known-good inputs (same shape as tests/test_well_control_kill_sheet.py case 1).
RAW = dict(
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
)


def _kwargs(**overrides):
    kwargs = dict(RAW)
    kwargs.update(overrides)
    return kwargs


def test_absent_casing_id_refuses_instead_of_computing():
    inp = build_canonical_kill_sheet_inputs(**_kwargs(casing_id_in=None))

    assert inp.missing_inputs == ("casing_id_in",)

    result = compute_kill_sheet(inp)
    assert result.success is False
    assert "casing_id_in" in result.error
    assert "missing required kill-sheet inputs" in result.error


def test_present_casing_id_still_computes_the_annulus():
    inp = build_canonical_kill_sheet_inputs(**_kwargs())

    assert inp.missing_inputs == ()
    result = compute_kill_sheet(inp)

    assert result.success is True, result.error
    assert result.total_ann_vol_bbl > 0.0        # the annulus is really used
    assert result.ann_detail                      # one entry per string section
    assert result.stk_annular > 0.0               # and it drives the strokes


def test_explicit_zero_casing_id_is_a_supplied_value():
    """Only the *unknown* is gated - an explicit 0.0 is a supplied number."""
    inp = build_canonical_kill_sheet_inputs(**_kwargs(casing_id_in=0.0))

    assert "casing_id_in" not in inp.missing_inputs
    assert compute_kill_sheet(inp).success is True
