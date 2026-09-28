> **HISTORICAL MISSION RECORD (Mission 28).** This file is preserved unedited as the evidence it produced. Its counts, hashes and verdicts describe the tree at that time and are superseded by the Mission 33 re-adjudication — see [M33_SEMANTIC_AUDIT.md](../../M33_SEMANTIC_AUDIT.md) and [M33_RELEASE_CERTIFICATION.md](../../M33_RELEASE_CERTIFICATION.md).

# Mission 28 — Forensic re-audit, repairs and final source gate

Date: 2026-09-22. Verdict: **NOT RELEASE-CERTIFIABLE**.

The named defects below were repaired and committed. The final **clean repository source gate passed**. This is not a claim that every legacy reduction, save path, external integration or shipping environment has been semantically certified. In particular, the requested exhaustive residual-site closure remains incomplete. This report replaces earlier release-readiness conclusions, not their historical evidence.

Evidence directory: [`m28-evidence/`](m28-evidence/). Execution results are local unless explicitly identified otherwise.

## A. Git reality and provenance

### Exact implementation and certification identities

- Repository: `asgareyvazi/Drill-master`.
- Session/work branch: `arena/01a0c945-drill-master`. No other branch was checked out, created, pushed or deleted.
- Requested remote target: `arena/01a085e0-drill-master`, independently queried at **`c28bbef37cbac9de7abcfa693e7e21f678fa74ab`**. It does **not** contain the independent repairs.
- Final tested implementation: **`e83fc3ec85447446e50b4dd2acbc64169d07f054`**.
- The certification/evidence commit is the subsequent documentation-only commit adding this report and the final execution evidence. It is **not** the implementation SHA tested by the full suite. Resolve its identity with `git log -1 --format=%H -- docs/audits/2026-09-22_M28_FORENSIC_RELEASE_GATE.md`; the final response also identifies it.
- The source manifest fingerprints **348** tracked source/test/config/build/asset files, excluding historical audit documents. See `source-manifest.json`. Documentation-only certification changes must not be represented as a new full-suite run.

### Reconstructed history, not commit-message certification

| Commit/range | Independently established meaning |
|---|---|
| `3f52e2e..95dd631` | Original cleanup changed **107 files**, 156 insertions / 344 deletions. AST comparison finds **479 removed import occurrences**, or **425 distinct per-file import aliases**. The message's `485` was not reproduced by these definitions. |
| `95dd631..c28bbef` | One certification document, 389 added lines. This is a certificate commit, not a new implementation or execution result. |
| Worktree inherited at `c28bbef` | Separate independent M27 fixes: 29 modified tracked files plus 17 new files. All **341** entries in its historical source manifest matched before preservation. |
| `b158557` | Preserved that independent patch: 46 files, 2968 insertions / 209 deletions. Thus “uncommitted independent repairs” did not mean that `95dd631` or `c28bbef` were absent remotely. |
| `83eea08` | M28 currency/NULL/safety fixes, tests, gate changes and initial forensic evidence. |
| `c2fac7c` | Restored the credential-policy entrypoint re-export and added actual source startup smoke. |
| `8fbf08e` | Canonicalized cost ORM writes and tested known/unknown currency import round trips. |
| `e83fc3e` | Enforced W8 child-save permissions and cleared absent well context; final tested implementation. |

`git push origin arena/01a0c945-drill-master` was rejected after preservation: the GitHub App cannot create/update `.github/workflows/ci.yml` without **workflows permission**. No successful publication is claimed. Repeating the unchanged push would not resolve that permission. An applicable cumulative patch is supplied separately as `/home/user/mission28-repairs.patch`; apply it only to the matching `c28bbef` base in an authorized checkout. No credentials were requested or stored.

### Branch classification

The exact remote SHAs and implementation-relative ahead/behind counts are in `git-reality.txt` and `remote-heads.txt`.

| Branch | Classification | Decision |
|---|---|---|
| `arena/01a0c945-drill-master` | ACTIVE | Local session branch; preserve all repair commits. |
| `arena/01a085e0-drill-master` | ACTIVE | Requested target, still `c28bbef`; do not mistake it for tested implementation. |
| `arena/01a056c5-drill-master` | MERGED-SAFE-TO-DELETE | Ancestry checked; retained, not deleted. |
| `arena/01a05747-drill-master` | MERGED-SAFE-TO-DELETE | Ancestry checked; retained. |
| `arena/01a07094-drill-master` | MERGED-SAFE-TO-DELETE | Ancestry checked; retained. |
| `arena/01a0801f-drill-master` | MERGED-SAFE-TO-DELETE | Ancestry checked; retained. |
| `drill-Master` | UNMERGED-REVIEW-REQUIRED | Three unique commits and a unique PDF; retained without merge/reset. |

The unique PDF is **not missing**: `12 - DDR OEOC-201 AZNS-166 2025-Nov-07 (1404.08.16).pdf`, 740510 bytes, Git blob `e91e0b6899268c37455c93c6132620b012ed6112`. It was extracted outside the checkout without switching branches. SHA-256: `6ce9b37e4e30c7800191598d9f9febebc12d4cf0ab5932c5d7f6ad1b789a226c`. PyMuPDF opened four pages and extracted 10230 text characters. This establishes asset readability, **not** MinerU normalization/review/persistence acceptance.

## B. Findings: root cause, impact and closure evidence

All CLOSED findings below refer to the tested implementation, not the unchanged requested remote.

| ID | Severity | File / function | Root cause and impact | Evidence / disposition |
|---|---|---|---|---|
| M28-01 | Critical | `core/database.py` credential-policy re-exports; `app.py` imports | Cleanup removed `bootstrap_password_for_role` although `app.py` imported it. Actual application entrypoint failed before startup. Core-only imports missed it. | Initial `app.py --package-smoke` exit 1 retained; explicit compatibility re-exports restored; actual entrypoint subprocess is now a release test. **CLOSED**. |
| M28-02 | High | `cost_semantics.summarize_costs`; `DatabaseManager.get_cost_summary/get_actual_vs_plan`; Intelligence; reports | Category-only sums combined currencies; unknown values became zero or incomplete subtotals became totals. False financial claims could cross DB, UI and exports. | Common currency-aware reducer, strict completeness and separate category/currency groups; mixed/unknown currency tests and consumer parity. **CLOSED for audited paths**. |
| M28-03 | High | `tabs/w16_Cost_Management.py` AFE read/load/save/summary/export | Dollar labels, fabricated template budgets, NULL→0 widgets, dropped currency/metadata and stale well worksheet. Global currency could relabel loaded rows. | Nullable sentinel distinct from explicit zero; per-row currency; metadata preservation; blank monetary templates; context reset; CSV includes currency. Subprocess regression exercises actual controls and export. **CLOSED**. |
| M28-04 | High | `core/actual_vs_plan.py` `compare`, `compare_metrics`, `compare_plan_activities`; DB plan queries | Scalar missing inputs became 0/on-track; nonzero actual over zero plan became synthetic 100%; DB lost zero days/ROP and partial time appeared complete. Latest arbitrary plan could replace active-plan selection. | Nine-pair scalar/canonical and activity matrices; unavailable metadata preserves known side; undefined percentage stays None; active-plan uniqueness; shared complete-time reducer. **CLOSED**. |
| M28-05 | High | `SafetyReport` defaults; `safety_semantics.safety_kpis`; Intelligence | No observations were reported as zero incidents; historical maximum LTI-free days could mask a later reset. ORM defaults invented unobserved measurements. | No record→None; complete incident totals; uniquely latest LTI-day observation, including zero; nullable numerical defaults. **CLOSED**. |
| M28-06 | High | `tabs/w8_Safety_Widget.py` initialization, nullable load/save, BOP schedule and waste form | Invented drills/dates, 120 days, 5000 pressure, waste pH/volumes, turbidity and hardness could become persisted facts. Empty contexts retained previous values. An overdue date was moved into the future. | Empty/new forms are unknown; explicit zero editable; blank BOP rows; no overdue-date extension; missing dates NOT ASSESSED; no invented pH average; absent context clears. UI and DB regression. **CLOSED**. |
| M28-07 | High | `core/report_engine.py` EOWR/NPT/Cost/Plan collection, HTML and Excel; W12 cost view | Independent finance reducers and dollar labels contradicted source currency; projection and missing durations had inconsistent handling. | Shared currency/time contracts, explicit projection denomination, raw unaggregated cost lines, no mixed total, NULL-aware plan rendering and currency-aware Excel/HTML. **CLOSED for audited paths**. |
| M28-08 | High | `core/base_tab.py` `save_data/check_permission`; `hierarchy_operations.check_delete_permission`; W16 save | Broad exception handling failed open when the permission subsystem raised. | Exceptions now block writes/deletes; injected failure regression. **CLOSED**. |
| M28-09 | High | W8 `_preserve_nullable_safety_fields` / child saves | Child controls could persist without passing through the parent permission check. | Actual write boundary enforces viewer/read-only and edit permission, including exception failure; subprocess proves denied save leaves DB value unchanged. **CLOSED**. |
| M28-10 | High | `DatabaseManager.backup_to` | Failure cleanup deleted the destination, including a previously valid backup. | Backup writes a temporary sibling then replaces destination only after completion; injected SQLite failure preserves previous bytes and removes only temporary file. **CLOSED**. |
| M28-11 | Medium | `tests/test_release.py`, `verify_release.py` | Required GUI imports could become skips; root entrypoint was untested; explicit version/wheel metadata agreement was not checked. | No required-import green skip; real source entrypoint subprocess; version drift negative tests; wheel metadata/version validation. Existing accounting/diff/dependency/lint protections retained. **CLOSED for source gate**. |
| M28-12 | Medium | `tests/test_packaging_smoke.py`, `tests/test_ddr_acceptance.py` | A provided bundle was only structurally checked; explicitly requested PDF acceptance could skip absent MinerU. | Provided bundle requires Windows and executes smoke; explicitly provided PDF fails clearly as ENVIRONMENT-BLOCKED without MinerU. No asset supplied remains optional skip. **CLOSED test-contract defect; execution blocked externally**. |
| M28-13 | Medium | `CostRecord` ORM write events | Atomic import/direct ORM writers could retain stale variance or unnormalized currency independently of W16. | Insert/update canonicalization validates finite optional amounts, preserves NULL/zero, normalizes currency and recomputes variance. Import tests cover None/USD/EUR; stale-variance regression. **CLOSED**. |
| M28-14 | Medium | `save_safety_report/get_safety_report` | `.first()` could silently choose duplicate same-context safety observations. | Unique write selection; duplicate latest-date reads explicitly error instead of selecting an arbitrary observation. **CLOSED**. |

### Contracts established from the repository

**Currency.** `Project.currency` is a project setting, not proof of a `CostRecord` denomination and not an FX rate. `CostRecord.currency` is authoritative for that line. There is no demonstrated exchange-rate/conversion model. Only a single explicit currency permits an aggregate total. Mixed or unknown currencies suppress the overall total. Category/currency groups remain visible; unknown-currency groups do not fabricate sums. Raw source amounts remain visible without pretending they have known units. Each side of a total is complete only if every contributing amount on that side is known. No exchange model, accounting framework or new dependency was introduced.

**AFE/OPEX.** AFE replacement is still atomic, well-scoped and limited to AFE lines; OPEX lines remain untouched. Per-row currency and source metadata survive reload/resave. Rig/spread rates are explicitly labelled, nonpersistent projection assumptions. Projection currency must be supplied separately, and a projection never replaces actual cost. Explicit zero is allowed; missing currency/rate is not a zero-rate financial fact. No payroll, FX, NPV, IRR-return or payback engine was established; `IRR` in the currency selector means Iranian rial, not internal rate of return.

**Plan NULL matrix.** Both scalar and canonical paths exercise `(None,None), (None,0), (0,None), (0,0), (100,None), (None,100), (100,0), (0,100), (100,100)`. Missing side means unavailable, not on-track. The known side remains available to DB consumers. Zero/zero preserves the existing equality convention (0%, on-track). Nonzero/zero has a real delta but no finite percentage; it is unavailable for percentage assessment. Actual-minus-planned metric delta remains distinct from planned-minus-actual budget variance.

**Safety.** No record is no evidence, not zero incidents. Recorded zero remains zero. Missing contributor counts invalidate incident totals. Days without LTI uses a uniquely latest observation, not maximum historical value. Legacy stored zeros are not retroactively changed: whether they were explicit or generated historically cannot be recovered safely. No unsolicited migration/backfill was performed.

### Import/dead-code forensic scope

`import-removals.json` accounts for removed aliases and exact tracked Python symbol consumers, including root entrypoints and tools. The credential-policy consumer was found only after expanding beyond core/tabs/dialogs. Package `__init__.py` export lists were not removed by this cleanup; engineering public exports remain intact. False-positive name matches such as the local `field` parameter or `date` loop variable do not establish an import dependency. No additional module was deleted in this mission. Runtime/lazy/optional integrations still require their own behavior tests; import success alone is not proof of optional backend execution.

Final fresh isolated imports: **171 processes, 171 successes, 0 failures**, including `app`, `main_window` and `run`. Full tests additionally exercise engineering adapters/dialogs/persistence. MinerU remains external and optional, not a bundled core dependency.

### Broad default/reduction/exception inventory — explicit completeness boundary

`risky-site-inventory.json` indexes **1370** production sites: 345 `.get(...,0)` matches, 562 broad exception clauses, 124 numerical defaults, 195 `or 0` matches and 144 `.first()` selections. These counts use documented regex populations; they are not bug counts and are not interchangeable with older counts.

Reviewed classifications include:

| Classification | Example / rationale |
|---|---|
| SAFE | Sort-only `value or 0`, and `depth or 0` after an explicit `depth is not None` filter: no missing measurement is persisted or reported as zero. |
| EXPLICIT-ZERO | Recorded amount/ROP/time/count zero; exercised separately from NULL in regressions. |
| UNKNOWN-SAFE | Zero report-count denominator guarded so the derived financial metric remains None. |
| FABRICATED-DATA | Former W8 defaults and W16 monetary templates; removed, not merely documented. |
| AMBIGUOUS | Remaining unadjudicated legacy defaults/selections/broad catches. Inventory alone does not establish safety or justify deletion. |

The inventory does **not** individually adjudicate every remaining site or every `sum/max` caller. Consequently the mission's exhaustive “every material repository verification blocker closed” condition is **not certified**. The successful suite is not substituted for this missing semantic review.

## C. Fix verification and negative controls

Primary regressions are in `tests/test_m28_finance_safety_plan.py` (32 tests at final execution), with additional release/version/import regressions in existing test modules.

- Finance: common-currency grouping, unknown currency, incomplete amounts, no project-currency inference; currency/metadata round trip; DB→Intelligence→Plan/Actual→Cost/NPT/EOWR parity; raw HTML/Excel/CSV preservation.
- Plan: both nine-pair matrices; activity inputs; zero days and zero ROP through actual SQLAlchemy persistence.
- Safety: absence/zero/latest reset, duplicate observations, default-free ORM data, actual W8 controls, empty-context resets and viewer-denied writes.
- Integrity: permission-system exception injection, backup failure preservation, stale-variance ORM protection, source startup execution, version drift rejection.
- Existing M27 ownership, parent relationship, scope attribution, snapshot, selected-section and dirty-save tests were rerun as part of the final suite; they are not relisted as open defects.

**Mutation control:** runtime-only substitutions reintroduced mixed-currency summation, NULL→zero plan comparison and zero-for-missing safety. Selected real regressions produced **9 failed, 5 passed, 17 deselected**, expected pytest exit **1**, 0.40s. No production source mutation was retained. This is negative-control evidence, not a successful acceptance run.

**Failures were not hidden.** The first broad development execution had 23 failures and 65 errors, largely caused by an overbroad edit accidentally removing `log_audit/get_audit_logs`. Both methods were restored exactly and the remaining API definitions compared with the baseline. A subsequent clean gate at `c2fac7c` had one failure: an import test expected an aggregate without supplying currency. It now explicitly tests None/USD/EUR, verifies unchanged raw amounts and requires unknown aggregates for unknown currency. Later clean full gates passed; only the final implementation run is used below.

No runtime dependency or lock pin was changed.

## D. Residuals, typed and not confused with fixed defects

| Residual | Type | Status / exact missing evidence |
|---|---|---|
| Publication of repair commits and workflow | PERMISSION LIMITATION | GitHub App workflow permission denied; local commits and cumulative applicable patch exist. Requested remote remains unchanged. |
| Hosted CI for repaired implementation | PERMISSION LIMITATION / ENVIRONMENT LIMITATION | `c28bbef` has **0 check runs**. Remote action listing contains two successful historical dynamic runs at `c1e8edd…`, neither the target nor repaired implementation. Local execution is not hosted CI. |
| Windows executable, startup UI, installer/upgrade/uninstall/data preservation | ENVIRONMENT LIMITATION | Linux environment, no actual Windows bundle/installer execution. Static spec/PowerShell/Inno review and source smoke are not substitutes. |
| MinerU→IR→normalization→review→explicit persistence on real PDF | ENVIRONMENT LIMITATION | Real PDF recovered and readable, but MinerU health reports unavailable/disabled, no executable/version. Explicit PDF acceptance returns environment-blocked failure, not a green skip. |
| Approved production DB acceptance/migration/backup-restore | MISSING ASSET | No approved production DB supplied. Isolated databases and failure injections passed; cannot assert real-data migration acceptance. |
| Exhaustive legacy semantic sweep | DESIGN LIMITATION of current verification coverage | Inventory and tests do not prove all 1370 sites and all remaining reducers correct. Unadjudicated sites remain AMBIGUOUS; this is an unclosed verification obligation, not a claim that 1370 code bugs exist. |
| Python 3.12/3.13 execution and native Linux Qt | ENVIRONMENT LIMITATION | Fresh binary lock resolution succeeded for 3.12/3.13, but execution was only Python 3.11.2 with offscreen Qt native-library stubs. Native rendering/platform acceptance is unverified. |
| Exact lock on Python 3.10 | DESIGN LIMITATION / compatibility boundary | Fresh binary-only resolution failed (including `contourpy==1.3.3` Python support). Broad unlocked source metadata is not proof that the exact lock runs on 3.10. Documented locked release matrix is 3.11–3.13. |

No FX model is a documented design boundary, **not** an unresolved mixed-currency summation bug. No MinerU installation is **not** evidence of a missing PDF. Closed Plan NULL, Safety, startup import, currency and backup defects must not be carried forward as open blockers.

## E. Fresh test evidence

### Final clean implementation gate

```text
Implementation: e83fc3ec85447446e50b4dd2acbc64169d07f054
Branch: arena/01a0c945-drill-master
QT_STUB_DIR=/home/user/qt-libs
LD_LIBRARY_PATH=/home/user/qt-libs
QT_QPA_PLATFORM=offscreen
.venv/bin/python verify_release.py --expected-sha e83fc3ec85447446e50b4dd2acbc64169d07f054
Exit: 0
Collected: 1589
Passed: 1585
Skipped: 4
Failed/errors/xfail/xpass/deselected: 0 / 0 / 0 / 0 / 0
Warnings: 19
Pytest duration: 300.36 seconds
```

`source-gate.txt` contains the actual command output, clean Git state, dependency checks, collection, results and wheel build. Environment: Linux, CPython **3.11.2**, pytest **9.1.1**, ruff **0.16.6**, build **1.6.1**; exact runtime pins checked individually and `pip check` passed. This is the actual lock environment, not a developer package-list substitution.

| Check | Gate disposition | Evidence |
|---|---|---|
| Expected SHA / branch / clean state / staged and unstaged diff checks | PASS | Final source-gate log |
| Exact 26 runtime pins + pip consistency | PASS | Final source-gate log |
| Source/packaging version `1.0.0` | PASS | Version gate; wheel METADATA verified against canonical version |
| Required JSON/assets/build definitions | PASS | Resource gate |
| Compileall | PASS | Full configured source/tests/packaging targets |
| Ruff E722/F821 | PASS | Zero findings |
| Ruff debt ratchet | PASS | **5368 ≤ 5375**, explicitly **not lint-clean** |
| Collection and full pytest accounting | PASS | 1589 = 1585 + 4; no unexpected outcomes |
| Actual wheel build and contents | PASS | `drillmaster-1.0.0-py3-none-any.whl`; required config/resources present, tests excluded |
| Real source `app.py --package-smoke` | PASS | Fresh subprocess in release suite; temporary test DB, not production startup acceptance |
| Final isolated imports | PASS | 171/171, implementation SHA recorded in JSON |
| Full-gate optional external tests | SKIPPED-OPTIONAL | Four explicitly listed below; not acceptance successes |
| Real repository workbook opt-in | PASS | **1 passed, 1 warning, 5.22s**, actual tracked workbook, canonical IR/review/atomic DB boundary |
| Explicit real PDF opt-in | ENVIRONMENT-BLOCKED | **1 failed, 0.06s**, exit 1 because MinerU unavailable; independently retained |
| Windows frozen runtime/installer | NOT-AVAILABLE | No actual executable/installer run |
| Approved production DB | NOT-AVAILABLE | No asset supplied |
| Hosted CI on repaired SHA | CLAIMED-BUT-UNVERIFIED if inferred from local gate; no such claim made here | No published repaired SHA / qualifying remote run |
| Lock dry-run 3.12 / 3.13 | PASS — resolution only | Both exit 0; no cross-version execution claim |
| Lock dry-run 3.10 | FAIL — documented unsupported locked boundary | Exit 1; lock unchanged |

The four normal-suite skips are real DDR XLSX (path not set in that run), real DDR PDF (path not set), real MinerU integration input not set, and Windows bundle unavailable. The XLSX was separately run with the actual asset and passed. The PDF was separately requested and blocked by the external engine. Nineteen warnings are openpyxl validation-extension warnings, PyMuPDF/SWIG deprecations and the explicitly warning-only large-file inventory—not test errors.

The wheel builder used isolated build dependencies (`setuptools 84.0.0`, `wheel 0.48.0` in this execution). A successful wheel is not a reproducibly identical Windows EXE or an installer acceptance test.

## F. Release matrix — named domains

`VERIFIED` means the stated repository-level evidence under the declared environment, never universal production acceptance. Domain statuses use only the requested vocabulary.

| # | Domain | Status | Evidence / boundary |
|---|---|---|---|
| 1 | Git identity/current implementation | VERIFIED | Expected SHA + clean gate; manifest |
| 2 | History/certificate reconstruction | VERIFIED | Actual three-commit lineage and independent patch distinguished |
| 3 | Branch ancestry/unique asset preservation | VERIFIED | Remote heads, ancestry, unique PDF retained |
| 4 | Publication/remote current target | BLOCKED | Workflow permission; target unchanged |
| 5 | Architecture/callers/consumers | PARTIAL | Critical data paths traced; entire legacy graph not exhaustively certified |
| 6 | Import cleanup/re-exports | VERIFIED | AST inventory, real entrypoint repair, 171 isolated imports |
| 7 | Optional/lazy backend execution | PARTIAL | Adapter tests passed; real external runtimes absent |
| 8 | Ownership/relationship assignments/startup checks | VERIFIED | Full inherited ownership and migration regression suite |
| 9 | Scope attribution/read-only resolution | VERIFIED | Existing exact/unknown/ambiguous/conflict regressions rerun |
| 10 | W12 selected section/whole-well labels | FIXED-BUT-NOT-ENVIRONMENT-VERIFIED | Scope regressions pass; native desktop not run |
| 11 | General NULL/default/reducer sweep | PARTIAL | Named fixes complete; 1370-site inventory not individually certified |
| 12 | Plan scalar/canonical/activity NULL | VERIFIED | Nine-pair matrices and DB zero tests |
| 13 | Active plan and plan export | VERIFIED | Unique selection, NULL-safe totals/rendering, existing plan tests |
| 14 | Safety reducer/no-data vs explicit zero | VERIFIED | Pure/DB regressions and Intelligence parity |
| 15 | W8 forms/BOP/waste/save boundary | FIXED-BUT-NOT-ENVIRONMENT-VERIFIED | Actual offscreen subprocess; native Qt stubs boundary |
| 16 | Cost model/complete totals | VERIFIED | Canonical reducer and ORM write regressions |
| 17 | Currency/cohort aggregation | VERIFIED | Mixed/unknown suppression, per-currency groups, no FX inference |
| 18 | AFE/OPEX persistence/metadata | VERIFIED | Atomic replacement/idempotency/OPEX-preservation tests |
| 19 | W16 finance editor and CSV | FIXED-BUT-NOT-ENVIRONMENT-VERIFIED | Per-row currency, NULL, reload, context and CSV subprocess assertions |
| 20 | Projection assumptions vs actuals | VERIFIED | Explicit denomination and zero rate; separate report values |
| 21 | Economic return/payroll engine | NOT-APPLICABLE | No such implemented engine established; not invented |
| 22 | Operational time/partial denominators | VERIFIED | Shared reducer and inherited cross-consumer tests |
| 23 | ROP/weighted ROP/current observations | VERIFIED | Explicit zero preserved; weighted-pair regression suite |
| 24 | Deterministic engineering engines | VERIFIED | Existing numerical regression suite rerun |
| 25 | Engineering dialogs/adapters/native UI | FIXED-BUT-NOT-ENVIRONMENT-VERIFIED | Subprocess/source tests; no native shipping-platform acceptance |
| 26 | Engineering persistence/snapshots/aliasing | VERIFIED | Persistence, reopening and immutable historical snapshot regressions |
| 27 | Dirty-save/partial failure lifecycle | VERIFIED | Existing explicit SaveOutcome and preservation tests |
| 28 | Permission failure/write boundaries | VERIFIED | Base/hierarchy failure injection, W16 fail closed, W8 child denial |
| 29 | Credentials/bootstrap/startup import | VERIFIED | Policy regressions plus actual repaired source entrypoint |
| 30 | Backup failure preservation | VERIFIED | Atomic destination replacement and injected-failure test |
| 31 | Migration/production DB acceptance | BLOCKED | Isolated migration tests pass; real approved DB unavailable |
| 32 | DDR/Excel deterministic extraction | VERIFIED | Actual tracked workbook opt-in + regression suite |
| 33 | Import→IR→normalize→review→explicit DB save | PARTIAL | Workbook and synthetic adapter contracts tested; real MinerU PDF path blocked |
| 34 | Real PDF asset existence/readability | VERIFIED | Preserved unique blob, hash, four-page PyMuPDF inspection |
| 35 | MinerU real integration | BLOCKED | No external engine; explicit test environment-blocked |
| 36 | AI orchestration/optional capability detection | PARTIAL | Offline/source contracts; no actual external model/service acceptance |
| 37 | Cost/EOWR/NPT/Plan HTML and Excel | VERIFIED | Currency-aware source outputs, raw rows, null-safe totals and report tests |
| 38 | Real production PDF output/rendering | PARTIAL | Source export tests ≠ native production document/layout acceptance |
| 39 | Security boundaries overall | PARTIAL | Named permission/credential repairs tested; not a comprehensive penetration audit |
| 40 | Exact dependencies/platform support | PARTIAL | Exact 3.11 executed; 3.12/3.13 resolution only; 3.10 exact lock fails |
| 41 | Release gate/test integrity | VERIFIED | Meaningful imports/entrypoint, accounting, negative controls, version and resources |
| 42 | Hosted CI | BLOCKED | No qualifying repaired-SHA remote run |
| 43 | Wheel/source packaging | VERIFIED | Actual built wheel inspected |
| 44 | Windows spec/installer/runtime/data preservation | BLOCKED | Static review only; no Windows execution |
| 45 | Documentation/evidence identity | VERIFIED | Tested implementation separated from certificate commit and remote target |
| 46 | Dead code/cleanup hygiene | PARTIAL | Import removals audited; no speculative deletions or exhaustive dead-code claim |

### Explicit A–H blockers requested by the mission

- **A Currency:** named summation/relabeling/NULL bugs **closed** in audited paths; no remaining FX assumption is asserted.
- **B Plan NULL:** named scalar/canonical/activity/DB defects **closed**.
- **C Safety:** named no-record/default/stale-context/permission defects **closed**.
- **D CI:** **blocked** by publication permission and absent qualifying hosted run.
- **E Windows:** **blocked**, no actual runtime/installer acceptance.
- **F MinerU:** **blocked**, external engine unavailable.
- **G Real DDR/Excel/PDF:** actual repository XLSX narrow acceptance **passed**; real PDF exists and is readable, but MinerU/production PDF acceptance **blocked/partial**.
- **H Production DB:** **blocked**, approved asset unavailable.
- **Additional:** exhaustive semantic adjudication of remaining risky legacy sites is **partial**, preventing a claim of full mission-wide forensic closure.

## G. Verdict

**NOT RELEASE-CERTIFIABLE**

The final clean source gate is genuinely green at `e83fc3ec85447446e50b4dd2acbc64169d07f054`; the listed financial, plan, safety, startup, permission, backup and test-contract defects are repaired and committed. This does not fulfill the exhaustive audit/production acceptance standard requested in Mission 28. Publication/CI, native Windows/installer, actual MinerU PDF processing, approved production DB acceptance and remaining semantic adjudication are not verified.

Do not substitute older certificate text, branch-tip names, successful historical dynamic actions, synthetic bundle files, dry-run dependency resolution or these local source results for the missing evidence. The repair patch preserves the work despite the GitHub permission limitation.
