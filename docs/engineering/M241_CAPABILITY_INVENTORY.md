# M241 – Capability inventory (M231–M260)

**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.** Written against code tree `5ff4d09`, then corrected after the M239 extension; the final code SHA is recorded in the
M231–M260 report.
All evidence is synthetic (SYNTHETIC fixtures, offscreen Qt on Linux, GitHub-hosted Linux and Windows runners). No real
DDR or confidential document was opened. Real-document acceptance (`tests/test_ddr_acceptance.py`), real MinerU
(`tests/test_mineru_real_integration.py`) and the Windows bundle smoke (`tests/test_packaging_smoke.py:221`) are opt-in
skips and are never counted as passes.

## Status vocabulary (11 values, used consistently)

| Code | Status | Meaning |
|---|---|---|
| Q | IMPLEMENTED AND QUALIFIED (SYNTHETIC) | engine + persistence + integrated UI; tests on the final tree; covered by a complete mutation catalogue; synthetic data only |
| PQ | IMPLEMENTED — PARTIALLY QUALIFIED | works and is tested, but a named qualification element is missing |
| NUI | IMPLEMENTED — NOT UI-INTEGRATED | module exists, not reachable from the desktop UI (not complete by rule) |
| LS | IMPLEMENTED — LIMITED SCOPE | deliberately narrow; limits documented |
| OD | OWNER DECISION REQUIRED | blocked on a P1–P19 package |
| LD | LICENSED / REFERENCE DATA REQUIRED | needs data the project may not ship (API tables etc.) |
| IV | INDEPENDENT VALIDATION REQUIRED | method needs a second, independent reference before engineering use |
| WF | WINDOWS / FIELD ACCEPTANCE REQUIRED | needs the owner's Windows desktop or field run (P17) |
| B | BLOCKED | cannot proceed without an external change |
| NI | NOT IMPLEMENTED | — |
| DR | DEPRECATED / READ-ONLY | kept for old data only |

A capability can carry several codes; the first is the headline.

## Inventory

Fields: entry point (UI / module) · inputs and units · method / version · evidence on the final tree · status ·
limitations and gates.

| # | Area / capability | Entry point | Inputs, units | Method, version | Evidence | Status | Limitations, gates |
|---|---|---|---|---|---|---|---|
| 1 | Well hierarchy, selection context (company → project → well → wellbore → section → report) | `main_window.py`, `core/selection_manager.py` | ids; no units | M83/M102 context contract | `test_m70_selection_audit`, `test_m83_selection_lifecycle`, `test_m102_context_probes`; m70_m76, m101_m120 | Q · WF | one main window per process; M234 fixed the Export follower lambda |
| 2 | DDR daily workspace (W2/W3: time log, drilling parameters, mud, BOP, waste, logistics) | `tabs/w2_Daily_Report.py`, `tabs/w3_drilling_report.py`, `tabs/w7_logistics_Widget.py` | API field units (ft, ppg, gpm, psi); missing = None | M54/M84; carry-forward M217 | `test_m169_end_to_end_journey`, `test_m217_day_by_day_carry_forward`, `test_m229_w7_unknown_movements`; m201_m230 | PQ · WF | M242 audit (this mission) is a review of existing evidence only; real-DDR acceptance NOT RUN |
| 3 | DDR import (Excel/PDF) with lineage source → parsed → normalized → correction → accepted | `core/ddr_import_service.py`, `core/ddr_import_pipeline.py`, `dialogs/excel_import_dialog.py`, isolated spawn parser (M111) | workbook cells; units from headers | M61/M84/M111/M213/M214/M215/M218 | `test_m213_excel_limits`, `test_m214_header_mapping`, `test_m215_scalar_correction_adversarial`, `test_m218_ddr_revision_lineage`, `test_m147_m152_ddr_continuation`; m201_m230, m231_m260 (review queue) | PQ · WF | only synthetic workbooks; real DDR acceptance NOT RUN; PDF OCR is owner-gated (P4/P5) |
| 4 | DDR review queue, continuation rows | `core/import_review_queue.py`, `core/ddr_continuation.py` | — | M150 | `test_m147_m152_ddr_continuation`, `test_m239_review_queue_and_mse_summary`; m231_m260 12/12 | Q | M239 added the tests for 4 review-queue survivors |
| 5 | Data-quality workspace | `core/data_quality_workspace.py`, `dialogs/data_quality_dialog.py` | — | M227 | `test_m227_data_quality_workspace`; m201_m230 | Q | — |
| 6 | Well architecture, schematic | `tabs/w3b_wellbore_schematic_tab.py`, `tabs/well_architecture_panel.py`, `core/schematic_document.py` | in, ft | M57/M65/M205 | `test_m205_m207_schematic_provenance`; m201_m230 | PQ · IV | schematic is a drawing aid, not an engineering verification |
| 7 | Directional: surveys, integrity, datum, revisions | `tabs/w6_Trajectory_Widget.py`, `tabs/survey_revision_panel.py` | MD/inc/azi (ft or m, deg) | minimum curvature; M85/M105 | `test_m105_survey_integrity`, `test_m132_trajectory_layers`; m101_m120 | Q · IV · OD | datum/CRS owner gate P10; ISCWSA error models not implemented (P19) |
| 8 | Directional plan designer, multi-segment solver, anti-collision screening | `tabs/well_plan_designer_panel.py`, `core/engineering/engines/anti_collision.py` | ft/m, deg, deg/100 ft | M86/M106 | `test_m106_*`, m101_m120 | PQ · IV | separation-factor screening without error ellipses (no ISCWSA) |
| 9 | 2D / 3D trajectory views, layers, saved views, compare | `tabs/trajectory_viewer.py`, `tabs/trajectory_3d_view.py`, `tabs/trajectory_layers_panel.py` | — | M132/M178 | `test_m132_trajectory_layers`, `test_trajectory_3d`; m50 | Q | D51 (one CI hang in this file) OPEN, not reproduced in 12 bounded runs |
| 10 | Hydraulics (W13: pressure loss, ECD, TFA, nozzles) | `tabs/w13_Engineering_Calculator.py` | ppg, gpm, in, psi | W13 contracts M87/M107 | `test_m87_w13_contracts`, `test_m125_w13_classification`; m83_m96, m121_m140 | PQ · IV | M245 audit not performed in this mission; methods have contract status, not independent validation |
| 11 | Casing design (burst/collapse/tension, VME) | `core/engineering/engines/casing.py`, `core/engineering/casing_persistence.py` | psi, lbf, in, ppf | M57/M89; VME; method id `transition F r3` | `test_casing_vme_independent`, `test_m239_engine_semantics`; m231_m260 (`CAS-*`, the first catalogue to mutate this engine) | PQ · LD · IV | **D77 fixed in M239** (transition regime was never used); no shipped tubular ratings (P18); yield never inferred from grade |
| 12 | Cement (volumes, worksheet contract, re-run) | `core/engineering/engines/cement.py`, `core/engineering/cement_persistence.py` | bbl, ft³, ppg | M109 | cement tests; m52 (cement engine and persistence) | PQ · IV | — |
| 13 | Torque and drag | `core/engineering/engines/torque_drag.py`, `core/engineering/torque_drag_persistence.py` | lbf, ft·lbf, friction factor | soft-string; version recorded | `test_torque_drag_*`, `test_m239_engine_semantics`; m121_m140 (persistence only), m231_m260 (`TD-*`, engine) | PQ · IV | pwptemp / torque_drag (LGPL) not adopted (P3) |
| 14 | MSE, bit performance, BHA | `core/engineering/engines/mse.py`, `core/engineering/mse_persistence.py`, `tabs/bit_run_panel.py` | lbf, rpm, ft·lbf, ft/h, in | Teale; snapshot schema v1 | `test_mse_persistence`, `test_mse_save_widget_smoke`, `test_m239_review_queue_and_mse_summary`; m231_m260 | Q · IV | M239 found and closed an unknown-as-zero gap in the stored summary |
| 15 | Well control, kill sheet | `core/engineering/well_control_kill_sheet.py` | psi, ppg, bbl, stk | M177 | `test_well_control_kill_sheet*`, `test_kill_sheet_casing_id_gate`, `test_m239_engine_semantics`; m231_m260 (`KS-*`, the first catalogue to mutate it) | PQ · OD · IV | P11 Kill Sheet owner gate |
| 16 | Mud volume, mud engineering | `core/engineering/engines/mud_volume.py`, `tabs/mud_engineering_panel.py` | bbl, ppg | — | `test_mud_volume_*`; m101_m120 (one engine mutant); persistence not mutated | PQ · OD | **7.48 vs 7.48052 owner gate (P8) kept**; no global replacement |
| 17 | W13 classifications (each calculator: contract, not-supported reason) | `tabs/w13_Engineering_Calculator.py` | — | M107/M125 | `test_m125_w13_classification`, `test_m87_w13_contracts` | Q | M249 audit: existing evidence only |
| 18 | KPIs and executive dashboard | `tabs/home_tab.py`, `tabs/dashboard_widgets.py`, `core/operational_analysis*` | per KPI definition | M53/M104 KPI register | `test_m53_dashboard`; m53_m56, m101_m120 | Q | every KPI carries definition, unit, source, as-of (M250: existing evidence) |
| 19 | Operational analysis, NPT, parameter trends | `tabs/operational_analysis_panel.py`, `tabs/npt_reconciliation_panel.py`, `tabs/w12_Analysis.py` | — | M91/M104 | `test_m48_analysis_evidence`, m48, m101_m120 | Q | — |
| 20 | Calculation history / workbench (MATCH / DIFFERENT / NOT_REPRODUCIBLE / UNREADABLE) | `tabs/calculation_history_tab.py`, `core/engineering/calculation_verification.py` | — | M88/M108 | m101_m120 (`CH-*`, `TC-*`) | Q | M251: existing evidence only |
| 21 | Reports and export (Report Center, professional workbook/PDF, provenance) | `tabs/w11_Export.py`, `core/report_provenance.py` | — | M110 | m101_m120 (`PE-*`, `RP-*`); D76 timestamp handling | PQ | timestamped outputs are never claimed byte-identical (D76) |
| 22 | End-of-well package | `tabs/well_package_panel.py`, `core/well_package.py` | — | M135 | `test_d59_stale_partial`; m121_m140 | Q | — |
| 23 | Offline document intelligence, Knowledge Assistant | `tabs/documents_tab.py`, `tabs/knowledge_assistant.py`, `core/knowledge_*` | — | keyword retrieval; M49–M52 | `test_m49_knowledge_ui`, `test_m50_*`, `test_m52_sentence_support`; m49–m52 | LS · OD | no model weights shipped (P7); OCR / MinerU owner-gated (P4/P5); m50 keeps 3 survivors killed in m52 |
| 24 | UI integration, RTL + English | all tabs | — | M115/M95 | `test_m95_ux_responsiveness`, `test_m94_e2e_journeys` | PQ · WF | measured offscreen only; Windows desktop acceptance P17 |
| 25 | Units and semantics | `core/unit_manager.py`, constant inventory | — | M113 constant inventory | `tools/quality/constant_inventory.py` gate | PQ · OD | P8 (7.48) open |
| 26 | Security: authorization, audit, session lock, privacy gate | `core/authorization.py`, `core/session_lock.py`, `tools/privacy/privacy_check.py` | — | M121–M140 SEC | m121_m140 (`SEC-*`, 1 justified equivalent) | PQ · OD | encryption at rest, ACL, signing: P13/P14/P16 |
| 27 | Migrations, backup / restore, recovery | `core/db_maintenance.py`, `core/storage_guards.py` | — | additive migrations; M204 | `test_m204_restore_migration_cascade`; m201_m230 | Q · WF | — |
| 28 | Tubular reference catalogue import | `core/engineering/tubular_import.py`, `core/engineering/tubular_reference.py` | in, ppf | M181/M220 | `test_m181_m183_tubular_import`, `test_m220_tubular_import_hardening`; m201_m230 | LS · LD | user-supplied data only; no shipped dataset (P18) |
| 29 | Planning, procedures, cost, safety, services, equipment | `tabs/w10_Planning_Widget.py`, `w14`, `w16`, `w8`, `w9`, `w5` | — | — | per-tab tests; journeys | PQ | not re-audited in this mission; currency owner gate P9 |
| 30 | Windows installer (PyInstaller + Inno), UNSIGNED | `.github/workflows/windows-release-gate.yml` | — | — | CI windows-release on each pushed SHA | PQ · OD · WF | unsigned (P16); field acceptance P17 |

## Phases of this mission that this inventory does not upgrade

M242–M256 asked for product audits and completion work per area. In this mission they were carried out only as a
review of the evidence that exists on the final tree (the "Evidence" column); no area was re-implemented, and no
status above is higher than that evidence supports. See the M231–M260 report, phase register.

## Mutation reach (found while writing this inventory)

A path search of all 17 catalogues showed that the casing engine, the torque-and-drag engine and the kill sheet were
mutated by none of them, so their rows could not cite mutation evidence. M239 extended `mutation_m231_m260` with 9
mutants for them; 7 survived the existing tests at first, and the tests written for them exposed D77. Still not
mutated by any catalogue: `core/engineering/engines/anti_collision.py`, `bit_performance.py`, `fishing.py`,
`trajectory.py`, `well_control.py` (the kill sheet calls it), `mud_volume_persistence.py`, `casing_persistence.py`.
These are listed in the roadmap (report section C) as near-term qualification work.

## M290 catalogue (36 areas) – M261–M290 update

Written against the M261–M290 final code. It supersedes the 30-row table above for **state**; the rows above
stay as the M241 record.

**State vocabulary** (exactly as the M261–M290 mission defines it):
* IMPLEMENTED AND QUALIFIED — SYNTHETIC
* IMPLEMENTED — PARTIALLY QUALIFIED
* IMPLEMENTED — NOT UI-INTEGRATED
* ENGINE ONLY
* UI ONLY
* DOCUMENTED ONLY
* BLOCKED BY OWNER DECISION
* BLOCKED BY LICENSE OR DATA RIGHTS
* NOT IMPLEMENTED
* DEPRECATED
* READ-ONLY

"Fully implemented" needs all 15 points, including a UI entry, persistence, provenance, real-workflow tests and mutation coverage. **No area meets point 15 (real-world/field acceptance)**, so "QUALIFIED — SYNTHETIC" is the highest state used.

**Fields per area:**
* entry point (UI / module)
* inputs and units
* method and version
* persistence
* provenance
* tests on the final tree
* mutation catalogue(s)
* state
* limitations and owner gates

| # | Area | Entry point | Inputs, units | Method, version | Persistence | Provenance | Tests | Mutation | State | Limitations, gates |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Well hierarchy and selection context | `main_window.py`, `core/selection_manager.py` | ids | M83/M102 context contract; M265 window-owned routes | DB | context path on results | `test_m70`, `test_m83`, `test_m102`, `test_m265` | m70_m76, m101_m120, LC-* | IMPLEMENTED AND QUALIFIED — SYNTHETIC | P17 desktop acceptance |
| 2 | Window lifecycle (close, reopen, routes, status bar) | `main_window.closeEvent`, `core/qt_lifetime.py` | – | M265 | – | – | `test_m265_window_routes`, `test_d74_*` | LC-* (M268) | IMPLEMENTED — PARTIALLY QUALIFIED | closed windows retained by design (D74 cause 1, D63) |
| 3 | DDR daily workspace | `tabs/w2_Daily_Report.py`, `tabs/w3_drilling_report.py` | API field units; missing = None | M54/M84; carry-forward M217 (confirmation only) | DB | report lineage | `test_m169`, `test_m217_*` | m54, m201_m230 | IMPLEMENTED AND QUALIFIED — SYNTHETIC | real DDR NOT RUN |
| 4 | DDR import and lineage | `core/ddr_import_service.py`, `dialogs/excel_import_dialog.py` | workbook cells | M61/M111/M213–M218 | DB | source → parsed → normalized → correction → accepted | `test_m213_*` … `test_m218_*` | m61_m67, m201_m230 | IMPLEMENTED AND QUALIFIED — SYNTHETIC | real DDR acceptance NOT RUN |
| 5 | Review queue, continuation rows | `core/import_review_queue.py` | – | M150 | DB | parent links | `test_m147_m152_*`, `test_m239_*` | m231_m260 | IMPLEMENTED AND QUALIFIED — SYNTHETIC | – |
| 6 | Data-quality workspace | `dialogs/data_quality_dialog.py` | – | M227 | DB | finding sources | `test_m227_*` | m201_m230 | IMPLEMENTED AND QUALIFIED — SYNTHETIC | – |
| 7 | Well architecture | `tabs/well_architecture_panel.py` | in, ft | M57/M65 | DB (revisions) | revision SHA | `test_m89_*` | m201_m230 | IMPLEMENTED — PARTIALLY QUALIFIED | independent validation |
| 8 | Wellbore schematic | `tabs/w3b_wellbore_schematic_tab.py` | in, ft | M205 | document | provenance block | `test_m205_m207_*` | m201_m230 | IMPLEMENTED — PARTIALLY QUALIFIED | visual aid only, not verification |
| 9 | Surveys, integrity, revisions | `tabs/w6_Trajectory_Widget.py` | MD/inc/azi | minimum curvature; M85/M105 | DB | survey revision | `test_m105_*`, `test_m270_*` (TR) | m101_m120, TR-* | IMPLEMENTED — PARTIALLY QUALIFIED | P10 datum/CRS |
| 10 | Trajectory views, layers, saved views | `tabs/trajectory_viewer.py` | – | M132/M178 | DB (saved views) | – | `test_m132_*`, `test_m178_*` | m50 | IMPLEMENTED — PARTIALLY QUALIFIED | D51 not reproduced, not resolved |
| 11 | Plan designer | `tabs/well_plan_designer_panel.py` | ft/m, deg | M86/M106 | DB | plan revision | `test_m106_*` | m101_m120 | IMPLEMENTED — PARTIALLY QUALIFIED | independent validation |
| 12 | Anti-collision screening | `core/engineering/engines/anti_collision.py`, W13 (`tabs/w13_Engineering_Calculator.py`), plan designer | one linear unit | centreline + supplied 1σ RSS (not ISCWSA) | – | method/scope on result | `test_anti_collision_*`, `test_m270_*` | **AC-* 12/12** | IMPLEMENTED — PARTIALLY QUALIFIED | **BLOCKED BY OWNER DECISION** for ISCWSA (P19) |
| 13 | Hydraulics | W13 | ppg, gpm, in, psi | W13 contracts M87/M107 | history | contract id | `test_m87_*`, `test_m125_*` | m83_m96, m121_m140 | IMPLEMENTED — PARTIALLY QUALIFIED | independent validation |
| 14 | Mud volume | `core/engineering/engines/mud_volume.py` | bbl | balance; snapshot v1 | DB history | snapshot | `test_mud_volume_*`, `test_m270_*` | m101_m120, **MV-* 4/4** | IMPLEMENTED AND QUALIFIED — SYNTHETIC | P8 (7.48 kept) |
| 15 | Mud engineering | `tabs/mud_engineering_panel.py` | ppg/pcf | – | DB | – | per-tab tests | partial | IMPLEMENTED — PARTIALLY QUALIFIED | P8 |
| 16 | Casing design | `core/engineering/engines/casing.py` | psi, lbf, in, ppf | VME; `transition F r3` | DB history | M89 source block | `test_casing_*`, `test_m239_*`, `test_m270_*` | CAS-*, **CP-* 5/5** | IMPLEMENTED — PARTIALLY QUALIFIED | P12 methods, P18 tubular data |
| 17 | Cementing | `core/engineering/engines/cement.py` | bbl, ft³, ppg | M109; no inferred TOC/BOC | DB history | snapshot | cement tests | m52 | IMPLEMENTED — PARTIALLY QUALIFIED | independent validation |
| 18 | Torque and drag | `core/engineering/engines/torque_drag.py` | lbf, ft·lbf | soft string | DB history | snapshot | `test_torque_drag_*` | m121_m140, TD-* | IMPLEMENTED — PARTIALLY QUALIFIED | P3 (LGPL alternatives) |
| 19 | MSE | `core/engineering/engines/mse.py` | lbf, rpm, ft/h | Teale; snapshot v1 | DB history | snapshot | `test_mse_*` | MSE-* | IMPLEMENTED AND QUALIFIED — SYNTHETIC | independent validation |
| 20 | Bit performance, BHA, bit runs | `core/engineering/engines/bit_performance.py`, `tabs/bit_run_panel.py` | m, h, rpm, $ | weighted ROP, d-exponent, cost/ft | DB | – | `test_weighted_rop`, `test_m130_*`, `test_m270_*` | **BP-* 7/7** | IMPLEMENTED — PARTIALLY QUALIFIED | independent validation |
| 21 | Well control, Kill Sheet | `core/engineering/well_control_kill_sheet.py`, `core/engineering/engines/well_control.py` | psi, ppg, bbl, stk | M177 | DB history | snapshot | `test_well_control_*`, `test_m269_*`, `test_m270_*` | KS-*, **WC-* 7/7** | IMPLEMENTED — PARTIALLY QUALIFIED | **TRAINING AID**; P11 |
| 22 | Fishing / stuck pipe | `core/engineering/engines/fishing.py`, W13 stuck pipe | in, ft, lbf, ppg | legacy chart approximations (SCREENING); D81 fixed | W13 contract | contract | `test_m270_*`, `test_w13_fishing_result_ui` | **FI-* 8/8** | IMPLEMENTED — PARTIALLY QUALIFIED | screening only |
| 23 | W13 calculator classifications | W13 | – | M107/M125 | – | contract | `test_m125_*` | m83_m96 | IMPLEMENTED AND QUALIFIED — SYNTHETIC | – |
| 24 | Executive dashboard, KPI definitions | `tabs/home_tab.py`, `tabs/dashboard_widgets.py` | per KPI | M53; **M285 seven-field specs** | derived | source, as-of on each KPI | `test_m53_*`, `test_operations_dashboard`, `test_m285_*` | m53_m56, **KP-* 4/4** | IMPLEMENTED — PARTIALLY QUALIFIED | w12 Analysis KPIs have no structured spec |
| 25 | Operational analysis, NPT | `tabs/w12_Analysis.py`, `tabs/npt_reconciliation_panel.py` | h | M91/M104 | derived | evidence records | `test_m48_*` | m48, m101_m120 | IMPLEMENTED AND QUALIFIED — SYNTHETIC | – |
| 26 | Calculation workbench (MATCH / DIFFERENT / NOT_REPRODUCIBLE / UNREADABLE) | `tabs/calculation_history_tab.py` | – | M88/M108 | DB | snapshot + method | `test_m88_*`, `test_m108_*` | m101_m120 | IMPLEMENTED AND QUALIFIED — SYNTHETIC | D81 makes pre-fix stuck-pipe records re-run DIFFERENT (correct) |
| 27 | Report Center, export | `tabs/w11_Export.py`, `core/report_provenance.py` | – | M110 | files | provenance block | `test_m110_*` | m101_m120 | IMPLEMENTED — PARTIALLY QUALIFIED | no byte-identical claim for timestamped output |
| 28 | End-of-well package | `tabs/well_package_panel.py` | – | M135 | files | manifest | `test_d59_*` | m121_m140 | IMPLEMENTED AND QUALIFIED — SYNTHETIC | – |
| 29 | Offline document intelligence | `tabs/knowledge_assistant.py` | – | keyword retrieval with exact citations | DB index | citations | `test_m49_*` … `test_m52_*` | m49–m52 | IMPLEMENTED — PARTIALLY QUALIFIED | P4, P5, P7 |
| 30 | Units, constants | `core/unit_manager.py` | – | M113 inventory | – | – | inventory gate | m141_m170 | IMPLEMENTED — PARTIALLY QUALIFIED | P8 |
| 31 | Security, authorization, audit, privacy | `core/authorization.py`, `tools/privacy/privacy_check.py` | – | M121–M140 | DB | audit log | SEC tests | m121_m140 (1 equivalent) | IMPLEMENTED — PARTIALLY QUALIFIED | P13, P14, P15, P16 |
| 32 | Migrations, backup, restore | `core/db_maintenance.py` | – | additive migrations | DB | – | `test_m204_*` | m201_m230 | IMPLEMENTED AND QUALIFIED — SYNTHETIC | P17 |
| 33 | Tubular reference import | `core/engineering/tubular_import.py` | in, ppf | M181/M220 | DB | import provenance | `test_m181_*`, `test_m220_*` | m201_m230 | **BLOCKED BY LICENSE OR DATA RIGHTS** (no shipped dataset); import implemented | P18 |
| 34 | Planning, procedures, cost, safety, services | `w10`, `w14`, `w16`, `w8`, `w9`, `w5` | – | – | DB | – | per-tab, journeys | m171_m200 | IMPLEMENTED — PARTIALLY QUALIFIED | P9 currency |
| 35 | Reliability tooling (D63 reproducer, fault reporter, RSS profile, watchdog) | `tools/quality/*` | – | M264/M267 | – | – | opt-in | – | IMPLEMENTED — NOT UI-INTEGRATED (developer tooling) | – |
| 36 | Windows installer, release gate | `.github/workflows/windows-release-gate.yml` | – | – | – | – | CI per SHA | none | IMPLEMENTED — PARTIALLY QUALIFIED | **BLOCKED BY OWNER DECISION** for signing (P16), field acceptance (P17) |

Mutation reach after M270: all seven modules listed as unmutated in the M241 section above are now mutated
(`mutation_m261_m290`). Areas not reached by any catalogue: 36 (installer) and the fishing UI. The M289 cross-module journey
(`tests/test_m289_cross_module_journey.py`) chains areas 9, 12, 14, 16, 20, 21, 22, 24, 26 and 27.
