# DrillMaster import audit — 2026-09-06

## Scope and acceptance boundary

This audit covers the production daily-report import boundary on branch
`arena/01a07094-drill-master`. The checkout contains and executes the real
workbook `08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx`; the reported
OEOC-201 PDF/XLSX pair is not present in this checkout. Consequently the
Excel route is real-document validated, while the reported PDF failure and a
real MinerU 3.4.5 run remain pending on the user's Windows installation.

## Canonical architecture

1. `core/import_router.py` is the single format router. Known structured XLSX
   workbooks go directly to `ExcelIntelligence`; PDF and document-style inputs
   use the external MinerU adapter, with the explicit PDF/unknown-XLSX
   fallbacks retained.
2. `core/import_ir.py` is the lossless common raw IR. It records source file,
   sheet/page, row/column/cell, hidden/merged/formula state, table rows,
   text blocks, and coordinates without mapping or coercion.
3. Excel and MinerU adapt into this IR before canonical mapping. Canonical
   aliases/types/criticality remain in `core/canonical_schema.py`.
4. `core/value_normalizer.py` is the shared typed boundary for numbers,
   integers, decimals, strings, dates, times, datetimes, durations, booleans,
   enums, and engineering quantities. Unit conversion remains explicit in
   `core/unit_manager.py`; no unit is inferred from an absent source token.
5. `ImportReviewMatrix` and `ReviewItem` in `core/import_quality.py` are the
   one review contract. Legacy `value`, `source_value`, and
   `canonical_field` aliases are accepted and synchronized with
   `original_value`, `normalized_value`, `target_field`, expected type,
   status, confidence, reason, correction, and source location.
6. Persistence is downstream of typed normalization. Malformed numeric text
   is represented as `NULL` at the model boundary and its original token is
   retained in review/source-token lineage; it is never converted to zero.
   `DrillingParameters` now applies the same safe model coercion on insert and
   update.

## Reported failure regressions

- **Excel review crash:** fixed. The producer payload's `value`, `status`,
  `reason`, and certainty metadata now satisfy the single `ReviewItem`
  contract. A permanent regression covers this exact legacy payload shape.
- **MinerU `Drilling Data` numeric conversion:** fixed defensively. Titles and
  repeated headers are classified before row mapping; unsafe numeric values
  become `NULL` plus a review item containing original value, expected type,
  and page/row/column provenance. A permanent Markdown fixture reproduces
  `Drilling Data` in a drilling-parameter numeric cell and proves it cannot
  reach a numeric database value.

## Preservation and error behavior

Merged cells, hidden rows/columns, formula text, Excel date/time/timedelta
values, multi-row/side-by-side table records, repeated headers, notes,
footers, and placeholder rows are retained or classified in the common IR.
Safe rows continue when an individual cell requires review. Fatal structural
validation still stops the import boundary and the existing snapshot/rollback
path prevents partial report persistence. MinerU remains an optional,
subprocess-only external process with executable discovery, version/health
checking, timeout, output validation, per-file batch isolation, and no SQLite
access.

## Validation status

The temporary test environment used DrillMaster dependencies but did **not**
install or copy MinerU. Results:

- `python -m compileall ...`: passed.
- `pytest -q`: **494 passed, 5 skipped, 4 warnings**.
- `python verify_release.py`: passed with the same full-suite count.
- `tools/static_audit.py`: completed informational audit; it reports existing
  legacy counts (94 wildcard imports, 45 bare except handlers, 141 duplicate
  method names) and does not fail the build.
- Real Excel: the repository's real OEOC-208 workbook regression suite passed.
- Real reported PDF/XLSX pair: unavailable here; not claimed as executed.
- Real MinerU 3.4.5, the user's Windows executable/environment, and Python
  3.12 compatibility: not executable from this Linux checkout; not claimed as
  PASS.

## Remaining limitations

The reported OEOC-201 documents and the user's separately managed MinerU
installation must still be run end-to-end by the user. That run must capture
the official command, executable/version, Python runtime, generated Markdown/
JSON/assets, table classification, review matrix, normalized canonical data,
unit lineage, and database result. Existing informational legacy static-audit
findings and five environment-gated skips are not import-data failures.
