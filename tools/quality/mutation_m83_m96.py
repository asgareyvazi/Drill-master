#!/usr/bin/env python3
"""Repeatable mutation run for the M83-M96 guards.

Each mutant removes ONE guard (or swaps one rule) in a scratch copy of the working tree and must be KILLED
by the listed phase tests. Engine: ``tools/quality/mutation_m46.py`` (green baseline first; an anchor that
does not match exactly once is reported INVALID, never killed). The repository is never modified.

Usage::

    python tools/quality/mutation_m83_m96.py [--json OUT] [--only ID[,ID...]]

SYNTHETIC test data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

SM = "core/selection_manager.py"
Q = "core/ddr_import_queue.py"
SR = "core/survey_revisions.py"
WP = "core/well_plan_designer.py"
CON = "core/calculator_contracts.py"
CH = "core/calculation_history.py"
WA = "core/well_architecture.py"
OA = "core/operational_analysis.py"
MC = "core/method_catalogue.py"
RP = "core/report_provenance.py"
W10 = "tabs/w10_Planning_Widget.py"
DB = "core/database.py"
SG = "core/storage_guards.py"
T83 = ["tests/test_m83_selection_lifecycle.py"]
T84 = ["tests/test_m84_ddr_identity_cleanup.py"]
T85 = ["tests/test_m85_survey_references.py"]
T86 = ["tests/test_m86_directional_solver.py"]
T87 = ["tests/test_m87_w13_contracts.py"]
T88 = ["tests/test_m88_history_lineage.py"]
T89 = ["tests/test_m89_architecture_casing_cement.py"]
T91 = ["tests/test_m91_operational_analysis.py"]
T92 = ["tests/test_m92_method_catalogue.py"]
T93 = ["tests/test_m93_report_provenance.py"]
T94 = ["tests/test_m94_e2e_journeys.py"]
T95 = ["tests/test_m95_ux_responsiveness.py"]
T96 = ["tests/test_m96_persistence_audit.py"]

MUTANTS = [
    # ---- M83 selection lifecycle -----------------------------------------------------------------
    Mutant("SM-stale-token-accepted", SM,
           "        return tuple(token) == self.context_token()",
           "        return True",
           T83, "a worker result for a previous selection is applied to the new one"),
    # ---- M84 DDR import -------------------------------------------------------------------------
    Mutant("Q-identity-not-rechecked", Q,
           "        if entry.fingerprint and current != entry.fingerprint:\n            return (\"The file changed after",
           "        if False:\n            return (\"The file changed after",
           T84, "a file changed between preview and commit is persisted"),
    # ---- M85 survey revisions --------------------------------------------------------------------
    Mutant("SR-hash-not-verified", SR,
           "\"VERIFIED\" if stations_sha256(json.loads(row.stations_json)) == row.stations_sha256",
           "\"VERIFIED\" if True",
           T85, "a survey revision whose stations no longer match their hash reads as VERIFIED"),
    # ---- M86 directional solver ------------------------------------------------------------------
    Mutant("WP-dogleg-180-accepted", WP,
           "    if dogleg >= 180.0 - 1e-9:",
           "    if False:",
           T86, "a target needing a >= 180 deg dogleg is not reported infeasible"),
    # ---- M87 W13 contracts -----------------------------------------------------------------------
    Mutant("CON-unsupported-claimed", CON,
           "        return \"NOT_SUPPORTED\", f\"{reason}. Cases are stored as captured and are NOT REPRODUCIBLE\"",
           "        return \"SUPPORTED\", f\"{reason}. Cases are stored as captured and are NOT REPRODUCIBLE\"",
           T87, "a calculator without a contract is shown as supported"),
    # ---- M88 history lineage ---------------------------------------------------------------------
    Mutant("CH-survey-hash-not-checked-on-rerun", CH,
           "    if sr.stations_sha256(stations) != entry.inputs.get(\"stations_sha256\"):",
           "    if False:",
           T88, "a re-run recalculates tampered survey stations instead of reporting UNREADABLE"),
    # M73's three-answer label (gap found by this suite; test added in M97)
    Mutant("CH-unreadable-as-readable", CH,
           "    return {\"readable\": \"READABLE\" if readable else \"UNREADABLE\",",
           "    return {\"readable\": \"READABLE\",",
           ["tests/test_m73_contracts_history.py"] + T88, "a record whose stored data cannot be read is labelled READABLE"),
    # ---- M89 cement worksheet --------------------------------------------------------------------
    Mutant("WA-excess-on-cased-hole", WA,
           "host is None and excess_pct is not None",
           "excess_pct is not None",
           T89, "the declared excess is applied to cased intervals too"),
    # ---- M91 operational analysis ----------------------------------------------------------------
    Mutant("OA-incomplete-sum-as-total", OA,
           "    if not values or any(v is None for v in values):\n        return None\n    return float(sum(values))",
           "    if not values:\n        return None\n    return float(sum(v or 0.0 for v in values))",
           T91, "a missing value is counted as zero in a total"),
    Mutant("OA-rop-not-time-weighted", OA,
           "                weighted_pairs.append((footage, drill_h))",
           "                weighted_pairs.append((rop, 1.0))",
           T91, "the summary ROP is the mean of daily ROPs instead of sum(footage)/sum(hours)"),
    # ---- M92 method catalogue --------------------------------------------------------------------
    Mutant("MC-approved-by-default", MC,
           "NOT_APPROVED = \"NOT APPROVED — OWNER REVIEW REQUIRED\"",
           "NOT_APPROVED = \"APPROVED\"",
           T92, "catalogue methods read as approved without an owner decision"),
    # ---- M93 report provenance -------------------------------------------------------------------
    Mutant("RP-unsigned-label-dropped", RP,
           "LABEL = \"UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED\"",
           "LABEL = \"\"",
           T93, "exported reports lose the unsigned / not-approved label"),
    # ---- M94 journeys ----------------------------------------------------------------------------
    Mutant("OA-scope-without-well-name", OA,
           "        label = f\"{well.name} (well #{well.id})\" if well is not None",
           "        label = f\"Well #{well.id}\" if well is not None",
           T94 + T91, "an analysis / export no longer names the well it covers"),
    # ---- M95 responsiveness fixes ----------------------------------------------------------------
    Mutant("OA-memo-ignores-description", OA,
           "    if by_code is not None and by_code.method in (\"learned\", \"exact\"):",
           "    if by_code is not None:",
           T95, "an unresolved code is cached per code although its description decides the mapping"),
    Mutant("W10-state-on-wrapper", W10,
           "    tab = getattr(tab, \"_inner\", tab)\n    tab.current_well_id = well_id",
           "    tab.current_well_id = well_id",
           T95, "the section load of a W10 sub-tab runs against the previous well"),
    Mutant("W10-stale-section-kept", W10,
           "            _clear_child_context(sub)",
           "            pass",
           T95, "re-selecting a well keeps the W10 sub-tabs filtered by the old section"),
    # ---- M96 persistence -------------------------------------------------------------------------
    Mutant("DB-sweep-table-missing", DB,
           "\"cement_calculations\", \"mse_calculations\",",
           "\"cement_calculations\",",
           T96, "a saved MSE calculation makes its well undeletable"),
    Mutant("DB-unlink-unscoped", DB,
           "                    with operation_scope(HIERARCHY_DELETE_UNLINK):\n                        counts[table]",
           "                    if True:\n                        counts[table]",
           T96, "a deleter without edit rights cannot delete a section that has procedures"),
    Mutant("SG-replace-allowed", SG,
           "f\"WHEN EXISTS (SELECT 1 FROM {table} WHERE id = NEW.id) \"",
           "f\"WHEN 0 AND EXISTS (SELECT 1 FROM {table} WHERE id = NEW.id) \"",
           T96, "INSERT OR REPLACE overwrites an immutable history record"),
    Mutant("SG-single-delete-allowed", SG,
           "BEFORE DELETE ON {table} WHEN NOT ({owner_gone}) \"",
           "BEFORE DELETE ON {table} WHEN 0 AND NOT ({owner_gone}) \"",
           T96, "a single history record can be deleted while its well exists"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
