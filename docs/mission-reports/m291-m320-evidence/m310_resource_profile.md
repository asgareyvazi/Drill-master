# M310 — resource profile of the M291–M320 test modules

UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED. SYNTHETIC data only.

**Method.** The opt-in plugin `tools/quality/pytest_rss_profile.py` (M234/M267) ran in one pytest process over
every M295–M320 test module. The glob also picked up the older `test_m30_semantic_regressions.py`, which serves
as a reference. Settings:
* `DRILLMASTER_RSS_PROFILE_GC_EVERY=1`, so gc object counts are taken at every test. The plugin only reads; it
  never collects.
* PySide6 6.8.1.1 (the lock), offscreen Qt, Python 3.11.2.
* It ran on its own, never concurrently with the full suite.
* Raw data: `m310_rss_profile_m291_m320_tests.csv`, one row per test.

**Result.** 222 tests, 0 failures, 261 s of test time.

| Measure | Start | End | Max |
|---|---|---|---|
| anonymous RSS | 98 MB | 367 MB | 367 MB |
| live widgets (`QApplication.allWidgets`) | – | 0 | 0 at every module boundary |
| threads | 1 | 1 | 1 |
| open fds | 16 | 17 | 18 |
| QObject wrappers among gc objects | 0 | 217 | 265 |
| temp-dir entries | 344 | 344 | 344 (no leaked temporary files) |

| Module | Tests | s | Δ anon MB |
|---|---|---|---|
| test_m295_authored_value_entry | 19 | 21.2 | 47.8 |
| test_m296_import_value_states | 31 | 70.3 | 145.1 |
| test_m298_m299_registry_and_batch | 8 | 5.6 | 0.0 |
| test_m300_m301_value_lineage | 11 | 80.7 | −23.5 |
| test_m302_lineage_ui | 2 | 16.5 | 0.5 |
| test_m303_m306_clone_contract_and_bulk | 17 | 17.4 | 0.0 |
| test_m308_window_release_policy | 16 | 1.5 | 43.3 |
| test_m309_d51_monitor | 11 | 0.0 | 0.0 |
| test_m311_architecture_diff | 6 | 3.2 | 1.6 |
| test_m314_ddr_hydraulics_check | 16 | 16.9 | 10.7 |
| test_m317_cement_job_reconciliation | 14 | 15.2 | 6.9 |
| test_m318_td_friction_sensitivity | 14 | 2.3 | 15.1 |
| test_m320d_report_sections | 8 | 6.9 | 6.1 |
| test_m320e_citation_record | 7 | 1.1 | 1.3 |

**Reading.**
* The new modules leave no widgets, threads, file descriptors or temporary files behind.
* RSS growth is concentrated in the M296 import tests (72 / 61 / 39 MB for the three largest tests, each building
  a full synthetic import) and in the one M308 test that builds a MainWindow (43 MB). Anonymous RSS is not
  returned to the OS by the allocator, so Δ RSS is an upper bound, not a leak measurement. The negative Δ for M300
  shows that reuse does happen.
* The M311/M314/M317/M318/M320 modules together add about 42 MB in 45 s.

**Full suite on the same tree** (the code later committed as `2273aa4`): 5,867 tests, 0 failed, 0 errors,
4 skipped, 3,319 s. The D74 session report still lists 16 closed MainWindows alive with 189,276 live widgets.
That is expected on the 6.8.1.1 pin: windows are retained by policy until the PySide6 pin is raised (D63, owner
decision). It is not a regression.

**Status:** M310 COMPLETE as a measurement. It changes no product behaviour.
