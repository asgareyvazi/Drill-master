# M231–M260 – Repository recovery, engineering completion, reliability qualification and final capability roadmap

**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**
Branch `arena/72010272-drill-master` only. Final **code** SHA: **`db0cba301d42b99a59606fccc79c17144e2350a2`**.
This report and the evidence that follows the code are in the documentation commit(s) after it; the remote SHA of
the branch head is verified with `git ls-remote` after the push, outside this file (a commit cannot name itself).
All tests use SYNTHETIC data. `08-DDR` and the confidential PDFs were never opened, parsed or hashed. Real-DDR
acceptance: **NOT RUN**. Owner decisions P1–P19: **OWNER REVIEW REQUIRED** (none taken on the owner's behalf).

## Overall status (section D in short)

**PARTIAL.** Delivered: push access restored and verified (M231), report and matrix reconciled (M232), baseline
(M233), D74 root cause with one of its two causes and both side effects fixed (M234/M235), mutation reconciliation
(M238), a new 21-mutant catalogue (M239) that found and fixed a real engineering defect (**D77**, API 5C3
transition collapse), final-tree qualification (M240), capability inventory (M241), source re-audit (M257). Not
delivered as asked: D74 cause 1, D51 and D63 stay OPEN; M242–M256 were carried out as evidence reviews, not as new
product work; real-DDR acceptance and Windows / field acceptance are outside the sandbox.

## A. Delivery verification

| Item | Evidence |
|---|---|
| M201–M230 report delivered | `eaa003f` pushed; remote verified by `git ls-remote` (M231); addendum `8c9f21d` |
| Commits of this mission | `eaa003f` → `8c9f21d` → `cfaf476` → `55175e4` → `4b6514d` → `cddd332` → `4df5c01` → `5ff4d09` → `35f75e5` → `b8b2c3a` → `649e33d` → **`db0cba3` (final code)** → documentation commit(s) |
| Each push | verified by `git ls-remote origin arena/72010272-drill-master` after the push (never from a local message) |
| No rewrite | no force-push, amend, rebase, tag, release, signing or remote branch deletion; `drill-Master` (`e3fa42a`) and `main` untouched |
| Sandbox resets | 2026-11-18 (sixth reset): local HEAD fell back to `4336ea3`, venv, Qt stubs, `/home/user/m234` (drafts, chain run, D63 reproducer files) erased. Recovered without discarding anything: `git update-ref` compare-and-swap `4336ea3` → `b8b2c3a` (= remote), `read-tree HEAD`, upstream restored, tree clean; venv rebuilt from `requirements-lock.txt` + the CI tool pins, stubs from `tools/qt_headless_env.sh` |
| Working tree at the end | clean (`git status --short` empty) after the last documentation commit |
| Baseline | `docs/mission-reports/m231-m260-evidence/m233_baseline.md` |

### CI per pushed SHA (GitHub check-runs; only the latest attempt is visible there)

| SHA | 3.11 | 3.12 + coverage | 3.13 | Windows | Note |
|---|---|---|---|---|---|
| `8c9f21d` | ✅ | ✅ | ✅ | ✅ | report addendum |
| `cfaf476` | cancelled at 60 min | cancelled at 60 min | ✅ | ✅ | cost of `allWidgets()` per test (D74 item 6) |
| `55175e4` | cancelled | cancelled | cancelled | cancelled | superseded by the `4b6514d` push |
| `4b6514d` | ❌ 5522 / 1 / 4 | ❌ 5522 / 1 / 4 | ❌ 5522 / 1 / 4 | ✅ | the one failure is D78; legs finished in 33–46 min |
| `cddd332` … `35f75e5` | cancelled | cancelled | cancelled | cancelled | superseded by the next push |
| `b8b2c3a` | ❌ 5550 / 1 / 4 | ❌ 5550 / 1 / 4 | ❌ 5550 / 1 / 4 | ✅ | the one failure is D79; legs finished in 37–51 min |
| `649e33d` | ✅ 40 min | ✅ 47 min, coverage 72.23 % | ✅ 40 min | ✅ 30 min | green; superseded because its local qualification exposed D80 |
| **`db0cba3`** | ✅ 40 min | ✅ 50 min, coverage 72.23 % | ✅ 51 min | ✅ 30 min, 4 × 119 tests, 0 failures | **final code** |

The 60-minute job limit (owner decision), the per-test hang watchdog and the D51 / M122 budgets were **not**
changed; no retry or skip was added. Reruns: none. The watchdog value in the repository is **900 s**
(`verify_release.TEST_HANG_SECONDS`, set in M124, `f790f40`; `tests/conftest.py` arms it only when
`DRILLMASTER_TEST_HANG_SECONDS` is set, otherwise it is off). The mission text speaks of a 300 s watchdog; no
300 s value exists in the repository, and none was introduced or raised. The local qualification runs exported
`DRILLMASTER_TEST_HANG_SECONDS=900`, the same value CI uses through `verify_release.py`.

## Phase register

| ID | Objective | Work | Files | Tests / evidence | SHA | Status | Blockers |
|---|---|---|---|---|---|---|---|
| M231 | Restore push, deliver report | CAS recovery after a sandbox reset; push; remote check | – | `ls-remote` | `eaa003f`, `8c9f21d` | **DONE** | – |
| M232 | Reconcile report and matrix | final vs intermediate mutation numbers with SHA; m50 trio; equivalent; D74 OPEN; M212 / M230 PARTIAL | matrix, M201–M230 report addendum | – | `8c9f21d` | **DONE** | – |
| M233 | Immutable baseline | SHAs, status, diffs, stash, worktrees, environment, CI limits | `m233_baseline.md` | – | `cfaf476` | **DONE** | – |
| M234 | D74 root cause | per-test RSS / widget profile, probes | `tools/quality/pytest_rss_profile.py`, `d74_*`, `d74_d63_probes/` | `d74_d63_root_cause.md` | `cfaf476` | **DONE** (cause found) | – |
| M235 | Smallest justified fix | per-test deferred-delete flush; bound-method Export follower; closed window stops autosave; flush without `allWidgets()` | `tests/conftest.py`, `main_window.py` | `test_d74_deferred_deletes_and_window_leak.py`, `test_m70…test_zz_…autosave…` | `cfaf476`, `55175e4`, `4b6514d` | **PARTIAL** – cause 2 fixed, cause 1 OPEN | D63 blocks destroying windows |
| M236 | D51 hang | 12 bounded runs with faulthandler (8 plain, 4 under 2 CPU hogs) | `d51_bounded_repetition_cddd332.txt` | all passed, no hang | `4df5c01` | **OPEN – not reproduced** | CI-only |
| M237 | D63 segfault | diagnostic reproducer (destroying closed windows); rebuilt probe on the final tree | `d74_d63_probes/d63_reproducer_rebuilt_test.py.txt` | probe on `db0cba3`: 1 / 6 runs SIGSEGV inside `gc.collect()`, control without the disposal 0 / 6 (`d63_rebuilt_probe_runs_db0cba3.txt`) | – | **REPRODUCED IN A DIAGNOSTIC SETUP – ROOT CAUSE NOT IDENTIFIED** | no native debugger |
| M238 | Reconcile 16 catalogues | tool + table for `2764071` and `39b4d52` | `tools/quality/mutation_reconcile.py`, `m238_mutation_reconciliation.md` | identical output for both SHAs | `cddd332` | **DONE** | – |
| M239 | Meaningful mutants | `mutation_m231_m260` 22 mutants; tests for every killable survivor; D77 fixed | `tools/quality/mutation_m231_m260.py`, `tests/test_m239_*.py`, `core/engineering/engines/casing.py` | final `db0cba3`: 21 KILLED, 1 SURVIVED (documented), 0 E, 0 I | `b8b2c3a`; 22nd mutant (D80) in `db0cba3` | **DONE** | – |
| M240 | Final qualification | full suite, gates, 17 catalogues, CI on `db0cba3` (earlier candidate `649e33d` kept) | `final_db0cba3/`, `final_649e33d/` | §M240 | `db0cba3` | **DONE** (5551 passed / 0 failed / 4 opt-in skips; 17 / 17 catalogues `complete=True`, 1108 mutants, 1103 K / 4 S / 1 E / 0 I; CI 4 / 4) | – |
| M241 | Capability inventory | 11 statuses, 30 capabilities, mutation-reach finding | `docs/engineering/M241_CAPABILITY_INVENTORY.md` | – | `35f75e5` | **DONE** | – |
| M242–M256 | Product audits | evidence review per area on the final tree; D77 found in M246 scope | inventory | – | – | **PARTIAL (review only)** | scope / time |
| M257 | P1–P19, 50-source register | re-audit 2026-11-17: 46 unchanged, 3 new commits, 1 archived, no licence change | `oss_reaudit_m257.{txt,json}` | – | `35f75e5` | **DONE** (no owner decision taken) | owner |
| M258 | 20-step E2E | `test_m169_twenty_step_journey` (20 steps) and `test_m229_product_journey` (35 steps), fresh file databases, real MainWindow, offscreen | – | final suite | `db0cba3` | **DONE (synthetic, offscreen Linux)** – both journeys passed in the final suite | Windows desktop (P17) |
| M259 | Adversarial review | mutation reach, D77, D78, D79, D80, KS guard, harness | §M259 | – | `db0cba3` | **DONE** | – |
| M260 | Final report + matrix | this file; matrix section M231–M260 | – | – | docs | **DONE** | – |

## D74 / D51 / D63 (M234–M237)

Full analysis: `docs/mission-reports/m231-m260-evidence/d74_d63_root_cause.md` (sections 1–7).

* **D74 – OPEN, ROOT CAUSE IDENTIFIED, PARTIALLY MITIGATED.** (1) Module fixtures close their `MainWindow` without
  destroying it; shiboken-held lambda slots that capture the window form a cycle the collector cannot see, so
  ~9,500 widgets per module stay alive (14 windows, ~169,000 widgets by `test_m95`). Destroying them crashes (D63).
  OPEN. (2) Deferred deletions were flushed per module (m87 grew +717 MB); now per test – **fixed**. Side effects
  found and fixed: autosave timers of closed windows logged into later tests (`55175e4`); counting `allWidgets()`
  per test cost ~11 min per suite and pushed two CI legs past 60 min (`4b6514d`). Before / after (anon RSS):
  m137 1,165,580 → 861,432 kB; m53 2,618,988 → 2,323,756 kB; m87 start 3,110,340 → 2,694,628 kB. The D74 test
  passed in every CI leg of `4b6514d` and `b8b2c3a`. On the final code `db0cba3` the full suite again passed with the D74 line "14 closed MainWindows still
  alive after test_m95_ux_responsiveness (169,133 live widgets)": cause 1 is unchanged.
* **D51 – OPEN (not reproduced).** 8 / 8 runs of `tests/test_m132_trajectory_layers.py` passed (~20 s each) and
  4 / 4 under two CPU-burning processes (~31 s); no hang, no stack to analyse. Only observed in CI under full-suite
  load. No timeout raised, no retry.
* **D63 – REPRODUCED IN A DIAGNOSTIC SETUP, ROOT CAUSE NOT IDENTIFIED.** Destroying closed MainWindows leaves
  ~5,229 invalid shiboken wrappers in cyclic garbage; a later collection segfaulted (3 / 3 under faulthandler,
  1 / 4 module-scoped, 5 / 8 function-scoped, 0 / 2 baseline). The original reproducer files were lost in the
  sandbox reset; a rebuilt probe was run on `db0cba3`: 1 / 6 runs segfaulted with a garbage-collection frame
  in `gc.collect()` after the closed windows were destroyed, 0 / 6 runs of the identical control without the
  disposal (`d74_d63_probes/d63_rebuilt_probe_runs_db0cba3.txt`). The sample is small and the freed native object
  is not identified (no native debugger or debug Qt build in the sandbox). Not fixed.

## Mutation (M238 / M239)

* **M238** (`m238_mutation_reconciliation.md`, regenerated by `tools/quality/mutation_reconcile.py <sha>`): final
  `2764071`: 16 catalogues, all `complete=True`, 1086 mutants, 1082 KILLED, 3 SURVIVED (m50 trio, killed in m52 but
  not counted in m50), 1 EQUIVALENT (SEC-empty-password-unlocks, justified at `mutation_m121_m140.py:800`),
  0 INVALID. Intermediate `39b4d52`: 1081 / 4 / 1. The old 541 → 570 count omitted m46's 29 mutants.
* **M239 – `tools/quality/mutation_m231_m260.py`, 22 realistic mutants**: MSE snapshot unknown / missing vs zero
  (5), DDR review-queue counting and continuation lineage (6), closed-window autosave (1), D74 per-test flush (1,
  added with D80), casing (3), torque and drag (3), kill sheet (3). Every run is kept as evidence:

| Run | Tree | Mutants | KILLED | SURVIVED | E | I | complete |
|---|---|---|---|---|---|---|---|
| first | `4df5c01` | 12 | 7 | 5 | 0 | 0 | True (`mutation_m231_m260_first_run_4df5c01.json`) |
| after tests | `5ff4d09` | 12 | 12 | 0 | 0 | 0 | True (not kept: erased by the reset) |
| extended | `35f75e5` | 21 | 19 | 2 | 0 | 0 | True (`mutation_m231_m260_intermediate_35f75e5.json`) |
| after tests | `b8b2c3a` | 21 | 20 | 1 | 0 | 0 | True (not kept: erased by the reset) |
| candidate | `649e33d` | 21 | 20 | 1 | 0 | 0 | True (`final_649e33d/mutation_m231_m260.json`) |
| **final** | **`db0cba3`** | 22 | 21 | 1 | 0 | 0 | True (`final_db0cba3/mutation_m231_m260.json`) |

  The remaining survivor, `KS-unfilled-casing-id-assessed`, is **not** declared equivalent: the annulus loop already
  refuses an annular ID ≤ pipe OD, so the only distinguishing input is a shoe at MD 0, where the mutant's open-hole
  annulus is not wrong; no test can demand the refusal without asserting an over-restriction (engineering review
  item R-2, written in the catalogue).
* **Mutation reach:** the casing engine, the torque-and-drag engine and the kill sheet were mutated by no catalogue
  before M239. Still unmutated: `engines/anti_collision.py`, `bit_performance.py`, `fishing.py`, `trajectory.py`,
  `well_control.py`, `casing_persistence.py`, `mud_volume_persistence.py` (R-1, roadmap C1).

## D77 – API 5C3 transition collapse (found by M239, fixed in `35f75e5`)

`CasingEngine._abc` used the denominator `Yp (3 B/A − (B/A)³ − 1)` for the transition coefficient F instead of
`Yp (r − B/A)(1 − r)²`, r = 3(B/A)/(2 + B/A). F and G were negative, the plastic/transition limit lay above the
transition/elastic limit (55 ksi: 39.42 vs 37.21) and the transition regime was never used: walls in that band were
rated with the plastic formula, too low (conservative but wrong).

| Synthetic geometry | D/t | Before | After |
|---|---|---|---|
| 9.625 × 0.352 in, 55 ksi | 27.34 | plastic 1835.3 psi | transition 2023.4 psi |
| 13.375 × 0.380 in, 55 ksi | 35.20 | plastic 493.1 psi | transition 1130.5 psi |
| 10.75 × 0.350 in, 80 ksi | 30.71 | plastic 705.4 psi | transition 1730.7 psi |
| 9.625 × 0.395 in, 80 ksi | 24.37 | plastic 2788.8 psi | transition 3086.0 psi |
| 9.625 × 0.472 in, 80 ksi | 20.39 | plastic 4754.0 psi | plastic 4754.0 psi (unchanged) |
| 20.0 × 0.300 in, 55 ksi | 66.67 | elastic 163.3 psi | elastic 163.3 psi (unchanged) |

Oracle (`tests/test_m239_engine_semantics.py`): F derived from the condition that the transition line meets the
elastic curve at the transition/elastic limit, plus continuity at both boundaries and tangency, for 40–125 ksi;
it does not reuse the engine formula. The method id gained `transition F r3`, so casing runs saved earlier verify
as DIFFERENT (`method_matches=False`) instead of silently matching. Documented in
`ENGINEERING_CAPABILITY_STATUS.md`, `ENGINEERING_METHODS_AND_LIMITATIONS.md` and the generated `ENGINE_INVENTORY.md`.
Method approval (P12) and independent validation are still required before engineering use. No other formula,
constant or rounding was changed in this mission; 7.48 / 7.48052 untouched (P8).

## M240 – qualification of the final code `db0cba3`

Everything below ran on the committed tree `db0cba301d42b99a59606fccc79c17144e2350a2` (clean working tree,
`dirty=0` in `chain_progress.txt`). Evidence: `docs/mission-reports/m231-m260-evidence/final_db0cba3/`.

| Check | Result |
|---|---|
| Full suite, local (Python 3.11.2, PySide6 6.8.1.1, offscreen, no coverage, `-X faulthandler`, watchdog 900 s as in CI) | **5551 passed, 0 failed, 4 skipped (opt-in), 33 warnings in 2,409.17 s**; exit 0; lowest MemAvailable 506,976 kB (`full_suite_db0cba3_local_nocov.log.txt`, `load_samples_chain_db0cba3.txt`) |
| CI source gate, ubuntu-24.04 | 3.11 ✅ 09:18→09:58; 3.12 + coverage ✅ 09:18→10:08, **72.23 %** (78,079 / 108,098 over 286 files; floor 45.50 %, project minimum 70.46 %); 3.13 ✅ 09:18→10:09 (`ci_db0cba3.txt`) |
| CI Windows release gate, windows-2022 | ✅ 09:18→09:48; 4 × the Windows regression subset: 119 tests each, 0 failures / errors / skips, no native crash, 0 processes left, peak 231.4–234.3 MB |
| Reruns | none (no CI rerun, no local rerun of any catalogue or of the suite on this SHA) |
| Lint and gates | ruff (`core dialogs tabs tests`), privacy, constant inventory, silent-exception ceiling, dependency audit, `engine_inventory --check`: all clean on the final tree (re-run before the documentation commit) |
| Mutation catalogues | **17 / 17 `complete=True`, 1108 mutants: 1103 KILLED, 4 SURVIVED, 1 EQUIVALENT, 0 INVALID**, 10,935 s, run one after the other on the same tree (`reconciliation_db0cba3.md`, `mutation_*.json`, `mutation_summary_lines.txt`) |

Not fully killed, each documented:

* m50 52 / 55: the three survivors `R-file-name-context-dropped`, `R-absent-ignores-context`,
  `A-sentence-inherits-any-size` are killed by m52 but, by rule, **not** counted as killed in m50.
* m121_m140 329 / 330: `SEC-empty-password-unlocks` EQUIVALENT (justification at `mutation_m121_m140.py`, the
  equivalent flag is set in the catalogue, never counted as KILLED). The two D52 mutants are KILLED again (D80).
* m231_m260 21 / 22: `KS-unfilled-casing-id-assessed` SURVIVED (R-2, see M239).

All other 14 catalogues are fully killed: m46 29, m47 26, m48 44, m49 38, m51 29, m52 70, m53_m56 38, m61_m67 19,
m70_m76 18, m83_m96 20, m101_m120 184, m141_m170 28, m171_m200 103, m201_m230 55.

Against the superseded candidate `649e33d` (1107 mutants, 1100 K / 5 S / 1 E / 1 I, kept in `final_649e33d/`
with its own reconciliation and a README): +1 mutant (`D74-per-test-flush-skipped`), the D52 INVALID and the D52
SURVIVED became KILLED (D80). The `649e33d` CI (4 / 4 green) and its suite (5551 / 0 / 4) remain valid history
but are not the final qualification.

Limits kept distinct: the CI job limit stays 60 minutes; the per-test watchdog stays at the repository value of
900 s (the local chain exported that same value; the "300 s" of the mission text does not exist in the
repository and nothing was raised); the D51 / M122 budgets were not touched. D51 did not occur in any run.

## M241 – capability inventory

`docs/engineering/M241_CAPABILITY_INVENTORY.md`: 11 status codes, 30 capabilities with entry point, inputs and
units, method / version, evidence, status, limitations and gates. Writing it corrected five rows that would
otherwise have cited catalogues that never mutate those modules.

## M242–M256 – product audits (evidence review against the final tree)

These phases were **not** carried out as new implementation work. For each area the existing evidence on the final
tree was reviewed and the status set no higher than that evidence (inventory row in brackets).

| Phase | Area | Finding | Status |
|---|---|---|---|
| M242 | DDR daily workspace (2) | journeys m169 / m229, carry-forward only after confirmation (`ddr-carry-forward-v1`) | PQ · WF; real DDR NOT RUN |
| M243 | Ingestion lineage source → parsed → normalized → correction → accepted (3, 4) | revision lineage M218, review queue M150; M239 added 6 review-queue mutants (all killed after 4 new tests) | PQ (synthetic) |
| M244 | Architecture, trajectory (6–9) | no change; ISCWSA absent (P19), datum / CRS P10 | PQ · IV · OD |
| M245 | Hydraulics (10) | W13 contracts; no independent validation | PQ · IV |
| M246 | Casing and cement (11, 12) | **D77 found and fixed**; casing engine now mutated (3 mutants killed) | PQ · LD · IV |
| M247 | Torque and drag (13) | engine now mutated (3 killed); LGPL libraries not adopted (P3) | PQ · IV |
| M248 | MSE, bit, BHA (14) | an absent MSE headline result stored as 0 psi passed the tests → test added (mutant killed) | Q · IV |
| M249 | W13 classifications (17) | unchanged 9 / 10 / 4 / 1 / 1 / 2 | Q |
| M250 | KPIs (18) | definitions, units and sources as before | Q |
| M251 | Workbench MATCH / DIFFERENT / NOT_REPRODUCIBLE / UNREADABLE (20) | the D77 method id keeps older casing runs DIFFERENT | Q |
| M252 | Reports (21) | timestamped outputs never claimed byte-identical | PQ |
| M253 | Offline document intelligence (23) | no models shipped; OCR / MinerU owner-gated | LS · OD |
| M254 | UI integration RTL + English (24) | offscreen only | PQ · WF |
| M255 | Units and semantics (25) | 7.48 owner gate kept (P8); unknown-vs-zero checked in MSE, T&D, kill sheet | PQ · OD |
| M256 | Security, migrations, recovery (26, 27) | unchanged; encryption / ACL / signing owner-gated | PQ · OD |

## M257 – owner decisions and source register

P1–P19 (`docs/engineering/M196_OWNER_DECISION_PACKAGES.md`) re-read: nothing in this mission resolves or changes
any of them; all **OWNER REVIEW REQUIRED**. D77 adds evidence to P12 (method approvals): the casing method id
changed. The 50-source register was re-audited on 2026-11-17 with `tools/quality/oss_reaudit_m193.py`
(`oss_reaudit_m257.txt` / `.json`): 46 UNCHANGED, 3 NEW COMMITS (mud-engineer-pro, wellbrief, BoreTHM; licence
unchanged), 1 ARCHIVED (api-evangelist/national-oilwell-varco), no licence change, nothing adopted. The three
repositories (Drill-master, Prog-Proc, DrillAI) stay independent.

## M258 – synthetic end-to-end qualification

`tests/test_m169_end_to_end_journey.py::test_m169_twenty_step_journey` (20 numbered steps: real MainWindow, fresh
file database, real authorization, real DDR pipeline on a copy of the synthetic workbook with SHA-256 check,
review queue, audited decisions, cross-well refusal, pending context and autosave, tubular library publish,
snapshot drift) and `tests/test_m229_product_journey.py` (35 steps incl. W13 Casing Strength, backup → modify →
restore). Both ran in the final full suite on `db0cba3` and **passed** (5551 passed, 0 failed; the 4 skips are the
opt-in real-DDR, MinerU and Windows-bundle tests, never counted as passes). Limitation: offscreen Linux only; not a Windows desktop
or field run (P17); the journeys were not extended with D77-specific steps (unit tests cover it).

## M259 – adversarial review and defect register

| ID | Severity | Finding | Status |
|---|---|---|---|
| D77 | P2 | API 5C3 transition collapse never used (negative F, G) | **FIXED** `35f75e5`; method id `transition F r3` |
| D78 | P3 | the D74 per-test CSV committed in `55175e4` carried 31 synthetic secret-pattern test ids; the privacy gate failed locally and on all CI Linux legs at `4b6514d` | **FIXED** `cddd332` (ids redacted, note in `d74_d63_root_cause.md`) |
| D79 | P3 | `ENGINE_INVENTORY.md` edited by hand in `35f75e5`; the generated test-file counts were stale and `test_m75_engine_inventory` failed on all CI Linux legs at `b8b2c3a` | **FIXED** `649e33d` (regenerated with `tools/quality/engine_inventory.py --write`) |
| D80 | P3 | the D74 conftest changes (`cfaf476`, `4b6514d`) made `mutation_m121_m140` `D52-flush-is-a-no-op` INVALID (its 4-space anchor also matched the new per-test flush) and let `D52-module-fixture-skips-the-flush` SURVIVE (the per-test flush ran the test's deletion); found by the full catalogue run on `649e33d` | **FIXED** `db0cba3`: unique anchor; `test_the_conftest_flushes_between_modules` now leaves a deletion in a module fixture's teardown (beyond the per-test flush); new mutant `D74-per-test-flush-skipped` in m231_m260 |
| R-1 | review | 5 engines and 2 persistence modules are mutated by no catalogue | OPEN → roadmap C1 |
| R-2 | review | kill sheet: annulus refused for an explicit casing ID 0 even with the shoe at surface (no cased zone) | OPEN – engineering review item |
| R-3 | review | redundant mud-weight guard in T&D: the precedence of the scalar check is now pinned by a test | CLOSED (test) |
| D74 | P3 | see above | OPEN (cause 1) |
| D51 | P2 | see above | OPEN |
| D63 | P2 | see above | REPRODUCED IN A DIAGNOSTIC SETUP, NOT FIXED |
| D6, D11 | – | datum / CRS partial (P10) | PARTIAL |

Process notes: D78, D79 and D80 were introduced by this mission and caught by the repository's own gates, which is why
the final suite and CI on the final code matter more than a local subset. A `pkill -f` once matched the sandbox
shell's own command and ended that shell (no repository or process data lost); the standing rule against
`pkill -f` is restated.

## B. Capability catalogue since inception (27 areas)

Inventory numbers in brackets; codes as in M241 (Q qualified-synthetic, PQ partially qualified, LS limited scope,
OD owner decision, LD licensed data, IV independent validation, WF Windows / field).

| # | Area | Status |
|---|---|---|
| 1 | Hierarchy and selection context (1) | Q · WF |
| 2 | DDR daily workspace (2) | PQ · WF |
| 3 | DDR import Excel / PDF, lineage (3) | PQ · WF (real DDR NOT RUN) |
| 4 | Review queue, continuation (4) | Q |
| 5 | Data-quality workspace (5) | Q |
| 6 | Well architecture, schematic (6) | PQ · IV |
| 7 | Surveys, integrity, datum (7) | Q · IV · OD |
| 8 | Plan designer, anti-collision screening (8) | PQ · IV |
| 9 | Trajectory views (9) | Q (D51 OPEN) |
| 10 | Hydraulics (10) | PQ · IV |
| 11 | Casing (11) | PQ · LD · IV (D77 fixed) |
| 12 | Cement (12) | PQ · IV |
| 13 | Torque and drag (13) | PQ · IV |
| 14 | MSE, bit, BHA (14) | Q · IV |
| 15 | Well control, kill sheet (15) | PQ · OD · IV |
| 16 | Mud volume, mud engineering (16) | PQ · OD |
| 17 | W13 classifications (17) | Q |
| 18 | KPIs, dashboard (18) | Q |
| 19 | Operational analysis, NPT, trends (19) | Q |
| 20 | Calculation history / workbench (20) | Q |
| 21 | Reports and export (21) | PQ |
| 22 | End-of-well package (22) | Q |
| 23 | Offline document intelligence (23) | LS · OD |
| 24 | UI integration RTL + English (24) | PQ · WF |
| 25 | Units and semantics (25) | PQ · OD |
| 26 | Security, migrations, backup / recovery (26, 27) | PQ · OD |
| 27 | Planning, procedures, cost, safety, services, equipment, tubular import, Windows installer (28–30) | PQ / LS · LD / PQ · OD · WF |

## C. Prioritized roadmap

1. **Near-term (no owner input):** mutation catalogues for the 7 unmutated modules (R-1); D74 cause 1 – replace the
   window-capturing lambda slots so closed windows can be collected without destruction; D63 native frame on a host
   with gdb; D51 stack capture on CI with the existing faulthandler annotation; journey steps for D77; R-2 review.
2. **Owner decision:** P1–P19, in particular P8 (7.48), P10 (datum / CRS), P11 (kill sheet), P12 (method approvals,
   now including the `transition F r3` casing method), P13 / P14 / P16 (encryption, ACL, signing), P18 (tubular data).
3. **Licensed data:** API 5CT / 5C3 tubular tables, ISCWSA error models (P19), vendor catalogues – none shipped.
4. **Independent validation:** casing (incl. the D77 values against licensed tables), hydraulics, T&D, cement, MSE,
   kill sheet, by an engineer with an independent tool.
5. **Windows / field:** owner's Windows desktop run of the unsigned installer, real-DDR acceptance
   (`tests/test_ddr_acceptance.py`, opt-in), field acceptance (P17).

## D. Overall status

**PARTIAL.** Reasons: D74 cause 1, D51 and D63 OPEN; M242–M256 performed as evidence reviews only; real-DDR,
Windows and field acceptance not possible here; owner decisions open. What is complete is complete with the evidence
named above. **UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**
