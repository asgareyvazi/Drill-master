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
| M274, M277, M280, M281, M287, M288 | – | not re-implemented in M261–M290 | NOT STARTED at the start of M291; see the M291–M320 status table below |
| M275, M276, M278, M279, M282, M283 | mutation coverage | mutation only; no workflow change | PARTIALLY RESOLVED |

## Defects

| ID | Re-check | Class |
|---|---|---|
| D51 | 1 event in 300 historical runs. None of the 13 later source-gate runs inspected in M294 failed on a watchdog. **M309:** monitor `tools/quality/d51_ci_monitor.py`, window 2026-11-18 → 2026-11-22: 28 SUCCESS, 18 SUPERSEDED, 2 JOB_TIMEOUT (D88 class), 4 IN_PROGRESS, **0 D51_WATCHDOG** | NOT REPRODUCED (absence bounds the rate; it is not a fix) |
| D63 | **M307:** freed object decoded (QDoubleValidator signal-instance cache, `notationChanged`); cause = PySide6 6.8.1.1 SignalInstance weakref use-after-free (`WeakRef::create(source, sourceGone, self)`), fixed upstream in 6.8.2 (e226b5827c); A/B 6.8.1.1 5/5 SIGSEGV vs 6.8.2.1 0/5. Fix = pin bump, not done | OWNER DECISION REQUIRED |
| D74 | routes fixed (M265); **M308:** version-gated weak window attributes; on 6.8.2.1 0/3 closed windows and 0 widgets left, on the pinned 6.8.1.1 still retained (3/3, 28,680 widgets) | PARTIALLY RESOLVED |
| D81 | string stretch ∝ L²; test against Hooke's law | RESOLVED |
| D82 | route registry with `WeakMethod`; regression test | RESOLVED |
| D83 | workbench status set after refresh; test plus mutant | RESOLVED |
| D84 | policies for the two event tables; authorization tests | RESOLVED |
| D85 | `DELETED_AFTER_REPORT` sweep; test plus mutant | RESOLVED |
| D86 | comma refusal in `parse_authored` | RESOLVED: live in the W2 typed column (M295, `ae016a7`); import keeps `1,500` for review (M296) |
| D87 | `source_created_at` snapshot. **M304:** a source with NULL `created_at` is refused for cloning; a reused id with a different `created_at` is SOURCE_REPLACED and not compared. Two rows with an equal timestamp and a reused id stay indistinguishable | PARTIALLY RESOLVED |
| D88 | 3.12 coverage leg: direct-SHA cancellations; 72.40 % on the documentation-only descendant | PARTIALLY RESOLVED (M293 addendum); timing cause unknown |

### Regressions found and fixed during M291–M320 (stated, not hidden)

* **`field_registry` (M298):** `core/ddr_value_states.registry()` tripped the repo-wide `test_model_registry` AST
  guard (a function named `registry` is reserved). The guard runs only in the full suite, so the failure was pushed
  in `d57f5b2` and CI was expected to fail on it. The function was renamed `field_registry()` (tests and evidence
  updated); the guard tests now run before every push.
* **`ae016a7` CI:** its 3.12 and 3.13 legs were cancelled at 47 min by the concurrency group when `d57f5b2` was
  pushed (superseded, not failed). That commit has no 3.12/3.13 result; 3.11 and Windows passed.
* **M320 E Windows layout:** the citation buttons on the Knowledge Assistant evidence header widened the panel to
  1,590 px on Windows (M49 limit 1,300). Windows gate run `45001056829` failed on `2273aa4`. They now sit on their
  own row (1,275 px, the same as before M320 E), and a structural assertion was added to the M320 E UI test.
* **Exception ceiling:** M308/M314/M317 added four unexplained silent handlers (87 > 83). Each one is now marked
  `# silent-ok:` with its reason; the ceiling was not raised.

## M291–M320 implementation status

| Item | Mission | Evidence | Class |
|---|---|---|---|
| M295–M297 value-state entry and import | M295–M297 | `m295_m297_value_state_entry_and_import.md` | RESOLVED for the 11 header fields (synthetic) |
| M298–M299 registry and batch | M298–M299 | `m298_m299_registry_and_batch.md` | RESOLVED (synthetic) |
| M300–M302 value lineage | M300–M302 | `m300_m302_value_lineage.md` | RESOLVED (synthetic) |
| M303 clone contract (11 adapters) | M303 | `m303_m306_clone_contract_bulk_and_compare.md` | RESOLVED |
| M304 clone provenance / D87 | M304 | same | PARTIALLY RESOLVED (D87 equal-timestamp case) |
| M305 bulk archive / restore | M305 | same | RESOLVED (synthetic) |
| M306 clone vs source | M306 | same | RESOLVED (copy, never a rerun) |
| D63 root cause | M307 | `m307_m308_d63_root_cause_and_d74.md` | OWNER DECISION REQUIRED (PySide6 ≥ 6.8.2 pin) |
| D74 release policy | M308 | same, `m308_d74_product_policy_runs.txt` | PARTIALLY RESOLVED |
| D51 monitoring | M309 | `m309_d51_monitoring.md` | NOT REPRODUCED |
| **M274** architecture revision diff | M311 | `m311_m274_architecture_revision_diff.md` | RESOLVED (synthetic) |
| **M277** DDR hydraulics check | M314 | `m314_m277_ddr_hydraulics_check.md` | RESOLVED (SCREENING; history NOT REPRODUCIBLE, stated) |
| **M280** cement job reconciliation | M317 | `m317_m280_cement_job_reconciliation.md` | RESOLVED (WORKSHEET; history NOT REPRODUCIBLE, stated) |
| **M281** T&D friction sensitivity | M318 | `m318_m281_td_friction_sensitivity.md` | RESOLVED (SCREENING; never interpolates a factor) |
| **M287** Report Center section manifest | M320 D | `m320d_m287_report_section_manifest.md` | RESOLVED for DDR and EOWR; NPT / Cost / Plan stated as not available |
| **M288** answers with exact citations | M320 E | `m320e_m288_citation_record.md` | RESOLVED (synthetic; a citation is not a semantic verification) |
| Dialog lifetime re-check (`WA_DeleteOnClose`) | M308 follow-up | lineage and clone-comparison dialogs contain no validator (the D63 object); callers only overwrite their reference | RESOLVED |

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
