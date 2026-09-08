# Release notes — import consistency audit (2026-09-08)

## Branch

`arena/01a07094-drill-master`

## Targeted changes

- Repaired `core/import_ir.py` into a serializable lossless contract for
  source file/page/sheet/table/row/column/cell, headers, section titles, units,
  coordinates, original/normalized values, extraction method, confidence,
  validation state, and review state.
- Made `ExcelIntelligence._build_cache()` and merge analysis consume the common
  workbook IR instead of rereading openpyxl cells.
- Extended Excel extraction results and MinerU normalization to retain source
  values separately from normalized values and update IR state.
- Completed `ReviewItem` serialization/deserialization and preview edit
  propagation for mapping, value, unit, accept/reject/ignore decisions.
- Disabled Smart Template's silent `ProfileImportEngine` fallback and disabled
  the profile engine's direct DB write API.
- Removed the database compatibility method's non-atomic per-table rescue loop;
  the compatibility name now delegates only to the atomic saver.
- Added environment-gated real DDR Excel/PDF acceptance tests using
  `DRILLMASTER_TEST_DDR_XLSX` and `DRILLMASTER_TEST_DDR_PDF`.
- Reconciled architecture, pipeline, AI, readiness, testing, README, and audit
  documentation with source behavior.
- Corrected ReviewItem provenance/entity/type/mapping normalization across
  field, time-log, lookahead, BOP, and survey persistence rows; retained
  same-value duplicate provenance explicitly.
- Corrected template-anchor precedence so placeholders and empty note anchors
  cannot be replaced by diagonal/fuzzy values; added real-workbook golden
  counts, semantic validation, and a complete 79-item baseline/current audit.
- Added PDF density unit safety (`10.2` is not ppg without explicit source
  evidence), failed MinerU output cleanup, and Windows acceptance sequencing.

## Certification status

- Source compile and pure-Python IR/review smoke checks: **PASS** in this
  workspace.
- Dependency-backed Python 3.11 complete suite: **530 passed, 8 skipped, 0
  failed/errors** (538 collected); real repository workbook audit: **PASS for
  source-level evidence**. This is not Windows/Python 3.12 acceptance.
- Repository workbook fixture: audited; this is not AZNS-12 production evidence.
- **AZNS-12 production asset not present in repository/workspace.**
- User Windows MinerU/PDF: **BLOCKED / not available**.
- Python 3.12: **BLOCKED / not executed**.
- Windows PyInstaller/Inno Setup and clean-machine checks: **BLOCKED / not
  executed**.

## Remaining limitations

The PDF Camelot/PyMuPDF/OCR path is explicitly a legacy fallback with weaker
PDF-native provenance and is not equivalent to a real MinerU certification.
WITSML/LAS and legacy XLS remain unsupported contracts. Review data is carried
in the import report/export and does not have a dedicated review ORM table.
