> **HISTORICAL MISSION RECORD — Mission 30 checkpoint (2026-09-23).** Its inventory baseline (2232 occurrences) and its `NOT RELEASE-CERTIFIABLE — EVIDENCE INCOMPLETE` verdict describe the tree as it stood then; the numbers have since been re-adjudicated by Missions 31-33. Current state: 8932 occurrences, 3712 verified-correct, 2266 intentional-by-design, 47 defect-fixed, 49 removed-with-evidence, 2837 under-review, 4 evidence-incomplete — see [M33_SEMANTIC_AUDIT.md](M33_SEMANTIC_AUDIT.md). The body of this document is preserved unedited.

---

# Mission 30 — semantic audit checkpoint (INCOMPLETE)

Date: 2026-09-23. **This is an incomplete audit, not successful completion of Mission30.**

**Verdict: NOT RELEASE-CERTIFIABLE — EVIDENCE INCOMPLETE**

## Evidence boundary

The independently tested application/source commit is `e2eeb3539c5d9c468e73961824e9fe5229864a59`, tree `e6e6982d8238917d877f1716a9c6f59eef5649c4`, on `arena/01a0c945-drill-master`. Subsequent reporting commits must not be mistaken for this test invocation's SHA. The final delivery HEAD and patch tree are recorded separately in the publication-state artifact accompanying the patch; Git remains authoritative.

The old checkpoint was treated as a claim. Recovery commit `964e922a221870b3844fc9469544c4862ab67fbb` reproduced tree `23805f4689b43e5efd6c54e30bf09aeb829df952`; all **352/352** recorded file hashes matched. Reconstructing the M29 binary patch from `c28bbef37cbac9de7abcfa693e7e21f678fa74ab` produced 2,610,017 bytes, SHA-256 `f0ce2d925c995218069e1534d5ceeeec861b020ae7bbe5b573bb185183a06a54`. Applying it to a separate index produced that same recovery tree. This establishes content equivalence, NOT the original commit ancestry. Original `fb857d7`/`beaf963` objects remain unavailable locally; fresh GitHub lookups returned no such commit. `0bbcbd4` ancestry was not reconstructed.

The baseline gate was independently rerun: **1690 collected; 1687 passed, 3 skipped, 20 warnings, 258.02s**, exit 0. A green baseline did not prevent the subsequently demonstrated defects.

## Inventory accounting — no disguised completion

Artifact: [`docs/audits/m30-evidence/inventory.json`](docs/audits/m30-evidence/inventory.json).

| Measure | Actual |
|---|---:|
| Original occurrences | 2259 |
| Previously marked reviewed by M29 | 27; approvals not inherited automatically |
| M30 requested queue | 2232 |
| Contextually reviewed in this checkpoint | **41** |
| Closed within the stated occurrence-level boundaries | **40** |
| Reviewed but still insufficient evidence | **1** |
| Not reviewed | **2191** |
| A VERIFIED-CORRECT | 12 |
| B DEFECT, repaired in this checkpoint | 16 |
| C DUPLICATE/DEAD/LEGACY, retained unwired prototype | 2 |
| D INTENTIONAL | 9 |
| E ACCEPTED LIMITATION | 1 |
| F EXTERNAL ACCEPTANCE | 0 |
| G NOT ENOUGH EVIDENCE | **2192** |

G on the 2191 unreviewed rows is an explicit open-queue marker, **not a substantive disposition**. Therefore **2232/2232 closure was NOT achieved**. B counts inventory occurrences, not independent bugs or root-cause clusters. Several repaired defects lie outside the original pattern inventory. A/D approvals apply only to their documented context and input preconditions, not an entire module or every direct-ORM/raw-SQL path.

The original textual IDs collide **100 times**. M30 preserves the original array ordinal in unique `M30-xxxxx` identifiers rather than dropping occurrences in a dictionary keyed by the old ID. Each reviewed entry contains the baseline expression, source hash, caller, data contract, output effect, tests, reason and disposition. Unreviewed entries deliberately have no invented caller/test evidence.

Conservative queue priorities are 1163 CRITICAL and 1069 HIGH, based on sensitive domain routing, **not discovered-defect severity ratings**. Of the unclosed entries, 1139 carry CRITICAL priority and 1053 HIGH. These still block certification.

## Fresh semantic scans

The same original scanner was rerun with **no inherited approvals**:

- 174 production files; **2262** occurrences, compared with 2259 originally.
- Expression/context/kind multiset comparison: **2249 unchanged**, **10 removed/changed**, **13 added/changed**. Line shifts do not create artificial differences; duplicated expressions retain multiplicity.
- These are detection counts, not safety judgments. A changed exception body can appear as a removed/added pair.

A separate broader AST sweep over `core`, `dialogs`, `tabs`, `ui` found 173 `or zero`, 489 `or empty`, 743 falsey-if, 148 single-row/scalar selections, 566 broad handlers, 114 pass statements and 1020 None/False returns. Its coverage differs from the original scanner, which also includes four root entrypoints. The categories are **not directly comparable totals** and are not automatically classified safe/unsafe. See `fresh-sweep.json` and `sweep-comparison.json`.

## Independently demonstrated failures and corrections

See [M30_ROOT_CAUSES.md](M30_ROOT_CAUSES.md) for locations and regressions. Recorded before-fix failures include:

- Initial new regression set: **16 failed, 3 passed**.
- Disappearing backup source and extreme MSE arithmetic: **4 failed, 22 passed** in the expanded targeted selection.
- Derived monetary/plan overflow: **4 failed**.
- Unrepresentable integer conversion: **2 failed**.
- Explicit unknown currency markers: **4 failed**.

These selections overlap; their counts must not be added as unique defect counts. Compound tests may stop at their first failed assertion. Later assertions are not independently established before-fix failures merely because the test failed.

The new regression module has **42 parametrized cases**. Final full gate: **1732 collected, 1729 passed, 3 skipped, 20 warnings, 236.34s; zero failed/errors/xfail/xpass/deselected**, exit 0. Linux Python 3.11.2, offscreen Qt, **explicit Qt dependency stubs**. Native Qt loading failed for missing `libGL.so.1`; this is not native GUI or Windows certification.

Mutation evidence: all **14 inherited controls were independently replayed**, all **10 new controls detected their injected defect**, and the separate UI-package omission control failed both its focused test and installed-wheel gate. Every mutated file was restored to its exact preceding SHA-256; no mutant was committed. Later replay of the inherited controls and wheel control again restored the source exactly. Test-sensitivity evidence does not validate every assertion or every unreviewed test.

## A–T scenario evidence

PASS below is limited to the described automated scenario, not global domain certification. Test modules and complete execution logs are in the evidence archive; each listed test was included in the full gate unless marked external.

| ID / setup | Action | Expected | Actual / artifact |
|---|---|---|---|
| A — two wells, similarly matching records | Search with a well filter | No result owned by the other well | PASS: `test_search_honors_well_scope_for_every_entity_and_ai` |
| B — two bores | Analyze ownership | No arbitrary bore selection | PASS: scope attribution multiple-bore/sidetrack tests |
| C — two sections | Analyze ambiguous report | Ambiguous, no silent assignment | PASS: `test_multiple_sections_ambiguous` |
| D — same stock name, different units | Save/carry bulk stock | Separate identities, no quantity borrowing | PASS: `test_bulk_same_name_different_unit_does_not_overwrite`; carry regression. This is NOT complete same-name UI coverage. |
| E — NULL/NULL report, two bores/one section | Analyze, then explicit resolution | Preview unchanged; safe multi-pass convergence | PASS: `test_two_bores_one_section_null_null_report_converges_safely` |
| F — explicit zero quantities | Compare/save/display | Zero stays known | PASS: M28/M29 scalar/persisted plan matrices and inventory tests |
| G — missing quantities | Compare and summarize | Missing is not zero | PASS: matrix and time regressions; repository-wide default audit remains open |
| H — mixed/unknown currencies | Aggregate records | No unsupported cross-currency total | PASS: M28 grouping and M30 explicit-marker tests; no FX invented |
| I — plan only | Scalar and persisted comparison | Actual absent; variance/percentage unavailable | PASS: `test_required_eleven_pair_plan_matrix`, `test_persisted_plan_matrix_matches_scalar_contract` |
| J — actual only | Same consumers | Plan absent; no fabricated target | PASS: same two matrices |
| K — permission exception | Attempt guarded action | Fail closed | PASS: M28/M29 permission regressions and reintroduced permission bug detected; not complete OS ACL coverage |
| L — existing backup, source disappears | Back up while source open fails/races | Old destination preserved, no empty-source creation or success | PASS: `test_backup_source_disappearing_does_not_create_empty_success` and old-destination fault regression |
| M — nested JSON/outcome data | Mutate input and returned structures | No alias mutation of authoritative snapshot | PASS: M29 nested snapshot and M30 attribution serialization tests |
| N — duplicate import | Repeat DDR workflow | No duplicate authoritative persistence | PASS: existing DDR lifecycle/idempotency tests in full gate; exhaustive vendor identity review remains open |
| O — malformed write/import | Submit invalid stock and malformed DDR data | Rollback, no partial successful report | PASS: M30 real-DB invalid movement and existing DDR atomic persistence tests |
| P — ambiguous or malformed attribution candidates | Analyze/resolve | Ambiguous/invalid, no fabricated ownership | PASS: new invalid-candidate regression plus scope suite |
| Q — invalid ownership/parent moves | ORM relationships and guarded writes | Rejection, not correction | PASS: M29 relationship/parent-move tests; every merge/raw-SQL/import path not closed |
| R — inconsistent stored DB | Startup validation | Detect/block without rewriting owners | PASS: `test_startup_validator_rejects_stored_section_contradiction_without_repair`; production legacy DB acceptance NOT-RUN |
| S — installed package outside checkout | Build clean wheel, install, run `app.py --package-smoke` | Package resources resolve without checkout fallback | PASS: final gate; intentional missing `ui*` mutation detected. Not a frozen Windows run. |
| T — AI/MinerU unavailable | Retrieve through failing DB; explicitly request real PDF acceptance | Failed/unavailable, not no-match/false success | PASS for typed retrieval failure; real PDF acceptance **EXTERNAL-BLOCKED**, opt-in run actually failed because MinerU was disabled/not detected |

## Open work is substantive

The 69-domain matrix remains PARTIAL throughout. In particular, entire financial pipelines and assumptions, every engineering persistence/UI/export path, all ownership mutation entrypoints, complete UI selection transitions, all warning consumers, every test's integrity, all lint occurrences, dependency/import/resource closure and field-level export parity are not closed. A valid helper or green targeted test does not discharge these obligations.

Legacy inventory decoding is specifically kept G: read-only malformed/huge numbers become unknown, but complete migration/re-save provenance consequences were not established. Formation-similarity methods are retained unwired prototypes, not asserted to be a working production feature or proven safe to delete. Backup-temp cleanup denial is an accepted OS limitation: operation fails, previous destination remains, warning is logged, and operator cleanup may be needed.

No production dependency or lock version was changed to match this environment. No branch, production module or historical audit was deleted. No exhaustive release or external-only verdict is justified.
