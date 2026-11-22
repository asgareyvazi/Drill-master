# M309 — D51 monitoring

UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.

* New repeatable, read-only monitor: `tools/quality/d51_ci_monitor.py` (jobs API + check-run annotations via
  `gh api`; raw logs are outside the sandbox allowlist). Classes: D51_WATCHDOG (faulthandler / wall-clock
  signature), TEST_FAILURE, JOB_TIMEOUT (60-minute limit, D88 class), SUPERSEDED (concurrency-group cancel or
  < 15 min), OTHER, IN_PROGRESS, SUCCESS. Tests: `tests/test_m309_d51_monitor.py` (11, pure classification and a
  stubbed scan; no network).
* Window 2026-11-18 → 2026-11-22 (`m309_d51_monitor_2026-11-18_to_now.txt`): 28 SUCCESS, 18 SUPERSEDED,
  2 JOB_TIMEOUT (the D88 3.12 legs of `4eae8f5` and `07a0f8b`), 4 IN_PROGRESS (`d57f5b2`), **0 D51_WATCHDOG**.
* Found by the monitor and reported, not hidden: the 3.12 and 3.13 legs of `ae016a7` were **cancelled at
  47 min** by the concurrency group when `d57f5b2` was pushed. They are superseded, not failed, and `ae016a7`
  has no 3.12/3.13 result. Its 3.11 leg (44.3 min) and Windows (36.5 min) passed. The first classifier version
  labelled these OTHER; it now reads the cancellation annotation.
* Status: D51 **NOT REPRODUCED**. Absence of recurrence is not a fix; it only bounds the observed rate
  (1 event in the 300 runs studied in M266, 0 since).
