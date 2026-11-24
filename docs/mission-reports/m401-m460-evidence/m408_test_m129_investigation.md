# M408 — `test_m129` intermittent failure: investigation record

**Status: OPEN — NOT REPRODUCED — NOT ROOT-CAUSED.** No fix was applied. The test is not skipped, marked xfail, given a sleep, excluded or rerun-until-pass.

Input class: SYNTHETIC (test fixtures only).

## Original observation

- Failing test: `tests/test_m129_surveys_anticollision.py::test_w13_anti_collision_is_the_revision_panel_without_a_separation_factor`
- Where it failed: once, in local shard 3 on `8ceaeb7` (M361–M400). It has not been seen in any CI run.
- What failed: the combined assertion `panel.wait_until_idle() and panel.result.status == tc.ASSESSED`. Because the assertion was combined, the failing stage could not be identified.

## Reproduction attempts (this machine: 2 CPUs, 3939 MB RAM, Python 3.11.2, PySide6 6.8.1.1)

| # | Configuration | Runs | Result | Evidence |
|---|---|---|---|---|
| 1 | Pre-129 file range of shard 3 (35 files, test order as in the shard) under 2 CPU busy loops | 2 passes | 396/396 and 396/396 passed (534 s, 547 s) | `m408_loaded_pre129_pass1.txt`, `m408_loaded_pre129_pass2.txt` |
| 2 | Selection-signal spy on the 5 selection-touching files (logs every `SelectionManager` well-id change and any stale ticket) | 1 | all passed; 0 unexpected changes or discards | spy log kept outside the repo (scratch) |
| 3 | `test_m129` alone, isolated | 10 | 10 × exit 0 | `m408_repeated_runs.txt` |
| 4 | `test_m129` alone under 2 CPU busy loops plus a ~2.2 GB resident memory hog | 10 | 10 × exit 0 | `m408_repeated_runs.txt` |

## Hypotheses considered (none proven)

- **H1.** A MainWindow leaked from an earlier test (the D74 warning is seen in these runs) fires a deferred `QTimer.singleShot` in `main_window.py` (l.202, 206, 2005, 2525, 2533, 2976, 2983). That moves the shared selection, which bumps the selection generation, so the panel's worker result is discarded as stale (`core/selection_manager.py` `stale_reason`). The panel would then show no result.
  - *Gap:* the spy logged well-id changes only, not same-id `force` / `data_changed` generation bumps.
- **H2.** The worker does not finish within the 30 s `wait_until_idle` under heavy load. This was not observed even under combined CPU and memory pressure.
- **H3.** Residual state in the module-level selection singleton. `tests/conftest.py` has no selection reset, but the isolated runs share the same fixture order and pass.

## Diagnostic change (not a fix, not weaker)

The single assertion was split into three staged assertions with messages: idle within the wait, result shown, status ASSESSED with the reasons. Each stage is required, exactly as before. A recurrence will now name the stage that failed.

## Next steps (backlog `BL-M408`)

1. Extend the spy to log generation bumps with their call stack.
2. Collect the staged-assertion message from any recurrence (local sharded runs or CI).
3. Only then decide whether to fix it (e.g. reset the selection between tests, or drain deferred timers of leaked windows). D74 itself is owner-gated.
