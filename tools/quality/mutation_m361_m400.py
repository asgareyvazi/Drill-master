#!/usr/bin/env python3
"""Repeatable mutation run for M361-M400 (M389): M365 D87 identity pinning, M366 hydraulics workflow, M370 hole
cleaning, M367 / D93 vertical-aware buckling with replay pinning, M369 / D94 geometric closest approach, M374 W12 KPI
structural definitions and M377 CI run-state classification.

Same engine and rules as ``tools/quality/mutation_m321_m360.py`` (``tools/quality/mutation_m46.py``): one realistic
defect per mutant in a scratch copy, the listed tests must KILL it, an anchor that does not match exactly once is
INVALID, ``--only`` never gives complete=True, EQUIVALENT mutants are declared with the reason and still executed.
Mutation results show which defects the tests detect; they are not a proof of correctness.

Usage::

    python tools/quality/mutation_m361_m400.py [--json OUT] [--only ID[,ID...]]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

HW = "core/hydraulics_workflow.py"
RI = "core/record_identity.py"
WB = "core/calculation_workbench.py"
CC = "core/calculation_clone_contract.py"
CA = "core/calculation_cases.py"
TD = "core/engineering/engines/torque_drag.py"
TDP = "core/engineering/torque_drag_persistence.py"
TDS = "core/torque_drag_sensitivity.py"
AC = "core/engineering/engines/anti_collision.py"
AE = "core/analysis_evidence.py"
CRS = "tools/quality/ci_run_states.py"
SPD = "core/survey_plan_deviation.py"
CAL = "core/casing_axial_loads.py"

THW = ["tests/test_m366_hydraulics_workflow.py"]
TID = ["tests/test_m365_d87_identity.py", "tests/test_m303_m306_clone_contract_and_bulk.py"]
TENG = ["tests/test_m367_m369_m396_engineering.py"]
TKPI = ["tests/test_m374_w12_kpi_specs.py", "tests/test_m48_analysis_evidence.py"]
TCRS = ["tests/test_m377_ci_run_states.py"]
TSPD = ["tests/test_m368_survey_plan_deviation.py"]
TCAL = ["tests/test_m371_casing_axial_loads.py"]
TTD = TENG + ["tests/test_m349_benchmarks_d92.py", "tests/test_m318_td_friction_sensitivity.py"]

MUTANTS = [
    # ------------------------------------------------------------------ M366 hydraulics workflow
    Mutant("HW-budget-misclassified", HW, "    if text in BHA_TYPES:\n        return \"bha\"\n",
           "    if text in BHA_TYPES:\n        return \"drill_pipe\"\n", THW,
           "BHA losses are booked as drill-pipe losses in the pressure budget"),
    Mutant("HW-pump-limit-zero-is-limit", HW,
           "                               \"max_pressure_psi\": max_p if max_p and max_p > 0 else None,\n",
           "                               \"max_pressure_psi\": max_p if max_p is not None else None,\n", THW,
           "an un-entered pump limit (0 on the page) is treated as a 0 psi limit"),
    Mutant("HW-no-tolerance-classified", HW,
           "    if tolerance is None:\n        return {\"status\": \"NOT CLASSIFIED\",",
           "    if False:\n        return {\"status\": \"NOT CLASSIFIED\",", THW,
           "plan vs actual is classified without a declared tolerance"),
    Mutant("HW-replay-sha-skipped", HW,
           "    if values_sha256(snap[\"values\"]) != stored_sha:\n",
           "    if False:\n", THW, "a tampered frozen snapshot is replayed instead of UNREADABLE"),
    Mutant("HW-sweep-flow-not-proportional", HW,
           "            q = total_flow_gpm * page_q / page_total\n",
           "            q = total_flow_gpm\n", THW,
           "every pump is charged the whole sensitivity flow"),
    Mutant("HW-budget-closure-ignored", HW,
           "    closes = total is not None and abs(component_sum - total) <= max(rounding, 1e-6)\n",
           "    closes = total is not None\n", THW, "a budget that does not sum to the SPP is reported as closing"),
    # ------------------------------------------------------------------ M370 hole cleaning (CCI)
    Mutant("HW-cci-inclination-gate-dropped", HW, "        if max_inc > CCI_MAX_INCLINATION_DEG:\n",
           "        if False:\n", THW, "the vertical-hole CCI is reported for a 60° well"),
    Mutant("HW-cci-fann-ignored", HW, "    if t600 and t300 and t600 > 0 and t300 > 0:\n", "    if False:\n", THW,
           "entered Fann readings are ignored in favour of PV/YP"),
    Mutant("HW-cci-uses-mean-not-lowest-av", HW,
           "            \"hole_cleaning\": hole_cleaning(values, _min_av(result), getattr(engine.mud, \"mw_ppg\", None)),\n",
           "            \"hole_cleaning\": hole_cleaning(values, max(v for _n, v in result.annular_velocities), "
           "getattr(engine.mud, \"mw_ppg\", None)),\n", THW + TENG,
           "the index uses the fastest annulus instead of the slowest"),
    # ------------------------------------------------------------------ M365 D87 identity pinning
    Mutant("ID-mark-fingerprint-ignored", WB,
           "        if stored_fp is not None and prints.get(key) != stored_fp:\n",
           "        if False:\n", TID, "an equal-timestamp replacement row inherits the archive mark"),
    Mutant("ID-mark-fingerprint-not-stored", WB,
           "                   source_fingerprint=record_identity.fingerprint(entry.table, source),\n",
           "                   source_fingerprint=None,\n", TID, "new archive marks are timestamp-only again"),
    Mutant("ID-link-fingerprint-not-stored", CA,
           "        source_fingerprint=record_identity.fingerprint(table, source),      # M365 (D87): content identity pin\n",
           "        source_fingerprint=None,\n", TID, "new clone links are timestamp-only again"),
    Mutant("ID-match-ignores-born-after-link", CC,
           "        if born is not None and linked is not None and born > linked:\n",
           "        if False:\n", TID,
           "an identical-content row created after the link is VERIFIED as the clone source"),
    Mutant("ID-different-not-decisive", CC,
           "    if pinned == record_identity.DIFFERENT:            # M365 (D87): the content fingerprint is decisive "
           "when it differs\n",
           "    if False:\n", TID, "a changed source with the same timestamp is VERIFIED"),
    Mutant("ID-null-time-refusal-removed", WB,
           "        if action == ARCHIVE and identity_basis(entry.table, source) is None:\n",
           "        if False:\n", TID, "a NULL-time row of a table without a fingerprint contract can be archived"),
    Mutant("ID-compare-always-match", RI,
           "    return MATCH if fingerprint(table, row) == stored else DIFFERENT\n",
           "    return MATCH\n", TID, "fingerprint comparison never reports DIFFERENT"),
    Mutant("ID-mark-authorization-skipped", WB,
           "        authorize_change(auth, \"calculation_archive_marks\", \"insert\")     # raises AuthorizationError\n",
           "        pass\n", TID + ["tests/test_m286_m272_authorization.py"],
           "a user without the right writes archive marks"),
    # ------------------------------------------------------------------ M367 / D93 buckling v2 + replay pinning
    Mutant("TD-vertical-load-dropped", TD,
           "                f_sin, f_hel = max(f_sin, f_sin_v), max(f_hel, f_hel_v)\n",
           "                pass\n", TTD, "D93 regression: vertical collars under small WOB flagged helical"),
    Mutant("TD-vertical-coefficient-wrong", TD,
           "                f_sin_v, f_hel_v = 1.94 * cube, 5.55 * cube\n",
           "                f_sin_v, f_hel_v = 1.0 * cube, 5.55 * cube\n", TTD,
           "Lubinski coefficient 1.94 replaced by 1.0"),
    Mutant("TD-v2-default-is-v1", TD,
           "                buckling_version = BUCKLING_V1 if max_segment_m is None else BUCKLING_V2\n",
           "                buckling_version = BUCKLING_V1\n", TTD, "new runs keep the defective buckling thresholds"),
    Mutant("TDP-v1-run-replayed-with-v2", TDP,
           "    elif method == TorqueDragEngine.SEGMENTED_V1_METHOD:\n",
           "    elif False:\n", TTD, "a run saved before M367 is verified against buckling v2 (false DIFFERENT)"),
    Mutant("TDS-v2-case-replayed-with-v3", TDS,
           "    buckling = BUCKLING_V2 if version == METHOD_VERSION else BUCKLING_V1\n",
           "    buckling = BUCKLING_V2\n", TTD, "an M318 v2 sweep is replayed with buckling v2"),
    Mutant("TD-criterion-mislabelled", TD,
           "                if f_sin_v > f_sin:\n", "                if f_sin_v < f_sin:\n", TTD,
           "the governing buckling criterion is reported inverted"),
    # ------------------------------------------------------------------ M369 / D94 geometric closest approach
    Mutant("AC-3d-warning-dropped", AC,
           "            if closest_3d[\"distance\"] < closest[\"distance\"] * (1 - 1e-6) - 1e-9:\n",
           "            if False:\n", TENG, "a smaller geometric approach is not warned"),
    Mutant("AC-conservative-uses-common-md", AC,
           "                \"minimum_separation_conservative\": min(closest[\"distance\"], closest_3d[\"distance\"]),\n",
           "                \"minimum_separation_conservative\": closest[\"distance\"],\n", TENG,
           "the conservative separation ignores the geometric closest approach"),
    Mutant("AC-segment-clamp-dropped", AC,
           "                if t < 0.0:\n", "                if False:\n", TENG,
           "closest points outside the offset segment are accepted (distance too small)"),
    # ------------------------------------------------------------------ M374 W12 KPI structural definitions
    Mutant("KPI-spec-fields-not-shown", AE,
           "    lines += [f\"{field.capitalize()}: {spec[field]}\" for field in KPI_SPEC_FIELDS if spec.get(field)]\n",
           "    lines += []\n", TKPI, "the card tooltip drops window / scope / source / method / missing / counting"),
    # ------------------------------------------------------------------ M377 CI run states
    Mutant("CRS-timeout-annotation-ignored", CRS,
           "    if conclusion in (\"cancelled\", \"failure\") and TIMEOUT_ANNOTATION in notes:\n",
           "    if False:\n", TCRS, "a D88 timeout with stale job times is reported as an unexplained cancel"),
    Mutant("CRS-cancel-is-green", CRS,
           "        return {**out, \"state\": FAILURE, \"reason\": \"cancelled, neither superseded nor at the timeout "
           "(not a pass)\"}\n",
           "        return {**out, \"state\": SUCCESS, \"reason\": \"cancelled\"}\n", TCRS,
           "an unexplained cancel counts as green"),
    Mutant("CRS-other-workflow-supersedes", CRS,
           "             if o.get(\"workflowName\") == run.get(\"workflowName\") and o.get(\"headBranch\") == "
           "run.get(\"headBranch\")\n",
           "             if True\n", TCRS, "a newer run of another workflow or branch marks a cancel SUPERSEDED"),
    Mutant("CRS-best-job-wins", CRS,
           "        state = max((j[\"state\"] for j in jobs), key=_RANK.__getitem__)\n",
           "        state = min((j[\"state\"] for j in jobs), key=_RANK.__getitem__)\n", TCRS,
           "one green leg makes the run green"),
    # ------------------------------------------------------------------ M368 survey vs plan deviation
    Mutant("SPD-right-sign-flipped", SPD,
           "        right = _norm(_cross((0.0, 0.0, 1.0), tangent))\n",
           "        right = _norm(_cross(tangent, (0.0, 0.0, 1.0)))\n", TSPD, "left and right are swapped"),
    Mutant("SPD-reference-not-compared", SPD,
           "        if str(survey.get(key) or \"\").strip().lower() != str(refs[key] or \"\").strip().lower():\n",
           "        if False:\n", TSPD, "a survey in another datum / azimuth reference is compared with the plan"),
    Mutant("SPD-frame-prefix-skipped", SPD,
           "    problem = _same_prefix(_positions(pinned), actual, tie_md)\n",
           "    problem = None\n", TSPD, "a survey in another frame above the tie-in is compared"),
    Mutant("SPD-tolerance-defaulted", SPD,
           "    if tolerance_m is None:\n        row[\"status\"] = NO_TOLERANCE\n",
           "    if tolerance_m is None:\n        row[\"status\"] = WITHIN\n", TSPD,
           "no declared tolerance is reported WITHIN"),
    Mutant("SPD-replay-hash-unchecked", SPD,
           "    if snapshot_sha256(snap) != (inputs.get(\"snapshot_sha256\") or {}).get(\"value\"):\n",
           "    if False:\n", TSPD, "a tampered frozen snapshot is replayed"),
    Mutant("SPD-not-reached-as-miss", SPD,
           "    if near[\"md\"] >= actual[-1][\"md\"] - MD_TOLERANCE_M and coords[2] > actual[-1][\"tvd\"] + "
           "POSITION_TOLERANCE_M:\n",
           "    if False:\n", TSPD, "a target below the drilled depth is reported HIT / MISS"),
    # ------------------------------------------------------------------ M371 casing axial loads and wear
    Mutant("CAL-thermal-sign-flipped", CAL,
           "            COMPUTED, -v[\"youngs_modulus_psi\"] * v[\"expansion_per_degf\"]",
           "            COMPUTED, v[\"youngs_modulus_psi\"] * v[\"expansion_per_degf\"]", TCAL,
           "heating increases tension"),
    Mutant("CAL-ballooning-areas-swapped", CAL,
           "(a_in * v[\"delta_internal_psi\"] - a_out * v[\"delta_external_psi\"])",
           "(a_out * v[\"delta_internal_psi\"] - a_in * v[\"delta_external_psi\"])", TCAL,
           "ballooning uses the wrong areas"),
    Mutant("CAL-partial-sum-as-total", CAL,
           "    elif any(c[\"status\"] != COMPUTED for c in axial_parts + [comps[\"bending\"]]):\n",
           "    elif False:\n", TCAL, "a total is reported with a component not assessed"),
    Mutant("CAL-wear-ignored", CAL,
           "        wall = (od - idd) / 2.0 * (1.0 - v[\"wear_percent\"] / 100.0)\n",
           "        wall = (od - idd) / 2.0\n", TCAL, "the ratings ignore the declared wear"),
    Mutant("CAL-bending-diameter-not-halved", CAL,
           "        sigma_b = v[\"youngs_modulus_psi\"] * od / 2.0 * kappa\n",
           "        sigma_b = v[\"youngs_modulus_psi\"] * od * kappa\n", TCAL, "bending stress doubled"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
