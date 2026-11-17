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
