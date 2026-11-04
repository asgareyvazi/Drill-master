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
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
