# DrillMaster engineering roadmap after M520

**PARTIAL — UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**

- Written against the M461–M520 code.
- Supersedes `DRILLMASTER_ENGINEERING_ROADMAP_M460.md` for ordering. That file is kept unchanged as the M460 record.
- Capability states: `DRILLMASTER_COMPLETE_ENGINEERING_CAPABILITY_CATALOGUE_M520.md`.
- Evidence: `docs/mission-reports/M461_M520_INTEGRATED_ENGINEERING_DELIVERY_REPORT.md`.
- No item here approves an owner decision (P1–P19) or adopts external code or data.

## 0. What M461–M520 closed from the M460 roadmap

| M460 item | Outcome |
|---|---|
| U1 Render the EOWR NOT_RENDERED tables | **Done** (M464–M468). Sections 12–17 are rendered from source rows, with source ids, chronology, a period filter and explicit NOT_RECORDED / NOT_RENDERED / QUERY_FAILED. Manifest v3. A real MainWindow journey; benchmark M468. |
| U2 Open a `.citations.json` passage from the Documents tab | **Done for synthetic scope** (M469–M472). A strict bounded reader with a published schema; per-entry UNREADABLE / IDENTITY_MISMATCH; Library › "Open citation file…" → passage; a real MainWindow journey. |
| U3 Mutation-only items from M261–M290 | **Closed for mutation coverage** (M473–M474). TR/AC/MV/CP/BP/WC 39/39 killed on current code. Anchors are pinned by a suite test. |
| E6b Drill-off with downhole WOB / torque and a robust fit | **Robust fit done** as `m475.drilloff_robust` (L1), with a declared WOB basis that is never converted. **Downhole derivation and validation are still open** (E6c). |
| Erge 2015 gap | **Marked NOT VERIFIED** (M482). The transcription matches the BoreTHM secondary reference at e = 0; the primary paper was not accessed. The numbers are unchanged. |
| E1c / E11 / E12 | **Owner packages written** (M483–M485). No behaviour change. E1c stays DISABLED. |
| R3 `BL-M408` (`test_m129`) | Re-checked (M486): 20/20 repeats and the full sharded suite pass. Still not reproduced; closing it is the owner's call after N clean CI runs. |

## 1. Reliability

| # | Item | State after M520 | Exit criterion |
|---|---|---|---|
| R1 | PySide6 pin (D63, D74) | **BLOCKED BY OWNER DECISION.** The pin stays at 6.8.1.1. | Owner approval, then the M378 checklist. |
| R2 | D88: the 3.12 coverage leg runs against the 60 min limit | **Active risk; BLOCKED BY OWNER DECISION.** M487 refreshes the profile (`m487_suite_profile.md`). The workflow and the timeout are unchanged. | The owner records a CI design decision. |
| R3 | `BL-M408` | OPEN, not reproduced (M486). | N clean CI runs (owner). |
| R4 | Mutation catalogue | The M461–M520 tool holds 55 mutants (`mutation_m461_m520.py`). `test_m473_mutation_anchor_integrity` keeps the anchors of five tools (M261–M290, M321–M360, M361–M400, M401–M460, M461–M520) valid. | Keep a mutant for every new service. |
| R4b | Drifted historical anchors | **DONE (M494, `750e3cd`).** The 7 IL-* / WB-* mutants in `mutation_m261_m290.py` (M273, M286) were re-anchored to the current code and re-run: 7/7 KILLED. All 89 anchors are valid and pinned by `test_m473` (addendum 2 in `m473_m474_u3_mutation_recovery.md`). | None. |

## 2. Engineering (ordered)

| # | Item | Notes | Gate |
|---|---|---|---|
| E8b | Surge / swab: open-ended string flow split | M479 blocker: no primary-source validation available. M420 returns NOT ASSESSED for an open end. | validation source |
| E8c | Transient surge (inertia, compressibility) | Not started. | method + data |
| E6c | Validated downhole drill-off (derived or measured downhole WOB / torque) | M475 accepts a declared downhole basis only. | data rights |
| E1b | HB annulus: eccentricity, pipe rotation, exact annulus for κ < 0.3 | M480–M481 blocker. | validation data |
| E1c | HB parameter fit from Fann readings | Owner package M483. DISABLED. | P12 |
| E-ERGE | Verify the Erge 2015 coefficients against the paper | Needs access to SPE Drill. Complet. 30(3). | source access |
| E2 | ISCWSA error models and separation factor | Unchanged. | P19 |
| E3 | Stiff-string T&D | Unchanged. | P3 |
| E4 | Casing triaxial envelope, connection ratings, casing buckling | Unchanged. | P12, P18 |
| E5 | Well control TRAINING AID: lubricate-and-bleed, bullheading, gas-law migration | Unchanged. | P11 |
| E7 | Survey datum / CRS conversion | Refused, not converted. | P10 |
| E11 | `BL-SS-CONSOLIDATE` | Owner package M484. | owner / product |
| E12 | `BL-BIT-DEFAULTS` | Owner package M485. | owner |
| N-BIT-1 | Bit wear / remaining-life prediction | M427 is a record only. | data rights |
| N-TEMP | Wellbore temperature model | pwptemp is LGPL. | P3 |
| N-WITSML | Real-time ingestion | Out of scope so far. | – |

## 3. Product

| # | Item | Notes |
|---|---|---|
| U4 | Citation record v2 with a document content hash | U2 checks identity by file name only. |
| U5 | EOWR: cross-section consistency (for example, bit footage against time-log hours) | Not started. It must stay source-only, with nothing inferred. |

## 4. Data, standards, licences, security, acceptance

P8, P10, P11, P12, P18 and P19 are covered in `M196_OWNER_DECISION_PACKAGES.md`, which now has an M520 status table.
P13–P17 are unchanged: there is no encryption, signing or field-acceptance claim.

Real DDR acceptance, Windows desktop acceptance and field acceptance: **NOT RUN**. Linux offscreen runs are not
Windows acceptance.
