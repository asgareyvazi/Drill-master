# M267 resource profile (full suite, `b21782b`)

Profile of the full local suite on `b21782b` (`tools/quality/pytest_rss_profile.py`, one long-lived pytest process, offscreen Qt, 2 CPUs / 3.94 GB, no coverage). Per-test CSV: `m267_profile_b21782b.csv`.

| Measure | Start | Peak | End |
|---|---|---|---|
| RSS anonymous (kB) | 233,112 | 3,603,916 | 3,603,712 |
| RSS file-backed (kB) | 56,136 | 100,872 | 18,668 |
| live widgets | 0 | 197,825 | 197,792 |
| Python gc-tracked objects (sampled) | 328,043 | 5,085,903 | 4,965,878 |
| QObject wrappers (sampled) | 0 | 283,056 | 282,760 |
| threads | 1 | 9 | 8 |
| open fds | 16 | 217 | 39 |
| temp-dir entries | 150 | 295 | 295 |

Tests profiled: 5609; sum of per-test wall time 2,542 s (setup + call + teardown). The profiler's sampling (gc object and wrapper scans at 506 points) made this run slower than an unprofiled one (2,409 s on `db0cba3`); the pytest total was 4,565.77 s.

Slowest modules (s):

| Module | Seconds | Δ anon RSS (kB) |
|---|---|---|
| `tests/test_m215_scalar_correction_adversarial.py` | 110 | -30,936 |
| `tests/test_m102_context_probes.py` | 61 | +124,064 |
| `tests/test_m178_trajectory_views.py` | 60 | +12 |
| `tests/test_m50_analysis_async.py` | 53 | +1,204 |
| `tests/test_windows_release_evidence.py` | 53 | -3,688 |
| `tests/test_db_restore_service.py` | 52 | +1,988 |
| `tests/test_m70_integrity.py` | 50 | +5,232 |
| `tests/test_m48_analysis_ui.py` | 50 | -24 |
| `tests/test_m96_persistence_audit.py` | 49 | +77,684 |
| `tests/test_m173_scalar_correction.py` | 48 | +34,708 |
| `tests/test_m87_w13_contracts.py` | 48 | +2,784 |
| `tests/test_m51_analysis_snapshot.py` | 38 | +8 |

Largest anonymous-RSS growth by module (kB):

| Module | Δ anon RSS | Seconds |
|---|---|---|
| `tests/test_m265_window_routes.py` | +253,584 | 13 |
| `tests/test_m229_product_journey.py` | +229,152 | 14 |
| `tests/test_m169_end_to_end_journey.py` | +162,636 | 11 |
| `tests/test_ddr_followup_lifecycle.py` | +126,776 | 28 |
| `tests/test_m102_context_probes.py` | +124,064 | 61 |
| `tests/test_m227_data_quality_workspace.py` | +107,344 | 7 |
| `tests/test_m83_selection_lifecycle.py` | +92,924 | 36 |
| `tests/test_m95_ux_responsiveness.py` | +90,496 | 21 |
| `tests/test_m45_ui.py` | +89,300 | 9 |
| `tests/test_m217_day_by_day_carry_forward.py` | +89,044 | 9 |

## Findings

1. **Budgets are kept separate.** The CI job limit stays at 60 min and the per-test hang watchdog (`verify_release.TEST_HANG_SECONDS`) stays at 900 s. D51 is tracked on its own (`d51_*.txt`). This profiled run is not a CI-time measurement: the profiler's own scans roughly doubled the wall time (4,566 s, against 2,409 s unprofiled on `db0cba3`). The sum of per-test time is 2,542 s.
2. **Anonymous RSS growth is dominated by retained closed MainWindows (D74 cause 1, held back by D63).** At the end, 17 closed windows held 197,792 widgets and about 283 k QObject wrappers. That is roughly 11.6 k widgets and about 200 MB of anonymous RSS per window on average. Peak anonymous RSS was 3.60 GB on a 3.94 GB machine.
3. **The M265 tests themselves were the largest single contributor (+254 MB, 4 windows).** M268 therefore restructures `tests/test_m265_window_routes.py` to share one window across the selection/reopen tests. The assertions are unchanged; the reopen test now also checks that the first, closed window ignores the reopen. The isolated module run then retains 2 windows (19,105 widgets) instead of 4.
4. **Threads and fds:** 9 threads at peak and 8 at the end (Qt thread pool, SQLAlchemy and logging handlers; no unbounded growth). fds peaked at 217 during release-boundary subprocess tests and returned to 39.
5. **Temp entries:** 150 → 295. The growth comes from `tmp_path` directories that pytest keeps (its retention policy), not from leaked handles.
6. **Coverage overhead** was not re-measured locally (local coverage runs out of memory on 3.94 GB). CI on `b21782b` (coverage job, Linux runner) succeeded within the 60 min limit.
7. **One failure in this run: `test_release_boundary_imports::test_wheel_from_tracked_population_starts`.** It is an environment artefact. The sandbox's virtualenv is reached through a `.venv` symlink inside the checkout, so its `site-packages` path contains `Drill-master`, which the probe's own assertion forbids. The test passes with the interpreter started from its real path (reproduced both ways). This is not a product defect. The final full suite uses the real interpreter path.
