# Release notes — import consistency audit (2026-09-06)

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

## Certification status

- Source compile and pure-Python IR/review smoke checks: **PASS** in this
  workspace.
- Full pytest suite: **NOT EXECUTED**; `pytest` and `openpyxl` are unavailable
  in the active sandbox runtime.
- Repository OEOC-208 fixture: present, but no real extraction PASS is claimed
  without the dependency-complete test environment.
- User OEOC-201 Excel: **BLOCKED / not available**.
- User Windows MinerU 3.4.5/PDF: **BLOCKED / not available**.
- Python 3.12: **BLOCKED / not executed**.
- Windows PyInstaller/Inno Setup and clean-machine checks: **BLOCKED / not
  executed**.

## Remaining limitations

The PDF Camelot/PyMuPDF/OCR path is explicitly a legacy fallback with weaker
PDF-native provenance and is not equivalent to a real MinerU certification.
WITSML/LAS and legacy XLS remain unsupported contracts. Review data is carried
in the import report/export and does not have a dedicated review ORM table.
