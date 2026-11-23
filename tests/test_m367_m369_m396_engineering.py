"""M367 / M369 / M396: T&D buckling finding (D93), anti-collision closest approach (D94), benchmark gate.

SYNTHETIC data only; expected values are closed forms written here.
"""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pytest

from core.engineering.engines.anti_collision import AntiCollisionEngine
from core.engineering.engines.torque_drag import TorqueDragEngine

ROOT = Path(__file__).resolve().parents[1]
REF = [{"md": md, "north": 0.0, "east": 0.0, "tvd": md} for md in (0.0, 500.0, 1000.0)]
SKEW = [{"md": 0.0, "north": -50.0, "east": 20.0, "tvd": 0.0}, {"md": 141.42, "north": 50.0, "east": 20.0, "tvd": 100.0}]


# ---- D94 --------------------------------------------------------------------------------------------------
def test_d94_geometric_closest_approach_is_reported_and_warned_when_smaller():
    r = AntiCollisionEngine.screen_clearance(REF[:2], SKEW, coordinates_unit="m")
    v = r.values
    assert v["closest_approach_3d"]["distance"] == pytest.approx(20.0, abs=1e-6)       # the vertical line x=y=0 vs E=20
    assert v["minimum_separation"] > 27.0                                              # common-MD value unchanged
    assert v["minimum_separation_conservative"] == pytest.approx(20.0, abs=1e-6)
    assert any(w.startswith("D94:") for w in r.warnings)
    # closest point: the offset crosses north 0 at t = 0.5 → offset MD 70.71, TVD 50 → reference MD 50
    assert v["closest_approach_3d"]["offset_md"] == pytest.approx(70.71, abs=1e-3)
    assert v["closest_approach_3d"]["ref_md"] == pytest.approx(50.0, abs=1e-6)


def test_d94_no_warning_when_the_scans_agree():
    parallel = [{"md": md, "north": 10.0, "east": 0.0, "tvd": md} for md in (0.0, 500.0, 1000.0)]
    r = AntiCollisionEngine.screen_clearance(REF, parallel, coordinates_unit="m")
    assert r.values["closest_approach_3d"]["distance"] == pytest.approx(10.0)
    assert not any(w.startswith("D94:") for w in r.warnings)
    assert r.values["uncertainty"]["iscwsa_applied"] is False                           # never an ISCWSA SF


@pytest.mark.parametrize("p0,p1,q0,q1,expected", [
    ((0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0), 1.0),                                  # parallel
    ((0, 0, 0), (1, 0, 0), (0.5, -1, 1), (0.5, 1, 1), 1.0),                             # crossing, 1 above
    ((0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0), 1.0),                                  # collinear, gap 1
    ((0, 0, 0), (0, 0, 0), (3, 4, 0), (3, 4, 0), 5.0),                                  # two points
])
def test_segment_closest_distance_exact_cases(p0, p1, q0, q1, expected):
    assert AntiCollisionEngine._segment_closest(p0, p1, q0, q1)[0] == pytest.approx(expected)


# ---- D93 --------------------------------------------------------------------------------------------------
VERTICAL = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 2000.0, "inc": 0.0, "azi": 0.0}]
STRING = [{"component": "DC", "od_in": 6.5, "id_in": 2.8125, "length_m": 200.0, "weight_ppf": 90.0},
          {"component": "DP", "od_in": 5.0, "id_in": 4.276, "length_m": 1800.0, "weight_ppf": 19.5}]


def test_d93_vertical_collars_under_5_klbf_are_not_helically_buckled():
    """Lubinski vertical critical load 1.94 (E I w²)^(1/3) ≈ 9 klbf for a 6.5 x 2.8125 in collar in 10 ppg mud."""
    survey, bha = VERTICAL, STRING
    ixx = math.pi / 64 * (6.5 ** 4 - 2.8125 ** 4)
    w = 90.0 / 12 * (1 - 10.0 / 65.5)
    lubinski = 1.94 * (30e6 * ixx * w ** 2) ** (1 / 3)
    assert lubinski > 5000.0
    v = TorqueDragEngine.calculate(survey, bha, 10.0, 0.25, wob_klbf=5.0, wellbore_id_in=8.5).values
    assert all(row["flag"] != "helical" for row in v["buckling"]["details"])
    dc = v["buckling"]["details"][0]
    assert dc["component"] == "DC" and dc["criterion"] == "vertical_lubinski"
    assert dc["f_sin_lbf"] == pytest.approx(lubinski, abs=1.0)
    assert v["buckling"]["version"] == "v2"


def test_d93_v1_reproduces_the_defective_flag_for_replay_only():
    v1 = TorqueDragEngine.calculate(VERTICAL, STRING, 10.0, 0.25, wob_klbf=5.0, wellbore_id_in=8.5,
                                    buckling_version="v1")
    assert v1.values["method"] == TorqueDragEngine.SEGMENTED_V1_METHOD
    assert "version" not in v1.values["buckling"]                                       # exact pre-M367 shape
    assert v1.values["buckling"]["details"][0]["flag"] == "helical"                     # the D93 defect, pinned


def test_d93_inclined_hole_keeps_dawson_paslay_when_it_governs():
    survey = [{"md": 0.0, "inc": 60.0, "azi": 0.0}, {"md": 1000.0, "inc": 60.0, "azi": 0.0}]
    pipe = [{"component": "DP", "od_in": 5.0, "id_in": 4.276, "length_m": 1000.0, "weight_ppf": 19.5}]
    a = TorqueDragEngine.calculate(survey, pipe, 10.0, 0.3, wob_klbf=20.0, wellbore_id_in=8.5).values["buckling"]
    b = TorqueDragEngine.calculate(survey, pipe, 10.0, 0.3, wob_klbf=20.0, wellbore_id_in=8.5,
                                   buckling_version="v1").values["buckling"]
    assert a["details"][0]["criterion"] == "dawson_paslay"
    assert a["details"][0]["f_sin_lbf"] == b["details"][0]["f_sin_lbf"]
    ixx = math.pi / 64 * (5.0 ** 4 - 4.276 ** 4)
    w = 19.5 / 12 * (1 - 10.0 / 65.5)
    assert a["details"][0]["f_sin_lbf"] == pytest.approx(2 * math.sqrt(30e6 * ixx * w * math.sin(math.radians(60))
                                                                       / ((8.5 - 5.0) / 2)), abs=1.0)


def test_d93_saved_runs_replay_with_the_buckling_they_were_produced_with():
    from core.engineering.torque_drag_persistence import build_snapshot, recalculate_from_snapshot

    def snap(method):
        ui = [{"type": c["component"], "od": c["od_in"], "id": c["id_in"], "length": c["length_m"],
               "weight": c["weight_ppf"]} for c in STRING]
        return build_snapshot(survey=VERTICAL, components=ui, mud_density_ppg=10.0, friction_factor=0.25,
                                    wob_klbf=5.0, wellbore_id_in=8.5, method=method)

    old = recalculate_from_snapshot(snap(TorqueDragEngine.SEGMENTED_V1_METHOD))
    new = recalculate_from_snapshot(snap(TorqueDragEngine.METHOD))
    legacy = recalculate_from_snapshot(snap(TorqueDragEngine.LEGACY_METHOD))
    assert old.values["method"] == TorqueDragEngine.SEGMENTED_V1_METHOD and old.values["buckling"]["details"][0]["flag"] == "helical"
    assert new.values["method"] == TorqueDragEngine.METHOD and new.values["buckling"]["details"][0]["flag"] != "helical"
    assert legacy.values["method"] == TorqueDragEngine.LEGACY_METHOD and "version" not in legacy.values["buckling"]


def test_d93_legacy_method_refuses_buckling_v2():
    r = TorqueDragEngine.calculate(VERTICAL, STRING, 10.0, 0.25, max_segment_m=None, buckling_version="v2")
    assert not r.success and "buckling v1" in r.error


# ---- M396 benchmark gate ----------------------------------------------------------------------------------
def test_m396_benchmarks_all_within_tolerance_and_table_unchanged():
    out = subprocess.run([sys.executable, "tools/quality/benchmark_m396.py", "--check"], cwd=ROOT,
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]
    assert "0 outside tolerance" in out.stdout


def test_d93_m318_sweep_versions_pin_their_buckling():
    from core import torque_drag_sensitivity as tds
    from core.survey_revisions import stations_sha256

    run = {"survey": VERTICAL, "components": STRING, "mud_density_ppg": 10.0, "wob_klbf": 5.0, "wellbore_id_in": 8.5,
           "survey_source": {"revision_id": 7, "revision": 1, "stations_sha256": stations_sha256(VERTICAL)}}
    v2 = tds.sweep(run, [0.25], version=tds.SEGMENTED_VERSION)
    v3 = tds.sweep(run, [0.25])
    assert v2["engine_method"] == TorqueDragEngine.SEGMENTED_V1_METHOD and v2["rows"][0]["buckling"] is True
    assert v3["engine_method"] == TorqueDragEngine.METHOD and v3["method_version"] == tds.METHOD_VERSION
    assert v3["rows"][0]["buckling"] is False                                            # no D93 false flag
