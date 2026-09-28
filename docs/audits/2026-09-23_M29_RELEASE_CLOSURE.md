> **HISTORICAL MISSION RECORD (Mission 29).** This file is preserved unedited as the evidence it produced. Its counts, hashes and verdicts describe the tree at that time and are superseded by the Mission 33 re-adjudication — see [M33_SEMANTIC_AUDIT.md](../../M33_SEMANTIC_AUDIT.md) and [M33_RELEASE_CERTIFICATION.md](../../M33_RELEASE_CERTIFICATION.md).

# Mission 29 — release closure evidence and incomplete certification audit

Date: **2026-09-23**. Verdict: **NOT RELEASE-CERTIFIABLE**.

**Mission 29 is not complete.** Demonstrated defects were repaired, committed and tested. The final clean **source gate passed**, but the requested exhaustive semantic/consumer audit has not been completed. This is not an external-blockers-only conclusion: **2232 inventoried risky sites remain unadjudicated**. Passing tests, a large inventory, or the matrix below cannot substitute for that work.

- Final tested implementation: **`beaf9635ffb7bcecf16b3320b138077c7ef8e6c8`**.
- Full gate: **1690 collected; 1687 passed; 3 external skips; 0 failed/errors/xfail/xpass/deselected**, pytest **271.79 seconds**, overall command approximately **284.41 seconds**, exit **0**.
- Actual clean-staged build, installed-wheel smoke outside the checkout: **PASS**.
- [69-domain coverage matrix](2026-09-23_M29_DOMAIN_MATRIX.md): explicitly PARTIAL, not 69 certified domains.
- [Evidence directory](m29-evidence/): source fingerprints, 62-model inventory, 118 W10/W11/W12/W16 scope-consumer entries, exact gate output, mutations and publication failure.

Later changes are documentation/audit evidence only. The full run above is attributed to its actual implementation SHA, not to a later evidence commit. Resolve the latest documentation commit with `git log -1 --format=%H -- docs/audits/2026-09-23_M29_RELEASE_CLOSURE.md`.

## A. Git reality

### Local history and publication boundary

All work stayed on **`arena/01a0c945-drill-master`**. The session cannot use the requested target branch as its working branch. No branch was deleted, switched to or created.

| Object | Independently established meaning |
|---|---|
| `c28bbef37cbac9de7abcfa693e7e21f678fa74ab` | Requested target's starting identity, established during initial Git verification; the original certification commit, not the independent repairs. |
| `0bbcbd4` | Not available after the initial fetch/object investigation. Original ancestry cannot be reconstructed from a commit message. |
| `2e73747e5507b22587436005e4906b49a46510ee` | Preserved the recovered M28 content after matching its **348-entry historical source manifest**. Recovery changes **83 files**, 20133 insertions / 820 deletions relative to `c28bbef`. |
| `8a20cb90b68bacb6c69e3cdf6e8303d4a009e599` | First M29 implementation/evidence commit. The subsequent full run failed two obsolete omitted-depth assertions; that failure is retained. |
| `2bdc25d116c0f1fd9aabce0962f8e983b7375235` | Corrected those two assertions to NULL, retaining the separate explicit-zero test. A clean source gate passed at this intermediate SHA, but its 1678-pass count is superseded. |
| `beaf9635ffb7bcecf16b3320b138077c7ef8e6c8` | Final application/test fixes, including calendar ambiguity, directional mud facts, atomic metadata and truthful chart/export failures. Final full gate identity. |

Recovery applicability and hash agreement prove content/provenance consistency, **not correctness or availability of the original `0bbcbd4` object**. The recovery-file inventory records the 83 changed paths individually.

Publication was actually attempted with `git push origin arena/01a0c945-drill-master`. It failed, exit **128**:

```
fatal: could not read Username for 'https://github.com': terminal prompts disabled
```

A fresh `gh api` request returned **HTTP 401, Bad credentials**. GitHub must be reconnected in Arena. No remote update or hosted CI success is claimed. The older workflow-permission denial in M28 is historical; it is **not** substituted for this current authentication failure. Current remote heads/Actions outcomes cannot be independently refreshed while authentication is broken.

### Branch content classification

`branch-inventory.json` records local/cached ref identities and ancestry. Network freshness is unavailable at closure.

- Session branch and requested target reference: **ACTIVE** for this work/target, retained.
- Cached `origin/arena/01a056c5-drill-master`, `01a05747`, `01a07094`, `01a0801f`: **MERGED-SAFE-TO-DELETE by local ancestry only**; no unique reachable commits relative to the implementation. No deletion was performed or recommended without refreshing remote reality.
- `drill-Master`, `origin/drill-Master`, and its cached `origin/HEAD` alias: **UNMERGED-REVIEW-REQUIRED**. Three commits are outside session ancestry: two merges and upload `02053eb`. `git cherry` identifies the upload as the unique nonmerge patch. The three-dot content diff is the **740510-byte real DDR PDF**, not unique application code. That document is useful acceptance input and was retained/extracted separately, not blindly discarded or merged as code.
- Unobserved remote changes: **UNKNOWN**, not inferred from cached refs.

## B. Independent M28 patch verification

M28 was a starting point, not a certificate. Its recovery was checked against the historical manifest, then its live contracts were exercised again by the fresh suite and targeted negative controls.

| Boundary | Current evidence | Limit |
|---|---|---|
| Finance/currency/NULL | `test_cost_truth_boundary`, `test_m28_finance_safety_plan`, M29 AFE/no-DDR regressions; currency mutation fails | Does not certify every fiscal category or exporter. |
| Plan truth | Scalar and persisted **11-pair** M29 matrix; planning UI subprocess | Reducer parity alone does not certify all consumers. |
| Safety | Absence/zero/latest-assessment tests; zero-on-absence mutation fails | Every report/export safety path still needs individual closure. |
| W8 permissions | Recovered save guards and permission regressions re-executed | Entire application action matrix is not complete. |
| W16/report money | Cost-widget and report scope/currency tests re-executed | No FX, payroll, tax or revenue engine is implied. |
| Entrypoint re-export | Actual source package-smoke consumer; removal mutation fails | Native frozen runtime is a different boundary. |
| Backup | Failure preserves existing destination; false-success mutation fails | Production-size and complete restore fault matrix remain unaccepted. |
| Gate | Strict accounting tests and actual final clean gate | Source gate is intentionally narrower than semantic certification. |

Original cleanup/certification history (`95dd631`, `c28bbef`) must not be conflated with the independently recovered repair content. No claim that a successful patch application proves those repairs correct is made.

## C. New findings, causes and impact

The following are repaired findings, not open defects. P1 denotes integrity/authority/false-fact risk; P2 denotes significant UI, packaging or failure-reporting risk. Source paths and function boundaries identify the affected code; regression detail is in section D and the changed tests.

| ID | Severity | File / function boundary | Root cause and impact | Evidence / repair |
|---|---|---|---|---|
| M29-01 | P1 | `core/database.py`, auxiliary ownership checks and stored-ownership validation | Auxiliary section/plan ownership could contradict well authority, including relationship/parent changes. | ORM/FK/parent guards and startup rejection; parameterized mapped-model adversarial tests. |
| M29-02 | P1 | `main_window.py:_check_delete_permission`, `core/hierarchy_operations.py:check_delete_permission` | Generic/failing permission lookup could authorize the wrong destructive entity. | Entity-specific, fail-closed permission checks; deliberate permission-service failure test. |
| M29-03 | P1 | `core/database.py`, physical/plan observation columns and services | Numeric defaults fabricated measured zero, including an unrecorded header hiding genuine parameter ROP. | Nullable omitted measurements; header/parameter ROP, trip NULL, persisted plan and schematic regressions. Existing rows were not blindly backfilled. |
| M29-04 | P1 | `dialogs/planning_dialog.py`, edit/save/import staging | `or` defaults, incomplete activity dates and inferred import values collapsed unknown/zero or staged partial input. | Nullable editors, zero retention, required schedule review, atomic in-memory staging and unknown phase/depth preservation. |
| M29-05 | P1 | `core/actual_vs_plan.py`, W10/W12 milestone consumers | Incomplete plans and duration-derived actuals could become manufactured totals/comparisons. | Shared comparison/complete-input rules and eleven scalar/persisted pairs. |
| M29-06 | P1 | `tabs/w10_Planning_Widget.py:MaterialInventoryTab` | Name-only selection and ambiguous row identity could affect the wrong unit/scope; NULL stock collapsed. | Hidden persisted IDs, qualified identity, unknown stock, explicit no-movement convention and permission tests. |
| M29-07 | P1 | `tabs/w10_Planning_Widget.py:NPTReportTab`, code/status readers | Report/section filtering and incomplete durations could yield misleading scope/totals. | Qualified queries, shared time semantics and nullable displays; scope mutation fails. |
| M29-08 | P1 | `tabs/w12_Analysis.py:get_today_data` | Arbitrary latest-day selection and manufactured directional mud/“Drilling” facts. | Unique 0/1/2+ selection; generic sample `mud_weight` separate from explicit header inlet/outlet; unsupported activity remains unknown. |
| M29-09 | P1 | `tabs/w12_Analysis.py:calculate_kpis`, `get_time_depth_data`, `analyze_rop_prediction` | Observation ordinals treated as elapsed days; endpoint `.first()` hid ambiguity; interval changes labelled daily gain. | Calendar gaps, unique same-bore endpoints, no canonical unknown/zero fallback, interval-change labels, finite-input/assumption checks. |
| M29-10 | P1 | `core/operations_intelligence.py`, `core/cost_semantics.py` | No-DDR early return concealed genuine costs/safety; legacy summaries bypassed money truth; report counts confused with duration-derived days. | Independent evidence preserved, common currency/NULL contract, explicit recorded-report versus hour-derived-day labels. |
| M29-11 | P1 | `core/database.py`, snapshot create/restore | Nested mutable values were not sufficiently isolated and an absent restoration target could claim success. | Deep-copy boundaries, missing-target failure and mutation-sensitive restoration regression. |
| M29-12 | P1 | `core/hierarchy_operations.py`, next-day copying | Dates, explicit zero closing stock and safety assessment could be carried incorrectly. | Target-date/zero-stock handling and no fabricated next-day assessment. This is not the same contract as a revision snapshot. |
| M29-13 | P1 | `core/ddr_import_service.py`, identity resolution | Normalized identity collision could silently choose authority. | Collision rejection rather than guessed match; import/identity regressions re-executed. All normalization paths are not thereby certified. |
| M29-14 | P2 | `tabs/w6_Trajectory_Widget.py:TripSheetTab` | Invalid time replaced with current time; blank measurements and hidden-ID alignment corrupted input meaning. | Invalid time fails; NULL survives; row alignment and legacy payload support; permission guard; cumulative unknown propagation. |
| M29-15 | P2 | W10 material save/delete and chart loaders; W12 milestone failures | Successful durable commit followed by renderer failure was reported as persistence failure; stale charts survived failed refresh. | Commit-aware outcomes and explicit refresh failure; clear failed/no-context charts. Injected renderer regression verifies durable deletion. |
| M29-16 | P2 | `NPTReportTab.export_charts_to_file` | Ignored image-save boolean and PDF painter outcome could log successful export after writer failure. | Check writer outcomes, explicit failure message/False, and negative control. |
| M29-17 | P1 | `core/mapping_store.py`, `core/runtime_config.py:atomic_write_json`, template/learning saves | Direct overwrite risked partial JSON; failed persistence left memory claiming a new mapping revision. | Serialize first, same-directory temporary write/fsync/replace, cleanup, publish memory after success. Fault injection covers serialization/fsync/replace; nested incoming mappings are owned copies. |
| M29-18 | P2 | `dialogs/smart_template_dialog.py`, runtime template paths | Mutable data in application resources, normalization collision or tied template selection could overwrite/choose the wrong configuration. | User-data storage, explicit collisions/ties, visible failed-save outcome and atomic writes. |
| M29-19 | P1 | `verify_release.py` | Weak result accounting/version/resource assertions or stale wheel build sources could certify the wrong execution/package. | Git/lock/version/compile/fatal-lint/collection/JUnit checks and clean tracked-source wheel staging; mutations fail. |
| M29-20 | P1 | `pyproject.toml`, `packaging/DrillMaster.spec`, `packaging/package_smoke.py` | `ui`/template omissions and source-tree shadowing masked incomplete installed packages. | Resources included; real installed smoke outside checkout; removing `ui*` fails both focused test and real staged-wheel gate. |
| M29-21 | P2 | Living documentation and legacy model docstrings | Historical counts/claims and independent legacy models described as current/canonical could mislead certification. | Ten living documents reconciled, historical reports retained, independent unwired legacy Base explicitly documented. |

## D. Fixes, tests, mutations and post-fix review

### Behavioral contracts

The required Plan pairs are **None/None, None/0, 0/None, 0/0, None/100, 100/None, 0/100, 100/0, 100/100, 100/80, 80/100**. Tests cover actual persistence as well as scalar status, variance and percentage. Unknown operands do not become zero; a nonzero actual against a zero plan has no fabricated percentage. Reporting variance orientation is explicitly distinct from money remaining (`planned − actual`).

Safety with no assessment remains **NOT ASSESSED**; an entered zero remains zero. Costs with absent/inconsistent currency do not become one monetary total or presumed USD. **IRR as a currency code means Iranian rial**, not an internal-rate-of-return calculation. No new economic, tax, payroll, revenue or FX model was invented. Category support in a cost table is not a validated fiscal workflow.

Trip cumulative values remain a sum of the entered depth values, with unknown propagation. This audit did not invent a travel-distance reconstruction. Daily header physical observations, trip measurements, NPT cost/delay and actual plan duration are not manufactured by omitted-input ORM defaults.

W12 generic mud sample weight is not evidence for both inlet and outlet. Known header inlet/outlet zero values survive. Calendar regression uses actual gaps: January 1 ROP 0 and January 10 ROP 9 imply a 1.000 m/hr/day fitted slope, with the projection explicitly an assumption. Depth endpoint ambiguity does not pick the first row.

### Negative controls

`mutation-controls.json` records **14 controls**. Each focused test command actually returned **1**, and each altered production file was restored and SHA-256 checked:

currency, NULL Plan, safety, ownership, permission, backup, snapshot, gate accounting, NPT scope, calendar ambiguity, mud direction, failed atomic-memory publication, export return value, and entrypoint re-export.

Separately, removing `ui*` from wheel selection caused **both** its packaging test and the actual clean-source wheel gate to fail, exit **1**. `mutation-wheel.json` records restoration. Mutations were not committed. A positive final full gate ran after restoration and the latest fixes.

### Source re-review boundary

- `source-manifest.json` fingerprints **352** selected tracked source/test/config/build/asset inputs, excluding audit/history and Markdown documentation. Hashes are tied to the final implementation, not assumed from test success.
- AST inventory covers **174** production Python files and **2259** selected risky-pattern sites: 312 reductions, 126 numeric parameter defaults, 348 typed exceptions, 406 numeric `.get` defaults, 619 broad exceptions, 124 numeric keyword defaults, 173 `or zero` expressions, and 151 single-row selections.
- Exactly **27** sites have individual, expression-hashed adjudications. The inventory runner applies those decisions only when the **source-file and expression hashes both match**. Earlier function-wide generic classifications were replaced with explicit reasons.
- **2232 sites remain NOT-REVIEWED.** This syntax inventory also does not enumerate every possible numeric convenience default or dynamically routed consumer. It is not exhaustive semantic closure.
- `model-inventory.json`: **62** canonical mapped models, scope columns, FKs and scalar numeric defaults. This is not 62 individually certified models.
- `scope-consumer-index.json`: **118** source-located W10/W11/W12/W16 methods. W12 aggregate well/bore scope and report-level today scope are distinct; W11/W16 money scope must not be inferred to narrow merely because another tab selected a report.
- Post-fix AST comparison found **no removed production class/function names** relative to recovered M28. This is a removal inventory, not proof of compatibility. `core/db_models.py` and `core/db_services.py` were retained as unwired independent legacy code; they are not canonical aliases and external callers are not exhaustively proven absent.

## E. Remaining repository defects and verification gaps

The full requested repository audit is **not closed**. No claim that residual type A is empty can be made from the current coverage.

| Type | Remaining item | Required closure |
|---|---|---|
| **B — repository verification** | 2232 risky sites, plus syntax/consumer routes outside the selected AST patterns, lack individual semantic adjudication. | Review each source/caller/persistence/export path and fix demonstrated defects; update hash-bound decisions and regressions. |
| **B — repository verification** | W12 complete line-by-line closure and exhaustive W10/W11/W16 scope/ownership matrices are incomplete. | Finish all KPI/chart/forecast/risk/plan/quality/export paths, including failures and ambiguity. Source indexes are not substitutes. |
| **B — repository verification** | Financial categories, units/time bases, all importer normalization/collision paths, and engineering adapters/UI defaults are not individually closed. | Trace each raw input through persistence and all output formats; distinguish unsupported fiscal capabilities from implemented cost tracking. |
| **B — repository verification** | Every Save/Delete/Edit/Import/Export/Reset/Backup/Restore failure and every startup/partial-schema state has not been fault-injected. | Complete action/error and migration matrices, including existing/corrupt/partial files and databases. |
| **B — repository verification** | Next-day copy entrypoint parity/repeat-copy behavior, all snapshot/reference mutations, and external legacy callers remain incompletely adjudicated. | Demonstrate behavior and retain/classify useful code; no blind deletion or authority backfill. |
| **C — documentation integrity** | Living current-status prefaces are corrected, but historical engineering/reference assertions are not all independently recertified. | Retain history while separately completing current source evidence; do not read old “verified” tables as new certification. |
| **D — reproducibility** | Exact runtime lock was installed and checked; build isolation still resolved build tools rather than proving one exact build-tool environment across platforms. | Verify and, only if justified, define reproducible build tooling. No runtime lock was changed merely to match the developer environment. |
| **I — nonblocking debt** | Broad Ruff debt remains; targeted fatal checks pass. Dependency deprecations and large modules remain. | Maintain the ceiling and assess future upgrades/refactors independently; no blind cleanup. |

The table contains genuine unfinished **repository work**, not just external acceptance. It must not be reworded into an external-only release limitation.

## F. External acceptance

| Type | Boundary | Actual state |
|---|---|---|
| **E** | GitHub publication/hosted CI | **ENVIRONMENT-BLOCKED** by current authentication; push exit 128, API 401. Hosted results **NOT VERIFIED**, not assumed absent or successful. |
| **F** | Windows EXE/plugins/DLLs/installer/clean machine | **NOT RUN**. Linux source/installed-wheel and structural packaging tests are not native/frozen acceptance. |
| **G** | Supplied real Excel DDR | **PASS within this input's contract** in the final full gate with `DRILLMASTER_TEST_DDR_XLSX` set. Not general acceptance of all company workbooks. |
| **G** | Real PDF → MinerU → common IR → review → atomic DB | **ENVIRONMENT-BLOCKED**. An actual pipeline attempt failed because MinerU was unavailable/disabled, not because the asset was absent. |
| **H** | Production database upgrade, operator data and field engineering | **NOT RUN / NOT VERIFIED**. Synthetic source tests cannot certify production data or operational use. |

The real PDF is **740510 bytes**, four independently readable pages, SHA-256 **`6ce9b37e4e30c7800191598d9f9febebc12d4cf0ab5932c5d7f6ad1b789a226c`**. Extracted text lengths were 3770/4258/1393/809. Reading it with PyMuPDF is **not** acceptance of the MinerU pipeline. The blocked pipeline attempt and probe are retained in evidence.

## G. Fresh execution and warning accounting

### Final implementation execution

Command:

```bash
QT_STUB_DIR=/home/user/qt-libs \
LD_LIBRARY_PATH=/home/user/qt-libs QT_QPA_PLATFORM=offscreen \
DRILLMASTER_TEST_DDR_XLSX='/home/user/Drill-master/08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx' \
.venv/bin/python verify_release.py \
  --expected-sha beaf9635ffb7bcecf16b3320b138077c7ef8e6c8
```

Environment: **Linux, Python 3.11.2**, exact installed runtime lock; pytest **9.1.1**, Ruff **0.16.6**, build **1.6.1**. Offscreen Qt uses dependency stubs under `/home/user/qt-libs`: that does not demonstrate native GL/Windows support. `environment.json` records the installed freeze and platform.

| Gate | Actual result |
|---|---|
| Expected Git identity, branch, clean worktree and diff checks | PASS at the final implementation SHA |
| Runtime installed versions, lock checks, `pip check` | PASS |
| Application/package version | 1.0.0, consistent |
| Compilation and fatal Ruff E722/F821 | PASS |
| Broad Ruff ceiling | **5334 findings / ceiling 5375** for the established `core dialogs tabs tests` population; not lint-clean |
| Collection and strict test-result accounting | 1690 collected; 1687 passed; 3 skipped; all failure/error/xfail/xpass/deselection counts zero |
| Full pytest | **271.79 s**, **20 captured warnings**, exit 0 |
| Clean staged wheel + install + smoke outside checkout | PASS, actual execution, not only a unit test of the gate |
| Separate fresh isolated production imports | **174 subprocess imports, 0 failures**; optional capabilities are not thereby executed |
| Latest focused regression batch before final gate | **93 passed, 14 warnings, 7.70 s**, exit 0 |

The three skipped test identities are only the declared external cases: real DDR PDF/MinerU, real MinerU integration, and real Windows bundle. Their source-gate classification is SKIPPED-OPTIONAL; their **acceptance classification is NOT-RUN or ENVIRONMENT-BLOCKED**, not PASS. The real Excel acceptance did execute.

A separate post-documentation root-wide Ruff run returned **1**, with **5545 findings**. The established ceiling covers only `core dialogs tabs tests` (still 5334); it must not be applied to a different population or described as root-wide lint cleanliness. Root-wide fatal E722/F821 passed. An initial post-documentation comparison incorrectly compared the root count with the scoped ceiling; the evidence now explicitly separates them, without changing the ceiling or product source.

The earlier failed full gate is retained: 1676 passed, 2 failed, 3 skipped at `8a20cb9`. Both failures asserted the former fabricated omitted-depth zero. The corrected tests assert NULL and retain a separate explicit-zero case. This failure was not hidden or converted into a skip. Older 1658/1678 pass counts are superseded, not current evidence.

### Warnings — every emitted family/context accounted for

| Emission | Count/context | Classification and impact |
|---|---|---|
| openpyxl: data validation extension unsupported and removed | **14**: DDR acceptance 1, follow-up lifecycle 3, forensic regression 1, DDR regression 1, Excel-intelligence regressions 3, golden DDR 1, real OEOC golden 1, review-contract certification 3 | **EXPECTED, with REAL RISK for fidelity-preserving re-save**. Tests read vendor workbooks; source bytes are not intentionally rewritten. Passing numeric extraction does not promise preservation of unsupported Excel validation metadata in a re-export. That unsupported round-trip guarantee is explicitly not made. |
| SWIG `SwigPyPacked` missing `__module__` | **2**, dependency import test | **DEPRECATION** in the installed PDF binding; not an observed parse failure. Future interpreter/dependency compatibility requires its own acceptance. |
| SWIG `SwigPyObject` missing `__module__` | **2**, same dependency import context | **DEPRECATION**, same boundary. |
| SWIG `swigvarlink` missing `__module__` | **1 captured** plus an additional interpreter-shutdown emission after pytest's summary | **DEPRECATION**; shutdown emission is not silently added to the captured-warning count. |
| Project large-file warning | **1**: `main_window.py`, `core/database.py`, W12 and W13 exceed 3000 lines | **EXPECTED technical debt**, not runtime failure and not justification for blind refactoring. |
| Pyparsing deprecated `oneOf`, `parseString`, `resetCache`, `enablePackrat` via Matplotlib | Focused batch **1 + 6 + 6 + 1 = 14**, separately from the final full suite's 20 | **DEPRECATION** in pinned dependency interaction. Current tested rendering works; no lock change was made solely to remove warning noise. |

Full run and focused run counts refer to separate executions. No blanket “warnings harmless” or warning-free claim is made.

## H. Verdict

**NOT RELEASE-CERTIFIABLE**

### REPOSITORY BLOCKERS

The required exhaustive individual semantic/source/consumer review, complete scope/failure matrices and related reproducibility closure remain unfinished. The most concrete quantitative boundary is **2232 NOT-REVIEWED risky sites**, not a claim that they are safe. The 69-domain matrix and passing 1690-item collection demonstrate coverage and progress, not completion.

### EXTERNAL ACCEPTANCE BLOCKERS

GitHub reconnection/publication and observed CI, clean Windows frozen/installer execution, real MinerU PDF pipeline acceptance, and production database/field acceptance.

### NON-BLOCKING LIMITATIONS

Known lint/size debt and documented dependency deprecations; optional capabilities outside demonstrated acceptance; no byte-for-byte vendor-workbook validation-metadata preservation; no invented fiscal/FX model.

All demonstrated repairs are committed locally. Publication is not claimed. A cumulative binary-capable patch from the exact `c28bbef` base is provided separately, with an index-application/tree-equivalence check. That check proves applicability, not semantic certification. The next work is to finish the repository adjudication and fix further demonstrated defects before seeking an external-only conclusion.
