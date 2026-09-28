"""Absent vs explicitly-zero casing loads must stay distinguishable (M33 Part E).

``CasingEngine.collapse_combined`` treats a load that was NOT supplied and a
load supplied as exactly 0 the same *numerically* — both evaluate at zero
stress, which is the uniaxial API 5C3 baseline rating. They are not the same
statement, though: the first must never be echoed back as a measured zero.

Before this regression suite the engine returned ``axial_stress_psi: 0.0`` /
``fyax_psi: 80000.0`` / ``internal_pressure_psi: 0.0`` for a run where no axial
load and no internal pressure were supplied, and the W13 tab displayed
``fyax=80,000 psi`` for it — an input the engineer never entered, persisted
into the run's ``result_values``.

Contract sources (all in-repo, no invention):

* ``core/engineering/result.require_number`` — "Never invent 0 for a missing
  engineering input" (and ``optional_number`` exists precisely to return None).
* ``core/engineering/casing_persistence.build_snapshot`` — "None optional loads
  are preserved as None so reconstruction reproduces the identical call".
* ``CasingEngine.evaluate`` — the von Mises check and every safety factor are
  gated on the load being supplied.

The rating numbers are deliberately NOT changed by this contract: an absent load
contributes zero stress, exactly as before. Only the *reported inputs* stop
claiming a value that was never supplied.
"""
from __future__ import annotations

import pytest

from core.engineering.engines.casing import CasingEngine

BASE = dict(od_in=9.625, wall_in=0.472, id_in=8.681, yield_psi=80000.0)


def test_absent_loads_are_reported_as_not_recorded():
    r = CasingEngine.evaluate(**BASE)
    assert r.success, r.error
    v = r.values
    assert v["axial_stress_psi"] is None
    assert v["fyax_psi"] is None
    assert v["internal_pressure_psi"] is None
    assert v["axial_tension_supplied"] is False
    assert v["internal_pressure_supplied"] is False
    # the uniaxial baseline rating is still reported (not None, not invented)
    assert v["collapse_uncorrected_psi"] == pytest.approx(v["collapse_combined_psi"])
    assert v["governing_collapse_psi"] == pytest.approx(4754.0, abs=1.0)


def test_explicit_zero_loads_remain_measured_zero():
    r = CasingEngine.evaluate(**BASE, axial_tension_lbf=0, internal_pressure_psi=0)
    assert r.success, r.error
    v = r.values
    assert v["axial_stress_psi"] == 0.0
    assert v["fyax_psi"] == pytest.approx(80000.0)
    assert v["internal_pressure_psi"] == 0.0
    assert v["axial_tension_supplied"] is True
    assert v["internal_pressure_supplied"] is True


def test_absent_and_explicit_zero_share_the_same_rating():
    """Documented equivalence: the distinction is reporting, not physics."""
    absent = CasingEngine.evaluate(**BASE)
    zero = CasingEngine.evaluate(**BASE, axial_tension_lbf=0, internal_pressure_psi=0)
    assert absent.value == zero.value
    assert absent.values["governing_collapse_psi"] == zero.values["governing_collapse_psi"]


def test_absent_loads_emit_explicit_warnings_and_evaluate_propagates_them():
    absent = CasingEngine.evaluate(**BASE)
    text = " ".join(absent.warnings)
    assert "Axial tension not supplied" in text
    assert "Internal pressure not supplied" in text
    # a supplied load must not warn about itself
    supplied = CasingEngine.evaluate(**BASE, axial_tension_lbf=50000, internal_pressure_psi=1000)
    text = " ".join(supplied.warnings)
    assert "Axial tension not supplied" not in text
    assert "Internal pressure not supplied" not in text
    assert "Internal pressure not supplied" in " ".join(
        CasingEngine.evaluate(**BASE, axial_tension_lbf=50000).warnings
    )


def test_supplied_loads_still_apply_fyax_and_pi():
    """Ground truth is unchanged by the reporting contract."""
    pc = CasingEngine.collapse(9.625, 0.472, 80000.0)
    assert pc.success, pc.error
    ten = CasingEngine.evaluate(**BASE, axial_tension_lbf=100000)
    # tension derates the collapse rating below the uniaxial baseline
    assert ten.values["collapse_combined_psi"] < pc.value
    assert ten.values["fyax_psi"] < 80000.0
    assert ten.values["axial_stress_psi"] > 0
    # compression raises it (sign of the 0.5z term flips)
    comp = CasingEngine.evaluate(**BASE, axial_tension_lbf=-100000)
    assert comp.values["collapse_combined_psi"] > pc.value
    # internal pressure adds the Pi(1 - 2t/D) addendum
    pi = 1000.0
    with_pi = CasingEngine.evaluate(**BASE, internal_pressure_psi=pi)
    assert with_pi.values["collapse_combined_psi"] == pytest.approx(
        pc.value + pi * (1.0 - 2.0 * 0.472 / 9.625), abs=0.1
    )
    # direct call: same distinction, no evaluate() layer involved
    direct = CasingEngine.collapse_combined(9.625, 0.472, 80000.0)
    assert direct.success, direct.error
    assert direct.values["fyax_psi"] is None
    assert direct.values["internal_pressure_psi"] is None
    explicit = CasingEngine.collapse_combined(9.625, 0.472, 80000.0, axial_tension_lbf=0)
    assert explicit.values["fyax_psi"] == pytest.approx(80000.0)
