# Product capability matrix (M53–M60)

States: **COMPLETE** (usable in the product, tested) / **PARTIAL** (usable, with named gaps) / **SCREENING** (usable, labelled as a check aid and not a design approval) / **OWNER REVIEW REQUIRED** / **NOT IMPLEMENTED** / **NOT RUN**.

Evidence for "tested": offscreen Qt (Linux, PySide6 6.8.1.1) and unit tests on synthetic data. None of this is Windows desktop, field or production acceptance; those remain owner items. Release status: UNSIGNED and NOT RELEASE-APPROVED.

## M53 – Executive / operations dashboard (P0)

| Capability | State | Evidence / gap |
|---|---|---|
| KPI cards (wells by status, DDRs, latest date, depth, footage, ROP, NPT h/%, cost, cost/m, NPT cost, attention, survey readiness, imports), each with definition, unit, source, freshness and drill-down | COMPLETE | `core/operations_dashboard.py`, `tests/test_m53_dashboard.py`. Unknown is shown as Unavailable; no cross-currency sums |
| Rig KPI | PARTIAL | Rig is a filter and a portfolio column (`Well.rig_name`); there is no separate rig entity or utilisation KPI |
| Portfolio table with navigation | COMPLETE | Click opens the well |
| Charts (ROP, depth-time, NPT category/trend, cost vs AFE) | COMPLETE | Drawn only with data, otherwise an explicit empty state |
| ECD chart | NOT IMPLEMENTED | No ECD field is stored (`MudReport` has MW in PCF only) |
| Bit and MSE dashboard charts | PARTIAL | Shown where records exist; W13 MSE history is separate |
| Trajectory preview from real surveys and open-full-view | COMPLETE | |
| Alerts (NPT_HIGH, COST_OVER_AFE, COST_CURRENCY), linked | COMPLETE | |
| Recent activity, filters, worker with stale-result guard | COMPLETE | |
| English-only and LTR | COMPLETE | Test asserts LTR and no Persian strings |
| Screenshots (overview, selected well, empty, alert) | COMPLETE | `docs/mission-reports/m53-screenshots/` (synthetic, offscreen) |
| Light theme | NOT IMPLEMENTED | Dark theme only |

## M54 – Daily drilling report (P0)

| Capability | State | Evidence / gap |
|---|---|---|
| Create, edit, previous/next, timeline list, new | COMPLETE | `tabs/w2_Daily_Report.py`, `tests/test_m54_ddr_workflow.py` |
| Unsaved-change guard | COMPLETE | M54 regression fixed: display-only panels (related documents, timeline) no longer count as edits (`core/editor_bindings.exclude_from_editor_snapshot`) |
| Duplicate for review (nothing persisted until Save) | COMPLETE | `dialogs/ddr_duplicate_dialog.py` |
| Time-log validation: overlap blocks, gaps noted, midnight handling | COMPLETE | |
| Versioned report profiles (operator, format, aliases, column maps, units) | COMPLETE | `core/ddr_report_profiles.py`, `dialogs/ddr_profile_dialog.py`, `tests/test_m54_report_profiles.py` |
| Profile date formats, table rules, continuation, confidence threshold | PARTIAL | Stored, validated and editable; not yet applied by the importer |
| Generic PDF tables: scanned-page detection, header/footer exclusion, multi-page and ruled continuations, wrapped cells | COMPLETE | `core/import_adapters/pdf_generic_tables.py`, `tests/test_m54_pdf_generic_tables.py` |
| OCR | NOT IMPLEMENTED | No local engine; an explicit "OCR unavailable" state is shown. Engines and models are owner-gated |
| Review workspace with per-field detail and decisions, no silent persistence | COMPLETE | Review detail panel in `dialogs/excel_import_dialog.py` |
| Excel sheet selection, batch import | PARTIAL | Single-file review flow; batch queue not built |
| Import worker cancellation | PARTIAL | Existing import worker; cancellation is not separately verified in M54 |

## M55 – Directional (P0)

| Capability | State | Evidence / gap |
|---|---|---|
| Survey import CSV/TXT/DAT/XLSX with unit, row and azimuth-reference validation, wired into W6 | COMPLETE | `core/survey_file_import.py`, `dialogs/survey_import_dialog.py`, W6 Import; `tests/test_m55_directional.py` |
| Plan designer: KOP/hold, build, drop, turn, hold-to-TVD, DLS limit warning, targets, canonical MinCurv | COMPLETE | `core/well_plan_designer.py`, Trajectory viewer → **Plan designer**; golden closed-form J-profile |
| Tangent-to-target solver, turn-only segments | NOT IMPLEMENTED | |
| Visualization: plan, section, 3D, DLS/inc/az/TVD vs MD | PARTIAL | Existing viewer (plan, section, 3D, station panel); no dedicated DLS/inc/az-vs-MD plot set; targets and offsets not drawn in 3D |
| Export | COMPLETE | Designer CSV and comparison CSV |
| Plan vs actual (HL/RL/along, worst point), saved records, designed plan handed over in memory | COMPLETE | M52 `core/trajectory_compare.py` plus M55 `set_plan_rows` |
| Versioned plan saves | PARTIAL | Comparisons are saved append-only; designed plans are exported as CSV. There is no `WellPlan` model |
| Anti-collision | SCREENING | Centre-to-centre only; separation factor and clearance unavailable without uncertainty data |
| ISCWSA error models (welleng) | OWNER REVIEW REQUIRED | No compliance claim |

## M56 – W13 engineering workbench (P0)

| Capability | State | Evidence / gap |
|---|---|---|
| Search, favourites, recents over the live calculator tree | COMPLETE | `tabs/calculator_finder.py` in W13; `tests/test_m56_calculator_finder.py` |
| Categories | COMPLETE | Existing tab groups (11 top-level, nested calculators) |
| Well context | PARTIAL | W13 follows the selected well (pre-existing `SelectionManager` wiring); not every calculator pre-fills from it |
| Structured result (status, value, unit, formula, method, assumptions, warnings, failure reason, scope) | PARTIAL | `core/engineering/result.EngineeringResult` for engine-backed calculators; legacy inline calculators lack it |
| Saved calculation records and history | PARTIAL | Records for casing, cement, torque and drag, MSE and kill sheet; history browser for MSE only |
| Case compare, save/reopen of input sets | NOT IMPLEMENTED | |
| Hydraulics engine audit | PARTIAL | `core/hydraulics_engine.py` reviewed for structure only; not re-validated |
| Torque & drag improvement | NOT IMPLEMENTED | Soft-string Johancsik engine unchanged (SCREENING); no LGPL code taken |

## M57 – Well architecture, casing and cement (P1)

| Capability | State | Evidence / gap |
|---|---|---|
| Well schematic view | PARTIAL | Pre-existing `tabs/w3b_wellbore_schematic_tab.py`; record linking and export not extended in M53–M60 |
| Casing engine | PARTIAL | API TR 5C3 **pipe-body subset** (Barlow, four collapse regimes, fyax, VME). Connections and full tri-axial design factors are not implemented |
| Cement integration | PARTIAL | Volume and hydrostatic calculation; balanced plug is SCREENING; no invented slurry data |
| Calculation linked to casing string and section | NOT IMPLEMENTED | |

## M58 – Operational analytics (P1)

| Capability | State | Evidence / gap |
|---|---|---|
| ROP, NPT, cost per metre, AFE vs actual | COMPLETE | Through the M53 dashboard (`core/operations_dashboard.py`, `core/cost_semantics.py`) |
| MSE | PARTIAL | W13 MSE with records and history; not aggregated per well on the dashboard |
| Deterministic alerts | COMPLETE | NPT_HIGH, COST_OVER_AFE, COST_CURRENCY |
| Analysis workspace linked to records | PARTIAL | Pre-existing `tabs/w12_Analysis.py`, not extended |
| ML | NOT IMPLEMENTED | No qualified dataset; training is owner-gated |

## M59 – Optional engineering modules (P2)

| Capability | State |
|---|---|
| Hole cleaning, wellbore stability, thermal (BoreTHM) | NOT IMPLEMENTED (optional; BoreTHM is Apache-2.0 but not integrated) |

## M60 – Integration and offline readiness (P0)

| Capability | State | Evidence / gap |
|---|---|---|
| Shared well context | PARTIAL | `core/selection_manager.SelectionManager` drives W2, W6, W13, viewer, dashboard and others. Not all 29 tabs subscribe |
| Unified calculation history (filter, recalculate with original version, compare, export) | NOT IMPLEMENTED | Per-engine records exist (append-only); no single history screen |
| Engineering reports with approval scope | PARTIAL | Comparison and calculation records carry method, version, inputs and warnings; no consolidated engineering report document |
| Offline operation | COMPLETE | No cloud API, telemetry, required key or auto-download (pre-existing gates) |
| UX review | PARTIAL | Dashboard, W2, the import review and the M55/M56 panels were reviewed; the other tabs were not |
