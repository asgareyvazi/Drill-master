# M292 – independent audit of M261–M290 and authoritative residual register

**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**

## Method

* Read in full: the M261–M290 report (including the new M293 addendum), `PRODUCT_CAPABILITY_MATRIX.md`, `M241_CAPABILITY_INVENTORY.md` (M290 catalogue) and `M196_OWNER_DECISION_PACKAGES.md`.
* Re-checked against the tree at `b6a6a33` (product source = `07a0f8b`) and the CI API.
* Claims that depend on code paths were re-read in the code. M295 and M300 found two gaps that the M261–M290 report did not state (M272-G1 and M273-G1 below).

Classes: RESOLVED · PARTIALLY RESOLVED · OPEN · NOT REPRODUCED · REPRODUCED — ROOT CAUSE UNKNOWN · OWNER DECISION REQUIRED · LICENSE / DATA RIGHTS BLOCKED · INDEPENDENT VALIDATION REQUIRED · NOT STARTED.

## Implementation claims of M261–M290

| ID | Claim | Re-check | Class at the start of M291 |
|---|---|---|---|
| M272 | value states for the 11 numeric DDR header fields, W2 editor, data quality | Present at `07a0f8b`. **M272-G1 (new):** `parse_authored` had no production caller. **Update M295/M296/M297:** the W2 value-states dialog has a typed column that goes through `parse_authored` and `record_authored` (`ae016a7`); the Excel and supported-PDF imports record value states in the import transaction (`core/ddr_import_value_states.py`). The W2 header spin boxes themselves are unchanged (they cannot hold a comma). Partial-success semantics kept and made explicit (M299). | RESOLVED |
| M273 | review-item lineage, stored-now check | Present. **M273-G1 (new):** an ACCEPTED item without a correction was always NOT_CHECKED; imported values without a review item had no lineage. **Update M300/M301/M302:** accepted items are checked against the latest correction, else the persisted acceptance snapshot, else the normalized value when no conversion is declared, else NOT_CHECKED with a reason; non-accepted items are NOT_APPLICABLE; imported values have a stable `iv:` identity and read-only lineage without review items; a read-only lineage dialog is reachable from W2 and the review queue. | RESOLVED |
| M286 | clone / archive / restore | Present for every history kind through `_source_row`. Tests exercise one casing record and one calculation case. No bulk operation and no clone/source side-by-side view. D87 identity rests on `created_at` equality, which is weak when the timestamp is NULL. | PARTIALLY RESOLVED |
| M285 | dashboard KPI specs | 20 dashboard KPIs specified; W12 Analysis KPIs not specified | PARTIALLY RESOLVED |
| M289 | 13-step journey | synthetic, no MainWindow | PARTIALLY RESOLVED |
| M274, M277, M280, M281, M287, M288 | – | not re-implemented in M261–M290 | NOT STARTED (in this mission series) |
| M275, M276, M278, M279, M282, M283 | mutation coverage | mutation only; no workflow change | PARTIALLY RESOLVED |

## Defects

| ID | Re-check | Class |
|---|---|---|
| D51 | 1 event in 300 historical runs. None of the 13 later source-gate runs inspected in M294 failed on a watchdog. | NOT REPRODUCED |
| D63 | deterministic opt-in reproducer; freed object unidentified; no native debugger in the sandbox | REPRODUCED — ROOT CAUSE UNKNOWN |
| D74 | routes fixed (M265); 16 closed MainWindows / 188,315 widgets retained at the end of the full suite | PARTIALLY RESOLVED |
| D81 | string stretch ∝ L²; test against Hooke's law | RESOLVED |
| D82 | route registry with `WeakMethod`; regression test | RESOLVED |
| D83 | workbench status set after refresh; test plus mutant | RESOLVED |
| D84 | policies for the two event tables; authorization tests | RESOLVED |
| D85 | `DELETED_AFTER_REPORT` sweep; test plus mutant | RESOLVED |
| D86 | comma refusal in `parse_authored` | RESOLVED: live in the W2 typed column (M295, `ae016a7`); import keeps `1,500` for review (M296) |
| D87 | `source_created_at` snapshot | PARTIALLY RESOLVED (NULL / equal-timestamp identity; M304) |
| D88 | 3.12 coverage leg: direct-SHA cancellations; 72.40 % on the documentation-only descendant | PARTIALLY RESOLVED (M293 addendum); timing cause unknown |

## Mutation

| Item | Re-check | Class |
|---|---|---|
| 18 catalogues (1,197 / 1,192 K / 4 S / 1 E / 0 I) | complete runs recorded with JSON evidence | RESOLVED as a record; "all killed" is NO |
| R-1 (7 modules) | 47/47 killed | RESOLVED |
| R-2 `KS-unfilled-casing-id-assessed` | survivor justified | OWNER DECISION REQUIRED (P11) |
| m50 trio | survived | OPEN (method limitation); never counted as killed |
| `SEC-empty-password-unlocks` | equivalent | never killed (equivalent) |

## Owner decisions (M196 packages) – unchanged, none taken on the owner's behalf

| P | Subject | Class |
|---|---|---|
| P1 | PyMuPDF (AGPL-3.0) | LICENSE / DATA RIGHTS BLOCKED |
| P2 | PySide6 LGPL-3.0 distribution terms | OWNER DECISION REQUIRED |
| P3 | pwptemp, torque_drag (LGPL-3.0) | LICENSE / DATA RIGHTS BLOCKED |
| P4 | MinerU | LICENSE / DATA RIGHTS BLOCKED |
| P5 | OCR engines | LICENSE / DATA RIGHTS BLOCKED |
| P6 | qtribbon | OWNER DECISION REQUIRED |
| P7 | AI / GPU / model weights | LICENSE / DATA RIGHTS BLOCKED |
| P8 | 7.48 vs 7.48052 | OWNER DECISION REQUIRED |
| P9 | currency | OWNER DECISION REQUIRED |
| P10 | datum and CRS | OWNER DECISION REQUIRED |
| P11 | Kill Sheet | OWNER DECISION REQUIRED |
| P12 | method approvals | INDEPENDENT VALIDATION REQUIRED |
| P13 | encryption at rest | OWNER DECISION REQUIRED |
| P14 | Windows ACL | OWNER DECISION REQUIRED |
| P15 | idle lock | OWNER DECISION REQUIRED |
| P16 | code and report signing | OWNER DECISION REQUIRED |
| P17 | Windows and field acceptance | OWNER DECISION REQUIRED (NOT RUN) |
| P18 | tubular reference data | LICENSE / DATA RIGHTS BLOCKED |
| P19 | ISCWSA / welleng | OWNER DECISION REQUIRED |

Real DDR acceptance: NOT RUN. Windows desktop acceptance: NOT RUN. Field acceptance: NOT RUN.
