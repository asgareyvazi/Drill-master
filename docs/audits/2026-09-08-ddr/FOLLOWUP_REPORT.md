# DDR lifecycle follow-up — final verification report

**Date:** 2026-09-08
**Decision: NOT PRODUCTION CERTIFIED**
**Evidence-weighted score: 70/100**

This is the current report for the follow-up to **`eb8041de79d44f6ac6099ca84e569116af0d617c`**. The older `REPORT.md` and `evidence/golden-a.json` remain historical baseline evidence. Implemented fixes and successful headless acceptance are not equivalent to native desktop certification. Several requested manual/desktop gates remain incomplete.

## 1. Repository, preservation and environment

- Repository: `asgareyvazi/Drill-master`.
- Fixed session branch: **`arena/01a0801f-drill-master`**. No reset, branch switch, cherry-pick or recreation of previous work was used.
- Authoritative baseline: **`eb8041de79d44f6ac6099ca84e569116af0d617c`**. The prior 56-file remediation remains in the ancestry. This follow-up extends it; regression evidence below tests the combined result.
- Execution: **Python 3.11.2**, Linux x86-64 / glibc 2.36, SQLite, SQLAlchemy, openpyxl and existing engineering engines.
- The final implementation revision is the commit containing this report. Its exact SHA and remote push verification are returned in the completion message; a report cannot embed its own Git commit hash without changing that hash.
- No verification databases are committed. Reproducible scripts and compact JSON, text, JUnit and one actual Agg-rendered image are under `evidence/followup/`.

Architecture was traced before remediation in [FOLLOWUP_INSPECTION.md](FOLLOWUP_INSPECTION.md), including source/extraction/canonical/domain/DB/repository/widget/edit/save/reload/engineering/visualization, and an inventory of 498 lifecycle/query methods. Subsequent inspection additionally found Main Window aggregation, cache-only equipment saves, planning snapshot/date handling, and chemical balance defects.

## 2. Root causes and implemented repairs

| Area | Root cause | Repair / regression evidence |
|---|---|---|
| Runtime outcomes / Main Window | Truthy counts or one successful child could yield a global success notification; false/None results lost section context | `core/save_outcome.py` defines SUCCESS, REVIEW_REQUIRED, INVALID_SOURCE, UNSUPPORTED and SYSTEM_ERROR, retains section/row/field/reason/action and exception traceback, and aggregates independently committed operations honestly. Main Window and W3/W4/W5/W6/W7/W8/W9/W10 paths use it. Actual Main Window method is executed with protocol fakes in a headless test; this is not a Qt click test. |
| Import status | Legacy ACCEPT / VALIDATION_ERROR / PERSISTENCE_ERROR could be confused with source review states | Additive `outcome_status` bridge on import diagnostics, service results and serialized ReviewItems. Legacy status fields remain compatible. The six causal audit categories are deliberately separate. |
| Collections / safety | JSON `null`, blank collections and invalid shapes were inconsistent; replacing a partially invalid BOP/waste collection could delete stored children | `collection_value`: None/JSON null/blank/[] → []; invalid non-list/non-record shape → exception. Failed queries are not converted to an empty dataset. Safety validates before replacing, keeps rejected typed and legacy collections, and scopes child reload to the selected safety report. Explicit [] clears are supported. |
| POB | Add seeded today's dates; partial saves could announce success before rejected rows; partial remark updates could clear existing dates | Blank Add dates, shared validation and aggregate diagnostics, no `None` string parsing as a real date, preserve omitted date fields on patch updates, reject invalid/negative personnel counts. Date-in/date-out semantics are preserved; complete planned-versus-actual native workflows are not certified. |
| Density | Explicit PCF source evidence was overridden by a ppg template hint; normalized review magnitude was forced to NULL; non-PCF conversion targeted the wrong native unit | Explicit unit resolution retains 71 PCF and its lineage without a unit review. `mud_density_pcf` uses the existing UnitManager to target the PCF-native model/widget. Supported explicit-unit variants are regression-tested; unresolved units must still be reviewed. |
| Mud edits | Numeric/time widget placeholders could become source measurements; same-value zero edits could go undetected | Separate loaded source, displayed value and user-touched state; text-edit tracking supplements numeric valueChanged; actual sample time is loaded, absent time remains NULL on unchanged save. This is implemented but native signal behavior is not certified. |
| Chemicals / inventory balance | Provenance and callbacks captured row ordinals; Add invented a product/unit/zero quantities; closing stock was recomputed as received-used with no opening balance | Stable product-widget row ownership; blank Add values; hidden source provenance; explicit current stock entry. The existing ChemicalLedgerEntry is used only when opening/received/used/returned/adjusted are supplied. Derived balance is separate and cannot overwrite source/current stock. A received edit keeps original closing stock and untouched chemicals. |
| Scalar extraction | Nearby weather and Received Items labels could masquerade as measurements/text values | General label-boundary recognition. Weather values remain genuinely missing; their reviews are reclassified rather than suppressed. |
| Formula-only narrative | Whitespace plus a formula-only duration produced a phantom morning continuation and literal `None` description | Whitespace is excluded from content classification; formula-only rows remain in raw IR but do not become operational narrative/review rows. Generalized structural regression added. |
| BHA / downhole / formation | Repository bypass, inconsistent named projection, last-row deletion not saved, and stale cumulative lengths; formation Add invented TVD from MD | Shared named adapters, BHA repository delegation, explicit empty snapshot saves; retain unchanged source cumulative anchors and recompute edited lengths using the existing path. Hidden Qt.UserRole provenance was already present and was preserved. Formation does not infer TVD from MD. |
| Survey / engineering | MD-as-identity caused edit/delete/context problems; Add fabricated measurements; one invalid row blocked all useful diagnostics | Stable IDs plus scoped snapshot deletion and collision validation; blank Add; row-level numeric/review handling; existing minimum-curvature calculator reused. Source angles are not derived values. Missing angles remain NULL. Survey edit audit is associated with its report when the batch has one report context. |
| Equipment | Single-tab Save wrote only an in-memory cache; repeat Save could insert duplicates; row deletion was not an authoritative DB snapshot | Single-tab and aggregate paths converge on report/type-scoped `save_equipment_records`, which delegates to `save_equipment_log` in an owned transaction. Stable IDs/natural identity checks, explicit snapshot deletion/clear, invalid-hour validation, and rollback tests. No duplicate engine or table schema was introduced. |
| Planning | Save generated dates from today, load displayed only seven positions despite eleven imported rows, and parent announced success without checking persistence | Load every actual row and attach source/ID data; save explicit dates, preserve actual timestamps, update IDs, support snapshot clear/delete, and inhibit deletion if rows are invalid. Parent receives the actual structured outcome. |
| Services | Dialog-immediate persistence was represented as a fictitious pending batch | Zero-pending SaveOutcome is propagated; existing record dialogs remain the persistence path. |
| Visualization | Unverified rendering and stale/error-prone presentation could be mistaken for engineering failure | The actual W6 3D drawing boundary is factored into Qt-free `draw_trajectory_3d`, using only finite, complete, calculated stations. The same function executes on Agg. `TrajectoryPlotTab.load_for_report` was inspected and **does exist**; it sets report context and calls `load_plots`. No substitute engineering engine or fake trajectory point is used. |
| DrillPipe resource | Optional vendor lookup messaging did not clearly distinguish reference availability from independent calculations | Existing canonical search order retained: configured `DRILLMASTER_DRILLPIPE_PATH`, application data directory, packaged resources/data and legacy application locations. UI now gives the same actionable optional-reference explanation. Expected vendor sheet is `Aa`; this is a reference adapter, not an operational DDR dependency. |

**Prior `show_warning` runtime defect:** `MudReportTab` is a plain QWidget, not a DrillTabBase, so calling the base-tab warning method there was invalid. The prior repair using `QMessageBox.warning` is preserved. `StatusBarManager.show_warning` (`core/managers.py`) and `DrillTabBase.show_warning` exist for their actual owners; the new validator-to-outcome bridge also propagates warnings to Save All. Native warning-dialog interaction remains unverified.

**Transaction boundary:** import remains atomic. Survey, equipment and planning snapshots own their respective transactions. Safety child synchronization participates in its parent transaction. **Main Window Save All is not one transaction across all tabs**; it reports accepted work and unresolved/failed work rather than falsely promising rollback or complete success.

## 3. Individual classification of all 65 original reviews

The complete per-item table includes source file/cell/row, canonical field, original and prior normalized value, current domain destination/value, reason, source sufficiency, deterministic auto-resolution possibility, genuine user need, and current disposition:

- [REVIEW_CLASSIFICATION_65.md](REVIEW_CLASSIFICATION_65.md)
- [review-classification-65.csv](review-classification-65.csv)

| Exact causal category | Original cohort count |
|---|---:|
| EXPECTED_MISSING_SOURCE | 24 |
| VALID_REVIEW_REQUIRED | 15 |
| IMPORTER_DEFECT | 4 |
| MAPPING_DEFECT | 1 |
| UNSUPPORTED_SOURCE_FEATURE | 21 |
| SYSTEM_ERROR | 0 |
| **Total** | **65** |

Current actual A import has **64 reviews**, not a blanket reduction: known density resolved **−1**, phantom formula/whitespace continuation removed **−1**, previously misread Received Items heading correctly exposed as missing **+1**. Three weather-label defects become three legitimate missing-source reviews, net zero. Current causal distribution is 28 expected missing, 15 valid review, 21 unsupported feature.

The unsupported group contains two coordinate-reference issues and nineteen products whose described roles are not supported by the current six-role chemical catalogue. Five other unmatched chemicals need role/vendor disambiguation. The existing catalogue and `core/combo_identity.py` are reused; no arbitrary default or invented category is assigned. There are still **34 chemical records: 10 mapped and 24 unclassified**. Names, units, stocks and provenance are retained. “Unclassified” does not mean the inventory row was lost.

## 4. Actual Golden A — executed lifecycle evidence

File: `08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx`
SHA-256: **`37a6d96a6f154a9583590f52f9fb7cd92630f01d0a2abec2a9424877c1e4ef7a`**.

Reproducible runner: `tools/certify_ddr_lifecycle.py WORKBOOK --output NEW_DIRECTORY`. It refuses to reuse its import verification database. It uses actual import/domain/database services, not stubbed persistence.

Executed sequence:

1. Fresh DB, formula and cached workbooks, raw IR, canonical extraction, normalized import and atomic persistence.
2. Capture all 23 model snapshots, close engine, create a new DatabaseManager, reload, then repeat source import without duplication.
3. Prepare explicit verification edits through service boundaries: drilling bit number, mud summary and one received quantity, BHA/downhole remarks, formation description, POB remarks, equipment notes, service-company description, lookahead remarks, safety observation; resave real survey source values and fuel/water.
4. Execute the **actual shared Save All coordinator with actual service callbacks**, then close/reopen and verify edits, source NULLs, quantities, dates, record counts and retained provenance.
5. Recalculate through the existing survey path; obtain real chart inputs; render the actual shared 3D no-complete-stations state on Agg.
6. Import the original file into a **separate clean context** and compare with the original imported snapshot, excluding only generated IDs/context IDs and created/updated timestamps, not source measurements.

**This does not execute native tab editors or a native Save All button.** Main Window aggregation has a separate protocol-level method test. Neither is claimed as a desktop end-to-end acceptance run.

| Evidence | Result |
|---|---|
| Service extraction | 17 tables, 147 extracted rows, 43 scanner rejections |
| Atomic import | 101 aggregate accepted operations, **0 failed**, **64 reviews** |
| Persisted snapshot | **65 SQL rows across 23 inspected model types**; JSON children are counted separately |
| Initial close/reopen | Equal |
| Repeated source import | Equal, no duplicate operational rows |
| Service-level Save All | **REVIEW_REQUIRED**, 32 accepted operation/row returns, 28 issues: partial mud composition, 24 chemical categories, 3 missing azimuths |
| Edit → close → reopen | Equal to edited snapshot |
| Clean source replay | Semantically equal to original import |
| Survey / 3D | 3 measured stations; 0 complete calculated stations; empty geometry series; rendered **INSUFFICIENT_DATA** state |
| Native Save All / widgets / 2D-3D windows | **NOT VERIFIED** |

A direct recount of the evidence dictionary confirms **23 inspected model types**, correcting the earlier narrative count of 24; the SQL row total remains 65. Well/context and audit rows are outside that operational snapshot.

Operation counts are not SQL row counts and are not the number of tabs. Scanner rejections are not transaction failures. The cached-only extractor test has 10 scanner rejections, whereas the service opens formula and cached workbooks and reports 43; these are different extraction modes, not conflicting persistence counts.

Persisted rows: DailyReport 1; TimeLog24H 7; TimeLogMorning 6; MudReport 1; DrillingParameters 1; SurveyPoint 3; BHAReport 1 (9 components); DownholeEquipment 1 (3 records); FormationReport 1; POB 6 (total 130); BOP 5; Waste 0; FuelWater 1; BulkMaterials 0; ServiceCompany 6; Lookahead 11; EquipmentLog 9; Casing 1; Cement 1 (9 additives); TimeDepth 1; NPT 0; Safety 1; MaterialRequest 1. These counts remain after the selected edits.

Artifacts: [golden-a-import.json](evidence/followup/golden-a-import.json), [golden-a-lifecycle.json](evidence/followup/golden-a-lifecycle.json), [acceptance.txt](evidence/followup/acceptance.txt), [golden-a-3d-state.png](evidence/followup/golden-a-3d-state.png). JSON is authoritative for individual values and statuses.

**Golden B: NOT AVAILABLE / NOT VERIFIED.** No synthetic variation or controlled edit is presented as a second real workbook. The unexecuted PDF is not substituted for B.

## 5. Mud percentages, engineering and identity

- Actual A provides solids **7%**. The combined Oil/Water token **5** is ambiguous, so both phase percentages remain NULL. **7 is a partial known subtotal, not an invalid complete composition and not a reason to invent 93% water.**
- Totals such as **12** or **17** can result from summing partial/staged/displayed values. Their magnitude alone does not establish a complete mixture. If any constituent is missing, the state is partial; if all are explicitly supplied but disagree with approximately 100%, the existing validator warns about inconsistency; malformed numeric values are invalid source. No balancing phase is fabricated.
- Source, user-entered, derived and display values are kept distinct at the repaired boundary. Widget zero is not automatically source zero. Chemical stock is not derived from incomplete movement data.
- A survey MD values are **50 / 108 / 146 m**, inclination **0 / 0.25 / 0.25°**, azimuth **NULL / NULL / NULL**. The established minimum-curvature engine cannot produce a complete directional trajectory from these inputs without inventing angles. Zero calculated rows and the insufficient-data plot are the correct result.
- Complete controlled survey fixtures verify the existing calculator, saved derived fields, finite chart arrays and the shared 3D draw function. Those fixtures are **not Golden B**. Native pyqtgraph 2D and Qt Matplotlib canvases remain unverified.
- BHA untouched source cumulative anchors survive; edited-length fixtures verify recalculation. Formation retains source MD and does not invent TVD. Full arbitrary partial-assembly engineering behavior is not certified.
- Combo identities use semantic itemData/catalogue resolution, including documented DDR ordinal rules; arbitrary numeric Qt indices and first-item fallback are not accepted identities. NPT activation, NPT code and attributed company remain separate. Existing NPT regressions pass; native checkbox signal order and dedicated W10 NPT CRUD are not proven by those tests.

## 6. Manual lifecycle coverage and remaining work

[MANUAL_LIFECYCLE_MATRIX.md](MANUAL_LIFECYCLE_MATRIX.md) and [manual-lifecycle-matrix.csv](manual-lifecycle-matrix.csv) enumerate **26 section groups**, with Import/Add/Edit/Delete/Save/Reload/Tested and limitations. “Handler exists” is not labeled “GUI verified.”

Key remaining gaps:

1. Native desktop Import → widget population → edits → Add/Delete → Save All → reload → calculation → charts was **not executable** here. This is a critical gate, not waived by passing pytest.
2. Not every manual CRUD path has a new service-level acceptance cycle: trip sheets, crew/transport, standalone bulk inventory, all casing/cement/tally variants, material/service dialogs, NPT dialogs and peripheral procedures/cost/reference modules remain partial or inspection-only.
3. Native null/dirty-state behavior, date semantics in every planned/actual POB workflow, all unshown equipment fields and arbitrary BHA partial-anchor cases need further execution. Older bulk-ledger carry-forward/default semantics are not recertified by the new chemical balance boundary.
4. Some legacy scalar CRUD callbacks still log and return failure without a detailed domain exception. The coordinator classifies missing confirmation as SYSTEM_ERROR and does not report success, but that is not full remediation of every legacy diagnostic path.
5. Unknown coordinate CRS and unsupported/ambiguous chemical roles remain unresolved. They must not be auto-guessed merely to reduce review counts.
6. Real desktop exports, real PDF/MinerU integration, packaged optional-reference behavior and Windows/Python 3.12 remain unverified.

## 7. Tests and strongest actual runtime attempt

All final pytest runs used `QT_QPA_PLATFORM=offscreen`, `-p no:pytest-qt`, and the real XLSX acceptance environment variable. No existing test was deleted or disabled by this change. The Qt plugin is disabled because native Qt cannot import on this host, not to claim GUI coverage.

| Run | Collected | Passed | Failed | Errors | Skipped | Warnings | Elapsed |
|---|---:|---:|---:|---:|---:|---:|---:|
| Fresh authoritative baseline | 616 | 609 | 0 | 0 | 7 | 12 | 85.08 s |
| Final focused follow-up file | 46 | 46 | 0 | 0 | 0 | 3 | 28.48 s |
| Final subsystem | 165 | 164 | 0 | 0 | 1 | 12 | 89.55 s |
| **Final full suite** | **662** | **655** | **0** | **0** | **7** | **15** | **111.31 s** |

Logs and JUnit XML are in `evidence/followup/`. The full suite adds 46 follow-up tests over baseline. Compilation of changed application modules and Ruff undefined-name checks passed; new modules/tests/tool also pass Ruff F checks. `git diff --check` is clean.

An earlier subsystem run had 151 passed / 3 failed / 1 skipped. The failures were old golden expectations: treating every source token as a review, assuming every non-pending token normalized to NULL, and counting labels as detected source values. Tests now explicitly assert resolved unit lineage, missing Received Items, and the corrected counts, alongside new structural regressions. Legitimate review assertions were not removed. Intermediate new-test/harness mistakes were corrected before the final evidence: the survey structured API is `save_survey_records`, and manual safety reload must use `get_safety_report`'s authoritative typed-child projection, not the nullable legacy ORM cache.

Seven final skips are explicit:

- Real DDR PDF: `DRILLMASTER_TEST_DDR_PDF` absent.
- Qt report cost path: libGL unavailable.
- Native nozzle UI boundary: libGL unavailable.
- Real MinerU integration input/install absent.
- Windows bundle unavailable.
- Full native core import sweep: Qt/libGL unavailable.
- Native circular-import sweep: Qt/libGL unavailable.

Warnings are openpyxl's unsupported data-validation extension and the existing oversized-file warning. They are not suppressed or counted as successful native execution.

Actual desktop startup was attempted before and after the changes with `run.py`; it fails importing PySide6 at **`ImportError: libGL.so.1`**, before the application window exists. Inspection also found EGL/xkbcommon/dbus unavailable; HTTP/HTTPS package recovery failed. See [desktop-startup.txt](evidence/followup/desktop-startup.txt) and `system-libraries.txt`. No fake GUI success or Windows inference is made.

**Windows / Python 3.12: NOT VERIFIED. Packaged desktop: NOT VERIFIED.**

## 8. Gates A–J

| Gate | Status | Evidence / blocker |
|---|---|---|
| A — import | PASS for actual A, limited generalization | Atomic A import, raw IR, isolated source review, clean replay. No B; unsupported source features remain explicit. |
| B — persistence | PASS within tested boundaries | Reopen/replay equality; selected service edits; per-snapshot atomicity. Not an all-tab transaction claim. |
| C — manual lifecycle | **PARTIAL / critical unverified** | Repaired and exercised service paths, but 26-group matrix is not a full native CRUD run. |
| D — engineering | PARTIAL | Existing engine and complete fixtures verified; actual A correctly insufficient for directional geometry. Broader native engineering sequence unverified. |
| E — visualization | **PARTIAL / critical unverified** | Actual shared 3D Agg boundary and chart inputs verified; native 2D/3D interaction not executed. |
| F — provenance | PARTIAL PASS | Raw IR/import audit retained; named adapters and row-bound provenance tested. Every native edit/export path not proven. |
| G — missingness | PARTIAL PASS | NULL/unit/collection/empty/rejected cases tested; native widget behavior across all sections remains unverified. |
| H — error handling | PARTIAL PASS | Shared actionable outcomes, no false aggregate success, source failure isolation. Some legacy failure-only callbacks remain. |
| I — regression | PASS for executed environment | 655 passed, 0 failed, 0 errors, 7 documented skips. |
| J — platform | **BLOCKED / critical unverified** | Native Linux Qt blocked; Windows/Python 3.12/package not executed. |

## 9. Transparent score and decision

| Category | Earned / available | Deduction rationale |
|---|---:|---|
| Import | 17 / 20 | One actual workbook; unsupported catalogue/CRS coverage and no second-source verification |
| Persistence | 14 / 15 | Strong source/reload/snapshot evidence, but not every legacy manual route certified |
| Manual lifecycle | 7 / 15 | Selected service CRUD verified; full native and several peripheral CRUD paths incomplete |
| Engineering | 12 / 15 | Existing-engine tests pass; real A lacks complete directional inputs and broad desktop calculation verification |
| UI / visualization | 3 / 10 | Real data boundary and shared Agg rendering only; native widgets unverified |
| Error handling | 8 / 10 | Coordinated outcomes fixed; remaining legacy diagnostic granularity |
| Regression | 9 / 10 | Full Linux headless suite passes; seven excluded integration/platform cases |
| Platform | 0 / 5 | No native desktop or Windows/Python 3.12 proof |
| **Total** | **70 / 100** | Evidence-weighted assessment, not a statistical reliability estimate |

**Final decision: NOT PRODUCTION CERTIFIED.** Critical manual/visualization/platform gates cannot be certified from this environment. This follow-up delivers implemented root fixes, a complete original-review classification, reproducible real-A service lifecycle evidence and passing regressions—not a claim that every requested desktop acceptance criterion is closed.
