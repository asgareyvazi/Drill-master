# M401–M460 — Integrated engineering delivery report

**PARTIAL — UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**

- Branch `arena/72010272-drill-master`. `drill-Master` is untouched at `e3fa42a3257e981d9bdf9d012c97919e3352a53a`.
- Mission baseline: `e9244e80364641315d1da31e62e055b9548d57dd`, with its tree identical to `41ea53e` (`m401_live_baseline.md`).
- Evidence: `docs/mission-reports/m401-m460-evidence/`.
- Everything below is synthetic: offscreen Qt on Linux and GitHub-hosted runners.
- Mutation results show that the listed tests detect the listed defects. They are not proof of correctness.
- **Scope honesty.** The M401–M460 directive text is not stored in the repository. Missions without a recorded deliverable are listed in §2.3 as NOT DELIVERED. They are not reported as done.

## 1. SHAs, CI, local suite, mutation, benchmarks

| Item | Value |
|---|---|
| Product SHA | `1c5d0f7c023adbae10edc09055dee357ac406441`: all M401–M460 code, tests, tools and documents except this report and the M409 profile. |
| CI on `1c5d0f7` | **FAILURE — not green.** Windows `45384695338` SUCCESS (33m37s). Source `45384695412`: 3.11 SUCCESS (42m00s); 3.12 **FAILURE**, 1 test: `test_m412_benchmark_table_is_reproduced_exactly` (collected 6140, passed 6135, failed 1). The stored M412 table printed relative errors at floating-point-noise level (`%.2e` of ~1e-16), and those digits differ between the 3.11 and 3.12 builds. All 30 cases were inside tolerance. 3.13 **TIMEOUT** at the 60 min limit (D88). **Fix:** `benchmark_m412.py` now stores errors below min(1e-9, tolerance) as that bound; the PASS / FAIL decision still uses the exact value. The fix is in the next commit, whose CI is reported in the hand-over. |
| Local full suite on `1c5d0f7` | **6140 collected, 6136 passed, 0 failed, 0 error, 4 skipped, 8/8 shards OK, exit 0**. Run with `tools/quality/run_suite_sharded.py --shards 8` and `/home/user/.venv/bin/python` 3.11.2; 3026 s; output in `m401_suite_1c5d0f7.txt`. These are pytest's own per-test outcomes (M407 recorder), not exit codes. The 4 skips need real data or a Windows bundle (real DDR Excel/PDF, real MinerU, real Windows bundle smoke). |
| Targeted regression (before the commit) | 882/882 passed in 3 shards (`m401_targeted_regression.txt`). |
| Mutation M401–M460 | **Run 2: 30 mutants, 30 KILLED, complete** (`m401_m460_mutation_run2.txt` / `.json`). Run 1: 27/30; survivors SS-partial-sum-total, DG-trend-unordered and DLG-empty-is-zero, each then killed by a new assertion (`m401_m460_mutation_run1.*`). |
| M411 audit re-execution | M401–M460 30/30 and M361–M400 53/53 killed. First killing test recorded per mutant (`m411_mutant_audit.md`). |
| Benchmarks | M412: 30 independent cases inside tolerance and 6 status checks PASS (`m412_benchmarks.txt`; errors below min(1e-9, tolerance) are stored as that bound so the table is the same on every build). M396: 31 cases, unchanged, PASS. |
| Privacy check | 0 findings (1906 files). |
| Inventories | `engine_inventory`, `dependency_audit` (66 catalogue entries, 0 approved) and `constant_inventory` all pass `--check`. The M403 ledger passes `--check`. |

### 1.1 CI result for the product SHA

See the hand-over message for the final 3.12 / 3.13 states of Source run `45384695412`. A file cannot be updated after its own commit without creating a new SHA. A TIMEOUT is reported as TIMEOUT (D88) and never as green.

## 2. Missions

### 2.1 Phase A — audit and reliability

| Mission | Delivered | Evidence | State |
|---|---|---|---|
| M401 | Live repository baseline: SHAs, remote, protection (403 = NOT CHECKED), rulesets `[]`, tree identity `41ea53e` = `e9244e8`, CI on `e9244e8` with every attempt (3.12 attempt 1 TIMEOUT retained). | `m401_live_baseline.md` | done |
| M402 | Independent audit of the M361–M400 claims, re-derived from `git archive e9244e8`: 62 catalogue entries, 53 mutants, 35 journey steps, 48 catalogue rows, inventories current. | `m402_m400_independent_audit.md` | done |
| M403 | M1–M400 traceability ledger, generated. Directives are UNAVAILABLE IN REPOSITORY, and the ledger never invents them. Result: 202 missions have no named artefact (a gap marker, not a state). 182 are PARTIALLY QUALIFIED, from a strict label or named tests only. | `docs/engineering/M403_TRACEABILITY_LEDGER_M1_M400.md`, `tools/quality/traceability_ledger_m403.py`, `tests/test_m403_m411_ledger_and_mutant_audit.py` | done (DOCUMENTED ONLY) |
| M404 | Reconciliation addendum with 16 rows. Historical files are unchanged. Main corrections: CCI value and class were stored since `70fa14b`, and only provenance was missing; M376 did not cover M372/M373; D88 is an active risk; AC2 is not D94 evidence; the P10 wording; `BL-BIT-DEFAULTS`. | `m404_reconciliation_addendum.md` | done |
| M407 | Sharded runner: each shard is judged on pytest's own outcomes (recorder plugin), never on exit codes alone. This fixes a defect: the old runner's regex never matched, so it recorded no counts. | `run_suite_sharded.py`, `pytest_outcome_recorder.py`, `tests/test_m407_sharded_runner_counts.py` | done |
| M408 | `test_m129` intermittent failure: **not reproduced**. Loaded runs gave 396/396 twice, the spy found no discards, and 20/20 repeated runs passed. The test now has staged assertions so the next failure names its stage. | `m408_test_m129_investigation.md` | **OPEN** (`BL-M408`) |
| M409 | Per-test durations recorded and a suite profile written (D88 decision input). The top file takes 3.6 % of the time and the top 10 files take 22.4 %. A file-level two- or three-way split balances to within 0.1 %. | `m409_suite_profile.md`, `m409_file_durations_1c5d0f7.json`, `suite_profile_m409.py` | done; the decision is **BLOCKED BY OWNER DECISION** |
| M411 | Mutant audit: the mutated symbol and the first killing test for each mutant. Finding: "first" means first in file order, not the only killer, so the table is a lower bound on specificity. | `m411_mutant_audit.md`, `m411_audit_*.md/.json`, `mutant_audit_m411.py` | done |
| M412 | Independent benchmarks: R1–R8, SS1–2, DF1–2, D94-1/2, F1–F5, B1–B5, Z, U, plus status checks S1–S6. | `benchmark_m412.py`, `m412_benchmarks.txt` | done |

### 2.2 Phase B / C — engineering services

Every service follows the same chain: UI → service → validation → calculation case (inputs SHA-256) → replay (`core/history_replay.SERVICE_MODULES`) → method catalogue. Missing inputs are reported as NOT ASSESSED, and zero is treated as a value. Every service has a W13 dialog test from the real tab and is covered by mutants.

| Mission | Delivered | UI entry | Label |
|---|---|---|---|
| M415 / M416 / M417 / M418 | **R-HYD-2.** Herschel-Bulkley narrow-slot annulus with three regimes: exact laminar; transition bands (Founargiotakis 2008 or Erge 2015, declared); turbulent with Colebrook. Restricted to κ ≥ 0.3. Spec, service, benchmarks R1–R8 and dialog. | W13 hydraulics › "🧮 HB Annulus (R-HYD-2)" | SCREENING |
| M419 / M420 / M421 | **Surge / swab.** Quasi-steady, closed-end string: Burkhardt model with a declared K_c, applied to the R-HYD-2 slot; EMW from 12/231 psi/ft per ppg. | W13 hydraulics › "📉 Surge/Swab HB (closed-end)" | SCREENING |
| M422 | **CCI provenance.** `M366 v2` stores the CCI inputs as case fields. `M366 v1` cases still replay. | W13 › "Budget & sensitivity…" | SCREENING |
| M423 / M424 | **Fitted drill-off.** Continuous hinge fitted by least squares, with leave-one-out outlier flags. M372 is unchanged. | W13 bit page › "📐 Drill-off fitted line…" | SCREENING |
| M427 | **IADC dull grade.** Record, validation and per-well trend. No prediction. | W13 bit page › "🦷 Bit dull grade (IADC)…" | RECORD |
| (M376 extension) | Qt lifecycle: the M372 and M373 dialogs and the four new dialogs are parented to the W13 tab and destroyed with it. | – | test |
| Catalogue | +4 calculation-case services: 66 entries, 0 approved. | Help › Method catalogue | – |

Defects found and fixed during M401–M460:
- The M407 runner recorded no counts.
- The dull grade crashed on None inputs.
- The dialog raised a `_dg` NameError: class-body names are not visible in comprehensions.
- Drill-off pooled-s flagging could never trigger for n ≤ 12; it was replaced by leave-one-out.
- The M411 audit parser truncated parametrised ids that contain spaces.

### 2.3 Not delivered in this branch

| Missions | State | Reason |
|---|---|---|
| M405, M406, M410, M413, M414, M425, M426, M428, M429 | **NOT DELIVERED as separate missions** | The directive text for these numbers is not recorded in the repository or the working notes, so none is claimed. Related deliverables exist: benchmark groups D94, F and B in `benchmark_m412.py`, whose header names M425/M426/M429, and the M376 lifecycle extension. They are counted under M412 and §2.2, not under these numbers. |
| M430–M459 (Phases D–G) | **NOT STARTED** | Not reached in this delivery. The open product items U1 (EOWR NOT_RENDERED tables) and U2 (citation passage from the Documents tab) remain on the roadmap. |

## 3. Documents

- Catalogue: `docs/engineering/DRILLMASTER_COMPLETE_ENGINEERING_CAPABILITY_CATALOGUE_M460.md`.
  - 52 domains: rows 49–52 are new, and rows 2, 13–16, 28, 29, 33 and 48 are updated.
  - Row 16 is corrected.
  - The planned list is updated: N-3 and N-6 are now partly implemented.
- Roadmap: `docs/engineering/DRILLMASTER_ENGINEERING_ROADMAP_M460.md`. Closed: E1, E6, E8, E9, E10. New: E1b, E1c, E6b, E8b, E11, E12, N-BIT-1.
- Specs:
  - `R_HYD_2_HB_SLOT_METHOD_SPECIFICATION.md`
  - `SURGE_SWAB_METHOD_SPECIFICATION.md`
  - `DRILLOFF_FITTED_LINE_METHOD_SPECIFICATION.md`
  - `BIT_DULL_GRADE_RECORD_NOTE_M427.md`
- M401–M460 sections added to:
  - `M241_CAPABILITY_INVENTORY.md`
  - `PRODUCT_CAPABILITY_MATRIX.md`
  - `ENGINEERING_METHODS_AND_LIMITATIONS.md`
  - `M196_OWNER_DECISION_PACKAGES.md` (M460 status table)
  - `ENGINE_INVENTORY.md` (generated)
- The M400 catalogue, the M400 roadmap and the M361–M400 report are unchanged. Corrections to them are in the M404 addendum.

## 4. Owner-gated (BLOCKED BY OWNER DECISION — nothing approved)

`OWNER_APPROVALS` is empty. The gated items are:
- P2: the PySide pin stays at 6.8.1.1.
- **D88**: an active TIMEOUT risk. M409 provides the input for the decision. The limit has not been raised and the workflow has not been split.
- P8: the density divisor is kept. M420 uses the exact 12/231.
- P10: datum / CRS.
- P11: kill sheet.
- P12 / P18: casing methods and tubular data.
- P19: ISCWSA.
- P3: LGPL dependencies.

Backlog items needing an owner or product decision: `BL-SS-CONSOLIDATE`, `BL-BIT-DEFAULTS`, `BL-M408`.

## 5. Disclosures and limitations

- **M416**
  - Concentric slot only, with κ ≥ 0.3. At κ = 0.3 the slot under-predicts by 2.25 % against the exact annulus. Eccentricity, rotation, tool joints, cuttings and temperature are not modelled.
  - τ0, K and n are declared, never fitted.
  - Colebrook evaluated at Re_G is a stated approximation.
  - **The Erge 2015 transition-band equations were taken from the BoreTHM (Apache-2.0) docstring citation and were not re-checked against the paper.** This is a stated verification gap. The Founargiotakis 2008 band is the alternative.
  - BoreTHM is a method reference only; no code was copied.
- **M420**
  - Quasi-steady only: no inertia, compressibility or pressure waves.
  - The open-ended string is NOT IMPLEMENTED (NOT ASSESSED).
  - K_c is declared. K_c = 0.5 is exact only for a Newtonian laminar slot.
  - The legacy W13 surge dialog (fixed 0.45 clinging factor) is unchanged and separate (`BL-SS-CONSOLIDATE`).
- **Legacy W13 hydraulics.** Its HB option remains a power-law plus yield-stress screening approximation, and it carries its own warning. M416 does not replace it, and no default was changed.
- **M423.** Least squares is not robust. A +40 ft/h outlier at W 16 (break at 26) moves the fitted break to 16.0 and flags nothing; this is tested and documented. Surface WOB only.
- **M427.** Record only. No wear or remaining-life prediction, and no inference from DDR rows.
- **M403.** The ledger's states come from strict labels or named tests. The directive text of M1–M400 is not in the repository.
- **M408.** `test_m129` stays OPEN. The spy did not observe same-id generation bumps (hypothesis H1 gap).
- **Local suite.** One pytest process exceeds the 4 GB sandbox, so the suite runs as 8 sequential shards. Order-dependent tests (D53) may behave differently across shard boundaries. CI keeps the single-process run.
- **D88.** The 3.12 CI leg runs 55–60 min against a 60 min limit. `e9244e8` attempt 1 on 3.12 was a TIMEOUT, and on `1c5d0f7` the **3.13** leg also hit the limit, so the risk now covers more than one leg. M409 is local timing without coverage, so only its relative shares transfer to CI.

## 6. Delivery audit

| Check | Result |
|---|---|
| Only branch written: `arena/72010272-drill-master`. Fast-forward pushes only. Remote SHA verified with `git ls-remote`. | PASS |
| `drill-Master` unchanged (`e3fa42a`) | PASS |
| No `reset --hard`, `clean -fd`, force-push, history rewrite or branch deletion | PASS |
| PySide6 pins unchanged; no dependency change | PASS |
| No owner decision marked approved; 66 catalogue entries all NOT APPROVED | PASS |
| P8 untouched; kill sheet stays TRAINING AID; ISCWSA / SF not claimed | PASS |
| No LGPL code, no copied code, no datasets, no proprietary ratings | PASS |
| Historical reports intact; corrections made as addenda | PASS |
| No COMPLETE label; synthetic results are not presented as field acceptance | PASS |
| Missions without a recorded deliverable reported as NOT DELIVERED | PASS (§2.3) |
| Real DDR, Windows desktop and field acceptance | NOT RUN |
