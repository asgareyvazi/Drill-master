# DrillMaster engineering roadmap after M460

**PARTIAL — UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**

- Written against the M401–M460 code.
- Supersedes `DRILLMASTER_ENGINEERING_ROADMAP_M400.md` for ordering. That file is kept unchanged as the M400 record.
- Capability states: `DRILLMASTER_COMPLETE_ENGINEERING_CAPABILITY_CATALOGUE_M460.md`.
- Evidence: `docs/mission-reports/M401_M460_INTEGRATED_ENGINEERING_DELIVERY_REPORT.md`.
- No item here approves an owner decision (P1–P19) or adopts external code or data.

## 0. What M401–M460 closed from the M400 roadmap

| M400 item | Outcome |
|---|---|
| E1 R-HYD-2 | **Implemented** as a separate method: `m416.hb_slot_annulus`. Comes with a spec, benchmarks R1–R8 and mutants HB-*. The existing W13 Bingham / power-law / HB-approximation branches are unchanged, and no default has changed. |
| E6 drill-off fitted line | **Implemented** as `m423.drilloff_fitted`, next to M372. Downhole WOB and torque are still open (E6b). |
| E8 surge and swab | **Implemented** for the quasi-steady closed-end case (`m420.surge_swab`). The open-ended string and transient surge are still open (E8b). |
| E9 fishing and bit benchmarks | **Done** in `benchmark_m412.py` (groups F1–F5 and B1–B5). |
| E10 CCI outside the summary lines | **Done** in `M366 v2` (M422). This also corrects the M400 statement that CCI appeared in the summary lines only. |
| R4 local full-suite memory | The runner now records exact pytest outcomes (M407) and per-test durations (M409). |

## 1. Reliability

| # | Item | State after M460 | Exit criterion |
|---|---|---|---|
| R1 | PySide6 pin (D63, D74) | **BLOCKED BY OWNER DECISION.** The pin stays at 6.8.1.1. M378 recommends 6.8.3. | Owner approval, then the M378 checklist. |
| R2 | D88: the 3.12 coverage leg runs against the 60 min limit | **Active risk; BLOCKED BY OWNER DECISION.** On `e9244e8`, attempt 1 of the 3.12 leg was a TIMEOUT and the re-run passed in 56m19s. `m409_suite_profile.md` gives per-file shares and a balanced split. | The owner records a CI design decision (split, shard, or accept the risk). The limit is never changed silently. |
| R3 | `BL-M408`: `test_m129` intermittent failure | **OPEN, not reproduced.** Loaded runs passed 396/396 twice and 20/20 repeats. `test_m129` now has staged assertions. | Reproduce with the staged asserts, or close after N clean CI runs (owner). |
| R4 | M401–M460 mutation catalogue | 30/30 killed (run 2). The M411 audit names the first killing test of each mutant. | Keep a mutant for every new service. |

## 2. Engineering

| # | Item | Notes | Gate |
|---|---|---|---|
| E1b | HB annulus: eccentricity, pipe rotation, exact annulus for κ < 0.3 | M416 refuses κ < 0.3 today. | – |
| E1c | HB parameter fit from Fann readings (τ0, K, n) | `core/mud_engineering.py` reports the HB fit as NOT ASSESSED, and M416 takes declared values only. | P12 (method approval) |
| E2 | ISCWSA error models and separation factor | Unchanged. M412 D94 benchmarks the centreline geometry only. | P19 |
| E3 | Stiff-string T&D | Unchanged. | P3 |
| E4 | Casing triaxial envelope, connection ratings, casing buckling | Unchanged. | P12, P18 |
| E5 | Well control TRAINING AID: lubricate-and-bleed, bullheading, gas-law migration | Unchanged. | P11 |
| E6b | Drill-off with downhole WOB / torque and a robust fit | M423 documents its non-robustness. | – |
| E7 | Survey datum / azimuth conversion | P10 rule restated in the M404 addendum. | P10 |
| E8b | Surge / swab: open-ended string flow split, transient surge | M420 returns NOT ASSESSED for an open-ended string. | – |
| E11 | `BL-SS-CONSOLIDATE`: one surge method in the UI | The legacy W13 surge (fixed 0.45 clinging factor) and M420 coexist. | Owner / product decision |
| E12 | `BL-BIT-DEFAULTS` | The dc normal gradient default is 8.6 ppg. Cost per foot without rotating hours is trip-only. Decide whether either should require explicit input. | Owner |
| N-BIT-1 | Bit wear / remaining-life prediction | M427 is a record only. A predictor needs a validated dataset with data rights. | Data rights |

## 3. Product

| # | Item | Notes |
|---|---|---|
| U1 | Render the EOWR NOT_RENDERED tables | Carried over (M320 P2, M400 U1). |
| U2 | Open a `.citations.json` passage from the Documents tab | Carried over (M320 P3, M400 U2). |
| U3 | Mutation-only items from M261–M290 | Carried over. |

## 4. Data, standards, licences, security, acceptance

P8 (density divisor kept), P10, P11, P12, P18 and P19 are covered in `M196_OWNER_DECISION_PACKAGES.md`, which has an M460 status table. P13–P17 are unchanged.

Real DDR acceptance, Windows desktop acceptance and field acceptance: **NOT RUN**.
