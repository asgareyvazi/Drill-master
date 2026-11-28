# M461–M520: Integrated engineering delivery report

**PARTIAL — UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**

## Result: PARTIAL

The M460 open items U1, U2 and U3 are delivered for the stated synthetic scope. Engineering item E6b (the robust fit)
is delivered, and the Erge 2015 coefficients are marked NOT VERIFIED.

**Why the result is PARTIAL:**

1. **CI is not cleanly green.** The 3.13 leg of the Source gate hit the 60 min limit (D88) at `f7075a0` and on attempt 1
   at `46c471c`. TIMEOUT ≠ SUCCESS. A re-run of only the failed job at `46c471c` (attempt 2) passed in 42m48s, and no
   3.13-specific regression was found (`m494_python313_ci_investigation.md`). The timeouts are kept in the history and
   counted here.
2. **Missions blocked by missing validation sources:** M479 (open-ended surge) and M480–M481 (HB extensions).
3. **Owner decisions:** none of P1–P19 is approved.

The result "ACCEPTED FOR STATED SYNTHETIC SCOPE" is **not** claimed.

- **Branch:** `arena/72010272-drill-master`. `drill-Master` is untouched at `e3fa42a3257e981d9bdf9d012c97919e3352a53a`.
  Nothing was merged.
- **Start:** `e5610729f9f3370341a8cb2a6fb8b7b28ec523f5`, the M401–M460 closure, whose CI was green
  (`m461_live_baseline.md`).
- **Evidence:** `docs/mission-reports/m461-m520-evidence/`.
- **Scope of the evidence:** everything is synthetic, run as offscreen Qt on Linux plus GitHub-hosted runners. None of
  it is Windows desktop acceptance, real-DDR acceptance or field acceptance (P17 NOT RUN).
- **Mutation results** show that the listed tests detect the listed defects. They are not proof of correctness.
- **Unchanged historical records:** the M401–M460 report and the M460 catalogue and roadmap. M430–M459 remain
  **NOT DELIVERED**.

## 1. SHAs, CI, suite, mutation, benchmarks

| Item | Value |
|---|---|
| Commits | `3b4c297` (M461–M468) → `842c35c` (M469–M472) → `20c05d0` (M473–M474) → `f7075a0` (M475–M485) → `44d3fb4` (M486–M493 code and tests), → `46c471c` (this report and the M494–M503 documents) → `750e3cd` (R4b re-anchoring, Erge secondary-consistency test), followed by the commit that adds the 3.13 investigation and these report updates (documents only). Full SHAs: `m503_git_audit.md`. |
| CI `3b4c297`, `842c35c`, `20c05d0` | Every run was **cancelled**, superseded by the next push (concurrency group). The runs are kept. |
| CI `f7075a0` | Windows `45578429709` **SUCCESS** (31m12s). Source `45578429792` **TIMEOUT**: 3.11 SUCCESS and 3.12 SUCCESS (both about 55 min); 3.13 **TIMEOUT** ("exceeded the maximum execution time", 60 min; D88). Classified with `ci_run_states.py`. |
| CI `46c471c` | Windows `45588540716` **SUCCESS**. Source `45588540843` attempt 1: 3.11 SUCCESS (43m46s), 3.12 SUCCESS (57m13s, coverage), 3.13 **TIMEOUT** (cancelled at 60 min). Attempt 2 (`gh run rerun --failed`, 3.13 only): **SUCCESS** (42m48s); the run now reports `success` at attempt 2. Attempt 1 is kept and counted as a TIMEOUT. |
| Python 3.13 investigation (M494) | CI history shows 3.13 at 42–54 min before `f7075a0`. Local 3.13.18 sharded suite on the `750e3cd` tree: **6264 collected, 6260 passed, 0 failed, 4 skipped (NOT RUN)**, after re-running the one file whose 2 errors came from the diagnostic interpreter (missing stdlib `venv`). Summed test time 2701 s against 2608 s on 3.11; no file is pathologically slower. Result: intermittent, no code regression found (`m494_python313_ci_investigation.md`, `m494_full_suite_py313_46c471c_dirty.txt`). |
| CI on the pushed tip (after `46c471c`) | Not knowable inside this file. It is reported in the hand-over message. |
| Full local suite at `44d3fb4` | **6229 collected, 6225 passed, 0 failed, 0 error, 4 skipped. 8/8 shards OK; 2677 s** (`m494_full_suite_44d3fb4.txt`). The 4 skips stay **NOT RUN**: they need real DDR files, real MinerU or a real Windows bundle. After this run, `test_m473` gained two parametrised cases (the M361–M400 and M261–M290 anchors; run alone, it passes 6/6) and `test_m482` (33 tests) was added. The later 3.13 run below collects 6264. |
| Mutation M461–M520 | **55 mutants, 55 KILLED, 0 invalid, complete=True** (`m494_mutation_m461_m520_full.json`). Breakdown: EOWR 21, citation 14, robust drill-off 13, Erge 3, integration 4. |
| Historical U3 re-run | TR/AC/MV/CP/BP/WC: **39/39 KILLED** on current code (`m473_u3_historical_mutation_rerun.json`). |
| Historical M261–M290 re-run (R4b) | The 7 drifted IL-* / WB-* mutants re-anchored to current code: **7/7 KILLED**; all 89 anchors of `mutation_m261_m290.py` valid and pinned by `test_m473` (6 cases). Commit `750e3cd`. |
| Historical citation re-run | The CR-* / KA-* citation mutants in `mutation_m321_m360.py`: 15/15 KILLED with `--only` during Phase C. |
| Benchmarks | M468 EOWR (60 days): rendered = expected in every section. M478 robust drill-off: 9/9. M412: 30 cases inside tolerance, 6 status checks pass. M396: 31 cases. M349: pass. |
| Inventories and privacy | `dependency_audit`: lock 26, imports 185, 0 findings; catalogue **67 entries, 0 approved**. `engine_inventory` and `constant_inventory` pass `--check`. Privacy check: 0 findings. |
| Lock | `requirements-lock.txt` sha256 `697124eaf6dc00e18f5b41dac3481ff17450333d34d80794c5cd936e7edcfadd`, unchanged. PySide6 / shiboken6 stay at 6.8.1.1 and `core.qt_gc` is kept. |

## 2. Missions

| Mission | Delivered | Evidence | State |
|---|---|---|---|
| M461 | Live baseline | `m461_live_baseline.md` | done |
| M462–M463 | Canonical M461–M520 backlog with U1/U2/U3. The E6b/E8b labels were corrected in M475. | `m462_m463_canonical_backlog.md` | done |
| M464–M466 | **U1:** EOWR sections 12–17 rendered from source rows. Source ids, chronology, a period filter, units, "—" for missing values, NOT_RECORDED / NOT_RENDERED / QUERY_FAILED. Manifest v3; Excel sheets. | `core/eowr_sections.py`, `test_m464` (15), `test_m320d`, `m464_m468_eowr_sections.md` | IMPLEMENTED — PARTIALLY QUALIFIED |
| M467 | EOWR real MainWindow journey | `test_m467` (3) | done |
| M468 | EOWR mutants (21/21) and benchmark | `m468_*.json` | done |
| M469–M471 | **U2:** strict bounded citation reader with a published schema. A malformed entry is UNREADABLE and the others are still verified; IDENTITY_MISMATCH; PlainText status labels; Documents tab › "Open citation file…" → passage. | `core/citation_passage.py`, `test_m469` (30), `m469_m472_citation_passages.md` | IMPLEMENTED — PARTIALLY QUALIFIED (synthetic) |
| M472 | Citation real MainWindow journey, plus 14 mutants | `test_m472` (2) | done |
| M473–M474 | **U3:** M275/M276/M278/M279/M282/M283 families 39/39 KILLED; anchors pinned by a suite test. Addendum: 7 drifted IL/WB anchors outside U3 were re-anchored in M494 (R4b, 7/7 KILLED). | `m473_m474_u3_mutation_recovery.md`, `test_m473` (6) | done (mutation coverage) |
| M475–M478 | **E6b (robust part):** `m475.drilloff_robust` v1 (L1 hinge, exact vertex search, MAD flags), with a declared WOB basis that is never converted. Catalogue entry, replay, W13 dialog, benchmark, 13 mutants. M372 and M423 v1 are unchanged. | `core/drilloff_robust.py`, `test_m475` (20), `m475_m485_engineering.md`, `m478_benchmark_drilloff_robust.json` | IMPLEMENTED — PARTIALLY QUALIFIED (SCREENING) |
| M479 | E8b open-ended surge | blocker in `m475_m485_engineering.md` | **NOT IMPLEMENTED — BLOCKED (validation source)** |
| M480–M481 | E1b eccentricity, rotation, κ < 0.3 | blocker in `m475_m485_engineering.md` | **NOT IMPLEMENTED — BLOCKED (validation data)** |
| M482 | Erge 2015: primary paper not accessed. Numerically equal (rel. 1e-12) to an independent re-typing of the BoreTHM secondary reference at e = 0 inside the fitted range, pinned by `test_m482` (33 tests); outside 0.15 < n′ < 0.4 the engine refuses where BoreTHM clips. Reported **NOT VERIFIED** in every result, summary and case note; numbers and replay unchanged. | `UNVERIFIED_CRITERIA`, `test_m475::test_erge_*`, `test_m482_erge_secondary_consistency.py` | **NOT VERIFIED** (marked) |
| M483–M485 | Owner packages E1c (stays DISABLED), E11, E12. No behaviour change. | `docs/engineering/M483_M485_OWNER_PACKAGES_E1C_E11_E12.md` | DOCUMENTED ONLY |
| M486 | `BL-M408`: `test_m129` 20/20 repeats plus the full run | `m486_m493_reliability_integration.md` | OPEN (not reproduced) |
| M487 | D88 profile at `44d3fb4`. No workflow change; the 60 min timeout is kept. | `m487_suite_profile.md` | done (decision input) |
| M488–M490 | Catalogue ↔ replay consistency, well context, replay contract | `test_m488` (15) | done |
| M491 | **Security finding fixed:** the summaries of three calculation dialogs rendered typed text as rich text; they are now PlainText. Mutants killed. | `test_m488`, `m486_m493_reliability_integration.md` | done |
| M492 | E2E journeys (EOWR, citations, robust drill-off dialog) | full run | done |
| M493 | Windows gate, static review only. Windows CI `f7075a0` SUCCESS. | `m486_m493_reliability_integration.md` | done (not Windows acceptance) |
| M494 | Full sharded suite, full mutation run, benchmarks | §1 | done |
| M495–M500 | Audits: inventories, privacy, carried smoke checks (`workflow_m46` 24/24; `real_user_acceptance` and `well_package` call `generate(...)` with the new optional `period`) | §1 | done |
| M501 | M520 catalogue and roadmap; M196 M520 status | links below | done |
| M502 | This report and exact-SHA CI | §1 | **CI not cleanly green** (3.13 TIMEOUT at `f7075a0` and on attempt 1 at `46c471c`; attempt 2 SUCCESS) |
| M503 | Git audit | `m503_git_audit.md` | done |
| M504–M520 | Reserved. No work is claimed. | – | – |

## 3. Owner decisions

**No owner decision P1–P19 is approved.** `OWNER_APPROVALS` is empty and every catalogue row shows "NOT APPROVED —
OWNER REVIEW REQUIRED". The M520 status table is in `docs/engineering/M196_OWNER_DECISION_PACKAGES.md`.

| Decision | State |
|---|---|
| P2 | PySide6 pin 6.8.1.1 kept. |
| P3 | No LGPL code adopted. |
| P8 | Divisor kept. |
| P10 | No datum / CRS conversion. |
| P11 | Well control stays a TRAINING AID. |
| P12 / P18 | No ratings invented. |
| P13 / P16 / P17 | No encryption, signing or field-acceptance claim. |
| P19 | No ISCWSA separation-factor claim. |
| D88 | Active risk: 3.13 TIMEOUT at `f7075a0` and `46c471c` (attempt 1); 3.12 with coverage at 55–59 min. Timeout and workflow unchanged. |
| E1c, E11, E12 | Packages only. |

## 4. Capabilities that remain NOT IMPLEMENTED

| Capability | Gate |
|---|---|
| ISCWSA error models and separation factor | P19 |
| Stiff-string torque and drag | P3 |
| Wellbore temperature model | P3 |
| Casing triaxial envelope, connection ratings, casing buckling | P12, P18 |
| Gas-law kick migration (expansion, z-factor) | P11 |
| Lubricate-and-bleed and bullheading worksheets | P11 |
| Datum / CRS conversion | P10 |
| Bit wear / remaining-life prediction | data rights |
| Real-time WITSML ingestion | – |
| Encryption at rest | P13 |
| Transient surge / swab, and the open-ended string split (M479) | – |
| Eccentric-annulus HB, pipe rotation and κ < 0.3 (M480–M481) | – |
| Validated downhole drill-off: M475 accepts a declared downhole basis and derives nothing | data rights |
| Verification of the Erge 2015 coefficients against the primary paper | source access |

## 5. Links

- Capability catalogue: `docs/engineering/DRILLMASTER_COMPLETE_ENGINEERING_CAPABILITY_CATALOGUE_M520.md`
- Roadmap: `docs/engineering/DRILLMASTER_ENGINEERING_ROADMAP_M520.md`
- Owner packages: `docs/engineering/M196_OWNER_DECISION_PACKAGES.md` (M520 status) and
  `docs/engineering/M483_M485_OWNER_PACKAGES_E1C_E11_E12.md`
- Evidence: `docs/mission-reports/m461-m520-evidence/`
