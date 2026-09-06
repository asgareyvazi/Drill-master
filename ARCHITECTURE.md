# DrillMaster architecture and import audit

**Branch:** `arena/01a07094-drill-master`
**Audit date:** 2026-09-06
**Status:** canonical import path repaired; real OEOC-201/Windows MinerU acceptance is **BLOCKED** in this Linux checkout.

## 1. One canonical runtime architecture

The supported universal import boundary is:

```text
Excel -> extractor -> common Import IR -> classification/mapping
      -> canonical_schema -> shared value normalization
      -> authoritative unit normalization -> validation
      -> ReviewItem/preview -> atomic persistence

PDF/document/image -> MinerU adapter -> same common Import IR and downstream path
```

The extractor is source-specific; the downstream contract is not. `core/excel_intelligence.py`
now builds its cache and merge lookup from the `RawDocument` created by
`core/import_ir.py`; it does not reread the workbook for a second mapping path.
`core/mineru_engine.py` adapts `MinerUDocument` to the same IR before
`DocumentNormalizer` maps values.

Persistence is owned by `dialogs/excel_import_dialog.py` at `_do_import()` and
`DatabaseManager.save_imported_multi_tab_data_atomic()`. The database layer no
longer catches an atomic failure and starts a per-table legacy rescue loop.
`ProfileImportEngine.import_to_db()` is disabled, and Smart Template no longer
silently invokes `ProfileImportEngine`.

## 2. Runtime components

| Component | Responsibility | Must not do |
| --- | --- | --- |
| `core/import_router.py` | suffix/template route selection | parse or write the DB |
| `core/import_ir.py` | lossless source document/table/cell contract | guess fields or coerce values |
| `core/excel_intelligence.py` | deterministic template/alias extraction | write the DB |
| `core/mineru_engine.py` | external process, output parsing, IR adaptation, canonical normalization | import MinerU into DrillMaster or write SQLite |
| `core/canonical_schema.py` | authoritative field specs, aliases, quantities, units, bounds, criticality | perform extraction |
| `core/value_normalizer.py` | typed normalization and missing/invalid state | infer missing values |
| `core/unit_manager.py` | explicit engineering conversion and conversion records | choose a unit that is absent from source |
| `core/import_quality.py` | validation, `ReviewItem`, review matrix, time-log rules | persist data |
| `dialogs/excel_import_dialog.py` | status, preview/editing, validation, atomic save | bypass review |
| `core/database.py` | model-boundary coercion and atomic persistence | retry through a partial legacy path |

## 3. Common Import IR contract

`RawDocument`/`RawTable`/`RawCell` preserve, and can serialize/deserialize:

- source document/file, page, sheet, table, row, column, cell and PDF bounding coordinates;
- original source value and separate normalized value/unit fields;
- headers, table names, section titles and optional source units;
- extraction method, optional confidence, validation state and review state;
- Excel formula text, hidden rows/columns, merged-cell membership and merge anchor;
- MinerU pages, headings, text blocks, tables and raw output metadata.

`RawDocument.to_dict(include_cells=True)` is the complete audit form;
`RawDocument.from_dict()` restores it. Unknown coordinates, units, dates,
depths, pressures, company values, and confidence remain `None`/unknown.

## 4. Canonical schema facts

The authoritative `FIELD_SPECS` registry currently contains **325 fields in 28
domains**, **12 critical fields**, and **523 alias entries**. Thirty-seven
normalized alias keys are shared by more than one field; alias lookup must use
field/domain context and must not claim that those strings are globally unique.

No importer may invent a missing value or replace a source placeholder with
zero. A malformed numeric source token becomes a NULL/needs-review result with
its original token retained in source-token/review provenance.

## 5. Review and persistence boundary

`ReviewItem` is the single review contract. It carries file/sheet/page/table,
section title, source cell/coordinates, original/normalized value and units,
target/canonical field, expected type, confidence/certainty, mapping method,
transform, validation state/message, decision, review state, reason, and user
correction. `ReviewItem.to_dict()` and `ReviewItem.from_dict()` support the
serialized UI/export contract; `ImportReviewMatrix.from_rows()` restores a
matrix.

The Qt preview renders these fields. Mapping, normalized-value, unit, accept,
reject, and ignore edits are synchronized back into the serialized row and
applied to scalar canonical dotted paths before `_do_import()`. The DB write
occurs only after confirmation. Review rows are included in the import report
and exports; DrillMaster does not currently have a separate review-item ORM
table.

## 6. Deliberately bounded legacy/unsupported components

These are not alternate production architectures:

- `SmartTemplateDialog` is a manually opened legacy mapping UI. Its private
  heuristic data is not automatically called by the universal route; its
  profile fallback hook is a no-op and its output must use the shared review /
  atomic boundary.
- `ProfileImportEngine.analyze_and_extract()` remains an explicit compatibility
  analysis utility for old callers. It is not a canonical route and direct DB
  import raises `LEGACY_DIRECT_DB_IMPORT_DISABLED`.
- `core/universal_import.py` remains scanner/classifier support for legacy UI
  and tests, not a persistence entry point.
- `document_import.py` and `import_adapters/pdf_tables.py` are conversion or
  legacy extraction helpers. PDF fallback may create an intermediate XLSX,
  but it is accepted only when the canonical Excel template path can continue;
  missing templates stop before persistence and cannot enter profile heuristics.
- `core/witsml_import.py` is a validation/placeholder contract and returns
  unsupported for actual import. `core/managers.py:ImportCoordinator` is a
  placeholder, not a second coordinator.
- `.xls` is explicitly unsupported until converted to `.xlsx`; XLSX templates
  in `templates/` are configuration, not executable importers.

## 7. Security and operational boundaries

MinerU is an externally managed installation. DrillMaster does not reinstall
it, merge its Python environment with DrillMaster's Python, or bundle it. The
adapter uses an argument list with `shell=False`, validates input suffixes,
uses isolated output directories, captures output, enforces timeout/exit/output
checks, and reports unavailable executable, Python, process, timeout,
unsupported format, malformed output, normalization, and DB errors separately.
Optional AI is advisory, disabled by default, local-only when enabled, and
never has direct DB access.

## 8. Packaging and release boundary

The application supports the repository's Windows PyInstaller/Inno Setup
packaging scripts. This Linux checkout cannot execute the Windows executable,
installer, clean-machine upgrade, or the user's Windows MinerU environment.
Those results must be recorded as BLOCKED/PENDING, never as automated PASS.
