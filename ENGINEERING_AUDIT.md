# DRILLMASTER — FULL ENGINEERING AUDIT REPORT

> **Date:** 2026-08-29
> **Branch:** arena/01a032f0-drill-master
> **Auditor:** Multi-role (Drilling Engineer + Software Architect + QA)
> **Tests:** 261 passed, 2 skipped, 0 failed

---

## A. Executive Summary

DrillMaster is a **functional drilling operations management desktop application** with solid foundations in data import, engineering calculations, and database management. The application can successfully import real-world DDR files, store drilling data across 53 database models, and provide engineering calculations for trajectory, hydraulics, well control, and mud engineering.

**Strengths:**
- Robust Excel import pipeline with merged-cell support, table detection, and activity code mapping
- Deterministic engineering calculations based on published formulas (Bourgoyne, API, IWCF)
- Comprehensive database schema covering all major drilling domains
- Good test coverage (261 tests including integration and golden regression)
- Canonical schema as Single Source of Truth for field mapping

**Key Gaps:**
- Engineering calculator UI is self-contained (4,784 lines) — doesn't use core engines
- No real torque & drag implementation
- Casing design is placeholder only
- Cementing calculations are basic
- No kick tolerance calculation
- MainWindow is monolithic (2,958 lines)

---

## B. Engineering Score

| Module | Score | Status |
|--------|-------|--------|
| **Daily Report** | 8/10 | ✅ Functional, good data model |
| **Time Log** | 9/10 | ✅ Excellent validation (24h, overlap, gap, NPT) |
| **BHA** | 5/10 | 🟡 Basic cumulative length/weight only |
| **Drilling Parameters** | 7/10 | ✅ Good storage, basic analysis |
| **Mud** | 7/10 | ✅ Properties stored, ledger works |
| **Hydraulics** | 7/10 | ✅ Advanced engine exists (Bingham, Power-Law, H-B) |
| **Survey/Trajectory** | 9/10 | ✅ MCM correct, validation comprehensive |
| **Well Control** | 6/10 | 🟡 Kill MW and MAASP correct, missing kick tolerance |
| **Casing** | 3/10 | 🔴 Storage only, no burst/collapse/tension design |
| **Cementing** | 4/10 | 🟡 Basic volume calculation only |
| **NPT** | 7/10 | ✅ Good data model, basic analysis |
| **Services** | 6/10 | 🟡 Storage only, no performance analysis |
| **Logistics** | 7/10 | ✅ Good tracking, carry-forward works |
| **HSE/Safety** | 7/10 | ✅ Good incident tracking, BOP management |
| **Planning** | 7/10 | ✅ 7-day lookahead, plan vs actual |
| **Cost** | 5/10 | 🟡 Basic storage, no AFE/forecast |
| **Analysis** | 6/10 | 🟡 KPI framework exists, limited depth |
| **Import/Export** | 8/10 | ✅ Strong pipeline, good test coverage |

---

## C. Critical Problems (P0/P1)

### P0-1: ROP Model Constants Unrealistic
- **Problem:** Bourgoyne & Young ROP model returns 25,000+ m/hr
- **Why:** Default K constant is too high for the simplified model
- **Current:** `k = 200 * strength_factor * (1 + porosity_pct / 100)` → K = 240
- **Fix:** Calibrate K to typical field values (K ≈ 1-5 for metric)
- **File:** `core/engineering/extended.py`

### P0-2: Engineering Calculator Doesn't Use Core Engines
- **Problem:** `w13_Engineering_Calculator.py` (4,784 lines) has its own inline calculations
- **Why:** Should delegate to `core/engineering/core.py` engines
- **Impact:** Duplicated logic, inconsistent results
- **File:** `tabs/w13_Engineering_Calculator.py`

### P1-1: No Torque & Drag Implementation
- **Problem:** `engines/torque_drag.py` is a stub
- **Why:** T&D is critical for well planning and stuck pipe prevention
- **Impact:** Cannot predict hookload, drag, or surface torque
- **File:** `core/engineering/engines/torque_drag.py`

### P1-2: Casing Design Not Implemented
- **Problem:** Only storage, no burst/collapse/tension calculations
- **Why:** Casing design is fundamental to well construction
- **File:** `core/engineering/extended.py` (CasingDesign is minimal)

### P1-3: No Kick Tolerance Calculation
- **Problem:** WellControlEngine has kill MW and MAASP but no kick tolerance
- **Why:** Kick tolerance is critical for safe drilling margin
- **File:** `core/engineering/core.py`

### P1-4: MainWindow Monolithic
- **Problem:** 2,958 lines, 108 functions in one class
- **Impact:** Hard to test, maintain, and extend
- **File:** `main_window.py`

---

## D. Changes Implemented (This Session)

### Files Changed
| File | Change |
|------|--------|
| `core/activity_mapper.py` | NEW — 30 canonical activities, company-aware mapping |
| `core/excel_intelligence.py` | Deep fix — candidate scoring, validation, label detection |
| `core/canonical_schema.py` | Expanded to 150+ fields with aliases, bounds |
| `core/table_record_mapper.py` | Now consumes canonical_schema (no independent ALIASES) |
| `core/managers.py` | Added TableManager, DrillingManager, setup_widget_with_managers |
| `core/db_models.py` | NEW — 53 ORM models extracted |
| `core/db_services.py` | NEW — Domain service functions |
| `core/lineage.py` | NEW — Data lineage tracking |
| `core/hierarchy_operations.py` | NEW — Hierarchy delete/context menu |
| `core/toolbar_manager.py` | NEW — Toolbar extraction |
| `core/performance.py` | NEW — Chunked reading, progress tracking |
| `core/health_check.py` | Enhanced health check |
| `core/import_quality.py` | Fixed TimeLogValidator crash |
| `core/operations_intelligence.py` | Fixed attribute errors |
| `core/document_import.py` | Improved CSV import |
| `dialogs/excel_import_dialog.py` | Template/Smart import, AI disabled, ActivityMapper integration |
| `dialogs/smart_template_dialog.py` | v3 template support, resolve_canonical |
| `templates/OEOC_DDR_v3.json` | Complete DDR template (259 fields) |
| 7 documentation files | Architecture, import, DB, engineering, AI, testing |
| 8 test files | 197 new tests |

---

## E. Tests

```
Total tests:     261
Passed:          261
Failed:          0
Skipped:         2 (headless sandbox — PySide6 requires display)
New tests:       197
Regression:      Real DDR golden test (14 tests)
Integration:     9 end-to-end tests
Release:         14 verification tests
Engineering:     20 formula verification tests
Activity:        28 mapping tests
```

---

## F. Engineering Limitations

**DrillMaster should NOT yet claim to support:**
- Complete casing design (burst/collapse/tension triaxial)
- Torque & drag prediction
- Cement job design (slurry scheduling, thickening time)
- Kick tolerance calculation
- Real-time drilling optimization
- Wellbore stability analysis
- Fracture gradient prediction
- Pore pressure prediction
- Managed pressure drilling
- Underbalanced drilling

---

## G. Remaining Roadmap

### P1 (Next Phase)
1. Implement torque & drag engine
2. Implement kick tolerance
3. Wire Engineering Calculator to core engines
4. Implement casing burst/collapse design
5. MainWindow refactor (extract managers)

### P2
1. Cement job design (slurry, displacement, TOC)
2. NPT Pareto/trend analysis
3. Cost AFE/forecast
4. Service performance analysis
5. Real-time data integration

### P3
1. Wellbore stability
2. Fracture gradient
3. Managed pressure drilling
4. 3D trajectory visualization
5. Anti-collision

### Future
1. Real-time drilling optimization
2. Machine learning ROP prediction
3. Automated NPT classification
4. Digital twin integration


---

## H. OEOC Real-Import Audit Addendum (2026-08-31)

### Verified end-to-end with the REAL workbook
`08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx` + `templates/OEOC_DDR_v3.json`
(no fabricated fixtures), full path:
`Excel workbook -> Template (anchored) -> Canonical JSON -> SQLite -> UI tabs`.

### Pipeline facts (as implemented)
- Canonical schema (`core/canonical_schema.py`) is the single registry
  (FIELD_SPECS with aliases, engineering bounds, quantity/unit, criticality;
  lookup_alias / get_engineering_bounds / get_quantity_unit / get_field_spec /
  get_critical_fields / get_fields_by_quantity).
- `core/excel_intelligence.py` extracts with multi-candidate scoring:
  preferred cell > merge cell > exact label > alias > fuzzy. Certainty policy:
  deterministic preferred/label mappings >= 0.70 -> HIGH, >= 0.50 -> MEDIUM,
  fuzzy never HIGH (never inflated).
- Placeholder policy: missing = key absent; "N.C" = key None + key_source +
  source_tokens provenance; real zero = 0. Never invented numbers.
- Import flow is generic: Company Source -> Template -> Canonical Model ->
  Database. No `if company == "OEOC"` branching anywhere.
- DB schema upgrades are additive-only (`_apply_safe_schema_upgrades`
  ALTER TABLE ADD COLUMN, idempotent, data-preserving).

### Real workbook verification results (this audit)
- Report date 2024-10-22 (assembled from Year/Month/Day parts)
- Bit 17.5 in, No. 2, rerun 1, KingDream, IADC 135, nozzles 1x18/32" + 2 Open,
  TFA 4.32 — funnel/other sizes NOT picked
- Mud: MW 71 PCF (native UI unit), PV 7, YP 15, funnel 33, gel 4/6, pH 10.5,
  chlorides 7400, solids 7, hardness 400; 34 chemicals with used/received/
  on-hand + units; Fluid Loss = N.C -> NULL (never 0, never invented)
- Pumps: liner text preserved verbatim; SPM/SPP/flow min-max extracted
- Drilling parameters: WOB 10-30 klb, RPM 80-120, torque 2-4, SPP 350-600
- Time logs: 24h rows and morning rows kept separate (morning NOT duplicated)
- Services: Vira, APAD, GEO Data, OEOC (CSG + Wellhead), SPAD Energy — all 6
  preserved with hole section/dates/duration/description
- Lookahead: 13 activities with hours -> 11 stored in seven_days_lookahead
  (rows without activity text are skipped; hours prefixed into remarks)
- BOP: Annular RS 3000 psi 20-3/4" + 5 more stack components (Jalali
  last-test date preserved as provenance text, never stored as wrong date)
- Notes: Note#01/Note#02 appended to the Daily Report summary
- LTA (Day) 468 -> DailyReport + Well; Actual Rig Days 7.25
- POB breakdown (rig 76, client 3, MSA 7, service 14, catering 22, labour 8,
  total 130) -> ServiceCompanyPOB rows (total not stored -> no double count)
- Safety: days_without_lti 468; missing drill dates stay NULL (no fake dates)

### Test status (this audit)
Full suite: 352 passed, 2 skipped (PySide6 display), 0 failed, 0 errors.
Golden OEOC regression: 32 tests in `tests/test_real_oeoc_golden.py`
(+ `tests/test_multi_company_template.py` for the generic template path).

### Remaining genuine limitations
- Time-log extraction: 7 of 10 canonical 24h rows and 6 of 7 morning rows
  reach the DB — rows whose time cells arrive as `timedelta` (not `time`)
  are skipped by the dialog's `to_time` filter.
- 2 of 13 lookahead rows lack activity text in the workbook and are skipped
  (stored: 11).
- No NPT report is generated from service rows with negative durations;
  service NPT is visible via service_companies, not npt_reports.
- UI verification is code-path level (headless env: no libGL); tabs w1/w7/w8
  load the imported values through their DB getters.
