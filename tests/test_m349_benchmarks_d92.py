"""M349 benchmarks and D92 (T&D integration resolution followed the drill-string entries).

D92: every drill-string entry was integrated as ONE element, its inclination the mean of its ends, so one 3,048 m
pipe entry through a build-and-turn well read slack-off +18.5 % and torque −19.6 % against a converged
integration, and the answer changed with the way the same pipe was typed in. The engine now integrates segments
of ≤ 5 m. Runs and M318 cases saved with the old method are recalculated with the old method (never re-labelled).
"""
from __future__ import annotations

import math

import pytest

from core import history_replay as hr
from core import torque_drag_sensitivity as tds
from core.engineering.engines.torque_drag import MAX_SEGMENT_M, TorqueDragEngine
from tools.quality import benchmark_m349 as bm

BUILD = bm.BUILD


def _string(entries):
    return bm._string(entries)


def test_benchmark_evidence_is_current_and_every_case_is_inside_its_tolerance():
    assert bm.main(["--check"]) == 0
    report = bm.run()
    assert report["failed"] == 0 and report["total"] >= 40
    assert {c["group"] for c in report["cases"]} == {"M314", "M317", "M318"}


def test_answer_does_not_depend_on_how_the_pipe_was_entered():
    results = [TorqueDragEngine.calculate(BUILD, _string(n), 10.0, 0.3).values for n in (1, 7, 10, 100)]
    for key in ("hookload_pickup", "hookload_slackoff", "surface_torque_rotating_ft_lbf"):
        values = [r[key] for r in results]
        assert max(values) / min(values) - 1 < 0.001, (key, values)


def test_converges_to_the_fine_step_reference():
    ref = bm._reference_integration(BUILD, 0.3)
    v = TorqueDragEngine.calculate(BUILD, _string(1), 10.0, 0.3).values
    assert v["hookload_slackoff"] == pytest.approx(ref["slackoff"], rel=0.001)
    assert v["surface_torque_rotating_ft_lbf"] == pytest.approx(ref["torque"], rel=0.001)
    assert v["method"] == TorqueDragEngine.METHOD and "5 m" in TorqueDragEngine.METHOD and MAX_SEGMENT_M == 5.0


def test_slant_hole_closed_form():
    survey = [{"md": 0, "inc": 45, "azi": 0}, {"md": 2000, "inc": 45, "azi": 0}]
    comps = [{"name": "DP", "od": 5.0, "id": 4.276, "length": 2000.0, "weight": 19.5}]
    weight = 19.5 * 2000 / 0.3048 * (1 - 10 / 65.5)
    v = TorqueDragEngine.calculate(survey, comps, 10.0, 0.25).values
    s = math.sin(math.radians(45))
    assert v["hookload_pickup"] == pytest.approx(weight * (s + 0.25 * s) / 1000, abs=0.006)
    assert v["hookload_slackoff"] == pytest.approx(weight * (s - 0.25 * s) / 1000, abs=0.006)
    assert v["surface_torque_rotating_ft_lbf"] == pytest.approx(0.25 * weight * s * 5 / 24, abs=0.06)


def test_legacy_method_is_the_old_whole_entry_integration_and_is_named():
    v = TorqueDragEngine.calculate(BUILD, _string(1), 10.0, 0.3, max_segment_m=None).values
    assert v["method"] == TorqueDragEngine.LEGACY_METHOD
    # one entry = one element at the mean inclination (30°): the old numbers are reproduced exactly
    weight = 19.5 * 3048 / 0.3048 * (1 - 10 / 65.5)
    assert v["hookload_slackoff"] == pytest.approx(weight * (math.cos(math.radians(30)) - 0.15) / 1000, abs=0.006)
    refused = TorqueDragEngine.calculate(BUILD, _string(1), 10.0, 0.3, max_segment_m=0)
    assert not refused.success and "max_segment_m" in refused.error


def test_profiles_keep_one_row_per_entry_and_side_force_is_the_entry_total():
    comps = [dict(c, component_name=c["name"]) for c in _string(3)]
    fine = TorqueDragEngine.calculate(BUILD, comps, 10.0, 0.3, wellbore_id_in=8.5).values
    assert [p["component"] for p in fine["tension_profile"]] == [c["name"] for c in reversed(comps)]
    assert len(fine["buckling"]["details"]) == 3
    assert {d["component"] for d in fine["buckling"]["details"]} == {c["name"] for c in comps}
    assert all("_component_index" not in d for d in fine["buckling"]["details"])
    legacy = TorqueDragEngine.calculate(BUILD, comps, 10.0, 0.3, max_segment_m=None).values
    assert len(legacy["side_force_profile"]) == len(fine["side_force_profile"]) == 3


def test_same_name_entries_keep_separate_buckling_rows():
    comps = [dict(c, component_name="DP") for c in _string(2)]
    details = TorqueDragEngine.calculate(BUILD, comps, 10.0, 0.3, wellbore_id_in=8.5).values["buckling"]["details"]
    assert len(details) == 2


def test_saved_legacy_run_recalculates_with_the_legacy_method():
    from core.engineering import torque_drag_persistence as tp

    legacy = TorqueDragEngine.calculate(BUILD, _string(1), 10.0, 0.3, max_segment_m=None).values
    current = TorqueDragEngine.calculate(BUILD, _string(1), 10.0, 0.3).values
    snapshot = {"method": TorqueDragEngine.LEGACY_METHOD, "survey": BUILD, "components": _string(1),
                "parameters": {"mud_density_ppg": 10.0, "friction_factor": 0.3}}
    assert tp.recalculate_from_snapshot(snapshot).values == legacy
    assert tp.recalculate_from_snapshot(dict(snapshot, method=TorqueDragEngine.METHOD)).values == current
    assert legacy["hookload_slackoff"] != current["hookload_slackoff"]


def _sweep_run():
    from core.survey_revisions import stations_sha256
    from core.w13_weight import engine_components

    pin = {"revision_id": 7, "revision": 2, "stations_sha256": stations_sha256(BUILD)}
    pipes = [{"name": "SYN DP", "od": 5.0, "id": 4.276, "length": 3048.0, "weight": 19.5}]
    return {"survey": BUILD, "components": engine_components(pipes), "mud_density_ppg": 10.0, "wob_klbf": 0.0,
            "wellbore_id_in": None, "survey_source": pin}


def test_m318_v1_case_replays_with_v1_and_v2_is_the_default():
    run = _sweep_run()
    v1 = tds.sweep(run, [0.3], version=tds.LEGACY_VERSION)
    v2 = tds.sweep(run, [0.3])
    assert v1["method_version"] == tds.LEGACY_VERSION and v1["engine_method"] == TorqueDragEngine.LEGACY_METHOD
    assert v2["method_version"] == tds.METHOD_VERSION and v2["engine_method"] == TorqueDragEngine.METHOD
    assert v1["rows"][0]["slackoff"] != v2["rows"][0]["slackoff"]
    with pytest.raises(tds.SensitivityError, match="not available"):
        tds.sweep(run, [0.3], version="M318 v0")
    inputs, results = tds.case_payload(v1, {})
    assert hr.reproducibility(tds.METHOD_ID, inputs, tds.LEGACY_VERSION)[0] == "REPRODUCIBLE"
    outcome = hr.verify(None, tds.METHOD_ID, inputs, results, tds.LEGACY_VERSION)
    assert outcome["status"] == "MATCH", outcome
    # the same v1 numbers claimed as v2 are a difference, never a silent match
    outcome = hr.verify(None, tds.METHOD_ID, inputs, results, tds.METHOD_VERSION)
    assert outcome["status"] == "DIFFERENT"


def test_buckling_row_of_an_entry_is_its_worst_segment():
    """Slack-off through a horizontal well without WOB: compression is zero at the bit and peaks at the heel, so the
    worst segment of one long entry is not its first. The entry row must equal the worst of the same segments typed
    in as separate entries."""
    survey = [{"md": 0, "inc": 0, "azi": 0}, {"md": 600, "inc": 0, "azi": 0}, {"md": 1500, "inc": 90, "azi": 0},
              {"md": 3000, "inc": 90, "azi": 0}]
    one = [{"name": "DP", "od": 5.0, "id": 4.276, "length": 3000.0, "weight": 19.5}]
    pieces = [{"name": "DP", "od": 5.0, "id": 4.276, "length": 5.0, "weight": 19.5}] * 600
    single = TorqueDragEngine.calculate(survey, one, 10.0, 0.4, wellbore_id_in=8.5).values["buckling"]["details"]
    many = TorqueDragEngine.calculate(survey, pieces, 10.0, 0.4, wellbore_id_in=8.5).values["buckling"]["details"]
    worst = max(many, key=lambda d: d["compression_lbf"])
    assert worst is not many[0] and worst["compression_lbf"] > many[0]["compression_lbf"]
    assert len(single) == 1 and single[0]["compression_lbf"] == worst["compression_lbf"]
    assert single[0]["md_top_m"] == worst["md_top_m"]
