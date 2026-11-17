#!/usr/bin/env python3
"""Repeatable mutation run for M231-M260 (M239): unknown vs zero and missing vs default in the MSE input snapshot
(report reproducibility), the DDR import review queue (continuation lineage, counting), and the M234 rule that a
closed main window stops autosaving.

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

T239 = "tests/test_m239_review_queue_and_mse_summary.py"      # added for the five survivors of the first run (4df5c01)
TMSE = ["tests/test_mse_persistence.py", "tests/test_mse_save_widget_smoke.py", T239]
TRQ = ["tests/test_m147_m152_ddr_continuation.py", T239]
TMW = ["tests/test_m70_selection_audit.py"]

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
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
