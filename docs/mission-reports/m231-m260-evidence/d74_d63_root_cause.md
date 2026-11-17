# M234 / M235 / M237 – D74 root cause, the fix that was applied, and a D63-class reproducer

All runs: Linux sandbox, Python 3.11.2, PySide6 6.8.1.1 offscreen, 2 CPUs, 3,939 MiB, no swap; no coverage.
Probes are kept verbatim in `d74_d63_probes/` (`*.py.txt`, loaded with `-p <name>` from a scratch `PYTHONPATH`;
none is part of the product or the suite).

## 1. Per-test profile of the pytest process (before, tree `eaa003f` = code `2764071`)

`tools/quality/pytest_rss_profile.py` (new, opt-in, read-only): one CSV row per test around the whole runtest
protocol – `RssAnon` / `RssFile` from `/proc/self/status`, `len(QApplication.allWidgets())`, threads, fds, and
`len(gc.get_objects())` every 50 tests and at module boundaries.

`d74_profile_before_eaa003f_per_test.csv` – 3,898 tests, then stopped by the memory guard
(`d74_profile_before_eaa003f_memavailable.txt`, MemAvailable 223,852 kB) inside
`tests/test_m95_ux_responsiveness.py`, i.e. exactly where D74 fails:

| Point in the run | Test index | Anonymous RSS | Live widgets |
|---|---|---|---|
| 10 % | 389 | 357,744 kB | 0 |
| 25 % | 974 | 582,316 kB | 2,460 |
| 50 % | 1,949 | 1,186,740 kB | 28,015 |
| 75 % | 2,924 | 2,199,824 kB | 106,730 |
| stop (m95) | 3,897 | 3,534,448 kB | 169,688 |

Live widgets left after a module ended (largest): `test_m44_ui` +11,573, `test_m45_ui` +9,872,
`test_m169_end_to_end_journey` +9,674, `test_m70_selection_audit` +9,618, `test_m92_method_catalogue` +9,611,
`test_m139_end_to_end_journey` +9,608, `test_m229_product_journey` +9,591, `test_m95_ux_responsiveness` +9,568,
`test_m190_tubular_journey` +9,563, `test_m153_context_blocked_autosave` +9,551, `test_m94_e2e_journeys` +9,551,
`test_m227_data_quality_workspace` +9,484, `test_m217_day_by_day_carry_forward` +9,407,
`test_m102_context_probes` +9,393, `test_m83_selection_lifecycle` +9,393 – each one `MainWindow`.

Largest anonymous growth inside one module: `test_m87_w13_contracts` +717,372 kB with no widgets left behind.

## 2. Two mechanisms

**(a) Pending deletions were held until the end of each module.** Function fixtures call `tab.deleteLater()`;
the conftest ran the deferred deletions only per module (D52). `test_m87_w13_contracts` built one W13 tab
(1,647 widgets) per parametrized case and accumulated 49,428 widgets before the module flush. glibc keeps the
freed heap: in three modules (`d74_d63_probes/boundary_*.csv`) the anonymous RSS at the boundaries was 967 MB
without and with `gc.collect()` (nothing collectable), and dropped to 255 MB only after `malloc_trim(0)`.
Running the deferred deletions after every test instead (`per_test_flush.py.txt`) ended the same three modules
at 196 / 226 / 235 MB.

**(b) A closed `MainWindow` is never freed.** `close()` without `WA_DeleteOnClose` only hides the window.
`holder_probe.py.txt`: after `test_m102_context_probes` the window was still alive (9,798 widgets), referenced
from closure cells, `StatusBarManager` and tab attributes. `lambda_slot_cycle.py.txt` isolates the cause:

| Window pattern (closed, last Python reference dropped, `gc.collect()`) | Result |
|---|---|
| child widget stores the window in an attribute | collected |
| bound method of the window connected to a child's signal | collected |
| **lambda capturing the window connected to a child's signal** | **alive** |

Shiboken keeps the lambda of a connection where the cyclic garbage collector does not traverse it, so the
window ↔ lambda cycle is invisible to `gc`. `MainWindow` and its tabs connect many such lambdas. The
application has one main window per process; in the suite every window module leaks one.

## 3. What was changed (M235)

1. `tests/conftest.py` – `_flush_deferred_deletes_per_test`: the deferred deletions run after every test's own
   teardown (D52 extended from modules to tests; the same objects are destroyed, earlier).
2. `tests/conftest.py` – closed `MainWindow`s that are still alive are **reported**, not destroyed:
   "D74 closed MainWindows still alive: N after <module> (W live widgets)" in the terminal summary.
3. `main_window.py` – the Export tab follows the selected well through the bound method
   `_export_follows_well` instead of a lambda on the process-wide `SelectionManager`. Found because a destroyed
   window's lambda kept calling `set_current_well` on its deleted Export tab
   (`RuntimeError: Internal C++ object (PySide6.QtWidgets.QComboBox) already deleted`).
4. Tests: `tests/test_d74_deferred_deletes_and_window_leak.py` (pending deletion runs after the test; only the
   lambda pattern survives `gc`; detection of closed vs visible main windows) and
   `tests/test_m70_selection_audit.py::test_the_export_tab_follows_the_well_through_a_bound_method_of_the_window`.

No timeout, watchdog, retry, skip or `gc.collect()` was added; the 300 s M95 budget and the 60-minute CI limit
are unchanged.

## 4. Why closed main windows are not destroyed (M237 – a D63-class reproducer)

Destroying the closed windows was implemented and rejected:

* Deleting every hidden top-level widget segfaulted at once: `QApplication.topLevelWidgets()` also returns
  parented windows (a combo box's popup container, menus); deleting them before their owner crashed in the
  owner's destructor (`which_top.py.txt`, `bisect_mw.py.txt`, `prefix_mw.py.txt`).
* Restricted to parentless hidden windows it still segfaulted: pyqtgraph's parentless `ViewBoxMenu` and other
  menus are still referenced by their Python owners.
* Restricted to `main_window.MainWindow` only, each module passed, but **the process segfaulted afterwards
  in the garbage collector** (faulthandler: "Garbage-collecting", from pytest's `gc_collect_harder` at
  unconfigure):

| Scenario (fixed conftest + disposal of closed MainWindows) | Segfaults |
|---|---|
| `test_m102_context_probes` + `test_m70_selection_audit` + `test_m83_selection_lifecycle` (module-scoped windows, as in the suite) | 1 of 4 runs |
| a test file with three function-scoped real windows | 5 of 8 runs (two batches) |
| same, but every pyqtgraph `GraphicsView.close()` first | 5 of 6 (worse; hypothesis rejected) |
| baseline code (no disposal) – m102 + m70 | 0 of 2 |

`garbage_types.py.txt` (DEBUG_SAVEALL): 29,519 unreachable objects after three destroyed windows, 7,241 of them
Shiboken wrappers, 5,229 of those already invalid (C++ object deleted), and still-valid Python-owned Qt objects
(300 `QMenu` incl. `ViewBoxMenu`, 60 `QWidgetAction`, `QTimer`s). The crash also occurred inside a
`DEBUG_SAVEALL` collection, where objects are not freed, so it is in the collector's traversal / finalizer /
weakref-callback phase over this graph, not in a destructor called by our code. No native debugger is available
in the sandbox (`gdb`, `lldb`, `eu-stack`, `valgrind` absent), so the native frame is not identified.

This is the first deterministic setup that produces the D63 symptom (SIGSEGV with a garbage-collection frame,
no pytest summary) – D63 is **REPRODUCED IN A DIAGNOSTIC SETUP, ROOT CAUSE NOT IDENTIFIED**, not fixed. It does
not occur in the committed suite, because closed windows are never destroyed there. Product relevance: the
application destroys its `MainWindow` only at exit; whether interpreter shutdown can reach the same collection
was not established (open item).

## 5. After – full suite with the profiler on `cfaf476` (fix items 1–4)

`full_suite_cfaf476_local_nocov_profiled.log.txt`, `d74_profile_after_cfaf476_per_test.csv`,
`d74_profile_after_cfaf476_memavailable.txt` (in the CSV the parameter ids of the 31 `tests/test_privacy_check.py` cases are replaced by `[parameter-redacted-<index>]`: they are synthetic secret patterns that the repository privacy gate rightly refuses in a tracked file): **5521 passed, 1 failed, 4 skipped in 6,072 s** (the profiler's
`gc.get_objects()` sampling and page-ins under memory pressure; the unprofiled run on `2764071` took 3,010 s).

| Same test | Before (`eaa003f`) anon RSS / widgets | After (`cfaf476`) anon RSS / widgets |
|---|---|---|
| `test_m137_dependency_reconciliation` (≈ 35 %) | 1,165,580 kB / 18,407 | 861,432 kB / 18,407 |
| `test_m214_header_mapping` (≈ 42 %) | 1,452,536 kB / 56,803 | 1,472,348 kB / 56,747 |
| `test_m53_dashboard` (≈ 62 %) | 2,618,988 kB / 119,463 | 2,323,756 kB / 119,407 |
| start of `test_m87_w13_contracts` | 3,110,340 kB / 168,405 | 2,694,628 kB / 140,350 |
| `test_m95 … measurement_tool_runs_and_reports_every_path` (D74) | killed at its 300 s budget in every earlier local full run; this profiled run was stopped by the memory guard before reaching it | **passed in 13.2 s** at 3,050,928 kB |

The terminal summary reported "D74 closed MainWindows still alive: 14 after test_m95_ux_responsiveness
(169575 live widgets)" – mechanism (b) is unchanged, so the peak is unchanged; the per-test flush removed the
in-module peaks (m87) that tipped the child into starvation in this run.

**New failure, explained by the same leak:** `test_m169_end_to_end_journey.py::test_m169_twenty_step_journey`
step 15 found a `WARNING Auto-save: CONTEXT_BLOCKED … BOP, Waste` record that its own call did not produce.
`MainWindow.closeEvent` stopped the clock, backup scheduler and session lock but **not the tabs' autosave timers**
(`AutoSaveManager.enable_for_widget`, every 5 min): the 13 closed-but-alive windows of earlier modules kept
autosaving against their disposed databases and logged into whichever test was running. The file passes alone
(2 of 2). Fix (item 5): an accepted close disables every autosave manager of the window
(`main_window.py`, before `cleanup()`), test
`tests/test_m70_selection_audit.py::test_zz_an_accepted_close_stops_every_autosave_timer_of_the_window`
(fails without the fix: the timers stay active; passes with it). In the application this only affected the time
between the close and the end of the process; "Return to startup" reuses the same window.

## 6. Status

* **D74: OPEN – ROOT CAUSE IDENTIFIED, PARTIALLY MITIGATED.** The growth is attributed (closed `MainWindow`s kept
  alive by lambda slots + per-module deferred deletions); the mitigations are in the harness and in
  `main_window.py`; destroying the leaked windows is blocked by the D63-class crash; the peak RSS of a local full
  run is unchanged (~3.3–3.5 GB of 3.94 GB). Whether the D74 test now passes reliably is decided by the unprofiled
  full runs recorded in the M231–M260 report, not by this single profiled run.
* **D63: REPRODUCED IN A DIAGNOSTIC SETUP (destroying closed MainWindows) – ROOT CAUSE NOT IDENTIFIED – NOT FIXED.**
