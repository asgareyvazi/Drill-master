# DrillMaster — Scope Matrix (2026-09-09)

Per-area status against the master handoff requirements. Statuses are
`PASS` / `BLOCKED` / `NOT VERIFIED` / `OUT OF SCOPE` with the *actual* evidence
command. This file is updated as phases complete; it never contains a status
without a command or test name behind it.

Legend for this session: baseline (before any change) → current.

---

## A. Domain areas

| Area | Baseline status | Evidence (baseline) | Notes / gaps |
| --- | --- | --- | --- |
| Well Identity | PARTIAL | `core/database.py:166` Well(id,name,unique code); tests `test_p0_well_identity.py` pass | Rig is an attribute (`rig_name`) not identity ✔. Identity = id+code; no alias/history table; no normalisation service. Reimport dedup handled in `ddr_import_service` `_ensure_well` — see `test_production_import_guarantees.py` (passing). |
| Alias/Rename | NOT VERIFIED (as a feature) | grep: no `WellAlias`/`alias` model; rename path not covered by a dedicated test | No alias mechanism exists to verify. Candidate Phase 2 item. |
| Wellbore | OUT OF SCOPE (this session) — entity does not exist | no `wellbore` table in `core/database.py`; grep confirms | Documented in MASTER_FORENSIC_AUDIT §4. Introducing a persistent Wellbore entity is a schema migration (schema v3) — scheduled, not silently attempted. |
| Section | PASS (unit level) | `tests/test_p0_well_identity.py`, section FK cascade tests pass | Belongs to exactly one well ✔ at ORM level. |
| DDR | PARTIAL | `DailyReport` model; `test_ddr_*` files pass | `section_id` nullable — a DDR may exist without a section (by design for header-less imports); no cross-well consistency check at DB level. |
| Workover | NOT VERIFIED | no `Workover` model/flag; `Well.well_type`/`purpose` strings only | No distinct workover modeling found. |
| Sidetrack | PARTIAL | name-based: `"ST"` tokens kept distinct in import dedup (test_real_oeoc_golden asserts separate wells) | Sidetrack-as-wellbore requires the Wellbore entity (not present). |
| Schematic | PARTIAL | `tabs/w3b_wellbore_schematic_tab.py` + `core/wellbore_schematic_engine.py`; R18 round-trip tests in `test_r18_r19_save_preservation.py` pass | Per-well rows with nullable report linkage; "current state + history" semantics rely on `report_date` ordering. No-fabrication rule enforced by tests (`test_real_3d_draw_boundary_and_no_data`). |
| BHA | PARTIAL | `BHAReport.bha_data_json` per report; R19 legacy protection `core/legacy_bha.py`, tests pass | Longitudinal run identity lives inside JSON, not as rows. R19 protections intact (tests green). |
| Bit | PARTIAL | `BitReport.bit_records_json`; golden `TestBitRunImport` covers field mapping | Same JSON pattern; cumulative-run identity is import-time logic. |
| Inventory | PARTIAL | `core/mud_ledger.py` ledger math + `BulkMaterials`; NULL≠0 covered by golden tests (KCL, FL NULL assertions) | Ledger is service-level over daily rows; no material master/transaction tables. |
| Cost | PARTIAL | `CostRecord` (planned/actual/variance/AFE); `test_r18_r19…` and w16 tests pass | No Estimate/Forecast columns on CostRecord; `DailyReport.forecast` is free text. Labelling rules verified in `tabs/w16_Cost_Management.py`. |
| KPI | BLOCKED (canonicalization) | no single service; formulas in `core/operations_intelligence.py`, `tabs/w12_Analysis.py:1211+`, `tabs/home_tab.py` | See `KPI_MATRIX.md`. A canonical KPI service is a Phase 4 deliverable. |
| Home | PARTIAL | `tabs/home_tab.py` shows recent wells/project progress/status | Not yet an executive KPI dashboard; no duplicate tab created. |
| Analysis | PARTIAL | `tabs/w12_Analysis.py` KPI cards + analysis engines | Uses its own SQL KPIs (documented in KPI_MATRIX). |
| Planning | PARTIAL | `PlannedActivity`, `WellPlan`, `core/actual_vs_plan.py`; `test_p0_*` planning tests pass | PLAN vs FACT separation enforced in `actual_vs_plan`; versions via `WellPlan`. |
| Import | PASS (after Phase 1) | atomic staged `_do_import` with rollback; golden tests now run under **real Qt**; full suite green | P0 defects fixed: CodeResolver NameError, validator duality, unsafe test construction; 43 dead tuple-key cache reads revived in the retired-but-public profile engine. |
| Selection context | PASS (hardened this session) | `tests/test_selection_manager_context.py` (6/6) | Parent-change child invalidation already correct; new defensive guard rejects cross-well section/report selections when the payload carries an explicit `well_id`. |
| R18 (dirty/no-change save contract) | PASS | `tests/test_r18_r19_save_preservation.py` — all pass in baseline | Must stay green after every change (guard: full suite). |
| R19 (legacy BHA protection) | PASS | same file | ditto |

## B. Structural debt (Phase 5 scope)

### B.1 Bare `except:` — 40 sites at baseline → **0 remaining (all fixed this session)**

Every site was read individually and narrowed to the exception types actually
raiseable, preserving the intended fallback and adding comments/logging at the
non-obvious sites:

* `core/profile_import_engine.py` ×6 — one of these hid the CodeResolver
  NameError (P0-1); two hid the dead tuple-key cache readers (P0-7 below).
* `core/report_engine.py` ×2 (HTML export OSError)
* `dialogs/` ×9 (time/float/date parse fallbacks; session close)
* `tabs/` ×23 (table-cell parse fallbacks, delete-rollback guards, totals)

Discovered-and-fixed real bugs behind broad excepts (each has regression
coverage in `tests/test_p0_phase1_regressions.py`):
1. CodeResolver NameError → silent NPT contractor loss.
2. Dead tuple-key cache readers: `_configure_workbook_code_catalog`,
   `_extract_embedded_mud_chemicals`, 43 raw reads in
   `_extract_embedded_ddr_data` — all returned None against the
   `{row: {col: value}}` cache produced by `_build_unmerged_cache`.
3. `QAction` imported from QtWidgets (moved to QtGui in Qt6) in
   `core/hierarchy_operations.py` and `core/toolbar_manager.py` — masked by
   the DISPLAY-based test skip.

### B.2 Duplicate/legacy API

* `core/validators.py ImportValidator` — RESOLVED this session: now a real,
  documented deprecated subclass of the authoritative
  `core.import_quality.ImportValidator` (was a false-"delegating" wrapper with
  an incompatible signature). Regression: `tests/test_p0_phase1_regressions.py`.

### B.3 `core/repositories/` — disconnected layer

Production imports: none (verified by grep). It is option **B (abandoned)** in the
handoff's classification, but it is exercised by tests as a parallel memory-backed
implementation. Safe handling: kept as-is this session (removal is a behavior risk
with zero payoff now); treated as a deprecated experimental layer; do not extend it.

### B.4 God files

`core/database.py` 8575 lines; `tabs/w13_Engineering_Calculator.py` 4275;
`main_window.py` 2975. No wholesale rewrite; incremental extraction only when a
behavior change requires touching the area anyway.

### B.5 Wildcard imports (F403 ×92 / F405 ×4382)

No mass conversion. New code must not add star imports; opportunistic conversion
when files are touched for other reasons. CI enforces a blocking ratchet
(`.github/ruff-debt-ceiling.txt` = 5489 total findings; may only shrink).

## C. Environment / delivery

| Item | Status | Evidence |
| --- | --- | --- |
| Ruff defect gate (E722, F821) | PASS (0 findings; baseline 40 + 1) | `ruff check --select E722,F821 core dialogs tabs main_window.py app.py tests` |
| Ruff full project config | DEBT-RATCHETED (5489, baseline 5550) | `ruff check --statistics core dialogs tabs tests` + CI ratchet |
| CI workflow | ADDED (`.github/workflows/ci.yml`); first remote run NOT VERIFIED | YAML + ratchet arithmetic validated locally |
| Windows GUI | NOT VERIFIED | no Windows environment in this sandbox |
| Installer | NOT VERIFIED | packaging/ exists; `test_packaging_smoke` skips (no bundle) |
| Local AI / MinerU | NOT VERIFIED | integration tests are opt-in and skipped |
| PDF export (real printer) | NOT VERIFIED | QtPrintSupport imports headless; no physical output verified |
