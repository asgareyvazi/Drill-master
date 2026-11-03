#!/usr/bin/env python3
"""Repeatable mutation run for the M101-M120 guards.

Each mutant removes ONE guard (or swaps one rule) in a scratch copy of the working tree and must be KILLED
by the listed phase tests. Engine: ``tools/quality/mutation_m46.py`` (green baseline first; an anchor that
does not match exactly once is reported INVALID, never killed). The repository is never modified.

Usage::

    python tools/quality/mutation_m101_m120.py [--json OUT] [--only ID[,ID...]]

SYNTHETIC test data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

SR = "core/survey_revisions.py"
DP = "core/directional_plans.py"
TC = "core/trajectory_compare.py"
CP = "tabs/trajectory_compare_panel.py"
DB = "core/database.py"
T105 = ["tests/test_m105_survey_integrity.py", "tests/test_m105_survey_references.py"]

MUTANTS = [
    # ---- M105 survey derived-result integrity (D1) -------------------------------------------------
    Mutant("SR-field-set-unchecked", SR,
           "        if missing or extra:\n            issues.append(f\"station {index}: missing {missing} extra {extra}\")",
           "        if False:\n            issues.append(f\"station {index}: missing {missing} extra {extra}\")",
           T105, "a result station with a missing or extra field verifies as MATCH"),
    Mutant("SR-azimuth-not-wrapped", SR,
           "            if key == \"azi\":\n                delta = (delta + 180.0) % 360.0 - 180.0\n            worst[key]",
           "            if key == \"azi\":\n                delta = delta\n            worst[key]",
           T105, "an azimuth of 359.999999999 deg is reported as differing from 0 deg"),
    Mutant("SR-tolerance-loosened", SR,
           "            if abs(delta) > tol:",
           "            if abs(delta) > tol * 100:",
           T105, "a result field 10x outside its tolerance verifies as MATCH"),
    Mutant("SR-results-hash-not-checked", SR,
           "        return \"VERIFIED\" if results_sha256(json.loads(row.results_json)) == recorded else \"HASH MISMATCH\"",
           "        return \"VERIFIED\"",
           T105, "results edited after saving still read as hash VERIFIED"),
    Mutant("SR-save-hash-not-recorded", SR,
           "            results_sha256=results_sha256(results),\n            warnings_json=json.dumps(checked.warnings),",
           "            warnings_json=json.dumps(checked.warnings),",
           T105, "a new revision is saved without its results hash"),
    Mutant("SR-transform-hash-not-recorded", SR,
           "            results_sha256=results_sha256(results),\n            warnings_json=json.dumps([f\"Azimuths converted",
           "            warnings_json=json.dumps([f\"Azimuths converted",
           T105, "an azimuth-converted revision is saved without its results hash"),
    # ---- M105 fail-closed use (D2) ------------------------------------------------------------------
    Mutant("SR-missing-integrity-trusted", SR,
           "    if revision.get(\"integrity\") != \"VERIFIED\":",
           "    if revision.get(\"integrity\", \"VERIFIED\") != \"VERIFIED\":",
           T105, "a revision without an integrity state is used as VERIFIED"),
    Mutant("SR-use-without-recompute", SR,
           "    check = verify_results(revision)\n    if check[\"status\"] != \"MATCH\":",
           "    check = verify_results(revision)\n    if False:",
           T105, "forged results of a legacy (no results hash) revision feed a tie-in"),
    Mutant("SR-compare-unverified", SR,
           "            verify_for_use(revision, \"comparison\")",
           "            pass",
           T105, "a tampered revision is compared as if valid"),
    Mutant("DP-tie-in-results-unverified", DP,
           "        sr.verify_for_use(record, \"a plan tie-in\")",
           "        pass",
           T105, "a plan is saved against a survey revision whose results fail verification"),
    # ---- M105 datum shift --------------------------------------------------------------------------
    Mutant("SR-datum-offset-sign", SR,
           "    offset = round(source_elev - target_elev, 10)",
           "    offset = round(target_elev - source_elev, 10)",
           T105, "a datum shift moves depths the wrong way"),
    Mutant("SR-datum-missing-elevation-zero", SR,
           "    source_elev, target_elev = _finite(source_datum_elevation_m), _finite(target_datum_elevation_m)",
           "    source_elev, target_elev = _finite(source_datum_elevation_m) or 0.0, "
           "_finite(target_datum_elevation_m) or 0.0",
           T105, "a missing datum elevation is silently taken as zero"),
    Mutant("SR-datum-inclined-first-accepted", SR,
           "    if abs(float(stations_in[0][\"inc\"])) > 1e-9:",
           "    if False:",
           T105, "a datum shift is applied to a survey whose first station is inclined"),
    Mutant("SR-datum-stations-above-kept", SR,
           "    if above:\n        raise SurveyRevisionError(",
           "    if False:\n        raise SurveyRevisionError(",
           T105, "stations above the new datum are saved with negative MD"),
    # ---- M105 plan references ----------------------------------------------------------------------
    Mutant("DP-reference-contradiction-accepted", DP,
           "        if declared and str(declared).strip().lower() != str(getattr(row, key) or \"\").strip().lower():",
           "        if False:",
           T105, "a plan declaring GL is saved tied to an RKB survey"),
    Mutant("DP-references-dropped", DP,
           "    if references:                      # M105",
           "    if False:                           # M105",
           T105, "declared plan references are not stored"),
    Mutant("TC-reference-conflict-accepted", TC,
           "        if plan_value and actual_value and plan_value.lower() != actual_value.lower():",
           "        if False:",
           T105, "plan-vs-actual runs across different azimuth references or datums"),
    Mutant("TC-comment-rows-not-parsed", TC,
           "        while lines and lines[0].strip().lstrip('\"').startswith(\"#\"):",
           "        while False:",
           T105, "a plan file's declared reference is ignored (and the file is refused)"),
    Mutant("CP-reference-gate-removed", CP,
           "                if not check[\"ok\"]:\n                    self._clear_result(check[\"summary\"])",
           "                if False:\n                    self._clear_result(check[\"summary\"])",
           T105, "the desktop compares a plan in another reference"),
    # ---- M105 additive migration -------------------------------------------------------------------
    Mutant("DB-additive-column-skipped", DB,
           "                if column_name not in columns:\n                    raw.execute(f\"ALTER TABLE",
           "                if False:\n                    raw.execute(f\"ALTER TABLE",
           T105, "an existing database never gains the results-hash column"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
