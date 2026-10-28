#!/usr/bin/env python3
"""Repeatable mutation run for the M50 contracts.

Each mutant puts ONE old behaviour (or removes one guard) in a scratch copy of
the working tree and must be KILLED by the listed tests. The engine (copy,
exact-once snippet check, baseline run, JSON report, exit status) is the M46
one: ``tools/quality/mutation_m46.py``. The repository is never modified.

Usage::

    python tools/quality/mutation_m50.py [--json OUT] [--only ID[,ID...]]

The environment must be able to run the tests (Qt offscreen etc., see
tools/qt_headless_env.sh). SYNTHETIC test data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

W12 = "tabs/w12_Analysis.py"
EV = "core/analysis_evidence.py"
GC = "core/qt_gc.py"
APP = "app.py"
T_ASYNC = ["tests/test_m50_analysis_async.py"]

MUTANTS = [
    # ------------------------------------------------------------ P0: Analysis revision off the GUI thread
    Mutant("N-synchronous-fingerprint", W12,
           "        if not self._uses_revision_worker():\n            self._update_all_data_sync()",
           "        if True:\n            self._update_all_data_sync()",
           T_ASYNC, "the data revision is computed on the GUI thread again (M49 behaviour)"),
    Mutant("N-sequence-guard-removed", W12,
           "        if seq != self._rev_seq:\n            return                                  # superseded",
           "        if False:\n            return                                  # superseded",
           T_ASYNC, "a superseded (late) revision result is accepted and painted"),
    Mutant("N-generation-guard-removed", W12,
           "        if generation != self._generation or not self.current_well_id:",
           "        if not self.current_well_id:",
           T_ASYNC, "a revision requested before a scope change is painted for the new scope"),
    Mutant("N-verify-skipped", W12,
           '            self._start_revision("verify", painted=revision, reloads=reloads)\n            return',
           "            self._finish_status([])\n            return",
           T_ASYNC, "no second revision: a write committed during the load is shown as Updated"),
    Mutant("N-verify-mismatch-accepted", W12,
           "        if revision == painted:",
           "        if True:",
           T_ASYNC, "a changed revision after the load is accepted (concurrent edit ignored)"),
    Mutant("N-reload-limit-removed", W12,
           "        if reloads >= self._MAX_RELOADS:",
           "        if False:",
           T_ASYNC, "continuous edits are retried without bound and then reported as Updated"),
    Mutant("N-cleanup-leaves-worker", W12,
           "        self._cancel_revision(wait_ms=5000)",
           "        pass",
           T_ASYNC, "closing the page leaves the revision thread running"),
    Mutant("N-cancel-not-polled", EV,
           "        if cancelled is not None and count % _CANCEL_CHECK_ROWS == 0 and cancelled():",
           "        if False:",
           T_ASYNC, "a cancelled revision scan runs to the end"),
    Mutant("N-old-values-while-loading", W12,
           "            self._show_loading_values()\n",
           "            pass\n",
           T_ASYNC, "the previous well's numbers stay on screen while the new well loads"),
    Mutant("N-worker-not-retained", W12,
           "        _LIVE_REVISION_WORKERS.add(worker)\n",
           "",
           T_ASYNC, "unsafe Qt order: a running QThread can be destroyed when its page drops it"),
    Mutant("N-worker-uses-gui-engine", W12,
           "            with worker_database(self.db_manager) as reader:",
           "            with __import__('contextlib').nullcontext(self.db_manager) as reader:",
           T_ASYNC, "the worker reads through the GUI's engine instead of its own read-only one"),
    Mutant("N-error-shown-as-updated", W12,
           '            if error:\n                failed.append(f"read data revision ({error})")',
           "            if error:\n                pass",
           T_ASYNC, "a failed revision read is reported as Updated"),
    # ------------------------------------------------------------ GC only on the GUI thread
    Mutant("G-automatic-gc-left-on", GC,
           "        gc.disable()\n",
           "",
           T_ASYNC, "cyclic GC can run on worker threads (captured deadlock)"),
    Mutant("G-app-does-not-install", APP,
           "        qt_gc.install(self)\n",
           "",
           T_ASYNC, "the application never installs the GUI-thread GC policy"),
    Mutant("G-collect-never-runs", GC,
           "        if count0 > self.threshold[0]:",
           "        if False:",
           T_ASYNC, "with automatic GC off, reference cycles are never reclaimed"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
