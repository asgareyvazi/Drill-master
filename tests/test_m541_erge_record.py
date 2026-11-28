"""M541-M545: the Erge 2015 citation record names both candidate papers; the coefficients stay NOT VERIFIED and the
numbers (and therefore old cases) are unchanged."""
from __future__ import annotations

import pytest

from core import hydraulics_hb_slot as hb
from core import method_catalogue as mc


def test_erge_note_names_both_papers_and_stays_not_verified():
    note = hb.UNVERIFIED_CRITERIA["erge-2015"]
    assert "NOT VERIFIED" in note and "unresolved" in note
    assert "10.2118/167950-PA" in note and "30(3) 257-271" in note
    assert "10.1016/j.petrol.2015.02.007" in note and "128:128-139" in note
    assert "secondary" in note


def test_m416_catalogue_reference_flags_erge_as_not_verified():
    entry = next(e for e in mc.catalogue() if e.method_id == hb.METHOD_ID)
    assert "NOT VERIFIED" in entry.reference
    assert entry.version == hb.METHOD_VERSION


@pytest.mark.parametrize("n_index,kappa", [(0.3, 0.5), (0.6, 0.7)])
def test_erge_band_numbers_unchanged(n_index, kappa):
    """The Re1 formula as transcribed (e = 0); retyped here independently of the engine."""
    re1 = 2100.0 * (n_index ** 0.331 * (1 + 1.402 * kappa - 0.977 * kappa ** 2))
    assert hb.transition_band("erge-2015", n_index, kappa)[0] == pytest.approx(re1, rel=1e-12)
