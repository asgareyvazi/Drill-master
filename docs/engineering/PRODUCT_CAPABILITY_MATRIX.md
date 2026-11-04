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
| Still captured-only | PARTIAL | Trajectory calculations (legacy, unversioned) and the 20 NOT_SUPPORTED W13 calculators remain NOT REPRODUCIBLE, with the reason shown (superseded by M107: 9 NOT_SUPPORTED) |

### M89 – Architecture ↔ casing and cement worksheet

| Capability | State | Evidence / gap |
|---|---|---|
| Immutable wellbore-scoped architecture revisions | PASS (M74) | `core/well_architecture.py`, immutability trigger, SHA-256 on read; history source since M88 |
| Casing strength records the architecture revision and the origin of every input | PASS | W13 CSG/CMT "Load from architecture" (`casing_inputs`): OD/ID/weight `architecture`, wall `derived` (OD−ID)/2, yield always `unknown` until entered (`user`; never inferred from the grade); a value edited after loading becomes `user`; required unknowns refuse the calculation; snapshot `source` holds revision id/number/SHA-256/string/provenance; a run for another well cannot be saved. Engine is the TR 5C3 subset (SCREENING). `tests/test_m89_architecture_casing_cement.py` |
| Cement worksheet: segment geometry, declared caliper, explicit excess, History | PASS (WORKSHEET) | Segments by outer boundary with `outer_source` (casing ID / declared average caliper / entered open hole / recorded hole size / unknown); excess on open hole only and only when declared ("none" ≠ 0 %); case `m89.cement_annulus` v1 with wellbore and lineage "uses architecture revision" |
| Lineage architecture ↔ casing / cement | PASS | `uses` / `used_by` in the History lineage combo |
| Cement worksheet re-run | PASS (WORKSHEET, M109) | Superseded: re-run adapter and new linked case in M109 (was NOT IMPLEMENTED in M89) |

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
| One catalogue over every method source | PASS | 50 entries at M92 (52 since M93 added the time-log and cost-per-currency methods): 10 engines (incl. hydraulics), 7 W13 contracts + 1 legacy runnable version, 20 W13 calculators without a contract (NOT SUPPORTED), 4 specialist methods (M79), 8 directional / survey / architecture / analysis methods. Versions and method strings are read from the running code; a test discovers engine classes from the source and fails if one is missing |
| Fields | PASS | ID, title, family, source, status, label, version, reference, licence, limits, approval, blocker, module; details pane; CSV export with the UNSIGNED label |
| No self-approval | PASS | Approval only from `OWNER_APPROVALS`, an immutable mapping in the source (empty in this build); every method reads "NOT APPROVED — OWNER REVIEW REQUIRED" with "owner engineering approval" as a blocker; no approve, edit or delete control; table not editable |
| Misleading-entry guard | PASS | `violations()`: duplicate id, unknown status or label, IMPLEMENTED without version/limits/module/reference, not implemented without a blocker, approval for an unknown method |
| Stored use | PASS | Count of stored W13 cases per method and version, database-wide and for the selected well |
| Engine references | PARTIAL | Hydraulics: published reference not recorded in the source (blocker shown); references are statements, not owner-verified citations |

### M84 – DDR authoring and batch import

Audit of the existing DDR path against the M84 list; two defects fixed (file identity before commit, parser clean-up for files that never ran). `tests/test_m84_ddr_identity_cleanup.py` (4, offscreen Qt; 3 hand mutants killed); DDR regression 247 tests, 0 failures, 2 expected skips.

| Capability | State | Evidence / limits |
|---|---|---|
| In-app create / edit / navigate / timeline / duplicate with validation | PASS (pre-existing) | W2 report timeline, duplicate-for-review with copy options, canonical `TimeLogValidator` on save (blocking issues refuse the save); `test_m52_ddr_manual_edit`, `test_m54_ddr_workflow` |
| Time-log edit / reorder, overlap and gap checks | PASS (pre-existing) | Row up/down (`move_time_log_row`), `time_log_issues` (overlap, gap, 24 h total, midnight crossing — same rules as import) |
| Batch import: worker DTOs, profiles, unmapped columns, atomic persist, duplicates | PASS (pre-existing) | M71 preparation worker returns plain DTOs; M54/M61 explainable profiles and column summary; atomic `DDRImportService` save; in-batch and already-imported duplicates by SHA-256 (`test_m61_ddr_profile_rules`, `test_m70_queue_lifecycle`) |
| File identity re-checked before commit | PASS (M84) | `ImportQueue.verify_identity` re-hashes the file after the preview and immediately before the atomic save; a changed or vanished file is FAILED at stage `import.file_identity` and nothing is saved |
| Truthful cancel | PASS | Not-started files are cancelled; a running third-party parse cannot be interrupted (no thread killing) — its result is discarded at the next step and nothing is committed after a cancel; closing the dialog while a worker runs is refused and turns into a cancel (`test_m71_ddr_background`) |
| Clean-up after cancel | PASS (M84) | Parser results of files cancelled or found duplicate before they ran are released (previously leaked until exit) |
| Never auto-import, no OCR | PASS | Every file passes the user preview; scanned pages are reported, never OCR-ed |

### M93 – Reports and Document Intelligence

`core/report_provenance.py` (`M93 report provenance v1`) is the single output step of the five W11 report engines (DDR, EOWR, NPT, cost, plan). `tests/test_m93_report_provenance.py` (11, offscreen Qt; 6 hand mutants killed); report/export regression 567 passed (the two release-boundary failures were the untracked new module before staging).

| Capability | State | Evidence / limits |
|---|---|---|
| Scope, sources, revisions, methods and label on every report | PASS | Label banner first and a provenance block last: well, wellbore (DDR's own or "all wellbores of the well"), report or period; tables read (checked against the schema) and daily-report count; latest report / survey (SHA-256) / architecture (SHA-256) / directional-plan revision or "none recorded"; catalogue method IDs with versions read from the code and their approval state; generation time |
| HTML / PDF / Excel / CSV | PASS | PDF through Qt `QTextDocument` (report generation does not use PyMuPDF, AST-checked; PyMuPDF remains a pre-existing import dependency, see the M101 register); Excel gets a first "Provenance" sheet; CSV (new) writes one file per sheet of the engine's own workbook with `#` provenance rows first; W11 format lists PDF / HTML / Excel / CSV |
| RTL / LTR | PASS | W11 "Document direction" applies to every report kind and the batch; `dir` on `<html>` and the body; Qt lays out every block right-to-left (checked on the PDF's document model); Excel sheets right-to-left |
| Professional 16-sheet Excel / professional PDF (batch) | PARTIAL | Separate exporter (`core/professional_export.py`); not yet routed through the provenance step |
| Document index and search | PASS (pre-existing) | `DocumentLibrary` text index and `search()`; `test_document_library`, `test_documents_tab`, `test_m49_knowledge_retrieval` |
| Manual well confirmation | PASS (pre-existing) | Well-name matches are only suggestions; a link is saved after the user confirms (`test_document_links`) |
| No OCR | PASS (standard build) / OWNER REVIEW | No OCR package is in `requirements-lock.txt`; the M44 RapidOCR hook activates only if the optional requirements are installed, and its pages stay unapproved until reviewed. Keeping or removing the optional hook is the owner's OCR decision |

### M94 – UI-path journeys A–R

`tests/test_m94_e2e_journeys.py`: three connected journeys through one real MainWindow (well → W12 Operational Analysis → drill-down → W11 export worker with provenance → well switch without leakage → Persian-named well exported right-to-left) and a register test that fails if any referenced test function disappears. All 20 referenced files: 264 passed, 0 failed, 0 skipped (offscreen Linux, stub GL/xkb/dbus libraries; **not** Windows desktop acceptance). Found and fixed: the Operational Analysis scope showed "Well #2" instead of the well name (now name + id, wellbore by name).

| Journey | Scope | State | Tests |
|---|---|---|---|
| A | Context: select / switch / clear well, no leakage | PASS (offscreen) | `test_switching_wells_leaves_no_identifier_of_the_previous_well`; `test_clear_leaves_an_empty_state_and_clean_edit_baselines` |
| B | DDR authoring: edit, reorder, navigate, unsaved edits | PASS (offscreen) | `test_a_reordered_time_log_survives_save_and_reload`; `test_unsaved_edits_are_not_discarded_without_confirmation`; `test_previous_and_next_follow_date_order_and_stop_at_the_ends` |
| C | DDR batch import: worker, cancel, file identity | PASS (offscreen) | `test_cancel_during_preparation_saves_nothing_and_cancels_the_rest`; `test_a_late_result_cannot_be_saved_for_another_well`; `test_a_file_changed_during_preview_is_never_saved` |
| D | Survey: revision, reference declaration, conversion | PASS (offscreen) | `test_freeze_import_preview_and_compare_from_the_panel`; `test_panel_requires_declaration_and_converts_with_explicit_values` |
| E | Directional plan from an inclined tie-in | PASS (offscreen) | `test_designer_panel_solves_from_an_inclined_survey_tie_in`; `test_designer_ties_in_solves_and_hands_a_continuous_plan_to_compare` |
| F | Plan vs actual / closest approach (SCREENING) | PASS (offscreen) | `test_closest_approach_between_skew_lines_is_found_between_stations`; `test_unconfirmed_crs_and_missing_datum_are_not_assessed_with_every_reason` |
| G | Well architecture revision and cement worksheet | PASS (offscreen) | `test_w3b_architecture_page_freezes_reloads_and_derives_cement`; `test_w3b_cement_worksheet_with_caliper_and_excess_is_saved_with_lineage` |
| H | W13 case: save, reopen, re-run, clone, export | PASS (offscreen) | `test_bit_case_save_reopen_rerun_clone_export_and_verify`; `test_w13_casing_from_architecture_reaches_history_with_lineage` |
| I | History lineage and navigation | PASS (offscreen) | `test_history_tab_opens_a_linked_record_on_another_page`; `test_lineage_follows_revision_chains_and_the_architecture_survey_link` |
| J | Operational analysis with drill-down | PASS (offscreen) | `test_w12_page_refresh_drilldown_invalidation_and_export`; `test_journey_context_to_operational_analysis_drilldown_and_switch` |
| K | Report export with provenance | PASS (offscreen) | `test_every_engine_writes_provenance_in_every_format`; `test_journey_report_export_through_w11_carries_the_selected_well_only` |
| L | Stale async results are discarded | PASS (offscreen) | `test_context_token_changes_on_every_selection_event`; `test_a_late_result_cannot_be_saved_for_another_well` |
| M | Well delete: history goes with the well, audited, authorised | PASS (offscreen) | `test_deleting_a_well_removes_its_history_rows_with_one_audit_record`; `test_a_viewer_cannot_delete_a_well_with_history`; `test_deleting_the_project_of_the_selected_well_clears_the_selection` |
| N | Backup / restore | PASS (offscreen) | `test_file_database_backup_corruption_restore_and_reopen`; `test_restore_brings_back_revisions_with_their_immutability_guards` |
| O | Offline: no network library on the product path | PASS (offscreen) | `test_new_modules_import_no_network_library` |
| P | Language: Persian data, right-to-left output | PASS (offscreen) | `test_persian_answer_is_right_to_left_and_long_passages_are_elided`; `test_rtl_reaches_html_pdf_layout_and_excel`; `test_journey_persian_well_report_right_to_left` |
| Q | Method catalogue, no self-approval | PASS (offscreen) | `test_help_menu_opens_a_read_only_catalogue`; `test_no_self_approval` |
| R | Authorisation: viewers cannot write | PASS (offscreen) | `test_a_viewer_cannot_save_a_conversion`; `test_viewers_cannot_save_an_architecture` |

### M95 – UX responsiveness audit (measured)

Tool: `tools/quality/ux_responsiveness_m95.py` (real MainWindow, file SQLite, synthetic M70 world + 365 daily reports × 8 time-logs on one well, production GUI-thread GC policy). `max gap` = longest interval between 5 ms GUI timer ticks, i.e. the longest time the event loop could not run. **Offscreen Linux (2 CPUs, stub GL/xkb/dbus libraries): not a Windows desktop measurement; no Windows responsiveness claim is made.**

| Path | Before M95 (ms / max gap) | After M95 (ms / max gap) | State |
|---|---|---|---|
| Operational Analysis refresh, 1 year (median of 5) | 421 / 437 | 65 / 81 | PASS – `ActivityMapper` was ~90 % of the time; memoised per call (`_map`, returns only `canonical_id`/`method`; parity tested, whole analysis identical) |
| W10 Planning first visit after a selection | 326–397 / 332–397 | 144 / 148 | PASS – the whole-well code statistics and FACT/PLAN chart were built and then rebuilt for the pending section; the whole-well pass is skipped only when a section follows |
| Well switch (median of 5) | 11.6 / 30 | 10.5 / 30 | PASS |
| Other 18 selection-scoped tabs, first visit | ≤ 76 / ≤ 93 | ≤ 65 / ≤ 77 | PASS |
| Method Catalogue open | 11 / 11 | 11 / 11 | PASS |
| W11 EOWR HTML export (worker) | 57 / 9 | 63 / 9 | PASS – GUI never blocked |
| MainWindow startup (construction + show) | 1333 / 1306 | 1349 / 1318 | PARTIAL – one blocking construction of all tabs; pre-existing, not changed in M95 (lazy tab construction would be a structural change) |

Defects found by the audit tests and fixed: (1) W10 sub-tabs are `make_scrollable` wrappers – sub-tab state must be written on `_inner`, otherwise a section load would run against the previous well (regression test); (2) re-selecting the same well without a section left the W10 sub-tabs filtered by the old section while the combo showed "All Sections" – a well selection now clears sub-tab section/report. Tests: `tests/test_m95_ux_responsiveness.py` (13 incl. 8 parity cases); hand mutants 4/4 killed (no `_inner`, no child clear, no table clear on await, per-code cache for all methods). Regression over all W10/OA/selection/journey files: 179 passed.

### M96 – Persistence audit

Method: every table holding a foreign key to `wells`, `sections` or `daily_reports` gets one synthetic row (all NOT NULL columns filled) in a fresh world, then its parent is deleted **through the application path** (`delete_hierarchy_entity`). This runs on a fresh database and on one upgraded from an old schema. `tests/test_m96_persistence_audit.py`: 39 tests.

| Area | Finding before M96 | State after M96 |
|---|---|---|
| Foreign keys | `PRAGMA foreign_keys=ON` on every pooled connection; `foreign_key_check` clean | PASS |
| Well / project / company delete | **Defect:** 6 legacy W13 tables (`casing_`, `cement_`, `mse_`, `mud_volume_`, `torque_drag_`, `well_control_kill_sheet_calculations`) reference `wells` with no ON DELETE action and no ORM cascade. One W13 calculation saved with a well selected made that well (and its project/company) undeletable: `delete_well` returned False | PASS – removed in the same audited transaction, with per-table counts in the audit `details`. A model test fails if a new well FK has neither ON DELETE, an ORM cascade nor a sweep entry |
| Section delete | **Defect:** `operational_procedures.section_id` (no ON DELETE action) blocked deletion of its section | PASS – the reference becomes unknown (NULL). This runs in a narrow `hierarchy_delete_unlink` scope (that column, update only) inside the policy-checked delete; a plain update by the same principal is still refused |
| Report delete | Every report child removed or unlinked | PASS |
| Wellbore delete | No standalone UI path (wellbores go only with their well); `ON DELETE SET NULL` on history keeps lineage (M70 test) | PASS (scope note) |
| Rollback | A refused (viewer) delete and a failing audit both roll back the sweep; an exception inside a unit of work leaves nothing behind | PASS |
| Immutability, every path | **Defect:** guards were BEFORE UPDATE only. `INSERT OR REPLACE` / `REPLACE INTO` overwrote an immutable calculation case (verified), and a direct `DELETE` removed a single history row | PASS – BEFORE INSERT guards (id clash; unique-key clash with SQLite's own `UNIQUE constraint failed: uq_…` wording, so concurrent-revision reporting is unchanged) and BEFORE DELETE guards (allowed only once the owning well/case is gone, i.e. its cascade) on all 5 history tables. Well-less calculation cases can never be deleted |
| Migrations | New triggers install additively on start (versioned names); re-initialising is idempotent (schema identical, `install()` creates nothing); `integrity_check` ok on fresh and upgraded databases | PASS |
| Concurrency | WAL and `busy_timeout` ≥ 5 s on every connection; a reader never sees an uncommitted write; a second manager's commit is visible | PASS (single-machine SQLite; no multi-host claim) |

Hand mutants 6/6 killed: (1) sweep list minus one table; (2) no insert guard; (3) no delete guard; (4) unlink without its scope; (5) unique-key message without the SQLite wording. Mutant 5 survives the plan-stale test alone (the service also matches the constraint name) but is killed by the guard test. Regression over 45 history, deletion, migration and authorization files: 731 passed.

### M97 – Qualification (full suite, mutation, gates)

| Capability | State | Evidence / gap |
|---|---|---|
| Full suite on the exact checkpoint SHA | PASS | `python verify_release.py --coverage` on `c776e8cd863b88623df0a8719cf497fbede93d73` (2-CPU Linux sandbox, Python 3.11.2, PySide6 6.8.1.1 offscreen with a locally built EGL/xkbcommon/dbus and a stub libGL): collected 4454 = 4450 passed + 4 skipped, 0 failed, 0 errors, 1440 s. Baseline M81 4272 passed + 4 skipped; +178 = 178 items in the 14 new M83–M96 test files + 1 M73 gap test − 1 M72 parametrized case ("vertical tie-in" refusal) removed in M86 when the solver gained inclined tie-ins. Skips unchanged: the same 4 opt-in external acceptance tests |
| Coverage (branch+line, tracked product files) | PASS | 66.29% over 240 tracked files (62289/93969); target 65 reached (floor 45.50, unchanged) |
| Mutation – M83–M96 behaviour (new, `tools/quality/mutation_m83_m96.py`) | PASS | 20 mutants, 20 killed. The first run found one real gap: `entry_status` could report an UNREADABLE record as readable without any failing test. `test_entry_status_reports_records_whose_stored_data_cannot_be_read` added (M73 file) |
| Mutation – earlier suites, full selection | PASS | m70_m76 18/18; m61_m67 19/19; m52 70 mutants: 69 killed + 1 declared equivalent (unchanged since M52, `W12-staged-paint-ignores-scope`). Two m52 anchors went stale or ambiguous after M84/M95 and were re-anchored to the code that now holds the behaviour (not weakened); both KILLED |
| Ruff (new and modified files), lint ceiling, exception scan, privacy | PASS | 0 new ruff findings; lint 727 / ceiling 727; silent-exception ceiling held; privacy 0 findings over 1309 files |
| Performance vs M80 (`tools/perf/m80_measure.py --cases 3000`, 3 runs, median ms) | PASS (evidence, not a gate) | History full load 80.63 → 48.8–49.2; first page 12.04 → 10.2–10.9; survey save 2000 stations 50.04 → 36.5–44.9; architecture save 1.08 → 0.83–1.29; build-hold solver ×1000 4.01 → 8.45–10.66 (slower: M86 replaced the vertical-only closed form with the general 3-D tie-in solver and a whole-arc inclination check; profiled, about 9 µs per solve, one solve per user action) |
| Windows CI on the final code SHA | PASS | `c776e8cd863b88623df0a8719cf497fbede93d73`: Windows release validation run 41451853860 and Source release gate run 41451853825 (3.11/3.12/3.13), all jobs success. Windows CI is not desktop acceptance |

### M98 – Owner desktop acceptance procedure

| Capability | State | Evidence / gap |
|---|---|---|
| Procedure for journeys A–R, M95 measurement on Windows, record template | PASS (document) | `packaging/WINDOWS_RELEASE_ACCEPTANCE.md` → "M82-M100 owner desktop acceptance procedure" |
| Execution on a Windows desktop | OWNER REVIEW REQUIRED | NOT EXECUTED — OWNER DESKTOP ACCEPTANCE REQUIRED |

### M99 – Reconciled starting defect register

| Starting defect (M82) | Final state | Where |
|---|---|---|
| Selection lifecycle not uniform | PARTIAL | M83: clearing and A→B switches are uniform across tabs; workers still use tab-local tokens; no company/project/rig/date signals |
| DDR cancellation cannot interrupt a third-party parse | PASS (truthful cancel) | M84: never commits after a cancel and releases parser results; the running parse itself is not interrupted (no thread killing, by design) |
| Survey azimuth/datum stored but not transformed | PARTIAL | M85: azimuth conversions PASS; depth datum and CRS NOT IMPLEMENTED |
| Solver handles a vertical tie-in only | PASS | M86: any tie-in direction; multi-segment optimisation NOT IMPLEMENTED |
| Only Quick Calc has a W13 contract | PARTIAL | M87: 7 of 27 re-runnable; 20 NOT_SUPPORTED, shown as NOT REPRODUCIBLE (superseded by M107: 18 contracts, 9 NOT_SUPPORTED with exact reasons) |
| Cement is a nominal worksheet | PARTIAL | M89: segment geometry, caliper, open-hole excess, History; M109: contract, re-run and linked re-run case; still a WORKSHEET (no slurry design, not wired into the W13 cement engine) |
| Casing does not record the architecture revision | PASS | M89 |
| History coverage incomplete | PARTIAL | M88: 11 sources; M108: coverage register + guard test, new trajectory records versioned and re-runnable; legacy trajectory rows and the 9 NOT_SUPPORTED W13 calculators remain captured only (reasons shown) |
| Specialist registry not in the UI | PASS | M92: Help → Method catalogue (52 entries, all NOT APPROVED) |
| No Operational Analysis code | PASS / PARTIAL | M91: footage, ROP, NPT, activity, bit runs, cost, drill-down, export PASS; MSE trend and plan vs actual PARTIAL |
| Windows checklist not executed | OWNER REVIEW REQUIRED | M98 procedure written; NOT EXECUTED |

Reconciled documents (M99): this matrix, `ENGINEERING_METHODS_AND_LIMITATIONS.md` (M85–M96 sections),
`DRILLMASTER_USER_WORKFLOWS.md` (workflows 14–17), `ENGINE_INVENTORY.md` (regenerated, `--check` current),
`packaging/WINDOWS_RELEASE_ACCEPTANCE.md` (M98 section, current branch name).

## M101–M120 – Product closure programme

Statuses: PASS / PARTIAL / BLOCKED / NOT IMPLEMENTED / NOT RUN / OWNER REVIEW REQUIRED.
Product label: UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED. Start: code `c776e8c`, report `e90843f`.

### M101 – Evidence reconciliation

| Item | Finding | Resolution |
|---|---|---|
| Coverage numerator | CI Python 3.12 job 125298732667 annotation: 66.29% **62291/93969**. The M82–M100 report printed the local Python 3.11 figure 62289/93969 without labelling it as local | Report corrected (CI authoritative; local labelled) |
| PyMuPDF statement | "No PyMuPDF/fitz imported" was true only for the programme diff. PyMuPDF 1.24.14 is a pre-existing mandatory dependency, imported by `core/ddr_pdf_split.py`, `core/document_import.py`, `core/import_adapters/pdf_tables.py`, `core/document_library.py` (and three screenshot tools). §E wrongly said "remains excluded" | Report and this matrix corrected; AGPL-3.0 owner decision stays open (M112) |
| M52 "equivalent" mutant `W12-staged-paint-ignores-scope` | The proof assumed no exception between the scope bump and the cancel reached through `update_scope_indicator → update_all_data`. When that read raises (Qt swallows slot exceptions), only the generation check stops the old paint | Not equivalent. New scenario `scope_change_whose_refresh_fails_still_stops_the_old_paint` kills it |
| Warnings (CI 3.12: 859; local 3.11: 36) | The CI log is unreachable from this workspace (blob host). The Python 3.12 inventory cannot be produced locally | `verify_release.report_warnings` now prints the grouped inventory and annotates it in CI (check-run annotations are readable); inventory recorded in M118 |
| `THIRD_PARTY_NOTICES.md` | Defers runtime licences to the manifests, which carry no licence names; PyMuPDF's AGPL-3.0 is disclosed nowhere | M112 |

### M101 – Defect register (prioritized, source-backed)

| # | Priority | Defect (verified in source) | Phase | State |
|---|---|---|---|---|
| D1 | P0 safety | `survey_revisions.verify_results` compares TVD/N/E only and passes when a key is missing; MD, inclination, azimuth, DLS, VS and HD are unchecked | M105 | **resolved (M105)** |
| D2 | P0 safety | `tie_in_from_revision` checks only the station hash (and defaults a missing `integrity` to VERIFIED), then uses the stored derived results. A tampered `results_json` can become a plan tie-in. `compare_revisions` and plan vs actual also use unverified results | M105 | **resolved (M105)**; also found and closed: `directional_plans._check_survey_tie_in` matched the tie-in against unverified `results_json` |
| D3 | P1 | `tabs/operational_analysis_panel.refresh` runs `oa.analyze` synchronously on the GUI thread | M103 | **resolved (M103)**: measured 168 ms on one synthetic year; now a `ContextJobRunner` job with its own read-only connection, stale/superseded rejection, cancel, retry and bounded close |
| D4 | P1 | `core/professional_export.py` writes a hard-coded `"Revision": "Rev 0"` and shows a free-text `Approved By` as an approval; the 16-sheet workbook bypasses M93 provenance | M110 | **resolved (M110)**: the actual latest report revision, "No report revision recorded", or "Whole-well export — M110 professional export template v1"; names the daily report does not store show "not recorded"; the `approval_actions` record is shown as a workflow status, never as a signature; Excel gets a Provenance sheet and the PDF the M93 banner/provenance block in LTR or RTL; per-report workbooks in batches |
| D5 | P1 | `operational_analysis` uses whole-well `get_actual_vs_plan` and flags it only for a wellbore scope, not for a date range | M104 | **resolved (M104)**: plan vs actual is assessed only for the whole well without a date range; otherwise every row is NOT ASSESSED with the reason. Cost (no wellbore column) is not assessed for a wellbore |
| D6 | P1 | MSE records carry no wellbore/MD/source lineage; the trend is per well only | M104 | **PARTIAL (M104)**: additive columns `wellbore_id`, `report_id`, `input_source`, `lineage_version` are recorded for new saves (validated against the well); legacy runs stay unknown; the wellbore scope shows only that wellbore's runs. **MD is not recorded**: the W13 inputs carry no depth and a report's depth is not the depth of the run (no invented depth) |
| D7 | P1 | `SelectionManager` has well/wellbore/section/report signals only; `context_token()` exists but no tab consumes it; workers use tab-local tokens (W12, analysis views, trajectory compare, knowledge assistant) | M102/M103 | **PARTIAL**: context snapshot and `context_changed` reach all 21 tabs (M102); `context_token()` is consumed by `core.context_jobs` (M103, OA). The existing tab-local tokens in W12 snapshot reads, analysis views, trajectory compare and the knowledge assistant stay (they already reject stale results; migration is not needed for correctness) |
| D8 | P1 | 20 of 27 W13 leaves NOT_SUPPORTED (`core/calculator_contracts.NOT_SUPPORTED`) | M107 | **resolved (M107)**: 18 contracts; the 9 others are NOT_SUPPORTED with the exact reason (the table or state that is not captured, or the owner gate). See "### M107" |
| D9 | P2 | Cement worksheet captured only (no re-run adapter) | M109 | **resolved (M109)**: contract + re-run from the frozen architecture revision after its SHA-256 check; a re-run is stored as a NEW worksheet case linked `rerun_of`; labelled WORKSHEET — NOT A CEMENT DESIGN APPROVAL. Still a worksheet: not wired into the W13 cement engine, no slurry design |
| D10 | P2 | Directional solver: one arc + tangent only (no S-profile, build-turn or multiple targets) | M106 | **resolved (M106)**: multi-target chained curve-hold legs (build, drop, hold, turn in 3D, optional hold after each target, rate per leg) and a closed-form S-profile; DLS and inclination limits are hard; every solve is re-computed by the canonical engine. Limits: the S-profile needs a vertical tie-in; nothing is optimised; anti-collision stays SCREENING |
| D11 | P2 | Depth datum and CRS: not modelled | M105 | PARTIAL (M105): explicit vertical depth-datum shift implemented; CRS/geodetic NOT IMPLEMENTED by scope (`SURVEY_REFERENCE_SCOPE.md`), owner decision open |
| D12 | P2 | A running third-party parse cannot be interrupted (thread) | M111 | **resolved (M111)** for the production parsers: `core/isolated_parse.py` runs DDR preparation in a `spawn` child (plain data only, persistence in the parent, identity checked before/after, cancel discards late results, join → terminate → kill, no orphans). Injected parsers and a successful MinerU result stay in the M71 thread (cannot cross a process; stated). Windows spawn acceptance is an owner gate |
| D13 | P2 | Runtime dependency licences not disclosed | M112 | **resolved for disclosure (M112)**: `tools/quality/dependency_audit.py` classifies all 26 pins of `requirements-lock.txt` and every third-party import (160 import sites, guarded or not, declared or not) into `docs/engineering/dependency_audit.json`; the test fails on an unknown licence class, an unguarded optional import or a forbidden binding. The licence **decisions** stay open owner gates (`M112_OWNER_DECISION_PACKS.md`): PyMuPDF AGPL-3.0, PySide6/shiboken6 LGPL-3.0, pwptemp/torque_drag LGPL-3.0, qtribbon unknown, MinerU custom |
| D14 | P3 | Legacy trajectory calculations are captured only (no method identity) | M108 | **resolved for new records (M108)**: column `method_version` (additive), records hold their input stations and an inputs SHA-256 and re-run from History (MATCH / DIFFERENT / UNREADABLE). Rows saved before M108 stay "unversioned (legacy)" and NOT REPRODUCIBLE by design — the stations they used were never stored and the current method is never assigned to them |
| D15 | P2 | (found in M105) The M101 warning inventory counted pytest's collapsed `file: N warnings` lines (ten or more locations) as one occurrence each and read only the first summary section. CI 3.12 on `fc2daf2` therefore annotated 134 occurrences where pytest counts 859 | M105 | **resolved (M105)**: collapsed lines count N, every section is read, and the inventory is reconciled against pytest's own total (a mismatch is printed and annotated, never hidden) |
| D16 | P3 | (found in M105 from CI 3.12 annotations) Repository `DeprecationWarning`: sqlite3's default datetime adapter (deprecated in Python 3.12), raised through `core/database.py` raw `execute` calls. Its largest groups are 86 and 12 occurrences, as counted by the faulty inventory and so under-counted | M116 | open; legacy, not suppressed |
| D18 | P1 | (found in M102 by the extended probe) Values of the previous context stayed on screen: the daily report form kept the loaded report's date and summary after a well switch and after a clear; the export centre kept the report list and preview; planning tables kept report dates after a clear; cost cards kept the cost after a clear; section data kept the section label after a switch. M83's probe missed them because it never loaded a report and did not read date edits or model views | M102 | **resolved (M102)** |
| D23 | P2 | (found in M104) M103 made the OA refresh asynchronous but `tools/quality/ux_responsiveness_m95.py` still read the result right after `refresh()`, so `test_m95_ux_responsiveness` failed on `333313f`; the M103 focused regression had not included that file | M104 | **resolved (M104)**: the tool measures refresh until the result is shown (`wait()` pumps events) and reports `background` |
| D24 | P3 | (found in M104) The M102 refactor of `DailyReportWidget.new_report` (form reset moved to `_empty_report_form`) left the `mutation_m53_m56` anchor `W2-new-report-ignores-guard` matching nothing, so that mutant could not run | M104 | **resolved (M104)**: repointed to the same guard in the refactored code (not weakened) and KILLED; all 444 anchors of the 12 suites match exactly once (checked after M104) |
| D25 | P1 | (found by CI on `333313f`) M102 made `DrillTabBase._on_well_changed_internal` read `self.sel_manager`, which editors built without a selection manager do not have; three tests in `test_real_user_acceptance_regressions` failed. The M102/M103 focused regressions did not include that file, and the M102 CI run was cancelled before it reported | M106 | **resolved (M106)**: no selection manager means no known wellbore; the M102 mutant on that line was repointed and is KILLED. Process change: the full suite runs locally before each phase commit |
| D26 | P1 | (found in M107) Weight-up sack count: `MudVolumeEngine.weight_up` used V×42×ΔMW/(ρ−MW2)/100, leaving the additive density out of the sack mass, and W13 offered barite as "1470 pcf" (the ppg constant 42×35 used as a density); W15 printed the same formula. 500 bbl from 80 to 90 pcf gave 1.52 sacks instead of ≈427 | M107 | **resolved (M107)**: V×5.6146×ρ×ΔMW/(ρ−MW2)/100 in pcf/bbl, method "v2"; barite 4.20 SG = 262.2 pcf; one additive list for screen and contract; an unknown entry has no density (not a default). Calcium carbonate 170 pcf and hematite 320 pcf are unchanged (constant inventory, M113). Earlier weight-up results were never stored with a method version (generic W13 cases are UNVERSIONED / NOT REPRODUCIBLE), so no history is relabelled |
| D27 | P2 | (found in M108) `DatabaseManager.save_trajectory_calculation` updated an existing trajectory calculation in place when one matched the same report, or the same well and calculation date — method, parameters, results, totals and description were overwritten (never-overwrite rule). Only caller: the unused `TrajectoryCalculationManager.create_calculation` (W6), so no stored record is known to have been overwritten, but the path existed | M108 | **resolved (M108)**: insert-only; every call adds a new row; `method_version` only when supplied; test saves twice with the same well and date and checks the first row is unchanged |
| D28 | P3 | (found in M109) `test_m49_knowledge_ui.py::test_generation_never_blocks_the_ui_and_cancel_works` failed once in the full suite (its 10 s wait for the cancelled worker to be released timed out) and passed 23/23 three times in isolation; earlier full runs (M106–M108) passed it. A timing dependence under load, not a product failure shown so far | M118/M119 | **open**: re-observe in the M118 full run; investigate the worker-release path before changing the wait (no blind timeout increase) |
| D29 | P1 | (found in M110) `ProfessionalPDFExport.export` evaluated `metadata.get('Report Info', {{}})` inside its HTML f-string: in an f-string expression `{{}}` is a set holding a dict, so every professional PDF export raised `TypeError: unhashable type: 'dict'`, logged it and returned False without writing a file (W11 single and batch "Professional PDF"). Only an import smoke test referred to the class | M110 | **resolved (M110)**: the report info is read before the f-string; tests write the PDF in LTR and RTL; mutant `PE-pdf-report-info-set-literal` restores the defect and is KILLED |
| D17 | P3 | (found in M105) The CI 3.12 coverage numerator differs between runs: 62291/93969 on `c776e8c` (job 125298732667), 62289/93969 on `fc2daf2` (job 125749573280). The denominator is the same and M101 changed no tracked product file, so the ±2 lines are run-to-run variation (timing-dependent branches). This is not a regression | M118 | recorded; each report quotes the exact job |
| D30 | P2 | (found in M112 by the import audit) `EngineeringCalculatorTab._wt_import_reference_catalog` imported `QInputDialog` from **PyQt5** to ask for the worksheet of a multi-sheet vendor drill-pipe workbook. PyQt5 is not installed (and is GPL-3.0); the `ImportError` was caught by the broad handler, so the prompt never appeared and the active sheet was imported silently | M112 | **resolved (M112)**: `QInputDialog` comes from PySide6; the widget test asks for the sheet ("Aa" preselected) and imports the chosen sheet; mutant `W13-pyqt5-sheet-dialog-restored` killed; `test_no_pyqt_import_anywhere_in_the_product` guards the whole product |
| D31 | P2 | (found in M114) Document search ignored the library scope. With "Linked to the selected well" chosen, the list showed only that well's documents, but a search still returned hits from every document, including other wells' documents. After a well switch, a filter change or a deletion the previous hits stayed on screen. `DocumentLibrary.search` also had no way to restrict documents before its LIMIT | M114 | **resolved (M114)**: `search(..., document_ids=...)` restricts to the scope's pages inside the query, before LIMIT (FTS5 via a read-only `json_each` parameter, and the substring-scan fallback), and an empty scope searches nothing. The tab uses the same `_filter_documents` for the list and the search, states the scope, and re-runs an open search on every refresh (filter, selected well, links, delete). With no well selected it says so. 8 mutants killed |

### M105 – Survey integrity, depth datum and plan references

Acceptance criteria and evidence (synthetic data; offscreen Qt):

| Criterion | Status | Evidence |
|---|---|---|
| `verify_results` covers all 9 fields (md, inc, azi, tvd, north, east, vs, hd, dls), each with its own unit and tolerance (`RESULT_FIELDS`), wraps azimuth at 360°, and checks count, order (as MD differences), the exact key set (missing/extra), finiteness and None | PASS | `tests/test_m105_survey_integrity.py`: one parametrised alteration per field; a tolerance boundary per field (0.1× passes, 10× fails); wrap; missing/extra/reversed/truncated/NaN/None/non-list cases |
| Optional versioned results hash (`M105 survey results hash v1`) stored by save, azimuth transform and datum shift; pre-M105 rows show **NOT RECORDED** (NULL, never backfilled) | PASS | Additive column `survey_revisions.results_sha256` via `ADDITIVE_COLUMNS`, applied on every startup and idempotent; an old database without the column gains it on `initialize()`. The revisions panel has a "Results hash" column |
| Fail closed before use: `verify_for_use` (station hash VERIFIED, no results-hash mismatch, full recomputation MATCH) gates tie-in, azimuth transform, datum shift, revision compare, the plan-save tie-in check and plan-vs-actual on a revision | PASS | Tampered results with a hash are refused everywhere. Forged legacy results (hash NULL) are refused by recomputation ("north differs"). A missing integrity state is not VERIFIED |
| Datum offset only with explicit parameters, as a new revision | PASS | `transform_depth_datum` (`M105 vertical depth-datum shift v1`). Requires both elevations against one stated reference plus a value source. Refuses a missing elevation (never zero), a zero shift, the same datum, an inclined first station, and stations above the new datum (never dropped). Golden: RKB +30 m / GL +5 m vs MSL, so every MD and TVD is −25 m exactly; N/E/inc/azi/vs/hd/dls unchanged; shifting back restores the stations. Desktop: "Shift depth datum" row in the survey revisions panel |
| CRS scope document; no GIS, no network | PASS | `docs/engineering/SURVEY_REFERENCE_SCOPE.md`. Catalogue entry `survey.datum_transform` added; the `survey.revision` and `survey.azimuth_transform` limits were updated |
| Plan files declare their reference | PASS | Plans record `references` (azimuth reference, depth datum). A survey tie-in supplies them and a contradiction is refused (designer and service). The CSV export writes `azimuth_reference=…; depth_datum=…` in its comment row and now reads back into plan-vs-actual. `read_plan_file_with_reference` parses leading `#` rows (CSV/XLSX) and refuses duplicate or unknown values. Plan-vs-actual refuses differing declared references and labels undeclared ones "NOT DECLARED … unverified". Legacy plans: NOT DECLARED, inputs unchanged |
| Mutation | PASS | `tools/quality/mutation_m101_m120.py`: **20/20 killed** (baseline 44 passed). Existing `SR-hash-not-verified` (m83_m96) and `DP-survey-sha-unchecked` (m70_m76) re-run: KILLED. All 549 anchors in the 11 earlier suites still match once, in the same enclosing function |
| Regression | PASS | 327 tests across 20 survey/plan/compare/history/catalogue/journey/persistence files, rc=0 |

Limits: CRS, geodetic datums, magnetic models and grid-convergence computation stay NOT IMPLEMENTED (owner scope).
The datum shift is vertical only.

### M102 – Full selection context

Acceptance criteria and evidence (synthetic data; offscreen Qt, Linux):

| Criterion | Status | Evidence |
|---|---|---|
| One context object with every level the model supports: company, project, well, rig, wellbore, section, report number and date, period | PASS | `ContextSnapshot` (frozen) from `SelectionManager.snapshot()`. Rig is the well attribute `rig_name`: the model has no rig entity, so there is no rig selection and none is invented. The period is an analysis filter (validated, day-granular, kept across well switches and clears) |
| Labels come from the database relations, not from payloads; no invented relations | PASS | `core/selection_context.resolve` follows Company ← Project ← Well ← Wellbore/Section ← DailyReport only. A wellbore, section or report of another well is withheld and reported as a context conflict (tested with real foreign rows) |
| Signals reach all tabs, including legacy ones | PASS | `context_changed` after every change; `select_full_context` emits it once. All 19 `DrillTabBase` tabs get `current_context`, `current_wellbore_id` and the `on_context_changed` hook; CalculationHistoryTab and DocumentsTab are subscribed. The status bar shows the resolved path. Test: every one of the 21 tabs holds the same snapshot |
| Leak probes beyond IDs: report numbers, dates, descriptions, stations, architecture, plans, cost and NPT, forms, rows | PASS | `tests/test_m102_context_probes.py` reads line edits, labels, combo values, text edits, spin boxes, date edits, group titles, tab labels, table/list/tree widgets, every model view and pyqtgraph data. Positive controls first prove that every data kind is visible for the alpha well (at least 10 tabs). After a switch and after a clear no tab shows any alpha mark; switching back shows alpha again. Architecture names are not listed by the panel, so it is checked by revision rows (1 for alpha, 0 after the switch) |
| Real leaks fixed | PASS | D18: daily report form (switch and clear), export centre, planning tables, cost cards, section label |
| Documents follow the selection on request | PASS | "Linked to the selected well" filter; the default view stays portfolio-wide |
| Mutation | PASS | 18 mutants: **18/18 killed**. On the first run `SC-foreign-wellbore-shown` survived because the test used a non-existent wellbore id; the test now uses a real wellbore of another well and the mutant is killed |
| Regression | PASS | 238 tests across 26 selection/tab/journey files, rc=0 |

Portfolio views (Home, Documents with "All documents") list every well by design and are outside the leak probe.

### M103 – Background jobs bound to the selection context

Measured first (`tools/quality/measure_m103.py`, one synthetic year: 365 reports, 4,380 time-log rows; median of 3; Linux CPython 3.11.2):
`operational_analysis.analyze` 0.168 s (over the 100 ms GUI budget), `calculation_history.load_history` 0.0064 s (under budget, stays synchronous).
Trajectory comparison and Export Center jobs already ran in workers before M103.

| Criterion | Status | Evidence |
|---|---|---|
| Reusable pattern: GUI snapshot, worker session, DTOs, context token, stale rejection | PASS | `core/context_jobs.ContextJobRunner`. Plain parameters are captured on the GUI thread; the worker gets its own read-only connection (`worker_database`, `mode=ro`; a write fails); `SelectionManager.context_token()` is captured at start and a changed token rejects the result as STALE. In-memory databases run synchronously and say so |
| Loading / empty / error / retry / cancel / safe close | PASS | States LOADING, DONE, EMPTY, ERROR (type name only), CANCELLED, STALE. `retry()` re-runs the captured snapshot. Cancel is cooperative and the result is discarded even if the job ignores it. `shutdown(timeout)` cancels and joins within the bound and reports a worker that did not stop |
| Operational analysis uses it | PASS | Refresh starts a job; Cancel and Retry buttons; `oa.analyze(cancel_event=…)` checks between its five sections; W12 `cleanup()` joins the job |
| Tests: switch during a job, close during a job, newer job finishing first | PASS | `tests/test_m103_context_jobs.py` (16 tests, real QThreads, event-gated so each interleaving is exact): stale after switch; newer job wins whether the older finishes first or last; close joins a cooperative job and bounds an uncooperative one; OA switch shows nothing of either well; OA close joins the worker; OA error then retry |
| Mutation | PASS | 7 mutants: **7/7 killed** |
| Regression | PASS | 323 tests across the W12, analysis, trajectory compare, export worker, journey and M102 files, rc=0 |

Not migrated (they already reject stale results with their own tokens): W12 snapshot reads, analysis views, trajectory compare, knowledge assistant.

### M104 – Operational analysis: scope, MSE lineage, KPI register

| Criterion | Status | Evidence |
|---|---|---|
| MSE lineage for new records through an additive migration; legacy stays unknown | PASS | `mse_calculations` gains nullable `wellbore_id` (FK, SET NULL), `report_id` (FK, SET NULL), `input_source`, `lineage_version` through `ADDITIVE_COLUMNS` (idempotent, no backfill), and two indexes in `INDEX_PLAN`. `MSECalculationRepository.save_run` validates that the wellbore and report belong to the run's well (and the report to that wellbore); W13 records the selected wellbore and report of the same well. Legacy runs show "unknown (saved before lineage was recorded)". Test: a pre-M104 table rebuilt without the columns gains them on startup with zero backfilled rows |
| MD lineage | NOT RECORDED | The W13 MSE inputs have no depth; the linked report's depth is not the run's depth |
| Wellbore scope | PASS | MSE: only runs recorded for the wellbore; runs without a wellbore are counted in a note and not attributed. NPT register: only rows linked to the wellbore's reports (M91). Cost: NOT ASSESSED (cost records have no wellbore or report column) |
| Plan vs actual scope-aware, else not assessed with a reason | PASS | Assessed only for the whole well without a date range (reason names the plan id); a wellbore or a date range gives NOT ASSESSED with the reason; units per row (m, h, m/h, cost currency) |
| NPT kept separate | PASS | Time-log NPT and the NPT register are separate KPIs and never summed (M91, unchanged) |
| Footage/ROP edge cases, bit drill-down | PASS | Bit runs: depth out shallower than depth in is INVALID with both depths; ROP basis says "no hours on bottom" or "hours on bottom unknown"; daily rows say "drilling time unknown" when a log has no duration. New "Bit run rows" table lists every drilling-parameters row of each run, with report number and drill-down to the report |
| Per-currency cost | PASS | One KPI per currency; records without a currency are never summed; no converted or mixed total |
| Every KPI shows value, unit, scope, source, quality, reason | PASS | New "KPI register" table (first tab, exported): quality COMPLETE / PARTIAL / NOT ASSESSED; an unknown value is never 0 and always has a reason; scope names the well/wellbore and the date range |
| Filters: well, wellbore, dates | PASS | From the selection (well, wellbore) and the panel's date range (M91), now applied to MSE lineage and plan scope as well |
| Mutation | PASS | 13 new mutants: **13/13 killed**. Re-run because M103/M104 changed their code: M83–M96 OA 4/4, M50 11/11, M51 6/6, M52 W12 5/5 killed (26/26). The 27 M48 W12 mutants were not re-run: the only W12 change is the one-line `cleanup()` hook and their anchors still match |
| Regression | PASS | 365 tests across schema, migration, index, MSE persistence/history, W12/W13, OA, journeys and M103/M104 files; 3 failures found and fixed (D23, two expected consequences of the four new columns: the column count pinned in `test_mse_cross_process` and the report-child index rule) |

`OA_VERSION` is now "M104 operational analysis v2". CI on `01f0b3e` (M102) was cancelled by the next push (not a pass). CI on `333313f` (M103): Windows validation success (run 41611891237); Source release gate **failure** (run 41611891235, job 125836193787: collected 4539, passed 4531, skipped 4, **failed 4**): D23 and D25.

### M106 – Multi-segment directional solver

| Criterion | Status | Evidence |
|---|---|---|
| Build / drop / hold / turn | PASS | `solve_multi_target`: each leg is one constant-curvature arc in the plane of the arrival direction and the next target, then a tangent; it builds, drops and turns as the geometry needs (golden: build to 30°/45°, build-and-turn to 50°/80°, drop-and-turn to 20°/100°) |
| S-profile | PASS | `solve_s_profile`: vertical, build, tangent, drop to a final inclination, final hold; closed form in the target's vertical plane (formula in the docstring). Inclined tie-in: NOT SUPPORTED with a reason (use the multi-target solver) |
| Multiple targets | PASS | Ordered legs through every centre; optional hold after each target; one rate or one rate per leg |
| DLS / inclination limits | PASS | A rate above the DLS limit (`DLS_LIMIT`, with the leg) or an inclination above the limit anywhere on an arc (`INC_LIMIT`) is infeasible, never clipped |
| Documented objective and convergence; no optimality claim | PASS | `SOLVER_OBJECTIVE`: pass through every centre; nothing is minimised. `SOLVER_CONVERGENCE`: closed form, accepted only when the canonical minimum-curvature engine puts every centre within 0.01 m of the continuous path at the expected MD; otherwise `NOT_CONVERGED` (tested by forcing a miss and an out-of-order pass) |
| Independent goldens | PASS | Forward-constructed in the test with its own arc/tangent geometry (not the solver, not `design_plan`): three-target build/turn/drop, hold-after, S-profile to 5° with a final hold, S-profile back to vertical from an offset tie-in. Recovered to 1e-7° and 1e-6 m. One target equals the M86 solver |
| Infeasible cases | PASS | Multi: NO_TARGETS, DLS_LIMIT, INC_LIMIT (leg 2), TARGET_BEHIND, INSIDE_TURN_RADIUS (leg 2), INVALID_INPUT ×3. S: NOT_SUPPORTED, INSIDE_TURN_RADIUS, NO_DISPLACEMENT, TARGET_NOT_BELOW_KOP, INC_LIMIT, DLS_LIMIT, NO_DROP, NON_POSITIVE_RATE, INVALID_INPUT ×2. Every refusal returns no segments |
| Desktop | PASS (offscreen) | Plan designer "Solver mode": curve-hold to the first target (M86, unchanged default), through all targets, S-profile (drop rate, final inclination, final hold, max inclination; the panel's DLS limit applies). The solved segments are filled in and designed; the summary states the verified misses and "One feasible profile, not an optimum" |
| Catalogue | PASS | `directional.multi_segment_solver` (PLANNING AID, `M106 multi-target / S-profile solver v1`); the catalogue has 54 entries (53 before; the methods document said 52, now corrected) |
| Anti-collision | UNCHANGED | SCREENING — NO ISCWSA UNCERTAINTY — NOT APPROVED |
| Mutation | PASS | 12 mutants: **12/12 killed** |
| Regression | PASS | 130 tests across the solver, survey, plan, catalogue and documentation files; full suite before commit (see the M101–M120 report) |

### M107 – Every W13 calculator: a contract or an exact reason

| Criterion | Status | Evidence |
|---|---|---|
| All 27 leaves classified | PASS | `CONTRACTS` 18 + `NOT_SUPPORTED` 9 = the 27 finder leaves exactly; no overlap, nothing stale (test) |
| Semantic IDs | PASS | `w13.<area>.<name>` stable IDs, method IDs and versions; field IDs with canonical units; inputs bound by widget object name |
| New contracts (11) | PASS | Buoyancy, Balanced Plug, Kick Tolerance (+ trip margin), Pore Press & FG (Eaton, influx, dc), Stuck Pipe, Weight/Dilution/Mix, Volume Balance, Mud Lab, Fishing, Rheology, Nozzle Optimization; each adapter calls the same canonical engine as its W13 handler |
| Parity + independent goldens | PASS | Each new adapter against the on-screen value of the real handler; closed forms written in the test (free point 735294·e·W/P, Eaton, Jorden-Shirley d / Rehm-McClendon dc, MAASP, MBT, LSRYP, slug, corrosion mpy, weight-up mass balance, PV/YP/n, Q_max = HHP·1714/P) |
| Unknown ≠ 0 | PASS | Kill-sheet-style "Not recorded" (−1) is None in the adapters (as `_wc_value`); 0 = omit fields are None; a page part whose inputs are rejected is None; a page with nothing computable is rejected (UNVERSIONED case with the reason). The nozzle engine's zero fallbacks are rejected |
| Text / bool inputs | PASS | `FieldSpec.kind`: the weight-up additive (list entry) and the nozzle model (radio) are contract inputs; changing the additive gives DIFFERENT, an empty one UNREADABLE; radio buttons nested in a form row now take the row label |
| Exact NOT_SUPPORTED reasons (9) | PASS | Well Volumes (pump/pipe/casing tables), Hydraulics (page tables; runs are exported to CSV only, never stored, so not in Calc History — the M87 wording claimed otherwise and was corrected in M107), Weight (components table + T&D reads the Multi-Survey table), Casing Strength (architecture provenance not captured), Kill Sheet (TRAINING AID owner gate + geometry table), Choke Schedule (table output; no case can be saved), Multi-Survey (use Survey revisions), Anti-Collision (tables; SCREENING), DP Database (not a calculator). "not yet contracted" no longer appears |
| Persistence | PASS | Save → reopen → re-run MATCH for a text-input, a bool-input and three numeric new contracts |
| D26 weight-up | PASS | Corrected and versioned (see the defect register); golden 427.4 sacks; W15 reference row corrected |
| Catalogue | PASS | Still 54 entries (W13 entries move from NOT SUPPORTED to calculator contract); 42 IMPLEMENTED, 9 NOT SUPPORTED, 2 OWNER REVIEW REQUIRED, 1 NOT IMPLEMENTED; `violations()` empty |
| Mutation | PASS | 10 mutants: **10/10 killed** |
| Regression | PASS | 190 tests (contracts, history, catalogue, finder, mud, engineering ground truth, documentation). Full suite (offscreen, local): 4586 passed, 4 skipped (the four opt-in skips), **1 failed** — `test_engine_inventory_document_is_current` (`ENGINE_INVENTORY.md` still listed 7 `MudVolumeEngine` methods after the D26 change); regenerated with `engine_inventory.py --write`, then the inventory, M107, M87, exception-scan, release-boundary, documentation-truth and engineering-ground-truth files re-run green. +28 collected vs M106 = 17 new M107 tests + 11 M87 parametrised cases (`test_m87` parametrises over `CONTRACTS`, 7 → 18). The Hydraulics-reason guard (18th M107 test) was added after that run |
| Inherited wording corrected | PASS | The M87 Hydraulics reason said saved hydraulics runs are verified in Calc History; no hydraulics table exists and `_hy_export` only writes a CSV. The reason now says runs are exported to CSV only and never stored; a test guards both the text and the absence of a hydraulics table |

### M108 – Calculation history: every source, versions, re-run, full-field compare

| Criterion | Status | Evidence |
|---|---|---|
| Every calculation source in History | PASS | `calculation_history.COVERAGE`: 11 sources (6 engine snapshot tables, trajectory, calculation cases, directional plans, survey revisions, architecture revisions). A guard test lists every mapped table whose name looks like calculation storage; each is covered or in `NOT_CALCULATIONS` with a reason (`report_revisions` = DDR document history, `calculation_source_links` = lineage links). Hydraulics is not a source: its runs are exported to CSV only and never stored (stated in the W13 NOT_SUPPORTED reason) |
| Method/version on new trajectory records (D14) | PASS | Additive column `trajectory_calculations.method_version` (VARCHAR(120), `ADDITIVE_COLUMNS`); `save_comparison` writes `METHOD_VERSION`; History reads the column. Legacy rows keep NULL and are shown "unversioned (legacy)" — never given the current method (mutant on the `method` fallback killed) |
| Re-run of a stored comparison | PASS | Records carry `record_schema` 2, every input station (actual / plan / offset rows) and `inputs_sha256`. `verify_record`: NOT_REPRODUCIBLE (legacy; other version; rows missing — each with its exact reason), UNREADABLE when the inputs hash fails (never recomputed), else re-run and compare every stored field (numbers ±1e-6 m, text exact, row counts, target checks) → MATCH / DIFFERENT with field ids. The worker body and target checks moved from the panel to `core.trajectory_compare.run_comparison` so desktop and History run the same code |
| Insert-only trajectory saves (D27) | PASS | `DatabaseManager.save_trajectory_calculation` no longer updates a record with the same report or well+date; every call inserts a new row; `method_version` only when the caller supplies it |
| Full-field, unit-aware compare | PASS | `full_field_compare`: every input and result leaf (nested values flattened; `{value, unit}` entries kept whole) with SAME / DIFFERENT (delta, relative) / CHANGED / ONLY A / ONLY B / UNIT MISMATCH. Units from the stored entry or the key suffix (`hook_load_lbs` → lbf), shown with their source; a mismatch is never converted silently — within one quantity the converted value is offered as `b_in_unit_a` (`UnitManager.convert`); across quantities nothing is offered. Shown in the Calc History compare and in the comparison report HTML |
| Coverage register | PASS | `coverage(db)` per source: table, in history, which records carry a method version, recalculation path, compare, record and reproducible counts. Table below |
| Mutation | PASS | 16 mutants (re-run guards, version column and migration, desktop save, history adapters, unit mismatch, one-sided fields): **16/16 killed** |
| Regression | PASS | 21 files touching trajectory compare, history, the trajectory table or the additive columns (309 tests) green; full suite (offscreen, local): **4599 passed, 4 skipped** (the four opt-in skips), 0 failed, EXIT 0 — +12 vs M107 = 11 M108 tests + the M107 Hydraulics-reason guard |

| Source | Table | Method version | Recalculation | Compare |
|---|---|---|---|---|
| Torque & drag, Casing design, Cement volumes, MSE, Mud volume | engine snapshot tables | every record (engine method + snapshot schema) | engine snapshot re-run | full-field |
| Kill sheet | `well_control_kill_sheet_calculations` | every record | engine snapshot re-run (TRAINING AID) | full-field |
| Trajectory | `trajectory_calculations` | records from M108 on; earlier rows "unversioned (legacy)" | re-run of the stored stations; legacy NOT REPRODUCIBLE | full-field |
| Calculation case | `calculation_cases` | every case (W13_UNVERSIONED before M73) | contract re-run (18 W13 calculators); the 9 NOT_SUPPORTED NOT REPRODUCIBLE | full-field |
| Directional plan | `directional_plan_revisions` | every revision | plan re-design + result hash | full-field |
| Survey revision | `survey_revisions` | every revision | minimum curvature after the SHA-256 check | full-field |
| Well architecture | `well_architecture_revisions` | every revision (schema version) | validator after the SHA-256 check | full-field |

### M109 – Cement worksheet contract and re-run

| Criterion | Status | Evidence |
|---|---|---|
| Contract | PASS | `well_architecture.CEMENT_CONTRACT`: id `architecture.cement_annulus`, method `m89.cement_annulus`, version "M89 cement annulus worksheet v1" (unchanged: the method did not change), 7 named inputs with units, result ids (`total_bbl`, `base_total_bbl`, `interval_<n>`, `interval_<n>_excess`, bbl), source = the frozen architecture revision, and what is never inferred |
| One builder for save and re-run | PASS | `cement_case_payload(work)`; the W3b architecture panel saves through it (test: saved case = builder output) |
| Re-run adapter | PASS | `verify_cement_case`: NOT_REPRODUCIBLE (other version; revision id, hash or string not recorded; no database), UNREADABLE (revision missing, revision fails its SHA-256 check, or the revision's components differ from the hash the case recorded — never recomputed), else MATCH / DIFFERENT over every stored field (volume ±1e-9 bbl, interval description exact, fields on one side only). History passes its database (`recalculate_entry(entry, db=...)`) |
| New linked case | PASS | `save_cement_rerun` (History "Save recalculation" for a worksheet): a NEW full worksheet case (same calculator, method, version, inputs; fresh results), note "WORKSHEET — NOT A CEMENT DESIGN APPROVAL — …; re-run of case #N: MATCH/DIFFERENT", link `rerun_of` with the verification status; the original is never written; an UNREADABLE re-run cannot be stored. The new case is itself re-runnable and keeps the "uses architecture revision" lineage through its inputs |
| Label | PASS | "WORKSHEET — NOT A CEMENT DESIGN APPROVAL" on the panel status, the saved note, History scope (architecture worksheet and W13 Cement Volume cases), the W13 Cement Volume contract limits and the catalogue entry |
| Nothing inferred | PASS | No yield, sacks, slurry density or thickening time in the worksheet; casing yield stays `unknown` for a P110 string (never from the grade); W13 Cement Volume takes yield as an entered input |
| Mutation | PASS | 13 mutants (version, inputs, hash, value/label/one-sided differences, unreadable store, lineage, History adapters and scope, desktop database hand-over): **13/13 killed** |
| Earlier assertions changed | PASS | `test_m89` (W3b worksheet) and `test_m78` (workflow C) asserted the worksheet was NOT REPRODUCIBLE (captured only); both now assert REPRODUCIBLE, and M78 also re-runs to MATCH. The behaviour change is the M109 deliverable, not a weakened check |
| Regression | PASS (with one flaky failure, D28) | Full suite (offscreen, Linux, before the M109 commit): 4611 collected — 4606 passed, 1 failed, 4 skipped (the four opt-in skips), 0 errors. The failure is `test_m49_knowledge_ui.py::test_generation_never_blocks_the_ui_and_cancel_works` (a 10 s wait for a released worker under full-suite load); M109 does not touch the knowledge assistant, and the file passed 23/23 three times in isolation (7.8–7.9 s). Recorded as D28, not counted as a pass |

### M110 – Professional export: revision, approval wording, provenance, Mud Chemicals

| Criterion | Status | Evidence |
|---|---|---|
| No hard-coded "Rev 0" | PASS | `report_revision_label`: "Report revision {n} ({status}, {time})" from the latest `report_revisions` row of the exported report; "No report revision recorded" when there is none; whole-well exports: "Whole-well export — M110 professional export template v1 (no single report revision)". `ExportCoordinator.get_export_metadata` (dead code; no callers) delegates to the same builder, so its "Rev 0" and "Validated" are gone too |
| "Approved By" is not an approval | PASS | `DailyReport` has no prepared/checked/approved-by columns, so those names show "not recorded (the daily report has no such field)"; the PDF table is titled "Names as recorded — not an approval" and the signature lines are removed. The `approval_actions` "approve" record of the same report is shown separately: "Workflow status … set by … on … (workflow status only — not a signature, not a release approval)", else "No approval recorded in DrillMaster". Signature status: UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED |
| Workbook ↔ M93 provenance | PASS | New provenance kinds `workbook` (whole well) and `workbook_report` (one report): a "Provenance" sheet first in the workbook (scope, sources incl. `report_revisions`/`approval_actions`, revision, label, direction); the PDF carries the M93 banner and provenance block with `dir` |
| Honest sheet count | PASS | The workbook has the 16 core sheets plus Mud Chemicals and the report sections; W11 says "16 core sheets + report sections". The file stem `Professional_16Sheets_…` is kept for compatibility (pinned by `test_export_worker`) |
| Mud Chemicals | PASS | Always present. Chemicals come only from `mud_reports.chemicals_json`; every row carries `mud_report_id`, `report_id`, `mud_report_date`. A report without mud says "No mud report in scope"; a whole-well export says it lists the latest mud report only |
| Per-report workbooks in batches | PASS | `plan_batch(professional_per_report=True)` adds one workbook per selected daily report (`Professional_16Sheets_{num}_{date}_{ts}.xlsx`, report-scoped provenance); off by default, so historical names and order are unchanged; W11 checkbox "Professional workbook per report" |
| Format parity | PASS | Professional export: Excel and PDF in LTR and RTL (direction propagates from W11 batch jobs; RTL sheets right-to-left). There is no professional HTML/CSV variant; HTML/PDF/Excel/CSV parity for the report engines is M93 |
| Escaping | PASS | PDF metadata strings and the report summary are HTML-escaped (`<i>`, `<b>`, `&` in well name and summary shown literally) |
| No PyMuPDF for generation | PASS | `core/professional_export.py` imports neither `fitz` nor `pymupdf` (AST test); PDF via Qt `QTextDocument` |
| D29 | PASS | The professional PDF export never worked before M110 (see register); fixed and covered |
| Mutation | PASS | 16 mutants (revision, missing revision, latest revision, approval of another report, approval wording, blank names, provenance sheet and PDF block, escaping ×2, chemicals source and empty state, workbook scope, batch direction, per-report jobs, D29): **16/16 killed**; one survivor in the first run (`PE-pdf-metadata-unescaped`) was killed by adding a well name with markup to the test, not by weakening the mutant |
| Regression | PASS | Export, provenance, release e2e/smoke, REST, W11 and selection files (139 tests) green; full suite (offscreen, Python 3.11, Linux): 4622 collected, 4618 passed, 4 skipped (the four opt-in skips; not passes), 0 failed, 1560.6 s - the D28 m49 flake did not recur in this run |

### M111 – DDR parsing in an isolated spawn process (D12)

| Criterion | Status | Evidence |
|---|---|---|
| Parse in a separate process | PASS | `core/isolated_parse.py` (`ISOLATION_VERSION = 1`, mode "spawn process"): `prepare_isolated` starts a `spawn` child that runs `prepare_import`; the dialog uses it when every parser is the production one (`_parsers_can_be_isolated`); `parse_timeout` (default 600 s) and `isolate_parsing` are class settings |
| DTOs only, persistence in the parent | PASS | `is_plain` checks the request and the result (scalars incl. date/time/timedelta/Decimal, lists, tuples, sets, dicts); profiles cross as dictionaries; only a failed MinerU result is sent (its error text). The child never opens the database; preview, decision and save stay in the dialog |
| Identity | PASS | SHA-256 fingerprint in the parent before start, in the child before and after parsing, and in the parent after the result; any change → `IDENTITY_CHANGED`, nothing saved |
| Cancel never commits | PASS | The cancel event is honoured between steps; the parent stops waiting at once and discards a late result; the dialog test cancels during an isolated parse and nothing is persisted |
| Bounded shutdown, no orphans | PASS | join → terminate → join → kill → join; every child is a daemon and registered for `shutdown_all` (atexit); tests check the PID is gone (a child that ignores SIGTERM is killed) |
| Failure states | PASS | OK / CANCELLED / TIMEOUT / CRASHED / IDENTITY_CHANGED / NOT_PLAIN; every failure raises `IsolatedParseError("…; nothing was saved")`; original error types (ValueError, MinerU errors, ImportCancelled) are rebuilt by name, so stage/status mapping is unchanged |
| Real data (found while integrating) | PASS | The first integration run rejected `synthetic_ddr_golden_a.xlsx` as NOT_PLAIN: time-log durations arrive from openpyxl as `datetime.timedelta`. `timedelta` is a plain value type and is now allowed; every repository workbook fixture is parsed in the child and compared field by field with the in-process result |
| Scope (honest) | stated | Callables injected into the dialog (tests, plugins) and a successful MinerU result keep the M71 worker thread (a callable cannot cross a process). No OCR added. `multiprocessing.freeze_support()` in `app.py`/`run.py`; the test is in the Windows release gate (`REQUIRED_MODULES`), but Windows desktop acceptance of the spawn path remains an owner gate |
| Measured | recorded | Linux offscreen, `normal_ddr.xlsx`: in-process median 0.042 s, isolated median 0.268 s (spawn overhead ≈ 0.23 s per file, 3 runs). Windows spawn cost not measured here |
| Mutation | PASS | 16 mutants (identity before/after/parent, late result after cancel, timeout, no terminate, no kill, non-plain result, error type, unregistered child, request check, MinerU success isolated, injected extract/route isolated, isolation never used, timedelta rejected): **16/16 killed** |
| Regression | PASS | Import dialog, reentrancy, M52 split, M71 background, import architecture, Windows gate contract, release e2e, batch isolation, repairs, p0 import, golden/OEOC, preview bulk decisions, M54/M61/M84 import files green; full suite (offscreen, Python 3.11, Linux): 4645 collected (4622 + 23 M111), 4639 passed, 4 skipped (the four opt-in skips; not passes), 2 failed, 1612 s. The two failures were `test_release_boundary_imports` (closure tracked, wheel from tracked population): `core/isolated_parse.py` was not yet in the git index, which is exactly what that gate guards; with the new files in the index both pass (re-run with the M111 file) |
| Mutation hygiene (found in the mutation run) | fixed | Under `IP-no-kill`/`IP-no-terminate` the SIGTERM-ignoring test child (`hang_ignoring_terminate`) and its resource tracker stayed alive after the run (PPID 1); they were killed by hand. The test helper `_gone` now reaps the child in `finally` (SIGKILL, test hygiene only, after the assertions), so a mutant still fails the test but leaves no orphan; both mutants re-run: killed, no process left |

### M112 – Dependency and licence audit, catalogue evidence, owner packs (D13, D30)

| Criterion | Status | Evidence |
|---|---|---|
| Pinned dependencies | PASS (disclosure) | 26 pins in `requirements-lock.txt`, each with installed version, licence text from the installed metadata and a class. 22 permissive; PyMuPDF 1.24.14 (AGPL-3.0) and PySide6 / shiboken6 6.8.1.1 (LGPL-3.0) are marked as owner gates. Nothing is removed or replaced |
| Third-party imports | PASS | 160 import sites in product code. Each one is declared, or it is an optional import guarded by `try/except ImportError` and mapped to its gate: OCR/PDF tables, ISCWSA/welleng, LGPL engines, MinerU. 0 findings. Optional-package licences come from PyPI metadata read on 2026-11-03; nothing was installed |
| Forbidden bindings | PASS | No PyQt5/PyQt6 import anywhere in the product (test). This audit found D30 (a PyQt5 import in W13), which is now fixed |
| LGPL adapter | PASS | `TorqueDragAdapter.calculate` imports `torque_drag` inside `try/except ImportError` and returns `None` without it (test, mutant `TDA-unguarded-import`) |
| Catalogue evidence per method | recorded | 54 catalogue entries (was 52 before M107 added two), 0 approved. Statuses: 42 IMPLEMENTED, 9 NOT SUPPORTED, 2 OWNER REVIEW REQUIRED, 1 NOT IMPLEMENTED. For each method the JSON lists every test file that names the method id or its module. Counts: min 0, median 7, max 60. The only entry with 0 is `tnd.stiff_string` (NOT IMPLEMENTED). `thermal.wellbore_temperature` and `wellpath.iscwsa_error_model` have 1 each, both owner-gated. **These counts measure references, not assertions**; M119 checks what tests actually assert |
| Owner decision packs | PASS (packs only) | `docs/engineering/M112_OWNER_DECISION_PACKS.md`: ISCWSA/welleng, pwptemp, torque_drag, PyMuPDF, OCR (RapidOCR, Tesseract, camelot, onnxruntime, MinerU, torch), kill sheet, cost/currency, hydraulics and method approvals, 7.48 vs 7.48052, datum/CRS, Qt for Python LGPL distribution, qtribbon. Each pack states the facts, the options and what the code does until the owner decides. **There is no approval UI and nothing is approved** (test) |
| Mutation | PASS | 7 mutants (unguarded import seen as guarded, forbidden binding ignored, undeclared import ignored, AGPL as permissive, LGPL as permissive, D30 restored, unguarded LGPL import): **7/7 killed** |
| Regression | PASS | W13, drill-pipe import, catalogue, torque/drag and release-boundary files (58 files) green. Full suite (offscreen, Python 3.11, Linux, run in parallel with the M118 mutation run): 4654 collected (4645 + 9 M112), 4649 passed, 4 skipped (the four opt-in skips; not passes), 1 failed, 1622 s. The failure was real: the new `except ImportError: return None` in the torque/drag adapter raised the unexplained-silent-handler count above the ceiling (core 82 > 81). The handler is now annotated `# silent-ok:` with its reason, and the ceiling is unchanged. `test_exception_scan` and the M112 tests pass, and the re-anchored mutant is still killed |

### M113 – Unit-conversion constant inventory and versioning strategy

| Criterion | Status | Evidence |
|---|---|---|
| Inventory | PASS | `tools/quality/constant_inventory.py` → `docs/engineering/constant_inventory.json`. It covers 13 quantities and counts **NUMBER tokens only** (Python tokenizer; comments and strings excluded; `7.480` is treated as `7.48`) in `core`, `tabs` and `dialogs`; top-level modules such as `main_window.py` are not scanned. Quantities: pcf/ppg, ft³/bbl, gal/bbl, psi/ft per ppg and per pcf, ft/m, the 1029.4 capacity constant, mm/in, the 30.48 DLS conversion, °F/°C, psi/bar/kPa, lb/kg and fresh-water density. Cost per length, DLS unit and temperature unit are reported as conventions (both units in use) |
| Inconsistencies | recorded, not changed | **pcf per ppg**: 7.48052 (10 uses), 7.48 (11), 7.4805 (1); max relative difference 6.95 × 10⁻⁵. **ft³ per bbl**: 5.6146 (`core/engineering/engines/cement.py`) vs 5.615 (`tabs/w3c_section_data.py`). The 7.48 vs 7.48052 choice is an owner pack (M112) |
| Versioning strategy | documented | `docs/engineering/M113_CONSTANT_INVENTORY.md`: a constant changes only through a new method version. Records saved under the old version keep it, and the current constant is never assigned to them. No global search-and-replace. **No value was changed in M113** |
| Currency | PASS | The test fails when the committed JSON differs from a fresh scan |
| Mutation | PASS | 3 mutants (raw text scan instead of tokens, trailing-zero variant missed, inconsistency hidden): **3/3 killed**. The first draft had a mutant that added STRING/COMMENT tokens. It survived because it is provably equivalent: such a token always starts with a quote, a string prefix or `#`, while every catalogued literal starts with a digit, and `_canon` only strips `_` and lowercases, so it can never match. It was replaced by the stronger raw-text-scan mutant (killed); it was not declared equivalent |
| Regression | PASS | Full suite (offscreen, Python 3.11, Linux): 4658 collected (4654 + 4 M113), 4654 passed, 4 skipped (the four opt-in skips; not passes), 0 failed, 1734 s. *Environment note:* the sandbox was reset before this run. The venv was rebuilt from `requirements-lock.txt` plus the CI tool pins (pytest 9.1.1, ruff 0.16.6, build 1.6.1, coverage 7.16.2). The offscreen Qt system libraries were rebuilt from source: libglvnd 1.7.0 (EGL/OpenGL, no X11), libxkbcommon 1.7.0, dbus 1.14.10, expat 2.6.4. `libGL.so.1` is a stub whose GLX entry points return 0, because GLX is never used offscreen. This affects only the local test host, not the product or CI |

### M114 – Document intelligence: scope, citations, manual links, offline (D31)

| Criterion | Status | Evidence |
|---|---|---|
| Association is manual | PASS (existing, re-tested) | Links are created only by a user action (`DocumentLinkService.create_link`, audited). `suggest_wells` only proposes and changes no link count (test); every proposal cites a page and location |
| No cross-well leak | PASS (D31 fixed) | Well-scoped view: a search returns only documents linked to the selected well. Switching to `SYN-TWIN` (project East) shows only its document. The same-name `SYN-TWIN` in project West, which has no links, shows nothing. No well selected: no hits and "Select a well…" (widget tests) |
| Limit after the scope | PASS | FTS5 and the substring-scan fallback both apply the scope before the limit: with `limit=1`, a scoped search still returns the in-scope document that is not the library's top hit |
| List and search agree | PASS | One shared filter (`_filter_documents`); "unlinked" / "linked" searches return exactly the listed documents, and the info line names the scope |
| Page citations | PASS | Every hit carries file name, page number and location; the page opens at the cited page (existing M45 tests) |
| Delete / re-index | PASS | A deleted document disappears from the whole-library search, from a scoped search and, via the re-run, from the tab's open result list. Its links are gone, and a rebuilt index does not bring it back |
| Offline | PASS | Search runs with `socket.create_connection` and `socket.connect` patched to fail (in-memory SQLite FTS5, no network) |
| Honest "no text layer" | PASS | A PDF page without text is extracted empty (no OCR); a search without hits states that pages without a text layer or unapproved OCR are not indexed |
| Guard compatibility | PASS | The first draft restricted FTS through a TEMP table. `test_no_unreviewed_raw_sql_writer_bypasses_the_orm_guard` flagged it as a raw SQL writer, so it was replaced by a read-only `json_each(?)` parameter (SQLite JSON1, built in since 3.38; 3.40.1 here). The guard allow-list is unchanged |
| Mutation | PASS | 7 M114 mutants (scope ignored, empty scope = all, limit before scope, scan unscoped, tab search unscoped, stale hits kept, no-well guard): **7/7 killed**. The M102 mutant `DOC-selected-well-filter-unfiltered` was re-anchored to the moved filter with the same mutation and is still killed |
| Regression | PASS | Full suite (offscreen, Python 3.11, Linux): 4668 collected (4658 + 10 M114), 4664 passed, 4 skipped (the four opt-in skips; not passes), 0 failed, 1539 s |
