# Product capability matrix (M53–M100)

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
| Profile date formats, table rules, continuation, confidence threshold | COMPLETE (M61) | Applied by the importer; see M61 below |
| Generic PDF tables: scanned-page detection, header/footer exclusion, multi-page and ruled continuations, wrapped cells | COMPLETE | `core/import_adapters/pdf_generic_tables.py`, `tests/test_m54_pdf_generic_tables.py` |
| OCR | NOT IMPLEMENTED | No local engine; an explicit "OCR unavailable" state is shown. Engines and models are owner-gated |
| Review workspace with per-field detail and decisions, no silent persistence | COMPLETE | Review detail panel in `dialogs/excel_import_dialog.py` |
| Excel sheet selection, batch import | PARTIAL (M61) | Batch queue with statuses, remove/retry/cancel; see M61 below |
| Import worker cancellation | PARTIAL | Existing import worker; cancellation is not separately verified in M54 |

## M55 – Directional (P0)

| Capability | State | Evidence / gap |
|---|---|---|
| Survey import CSV/TXT/DAT/XLSX with unit, row and azimuth-reference validation, wired into W6 | COMPLETE | `core/survey_file_import.py`, `dialogs/survey_import_dialog.py`, W6 Import; `tests/test_m55_directional.py` |
| Plan designer: KOP/hold, build, drop, turn, hold-to-TVD, DLS limit warning, targets, canonical MinCurv | COMPLETE | `core/well_plan_designer.py`, Trajectory viewer → **Plan designer**; golden closed-form J-profile |
| Tangent-to-target solver | NOT IMPLEMENTED | Turn-only and build-and-turn curves exist (curve segment with target inc/az); no solver |
| Visualization: plan, section, 3D, DLS/inc/az/TVD vs MD | PARTIAL (M62) | Designer now plots Inc/Azi/DLS/TVD vs MD; targets and offsets still not drawn in 3D |
| Export | COMPLETE | Designer CSV and comparison CSV |
| Plan vs actual (HL/RL/along, worst point), saved records, designed plan handed over in memory | COMPLETE | M52 `core/trajectory_compare.py` plus M55 `set_plan_rows` |
| Versioned plan saves | COMPLETE (M62) | `DirectionalPlanRevision` (immutable revisions); see M62 below |
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

---

# M61–M69 additions

Same states and evidence rules as above. Offscreen Qt and unit tests on synthetic data only.

## M61 – DDR import completion (P0)

| Capability | State | Evidence / gap |
|---|---|---|
| Profile `date_formats` applied in declared order; ambiguous (two formats → different dates) or unmatched dates go to review with the original string | COMPLETE | `DocumentNormalizer._profile_value` (`core/mineru_engine.py`); `tests/test_m61_ddr_profile_rules.py` |
| Profile `table_rules`: `stop_markers` (marker row and later rows), `skip_rows_containing`, `skip_tables_containing`; each ignored row has a reason, profile key/version and page/row source | COMPLETE | `_profile_row_skip`, `_profile_table_skip`; editor fields in `dialogs/ddr_profile_dialog.py` |
| Header/identify/column-specific table rules | NOT IMPLEMENTED | Only the three rule kinds above |
| Profile `continuation` controls cross-page joins (text and ruled tables); page/row provenance kept either way | COMPLETE | `join_continuations(join=…)`, `generic_document_tables(continuation=…)`, `extract_tables(continuation=…)` |
| Profile `confidence_threshold` drives acceptance eligibility, review bands, counts and row colours in the preview | COMPLETE | `review_thresholds`, `review_counts` in `dialogs/excel_import_dialog.py`; values still needing review are never bulk-accepted |
| Profile key/version and rule set recorded on the result | COMPLETE | `metadata()["profile"]`, `profile_rules_version` (`PROFILE_RULES_VERSION = 1`) |
| Batch queue: visible list, per-file status and stage, profile, attempts, diagnostics | COMPLETE | `core/ddr_import_queue.py`, queue table in the import dialog |
| Distinct states SAVED / REVIEW_REQUIRED / SKIPPED / DUPLICATE / FAILED / CANCELLED | COMPLETE | Preview cancel is SKIPPED (previously counted as failed); re-import of an identical source is DUPLICATE |
| Remove (not running, not saved), retry (failed/skipped/cancelled), cancel remaining (running file finishes atomically) | COMPLETE | |
| In-batch duplicate detection (SHA-256 of bytes) | COMPLETE | Persisted-source duplicates continue to use the import audit fingerprint |
| Atomic per-file save | COMPLETE (pre-existing) | `DDRImportService` transaction per file |
| Worker thread for all heavy work | PARTIAL | MinerU parsing runs in a worker; XLSX extraction, PDF-native fallback and validation still run on the GUI thread with event processing |
| OCR adapter | PARTIAL | Detection of an already-installed engine and an explicit "OCR unavailable" diagnostic exist; no engine is installed or bundled (owner-gated) |
| Time-coverage/overlap validation and survey replace with before/after | COMPLETE (pre-existing, M54) | Not changed in M61 |
| Profile suggestion with confidence and reasons | NOT IMPLEMENTED | User selects the profile |

## M62 – Directional plans (P0)

| Capability | State | Evidence / gap |
|---|---|---|
| Persistent versioned plans (well, wellbore, key, revision, parent, status, method, version, inputs, results) | COMPLETE | `DirectionalPlanRevision`, `core/directional_plans.py`; `tests/test_m62_directional_plans.py` |
| New, save, open, revise, clone, archive, compare, export | COMPLETE | Plan designer panel buttons; revisions are never overwritten; archived revisions stay archived |
| Send to plan-vs-actual | COMPLETE (pre-existing) | `plan_ready` hand-over |
| Continuous target distance on the minimum-curvature arc | COMPLETE | `closest_on_path` / `evaluate_target`; closest station kept for transparency; closed-form arc reference |
| Numerical safeguards: non-finite inputs, antiparallel curve, impossible TVD, zero/negative lengths | COMPLETE | Explicit errors; no NaN reaches stations |
| DLS/Inc/Azi/TVD vs MD plots | COMPLETE | Designer **Plots** tab (pyqtgraph) |
| Target solving, build/turn-rate constraints, multiple-target optimisation | NOT IMPLEMENTED | |
| MD gap NOT ASSESSED handling in plan vs actual | PARTIAL (pre-existing M52 behaviour) | Not changed |
| Survey revision control | PARTIAL (pre-existing) | Survey replace confirmation exists; no survey revision table |
| Anti-collision | SCREENING | Unchanged; no SF without uncertainty |

## M63 – W13 workbench cases

| Capability | State | Evidence / gap |
|---|---|---|
| Save a named case (inputs, results, calculator path, method label, well) | COMPLETE | `CalculationCase` (insert-only; data-layer write policy NOBODY), `tabs/calculation_cases_panel.py`; `tests/test_m63_calculation_cases.py` (incl. real W13 Quick Calc) |
| Reopen (restores inputs, navigates), compare with current, re-run → new child case | COMPLETE | Generic capture of the open calculator page |
| Per-calculator method versions | NOT IMPLEMENTED | Cases are labelled `W13 calculator (no per-method version); case capture v1` |
| Finder categories/aliases/formula search, unit system switching | PARTIAL (pre-existing M56) | Not extended in this programme |

## M64 – Engines | M65 – Well architecture | M66 – Operational analysis | M68 – Specialist modules

| Item | State | Note |
|---|---|---|
| M64 hydraulics, mud, bit/MSE, T&D (soft-string SCREENING), casing (TR 5C3 subset), cement, kill sheet (training aid), fishing | PARTIAL (pre-existing) | No engine was changed; their saved runs are now in the unified history with recalculate-and-verify |
| M65 schematic from persisted records, links to casing/cement calculations, revisions | NOT IMPLEMENTED | Unchanged from M57 audit |
| M66 NPT Pareto, ROP/MSE aggregation, cost/AFE drill-down | PARTIAL (pre-existing W12/W16) | Not extended |
| M68 hole cleaning, wellbore stability, thermal | NOT IMPLEMENTED | No defensible sourced method was added; OWNER REVIEW REQUIRED before any |

## M67 – Calculation history and Report Center (P0)

| Capability | State | Evidence / gap |
|---|---|---|
| Unified history over 9 sources (6 engine snapshot tables, trajectory, W13 cases, plan revisions) via read-only adapters | COMPLETE | `core/calculation_history.py`; no migration; a missing source model raises instead of being skipped |
| Filters (well, source, text, date), CSV export | COMPLETE | `tabs/calculation_history_tab.py` (**Calc History** tab, follows the selected well) |
| Compare two entries (flattened inputs/results) | COMPLETE | |
| Recalculate & verify with the current method (MATCH / DIFFERENT / NOT_REPRODUCIBLE / UNREADABLE, method-change flag); save the recalculation separately as a new case | COMPLETE for engine snapshots and plans | Reuses each engine's `recalculate_from_snapshot` and `classify_verification`; trajectory and W13 cases have no recalculation adapter (stated in the UI) |
| Report Center: single-entry and comparison reports (HTML, PDF) with method, version, inputs, results, scope, UNSIGNED/not-validated statement | COMPLETE | Template v1 |
| `SelectionManager` shared context | PARTIAL | History tab and plan designer follow the selected well; no full audit of every tab |

## M69 – Integration

| Capability | State | Note |
|---|---|---|
| Navigation | PARTIAL | New **Calc History** tab; plan library inside the Trajectory viewer; case bar under the W13 finder |
| Dashboard English/LTR dark | COMPLETE (pre-existing M53) | Unchanged |
| Offline | COMPLETE | No network use added |
| Windows desktop acceptance | OWNER REVIEW REQUIRED | CI Windows job is not desktop acceptance |

## M70–M80 – Integrity, surveys, contracts, architecture

| Capability | State | Evidence / gap |
|---|---|---|
| Plan revision immutability (data layer) | COMPLETE | Storage triggers + service checks; `tests/test_m70_integrity.py` |
| Structured lineage, well delete cascade | COMPLETE | `tests/test_m70_verification_lineage.py`, `tests/test_m70_integrity.py` |
| DDR preparation in a worker (cancel, safe close) | PARTIAL | `tests/test_m71_ddr_background.py`; cancellation is cooperative between steps |
| Immutable survey revisions + plan tie-in | COMPLETE | W6 Survey revisions tab; `tests/test_m72_*` (fresh and upgraded DBs) |
| Build-hold target solver | PARTIAL | Closed form, vertical tie-in only; infeasibility reported |
| Plan vs actual 3D target checks | COMPLETE (SCREENING) | Compare panel; saved with the survey revision |
| Calculator contracts | PARTIAL | One contract (Quick Calc); other W13 calculators stay unversioned |
| History statuses, unit-safe compare, paging | COMPLETE | `tests/test_m73_contracts_history.py` |
| Well architecture revisions + schematic | COMPLETE | W3b Architecture tab; `tests/test_m74_well_architecture.py` |
| Cement geometry from architecture | PARTIAL (WORKSHEET) | Annulus volumes saved as cases; not wired into the W13 cement engine |
| Engine inventory, formula mutants | COMPLETE | `ENGINE_INVENTORY.md`, `tools/quality/mutation_m70_m76.py` |
| Operations analysis on W12/W16 | PARTIAL (pre-existing) | W12 KPI evidence + Home dashboard; no new W12/W16 drill-down |
| Specialist method registry | COMPLETE (registry); methods OWNER REVIEW | `core/specialist_methods.py` |
| Backup/restore of new revisions | COMPLETE | `tests/test_m80_recovery_offline.py` |
| Windows desktop acceptance | OWNER REVIEW REQUIRED | Checklist M80-01..12 in `packaging/WINDOWS_RELEASE_ACCEPTANCE.md`, NOT EXECUTED |

## M82–M100 – Product completion programme

Statuses here use the M82 vocabulary: PASS / PARTIAL / BLOCKED / NOT IMPLEMENTED / NOT RUN /
OWNER REVIEW REQUIRED. Product label: UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.

### M83 – Selection lifecycle

| Capability | State | Evidence / gap |
|---|---|---|
| Clearing the selection empties every well-scoped tab (11 tabs were stale before) | PASS | `on_selection_cleared` + `DrillTabBase.reset_context_view`; `tests/test_m83_selection_lifecycle.py` |
| A→B well switch leaves no identifiers of A; viewing tabs creates no fake unsaved edits | PASS | Same tests. Fixed defects: spin-box snapshot faked an edit on first show (W3c Cement, `core/editor_bindings._spin_display`); W10 Lookahead reset read as an edit; W3c well-switch branch was dead code so cement/casing values carried over to the next well |
| Deleting the current well / report / company / project clears the selection | PARTIAL | `_forget_selection_if_gone`; deleting a report clears the whole selection, not only the report |
| Context token (`SelectionManager.context_token()` / `is_current()`) | PARTIAL | Central token exists; workers still use their own tab-local tokens (W12, analysis views, trajectory compare) |
| Company / project / rig / date / period selection signals | NOT IMPLEMENTED | Only well, wellbore and report are selection signals |
| Probe coverage | PARTIAL | The leak probe checks well identifiers only; W2 daily-report form fields of the previous report are not cleared; W10 clears milestones/combos only (CodeManagementTab is global) |
| No-section prompt on navigation | PARTIAL (UX) | W2 asks "No Section — create one now?" modally when a well without sections is opened; tests patch it (M95) |

### M85 – Survey references and integrity

| Capability | State | Evidence / gap |
|---|---|---|
| Azimuth reference must be declared (no silent "true" default in API or panel) | PASS | `core/survey_revisions.py` (`preview`, `save_revision`, `snapshot_survey_points`); panel "— declare —" placeholder; `tests/test_m85_survey_references.py` |
| Explicit azimuth conversion true/grid/magnetic as a new linked revision | PASS | `transform_revision` ("M85 azimuth reference transform v1"); Survey revisions → **Convert azimuths**. Needs the declination (east +) and/or grid convergence (grid north east of true +), their source, and a date when a declination is used; parameters, convention and source hash stored in `source_ref`. Never looked up online |
| Station hash verified on every read; failed revisions blocked from conversion, tie-in and plan-vs-actual | PASS | `integrity` VERIFIED / HASH MISMATCH in the revision list; `verify_results` recomputes positions. The hash covers stations, not computed results |
| Independent minimum-curvature benchmarks | PASS | Vertical, hold, build arc, horizontal quarter turn, azimuth wrap, near-zero dogleg, rotation invariance of converted positions |
| Depth-datum transform | NOT IMPLEMENTED | The trajectory model has no datum elevation / TVD-offset field; revisions with different datums are not compared |
| CRS / grid coordinates | NOT IMPLEMENTED | No CRS is stored; convergence is a user value, not derived from a CRS |
| Plan file azimuth reference | PARTIAL | Plan-vs-actual checks the survey revision's integrity, but imported plan files carry no declared reference |

### M86 – Directional solver and screening

| Capability | State | Evidence / gap |
|---|---|---|
| Curve-hold target solver from any tie-in direction (inclined / horizontal / survey tie-in) | PASS | `core/well_plan_designer.solve_build_hold` ("M86 curve-hold target solver v2"), Trajectory viewer → Plan designer → Solve; closed-form goldens (build, drop, horizontal turn, pure hold, M72 J-profile) and 60 seeded targets verified by the forward minimum-curvature engine; `tests/test_m86_directional_solver.py`. The M72 test row that asserted the old "vertical tie-in only" refusal was replaced by these positive goldens |
| Structured infeasibility | PASS | `code` = INVALID_INPUT / NON_POSITIVE_RATE / KOP_ABOVE_TIE_IN / TARGET_NOT_BELOW_KOP / TARGET_AT_KOP / TARGET_BEHIND / INSIDE_TURN_RADIUS / TURN_TOO_LARGE / INC_LIMIT plus a reason; shown in the panel |
| Inclination limit along the whole arc | PASS | `_max_inc_along_arc`, checked against dense sampling |
| Build / drop / hold / turn segments, DLS-limit warning, targets with radius and TVD | PASS (pre-existing M55/M62) | Designer segments; target hit evaluated on the continuous arc |
| Multi-segment optimisation (S-profile, build-turn-hold with separate rates, multiple targets) | NOT IMPLEMENTED | The solver aims at the first target with one arc and one tangent |
| Plan vs actual, offset closest approach | PASS (SCREENING, pre-existing M52/M72) | Label now `SCREENING — NO ISCWSA UNCERTAINTY — NOT APPROVED (centre-to-centre)`; no separation factor or ellipses (no error model) |

### M87 – W13 calculator contracts and cases

| Capability | State | Evidence / gap |
|---|---|---|
| Contract status for every W13 leaf calculator (27 leaves) | PASS | `core/calculator_contracts.CALCULATOR_STATUS` via `calculator_status`; shown under the W13 finder; test fails on any unlisted or stale path. `tests/test_m87_w13_contracts.py` |
| Re-runnable contracts (ID, method version, field IDs bound by widget object name, units, validation, adapter, independent goldens, UI parity) | PARTIAL | 7 of 27: Quick Calc v2 (pipe + annulus), Bit Hydraulics page (hydraulics with nozzle program, MSE Teale, cost/ft), TFA, Hydrostatic & FP, Cement Volume (WORKSHEET), OWR, Build/Turn & DLS. The other 20 show NOT_SUPPORTED with the reason; their cases are stored as captured and are NOT REPRODUCIBLE |
| Case save / reopen / compare / re-run / clone / export, never overwritten | PASS | W13 case bar (Clone…, Export… CSV with the UNSIGNED label); re-run and clone are new linked cases (`rerun_of`, `clone_of`) |
| Structured results and method-change detection | PASS | Adapter results stored at engine precision (`source: contract`), compared with a 1e-9 relative tolerance; a changed method gives DIFFERENT, a removed version NOT_REPRODUCIBLE |
| Fixed defects | PASS | Quick Calc contract bound "length" to the annulus length (two "Length" labels) so correct cases verified DIFFERENT; legacy cases with a repeated label are now UNREADABLE. Build/Turn "Overall DLS" was sqrt(BR²+TR²) — now the minimum-curvature dogleg severity; an MD interval of 0 showed 0 deg/30 m — now "Not assessed". Cement "Displacement" showed 0.00 when missing — now n/a |
| Open engine notes for M90 | PARTIAL | HP & FP converts pcf→ppg with 7.48 while the bit page uses 7.48052 (0.007 %); currency of rig/bit cost is not recorded (owner-gated money model) |

### M88 – History coverage, recalculation and lineage

| Capability | State | Evidence / gap |
|---|---|---|
| One history schema over every stored calculation and revision | PASS | `core/calculation_history.py`: 11 sources (6 engine snapshots, trajectory, W13 cases, directional plans, **survey revisions**, **architecture revisions**); database filters and paging, including text search on tables without a `method` column. `tests/test_m88_history_lineage.py` |
| Recalculate from stored inputs (survey, architecture) | PASS | Survey: minimum curvature from the stored stations after the SHA-256 check (hand-derived golden); architecture: current validator on the stored components after the SHA-256 check. A failed hash → UNREADABLE and nothing is stored; altered stored results → DIFFERENT; method or version drift reported |
| New immutable linked records | PASS | `save_recalculation` creates a case with a `recalculation_of` link; the original revision is unchanged (hash re-checked in the test) |
| Lineage navigation | PASS | Case source / derived links plus revision parent / child (survey, architecture, plan, case) and architecture uses / survey used by. "Open linked" now jumps to the record's own page (it previously failed for records outside the current page) |
| Still captured-only | PARTIAL | Trajectory calculations (legacy, unversioned) and the 20 NOT_SUPPORTED W13 calculators remain NOT REPRODUCIBLE, with the reason shown |

### M89 – Architecture ↔ casing and cement worksheet

| Capability | State | Evidence / gap |
|---|---|---|
| Immutable wellbore-scoped architecture revisions | PASS (M74) | `core/well_architecture.py`, immutability trigger, SHA-256 on read; history source since M88 |
| Casing strength records the architecture revision and the origin of every input | PASS | W13 CSG/CMT "Load from architecture" (`casing_inputs`): OD/ID/weight `architecture`, wall `derived` (OD−ID)/2, yield always `unknown` until entered (`user`; never inferred from the grade); a value edited after loading becomes `user`; required unknowns refuse the calculation; snapshot `source` holds revision id/number/SHA-256/string/provenance; a run for another well cannot be saved. Engine is the TR 5C3 subset (SCREENING). `tests/test_m89_architecture_casing_cement.py` |
| Cement worksheet: segment geometry, declared caliper, explicit excess, History | PASS (WORKSHEET) | Segments by outer boundary with `outer_source` (casing ID / declared average caliper / entered open hole / recorded hole size / unknown); excess on open hole only and only when declared ("none" ≠ 0 %); case `m89.cement_annulus` v1 with wellbore and lineage "uses architecture revision" |
| Lineage architecture ↔ casing / cement | PASS | `uses` / `used_by` in the History lineage combo |
| Cement worksheet re-run | NOT IMPLEMENTED | Worksheet cases are captured only (NOT REPRODUCIBLE, reason shown) |

### M90 – Per-engine qualification

Independent goldens per engine family (closed forms written in the tests, never produced by the code under test). All engines remain SCREENING / WORKSHEET / TRAINING AID as labelled.

| Engine | State | Golden evidence |
|---|---|---|
| Hydraulics (bit ΔP, jet velocity, HHP, impact) | PASS | `test_engineering_independent_golden` (Bernoulli, Cd 0.95 → 10858) |
| Mud (hydrostatic, weight-up, **dilution**, mix, OWR) | PASS | `test_engineering_ground_truth`, `test_m87`, **`test_m90` dilution material balance** |
| Bit / MSE (TFA, Teale) | PASS | `test_m87` (Teale 127,997.67 psi) |
| Casing (burst, collapse, VME, **pipe-body yield**) | PASS (TR 5C3 subset) | `test_casing_vme_independent`, **`test_m90` tensile** |
| Cement (displacement, annulus, **TOC from volume**) | PASS (WORKSHEET) | `test_m74`, `test_m89`, **`test_m90` TOC** |
| Torque & drag (vertical, **straight inclined pickup / slack-off / rotating / torque**) | PASS (SCREENING) | `test_engineering_ground_truth`, **`test_m90` 30° and 60° tangents** |
| Well control (kill MW, ICP, FCP, MAASP, kill sheet) | PASS (TRAINING AID) | `test_engineering_independent_golden` |
| Fishing (free point, stretch, back-off, **overshot clearance**) | PASS (SCREENING) | `test_engineering_ground_truth`, **`test_m90` band edges** |
| Directional (minimum curvature, build-hold solver) | PASS (PLANNING AID) | `test_m85`, `test_m86` |
| pcf→ppg constant | DOCUMENTED DEVIATION | Hydraulics, unit manager and the bit page use 7.48052 gal/ft³ (exact 1728/231); the kill sheet, T&D, HP & FP and several W13 display handlers use 7.48 (relative 7·10⁻⁵, about 20× below the 0.1 pcf input resolution). Not changed: verification compares at 1e-6, so every stored kill-sheet, T&D and HP & FP record would turn DIFFERENT. Changing it needs versioned methods with legacy adapters — OWNER REVIEW REQUIRED |
| Output rounding | DOCUMENTED | Engines round outputs (e.g. bit ΔP 0.1 psi, hydrostatic 0.01 psi); goldens use matching absolute tolerances, stored-vs-recalculated verification stays at 1e-6 |

### M91 – Operational Analysis

W12 page "🧭 Operational Analysis" (`tabs/operational_analysis_panel.py`) over `core/operational_analysis.py` (`M91 operational analysis v1`); scope = W12 analysis scope (well or wellbore) plus an optional report-date range; read-only, recomputed on Refresh, cleared when the well or wellbore changes. Missing values are "—" on screen and blank in exports, never 0. Label: UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED. `tests/test_m91_operational_analysis.py` (8, offscreen Qt for the page test; 6 hand mutants killed).

| Capability | State | Evidence / limits |
|---|---|---|
| Daily footage and day ROP | PASS | Footage = depth 24:00 − depth 00:00; missing depth → unknown; a decrease → "INVALID footage" (not negative footage); drilling hours = time-log hours mapped to DRILLING (exact / learned / description) and not NPT; any unknown duration makes the day unknown |
| Time-weighted ROP | PASS | Σ footage / Σ drilling hours over days where both are known, with "X of N days" coverage (not a mean of daily ROPs) |
| Activity breakdown | PASS | Existing `ActivityMapper`; mapping method shown; unresolved codes stay "UNRESOLVED", fuzzy matches are "UNCERTAIN: …" and never count as drilling |
| NPT and NPT timeline with sources | PASS | Time-log NPT (`summarize_time_logs`) and the NPT register listed side by side with a source column; the two totals are never added; register rows outside the selected wellbore are excluded; unclassified NPT flag → day NPT unknown |
| Bit runs | PASS | Drilling parameters grouped by bit number / rerun; footage from daily drilled, else depth out − depth in (basis column); hours on bottom; whole-well uses the canonical parameter scope |
| MSE trend | PARTIAL | Stored MSE calculations in time order without interpolation; per well only (MSE records carry no wellbore or depth) |
| Cost | PASS | Per-currency rows (`summarize_costs`); a total only for one known currency; unknown currency shown as "UNKNOWN"; a date range excludes undated records (note). No conversion (owner-gated) |
| Plan vs actual | PARTIAL | Existing `get_actual_vs_plan` (whole well; no wellbore or date filter) |
| Drill-down | PASS | Row → source daily report via `SelectionManager.select_full_context`, refused for another well; the result is kept for the same well/wellbore and cleared otherwise |
| Export | PASS | CSV (one file per table) and XLSX with scope, method version, generation time and label |

### M92 – Method Catalogue

Help › "📐 Method Catalogue" (`dialogs/method_catalogue_dialog.py`) over `core/method_catalogue.py` (`M92 method catalogue v1`). `tests/test_m92_method_catalogue.py` (6, offscreen Qt through the real MainWindow; 6 hand mutants killed).

| Capability | State | Evidence / limits |
|---|---|---|
| One catalogue over every method source | PASS | 50 entries: 10 engines (incl. hydraulics), 7 W13 contracts + 1 legacy runnable version, 20 W13 calculators without a contract (NOT SUPPORTED), 4 specialist methods (M79), 8 directional / survey / architecture / analysis methods. Versions and method strings are read from the running code; a test discovers engine classes from the source and fails if one is missing |
| Fields | PASS | ID, title, family, source, status, label, version, reference, licence, limits, approval, blocker, module; details pane; CSV export with the UNSIGNED label |
| No self-approval | PASS | Approval only from `OWNER_APPROVALS`, an immutable mapping in the source (empty in this build); every method reads "NOT APPROVED — OWNER REVIEW REQUIRED" with "owner engineering approval" as a blocker; no approve, edit or delete control; table not editable |
| Misleading-entry guard | PASS | `violations()`: duplicate id, unknown status or label, IMPLEMENTED without version/limits/module/reference, not implemented without a blocker, approval for an unknown method |
| Stored use | PASS | Count of stored W13 cases per method and version, database-wide and for the selected well |
| Engine references | PARTIAL | Hydraulics: published reference not recorded in the source (blocker shown); references are statements, not owner-verified citations |
