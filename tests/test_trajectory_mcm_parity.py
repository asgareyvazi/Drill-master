"""Trajectory Minimum-Curvature parity against an independent textbook
implementation (randomized, deterministic seed). Guards the canonical
TrajectoryEngine against silent formula regressions."""
import math
import random

import pytest

from core.engineering.core import TrajectoryEngine


def ref_mcm_step(inc1, azi1, inc2, azi2, dmd):
    """Independent textbook MCM step (Bourgoyne et al.)."""
    I1, I2 = math.radians(inc1), math.radians(inc2)
    A1, A2 = math.radians(azi1), math.radians(azi2)
    c = math.cos(I1) * math.cos(I2) + math.sin(I1) * math.sin(I2) * math.cos(A2 - A1)
    c = max(-1.0, min(1.0, c))
    dl = math.acos(c)
    rf = 1.0 if dl == 0 else 2.0 / dl * math.tan(dl / 2.0)
    return dict(
        dls=math.degrees(dl) / dmd * 30.0,
        tvd=0.5 * dmd * (math.cos(I1) + math.cos(I2)) * rf,
        north=0.5 * dmd * (math.sin(I1) * math.cos(A1) + math.sin(I2) * math.cos(A2)) * rf,
        east=0.5 * dmd * (math.sin(I1) * math.sin(A1) + math.sin(I2) * math.sin(A2)) * rf,
    )


def test_mcm_matches_independent_implementation_random_surveys():
    random.seed(7)
    worst = 0.0
    for _ in range(300):
        i1, a1 = random.uniform(0, 90), random.uniform(0, 360)
        i2, a2 = random.uniform(0, 90), random.uniform(0, 360)
        dmd = random.uniform(10, 500)
        ref = ref_mcm_step(i1, a1, i2, a2, dmd)
        pts = TrajectoryEngine.calculate(
            [{"md": 0.0, "inc": i1, "azi": a1},
             {"md": dmd, "inc": i2, "azi": a2}], vs_azimuth=0.0)
        p2 = pts[-1]
        diff = max(abs(p2.tvd - ref["tvd"]), abs(p2.north - ref["north"]),
                   abs(p2.east - ref["east"]), abs(p2.dls - ref["dls"]))
        worst = max(worst, diff)
    assert worst < 1e-9


def test_mcm_horizontal_dogleg_case():
    # classic horizontal build: 0° → 90° over 300 m = 9°/30m DLS
    pts = TrajectoryEngine.calculate(
        [{"md": 0.0, "inc": 0.0, "azi": 0.0},
         {"md": 300.0, "inc": 90.0, "azi": 0.0}])
    p2 = pts[-1]
    assert p2.dls == 9.0
    # MCM balanced-tangent over a 90° arc: ΔTVD = ΔN = 0.5·L·RF, RF = 4/π
    assert p2.tvd == pytest.approx(600.0 / math.pi, abs=1e-9)
    assert p2.north > 0 and abs(p2.east) < 1e-9
