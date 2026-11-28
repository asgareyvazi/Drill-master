"""M482 follow-up (M494): numeric consistency of the ``erge-2015`` transition band with the SECONDARY reference.

The reference is BoreTHM ``src/borethm/fluids.py`` ``transition_band`` (Apache-2.0, commit 25f9a8e), which cites
Erge et al. 2015, SPE Drill. Complet. 30(3) 257-271, eqs. 17-18. It is re-typed here independently of the engine
(nothing is imported from ``core.hydraulics_hb_slot`` to build the expected values):

    Re1 = 2100 [N^0.331 (1 + 1.402 k - 0.977 k^2) - 0.019 e N^-0.868 k]      (eq. 17, 0.1 < N < 1)
    Re2 = 2900 clip(N, 0.15, 0.4)^(-0.039 Re1^0.307)                           (eq. 18, fitted at k = 0.5)

Agreement with a secondary source is NOT a verification against the primary paper: ``erge-2015`` stays in
``UNVERIFIED_CRITERIA`` (owner decision / primary-source check still open). Differences that are by design:

* the engine is concentric only (e = 0), so the eccentricity term is not exercised;
* BoreTHM clips N into [0.15, 0.4] for Re2; the engine refuses (NOT_ASSESSED) above Re1 outside that range instead
  of extrapolating, so the comparison is made only inside the fitted range.
"""
from __future__ import annotations

import pytest

from core import hydraulics_hb_slot as hb


def _borethm_reference(n: float, kappa: float, e: float = 0.0):
    re1 = 2100.0 * (n ** 0.331 * (1.0 + 1.402 * kappa - 0.977 * kappa ** 2) - 0.019 * e * n ** -0.868 * kappa)
    n_clipped = min(max(n, 0.15), 0.4)
    re2 = 2900.0 * n_clipped ** (-0.039 * re1 ** 0.307)
    return re1, re2


@pytest.mark.parametrize("n", [0.16, 0.2, 0.25, 0.3, 0.35, 0.39])
@pytest.mark.parametrize("kappa", [0.2, 0.35, 0.5, 0.65, 0.8])
def test_erge_band_matches_secondary_reference_inside_fitted_range(n, kappa):
    re1, re2 = hb.transition_band("erge-2015", n, kappa)
    ref1, ref2 = _borethm_reference(n, kappa)
    assert re1 == pytest.approx(ref1, rel=1e-12)
    assert re2 == pytest.approx(ref2, rel=1e-12)
    assert re1 < re2


def test_erge_spot_value_hand_computed():
    # n' = 0.3, kappa = 0.5: Re1 = 2100 * 0.3^0.331 * (1 + 0.701 - 0.24425) = 2100 * 0.67132... * 1.45675 = 2053.67
    re1, re2 = hb.transition_band("erge-2015", 0.3, 0.5)
    assert re1 == pytest.approx(2053.67, abs=0.01)
    assert re2 == pytest.approx(2900.0 * 0.3 ** (-0.039 * re1 ** 0.307), rel=1e-12)


def test_founargiotakis_band_matches_secondary_reference():
    for n in (0.2, 0.5, 0.8, 1.0):
        assert hb.transition_band("founargiotakis-2008", n, 0.5) == pytest.approx((3250 - 1150 * n, 4150 - 1150 * n))


def test_erge_stays_marked_not_verified():
    assert "erge-2015" in hb.UNVERIFIED_CRITERIA
    assert "NOT VERIFIED" in hb.UNVERIFIED_CRITERIA["erge-2015"]
