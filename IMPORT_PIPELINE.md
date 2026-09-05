# DrillMaster — Import Pipeline Documentation

> **Version:** 1.0 — Audit Baseline (2026-08-24)

---

## 1. Pipeline Overview

The import pipeline transforms raw Excel/PDF files into validated, normalized data stored in the database. It is designed to handle real-world drilling spreadsheets with irregular layouts, merged cells, multi-row headers, and inconsistent naming.

```
Excel/PDF → Scan → Classify → Map → Normalize → Validate → Review → Commit
```

---

## 2. Stage 1: Workbook Scanning

**File:** `core/universal_import.py` — `WorkbookScanner`

### 2.1 File-Level Metadata
- File name, size, type (.xlsx, .xls)
- Sheet count, hidden sheets
- Total merged ranges, total formula count
- Overall density (non-empty / total cells)

### 2.2 Sheet-Level Analysis
For each sheet:
- Row count, column count
- Hidden state
- Merged cell ranges
- Hidden rows and columns
- Used range coordinates
- Non-empty cell count, total cells
- Density (populated / area)
- Empty cell ratio
- Formula count

### 2.3 Table Detection

The table detector identifies table regions within each sheet using:

1. **Row Band Detection:** Groups consecutive rows with ≥2 populated cells, splitting on ≥2 consecutive empty rows
2. **Column Gap Detection:** Identifies side-by-side tables by detecting gaps of ≥3 empty columns
3. **Header Detection:** Analyzes first 3 rows for text ratio > 0.6 to identify header rows (supports 1-3 row headers)
4. **Title Detection:** Looks 1-2 rows above the first header for merged or sparse title rows
5. **Density Calculation:** Row density (data cells / possible cells) and column density (columns with data / total columns)
6. **Type Consistency:** Per-column analysis of numeric vs date vs text dominance

### 2.4 Table Types
- **Vertical:** Headers in row, data in rows below (most common)
- **Horizontal:** Headers in column, data in columns to the right
- **Nested:** BHA, bit records with sub-tables
- **Continuation:** Long tables split across page breaks

### 2.5 Column Profiling

For each column in a detected table:
- Header text
- Sample values (first 5)
- Data type (numeric, date, text)
- Min/max values (for numeric)
- Blank ratio
- Density
- Confidence score

---

## 3. Stage 2: Sheet Classification

**File:** `core/universal_import.py` — `SheetClassifier`

### 3.1 Classification Categories

| Category | Keywords |
|----------|----------|
| Daily Report | daily, ddr, report, remark, operation, activities, 24h, rig activity |
| Mud | mud, fluid, rheology, pv, yp, gel, chemical, funnel, filtrate |
| Drilling | drilling, parameter, wob, rpm, torque, rop, spp, pump |
| BHA | bha, bottom hole assembly, component, stabilizer, drill collar, dc, hwdp |
| Bit | bit, iadc, nozzle, tfa, bit run, bit record |
| Survey | survey, md, inclination, azimuth, tvd, north, east, dls, deviation |
| Trajectory | trajectory, wellbore, plan, vs, hd, section view, plan view |
| Safety | safety, hse, lti, incident, near miss, drill, h2s, fire, bop drill |
| BOP | bop, blow out preventer, wellhead, ram, annular, koomey, pressure test |
| Logistics | logistics, pob, personnel, fuel, water, bulk, inventory, transport |
| Services | service, company, contractor, third party |
| Cost | cost, afe, expense, budget, invoice, daily cost |
| Planning | plan, lookahead, forecast, 7 days, schedule |
| Reference | reference, lookup, master, config, template, code, activity code |

### 3.2 Classification Signals
1. Sheet name (highest weight)
2. Table headers
3. Table titles
4. Cell content samples
5. Data type patterns (e.g., MD + Inc + Azi → Survey)

---

## 4. Stage 3: AI-Assisted Mapping

**File:** `core/ai_import_mapper.py` — `AIImportMapper`

### 4.1 Architecture
- Uses Ollama local LLM (configurable model)
- Sends compact context (table title, headers, sample values)
- Returns proposals with confidence scores
- Validates against canonical schema

### 4.2 Proposal Format
```json
{
  "field": "mud_report.mw",
  "source_sheet": "Daily Report",
  "source_row": 17,
  "source_column": 8,
  "value": 10.2,
  "confidence": 0.96
}
```

### 4.3 Validation Rules
- Field must be in canonical schema
- Source sheet, row, column must be present
- Value must not be null
- Confidence must be between 0 and 1

### 4.4 Fallback
If AI is unavailable, mapping falls back to keyword-based heuristics.

---

## 5. Stage 4: Unit Normalization

**File:** `core/unit_manager.py` — `UnitManager`

### 5.1 Supported Conversions

| Quantity | From | To (Canonical) | Factor |
|----------|------|----------------|--------|
| Length | ft | m | 0.3048 |
| Length | in | m | 0.0254 |
| Pressure | bar | psi | 14.5038 |
| Density | SG | ppg | 8.3454 |
| Flow Rate | L/min | gpm | 0.2642 |
| Temperature | °F | C | (x-32)×5/9 |
| Torque | N·m | ft·lbf | 0.7376 |
| Force | kN | klbf | 0.2248 |
| ROP | ft/hr | m/hr | 0.3048 |

### 5.2 Preservation Record
Every conversion creates a `UnitRecord`:
```python
UnitRecord(
    field="mud_report.mw",
    quantity="density",
    source_unit="sg",
    canonical_unit="ppg",
    original_value=1.50,
    normalized_value=12.52,
    conversion_rule="1.50 SG * 8.3454 = 12.52 ppg",
    confidence=1.0
)
```

---

## 6. Stage 5: Validation

### 6.1 Validation Rules
- Required fields (critical=True in canonical schema)
- Numeric range checks
- Date format validation
- Cross-field consistency (e.g., depth_in < depth_out)
- Duplicate detection

### 6.2 Validation Output
```json
{
  "level": "error",
  "sheet": "Daily Report",
  "row": 17,
  "field": "mud_report.mw",
  "value": -5.0,
  "message": "Mud weight cannot be negative"
}
```

---

## 7. Stage 6: Atomic Database Commit

**File:** `core/database.py` — `DatabaseManager.save_imported_multi_tab_data_atomic()`

### 7.1 Transaction Model
```
BEGIN TRANSACTION
    Save DailyReport
    Save Surveys
    Save POB Records
    Save Service Companies
    Save Casing Report
    Save Cement Report
    Save Bit Report
    Save BHA Report
    Save Bulk Materials
    Save Fuel/Water Inventory
    Save Safety Report
    Save BOP Components
    Save Waste Records
    Save Cost Records
    Save Equipment Logs
    Save Downhole Equipment
COMMIT (or ROLLBACK ALL)
```

### 7.2 Guarantees
- No partial imports (all or nothing)
- No orphan child data
- Previous report data preserved via snapshot
- Rollback restores exact pre-import state

---

## 8. Known Limitations

1. **No data lineage table:** Imported values are not linked back to source cells
2. **No human review UI:** Low-confidence mappings are not presented for manual review
3. **Limited PDF support:** Only text-based PDFs (no OCR)
4. **No LAS/WITSML import:** Placeholders exist but not implemented
5. **AI mapping requires Ollama:** No fallback to cloud AI services


---

## 9. Company-Template Import Path (verified 2026-08-31)

### Flow (the ONLY import path for company workbooks)
```
Workbook sheets -> _auto_match_template(sheet names)
                 -> templates/OEOC_DDR_v3.json (anchored sections)
                 -> ExcelIntelligence.extract()  -> canonical JSON
                 -> ExcelImportDialog._do_import (atomic)
                 -> SQLite (all-or-nothing)
                 -> existing UI tabs via DB getters
```
- Template match is GENERIC (sheet-name based). No company-specific code
  branches; company-specific layout lives in the JSON template.
- `_unified_import` runs the template engine first and only falls back to
  heuristic smart-detection when no template matches.

### Canonical model
- `core/canonical_schema.py` FIELD_SPECS: 325 fields (aliases, engineering
  bounds, quantity + canonical unit, criticality).
- Scalar extraction: preferred cell (template anchor) > merge > exact label
  > alias > fuzzy. Label fallback is column/row-locked to the template anchor
  when the anchor is near the label, so neighbouring tables (e.g. cement
  additives vs. safety drills) never contaminate.
- Numeric normalizers: '17-1/2"' -> 17.5, '18/32"' -> 0.5625, '3K' -> 3000.
- Placeholders: "N.C" on numeric fields -> NULL + `fl_source` + metadata
  source_tokens (missing/N.C/zero distinguishable). "-", "--", "n/a" on
  numeric columns -> NULL (DB layer `coerce_model_values`).
- Units: PCF kept native for the Mud UI; SG/ppg converted via UnitManager
  with original value + unit preserved (mw_original/mw_unit).

### Atomic persistence (core/database.py save_imported_multi_tab_data_atomic)
Sections: surveys, POB breakdown (logistics -> ServiceCompanyPOB),
service_companies, lookahead (seven_days_lookahead), casing, cement, bit,
BHA, bulk materials, fuel/water, safety (safety_reports; drill dates
Gregorian-only, Jalali preserved as observations text), BOP components
(3K -> 3000 psi, component_type inferred from name, non-numeric rows
skipped), waste, cost, equipment, downhole.
Daily Report + Mud + Drilling Parameters + time logs are saved by the dialog
inside the same atomic block; the saver filters to model columns.

### Additive schema migration
`DatabaseManager.initialize` -> `_apply_safe_schema_upgrades`: ALTER TABLE
ADD COLUMN only (pump_liner_size), idempotent, never deletes/recreates.

### Verified against the REAL workbook (2026-08-31)
See ENGINEERING_AUDIT.md section H for the full value matrix. Import result:
102 records, 0 failures; golden regression in `tests/test_real_oeoc_golden.py`
(32 tests) and `tests/test_multi_company_template.py`.

### Known limitations
1. 24h time-log rows stored as `timedelta` are skipped (7/10 stored; morning 6/7)
2. Lookahead rows without activity text skipped (11/13 stored)
3. Service NPT not mirrored into npt_reports
4. UI verification is headless (no libGL in CI sandbox)

---

## 10. External MinerU Document Intelligence (Phase)

MinerU is an optional external engine. DrillMaster never vendors the MinerU
package, its Python environment, or its models. The adapter is
`core/mineru_engine.py`; it is independent of PySide6 and SQLite.

### 10.1 Detection and configuration

Detection order is:

1. `DRILLMASTER_MINERU_EXECUTABLE` / `MINERU_EXECUTABLE`
2. `DRILLMASTER_MINERU_PYTHON` / `MINERU_PYTHON` (invoked as
   `python -m mineru`)
3. `mineru` or `mineru.exe` on `PATH`
4. An existing user-home development virtual-environment convention

The following settings are supported. The `MINERU_*` aliases are accepted for
portable scripts:

| Setting | Default |
|---|---|
| `DRILLMASTER_MINERU_ENABLED` | enabled when MinerU is detected |
| `DRILLMASTER_MINERU_EXECUTABLE` | auto-discovery |
| `DRILLMASTER_MINERU_PYTHON` | unset |
| `DRILLMASTER_MINERU_BACKEND` | `hybrid-engine` |
| `DRILLMASTER_MINERU_METHOD` | `auto` |
| `DRILLMASTER_MINERU_OUTPUT_DIR` | isolated temporary directory |
| `DRILLMASTER_MINERU_TIMEOUT` | `600` seconds |
| `DRILLMASTER_MINERU_KEEP_OUTPUT` | `false` |

The adapter provides `is_available()`, `get_version()`, `health_check()`,
`parse_file()`, and `parse_batch()`.

### 10.2 Invocation and process safety

For MinerU 3.x CLI installations the adapter invokes the configured external
launcher using an argument list equivalent to:

```text
mineru -p INPUT -o OUTPUT -b hybrid-engine -m auto
```

The actual executable is selected by configuration/discovery. `shell=False`,
argument-list invocation, captured UTF-8 output, an explicit timeout, exit
code checks, isolated output directories, and per-file batch results prevent
shell injection and cross-file contamination.

### 10.3 Routing

```text
Known structured XLSX template -> ExcelIntelligence -> canonical JSON
Unknown/document-style XLSX     -> MinerU -> normalizer -> canonical schema
PDF                              -> MinerU -> normalizer
                                  -> Camelot -> PyMuPDF -> Tesseract fallback
DOCX/PPTX/Image                 -> MinerU -> normalizer -> canonical schema
CSV                              -> existing CSV -> XLSX -> existing importer
```

Known structured workbooks are matched before MinerU and do not pay a MinerU
startup cost. A MinerU failure on unknown XLSX falls back to the existing
smart/template importer. A MinerU failure on PDF is explicitly logged and
falls back to the existing three-tier PDF path. DOCX/PPTX/Image parsing
returns an actionable error when MinerU is unavailable because no equivalent
existing DB importer exists.

### 10.4 Intermediate representation

MinerU output is not treated as canonical JSON. `MinerUDocument` contains:

- pages and page text
- headings
- text blocks
- tables and rows
- extracted assets
- backend/method metadata
- raw output file names

Each extracted item carries `Provenance`: source file, page/sheet when MinerU
provides it, row/column when available, bounding box when available,
extraction method, and confidence. Missing values remain `None`; the adapter
does not invent coordinates, page numbers, units, dates, depths, pressures, or
well values.

`DocumentNormalizer` resolves only unambiguous labels through the existing
`core/canonical_schema.py` registry. Numeric literals are converted only when
the value is unambiguously numeric; units are never inferred or converted.
Ambiguous/unknown values remain out of the canonical payload and become review
warnings. Existing scalar report sections retain the dictionary shape expected
by the database layer; true table collections remain lists.

The existing `FieldSpec` bounds are applied to values that are safely numeric.
Validation errors stop the MinerU route before database import. The normalized
payload is passed to the existing preview and
`DatabaseManager.save_imported_multi_tab_data_atomic()` boundary; MinerU has
no database dependency and never writes SQLite directly.

### 10.5 UI and AI boundaries

The Import Dialog uses the existing `FunctionWorker` QThread architecture for
MinerU batch execution. Status messages identify engine detection, MinerU
parsing, normalization, validation, preview, and atomic import. The preview
shows MinerU source/backend/method/page/table/field counts and warnings.

`core/ai_import_mapper.py` remains optional and advisory. MinerU does not call
Ollama, Qwen, or RAG. Retrieval and embeddings remain future phases.
