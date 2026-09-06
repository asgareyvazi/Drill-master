# DrillMaster import consistency audit — 2026-09-06

## 1. Scope and exact acceptance boundary

Branch: `arena/01a07094-drill-master`
Starting audited commit: `0025bdbdcaa862bab531421008f65419c0cb38af`
Final SHA: fill from `git rev-parse HEAD` after the final commit.
Working-tree/push result: fill from the final release command.

This is a source and test-contract audit, not a claim that the user's Windows
installation was run. The repository's OEOC-208 fixture exists, but the user
OEOC-201 files and the Windows MinerU 3.4.5 environment are unavailable in this
Linux sandbox. Python 3.12 was not executed.

## 2. Thirty-point final report

1. **Architecture:** The one supported automatic graph is `Excel -> extractor
   -> common Import IR -> classification/mapping -> canonical schema -> shared
   normalization -> explicit units -> validation -> review -> atomic DB`; PDF
   enters through `MinerUAdapter` and then the same downstream graph.
2. **Changed files:** `core/import_ir.py`, `core/excel_intelligence.py`,
   `core/mineru_engine.py`, `core/import_quality.py`, `core/database.py`,
   `core/profile_import_engine.py`, `dialogs/excel_import_dialog.py`,
   `dialogs/smart_template_dialog.py`, `tests/test_ddr_acceptance.py`, and the
   eight reconciled documentation files.
3. **Discovery:** `core/import_router.py` is the universal format router;
   `ExcelImportDialog._run_import_pipeline()` is the UI orchestrator;
   `_do_import()` is the persistence boundary.
4. **MinerU executable/version/Python:** source supports configured executable
   or separately managed Python and official `--version`; no user executable
   was available, so no version/runtime PASS is claimed.
5. **API/CLI/command:** adapter command is an argument list equivalent to
   `mineru -p INPUT -o OUTPUT -b BACKEND -m METHOD`, with `shell=False`;
   actual configured path must be recorded during Windows acceptance.
6. **Formats:** XLSX/XLSM known templates use Excel; PDF/document/image use
   MinerU; CSV is conversion-only; legacy XLS and WITSML/LAS are unsupported or
   placeholder paths.
7. **Routing:** known template match precedes MinerU; MinerU success normalizes
   directly; PDF fallback is explicit and can continue only into canonical Excel
   template mapping.
8. **Excel preservation:** IR keeps formulas, hidden/merged state, source
   coordinates, headers/formal tables, original values and later normalized
   state; cache construction now consumes IR.
9. **PDF fallback:** Camelot/PyMuPDF/OCR remains a bounded legacy fallback,
   not a MinerU PASS; it has weaker PDF-native provenance and stops if no
   canonical template is available.
10. **IR:** `RawDocument`, `RawTable`, `RawCell`, `SourceLocation` include and
    round-trip file/page/sheet/table/row/column/cell, original/normalized
    values, headers, section titles, units, coordinates, extraction method,
    confidence, validation state, and review state.
11. **Canonical mapping:** `FIELD_SPECS` is authoritative: 325 fields, 28
    domains, 12 critical fields, 523 aliases; 37 normalized aliases are
    context-ambiguous and are not treated as globally unique.
12. **Provenance:** absent provenance remains `None`/unknown; no missing date,
    unit, depth, MW, pressure, company, or drilling value is invented.
13. **UI:** MinerU and fallback stage statuses are shown by the import dialog;
    preview shows source/normalized/review information before save.
14. **Errors:** source distinguishes invalid input, unsupported format,
    unavailable executable/Python, process failure, timeout, missing/malformed
    output, normalization/schema failure, review rejection, and DB failure.
15. **Tests:** new env-gated acceptance tests are explicit; current sandbox
    lacks pytest/openpyxl, so no full test count is claimed.
16. **Validation:** schema bounds, typed normalizer, engineering checks,
    duplicate/time-log checks, and model-boundary safe coercion remain in use.
17. **Real integration:** no real OEOC-201 Excel or Windows MinerU/PDF run was
    executed here; report **BLOCKED**, not PASS.
18. **Python 3.12:** not executed; **BLOCKED**.
19. **Conflicts:** removed the Excel IR/cache split, silent profile fallback,
    direct profile DB method, and non-atomic database rescue loop.
20. **Limitations:** legacy Smart Template/profile analysis remains for explicit
    compatibility; no dedicated ReviewItem ORM table; PDF fallback is weaker.
21. **SHA:** record exact final `git rev-parse HEAD` in this file/release report.
22. **Push:** only `git push origin arena/01a07094-drill-master` is allowed;
    record its result.
23. **Working tree:** final merge gate requires `git status --short --branch` to
    be clean after commit/push.
24. **Database verification:** acceptance tests seed in-memory SQLite and call
    `save_imported_multi_tab_data_atomic`; they assert zero failures and a
    positive imported count.
25. **Review:** acceptance tests round-trip `ReviewItem` rows and verify source,
    original, normalized, target, decision, validation and review state.
26. **Persistence:** no extractor or MinerU adapter writes SQLite; only the
    reviewed canonical payload reaches the atomic boundary.
27. **Security:** MinerU uses shell-free argument invocation, bounded timeout,
    isolated output and no credentials; optional AI is disabled by default.
28. **Packaging:** existing Windows PyInstaller/Inno definitions remain the
    package path; Linux cannot certify PE/installer/clean-machine behavior.
29. **Weak assertions:** acceptance tests assert canonical payload,
    provenance, serialized IR, review rows, atomic persistence and the
    `Drilling Data` regression—not merely process completion.
30. **Merge readiness:** **BLOCKED** until dependency-backed tests, actual
    Windows acceptance, exact SHA, push, and clean-tree evidence are recorded.

## 3. Entry-point matrix

The complete matrix is maintained in [`IMPORT_PIPELINE.md`](../IMPORT_PIPELINE.md).
The important source classifications are:

- Excel: `ExcelIntelligence` -> common IR -> canonical mapping -> review;
- PDF: MinerU adapter -> common IR -> `DocumentNormalizer` -> review;
- CSV/document conversion: conversion helper only, no direct DB write;
- Smart/profile/universal legacy utilities: not automatic canonical persistence;
- WITSML/LAS/XLS: unsupported/placeholder;
- review/dialog/service: `ReviewItem` and `_do_import` are the shared boundary.

## 4. ReviewItem end-to-end audit

`ReviewItem` now exposes a stable dataclass contract and `to_dict()` /
`from_dict()` methods. `ImportReviewMatrix` restores rows and exports typed
rows. The preview binds payload rows to UI rows, applies mapping/value/unit
edits, records decisions, and applies confirmed scalar changes to the canonical
payload before `_do_import()`. Rejected/ignored scalar fields are removed
rather than replaced with empty or zero values. Review rows are included in
import reports and professional exports; they are not stored in a separate ORM
review table.

## 5. Test and evidence status

Executed in this sandbox:

- `python -m compileall -q core dialogs tests/test_ddr_acceptance.py`: PASS.
- pure-Python IR/review serialization smoke check: PASS.
- `git diff --check`: PASS at audit time.

Not executable here:

- `pytest`: command unavailable.
- `openpyxl`-dependent Excel extraction: dependency unavailable.
- real OEOC-201 Excel: unavailable.
- Windows MinerU 3.4.5/PDF: unavailable.
- Python 3.12 and Windows packaging: unavailable.

The final report must not claim the prior repository snapshot's historical test
counts as evidence for this changed tree.
