"""Independent oracle for the casing VME check and method-ID semantics (M43 closure, Phase 5).

The oracle does not reuse the engine's closed forms:
* Lame thick-wall stresses come from solving the boundary-value problem
  sigma_r(r) = A - B/r^2 with sigma_r(ri) = -pi and sigma_r(ro) = -pe as a 2x2
  linear system (Cramer), then sigma_theta(ri) = A + B/ri^2;
* the capped-end axial stress comes from a free-body force balance on the caps;
* VME is sqrt(3 J2) of the deviatoric stress tensor, not the difference formula.

Pipe-body screening only (no connection, wear, temperature or full casing
integrity). Synthetic inputs.
"""

from __future__ import annotations

import math

import pytest

from core.engineering.engines.casing import CasingEngine

ROUNDED = 0.06  # engine values are rounded to 0.1 psi
OLD_METHOD = "API TR 5C3 pipe-body subset (Barlow + four-regime + fyax + VME)"  # before the capped-end pi fix


def _oracle(od, id_, pi, pe, fax, capped=True):
    ro, ri = od / 2.0, id_ / 2.0
    # [1, -1/ri^2] [A]   [-pi]
    # [1, -1/ro^2] [B] = [-pe]
    a11, a12, a21, a22 = 1.0, -1.0 / ri ** 2, 1.0, -1.0 / ro ** 2
    det = a11 * a22 - a12 * a21
    big_a = (-pi * a22 - a12 * -pe) / det
    big_b = (a11 * -pe - -pi * a21) / det
    sigma_r = big_a - big_b / ri ** 2
    sigma_h = big_a + big_b / ri ** 2
    wall_area = math.pi * (ro ** 2 - ri ** 2)
    cap_force = (pi * math.pi * ri ** 2 - pe * math.pi * ro ** 2) if capped else 0.0
    sigma_a = (fax + cap_force) / wall_area
    stresses = (sigma_r, sigma_h, sigma_a)
    mean = sum(stresses) / 3.0
    j2 = 0.5 * sum((s - mean) ** 2 for s in stresses)
    return {"sigma_radial_psi": sigma_r, "sigma_hoop_psi": sigma_h, "sigma_axial_psi": sigma_a,
            "vme_psi": math.sqrt(3.0 * j2)}


CASES = [
    # od, id, yield, pi, pe, tension, capped
    (9.625, 8.681, 80_000.0, 3_000.0, 0.0, 0.0, True),         # internal pressure only
    (9.625, 8.681, 80_000.0, 0.0, 4_000.0, 0.0, True),         # external pressure only
    (7.0, 6.276, 110_000.0, 0.0, 0.0, 250_000.0, True),        # tension only
    (9.625, 8.681, 80_000.0, 8_000.0, 6_000.0, 200_000.0, True),
    (13.375, 12.415, 55_000.0, 2_500.0, 1_000.0, -50_000.0, True),  # compression
    (9.625, 8.681, 80_000.0, 8_000.0, 6_000.0, 200_000.0, False),   # no end caps
]


@pytest.mark.parametrize("od,id_,yp,pi,pe,fax,capped", CASES)
def test_vme_matches_an_independent_lame_force_balance_tensor_oracle(od, id_, yp, pi, pe, fax, capped):
    result = CasingEngine.triaxial_vme(od, id_, yp, pi, pe, fax, include_capped_end=capped)
    assert result.success, result.error
    expected = _oracle(od, id_, pi, pe, fax, capped)
    for key, value in expected.items():
        assert result.values[key] == pytest.approx(value, abs=ROUNDED), key
    assert result.values["utilization"] == pytest.approx(expected["vme_psi"] / yp, abs=1e-4)


def test_thin_wall_limit_internal_pressure_capped():
    """D/t = 200: Lame tends to Barlow (sigma_h = pD/2t, capped sigma_a = pD/4t)."""
    od, t, pi = 20.0, 0.1, 100.0
    result = CasingEngine.triaxial_vme(od, od - 2 * t, 50_000.0, pi, 0.0, 0.0)
    barlow = pi * od / (2 * t)
    assert result.values["sigma_hoop_psi"] == pytest.approx(barlow, rel=0.01)
    assert result.values["sigma_axial_psi"] == pytest.approx(barlow / 2, rel=0.02)


# ------------------------------------------------------------ method ID

def test_current_method_id_is_pinned():
    """Changing CasingEngine.METHOD invalidates the method of every saved run; it must be deliberate."""
    assert CasingEngine.METHOD == "API TR 5C3 pipe-body subset (Barlow + four-regime + fyax + VME; capped-end r2)"
    assert CasingEngine.METHOD != OLD_METHOD


def test_run_saved_under_the_old_method_keeps_its_id_and_verifies_as_different():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from core.database import Base, DatabaseManager
    from core.repositories.casing_repository import CasingCalculationRepository

    manager = DatabaseManager()
    manager.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                                   poolclass=StaticPool)
    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(bind=manager.engine, autoflush=False, autocommit=False)
    repo = CasingCalculationRepository(manager)

    inputs = dict(od_in=9.625, id_in=8.681, wall_in=0.472, yield_psi=80_000.0, internal_pressure_psi=8_000.0,
                  external_pressure_psi=6_000.0, axial_tension_lbf=200_000.0, grade="N-80", weight_ppf=47.0)
    current = CasingEngine.evaluate(**inputs).values
    # The pre-fix engine divided the cap force by the wall area WITHOUT pi.
    ro, ri = 9.625 / 2, 8.681 / 2
    wall = math.pi * (ro ** 2 - ri ** 2)
    old_capped = (8_000.0 * ri ** 2 - 6_000.0 * ro ** 2) / (math.pi * (ro ** 2 - ri ** 2))
    old_axial = 200_000.0 / wall + old_capped
    sr, sh = current["vme_sigma_radial_psi"], current["vme_sigma_hoop_psi"]
    old_vme = math.sqrt(0.5 * ((sh - old_axial) ** 2 + (old_axial - sr) ** 2 + (sr - sh) ** 2))
    legacy = dict(current, vme_capped_end_psi=round(old_capped, 1), vme_sigma_axial_psi=round(old_axial, 1),
                  vme_vme_psi=round(old_vme, 1), vme_psi=round(old_vme, 1))
    assert abs(legacy["vme_psi"] - current["vme_psi"]) > 100.0  # the fix is material here

    run_id = repo.save_run(inputs=inputs, result_values=legacy, method=OLD_METHOD, label="legacy")
    saved = repo.get(run_id)
    assert saved.method == OLD_METHOD  # never re-stamped with the current ID
    outcome = saved.verify(current_method=CasingEngine.METHOD)
    assert outcome.method_matches is False
    assert outcome.status == "DIFFERENT"
    assert {"vme_psi", "vme_sigma_axial_psi"} <= {d["path"] for d in outcome.all_differences}
    again = repo.get(run_id)  # verification is observational
    assert again.method == OLD_METHOD and again.result["vme_psi"] == legacy["vme_psi"]
