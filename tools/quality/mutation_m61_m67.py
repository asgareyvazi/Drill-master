#!/usr/bin/env python3
"""Repeatable mutation run for the M61 DDR profile/queue, M62 plan, M63 case and M67 history contracts.

Each mutant removes ONE guard (or restores one old behaviour) in a scratch copy
of the working tree and must be KILLED by the listed tests. The engine is the
M46 one (``tools/quality/mutation_m46.py``). The repository is never modified.

Usage::

    python tools/quality/mutation_m61_m67.py [--json OUT] [--only ID[,ID...]]

SYNTHETIC test data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

ME = "core/mineru_engine.py"
PG = "core/import_adapters/pdf_generic_tables.py"
EI = "dialogs/excel_import_dialog.py"
Q = "core/ddr_import_queue.py"
WP = "core/well_plan_designer.py"
DP = "core/directional_plans.py"
CC = "core/calculation_cases.py"
CH = "core/calculation_history.py"
T61 = ["tests/test_m61_ddr_profile_rules.py"]
T62 = ["tests/test_m62_directional_plans.py"]
T63 = ["tests/test_m63_calculation_cases.py"]
T67 = ["tests/test_m67_calculation_history.py"]
SG = "core/storage_guards.py"
T70Q = ["tests/test_m70_queue_lifecycle.py"]
T70I = ["tests/test_m70_integrity.py"]
T70L = ["tests/test_m70_verification_lineage.py"]
T71 = ["tests/test_m71_ddr_background.py"]
T73 = ["tests/test_m73_contracts_history.py"]

MUTANTS = [
    # ------------------------------------------------------------------ M61 profile rules / queue
    Mutant("ME-ambiguous-date-accepted", ME,
           "        if len(hits) == 1:",
           "        if len(hits) >= 1:",
           T61, "a day/month-ambiguous date is accepted with the first reading"),
    Mutant("ME-stop-marker-not-sticky", ME,
           "            return f\"after stop marker {state['stopped']!r} ({tag})\"",
           "            pass",
           T61, "rows after a stop marker are imported again"),
    Mutant("ME-skip-row-rule-ignored", ME,
           "                return f\"skip rule {str(token)!r} ({tag})\"",
           "                return None",
           T61, "skip_rows_containing has no effect"),
    Mutant("PG-continuation-flag-ignored", PG,
           "                join\n                and position == 0",
           "                True\n                and position == 0",
           T61, "a profile that disables continuation still joins pages"),
    Mutant("EI-profile-threshold-ignored", EI,
           "            accept = min(1.0, max(0.0, float(profile_info[\"confidence_threshold\"])))",
           "            accept = 0.95",
           T61, "the profile confidence threshold does not change acceptance"),
    Mutant("EI-needs-review-bulk-accepted", EI,
           "                    continue  # ambiguous/unparsed values are never bulk-accepted",
           "                    pass",
           T61, "Accept-all-high accepts values that still need review"),
    Mutant("Q-in-batch-duplicate-missed", Q,   # retargeted in M81: M70.6 moved the check into _mark_twin
           "        if twin is None:\n            return False",
           "        if True:\n            return False",
           T61 + T70Q, "byte-identical files in one batch are imported twice"),
    Mutant("Q-saved-result-removable", Q,
           "REMOVABLE = {QUEUED, FAILED, CANCELLED, SKIPPED, DUPLICATE}",
           "REMOVABLE = {QUEUED, FAILED, CANCELLED, SKIPPED, DUPLICATE, SAVED}",
           T61, "a saved file can be removed from the batch record"),
    Mutant("Q-reimport-counted-as-saved", Q,
           "    if result.get(\"reimport\"):",
           "    if False:",
           T61, "an already-imported source is reported as a new save"),
    Mutant("EI-cancel-ignored", EI,   # retargeted in M81: M71 moved the check into the run loop
           "            runnable = (entry.status not in FINAL and not queue.cancel_requested\n",
           "            runnable = (entry.status not in FINAL\n",
           T61 + T70Q + T71, "Cancel remaining does not stop files that have not started"),
    # ------------------------------------------------------------------ M62 plans
    Mutant("WP-station-only-target-distance", WP,
           "\"name\": target.get(\"name\", \"Target\"), \"closest_md\": near[\"md\"], \"distance\": near[\"distance\"],",
           "\"name\": target.get(\"name\", \"Target\"), \"closest_md\": near[\"md\"], "
           "\"distance\": math.dist((station[\"north\"], station[\"east\"], station[\"tvd\"]), point),",
           T62, "target distance falls back to the closest station"),
    Mutant("WP-antiparallel-unguarded", WP,
           "            if dogleg > 180.0 - ANTIPARALLEL_TOL_DEG:",
           "            if False:",
           T62, "an antiparallel curve is designed with an undefined plane"),
    Mutant("WP-non-finite-unchecked", WP,
           "    problem = _non_finite(segments, targets, tie_in, step, dls_limit, vs_azimuth)",
           "    problem = None",
           T62, "NaN/inf inputs reach the designer"),
    Mutant("DP-revision-number-reused", DP,
           "    return (latest[0] if latest else 0) + 1",   # retargeted in M81: M70 _next_revision
           "    return latest[0] if latest else 1",
           T62 + T70I, "a revise overwrites/collides with the latest revision number"),
    Mutant("DP-archived-reactivated", SG,   # retargeted in M81: one transition table drives service + trigger
           "    \"archived\": (\"archived\",),",
           "    \"archived\": (\"archived\", \"draft\", \"approved\"),",
           T62 + T70I, "an archived revision can be made active again"),
    # ------------------------------------------------------------------ M63 cases
    Mutant("CC-rerun-loses-parent", CC,
           "wellbore_id=original[\"wellbore_id\"], parent_id=original[\"id\"], note=note,",   # retargeted in M81
           "wellbore_id=original[\"wellbore_id\"], parent_id=None, note=note,",
           T63 + T70L, "a re-run is not linked to the case it came from"),
    Mutant("CC-empty-inputs-accepted", CC,
           "    if not inputs:\n        raise ValueError(\"The case has no inputs to store.\")",
           "    if False:\n        raise ValueError(\"The case has no inputs to store.\")",
           T63, "a case without inputs is stored"),
    # ------------------------------------------------------------------ M67 history
    Mutant("CH-well-filter-ignored", CH,
           "        query = query.filter(model.well_id == well_id)",   # retargeted in M81: M73 DB-side filters
           "        pass",
           T67 + T73, "the history of one well shows other wells' calculations"),
    Mutant("CH-recalc-always-match", CH,
           "        return {\"status\": outcome.status, \"method_matches\": outcome.method_matches,",
           "        return {\"status\": \"MATCH\", \"method_matches\": outcome.method_matches,",
           T67, "a recalculation that differs from the stored result is reported as a match"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
