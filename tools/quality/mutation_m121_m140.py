#!/usr/bin/env python3
"""Repeatable mutation run for the M121-M140 guards.

Each mutant removes ONE guard (or reorders one step) in a scratch copy of the working tree and must be
KILLED by the listed phase tests. Engine: ``tools/quality/mutation_m46.py`` (green baseline first; an
anchor that does not match exactly once is reported INVALID, never killed). The repository is never
modified.

Usage::

    python tools/quality/mutation_m121_m140.py [--json OUT] [--only ID[,ID...]]

SYNTHETIC test data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

KA = "tabs/knowledge_assistant.py"
T122 = ["tests/test_m122_assistant_worker_lifecycle.py"]
MR = "core/repositories/mse_repository.py"
T123 = ["tests/test_m123_mse_lineage.py"]
T123_DASH = ["tests/test_m123_mse_lineage.py", "tests/test_m53_dashboard.py"]

MUTANTS = [
    # ---- M122 Knowledge Assistant worker lifecycle (D28) ------------------------------------------------
    Mutant("KA-check-before-connect", KA,
           "        worker.finished.connect(lambda w=worker: self._forget(w))\n"
           "        if worker.isFinished():\n"
           "            self._forget(worker)\n",
           "        if worker.isFinished():\n"
           "            self._forget(worker)\n"
           "        worker.finished.connect(lambda w=worker: self._forget(w))\n",
           T122, "the pre-M122 order: a thread ending between the check and the connect is never released (D28)"),
    Mutant("KA-immediate-check-dropped", KA,
           "        if worker.isFinished():\n"
           "            self._forget(worker)\n",
           "        if False:\n"
           "            self._forget(worker)\n",
           T122, "a thread that ended before the connection waits for a finished signal that never comes"),
    Mutant("KA-stop-worker-not-kept", KA,
           "            self._keep_until_finished(worker)      # keep a reference until the thread ends (M122)\n",
           "            pass\n",
           T122, "cancel/supersede/scope change drop the worker reference while its thread may run"),
    Mutant("KA-retire-not-kept", KA,
           "            pass\n        self._keep_until_finished(worker)\n\n    def _keep_until_finished",
           "            pass\n\n    def _keep_until_finished",
           T122, "a retired scope-list worker is neither tracked nor deleted"),
    Mutant("KA-completed-worker-leaks", KA,
           "            self._keep_until_finished(worker)   # M122: a completed worker was never deleted before\n",
           "            pass\n",
           T122, "every completed question leaves a QThread object on the panel"),
    Mutant("KA-corpus-check-late-connect", KA,
           "            self._keep_until_finished(worker)   # M122: `finished` has usually fired already\n",
           "            worker.finished.connect(worker.deleteLater)\n",
           T122, "the pre-M122 corpus-check release: finished has already fired, the worker is never deleted"),
    Mutant("KA-cleanup-destroys-running-thread", KA,
           "            worker.setParent(None)\n"
           "            release_when_finished(worker)\n",
           "            pass\n",
           T122, "a thread still running at close stays a child of the panel and is destroyed with it"),
    # ---- M123 MSE lineage v2 + audited repair (D6) ------------------------------------------------------
    Mutant("MSE-md-without-wellbore", MR,
           "            if wellbore_id is None:\n"
           "                raise ValueError(\"A measured depth can only be recorded with the wellbore it was measured in.\")\n",
           "            if False:\n"
           "                raise ValueError(\"A measured depth can only be recorded with the wellbore it was measured in.\")\n",
           T123, "a depth is stored without the wellbore it was measured in (a whole-well run looks depth-reproducible)"),
    Mutant("MSE-repair-no-evidence", MR, "        if not evidence:\n", "        if False:\n",
           T123, "a repair is recorded without the evidence it rests on"),
    Mutant("MSE-repair-no-reason", MR, "        if not reason:\n", "        if False:\n",
           T123, "a repair is recorded without a reason"),
    Mutant("MSE-repair-no-confirmer", MR,
           "            if user_id is None or session.get(User, user_id) is None:\n",
           "            if False:\n",
           T123, "an anonymous session can record a repair (no confirming user)"),
    Mutant("MSE-repair-standalone-run", MR,
           "            if row.well_id is None:\n"
           "                raise ValueError(\"A run saved without a well",
           "            if False:\n"
           "                raise ValueError(\"A run saved without a well",
           T123, "a run saved without a well is given a well-relative lineage (inference)"),
    Mutant("MSE-repair-overwrites-recorded", MR,
           "            if getattr(saved, field_name) is not None:\n",
           "            if False:\n",
           T123, "a repair shadows lineage that was recorded at save"),
    Mutant("MSE-repair-twice", MR,
           "            if saved.repair_for(field_name) is not None:\n",
           "            if False:\n",
           T123, "a second repair silently replaces the first (one live repair per field)"),
    Mutant("MSE-repair-bore-other-well", MR,
           "                if bore is None or bore.well_id != row.well_id:\n",
           "                if bore is None:\n",
           T123, "a wellbore of another well is accepted as the run's lineage"),
    Mutant("MSE-repair-report-other-well", MR,
           "                if report is None or report.well_id != row.well_id:\n",
           "                if report is None:\n",
           T123, "a report of another well is accepted as the run's lineage"),
    Mutant("MSE-repair-report-other-bore", MR,
           "                if bore is not None and report.wellbore_id not in (None, bore):\n",
           "                if False:\n",
           T123, "a report of another wellbore of the same well contradicts the run's wellbore"),
    Mutant("MSE-repair-md-without-bore", MR,
           "                if saved.effective_wellbore_id is None:\n",
           "                if False:\n",
           T123, "a depth is repaired onto a run whose wellbore is unknown"),
    Mutant("MSE-unlinked-repair-counts", MR,
           "        live = [r for r in self.repairs if r.field == name and not r.unlinked]\n",
           "        live = [r for r in self.repairs if r.field == name]\n",
           T123, "a repair whose report was deleted still supplies the (now non-existent) report"),
    Mutant("MSE-repair-not-audited", MR,
           "            self.db._add_mandatory_audit(\n                session, \"lineage_repair\"",
           "            (lambda *_a: None)(\n                session, \"lineage_repair\"",
           T123, "a lineage repair leaves no audit record"),
    Mutant("MSE-repair-trigger-inert", "core/storage_guards.py",
           "            f\"WHEN {repair_change} BEGIN SELECT RAISE(ABORT, \"\n",
           "            f\"WHEN 0 BEGIN SELECT RAISE(ABORT, \"\n",
           T123, "a stored repair can be edited in place (append-only evidence)"),
    Mutant("MSE-oa-recorded-not-effective", "core/operational_analysis.py",
           "input_snapshot_json=saved.input_snapshot, wellbore_id=saved.effective_wellbore_id,",
           "input_snapshot_json=saved.input_snapshot, wellbore_id=saved.wellbore_id,",
           T123, "OA's wellbore scope ignores audited repairs"),
    Mutant("MSE-oa-class-split-truncates", "core/operational_analysis.py",
           "            base_class = row.lineage_class.split(\" (repaired:\")[0]\n",
           "            base_class = row.lineage_class.split(\" (\")[0]\n",
           T123, "the OA lineage note truncates the class names ('depth (wellbore + entered MD)' -> 'depth')"),
    Mutant("MSE-history-legacy-label-lost", "dialogs/mse_history_dialog.py",
           "    return mr.LEGACY_LABEL if cls == mr.CLASS_LEGACY else cls\n",
           "    return cls\n",
           T123, "MSE History shows a legacy run without LEGACY - LINEAGE UNKNOWN - NOT DEPTH-REPRODUCIBLE"),
    Mutant("MSE-w13-md-always-recorded", "tabs/w13_Engineering_Calculator.py",
           "        if check is None or not check.isChecked():\n",
           "        if check is None:\n",
           T123, "W13 records a depth the user did not choose to record"),
    Mutant("MSE-w13-no-md-guidance", "tabs/w13_Engineering_Calculator.py",
           "        if md and lineage.get(\"wellbore_id\") is None:\n",
           "        if False:\n",
           T123, "W13 reports a failed save instead of explaining that a depth needs its wellbore"),
    Mutant("MSE-dashboard-legacy-merged", "core/operations_dashboard.py",
           "                (detail.mse_recorded if lineage_version is not None else detail.mse_legacy).append(point)\n",
           "                detail.mse_recorded.append(point)\n",
           T123_DASH, "the dashboard draws legacy runs as if their lineage were recorded"),
    Mutant("MSE-dashboard-points-joined", "tabs/dashboard_widgets.py",
           "        connect = self.kind != \"points\"\n",
           "        connect = True\n",
           T123_DASH, "discrete saved MSE runs are joined into a line that implies continuity"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
