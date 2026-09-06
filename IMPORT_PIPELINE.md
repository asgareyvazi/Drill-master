# Import pipeline and entry-point matrix

**Audit date:** 2026-09-06
**Canonical persistence boundary:** `ExcelImportDialog._do_import()` plus
`DatabaseManager.save_imported_multi_tab_data_atomic()`.

## 1. Supported pipeline

```text
route_file
  Excel template match -> openpyxl -> raw_document_from_workbook
  PDF/document/image  -> MinerUAdapter -> MinerUDocument
                         -> raw_document_from_mineru
  both                -> classification/mapping
                         -> FIELD_SPECS / contextual aliases
                         -> value_normalizer
                         -> UnitManager where an explicit source unit exists
                         -> validation and ReviewItem
                         -> preview/edit/confirmation
                         -> atomic DB save
```

The raw IR is lossless and source-oriented. It is not canonical JSON and does
not perform guessing. `ExcelIntelligence` consumes its IR cache, not a second
workbook walk. `DocumentNormalizer` consumes the MinerU-adapted IR and uses the
same schema and typed normalizer downstream.

## 2. Entry-point matrix

| Entry point / format | Common IR | Shared typed normalizer | DB write | Fallback/status |
| --- | --- | --- | --- | --- |
| `core.import_router.route_file` | route only | no | no | known XLSX -> Excel; PDF/document/image -> MinerU; CSV -> converter; XLS -> unsupported |
| `ExcelIntelligence.extract()` | **yes**, workbook adapter | **yes**, `normalize_for_field` | no | no alternate mapper inside extractor |
| `MinerUAdapter.parse_file()` | produces external document; adapter to IR occurs in normalizer | no by itself | no | distinct errors for unavailable/executable/input/format/process/timeout/output |
| `DocumentNormalizer.normalize()` | **yes**, `raw_document_from_mineru` | **yes** | no | ambiguous/invalid values remain review/NULL; never guessed |
| `ExcelImportDialog._run_import_pipeline()` | yes for successful Excel/MinerU paths | yes downstream | **yes**, after preview | PDF legacy conversion can feed canonical Excel template only; no profile fallback |
| `ExcelImportDialog._do_import()` | receives canonical payload + review report | validation and unit boundary | **yes**, snapshot/rollback + atomic multi-tab save | no partial success is reported as success |
| `SmartTemplateDialog` (manual UI) | not in its historical scanner | partial local legacy rules | no direct write; caller must use shared save | explicit manual/legacy route; profile fallback is disabled and is not called by universal import |
| `ProfileImportEngine.analyze_and_extract()` | no | no | no | compatibility analysis only; direct `import_to_db()` raises `LEGACY_DIRECT_DB_IMPORT_DISABLED` |
| `core.universal_import.py` | no common IR in scanner | no shared persistence normalizer | no | scanner/classifier support for legacy UI/tests only |
| `document_import.csv_to_xlsx()` | no (converter only) | no | no | conversion-only; universal route stops if no canonical template follows |
| `document_import.pdf_to_xlsx()` | no (legacy converter) | no | no | explicit PDF fallback; output must re-enter canonical Excel template path |
| `import_adapters.pdf_tables.py` | no | no | no | legacy Camelot/PyMuPDF/OCR helper, not a direct DB route |
| `core.witsml_import.WITSMLImportEngine` | no | no | no | XML validation/placeholder; actual WITSML import unsupported |
| `core.managers.ImportCoordinator` | no | no | no | placeholder returning “coordinated in dialog”; not a second service |
| `templates/*.json` | configuration consumed by Excel extractor | extractor applies shared normalizer | no | no executable fallback |
| `ReviewItem` / `ImportReviewMatrix` | carries IR-derived provenance | records normalization/validation state | no ORM write | serialized with `to_dict/from_dict`; preview edits are applied before save |
| `LineageTracker` / professional export | consumes lineage/review metadata | no mapping | export only | source provenance remains unknown when unavailable |
| `core.db_services` / service repositories | domain CRUD used by application tabs | no import IR/normalizer | **yes when called directly**, not an import route | must not be mistaken for the import coordinator |
| `core.excel_normalizer.py` | legacy workbook cleanup utility | no shared import mapping | no | compatibility helper; canonical route is Excel IR |
| `core.import_profiler.py` | timing/diagnostic instrumentation | no | no | observability only |
| `tools/mineru_integration.py` | developer integration harness | no | no | diagnostic/manual, not production persistence |

## 3. Format behavior

### Excel/XLSX/XLSM

A matching JSON template selects `ExcelIntelligence`. Workbook cells are
adapted once, including formulas, hidden/merged state, coordinates and formal
table headers. Preferred anchors, contextual aliases, exact labels and fuzzy
candidates are scored; low confidence, conflicts, bounds failures and
non-numeric tokens become review states. `.xls` is rejected rather than
silently converted by an unvalidated library.

### PDF and document-style input

MinerU is the primary parser and runs out of process using the official CLI
shape:

```text
mineru -p INPUT -o OUTPUT -b BACKEND -m METHOD
```

The configured backend/method defaults are `hybrid-engine`/`auto`. The actual
configured executable or separately managed Python runtime is used; DrillMaster
does not install MinerU or merge environments. The adapter parses Markdown,
JSON, HTML tables and assets, adapts them to the common IR, normalizes only
unambiguous fields, and sends the result to the same preview/atomic boundary.

When MinerU is unavailable for a PDF, the existing Camelot -> PyMuPDF -> OCR
converter is an explicitly labeled fallback. It is not a MinerU PASS and has
weaker PDF-native provenance. It can continue only if the generated workbook
matches a canonical Excel template; otherwise the import stops before DB write.

### CSV

CSV conversion supports UTF-8 and Persian-compatible encodings and creates an
XLSX intermediate. It is not itself canonical mapping. Without a matching
canonical template the route stops before persistence; it does not silently
invoke Smart Template/profile defaults.

### WITSML/LAS and legacy XLS

WITSML is currently a placeholder/unsupported import contract. LAS and legacy
XLS are not claimed as implemented import paths. Unsupported formats produce a
structured route error.

## 4. Error and atomicity behavior

Errors are distinguished as route/unsupported, invalid input, unavailable
external executable/Python, process nonzero, timeout, malformed/missing output,
normalization/schema validation, review rejection, and DB persistence failure.
The dialog reports the engine and stage in UI status. Atomic multi-tab failure
rolls back the transaction and the dialog restores/removes the report snapshot;
the old per-table rescue path has been removed.

No missing report date, unit, depth, MW, pressure, drilling parameter, company,
or provenance value is synthesized. A user correction is explicit in the
review matrix and is the only way an ambiguous value is accepted.
