# M261–M290 – Qt lifecycle reliability, mutation expansion, integrated engineering implementation and product qualification

**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**

* Branch: `arena/72010272-drill-master`, fast-forward pushes only.
* Code commits: `7fe52ff`, `b21782b`, `35d3bc6`, `8a76829`, `42eb03d`. This report follows them.
* All evidence is synthetic: SYNTHETIC fixtures, offscreen Qt on Linux (PySide6 6.8.1.1, Python 3.11.2), and GitHub-hosted Linux and Windows runners.
* No real DDR or confidential document was opened.
* Windows CI is not desktop or field acceptance.
* The four opt-in skips are never counted as passes.

## Overall status

**PARTIAL.** Every Part I phase (M261–M271) has been carried out and has evidence. D74 is improved but not closed, D63 is reproduced but its root cause is not identified, and D51 is not reproduced.

Three Part II phases received new implementation in this mission:
* M285: a seven-field KPI specification on the dashboard, with mutants.
* M284: the D81 string-stretch correction in the W13 stuck-pipe calculator.
* M289: a 13-step synthetic cross-module journey test.

Six further Part II phases received the mutation coverage that the mission required of them: M275, M276, M278, M279, M282 and M283. The remaining Part II phases rest on capabilities built in earlier missions and were **not** re-implemented here. The phase register states this row by row, and no row is marked COMPLETE unless every condition is met.

New defects this mission:
* **D81** (found and fixed).
* **D82** (a regression I introduced and fixed before any push).

## A. Delivery verification

| Item | Value |
|---|---|
| Start | HEAD = upstream = remote = `ac7657b` (07:34 UTC); `drill-Master` = `e3fa42a` |
| Pushed | `ac7657b..7fe52ff`, `7fe52ff..b21782b`, `b21782b..35d3bc6`, `35d3bc6..8a76829`, `8a76829..42eb03d` and the report commits – each verified by `git ls-remote` |
| Full local suite on the final code | run on the commit that adds this report; the result is recorded in the next commit |
| Full local suite on `b21782b` (profiled) | 1 failed, 5,604 passed, 4 skipped in 4,565.77 s (with the profiler). The failure, `test_release_boundary_imports::test_wheel_from_tracked_population_starts`, is an environment artefact: the sandbox venv is reached through a `.venv` symlink inside the checkout. The test passes with the real interpreter path; see M267 finding 7. D74 at the end of the run: 17 closed MainWindows, 197,792 widgets |
| CI on the final code | `b21782b`: Source release gate ✅, Windows release validation ✅. Final code: recorded in the next commit |
| Gate slip, corrected | `8a76829` was pushed although three gates failed (engine inventory, dependency audit, privacy findings in synthetic test ids in the profile CSV). A chained command did not stop on the failure. `42eb03d` restores all gates as a forward commit; nothing was amended. Later commits gate with `&&` |
| Gates on the final tree | ruff (core dialogs tabs tests) clean; exception ceiling OK; constant inventory current; dependency audit 0 findings; engine inventory current; privacy check 0 findings |
| Branch protection | `drill-Master` reports `protected=false` with no rulesets, and the direct protection read is unavailable to this token. The policy still forbids writing to it, and this discrepancy has been reported without being tested by a write. |

## Phase register

Columns: ID · objective · implementation (files) · UI · persistence · tests · mutation · evidence · SHA · status · blockers.

| ID | Objective | Implementation / files | UI | Persist. | Tests | Mutation | Evidence | SHA | Status | Blockers |
|---|---|---|---|---|---|---|---|---|---|---|
| M261 | live baseline, safe recovery | venv rebuilt from the lock file; headless Qt libraries rebuilt (`tools/qt_headless_env.sh`); no reset, clean or forced update | – | – | Qt smoke | – | section M261 | – | COMPLETE | – |
| M262 | independent audit of M231–M260, reconciled register | this report, section M262 | – | – | – | – | M262 table | – | COMPLETE | – |
| M263 | D74 signal/slot ownership audit | probe `d74_holders_probe.py.txt`; per-connection table below | – | – | `test_m265_window_routes` | LC-* | `d74_holders_before_db0cba3.txt`, `d74_holders_after_m265.txt` | `7fe52ff` | COMPLETE (audit) | – |
| M264 | D63 native diagnosis | `tools/quality/d63_window_release_probe.py`, `tools/quality/native/segv_bt.c` | – | – | reproducer (opt-in) | – | `d63_native_frames.txt`, `d63_window_release_probe_runs.txt` | `7fe52ff` | PARTIAL: reproduced deterministically; root cause NOT identified | no gdb/lldb/valgrind, no debug Qt build |
| M265 | D74 safe lifecycle fix | `core/qt_lifetime.py`, `core/base_tab.py`, `core/managers.py`, `main_window.py`, `tabs/w12_Analysis.py`, `tabs/w3b_wellbore_schematic_tab.py`, `tabs/trajectory_viewer.py` | yes (close) | – | `test_m265_window_routes` (9), `test_m70` updated | LC-* (M268) | section M265 | `7fe52ff` | PARTIAL: routes fixed; closed windows still retained by design (D63) | D63 |
| M266 | D51 CI-hang diagnosis | API history plus bounded stress runs | – | – | `test_m132` ×10 under load | – | `d51_ci_failure_history.txt`, `d51_watchdog_events.txt`, `d51_bounded_stress_m132.txt` | `b21782b` | PARTIAL: not reproduced; not resolved | raw CI logs unreachable from the sandbox |
| M267 | resource and runtime profile | `tools/quality/pytest_rss_profile.py` (+`qobject_wrappers`, `tmp_entries`) | – | – | full suite profiled | – | `m267_profile_summary.md`, per-test CSV | `b21782b` | COMPLETE (measurement) | coverage overhead not measured locally (OOM) |
| M268 | lifecycle regression group plus cleanup mutants | 7 `LC-*` mutants in `mutation_m261_m290.py`; 2 tests | – | – | `test_m265_window_routes` | LC 7/7 killed | `m268_catalogue_35d3bc6.json`, `m290_catalogue_42eb03d.json` | `35d3bc6` | COMPLETE (regression group and mutants); D74 itself remains PARTIAL | – |
| M269 | R-2 Kill Sheet review | domain table plus case proof | – | – | `test_m269_kill_sheet_geometry_table` (10) | KS survivor kept | `m269_kill_sheet_domain_table.md` | `7fe52ff` | COMPLETE: neither equivalent nor a fix; SURVIVED with justification; P11 | P11 |
| M270 | catalogue for the 7 R-1 modules | `tools/quality/mutation_m261_m290.py` | – | – | `test_m270_r1_engine_contracts` | 47/47 K (20/47 by older tests) | `m270_*` | `7fe52ff` | COMPLETE | – |
| M271 | survivor reconciliation, reach map | section M271 | – | – | – | all 18 catalogues | section M271 | – | COMPLETE (catalogue); "all killed": NO | – |
| M272 | DDR authoring semantics | existing (M54/M84/M217) | yes | yes | existing | m50, m201_m230 | M241 inventory #2 | – | NOT RE-IMPLEMENTED in this mission | – |
| M273 | import and lineage | existing (M61/M213–M218) | yes | yes | existing | m201_m230 | inventory #3 | – | NOT RE-IMPLEMENTED | – |
| M274 | well architecture, schematic | existing (M57/M205) | yes | yes | existing | m201_m230 | inventory #6 | – | NOT RE-IMPLEMENTED | IV |
| M275 | survey, trajectory, saved views | existing; **`trajectory.py` now mutated** (TR-*) | yes | yes | `test_m270_*` (trajectory) | TR 4/4 | m270 | `7fe52ff` | PARTIAL (mutation added) | P10 |
| M276 | anti-collision screening | existing; **engine now mutated** (AC-*, including "never claims ISCWSA") | yes | – | `test_m270_*` | AC 12/12 | m270 | `7fe52ff` | PARTIAL | P19 |
| M277 | hydraulics | existing (W13 contracts) | yes | partial | existing | m83_m96, m121_m140 | inventory #10 | – | NOT RE-IMPLEMENTED | IV |
| M278 | mud volume | existing; **`mud_volume_persistence` now mutated** (MV-*) | yes | yes | `test_m270_*` | MV 4/4 | m270 | `7fe52ff` | PARTIAL | P8 (7.48 kept) |
| M279 | casing | existing; **`casing_persistence` now mutated** (CP-*); `transition F r3` kept | yes | yes | `test_m270_*` | CP 5/5 | m270 | `7fe52ff` | PARTIAL | P12, P18 |
| M280 | cementing | existing; no TOC/BOC inferred | yes | yes | existing | m52 | inventory #12 | – | NOT RE-IMPLEMENTED | IV |
| M281 | torque and drag | existing | yes | yes | existing | m121_m140, m231_m260 | inventory #13 | – | NOT RE-IMPLEMENTED | P3 |
| M282 | MSE, bit, BHA | existing; **`bit_performance` now mutated** (BP-*) | yes | yes | `test_m270_*` | BP 7/7 | m270 | `7fe52ff` | PARTIAL | IV |
| M283 | well control, Kill Sheet | existing; **`well_control` now mutated** (WC-*); R-2 review | yes | yes | `test_m270_*`, `test_m269_*` | WC 7/7 | m269, m270 | `7fe52ff` | PARTIAL; TRAINING AID | P11 |
| M284 | fishing | **D81 fixed** (`string_stretch` ∝ L²); **engine now mutated** (FI-*) | yes (W13 stuck pipe) | – | `test_m270_*`, `test_single_source_guard` | FI 8/8 | m270, D81 | `7fe52ff` | PARTIAL: engine corrected; methods remain legacy screening | IV |
| M285 | KPIs and NPT, full definitions | **`KPI_SPECS`** (window, scope, method, missing, counting) on every dashboard KPI; card tooltip | yes (dashboard tooltip) | – (derived) | `test_m285_kpi_specifications` (6), `test_m289_*` step 1–2 | KP 4/4 | `m290_catalogue_42eb03d.json` | `b21782b`, `8a76829` | PARTIAL: implemented, UI-integrated, mutated; the w12 Analysis KPIs have no structured spec | – |
| M286 | workbench statuses, clone, compare, rerun, archive | existing (M88/M108) | yes | yes | existing | m101_m120 | inventory #20 | – | NOT RE-IMPLEMENTED | – |
| M287 | Report Center, end-of-well reports | existing (M110/M135) | yes | yes | existing | m101_m120, m121_m140 | inventory #21, #22 | – | NOT RE-IMPLEMENTED | – |
| M288 | offline document intelligence | existing (M49–M52) | yes | yes | existing | m49–m52 | inventory #23 | – | NOT RE-IMPLEMENTED | P4, P5, P7 |
| M289 | 13-step cross-module journey | **`tests/test_m289_cross_module_journey.py`**: dashboard specs → KPI card → composed survey + frozen revision → anti-collision → mud volume save/verify → casing save/verify → well control → fishing → weighted ROP → workbench status → workbench re-run MATCH (nothing written) → end-of-well provenance | KPI card (widget); no MainWindow | yes (file DB) | 1 test, 13 steps, each checked by hand calculation | via the modules' catalogues | this report | `8a76829` | PARTIAL: synthetic, no MainWindow; the real-window journeys stay M139/M169/M229 | D63/D74 memory: about 200 MB per retained window |
| M290 | adversarial audit, gates, catalogue, roadmap | this report; capability catalogue (36 areas); roadmap | – | – | gates on the final tree | – | sections M290, B, C | final | PARTIAL (inherits) | – |

## M261 – live baseline and safe recovery

* **Live check:** HEAD = upstream = remote = `ac7657b`; working tree clean; `drill-Master` = `e3fa42a`.
* **Rebuilt after the sandbox reset:** the virtual environment (from the lock file) and the headless Qt stubs. The Qt smoke test passed.
* **Native tooling:** gdb, lldb, valgrind and eu-stack are all absent.
* **Lambda connections counted at the start:** `connect(lambda` occurs once in `main_window.py`, 103 times in tabs, 15 in dialogs and once in core.
* No recovery operation was needed: there was no lost commit, and no reset, clean or forced update was used.
* Every scratch probe that this report cites is copied into `m261-m290-evidence/`.

## M262 – independent audit of M231–M260 and reconciled defect register

Each claim of the M231–M260 report was re-checked against the tree and against what was measured again in this mission.

| ID | M231–M260 claim | Re-check in M261–M290 | Reconciled class |
|---|---|---|---|
| D77 | fixed `35f75e5` | collapse tests pass on `b21782b` (5,604 passed on `b21782b`) | **resolved** |
| D78 | fixed `cddd332` | privacy gate 0 findings on every commit of this mission | **resolved** |
| D79 | fixed `649e33d` | engine inventory regenerated by the tool (never by hand), current | **resolved** |
| D80 | fixed `db0cba3` | m121_m140 anchors unique; not re-run this mission | **resolved** (not re-run) |
| D74 | open, cause 1 identified, partially mitigated | M263 confirmed four attribute holders and 46 closures at 36 sites. M265 removed the stale-route and status-bar parts. Closed windows are still retained: 3 windows give 28,656 widgets in the probe | **partial** |
| D63 | reproduced in a diagnostic setup, not fixed | now reproduced **deterministically** (3/3); native frames collected; freed object not identified | **reproduced – unexplained** |
| D51 | open, not reproduced | one D51 event in 300 runs (`600b2f0`, 2026-11-07); 0 in 99 pytest-stage jobs since; 10/10 bounded stress runs | **non-reproduced** |
| R-1 | 7 modules mutated by no catalogue | `mutation_m261_m290`: 47 mutants, all 7 modules; 47/47 killed | **resolved** (test + catalogue) |
| R-2 | kill-sheet explicit 0 with the shoe at surface | case proof: differs only on {shoe MD = 0, casing ID ≤ 0}; both readings defensible | **owner/licence blocker** (P11), survivor justified |
| R-3 | closed by a test | unchanged | **test-only** |
| D6, D11 | datum/CRS partial | unchanged | **owner/licence blocker** (P10) |
| m50 trio | survived in M50 | unchanged; never retro-counted as killed | **method limitation** |
| SEC equivalent | equivalent | unchanged; never counted as killed | **method limitation** |
| "D51 resolved by bounded runs" | not claimed in M231–M260 | not claimed here either | – |
| M242–M256 "evidence review only" | stated in that report | confirmed; those areas were not re-implemented in M231–M260 | **test-only / review** |

New defects this mission:

| ID | Severity | Finding | Status |
|---|---|---|---|
| **D81** | P2 | `FishingEngine.string_stretch` used L instead of L². The constants (65.44 ppg steel, 9.625·10⁷) only fit L²: at MW = 0 they give L²/1.4708·10⁶ in, and ρgL²/2E for steel gives L²/1.4706·10⁶ in. A 10,000 ft string in 10 ppg mud showed **0.01 in instead of 53.03 in** in the W13 stuck-pipe calculator. The only test rebuilt the same linear expression (self-confirming). | **FIXED** `7fe52ff`. Constants unchanged; a test checks against Hooke's law for a hanging bar; `test_single_source_guard` corrected; mutant `FI-stretch-linear-in-length`. Stored stuck-pipe history computed before the fix re-runs as DIFFERENT, which is correct. |
| **D82** | P1 (caught before push) | My first M265 route registry stored strong bound methods in the owner's `__dict__`. Every tab became cyclic garbage, and `test_m132` crashed at its idle `gc.collect()` 2/2 (the baseline `ac7657b` passed 0/2 crashes). | **FIXED** before the first push: bound methods are recorded as `WeakMethod`; `test_the_route_registry_does_not_make_its_owner_cyclic_garbage` fails on the strong design |

## M263 – D74 signal/slot ownership audit

Method: build N real `MainWindow`s on fresh synthetic file databases, close each with an accepted close, drop the last Python reference, then list every object and closure that still reaches the window (`d74_holders_probe.py.txt`).

**Baseline `db0cba3`/`ac7657b`, one closed window:** the window stays alive with 9,554 widgets. Its holders were:
* `StatusBarManager._main_window` (process-wide singleton);
* `HomeTab.parent_window`;
* `WellInfoTab.main_window`;
* `DailyReportWidget.parent_window`.

There were also 46 closures at 36 sites capturing the window or one of those holders (`d74_holders_before_db0cba3.txt`).

Connections from the process-wide `SelectionManager`. These are the routes that deliver stale updates:

| Sender.signal | Receiver (slot) | Captured refs | Lifetime before | On accepted close (M265) | On shutdown |
|---|---|---|---|---|---|
| `well_changed`, `section_changed`, `report_changed`, `selection_cleared`, `wellbore_changed`, `context_changed` | every `DrillTabBase` tab (`_on_*_internal`) | bound method (tab) | until the tab's C++ object died, i.e. never while the window was retained | disconnected (`disconnect_window_routes` walks window plus `findChildren`) | Qt drops receiver connections on destruction |
| `wellbore_changed` | W12 analysis, W3b schematic | bound method | same | disconnected | same |
| `wellbore_changed`, `selection_cleared` | `TrajectoryViewerTab._sync_layers` | bound method | same | disconnected | same |
| `well_changed`, `selection_cleared`, `context_changed` ×3 | `MainWindow` (`_show_selected_well`, `_show_no_selected_well`, `_show_context_path`), `calculation_history_tab`, `documents_tab`, `_export_follows_well` | bound methods (lambdas replaced) | same | disconnected; count recorded as `_closed_route_count` | same |

Window-owned connections that capture the window or a tab (the sender dies with the window):

| Site | Kind | Effect | M265 decision |
|---|---|---|---|
| `main_window.py` tree / search / tab shortcuts (6 lambdas) | lambda → bound method | the closure captured the window | replaced by bound methods (`_expand_tree`, `_focus_search`, `_show_*_tab`, …) |
| `core/managers.py:101` autosave `QTimer(widget)` lambda | captures the tab | timer is a child of the tab; stopped on close since `55175e4` (no autosave for closed windows) | kept; it dies with the tab |
| `core/editor_bindings.py:125` edit-section lambdas | capture the tab | stored on the tab; a cycle through the tab | kept (Python cycle, freed together with the tab) |
| `main_window.py:3216` maintenance worker `finished` lambda | captures window and worker | only while a maintenance job runs | kept |
| W2 / Home / W1 internal lambdas (about 25) | capture the tab | together with the tabs' window attributes these keep a closed window alive | **kept on purpose** (see M265: freeing the window reproduces D63) |

**After M265** (`d74_holders_after_m265.txt`): one closed window is still alive with 9,554 widgets. `StatusBarManager` no longer holds it; the remaining holders are the three tab attributes, and 39 closures remain at 29 sites.

## M264 – D63 native diagnosis

* **Reproducer:** `tools/quality/d63_window_release_probe.py`, opt-in and never part of the suite. It applies weak window attributes at runtime only, which makes closed windows freeable.

  | Mode | Runs | Outcome |
  |---|---|---|
  | `auto` (Python's automatic gc) | 3 windows, 3 runs | **SIGSEGV 3/3** (crash after window 2, at a gc frame) |
  | `collect` (gc right after each free) | 2 runs | 0/2 crashes; 0 windows and 0 widgets left |
  | `retain` (the product behaviour) | 2 runs | 0/2 crashes; 3 windows retained |

* **Earlier scratch runs** of the same scenario: `PYTHONMALLOC=malloc` crashed 2/2, and `PYTHONMALLOC=debug` crashed 0/3. The fault therefore depends on memory reuse. Deleting the 15 orphan pyqtgraph `ViewBoxMenu`s first still crashed 4/4, so that hypothesis was rejected; such deletion is also forbidden.
* **Native frames:** `tools/quality/native/segv_bt.c`, loaded via LD_PRELOAD, prints the RIP and a dladdr stack scan. No debugger is available.
  * The fault is at `0x515ee3` in `/usr/bin/python3.11`: the instruction `call *0x30(%rax)`, which is CPython's dict deallocation calling `Py_TYPE(value)->tp_dealloc`. The function pointer read there was NULL in one run and an anonymous-memory address in another.
  * The scan shows recursive `SbkDeallocWrapper` frames and `__libc_free`, beneath `PySide::WeakRef::create`, `PySide::Signal::updateSourceObject`, `PyObject_SetAttr` and the interpreter loop.
  * Reading: during the next window's construction, a weak-reference allocation started cyclic gc. That gc deallocated the freed window's Shiboken wrappers, and a value in an instance `__dict__` being cleared was an object that had already been freed: **a use-after-free during wrapper deallocation**.
  * Frames from a stack scan can be stale, and no symbolized frame identifies the freed object. **Root cause NOT claimed.**
* **Consequence for M265:** closed windows stay retained, by design. The directive forbids destroying them all, and freeing them reproduces D63.

## M265 – D74 safe lifecycle fix

The window and its tabs now own their `SelectionManager` routes through a duplicate-refusing `SignalRoutes` registry. The registry records bound methods weakly (D82), and `disconnect_window_routes` releases the routes on the accepted close. The status bar holds the window weakly and is unregistered on close.

| Acceptance item | Result |
|---|---|
| open window still follows the selection | `test_an_open_window_follows_the_selection_and_a_closed_one_stops` |
| no stale callbacks to a closed window | same test: the label and `well_info_tab` are unchanged after close |
| no duplicate connections; reopen gives exactly one route set | `test_reopening_creates_one_route_set_and_routes_do_not_accumulate`; duplicate `connect` raises |
| no autosave for closed windows | kept from `55175e4`; mutant `MW-*` in m231_m260 |
| no invalid wrappers or segfault | no window is destroyed; full suite 5,604 passed on `b21782b`; D63 probe in `retain` mode 0/2 |
| measured reduction | status-bar holder removed: 4 → 3 attribute holders, 46 → 39 closures. Routes per closed window: all disconnected (`_closed_route_count == opened`). Retained widgets per window **unchanged** (9,554), so it is not counted as a memory fix |
| route registry adds no cycles | `test_the_route_registry_does_not_make_its_owner_cyclic_garbage` (gc disabled; refcount only) |

## M266 – D51 CI-hang diagnosis

* **Source:** the GitHub REST jobs API and check-run annotations for the 300 most recent workflow runs (GitHub timestamps 2026-10-27 to 2026-11-21). Raw job logs are served from a host outside the sandbox allowlist.
* **Failed jobs:** 61 in total. 49 are test failures, all explained and fixed in their missions: engine-inventory, privacy, constant-inventory and dependency-audit staleness, migration indexes, `test_m169`, `test_m115`. 11 are wall-clock or watchdog events. 1 is other.
* **Watchdog events:**
  * **One D51 event:** `600b2f0`, 2026-11-07, Python 3.12. Test frame `tests/test_m132_trajectory_layers.py:199` in `viewer`, blocked in pyqtgraph `AxisItem._updateLabel`.
  * The same run on Python 3.11 hit the then-10-minute watchdog with no frame.
  * The other watchdog events are `test_m122` worker-cancel timeouts, a different defect fixed in M124.
* **Since the D51 event:** 33 source-gate runs and 99 pytest-stage jobs (each a full suite including `test_m132`), with **0** D51 events. By the rule of three, the per-job rate is below about 3 % at 95 % confidence.
* **Bounded stress:** `test_m132` passed 10/10 with one competing busy-loop process (19–29 s each).
* **Conclusion: not reproduced; NOT resolved.** The watchdog stays at 900 s, there is no retry, and nothing is skipped or mocked.

## M267 – resource and runtime profile

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

Full findings: `m267_profile_summary.md`. Main points:
* Anonymous RSS is dominated by retained closed windows, about 200 MB each (D74 cause 1, held back by D63).
* The M265 tests were the largest single contributor, so M268 shares one window across them.
* Threads and fds are bounded.

Limits are kept distinct: CI job limit 60 min (user decision); per-test hang watchdog 900 s (`verify_release.py:113`); the D51 budget is the watchdog. None was raised.

## M268 – integrated lifecycle regression group and cleanup mutants

* **Regression group:** `test_m265_window_routes` (routes, registry cycles, open/closed/reopen, status bar), `test_d74_deferred_deletes_and_window_leak`, `test_m70_selection_audit`, `test_m83_selection_lifecycle`, `test_m102_context_probes` and `test_m132_trajectory_layers`.
* **The 66 window-building test modules** passed 945/945 after D82 was fixed. They crashed before the fix.
* **Test changes:** the selection test and the reopen test now share one closed window (M267 measured +254 MB for this module). The reopen test also asserts that the first, closed window ignores the reopen. A new test shows that unregistering another window keeps the registered one.
* **Cleanup mutants:** seven `LC-*` mutants in `mutation_m261_m290.py`: routes kept on close, status bar not unregistered, unregistering any window, strong status-bar reference, duplicate route accepted, registry holding its owner, child routes not disconnected. Result: LC 7/7 killed.
* The status-bar test no longer calls `gc.collect()`; it proves the release by reference counting with gc disabled.

## M269 – R-2 Kill Sheet (`KS-unfilled-casing-id-assessed`)

The full table and proof are in `m269_kill_sheet_domain_table.md`.

* **Where the mutant differs:** only for {shoe MD = 0, explicit casing ID ≤ 0}. With no cased zone, the current code refuses the annulus and the mutant reports the open-hole annulus.
* **Assessment:** it is not equivalent, and there is no defect to fix. Pinning either reading would decide a kill-sheet input policy, which belongs to P11 and would be an over-restrictive rule imposed just to kill a mutant.
* **Result:** SURVIVED with justification. The Kill Sheet stays **TRAINING AID**.
* **Observation (not changed):** a negative casing ID is silently "not assessed" rather than refused.

## M270 – mutation catalogue for the seven R-1 modules

`tools/quality/mutation_m261_m290.py`: stable IDs, exact anchors (each verified to match exactly once), machine-readable `--json`, and survivor justification fields.

| Module | Prefix | Mutants | Killed (with M270 tests) | Killed by pre-existing tests alone |
|---|---|---|---|---|
| `engines/anti_collision.py` | AC | 12 | 12 | 3 |
| `engines/bit_performance.py` | BP | 7 | 7 | 3 |
| `engines/fishing.py` | FI | 8 | 8 | 1 |
| `engines/trajectory.py` | TR | 4 | 4 | 2 |
| `engines/well_control.py` | WC | 7 | 7 | 4 |
| `mud_volume_persistence.py` | MV | 4 | 4 | 4 |
| `casing_persistence.py` | CP | 5 | 5 | 2 |
| **total** | | **47** | **47** (`complete=True`) | **20** |

The pre-existing suite would not have caught `FI-stretch-linear-in-length`, which is D81. Evidence: `m270_catalogue_7fe52ff.json`, `m270_baseline_existing_tests_only.json`.

## M271 – survivor reconciliation and reach map

| Catalogue | Mutants | K | S | E | I | complete | Notes |
|---|---|---|---|---|---|---|---|
| 17 catalogues on `db0cba3` (M231–M260) | 1108 | 1103 | 4 | 1 | 0 | all `True` | m50 trio S (stays S in M50); SEC-empty-password-unlocks E (never K); KS-unfilled-casing-id-assessed S (justified, M269) |
| `mutation_m261_m290` (`42eb03d`) | 58 | 58 | 0 | 0 | 0 | `True` | 47 R-1 + 7 LC + 4 KP |
| **all 18** | 1,166 | 1,161 | 4 | 1 | 0 | all `True` | |

* **Complete:** YES. Every catalogue ran fully, and none used `--only`.
* **All killed:** NO. There are 4 justified survivors and 1 equivalent, and the equivalent is not counted as killed.

The reach map covers 30 product areas against the catalogue prefixes that mutate them. The table lists the 30 areas of the M241 inventory; each row names the catalogues that mutate code in it.

| # | Area | Catalogues | # | Area | Catalogues |
|---|---|---|---|---|---|
| 1 | selection context | m70_m76, m101_m120, m231_m260 (MW), **m261_m290 (LC)** | 16 | mud volume | m101_m120 (engine), **m261_m290 (MV)** |
| 2 | DDR workspace | m54/m83_m96, m201_m230 | 17 | W13 classifications | m83_m96, m121_m140 |
| 3 | DDR import, lineage | m61_m67, m201_m230 | 18 | KPIs, dashboard | m53_m56, m101_m120, **m261_m290 (KP)** |
| 4 | review queue | m231_m260 | 19 | operational analysis, NPT | m48, m101_m120 |
| 5 | data quality | m201_m230 | 20 | workbench / history | m101_m120 |
| 6 | architecture, schematic | m201_m230 | 21 | reports, export | m101_m120 |
| 7 | surveys | m101_m120, **m261_m290 (TR)** | 22 | end-of-well package | m121_m140 |
| 8 | plans, anti-collision | m101_m120, **m261_m290 (AC)** | 23 | document intelligence | m49–m52 |
| 9 | 2D/3D views | m50 | 24 | UI integration | m46–m48 |
| 10 | hydraulics | m83_m96, m121_m140 | 25 | units, constants | m141_m170 |
| 11 | casing | m231_m260 (CAS), **m261_m290 (CP)** | 26 | security | m121_m140 (SEC) |
| 12 | cement | m52 | 27 | migrations, backup | m201_m230 |
| 13 | torque and drag | m121_m140, m231_m260 (TD) | 28 | tubular catalogue | m201_m230 |
| 14 | MSE, bit | m231_m260 (MSE), **m261_m290 (BP)** | 29 | planning, cost, safety | m171_m200 |
| 15 | well control, kill sheet | m231_m260 (KS), **m261_m290 (WC)** | 30 | installer, release gate | none (CI only) |

**Not reached by any catalogue:** area 30 (installer) and the fishing *UI* (the fishing engine is now reached).

## Part II – implementation in this mission (M272–M289)

* **M285 (implemented, UI-integrated).**
  * What: `core/operations_dashboard.KPI_SPECS` gives each of the 20 dashboard KPIs its window, scope, method, missing-data behaviour and counting rule. The definition, unit and source already existed, so all seven fields are now complete.
  * Where it shows: every `Kpi` carries the spec, and the KPI card tooltip shows all seven fields.
  * Basis: the specifications restate the existing definitions and the code. Two claims beyond the sentences were checked against the code: NPT uses only 24-hour rows, and counts return 0, not No data.
  * Tests: completeness, the status-group partition (no double counting), NPT share from the same rows as NPT hours, and the tooltip.
* **M284 (engine correction, user-facing).**
  * D81: the W13 stuck-pipe stretch is now physically consistent.
  * The fishing methods remain legacy screening approximations, and no method was invented.
* **M275, M276, M278, M279, M282, M283 (qualification added):** mutation coverage was added for the modules these phases required to be mutated.
* **M289 (synthetic cross-module journey).**
  * One file database carries 13 steps. Each step consumes an earlier result: the TVD and MD of the composed survey feed well control and fishing, and the saved runs feed the workbench.
  * Each step is checked by hand calculation:
    * root-sum-square SF 30/5 = 6;
    * 500 + 40 − 12 = 528 bbl;
    * Barlow 6,865.5 psi;
    * kill MW = MW + SIDPP/(0.052·TVD);
    * D81 stretch;
    * weighted ROP 20 m/h versus a mean of 22.5.
  * No MainWindow is opened. Each closed window is retained, at about 200 MB (M267), and the real-window journeys are M139/M169/M229.
* **Not re-implemented in this mission:** M272, M273, M274, M277, M280, M281, M286, M287 and M288. Their capability state is unchanged from the M241 inventory and is restated in the M290 catalogue.

## M290 – adversarial audit

| Check | Result |
|---|---|
| "D74 fixed"? | No. Routes and status bar are fixed; retained windows are unchanged and stated as such. |
| "D63 root cause"? | Not claimed; native frames point to a use-after-free during wrapper deallocation, but the object is unidentified. |
| "D51 resolved"? | Not claimed; 0 events in 99 jobs is a bound, not a fix. |
| Mutation counts | equivalent never counted as killed; m50 trio not retro-counted; `--only` never used for a completeness claim |
| D81 changes a formula | documented here, in the engine comment and in the test; constants unchanged; derivation shown |
| Over-restriction to kill a mutant | none (M269) |
| Assertions deleted or scope reduced | none. `test_single_source_guard`'s expected value was corrected because it was self-confirming and wrong. `test_m70`'s source pin was updated to the new connect spelling, and the assertion is kept |
| Limits raised | none |
| Dependencies installed | none beyond the existing lock file; no external code adopted |
| Owner decisions taken | none (P1–P19 untouched) |
| Gates | see A |

## B. Capability catalogue

See `docs/engineering/M241_CAPABILITY_INVENTORY.md`, section "M290 catalogue (36 areas)". Each area lists entry point, inputs and units, method and version, evidence, mutation, persistence, provenance, state (vocabulary of this mission) and limitations and gates.

## C. Roadmap

See `docs/engineering/DRILLMASTER_ENGINEERING_ROADMAP_M290.md` (six categories).

## D. Overall status

**PARTIAL.** UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED. Real DDR acceptance NOT RUN. P1–P19 OWNER REVIEW REQUIRED.
