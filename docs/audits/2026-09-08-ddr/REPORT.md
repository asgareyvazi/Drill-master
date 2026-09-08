> **Historical baseline report.** The current lifecycle follow-up, test counts, review reconciliation and decision are in [FOLLOWUP_REPORT.md](FOLLOWUP_REPORT.md). Original evidence below is preserved for comparison.

# DDR forensic remediation and certification report

**Date:** 2026-09-08 · **Decision: NOT PRODUCTION CERTIFIED**

This report supersedes earlier import counts and certification claims for this working session. It does **not** certify two Golden workbooks, Windows, the desktop UI, or rendered charts. Substantial importer/domain fixes are implemented and tested, but the requested end-to-end acceptance chain is incomplete.

## 1. Repository and execution boundary

- Repository: `asgareyvazi/Drill-master`.
- Session branch: `arena/01a0801f-drill-master`, based on `ad7ea0dbf353f3c376fa59750cdee86713ff2d89`. The requested preceding branch was not checked out or pushed; this session is fixed to its own branch.
- Runtime actually used: Linux x86-64, Python **3.11.2**, SQLite, openpyxl, existing SQLAlchemy models and engineering engines.
- Golden A actually opened and executed: `08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx`, 191,160 bytes.
- SHA-256: `37a6d96a6f154a9583590f52f9fb7cd92630f01d0a2abec2a9424877c1e4ef7a`.
- Golden B: **NOT AVAILABLE / NOT VERIFIED**. Workspace/history and remote-tree investigation found one real Excel workbook plus synthetic fixtures. The remote PDF is not a substitute for the second requested workbook. The earlier repository audit also records the absent `40-DDR OEOC-208 AZNS-12 ST#1 2025-May-22.xlsx` asset.
- Actual `run.py` startup was attempted, not mocked. It stopped at `ImportError: libGL.so.1`. Native Qt dependency recovery was unavailable. See `evidence/desktop-startup.txt`.
- Windows/Python 3.12, packaged executable, actual button interaction, dirty-state behavior, real 2D/3D rendering and PDF/MinerU execution: **NOT VERIFIED**.

The test environment disables the pytest-qt plugin because the native Qt runtime cannot start. Some existing tests use Qt stubs/static source assertions; those are not GUI acceptance. The standalone Golden A service execution uses **no Qt stubs**.

## 2. Architecture inspected and changed

### Actual import path

```text
ExcelImportDialog — route / preview / user confirmation / presentation
  -> DDRImportService.extract_file
     -> formula workbook + cached-value workbook
     -> ExcelIntelligence / RawDocument IR / template matcher
     -> canonical field normalization + source-token and ReviewItem metadata
  -> DDRImportService.import_records / _do_import
     -> parent-scoped well identity and section/report context
     -> caller-owned SQLAlchemy session
     -> shared domain adapters and existing DatabaseManager services
     -> existing TrajectoryCalculator and daily-report derived aggregates
     -> domain records + immutable import AuditLog in the same transaction
  -> selection/refresh presentation in the dialog
```

`core/ddr_import_service.py` was extracted from the dialog rather than creating a separate certification-only importer. The desktop dialog inherits/delegates to it; `tools/certify_ddr.py` invokes this same service. The tool refuses to overwrite an existing certification database.

### Domain/manual boundaries

| Area | UI / dialogs | Shared/domain/persistence boundary | Evidence boundary |
|---|---|---|---|
| Well/report | w1, w2; daily-report dialogs | combo_identity, selected-project well resolution, DailyReport, TimeLog24H/Morning | Real header/time persistence; UI identity interaction unexecuted |
| Mud/drilling/casing/cement | w3, w3b, w3c; drilling dialogs | MudValidator, chemical taxonomy/adapters, MudReport, DrillingParameters, casing/cement models | Real persistence and targeted projections; not all manual editors executed |
| BHA/downhole/formation | w4 | named adapters in domain_records; existing BHAReport/DownholeEquipment/FormationReport | Real named JSON and reload; UI static wiring only |
| Equipment/solid control | w5 | EquipmentLog, existing repositories/services | Real solid-control persistence; equipment CRUD UI unexecuted |
| Survey/trajectory | w6 | survey_records -> existing TrajectoryCalculator -> save_survey_records; SurveyRepository delegates | Real incomplete stations; synthetic complete engine/save/reload/plot-data tests |
| Logistics/fuel/water | w7 | nullable-date helper, material routing, existing POB and inventory models | Real POB/routing plus invalid-row isolation; UI unexecuted |
| Safety/BOP/waste | w8 | shared save_safety_report, typed children, _sync_safety_children, collection projections | Real safety/BOP and synthetic repeated manual save; nullable widgets static only |
| Services | w9 | ServiceCompany and material handling | Real companies/request narrative; full service editor unexecuted |
| Planning/NPT | w10 | NPT catalog, NPTReport, daily-derived updates, SevenDaysLookahead | Synthetic NPT lifecycle; real planning save; full planning UI unexecuted |
| Export/analysis | w11/w12 | existing report/export/analysis infrastructure | Inspected; no real PDF or rendered chart certification |
| Engineering | w13 | existing engineering engines; runtime_config resource resolution | Automated engine checks; reference spreadsheet/bundle absent |
| Procedures/reference/cost | w14/w15/w16 | existing repositories/db_services and catalogs | Existing regression coverage; not an all-tab manual certification |

This is **not yet universal manual/import convergence**. Some legacy tabs/repositories still construct models directly, monolithic database code remains, and duplicated ORM definitions in `core/db_models.py` are architectural debt. The audit does not label every Add Row/edit/save/signals/dirty/refresh path PASS just because it shares a model.

### Layer separation

- **Source:** formula/cached values, coordinates, merged/hidden structure, original tokens in IR/audit.
- **Normalized:** finite typed measurements, nullable dates, canonical identity resolution.
- **Derived:** existing engineering calculations, BHA cumulative length, tracked daily-derived records.
- **Presentation:** named columns and plot-series projections; source metadata is not iterated as display fields.
- **Provenance:** `_provenance`, ReviewItems and AuditLog. Mud source-token notes and unsupported safety dates no longer get appended to business summary/observation fields.

## 3. Golden A: actual results

Final service evidence: [`evidence/golden-a.json`](evidence/golden-a.json).

| Stage | Observed result |
|---|---|
| Source | Real workbook, dual formula/cached views |
| Extraction | 17 table results, **148 extracted rows**, **42 scanner rejection events** |
| Time tables | 10 canonical 24-hour rows; 8 canonical morning rows |
| Save | **REVIEW_REQUIRED**, legacy aggregate `imported=101`, `failed=0`, `review=65` |
| Diagnostics | No persistence failure diagnostics in this run |
| Report-scoped snapshot | **65 SQL rows** across the 24 snapshotted model types, plus nested JSON records |
| Close/reinitialize/reload | New DatabaseManager/engine; covered persisted snapshots equal |
| Exact source replay | `reimport=True`, `imported=0`; covered snapshots unchanged; one DDR import audit |
| Source IR | Preserved in immutable import audit |
| Directional plots | Three actual stations, all azimuth NULL; **zero calculated stations and empty plot series** |
| Desktop/runtime | Startup blocked; NOT VERIFIED |

**Counters are not interchangeable.** `101` is the legacy aggregate of import operations/nested records, not 101 distinct SQL rows. Scanner rejection events include structural/formula-only cells and are not the same as 65 domain ReviewItems. Do not subtract 42 from 148 to infer persisted records.

The earlier 180-row extraction included uncached formula-only phantom time records. Those cells remain in source IR but no longer become business rows. Duplicate scanner reason accounting was also corrected. Historical cached-only tests now count 10 unique rejected rows; that is a different extraction view from the final dual-workbook service run.

### Independently compared source values

- Report date: `2024-10-22` -> `2024-10-22`.
- BHA: all **9 component names** equal source, including repeated DC/XOS entries; descriptive name remains distinct from tool type. Cumulative length regression: **135.825 m**.
- Survey MD: **50, 108, 146 m**; inclination: **0, 0.25, 0.25 degrees**; azimuth: **NULL, NULL, NULL**. Missing azimuth was not invented as zero.
- POB: **6 records, total 130**, matching source.
- Mud chemical Barite: **Weight Material**, stock **45**.
- KCl chemical inventory: stock **12**; mud-property KCL measurement remains **NULL**. These are different fields.
- Mud solids: **7%**; ambiguous Oil/Water source token `5` is reviewed, not copied into both fields or used to invent a 100% composition.
- Safety: **468 days without LTI**. Unsupported calendar token `1403-07-30` remains audit metadata; observations and Gregorian drill dates are not fabricated.
- Missing safety pH/test pressure/LTI count, fuel received/type, and material request quantity/unit remain **NULL**, not ORM-generated pH 7/zero/diesel/units.
- Planned dates no longer populate actual execution start/end.

The service log file had no emitted entries; stderr contained the openpyxl data-validation-extension warning. This is **not proof of a clean desktop runtime**.

### Per-section certificate

[`section-matrix.csv`](section-matrix.csv) covers 24 areas with source/persistence, mapping status, reload boundary, UI/chart status, and Golden B status. `SERVICE PASS` is deliberately narrower than end-to-end PASS. **Every Golden B stage and every real desktop/chart stage is NOT VERIFIED.**

## 4. Chemical classification certificate

The six category labels were taken from the pre-existing manual chemical combo in `tabs/w3_drilling_report.py`: Viscosifier, Weight Material, Alkalinity, Filtration Control, Lubricant, Shale Inhibitor. They are now centralized in `domain_records.CHEMICAL_TYPES`; aliases resolve through `core/combo_identity.py`.

[`chemical-matrix.csv`](chemical-matrix.csv) contains **all 34 source chemicals**, source location, imported name, assigned category, expected category/review policy, source and persisted stock, unit and result.

- **10 mapped:** 2 Viscosifier, 1 Weight Material, 4 Alkalinity, 1 Filtration Control, 1 Lubricant, 1 Shale Inhibitor.
- **24 unresolved:** stored with NULL type and ReviewItems, never defaulted to the first Viscosifier entry.
- Salt, anti-foam, scavengers, lost-circulation materials and ambiguous blends were **not forced into an unrelated available category**. A reviewed authoritative taxonomy extension is needed before those can be fully classified.
- `PASS review policy` in the CSV means correct preservation/review behavior, **not** successful full chemical classification.
- Golden B chemical matrix: **NOT VERIFIED**, because its workbook is unavailable.

## 5. Defect/root-cause/regression matrix

Here, PASS means the stated narrow regression passed. It does not override the desktop/Golden B boundaries above.

| ID / symptom and evidence | Cause and affected boundary | Implemented change | Regression evidence | Golden A / Golden B |
|---|---|---|---|---|
| D01 NPT status did not activate the checkbox/domain | Status, NPT code and company were interpreted through unrelated operation/positional identities | Shared NPT catalog/adapter; status activation; authoritative company resolution; unresolved company review; w2/dialog wiring | `test_npt_activation_and_company`, `test_npt_unknown_company_is_not_first_item`, `test_npt_source_status_persists_and_creates_normal_npt_domain` PASS | A has no actual NPT event: NOT EXERCISED; B NOT VERIFIED |
| D02 All chemicals became Viscosifier | QComboBox's first item and inconsistent import/manual JSON semantics supplied a false category | Central existing taxonomy; alias resolution; no selected index on unknown; NULL type + review; stock/name/units retained | chemical taxonomy/routing tests and 34-row matrix PASS at mapping/review scope | A 10 mapped/24 review; B NOT VERIFIED |
| D03 BHA names lost; metadata/path values spilled into weight/connection | Positional `dict.values()` presentation and mismatched `bha_configs`/`bha_data` schemas mixed source metadata with columns | Explicit named BHA/downhole/formation adapters; separate Tool Type/Component Name; canonical BHA fields; manual payload correction | `test_bha_named_projection_manual_and_import_roundtrip`, metadata and description cases PASS | A 9 exact names/3 downhole/1 formation; B NOT VERIFIED |
| D04 Survey nonnumeric failure and false derived coordinates | Unconditional float conversion, missing-angle zero defaults, direct derived-value persistence and no full append context | Shared numeric isolation; NULL missing angles; existing TrajectoryCalculator; report-context recomputation; repository delegation | survey isolation, append, update, reload and `plot_series` tests PASS | A 3 incomplete stations retained, no invented path; B NOT VERIFIED |
| D05 No calculation selected / generic survey save failure | Measurement save was coupled to calculation selection and failures lacked row context | Report/well-based survey persistence independent of calculation selection; structured reviews/exceptions; w6 load/save refresh wiring | Service/repository tests PASS; real button and Matplotlib/Qt rendering NOT VERIFIED | A persistence PASS, UI NOT VERIFIED; B NOT VERIFIED |
| D06 Mud inventory entered Fuel/Water bulk | Generic bulk loop ignored source mud-chemical section | Source-aware routing; mud chemicals saved as MudReport chemical JSON; unknown material review | `test_mud_stock_type_and_inventory_destination`, route cases PASS | A 34 chemicals, **0 bulk rows**; B NOT VERIFIED |
| D07 BOP/waste NoneType iteration; repeated Safety Save duplicates | JSON NULL was exposed as an iterable; summary JSON and child inserts were separate, duplicate manual loops | Collection normalization/projection; shared safety save and atomic child synchronization; duplicate UI insertion loops removed | empty/populated/error collections, mixed bad-BOP/good-survey, repeated manual safety save PASS | A 5 BOP/0 waste; waste positive synthetic only; B NOT VERIFIED |
| D08 MudReportTab missing show_warning/show_error | QWidget subtab called methods owned by another base abstraction | Existing QMessageBox notification path used explicitly for mud validation; no monkey-patching or warning suppression | Static notification wiring PASS; real dialog NOT VERIFIED | A persisted; UI NOT VERIFIED; B NOT VERIFIED |
| D09 POB dates displayed/parsing literal None | `str(None)` presentation and unconditional ISO-only `strptime` | Blank presentation for NULL; shared optional-date parsing; isolated invalid records; exact row/company diagnostics | optional/alternate/invalid date cases and POB partial-save/reload PASS | A 6 POB/130; B NOT VERIFIED |
| D10 W13 DrillPipe.xlsx depends on CWD/missing file | Relative asset lookup mixed optional reference with runtime requirement | runtime_config searches configured/user/bundle resource locations independent of CWD; optional absence explicit | CWD/config path tests PASS | File content and packaged Windows loading NOT VERIFIED for either Golden |
| D11 False mud composition warnings 7/12/17% | Missing measurements treated as zero and ambiguous Oil/Water copied into composition | Distinguish complete vs partial composition; preserve NULL through load/save; block load-time signal cascades; validate real complete total | partial, invalid-complete and valid-100 tests PASS | A 7% partial, no invented balance; B NOT VERIFIED |
| D12 Phantom time rows / inflated rejections | Uncached duration formulas and metadata-only rows looked like measurements; reason list counted twice | Formula-only row classification while preserving IR; unique rejection reasons | formula-only and real extraction/review contract tests PASS | A 148 raw rows, 10+8 time rows; B NOT VERIFIED |
| D13 Partial failure cancelled good records or concealed DB errors | Whole-batch source coercion and collection `except: return []` conflated bad input/empty/error | Typed row isolation; shared caller-owned transaction; collection failures propagate; source reviews distinct from unexpected persistence diagnostics | atomic rollback, collection-failure, bad BOP/valid survey and POB isolation tests PASS | A 0 failed operations/65 review; B NOT VERIFIED |
| D14 Re-import/derived duplicates and stale values | Additive/upsert updates without target-aware source replay or stale-derived cleanup | Well-scoped source audit lookup; immutable replay; tracked generated NPT/time-depth IDs; reset disappeared code aggregates; source-based last-used date | exact replay, target fingerprint and derived-cleanup tests PASS | A closed-engine reload and exact replay equal; B NOT VERIFIED |
| D15 Parent identity and first-section fallback | Global first matching well and unrelated section index could select the wrong domain identity | combo_identity-based well matching within selected project; ambiguous identity fails; w2 requires explicit valid section when multiple exist | parent-project and ambiguity tests PASS; UI static only | A source identity resolved; B NOT VERIFIED |
| D16 Source metadata/defaults masqueraded as business facts | Mud/safety provenance appended to notes; SQLAlchemy defaults invented missing values; planned dates mapped to actual dates | Audit-only metadata; explicit SQL NULL for affected imported measurements; nullable Safety presentation/save; report-derived date context; planned/actual separation | real source assertions plus `test_import_does_not_activate_orm_measurement_defaults` PASS | A source-backed NULL checks PASS; real Safety edit/save NOT VERIFIED; B NOT VERIFIED |
| D17 Opt-in acceptance test rejected a valid density | Test assumed every source-review token is nonnumeric, including SOURCE_UNIT_PENDING 71 | Assert finite unchanged numeric magnitude and review for unit-pending values; keep NULL assertions for invalid tokens | Reproduced failure on archived base commit; corrected real acceptance test PASS | A PASS; B NOT VERIFIED |

### Remaining acceptance failures / limitations

1. **FAIL end-to-end certification:** missing Golden B and Windows/Qt execution prevents the user's full acceptance chain. This is not a paperwork-only gap.
2. **NOT VERIFIED real charts:** complete synthetic surveys reach the existing engine and plot-data projection; Golden A has no azimuth and cannot honestly produce a calculated trajectory. The real 2D/3D canvas was not rendered.
3. **PARTIAL generalized detection:** the new conservative generic table detector handles six section signatures and canonical aliases; three synthetic structural variants pass through `extract_file -> import_records -> reload`. These cover offsets, reordered columns and hidden data rows. Existing merged/multirow/repeated-header tests also pass. They do not prove arbitrary publisher layouts, every adjacent table boundary, every unit-only header, or Golden B compatibility. Existing company templates remain in use.
4. **PARTIAL architecture:** not every legacy manual editor/repository has been migrated into a single domain service. Full all-tab Add/edit/save/reload/signals/dirty/refresh parity remains unverified.
5. **PARTIAL status contract:** domain row reviews use INVALID_SOURCE/REVIEW_REQUIRED and unexpected exceptions carry structured diagnostics, but legacy aggregate API names remain ACCEPT / VALIDATION_ERROR / PERSISTENCE_ERROR. A universal literal SUCCESS / REVIEW_REQUIRED / INVALID_SOURCE / UNSUPPORTED / SYSTEM_ERROR API is **not implemented everywhere**.
6. **PARTIAL diagnostics:** phase, exception, source row/field and traceback are available at supported boundaries; not every legacy database failure has exact column-level attribution. No blanket claim of clean runtime is made.
7. **PARTIAL lifecycle:** exact replay and new tracked-derived cleanup pass. Changed-workbook reconciliation, user edits followed by replay, deletion/replacement of survey MD keys, and pre-existing untracked derived rows are not comprehensively certified. Cleanup intentionally does not delete untracked/manual rows by guessing their origin.
8. **PARTIAL source interpretation:** 24 chemical types and several source/unit/date ambiguities remain review work, not success. Report-relative planning date inference and all optional typed-model defaults across every legacy tab are not globally certified.
9. **Optional asset unavailable:** DrillPipe reference resolution is fixed, but no actual spreadsheet or Windows bundle was available to verify its contents/packaging. It is not required for the core importer; that does not certify all W13 reference-dependent calculations.

## 6. Executed tests and runtime evidence

All counts below are final executions, not planned commands. Test groups overlap; **do not add their passed counts together**.

| Run | Passed | Failed | Errors | Skipped | Warnings | Time |
|---|---:|---:|---:|---:|---:|---:|
| Base commit ordinary suite | 536 | 0 | 0 | 8 | see baseline log | 53.35 s |
| Base commit real Excel opt-in (archived source) | 0 | 1 | 0 | 0 | 1 | 5.28 s |
| New forensic targeted suite | 72 | 0 | 0 | 0 | 1 | 24.84 s |
| Import/extraction group | 118 | 0 | 0 | 1 | 7 | 34.44 s |
| Engineering group | 136 | 0 | 0 | 1 | 0 | 0.83 s |
| Integration/static-wiring group | 97 | 0 | 0 | 0 | 1 | 29.58 s |
| Corrected real Excel opt-in alone | 1 | 0 | 0 | 0 | 1 | 5.02 s |
| **Final full suite, real Excel opt-in enabled** | **609** | **0** | **0** | **7** | **12** | **80.90 s** |

The base opt-in failure was actually reproduced from `git archive ad7ea0d...` in a separate directory, using the same workbook/environment. No branch switching was needed. It is an existing incorrect acceptance assertion, not evidence that a nonnumeric source token should be accepted. See `evidence/baseline-optin-failure.txt`.

Final skips: real PDF acceptance (input absent); real MinerU integration (installation/input absent); Windows bundle smoke (bundle absent); report-cost Qt path, missing-nozzle Qt path, all-core-import and circular-import Qt checks (native libGL unavailable). The real Excel test is **enabled and passes**, not left in the skip list.

Warnings: 11 openpyxl data-validation-extension warnings and one existing large-module warning (`database.py` and W13 remain monolithic). Warnings were not suppressed. Compileall and Ruff undefined/unused-symbol checks passed for the new service/domain/survey/NPT/semantic-table/harness/forensic-test modules; this is not a claim of repository-wide lint cleanup.

Machine-readable counts, exact selected test files, JUnit and logs are in `evidence/`. The integration group includes static/headless coverage; it is **not a successful interactive UI test suite**.

## 7. Transparent scores

These are conservative **audit evidence scores**, not a standardized product rating or a claim that a missing workbook is poor quality. Missing required evidence earns no certified points.

| Golden evidence dimension | Weight | Golden A awarded | Golden B awarded |
|---|---:|---:|---:|
| Source extraction and structural resilience | 20 | 15 | 0 — NOT VERIFIED |
| Semantic/domain mapping and source fidelity | 25 | 18 | 0 — NOT VERIFIED |
| Shared validation/calculation/manual convergence | 15 | 8 | 0 — NOT VERIFIED |
| Persistence, closed-engine reload and idempotency | 15 | 13 | 0 — NOT VERIFIED |
| Actual UI and 2D/3D rendering | 15 | 0 | 0 — NOT VERIFIED |
| Required Windows/Python 3.12 clean runtime | 10 | 0 | 0 — NOT VERIFIED |
| **Total** | **100** | **54/100** | **0 certified evidence points; file quality NOT ASSESSED** |

Production-readiness evidence score:

- Two-Golden coverage, weight 40: `40 * ((54 + 0) / 200) = 10.8`.
- Architecture/manual convergence, weight 20: 13.
- Engineering validation, weight 10: 7.
- Regression/negative-path evidence, weight 10: 9.
- Required desktop/Windows/packaging runtime, weight 20: 0.
- **Total: 39.8, rounded 40/100 — NOT READY FOR PRODUCTION CERTIFICATION.**

Critical runtime and second-Golden gaps materially lower these scores despite passing automated tests.

## 8. Reproduction and artifacts

From the repository root with dependencies installed:

```bash
python tools/certify_ddr.py \
  '08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx' \
  --output /path/to/new/evidence-directory

DRILLMASTER_TEST_DDR_XLSX="$PWD/08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx" \
QT_QPA_PLATFORM=offscreen \
python -m pytest -p no:pytest-qt tests
```

The certification SQLite database is retained outside Git at `/home/user/audit/golden-a-release-evidence/certification.db`. Tracked evidence includes the final persisted JSON snapshot, source comparisons, reviews, test logs and JUnit, not the generated database or cloned baseline dataset.

Changed implementation groups: canonical schema/normalizer/validators; combo identity and NPT catalog; shared DDR/domain/survey/semantic-table services; database/db_services and SurveyRepository; Excel/daily/drilling dialogs; w2/w3/w4/w6/w7/w8/w13; forensic and real/review/integration/acceptance tests; certification tool. This directory contains the report, matrices and evidence. Existing prior audit documents remain historical and should not be read as this branch's final certificate.

Implementation and evidence are committed on the session branch. Use `git log -1` for the final commit; its exact SHA is supplied in the delivery message (a commit cannot embed its own final hash).
