# Real import forensic audit — 2026-09-08

## Scope and evidence boundary

- Branch: `arena/01a07094-drill-master`
- Checkout at start of this validation: `c7e7697f80de0a91daf59541c419a44aadac8df9` (grafted)
- Exact workbook: `08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx`
- Required production asset: `40-DDR OEOC-208 AZNS-12 ST#1 2025-May-22.xlsx`
- Validation runtime: Linux, Python 3.11, openpyxl/SQLAlchemy/pytest installed in an isolated temporary environment. This is not Windows acceptance.

The previous automated PASS report was not used as real-import evidence. The real
workbook was opened, walked, routed, extracted, validated, persisted to an
in-memory SQLite database, and passed through the application route with a
collection-only preview and an auto-confirming preview. No production database
was used.

## Asset and history search

A repository filesystem search, reachable git-object path search, full-history
path/name search, `git log -S` search, and unreachable-object check found:

- the exact OEOC-208/AZNS-207 workbook above;
- synthetic Excel fixtures and templates;
- no repository PDF or stored MinerU output for this report;
- no `AZNS-12` workbook/PDF or other production AZNS-12 asset.

**AZNS-12 production asset not present in repository/workspace.**

`mineru` is not on PATH. `MinerUAdapter().health_check()` returned
`available=False`, `enabled=False`, `error="MinerU is disabled or not detected"`.
The adapter contract was inspected: it uses shell-free
`mineru -p INPUT -o OUTPUT -b BACKEND -m METHOD`, parses Markdown/JSON/assets,
retains output diagnostics, and maps through the common IR. Real PDF/MinerU
execution is therefore **BLOCKED**, not PASS.

## Workbook forensic inventory

Both formula (`data_only=False`) and cached-value (`data_only=True`) workbook
views were opened. The workbook has six sheets, 1,761 non-empty source cells,
1,326 merged ranges, 235 formula cells, and one formal Excel table (`Table2`).
The IR walk retained 8,702 cells, including merged-cell structure and formula
provenance, seven IR table/worksheet regions, zero text blocks, and zero IR
section-title blocks.

| sheet | dimensions | non-empty | merged ranges | formulas | formal tables |
|---|---:|---:|---:|---:|---:|
| DDR Remark | 109 x 84 | 417 | 830 | 113 | 0 |
| DDR Data | 114 x 43 | 542 | 412 | 21 | 0 |
| Lookahead | 26 x 23 | 80 | 55 | 41 | 0 |
| Service Company | 82 x 43 | 50 | 0 | 1 | 1 |
| Activity Codes | 150 x 41 | 416 | 29 | 1 | 0 |
| setting (hidden) | 51 x 31 | 256 | 0 | 58 | 0 |

Representative source evidence includes `DDR Remark!W3 = AZNS-207`,
`DDR Remark!AG4 = OEOC 208`, `DDR Data!R10 = 225`,
`DDR Data!G7/H7/I7` formula-backed date components, `Lookahead!B10` activity
text, three survey rows beginning at `DDR Data!J58`, and merged section/header
ranges in both DDR sheets. Continuation rows in the 24-hour and morning logs
were retained for review rather than dropped. Formula cells are preserved in
IR while cached values are used for canonical mapping; the date was assembled
from year/month/day as `2024-10-22`.

## Real public/application route and stage counts

The invoked application route was `ExcelImportDialog._run_import_pipeline()`
with `route_file()` and its generic template matcher. Excel was run in
collection-only mode by replacing only the preview confirmation boundary; no
DB write occurred in that run. A second invocation used an auto-confirming
preview and an in-memory SQLite database to exercise the same persistence and
UI result path.

| stage | observed result |
|---|---:|
| file opens | 2 workbook views opened successfully |
| router | `excel_intelligence` |
| fallback engine | none; Excel did not use MinerU |
| matched template | `OEOC DDR Template v3.0` / `templates/OEOC_DDR_v3.json` |
| sheets/dimensions | 6 sheets; dimensions listed above |
| source non-empty/formula/merge evidence | 1,761 / 235 / 1,326 |
| RawDocument | 8,702 cells; 7 table/worksheet regions; 0 text blocks |
| extracted fields | 124 detected; 124 `OK`, 17 unresolved, 15 review-required, 4 conflicts in 160 field results |
| extraction confidence | 130 HIGH, 12 MEDIUM, 18 LOW |
| extraction tables/rows | 17 table results; 180 rows observed; 14 rejected/held rows |
| extraction validation counter | 18 warnings/errors recorded by the extractor; no source row was silently discarded |
| shared source tokens | 7 unsafe numeric tokens preserved with normalized value `None` |
| field provenance | 140 canonical field provenance entries |
| canonical top-level domains | 24 populated domains; 2,018 non-empty canonical leaves including record provenance |
| meaningful-data guard | `True` |
| collection-only quality report | total 39; failed 0; errors 0; warnings 56; ReviewItems 39 |
| persistence | `imported=101`, `failed=0`, `validation_errors=0`, diagnostics 0 |
| persistence review | 79 shared ReviewItems; no invented values for continuation/BOP/survey issues |
| final application status | `REVIEW_REQUIRED` |
| final UI payload | one emitted result; same file/status/counts, 23 detail messages, 79 review items |

The persisted report-scoped SQLite rows included: 1 daily report, 7 valid
24-hour log rows, 6 valid morning rows, 3 survey points, 11 lookahead rows,
34 bulk-material rows, 6 service-company rows, 6 POB rows, 5 BOP rows, 9
solid-control rows, 9 cement rows, 9 equipment rows, and the other one-to-three
row report entities shown by the application. The database table-count check
returned: `daily_reports=1`, `time_logs_24h=7`, `time_logs_morning=6`,
`survey_points=3`, `seven_days_lookahead=11`, `bulk_materials=34`,
`service_companies=6`, `service_company_pob=6`, `bop_components=5`,
`casing_reports=1`, `cement_reports=1`, `bha_reports=1`,
`downhole_equipment=1`, `formation_reports=1`, `fuel_water_inventory=1`,
`material_requests=1`, `mud_reports=1`, `safety_reports=1`,
`drilling_parameters=1`, and `wells=2` (one seeded well plus the imported
`AZNS-207` identity).

### Meaningful-data decision

`has_meaningful_canonical_data(actual_output)` returned `True` because the
payload contains business values such as `well_info.name=AZNS-207`,
`daily_report.report_date=2024-10-22`, `daily_report.depth_2400=225.0`,
non-empty time-log activity descriptions, and survey `md` values. The decision
does not rely on `metadata`, `raw_document`, review rows, or provenance-only
keys. The seven unsafe source tokens remain review/provenance evidence and do
not manufacture numeric values.

## Renamed and column-order checks

- A completely renamed copy produced the same route, template, extraction
  counts, canonical keys, and semantic values.
- Reordering workbook sheet order preserved `AZNS-207`, `2024-10-22`, 38
  24-hour records, and six service-company records.
- Reordering the formal Service Company table columns (and updating its table
  reference) preserved all six semantic service records. The dynamic table
  resolver used header labels rather than the original positional columns.
- Generic `.xlsx` routing is independent of filename and does not route Excel
  through MinerU.

## Historical comparison and root-cause finding

The starting reachable code was compared with the current route using the same
real workbook. The historical direct extractor with a formula workbook
(`data_only=False`) produced formula strings in canonical fields (for example,
`well_info.name` became `='DDR Remark'!W3` and `report_date` was absent) and
only 10 24-hour rows. The current dual-workbook IR path retains formulas while
using cached values and produced the real semantic values, 38 24-hour rows,
and the date components above. The historical direct cached view did find the
well/date, so the old public `SmartTemplateDialog` path cannot be blamed with
certainty without its missing production log.

**First observable information-loss point:** the old formula-only workbook
view, before canonical mapping, when formula cells were consumed without their
cached values. In the current run there is no loss point before persistence:
RawDocument -> extraction -> canonical mapping -> normalization -> validation
-> ReviewItem -> atomic persistence all retained evidence. The previous
"no data" PASS report is therefore not a reproducible production failure; it
was an evidence/acceptance gap, not proof that this workbook had no data. The
generic current fix is the dual formula/cached IR path and the filename-
independent Excel router, not an AZNS/coordinate hardcode.

An additional forensic negative-path observation exposed a diagnostics issue:
a zero-content workbook reached the meaningful-data guard, while a corrupt XLSX
raised `BadZipFile` during open. The route now reports these separately as
`validation.meaningful_data` and `import.open` with `VALIDATION_ERROR`; database
failures remain `PERSISTENCE_ERROR`, and preview failures carry `ui.preview`.
No data is persisted for either negative path.

## Negative/ambiguous paths

- **Positive real workbook:** `REVIEW_REQUIRED`, 101 imported, 79 review
  items, no validation/persistence error.
- **Renamed workbook:** equivalent extraction and canonical evidence.
- **Empty workbook:** `VALIDATION_ERROR`, stage `validation.meaningful_data`,
  no persistence.
- **Malformed workbook:** `VALIDATION_ERROR`, stage `import.open`, exception
  `BadZipFile`, no persistence.
- **Ambiguous/review:** the real workbook itself retains unresolved/conflicting
  fields and continuation/BOP/survey review rows; final status is
  `REVIEW_REQUIRED`, never fabricated acceptance.
- **Persistence error:** the atomic transaction regression injects failures at
  well, section, report, mud, drilling, time, morning, and multi-tab stages;
  each returns `PERSISTENCE_ERROR` with a stage diagnostic and rolls back.
- **UI display failure:** the application catch boundary reports stage
  `ui.preview` using the existing four-status contract; it cannot be certified
  as a Windows GUI run in this Linux environment.

## Regression and verification commands

Added regression: `test_repository_workbook_contains_meaningful_semantic_evidence`
in `tests/test_excel_intelligence_regressions.py`. It opens the exact repository
workbook and asserts `AZNS-207`, `2024-10-22`, depth `225.0`, non-empty activity
text, and a real survey MD value.

Executed with the isolated validation environment:

- `PYTHONPATH=. pytest -q`: **532 collected, 524 passed, 8 skipped** after the
  regression addition.
- Real-workbook integration/route: PASS with the counts in this report;
  final real status is intentionally `REVIEW_REQUIRED`, not `ACCEPT`.
- `python -m compileall -q core dialogs tests`: PASS.
- `git diff --check`: PASS at the final verification point.
- Release smoke: `PYTHONPATH=. pytest tests/test_release.py tests/test_release_gate_and_w13.py tests/test_release_smoke.py -q` passed (31 passed, 2 skipped).
- `PATH=/tmp/drill-venv/bin:$PATH /tmp/drill-venv/bin/python verify_release.py`: PASS; syntax plus complete suite, 532 collected, 524 passed, 8 skipped, 0 failed/errors.

The real workbook acceptance is Linux/in-memory evidence only. Windows GUI,
production database, Python 3.12, MinerU execution, the AZNS-12 assets, and
PDF production acceptance remain genuine blockers.
