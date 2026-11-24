# DrillMaster complete engineering capability catalogue — M400

**Product label: PARTIAL — UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**
Written against the M361–M400 code (branch `arena/72010272-drill-master`). It supersedes the M290 36-area table in
`M241_CAPABILITY_INVENTORY.md` for **state**; that table stays as the M290 record. Exact commit SHAs, CI runs and the
mutation catalogue are in `docs/mission-reports/M361_M400_INTEGRATED_ENGINEERING_COMPLETION_REPORT.md` (a file
cannot name the commit that contains it).

## Rules used

**State vocabulary (strict, unchanged from M290):**
IMPLEMENTED AND QUALIFIED — SYNTHETIC · IMPLEMENTED — PARTIALLY QUALIFIED · IMPLEMENTED — NOT UI-INTEGRATED ·
ENGINE ONLY · UI ONLY · DOCUMENTED ONLY · BLOCKED BY OWNER DECISION · BLOCKED BY LICENSE OR DATA RIGHTS ·
NOT IMPLEMENTED · DEPRECATED · READ-ONLY.

* There is **no COMPLETE label**. No domain has real-world or field acceptance (P17), so "QUALIFIED — SYNTHETIC" is
  the highest state used, and it means: UI entry, persistence, provenance, a real-workflow test and a mutation
  catalogue entry, all on **synthetic** data.
* Method labels are part of the state: **SCREENING** (a simplified method; not for design sign-off), **WORKSHEET**
  (arithmetic aid; not a design approval), **TRAINING AID** (well control; P11 — not for operational use).
* Mutation results show the listed tests detect the listed defects; they are **not proof of correctness**.
* "Tests" names files on the final tree; it is where the evidence is, not a validation claim.
* A missing input stays missing: every M361–M400 service reports NOT ASSESSED instead of assuming a value.

**Fields per domain:** entry point · inputs and units · method and version · persistence · provenance · tests ·
mutation catalogue · state · limitations and owner gates.

## Catalogue (48 domains)

| # | Domain | Entry point | Inputs, units | Method, version | Persistence | Provenance | Tests | Mutation | State | Limitations, gates |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Well hierarchy, selection and shared well context | `main_window.py`, `core/selection_manager.py`, `core/base_tab.py` | ids | M83/M102 context; M265 routes; **M387** dialogs freeze the well they open for | DB | well id on every case | `test_m70`, `test_m83`, `test_m102`, `test_m265`, **`test_m387_shared_well_context`** | m70_m76, m101_m120, LC-* | IMPLEMENTED AND QUALIFIED — SYNTHETIC | P17 desktop acceptance |
| 2 | Window and Qt lifecycle | `main_window.closeEvent`, `core/qt_lifetime.py` | – | M265; M308 release policy; **M376** dialog parenting | – | – | `test_m265_*`, `test_m326_window_lifecycle`, `test_d74_*`, **`test_m376_qt_lifecycle`** | LC-* | IMPLEMENTED — PARTIALLY QUALIFIED | closed MainWindows retained on 6.8.1.1 (D74/D63); pin change **BLOCKED BY OWNER DECISION** (M378 recommends 6.8.3) |
| 3 | DDR daily workspace | `tabs/w2_Daily_Report.py`, `tabs/w3_drilling_report.py`, `core/ddr_value_states.py` | API field units; value states | M54/M84; M217; `ddr-value-states-v1` | DB (append-only) | report lineage, value-state events | `test_m169`, `test_m217_*`, `test_m272_*` | m54, m201_m230, m261_m290 (VS) | IMPLEMENTED AND QUALIFIED — SYNTHETIC | value states cover 11 header fields; real DDR NOT RUN |
| 4 | DDR import and value lineage | `core/ddr_import_service.py`, `dialogs/excel_import_dialog.py` | workbook cells | M61/M111/M213–M218; M300–M302 lineage | DB | source → parsed → normalized → corrected → accepted | `test_m213_*` … `test_m218_*`, `test_m273_*`, `test_m300_m301_value_lineage`, `test_m302_lineage_ui` | m61_m67, m201_m230, m261_m290 (IL) | IMPLEMENTED AND QUALIFIED — SYNTHETIC | real DDR acceptance NOT RUN |
| 5 | Import review queue | `core/import_review_queue.py` | – | M150 | DB | parent links | `test_m147_m152_*`, `test_m239_*` | m231_m260 | IMPLEMENTED AND QUALIFIED — SYNTHETIC | – |
| 6 | Data-quality workspace | `dialogs/data_quality_dialog.py` | – | M227; M272 | DB | finding sources | `test_m227_*`, `test_m272_*` | m201_m230, m261_m290 (VS) | IMPLEMENTED AND QUALIFIED — SYNTHETIC | – |
| 7 | Well architecture and revision diff | `tabs/well_architecture_panel.py` | in, ft | M57/M65; M311 diff; M329 export | DB (revisions) | revision SHA | `test_m89_*`, `test_m311_architecture_diff`, `test_m329_*` | m201_m230, m321_m360 | IMPLEMENTED — PARTIALLY QUALIFIED | independent validation |
| 8 | Wellbore schematic | `tabs/w3b_wellbore_schematic_tab.py` | in, ft | M205 | document | provenance block | `test_m205_m207_*` | m201_m230 | IMPLEMENTED — PARTIALLY QUALIFIED | visual aid only |
| 9 | Surveys, integrity, revisions | `tabs/w6_Trajectory_Widget.py` | MD, inc, azi | minimum curvature; M85/M105 | DB | survey revision SHA | `test_m105_*`, `test_m270_*` | m101_m120, TR-* | IMPLEMENTED — PARTIALLY QUALIFIED | P10 datum / CRS |
| 10 | Survey plan vs actual, targets (M368) | 3D view › layers › **"Plan vs actual…"** (`tabs/trajectory_layers_panel.py`, `dialogs/survey_plan_deviation_dialog.py`), `core/survey_plan_deviation.py` | m; declared tolerance | `m368.survey_plan_deviation` v1: centreline right/high/distance per plan station, target HIT/MISS | calculation case | frozen survey + plan stations, revision SHAs, tie-in | `test_m368_survey_plan_deviation`, `test_m375_main_window_journey` | **SPD-* 6** | IMPLEMENTED — PARTIALLY QUALIFIED (SCREENING) | centreline only; refuses (never converts) a datum or azimuth-reference mismatch; no uncertainty; P10 |
| 11 | Trajectory views, layers, saved views | `tabs/trajectory_viewer.py` | – | M132/M178 | DB | – | `test_m132_*`, `test_m178_*`, `test_trajectory_3d` | m50 | IMPLEMENTED — PARTIALLY QUALIFIED | D51 not reproduced, not resolved |
| 12 | Plan designer | `tabs/well_plan_designer_panel.py` | ft/m, deg | M86/M106 | DB | plan revision | `test_m106_*` | m101_m120 | IMPLEMENTED — PARTIALLY QUALIFIED | independent validation |
| 13 | Anti-collision screening (M369) | `core/engineering/engines/anti_collision.py`, W13, plan designer | one linear unit | centreline + supplied 1σ RSS; `closest_approach_3d` geometric minimum (M369) | – | method / scope on result | `test_anti_collision_*`, `test_m367_m369_m396_engineering` | AC-* | IMPLEMENTED — PARTIALLY QUALIFIED (SCREENING) | **not an ISCWSA separation factor** — ISCWSA **BLOCKED BY OWNER DECISION** (P19) |
| 14 | Hydraulics calculator | W13 hydraulics | ppg, gpm, in, psi | W13 contracts M87/M107 | history | contract id | `test_m87_*`, `test_m125_*` | m83_m96, m121_m140 | IMPLEMENTED — PARTIALLY QUALIFIED | independent validation |
| 15 | Hydraulics workflow: pressure budget, sensitivities, plan vs actual (M366) | W13 › **"Budget & sensitivity…"** (`dialogs/hydraulics_workflow_dialog.py`), `core/hydraulics_workflow.py` | gpm, ppg, psi, in | `m366.hydraulics_workflow`: losses, bit ΔP, TFA, HHP, HSI, jet velocity, impact force, AV; ECD only with complete annular geometry | calculation case | inputs SHA-256; replay adapter | `test_m366_hydraulics_workflow`, `test_m375_*` | **HW-* 9** | IMPLEMENTED — PARTIALLY QUALIFIED (SCREENING) | refused until the displayed inputs are confirmed; surface losses NOT ASSESSED without surface geometry; P8 |
| 16 | Hole cleaning, CCI (M370) | M366 workflow | ppg, ft/min, Fann 600/300 | CCI = K·AV·MW/400 000 | in the M366 case | as M366 | `test_m366_hydraulics_workflow` | HW-* | IMPLEMENTED — PARTIALLY QUALIFIED (SCREENING) | ≤ 35° only (NOT APPLICABLE above); CCI shown in summary lines only |
| 17 | DDR bit-hydraulics check (M314) | DDR | gpm, psi | recorded vs recomputed | calculation case | replay adapter | `test_m314_ddr_hydraulics_check` | m321_m360 | IMPLEMENTED — PARTIALLY QUALIFIED (SCREENING) | – |
| 18 | Mud volume | `core/engineering/engines/mud_volume.py` | bbl | balance; snapshot v1 | DB history | snapshot | `test_mud_volume_*`, `test_m270_*` | m101_m120, MV-* | IMPLEMENTED AND QUALIFIED — SYNTHETIC | P8 |
| 19 | Mud engineering | `tabs/mud_engineering_panel.py` | ppg / pcf | – | DB | – | per-tab tests | partial | IMPLEMENTED — PARTIALLY QUALIFIED | P8 |
| 20 | Casing design, API TR 5C3 pipe-body subset | W13 casing, `core/engineering/engines/casing.py` | psi, lbf, in, ppf | Barlow, four-regime collapse, fyax, VME; `transition F r3` | DB history | M89 source block | `test_casing_*`, `test_m239_*`, `test_m270_*` | CAS-*, CP-* | IMPLEMENTED — PARTIALLY QUALIFIED | P12 methods, P18 tubular data |
| 21 | Casing axial-load components and wear (M371) | W13 casing › **"📐 Axial loads & wear…"** (`dialogs/casing_axial_loads_dialog.py`), `core/casing_axial_loads.py` | in, psi, lbf, °F, deg/100 ft, % | `m371.casing_axial_loads` v1: bending, thermal, ballooning, fibre stress, worn-wall burst / collapse via `CasingEngine` | calculation case | inputs SHA-256; replay adapter | `test_m371_casing_axial_loads`, `test_m376_*`, `test_m387_*`, `test_m388_units_contract` | **CAL-* 5** | IMPLEMENTED — PARTIALLY QUALIFIED (SCREENING) | pipe body only; no triaxial envelope, no connection rating, no casing buckling; E, α, ν declared (no steel defaults); wear keeps the 0.875 wall tolerance |
| 22 | Cementing worksheet and balanced plug | `core/engineering/engines/cement.py` | bbl, ft³, ppg | M109 worksheet; M52 balanced plug (cement-calc method, MIT) | DB history | snapshot | `test_m109_cement_worksheet`, `test_m52_balanced_plug`, cement tests | m52 | IMPLEMENTED — PARTIALLY QUALIFIED (WORKSHEET) | no inferred TOC/BOC, yield or sacks |
| 23 | Cement job reconciliation (M317) | cementing | bbl | recorded job vs architecture | calculation case | replay adapter | `test_m317_cement_job_reconciliation` | m321_m360 | IMPLEMENTED — PARTIALLY QUALIFIED (WORKSHEET) | – |
| 24 | Torque and drag (M367) | W13 T&D, `core/engineering/engines/torque_drag.py` | lbf, ft·lbf, ppg | Johancsik soft string (SPE 11380), segments ≤ 5 m | DB history | survey revision pinning | `test_torque_drag_*`, `test_m367_m369_m396_engineering`, `test_m349_benchmarks_d92` | TD-*, TDP-* | IMPLEMENTED — PARTIALLY QUALIFIED (SCREENING) | soft string, never "stiff string"; LGPL `torque_drag` not adopted (P3) |
| 25 | Buckling check (D93) | inside T&D | lbf | D93 v2 = max(Dawson-Paslay/Chen, Lubinski 1.94, WJW 5.55 · (EIw²)^(1/3)) | with T&D | version pinned | `test_m367_*`, `test_m349_*` | TD-* | IMPLEMENTED — PARTIALLY QUALIFIED (SCREENING) | onset check only, no post-buckling contact model |
| 26 | T&D friction-factor sensitivity (M318) | W13 T&D › FF list | — | `m318.td_friction_sensitivity` | calculation case | replay adapter, v2/v3 pinned | `test_m318_td_friction_sensitivity`, `test_m375_*` | TDS-* | IMPLEMENTED — PARTIALLY QUALIFIED (SCREENING) | – |
| 27 | MSE (Teale) | W13 bit page, `core/engineering/engines/mse.py` | lbf, rpm, ft·lbf, ft/h, in | Teale 120π; snapshot v1 | DB history | snapshot | `test_mse_*` | MSE-* | IMPLEMENTED AND QUALIFIED — SYNTHETIC | surface WOB / torque |
| 28 | Drill-off test: founder point, step MSE, drilling efficiency (M372) | W13 bit page › **"📈 Drill-off test (founder)…"** (`dialogs/mse_drilloff_dialog.py`), `core/mse_drilloff.py` | klbf, rpm, ft·lbf, ft/h, in, psi (CCS) | `m372.mse_drilloff` v1: Dupriest & Koederitz step test; stated slope-fraction rule; MSE through `MSEEngine`; efficiency = CCS/MSE | calculation case | inputs + steps SHA-256; replay adapter | `test_m372_mse_drilloff`, `test_m387_*`, `test_m388_*` | **MDO-* 6** | IMPLEMENTED — PARTIALLY QUALIFIED (SCREENING) | constant-RPM test only (refuses beyond the declared tolerance); no CCS correlation; not an optimiser |
| 29 | Bit performance, bit runs, BHA | `core/engineering/engines/bit_performance.py`, `tabs/bit_run_panel.py`, `core/bit_runs.py`, `core/legacy_bha.py` | m, h, rpm, $ | weighted ROP, d-exponent, cost/ft | DB | – | `test_weighted_rop`, `test_m130_*`, `test_m270_*` | BP-* | IMPLEMENTED — PARTIALLY QUALIFIED | independent validation |
| 30 | Kill sheet (Driller's, Wait & Weight) | W13 well control, `core/engineering/well_control_kill_sheet.py` | psi, pcf, bbl, stk | M177; 10-interval choke schedule | DB history | snapshot | `test_well_control_*`, `test_m269_*`, `test_kill_sheet_casing_id_gate` | KS-*, WC-* | IMPLEMENTED — PARTIALLY QUALIFIED (**TRAINING AID**) | P11 |
| 31 | Kick tolerance, MAASP, influx type | `core/engineering/engines/well_control.py` | psi, ppg, bbl | IWCF / IADC manuals | DB history | snapshot | `test_well_control_*`, `test_m270_*` | WC-* | IMPLEMENTED — PARTIALLY QUALIFIED (**TRAINING AID**) | single bubble, no z-factor; P11 |
| 32 | Volumetric method and gas migration (M373) | W13 well control › **"🫧 Volumetric method (TRAINING AID)…"** (`dialogs/well_control_volumetric_dialog.py`), `core/well_control_volumetric.py` | psi, pcf, bbl/ft, h | `m373.volumetric_method` v1: G = ρ/144, ΔV = Pw·C/G, hold SICP+Ps+k·Pw; migration (dP/dt)/G | calculation case | inputs SHA-256; replay adapter | `test_m373_volumetric_method`, `test_m387_*`, `test_m388_*` | **WCV-* 5** | IMPLEMENTED — PARTIALLY QUALIFIED (**TRAINING AID**) | stops at a declared casing limit; single bubble, constant capacity, no gas law; lubricate-and-bleed NOT IMPLEMENTED; P11 |
| 33 | Fishing / stuck pipe | W13 stuck pipe, `core/engineering/engines/fishing.py` | in, ft, lbf, ppg | legacy chart approximations | W13 contract | contract | `test_m270_*`, `test_w13_fishing_result_ui` | FI-* | IMPLEMENTED — PARTIALLY QUALIFIED (SCREENING) | – |
| 34 | W13 calculator classifications | W13 | – | M107/M125 | – | contract | `test_m125_*` | m83_m96 | IMPLEMENTED AND QUALIFIED — SYNTHETIC | – |
| 35 | Executive dashboard KPIs | `tabs/home_tab.py`, `tabs/dashboard_widgets.py` | per KPI | M53; M285 seven-field specs | derived | source, as-of | `test_m53_*`, `test_m285_*` | m53_m56, KP-* | IMPLEMENTED — PARTIALLY QUALIFIED | – |
| 36 | Operational analysis KPIs, NPT (M374) | `tabs/w12_Analysis.py`, `core/analysis_evidence.py` | h | M91/M104; **M374** structured KPI specs with tooltips | derived | evidence records | `test_m48_*`, `test_m374_w12_kpi_specs`, `test_m375_*` | m48, KPI-* | IMPLEMENTED — PARTIALLY QUALIFIED | – |
| 37 | Calculation workbench: clone, archive, restore, D87 identity (M365) | `tabs/calculation_history_tab.py`, `core/calculation_workbench.py`, `core/record_identity.py` | – | M286; M303–M306; **M365** `D87fp1` fingerprint | DB (+ archive marks) | clone link; VERIFIED / SOURCE_REPLACED / TIMESTAMP_ONLY | `test_m286_*`, `test_m303_m306_*`, `test_m365_d87_identity` | **ID-* 8**, m261_m290 (WB) | IMPLEMENTED AND QUALIFIED — SYNTHETIC | legacy clones stay TIMESTAMP_ONLY |
| 38 | Calculation history replay (M328 + M361–M400 adapters) | `core/history_replay.py` | per-unit tolerances (M388) | MATCH / DIFFERENT / NOT_REPRODUCIBLE / UNREADABLE | – | inputs SHA-256 checks | `test_m323_m328_*`, the M366/M368/M371/M372/M373 replay tests, `test_m388_units_contract` | m321_m360, HW/SPD/CAL/MDO/WCV | IMPLEMENTED AND QUALIFIED — SYNTHETIC | repeatability tolerances, not engineering acceptance |
| 39 | Report Center, export | `tabs/w11_Export.py`, `core/report_provenance.py` | – | M110 | files | provenance block | `test_m110_*` | m101_m120 | IMPLEMENTED — PARTIALLY QUALIFIED | no byte-identical claim for timestamped output |
| 40 | End-of-well package | `tabs/well_package_panel.py` | – | M135; M320 section manifest | files | manifest | `test_d59_*` | m121_m140 | IMPLEMENTED AND QUALIFIED — SYNTHETIC | – |
| 41 | Offline document intelligence | `tabs/knowledge_assistant.py` | – | keyword retrieval, exact citations; M320/M334 citation records | DB index | citations | `test_m49_*` … `test_m52_*`, `test_m334_*` | m49–m52 | IMPLEMENTED — PARTIALLY QUALIFIED | P4, P5, P7 |
| 42 | Units and constants (M388) | `core/unit_manager.py`, `docs/engineering/constant_inventory.json` | – | M113 inventory; P8 divisor kept; M388 replay-unit contract | – | – | inventory gate, `test_m113_*`, `test_m192_*`, `test_m388_units_contract` | m141_m170 | IMPLEMENTED — PARTIALLY QUALIFIED | P8 |
| 43 | Security, authorization, audit, privacy | `core/authorization.py`, `tools/privacy/privacy_check.py` | – | M121–M140 | DB | audit log | SEC tests, `test_privacy_check` | m121_m140 | IMPLEMENTED — PARTIALLY QUALIFIED | encryption at rest NOT PROVIDED; P13–P16 |
| 44 | Dependency licence and vulnerability audit (M386) | `tools/quality/dependency_audit.py`, **`tools/quality/vuln_audit_m386.py`** | lock pins | M112 licence audit; M386 PyPI/OSV advisory check (NOT CHECKED is never clean) | `docs/engineering/dependency_audit.json`, M386 evidence JSON | lock + advisory ids | `test_m112_*`, `test_m137_*`, **`test_m386_vuln_audit`** | – | IMPLEMENTED — NOT UI-INTEGRATED (developer tooling) | pillow raised 12.3.0 → 13.0.0 for 58 published advisories; PySide pins untouched (P2 / M378) |
| 45 | Migrations, backup, restore | `core/db_maintenance.py` | – | additive migrations | DB | – | `test_m204_*` | m201_m230 | IMPLEMENTED AND QUALIFIED — SYNTHETIC | P17 |
| 46 | Tubular reference import | `core/engineering/tubular_import.py` | in, ppf | M181/M220 | DB | import provenance | `test_m181_*`, `test_m220_*` | m201_m230 | **BLOCKED BY LICENSE OR DATA RIGHTS** (no shipped dataset); import implemented | P18 |
| 47 | Planning, procedures, cost, safety, services, logistics | `w5`, `w7`, `w8`, `w9`, `w10`, `w14`, `w16` | – | – | DB | – | per-tab tests, journeys | m171_m200 | IMPLEMENTED — PARTIALLY QUALIFIED | P9 currency |
| 48 | Reliability, CI and release tooling (M377), Windows installer | `tools/quality/*`, **`tools/quality/ci_run_states.py`**, **`tools/quality/run_suite_sharded.py`**, `.github/workflows/*` | – | M264/M267/M309; M377 states SUCCESS / SUPERSEDED / TIMEOUT / FAILURE / IN_PROGRESS | – | per-SHA CI | `test_m377_ci_run_states`, `test_m309_*`, `test_windows_release_gate_contract` | CRS-* | IMPLEMENTED — NOT UI-INTEGRATED (developer tooling); installer IMPLEMENTED — PARTIALLY QUALIFIED | signing **BLOCKED BY OWNER DECISION** (P16); field acceptance P17; the 3.12 CI leg runs 55–60+ min against a 60 min limit (D88, timeout not raised) |

### Counts

| State | Domains |
|---|---|
| IMPLEMENTED AND QUALIFIED — SYNTHETIC | 1, 3, 4, 5, 6, 18, 27, 34, 37, 38, 40, 45 (12) |
| IMPLEMENTED — PARTIALLY QUALIFIED (incl. SCREENING / WORKSHEET / TRAINING AID) | 2, 7–17, 19–26, 28–33, 35, 36, 39, 41–43, 47 (33) |
| IMPLEMENTED — NOT UI-INTEGRATED (developer tooling) | 44, 48 (tooling part) (2) |
| BLOCKED BY LICENSE OR DATA RIGHTS | 46 (1) |

Owner-gated parts inside other rows: ISCWSA (13, P19), PySide pin (2, P2), signing (48, P16), tubular data (20, 46,
P18), casing method set (20, 21, P12), kill-sheet operational use (30–32, P11).

## PLANNED ENGINEERING CAPABILITIES — NOT YET IMPLEMENTED (M393)

Each item below is **NOT IMPLEMENTED**. Nothing in the product computes it; the roadmap
(`DRILLMASTER_ENGINEERING_ROADMAP_M400.md`) gives the order and gates.

| Id | Capability | Why not yet | Gate |
|---|---|---|---|
| N-1 | ISCWSA error models and separation factor | owner decision on welleng / ISCWSA source | P19 |
| N-2 | Stiff-string torque and drag | method work; LGPL reference not adoptable | P3 |
| N-3 | Herschel-Bulkley slot-annulus pressure losses, Colebrook turbulent friction (R-HYD-2, BoreTHM Apache-2.0 method reference) | clean-room implementation and benchmarks not done | – |
| N-4 | Wellbore temperature model | pwptemp is LGPL | P3 |
| N-5 | Triaxial casing design envelope with connection ratings and casing buckling | method set and rating data | P12, P18 |
| N-6 | Surge and swab | not started | – |
| N-7 | Lubricate-and-bleed, bullheading worksheets | not started; TRAINING AID scope | P11 |
| N-8 | Gas-law kick migration (expansion, z-factor) | not started | P11 |
| N-9 | Datum / CRS conversion for surveys | refused today rather than converted | P10 |
| N-10 | Bit wear / dull-grade prediction | no validated method | – |
| N-11 | Real-time data ingestion (WITSML) | out of scope of the desktop product so far | – |
| N-12 | Encryption at rest | NOT PROVIDED | P13 |
