#!/usr/bin/env python3
"""Repeatable mutation run for M231-M260 (M239): unknown vs zero and missing vs default in the MSE input snapshot
(report reproducibility), the DDR import review queue (continuation lineage, counting), and the M234 rule that a
closed main window stops autosaving; extended after the M241 finding that the casing engine, the
torque-and-drag engine and the kill sheet were mutated by no catalogue (units, design factor, unknown inputs).

Each mutant introduces ONE realistic defect in a scratch copy of the working tree and must be KILLED by the listed
tests. Engine: ``tools/quality/mutation_m46.py`` (green baseline first; an anchor that does not match exactly once
is INVALID, never killed). The repository is never modified.

Usage::

    python tools/quality/mutation_m231_m260.py [--json OUT] [--only ID[,ID...]]

SYNTHETIC test data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

MSE = "core/engineering/mse_persistence.py"
RQ = "core/import_review_queue.py"
MW = "main_window.py"
CAS = "core/engineering/engines/casing.py"
TD = "core/engineering/engines/torque_drag.py"
KS = "core/engineering/well_control_kill_sheet.py"

T239 = "tests/test_m239_review_queue_and_mse_summary.py"      # added for the five survivors of the first run (4df5c01)
TMSE = ["tests/test_mse_persistence.py", "tests/test_mse_save_widget_smoke.py", T239]
TRQ = ["tests/test_m147_m152_ddr_continuation.py", T239]
TMW = ["tests/test_m70_selection_audit.py"]
TENG = "tests/test_m239_engine_semantics.py"            # added for the survivors of the extension (D77 found here)
TCAS = [TENG, "tests/test_casing_vme_independent.py", "tests/test_casing_absent_load_semantics.py",
        "tests/test_engineering_ground_truth.py", "tests/test_m90_engine_qualification.py",
        "tests/test_engineering_completion.py"]
TTD = [TENG, "tests/test_single_source_guard.py", "tests/test_release_gate_and_w13.py",
       "tests/test_torque_drag_persistence.py", "tests/test_torque_drag_history.py",
       "tests/test_engineering_ground_truth.py", "tests/test_m90_engine_qualification.py",
       "tests/test_engineering_completion.py"]
TKS = [TENG, "tests/test_well_control_kill_sheet.py", "tests/test_kill_sheet_casing_id_gate.py",
       "tests/test_well_control_kill_sheet_persistence.py"]

MUTANTS = [
    # Unknown vs zero / missing vs default: the frozen MSE input snapshot reproduces the engine call exactly.
    Mutant("MSE-bool-frozen-as-number", MSE,
           "    if value is None or isinstance(value, bool):\n",
           "    if value is None:\n", TMSE,
           "a True/False input is frozen as 1.0/0.0 instead of unknown"),
    Mutant("MSE-non-finite-frozen", MSE,
           "    return number if math.isfinite(number) else None\n",
           "    return number\n", TMSE,
           "NaN / inf inputs are frozen into the snapshot as numbers"),
    Mutant("MSE-missing-input-frozen-as-zero", MSE,
           "        params[key] = _clean_number(inputs.get(key))\n",
           "        params[key] = _clean_number(inputs.get(key)) or 0.0\n", TMSE,
           "a missing WOB / RPM / torque / ROP / bit size is frozen as 0 instead of unknown"),
    Mutant("MSE-reconstruct-missing-as-zero", MSE,
           "    return {key: params.get(key) for key in _ENGINE_PARAMS}\n",
           "    return {key: params.get(key, 0.0) for key in _ENGINE_PARAMS}\n", TMSE,
           "re-running a stored snapshot fills a missing parameter with 0 (the engine would compute a value)"),
    Mutant("MSE-summary-unknown-as-zero", MSE,
           "    return {k: _clean_number(values.get(k)) for k in SUMMARY_KEYS}\n",
           "    return {k: _clean_number(values.get(k)) or 0.0 for k in SUMMARY_KEYS}\n", TMSE,
           "an absent headline result (MSE, axial / rotary term) is stored as 0 psi"),
    # DDR continuation and review queue: lineage of continuation rows and the review counts shown to the user.
    Mutant("RQ-persistence-review-counted-twice", RQ,
           "        item[\"already_counted\"] = True          # the import status counts persistence reviews itself\n",
           "        item[\"already_counted\"] = False\n", TRQ,
           "persistence reviews the import status already counts are added to the review count again"),
    Mutant("RQ-final-decisions-treated-as-counted", RQ,
           "               and str(row.get(\"decision\") or \"REVIEW\").upper() not in FINAL_REVIEW_DECISIONS}\n",
           "               }\n", TRQ,
           "rows with a final decision are treated as already counted pending reviews"),
    Mutant("RQ-negative-parent-index-accepted", RQ,
           "not 0 <= index < len(rows):\n",
           "not index < len(rows):\n", TRQ,
           "a negative continuation parent index attaches the item to the last 24-hour activity"),
    Mutant("RQ-morning-continuation-gets-24h-parent", RQ,
           "    if outcome.get(\"collection\") != \"time_logs_24h\":\n",
           "    if outcome.get(\"collection\") is None:\n", TRQ,
           "a morning-report continuation is linked to a 24-hour row with the same index"),
    Mutant("RQ-attached-counted-as-pending", RQ,
           "    pending = [item for item in items if item.get(\"state\") in PENDING_STATES]\n",
           "    pending = [item for item in items if item.get(\"state\") not in CLOSED_STATES]\n", TRQ,
           "safely attached continuations are reported as pending reviews"),
    Mutant("RQ-already-counted-ignored", RQ,
           "        item[\"already_counted\"] = identity in counted\n",
           "        item[\"already_counted\"] = False\n", TRQ,
           "field reviews the import status already counts are counted again"),
    # M234: a closed window saves nothing in the background.
    Mutant("MW-closed-window-keeps-autosaving", MW,
           "        # after the close (M234 - hidden test windows logged CONTEXT_BLOCKED autosaves into later tests).\n"
           "        for manager in self._autosave_managers():\n"
           "            manager.set_enabled(False)\n",
           "        # after the close (M234 - hidden test windows logged CONTEXT_BLOCKED autosaves into later tests).\n",
           TMW, "a closed main window keeps its tabs' autosave timers running"),
    # Units and engineering semantics in engines no earlier catalogue mutated (found during M241).
    Mutant("CAS-burst-wall-tolerance-dropped", CAS,
           "            rating = 0.875 * 2.0 * yp * t / od\n",
           "            rating = 2.0 * yp * t / od\n", TCAS,
           "burst rating ignores the 87.5 % minimum-wall tolerance (overstates the rating by 14 %)"),
    Mutant("CAS-design-factor-multiplies", CAS,
           "            rating = 0.875 * 2.0 * yp * t / od\n            df = optional_number(design_factor, \"design_factor\")\n            if df is not None and df <= 0:\n                raise EngineeringError(\"design_factor must be > 0 when supplied\")\n            working = rating / df if df is not None else None\n",
           "            rating = 0.875 * 2.0 * yp * t / od\n            df = optional_number(design_factor, \"design_factor\")\n            if df is not None and df <= 0:\n                raise EngineeringError(\"design_factor must be > 0 when supplied\")\n            working = rating * df if df is not None else None\n", TCAS,
           "the burst working pressure multiplies by the design factor instead of dividing"),
    Mutant("CAS-elastic-collapse-constant-typo", CAS,
           "            rating = 46.95e6 / (dt * (dt - 1.0) ** 2)\n",
           "            rating = 46.95e5 / (dt * (dt - 1.0) ** 2)\n", TCAS,
           "elastic-collapse constant mistyped by a factor of 10"),
    Mutant("TD-friction-factor-above-one-accepted", TD,
           "        if not (0.0 <= ff <= 1.0):\n",
           "        if not (0.0 <= ff):\n", TTD,
           "a friction factor entered in percent (e.g. 25) is accepted"),
    Mutant("TD-zero-mud-weight-accepted", TD,
           "        mud = require_number(mud_density_ppg, \"mud_density_ppg\")\n        if mud <= 0:\n",
           "        mud = require_number(mud_density_ppg, \"mud_density_ppg\")\n        if mud < 0:\n", TTD,
           "an unknown mud weight placeholder 0 is treated as air (no buoyancy) instead of rejected"),
    Mutant("TD-landing-friction-sign", TD,
           "            hook = buoyed - friction\n",
           "            hook = buoyed + friction\n", TTD,
           "the landing hook load adds friction instead of subtracting it"),
    Mutant("KS-unfilled-casing-id-assessed", KS,
           "        and inp.casing_id_in > 0\n",
           "", TKS,
           "an unfilled casing ID (stored as 0) still yields annular volumes and strokes"),
    # KS-unfilled-casing-id-assessed SURVIVES (not declared equivalent): the annulus loop rejects any annular ID
    # <= pipe OD in a zone of positive length, so casing ID 0 still gives no annulus whenever a cased zone exists.
    # The only input that tells the mutant apart is a shoe at MD 0 (no cased zone), where the mutant returns the
    # open-hole annulus - a value that is not wrong, so no test can demand the refusal without asserting an
    # over-restriction. Recorded in the M239 evidence; engineering review item.
    Mutant("KS-shoe-below-td-assessed", KS,
           "        and 0 <= inp.shoe_md_ft <= inp.md_ft\n",
           "        and 0 <= inp.shoe_md_ft\n", TKS,
           "a casing shoe deeper than the measured depth is used for annular geometry"),
    Mutant("KS-partial-string-volume-reported-as-total", KS,
           "    string_volume = total_string_vol if pipe_geometry_available else None\n",
           "    string_volume = total_string_vol\n", TKS,
           "a pipe program shorter than MD is reported as the full string volume"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
