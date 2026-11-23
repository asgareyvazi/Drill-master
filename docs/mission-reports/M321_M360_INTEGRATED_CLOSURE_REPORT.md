# M321–M360: integrated closure report (M360)

**Branch:** `arena/72010272-drill-master`. Start `6754e14` (M291–M320 delivery).
**Status: PARTIAL — UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**
All test and benchmark data is SYNTHETIC. `requirements-lock.txt` still pins **PySide6 6.8.1.1**. The upgrade is an open owner decision.

Evidence folder: `docs/mission-reports/m321-m360-evidence/`.

## 1. Commits

| Commit | Content |
|---|---|
| `bc8e15b` | M321 baseline, M322 audit, M323 residual repairs, M328 History replay, M331 yield-unit registry |
| `b7d16db` | M323 defect register and status-vocabulary corrections |
| `e70ae78`, `55b7340` | M324 PySide6 decision package and isolated CI evaluation workflow |
| `0aa0be7` | M326 real-MainWindow lifecycle tests (D74 retain policy); M327 catalogue |
| `1d391fd` | M329 architecture-diff table and export; D90 |
| `b18706d` | M327 survivor-kill tests (21); D91; M324 diagnostics; M328 evidence |
| `3293c3d` | M333 report manifests (A-7); M334 citation-record navigation (A-8); M352 pre-push guard (A-9) |
| `67ea1e2` | M324 CI evaluation evidence; probe hang detection; rehearsed M325 lock edit (runner only) |
| `aff8344` | **M349 benchmarks; D92 T&D integration fix** |
| `2646543` | M327: 22 new mutants run, 3 survivors killed |
| `56d3542` | M324 run 45115378469 evidence; hang instrumentation |
| `6ace038` | engine inventory regenerated (D92 method name); double stack dump; M324 hang diagnosis; M329/M352 notes; this report |
| `534e4f3` | complete M327 mutation run (121 mutants) recorded; paired-dump results (`m324_ci_evaluation.md` §3c); D51 register row; CI results |

## 2. Missions

| Mission | Result | Status | Evidence |
|---|---|---|---|
| M321 | Live baseline and non-destructive recovery after the 9th sandbox reset; local tree proven identical to `6754e14` | DONE | `m321_live_baseline.md` |
| M322 | Independent audit of M291–M320: A-1…A-9 | DONE | `m322_independent_audit.md` |
| M323 | Residual repairs D89, A-1, A-3, A-4, A-4b, A-5, A-6; defect register; corrected status vocabulary | DONE | `m323_defect_register.md` |
| M324 | PySide6 6.8.1.1 vs 6.8.2.1 vs 6.8.3. A public 6.8.5 does not exist. Isolated CI evaluation; fix proven in source (`PySideSignalInstanceShared`) | DONE, **decision with owner** | `m324_pyside_upgrade_decision.md`, `m324_ci_evaluation.md` |
| M325 | Raise the pin | **NOT EXECUTED: needs owner approval** | — |
| M326 | D63 / D74 lifecycle with real MainWindows | D63 BLOCKED BY OWNER DECISION; D74 PARTIALLY QUALIFIED | `m326_d63_d74_lifecycle.md` |
| M327 | Mutation catalogue, 121 mutants. One complete run on `6ace038`: 119 killed, 0 survived, 2 declared equivalent, 0 invalid | DONE | `m327_mutation_catalogue.md` |
| M328 | History replay for M314 / M317 / M318 cases | DONE | `m328_history_replay.md` |
| M329 | Architecture diff as a table and a CSV export with both revision SHA-256s; D90 | DONE | `m329_m352_evidence.md` |
| M331 | Cement yield-unit registry (ft3/sk, gal/sk, bbl/sk, L/sk) | DONE | `m323_defect_register.md`, tests |
| M333 | Section manifests for NPT, Cost and Plan reports (A-7) | DONE | register row A-7 |
| M334 | Navigation from a verified citation record to its passage (A-8) | DONE | register row A-8 |
| M349 | Independent engineering benchmarks: 44 cases, 0 outside tolerance; **found D92** | DONE | `m349_benchmarks.md` |
| M352 | Large-font pre-push guard (A-9, roadmap R6) | DONE (ratchet; opt-in hook) | `m329_m352_evidence.md` |
| M360 | This report | DONE | — |

Other mission numbers in M321–M360 have no separate deliverable in this branch, and none of them is claimed as done.

## 3. Defects found and fixed in this block

| ID | Severity | Summary | Fix |
|---|---|---|---|
| D89 | high | New Cement / Casing forms saved widget placeholders (yield 1.18, TOC 0, …) as recorded data | `bc8e15b` |
| D90 | low | A changed reference binding was shown as "unknown → unknown" | `1d391fd` |
| D91 | low (test tool) | Windows ANSI stdout made `ux_startup_m115.py` raise `UnicodeEncodeError` | `b18706d` |
| **D92** | **high** | The T&D engine integrated each drill-string entry as ONE element. One 3,048 m pipe entry through a build-and-turn well read slack-off +18.5 % and torque −19.6 %, and the answer depended on how the pipe was entered. Now ≤ 5 m segments (benchmark error ≤ 0.085 %). Saved legacy runs and M318 v1 cases recompute with the legacy method and are never relabelled. | `aff8344` |
| A-1…A-9 | low–medium | Audit findings (register) | `bc8e15b`, `3293c3d` |

**D51 (re-opened, then explained):** in the M324 evaluation on Linux / Python 3.13 the candidates hung intermittently with the recorded D51 frame (`AxisItem._updateLabel`). A GIL heartbeat (0 lines in 300 s) and native gdb stacks of every hung probe identified the deadlock M50 already fixed: cyclic GC on the dashboard worker thread destroyed a freed window's Qt objects. There `~QObject` held Qt's connection mutex and waited for the GIL, while the main thread held the GIL in Shiboken's `runDeletionInMainThread` and waited for that mutex. The probe builds `MainWindow` directly and had not installed `core.qt_gc`, which `app.py` installs. With the application's GC policy, run `45144294084` had **0 hangs in 32** candidate runs on Python 3.13, against **5 of 16** without it (p ≈ 0.003). So it is not a product or candidate defect and no longer blocks Python 3.13. The single M266 event is not proven to be the same and stays under the M309 monitor. An earlier "reload cycle" reading compared dumps from two different runs and is withdrawn (`m324_ci_evaluation.md` §3c).

## 4. Qualification labels

The label QUALIFIED requires the M327 mutation evidence and, where a numeric result exists, the M349 benchmarks.

| Capability | Label | Basis |
|---|---|---|
| M311 / M329 architecture comparison | **QUALIFIED ON SYNTHETIC DATA** | behaviour tests; all AD-* mutants killed; a numeric benchmark does not apply |
| M314 DDR bit-hydraulics check | **SCREENING — QUALIFIED ON SYNTHETIC DATA** | 15 benchmark cases (Bourgoyne); HC-* mutants killed; replay |
| M317 cement reconciliation | **WORKSHEET — QUALIFIED ON SYNTHETIC DATA** | 5 benchmark cases (exact geometry); CJ-* mutants killed; displacement remains an upper-bound check |
| M318 T&D sensitivity (v2) | **SCREENING — QUALIFIED ON SYNTHETIC DATA** | 24 benchmark cases after D92; TD-* and TDS-* mutants killed; soft-string limits unchanged |
| M320 D / M333 report manifests | IMPLEMENTED — QUALIFIED ON SYNTHETIC DATA | RS-* mutants killed |
| M320 E / M334 citation records | IMPLEMENTED — QUALIFIED ON SYNTHETIC DATA | CR-* and KA-* mutants killed |
| M352 guard | IMPLEMENTED | a ratchet: detects widening on Linux fonts; it does not prove the Windows width |
| D63 / D74 | BLOCKED BY OWNER DECISION / PARTIALLY QUALIFIED | M324 / M326 |

**Limits of these labels:**
- "Qualified on synthetic data" is not field acceptance.
- The mutation result comes from one complete run of all 121 mutants on `6ace038` (`complete=True`). It shows that the tests detect these specific seeded defects; it is not a proof of correctness.

## 5. Owner decisions still open

1. **PySide6 pin (M325).**
   - Recommendation: 6.8.3, with 6.8.2.1 as the alternative.
   - On the shipped runtime (Windows, Python 3.12) both candidates pass the probe, the UI subset, the PyInstaller build and the launched frozen exe.
   - Keep `core.qt_gc` installed on every path that builds windows: on the candidates closed windows are always freed (`m324_ci_evaluation.md` §3f).
2. The prior items (P11 Kill Sheet R-2, the 60-minute CI limit and others) are unchanged.

## 6. Quality gates

| Gate | Result |
|---|---|
| Full suite, local, Python 3.11.2, offscreen, `aff8344` tree | 5,954 tests: 5,949 passed, 4 skipped (opt-in), **1 failed** (`test_m75_engine_inventory`: `ENGINE_INVENTORY.md` was stale after the D92 method rename). Fixed in `6ace038` by `engine_inventory.py --write`; the m75, m112, m137, release-boundary and registry tests now pass (43 tests). |
| Tests added after that run | `test_m320d` (+1) and `test_m349` (+1): 26 pass. `test_m334`: 6 pass. |
| ruff (`core dialogs tabs tests` and the new tools) | clean |
| Exception scan | silent-unexplained 83 / ceiling 83 (not raised) |
| Privacy check | 1,808 files, 0 findings |
| `dependency_audit` / `constant_inventory` / `engine_inventory` | regenerated with `--write`; `--check` passes |
| M349 benchmark `--check` | 44 / 44 within tolerance |
| CI Windows release validation, `56d3542` | ✅ success |
| CI Source release gate, `56d3542` | cancelled by the push of `6ace038` |
| CI Windows release validation, `6ace038` (`45122896026`) | ✅ success |
| CI Source release gate, `6ace038` (`45122895968`) | 3.11 ✅, 3.13 ✅ (full suite incl. `test_m75`); 3.12 stopped by GitHub's 60-minute job limit with no test failure annotated (the known CI-duration residual) |
| CI PySide6 candidate evaluation, `6ace038` (`45122895952`) | Windows ×3 ✅, Linux 3.11/3.12 ×4 ✅, 3.13 × 6.8.1.1 baseline ✅; 3.13 × 6.8.3 ❌ (6/10 HANG), 3.13 × 6.8.2.1 ❌ (1/10 HANG). Expected: this is the D51 evidence, not a release gate |
| CI Windows release validation, `534e4f3` (`45130003013`) | ✅ success |
| CI Source release gate, `534e4f3` (`45130003098`) | ✅ success (3.11, 3.12, 3.13) |
| CI PySide6 candidate evaluation, `534e4f3` | not triggered (documentation-only change); the last run is `45122895952` above |
| CI PySide6 candidate evaluation, `246e7bf` (`45144294084`) | ✅ **all 10 jobs**. Python 3.13 with `core.qt_gc`: 0 / 32 candidate runs hung (6.8.3 0/16, 6.8.2.1 0/16), baseline 0/8; diagnostic control without it: 5 / 16 |
| CI Source release gate, `246e7bf` (`45144294022`) | ✅ success (3.11, 3.12, 3.13) |
| CI Windows release validation, `246e7bf` (`45144294116`) | ✅ success |
| `067aa44` | CI table only |
| `82d1fff` | corrected paired-dump reading (GIL starvation, not a reload cycle); probe `--heartbeat` and compact hang report; `tests/test_m324_hang_report.py` |
| `29620f4` | heartbeat result (§3d); `probe_loop --native-dump` (gdb) and `mode=retain` on 3.13 candidates |
| `90192f5` | full native stacks of the two blocked threads; `mode=collect` leg |
| `246e7bf` | root cause (§3e); probe `--qt-gc` as `app.py`; product-faithful 3.13 legs plus a diagnostic control; 7 tests in `test_m324_hang_report.py` |
| this commit | §3f confirmation (run `45144294084`, all 10 jobs ✅); register D51 row; decision record; CI results |
