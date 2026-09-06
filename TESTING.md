# Testing and acceptance guide

**Audit date:** 2026-09-06

## 1. Local test gate

From the repository root, in a dependency-complete environment:

```bash
python -m pytest -ra
python verify_release.py
python -m compileall -q core dialogs tabs tests
python -m py_compile app.py run.py main_window.py verify_release.py
python -m pip wheel . --no-deps --wheel-dir dist
git diff --check
```

The active sandbox did not have `pytest` or `openpyxl`, so only compile and
pure-Python smoke checks were executable during this audit. No full-suite pass
count is claimed from this environment.

## 2. Real DDR acceptance

The opt-in tests are `tests/test_ddr_acceptance.py`:

```bash
DRILLMASTER_TEST_DDR_XLSX='C:\path\to\DDR.xlsx' \
DRILLMASTER_TEST_DDR_PDF='C:\path\to\DDR.pdf' \
python -m pytest -q -m integration tests/test_ddr_acceptance.py
```

Each test skips explicitly when its path is absent/unavailable. The PDF test
also skips when the separately managed MinerU installation is unavailable; it
does not install MinerU. A supplied but malformed real input fails rather than
being converted into a synthetic PASS.

### Excel assertions

- source workbook -> `raw_document_from_workbook` -> `ExcelIntelligence`;
- cache/merge lookup comes from the common IR;
- original source tokens and normalized values remain separate;
- canonical schema mapping and bounds run;
- review rows deserialize as `ReviewItem`;
- `DatabaseManager.save_imported_multi_tab_data_atomic()` persists without
  failure in an in-memory DB;
- non-numeric `Drilling Data`/placeholder tokens remain NULL plus provenance,
  never zero or a numeric-conversion crash.

### PDF assertions

- `MinerUAdapter.health_check()` and `parse_file()` run the actual external
  executable;
- generated raw output files are present;
- MinerU tables/text/headings adapt to the common IR;
- page/row/column/bounding-box provenance, original/normalized values, review
  states, canonical validation and review rows survive;
- a real report date is required for DB acceptance; no date is invented;
- canonical values pass the same atomic DB boundary.

## 3. Test categories

| Category | Main evidence |
| --- | --- |
| Canonical schema | `test_canonical_schema.py`, expanded schema tests: field count, aliases, duplicate-context behavior, types, quantities, criticality, bounds |
| Shared normalizer | value normalizer tests and import regressions: missing tokens, invalid types, dates/times, zero vs missing |
| Authoritative units | `test_p0_unit_preservation.py`: original value/unit, conversion rule, canonical value, failed conversion review |
| Review contract | `test_import_quality_extra.py`, acceptance tests: aliases, serialization/deserialization, decisions, edits, provenance |
| Atomicity | `test_p0_atomic_import.py`, real-golden DB tests: failure rollback, no orphan/partial records, prior report preservation |
| MinerU failures | `test_mineru_engine.py`: unavailable executable, bad input/format, process error, timeout, missing/malformed output |
| Optional AI | mapper capability/failure tests: disabled, unavailable, timeout, malformed response, no invented values |
| Security | permissions, path/config, shell-free subprocess and secret-handling tests |
| Packaging/release | packaging smoke, release gate, version/spec/asset checks |
| Weak assertions | release gate and source-audit checks; acceptance tests assert persisted values/provenance rather than only non-crash |

## 4. Review/UI contract checks

`ReviewItem` preserves file, sheet/page, table/section, source cell and PDF
coordinates, original/normalized values and units, target field, confidence,
certainty, mapping method, validation/review state, decision, reason, and user
correction. `ImportReviewMatrix.from_rows()` restores serialized rows.

The preview supports accept-high, review-medium, reject-low, mapping edit,
value edit, unit edit, and ignore. `apply_review_changes()` synchronizes those
edits into the canonical scalar payload before `_do_import()`; a visual edit
alone is not considered a successful test.

## 5. Environment and certification limits

The repository's Windows packaging is not certified on Linux. The user's
Windows MinerU 3.4.5 installation and OEOC-201 files were not available here.
Python 3.12 is not PASS unless the exact runtime executes the suite and real
acceptance. Keep real documents, MinerU outputs, databases, and generated
builds outside Git unless a fixture is intentionally required.
