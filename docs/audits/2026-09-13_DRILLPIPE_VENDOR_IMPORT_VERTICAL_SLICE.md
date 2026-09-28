# DrillPipe Vendor Excel → Persisted Reference Catalog — Vertical Slice + Forensics

Date: 2026-09-13
Branch: `arena/01a085e0-drill-master`
Baseline HEAD before this work: `aa84a35`

This report documents the single production-grade vertical slice
**vendor Excel workbook → canonical normalization → validation →
`DrillPipeReferenceRepository.import_specs()` → persisted authoritative
catalog → existing Quick Select → `wt_pipes` → `TorqueDragEngine`**, together
with the mandatory dead/duplicate/legacy forensics.

---

## A. Objective

Establish ONE trustworthy pipeline that turns a real, messy vendor drill-pipe
spreadsheet into persisted, canonical reference specs that flow through the
already-built selection/calculation path — without creating a second
source-of-truth, a parallel normalizer, or a generic import framework.

## B. Reconstructed end-to-end path (as built)

```
vendor .xlsx (sheet, e.g. "Aa")
  → core.engineering.drill_pipe_import.read_workbook_rows()      # openpyxl, values only
  → _detect_header_row() / _dedupe_headers()                     # skip title/blank rows
  → per data row: {header: value}
  → DrillPipeSpec.from_vendor_row(row, provenance=…)             # CANONICAL normalizer (unchanged)
        · numeric/unit coercion, conflict + invalid detection, issues[]
        · provenance = "<file> [<sheet>]", notes="row N"
  → DrillPipeReferenceRepository.import_specs(specs)             # existing tx-safe upsert
        · NEW / UNCHANGED / ENRICHED / CONFLICT / INVALID per row, isolated tx
  → drill_pipe_specs table (persisted authoritative catalog)
  → AddPipeDialog Quick Select (build_reference_choices, "◆ " prefix)
  → reference_component_fields() → wt_pipes component dict
  → TorqueDragEngine.calculate()                                 # 165.23 klbf ground truth
```

Connectivity was proven at runtime (in-memory DB) end-to-end, not inferred from
file names — see §K.

## C. Source-of-truth matrix (unchanged, re-confirmed)

| Source | Role | Authority |
|---|---|---|
| `drill_pipe_specs` (persisted repo) | Vendor/company reference catalog, `◆ `-prefixed in Quick Select | **AUTHORITATIVE** |
| `PIPE_DB` (built-in presets) | Generic nominal presets, no vendor identity | Fallback, additive, KEEP |
| `DrillPipe.xlsx` W13 viewer (`_drill_pipe_df`) | Display-only tab; disconnected from calc + repo | Non-authoritative (viewer) |

The new importer writes ONLY into the authoritative persisted catalog. It does
not touch `PIPE_DB` or the W13 viewer, so no competing source-of-truth is
created.

## D. New code (the slice)

- `core/engineering/drill_pipe_import.py` (new, Qt-free): workbook reader +
  header detection + `parse_workbook()` + `import_workbook()` orchestration.
  It contains **no** numeric/unit/identity logic — every row goes through
  `DrillPipeSpec.from_vendor_row` (no bypass).
- `tabs/w13_Engineering_Calculator.py`: "📥 Import Reference Catalog…" button on
  the Weight-methods drill-string panel + `_wt_import_reference_catalog()`
  handler. Single summary dialog, sheet picker only for multi-sheet files.
- `tests/test_drill_pipe_import.py` (new, 13 tests, Qt-free).

No new dependency: `openpyxl` (3.1.5) and `pandas` (2.2.3) already present.

## E. Field mapping (delegated to the canonical aliases)

manufacturer / model / OD / ID / nominal-weight(ppf) / grade / connection (plus
TJ OD/ID, drift, tensile). OD/ID normalized to inches (with optional
`od_unit`/`id_unit`, e.g. mm → in verified at 127 mm = 5.000 in). **Weight stays
canonical ppf** and is never passed through a mass conversion. Conflicting alias
columns (`OD` vs `OD (in)`) leave the field `None` + `CONFLICTING_SOURCE` issue
— never silently first-wins. Bool-as-number, zero/negative/non-finite rejected
as `INVALID_VALUE`. Unmapped columns preserved verbatim in `extra`.

## F. Row semantics (repository, unchanged)

NEW → insert; IDENTICAL → UNCHANGED; complements-missing → ENRICHED;
known+conflicting → CONFLICT (stored value untouched); invalid/no-identity →
INVALID. Verified idempotent re-import (no duplicates) and conflict isolation
(trusted stored ID kept, not overwritten).

## G. Transaction / failure isolation

`import_specs` commits each row in its own unit of work, so one malformed row
cannot corrupt already-accepted rows. Verified: a workbook with a valid row, a
`not-a-number` OD row, and a second valid row → 2 inserted, 1 invalid, catalog
count 2.

## H. Provenance

Reuses the existing `Provenance` model: `source="<workbook> [<sheet>]"`,
`notes="row N"` (1-based worksheet row), `status="unverified"` by default.
Nothing is fabricated — the source label is the real file name and sheet.

## I. UI (§14–15 compliance)

Select workbook → optional sheet pick (multi-sheet only) → batch import →
**ONE** summary `QMessageBox` distinguishing NEW / UNCHANGED / ENRICHED /
CONFLICT / INVALID and blank-rows-skipped. **No `QMessageBox` in a loop, no
per-row confirmation.** Reuses the existing `QFileDialog`/`QMessageBox` patterns
already in the tab; no separate import subsystem introduced.

## J. Forensics — dead / duplicate / legacy (§4, §19, §20, §23)

| Finding | Classification | Evidence | Active consumer | Safe to remove | Action |
|---|---|---|---|---|---|
| Prior DrillPipe Excel importer | **NONE EXISTS** | grep of `from_vendor_row`/`import_specs`/`DrillPipeReferenceRepository`; git history | — | — | Built the genuine gap (not a duplicate) |
| DDR/document import stack (`universal_import`, `excel_intelligence`, `excel_import_dialog`, `import_router/ir`, `ddr_import_service`) | ACTIVE (different domain) | DDR/document semantics, not reference master data | DDR flows | No | Left untouched — reuse would over-couple a simple reference read to a 2000-line DDR engine (§5 no-stacking honored by NOT stacking on it) |
| `core/excel_normalizer.py::normalize_xlsx` | ACTIVE, reusable | 52-line merged-cell/unhide cleaner | DDR import | No | Evaluated; not needed — read-only `iter_rows` + header detection is sufficient and lighter for this case |
| `_drill_pipe_df` W13 viewer | LEGACY-BUT-REQUIRED (display) | Reads `DrillPipe.xlsx` sheet "Aa" for a viewer only | W13 viewer tab | No | Kept; already relabeled as viewer in `aa84a35` |
| Abandoned/reverted import attempts | NONE | git log/grep | — | — | Answer to "did we already try and leave a failed impl?": **No** |

No dead code, shadow implementation or duplicate reference-data source was
found that is safe to delete as part of this slice. No deletions were made
(deletion requires proof of death; none met the bar).

## K. Verification (runtime, end-to-end)

- Messy synthetic sheet (title banner, blank leading + interior rows,
  unit-suffixed headers) → header detected at correct row; usable specs parsed;
  blank/invalid/no-identity rows surfaced (not silently dropped).
- Import → 2 NEW; re-import → 2 UNCHANGED, catalog stays 2 (no dup).
- Enrichment fills missing ID; subsequent conflicting ID → CONFLICT, stored
  value untouched.
- Selected imported spec → Quick Select (`◆ ` label, deterministic order) →
  component → `TorqueDragEngine` = **165.23 klbf** (ground truth preserved).
- mm → in conversion (127 mm = 5.000 in); ppf never mass-converted.

## L. Test + gate results

- New importer tests: 13/13 pass (Qt-free; no real `QDialog`, no segfault).
- Full suite: 1050 collected, exit 0 (1046 passed / 4 pre-existing skips).
  Baseline was 1033 passed / 4 skipped.
- `compileall` clean; E722 = 0; F821 = 0.
- Lint debt 5489 → 5496 (+7). All +7 are `F405`
  (`undefined-local-with-import-star-usage`) from the file's existing
  `from PyQt5.QtWidgets import *` convention (525 pre-existing F405 in the same
  file). New standalone modules pass ruff cleanly.

## M. Deferred / documented (audit-only, NOT built)

- §17 traceability id: smallest future seam = add an optional `reference_id`
  column to `wt_pipes` components; deferred (no current consumer).
- §18 schema/migration: `drill_pipe_specs` is auto-created for new tables in the
  FK-off upgrade tx; no Alembic in project. UNIQUE on `identity_fingerprint` is
  DB-enforced. Limitation documented, philosophy not expanded.
- §23 other hard-coded reference data (casing/BHA/bits/mud …): systemic pattern
  noted; a `ReferenceProvider` consolidation is the safest future direction but
  is intentionally NOT implemented (no proven multi-consumer need now, §27).

## N. Definition-of-Done check

One authoritative path ✅ · real vendor-style workbook imports ✅ · all rows via
`from_vendor_row` ✅ · persisted via `import_specs` ✅ · appears in Quick Select
without duplication ✅ · reaches `TorqueDragEngine` ✅ · invalid/conflict cannot
silently overwrite ✅ · provenance retained ✅ · deterministic order/identity ✅ ·
no competing source-of-truth added ✅ · forensics classified, no unsafe
deletions ✅ · full suite passes, no Qt segfault ✅ · no unrelated redesign ✅ ·
no unjustified dependency ✅.
