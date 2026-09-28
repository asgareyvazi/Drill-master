> **HISTORICAL MISSION RECORD — Mission 30 checkpoint (2026-09-23).** Its inventory baseline (2232 occurrences) and its `NOT RELEASE-CERTIFIABLE — EVIDENCE INCOMPLETE` verdict describe the tree as it stood then; the numbers have since been re-adjudicated by Missions 31-33. Current state: 8932 occurrences, 3712 verified-correct, 2266 intentional-by-design, 47 defect-fixed, 49 removed-with-evidence, 2837 under-review, 4 evidence-incomplete — see [M33_SEMANTIC_AUDIT.md](M33_SEMANTIC_AUDIT.md). The body of this document is preserved unedited.

---

# M30 domain evidence matrix

Primary-domain routing below is an explicit triage mapping, not semantic proof. All 2232 baseline queue records are assigned once so totals are not inflated across domains. Shared modules may support other domains too. Zero selected-pattern items does NOT mean a domain has no code or is verified. All domains remain PARTIAL; 69/69 closure is not achieved.

| Domain | Inventory | Reviewed/Total | A Correct | B Defect/fixed | C Legacy | D Intentional | E Limitation | F External | G Evidence lacking | Tests/Fixes | Residual / Status |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| Git lineage/recovery | 0 | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Existing domain suite executed; no full semantic claim | Original 0bbcbd4 ancestry unavailable; PARTIAL |
| Canonical model registry | 744 | 0/744 | 0 | 0 | 0 | 0 | 0 | 0 | 744 | Existing domain suite executed; no full semantic claim | Individual default adjudication incomplete; PARTIAL |
| Wellbore ownership | 12 | 0/12 | 0 | 0 | 0 | 0 | 0 | 0 | 12 | Existing domain suite executed; no full semantic claim | All mutation order permutations not claimed; PARTIAL |
| Section ownership | 0 | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Existing domain suite executed; no full semantic claim | Residual site review incomplete; PARTIAL |
| Report ownership | 0 | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Existing domain suite executed; no full semantic claim | Direct SQL/legacy production data acceptance; PARTIAL |
| Parent reassignment | 0 | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Existing domain suite executed; no full semantic claim | Production migration datasets unavailable; PARTIAL |
| Startup/migration | 0 | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Existing domain suite executed; no full semantic claim | Every possible partial schema not certified; PARTIAL |
| Scope attribution | 3 | 3/3 | 1 | 2 | 0 | 0 | 0 | 0 | 0 | M30 regressions + existing domain modules; see item evidence | Exhaustive preview/apply case inventory incomplete; PARTIAL |
| Company/project/well hierarchy | 26 | 0/26 | 0 | 0 | 0 | 0 | 0 | 0 | 26 | Existing domain suite executed; no full semantic claim | All hierarchy UI failures not individually audited; PARTIAL |
| Daily report lifecycle | 52 | 0/52 | 0 | 0 | 0 | 0 | 0 | 0 | 52 | Existing domain suite executed; no full semantic claim | All print/export consumers not individually closed; PARTIAL |
| Revision snapshots | 0 | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Existing domain suite executed; no full semantic claim | Production snapshot restore acceptance; PARTIAL |
| Next-day carry-forward | 0 | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Existing domain suite executed; no full semantic claim | Cross-entrypoint copy parity and repeat-copy behavior incomplete; PARTIAL |
| Credentials/bootstrap | 13 | 0/13 | 0 | 0 | 0 | 0 | 0 | 0 | 13 | Existing domain suite executed; no full semantic claim | Remote secrets/production policy outside sandbox; PARTIAL |
| Permissions/W8 | 1 | 0/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | Existing domain suite executed; no full semantic claim | All UI Edit/Reset/Import paths not individually closed; PARTIAL |
| Backup/restore | 4 | 3/4 | 2 | 0 | 0 | 0 | 1 | 0 | 1 | M30 regressions + existing domain modules; see item evidence | Production-sized/corrupt/partial restore matrix incomplete; PARTIAL |
| Currency/NULL reducers | 3 | 0/3 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | Existing domain suite executed; no full semantic claim | Every category consumer not individually certified; PARTIAL |
| Daily cost/OPEX | 0 | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Existing domain suite executed; no full semantic claim | Complete category/time/unit trace pending; PARTIAL |
| CAPEX/revenue | 0 | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Existing domain suite executed; no full semantic claim | Dedicated revenue/CAPEX accounting workflow not certified; PARTIAL |
| Payroll/insurance/tax | 0 | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Existing domain suite executed; no full semantic claim | Not a verified payroll/tax calculation system; PARTIAL |
| Fuel/maintenance/overhead | 1 | 1/1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | M30 regressions + existing domain modules; see item evidence | Category-specific invoice-to-export audit incomplete; PARTIAL |
| Standby/moving | 0 | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Existing domain suite executed; no full semantic claim | No inferred monetary tariff; full consumer review pending; PARTIAL |
| Economic assumptions/IRR | 0 | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Existing domain suite executed; no full semantic claim | No verified IRR/NPV/revenue model asserted; PARTIAL |
| W16 cost scope | 7 | 0/7 | 0 | 0 | 0 | 0 | 0 | 0 | 7 | Existing domain suite executed; no full semantic claim | All handlers require individual scope/error adjudication; PARTIAL |
| Plan scalar/11-pair matrix | 3 | 3/3 | 2 | 0 | 0 | 1 | 0 | 0 | 0 | M30 regressions + existing domain modules; see item evidence | No claim all consumers closed by reducer test alone; PARTIAL |
| Well plan revision/persistence | 26 | 0/26 | 0 | 0 | 0 | 0 | 0 | 0 | 26 | Existing domain suite executed; no full semantic claim | Real operational plans not accepted yet; PARTIAL |
| Material identity/W10 | 1 | 0/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | Existing domain suite executed; no full semantic claim | All import aliases not exhaustively adjudicated; PARTIAL |
| NPT/W10 | 12 | 0/12 | 0 | 0 | 0 | 0 | 0 | 0 | 12 | Existing domain suite executed; no full semantic claim | Remaining chart consumers not fully certified; PARTIAL |
| W10 code/status charts | 4 | 0/4 | 0 | 0 | 0 | 0 | 0 | 0 | 4 | Existing domain suite executed; no full semantic claim | Full status/code domain collision audit pending; PARTIAL |
| W10 drilling/mud summaries | 10 | 0/10 | 0 | 0 | 0 | 0 | 0 | 0 | 10 | Existing domain suite executed; no full semantic claim | MW unit contract across all imports not individually closed; PARTIAL |
| W10 milestones | 2 | 0/2 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | Existing domain suite executed; no full semantic claim | Real schedule acceptance pending; PARTIAL |
| W12 shared KPI scope | 54 | 0/54 | 0 | 0 | 0 | 0 | 0 | 0 | 54 | Existing domain suite executed; no full semantic claim | All scalar assumptions not individually closed; PARTIAL |
| W12 today/unique selection | 1 | 0/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | Existing domain suite executed; no full semantic claim | All legacy date/alias permutations not closed; PARTIAL |
| W12 time-depth/calendar | 2 | 0/2 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | Existing domain suite executed; no full semantic claim | Multi-bore chart interpretation remains a review item; PARTIAL |
| W12 ROP prediction | 3 | 0/3 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | Existing domain suite executed; no full semantic claim | Not field forecasting acceptance; PARTIAL |
| W12 NPT forecast | 4 | 0/4 | 0 | 0 | 0 | 0 | 0 | 0 | 4 | Existing domain suite executed; no full semantic claim | Forecast model/assumptions require full consumer audit; PARTIAL |
| W12 cost analysis | 1 | 0/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | Existing domain suite executed; no full semantic claim | Every projection and fiscal category not certified; PARTIAL |
| W12 risk | 1 | 0/1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | Existing domain suite executed; no full semantic claim | Operational risk acceptance unavailable; PARTIAL |
| W12 plan/quality/milestones | 2 | 0/2 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | Existing domain suite executed; no full semantic claim | Complete line-by-line W12 closure still pending; PARTIAL |
| W11/export/report scope | 80 | 0/80 | 0 | 0 | 0 | 0 | 0 | 0 | 80 | Existing domain suite executed; no full semantic claim | Every Excel/PDF/HTML/JSON field not individually traced; PARTIAL |
| Report history/selection | 75 | 7/75 | 0 | 3 | 2 | 2 | 0 | 0 | 68 | M30 regressions + existing domain modules; see item evidence | Full mutation/reset interaction matrix incomplete; PARTIAL |
| Safety | 19 | 0/19 | 0 | 0 | 0 | 0 | 0 | 0 | 19 | Existing domain suite executed; no full semantic claim | All report/export safety consumers not individually closed; PARTIAL |
| Trip sheet/W6 | 0 | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Existing domain suite executed; no full semantic claim | Cumulative sum is entered-depth sum, not reconstructed travel; PARTIAL |
| Logistics/personnel/transport | 38 | 0/38 | 0 | 0 | 0 | 0 | 0 | 0 | 38 | Existing domain suite executed; no full semantic claim | Remaining personnel/equipment/default sites unadjudicated; PARTIAL |
| Inventory/bulk/fuel stock | 74 | 20/74 | 5 | 9 | 0 | 5 | 0 | 0 | 55 | M30 regressions + existing domain modules; see item evidence | Remaining raw import/default sites unadjudicated; PARTIAL |
| Engineering facade/result | 244 | 2/244 | 0 | 2 | 0 | 0 | 0 | 0 | 242 | M30 regressions + existing domain modules; see item evidence | Not independent field/formula certification; PARTIAL |
| Trajectory/MCM | 9 | 0/9 | 0 | 0 | 0 | 0 | 0 | 0 | 9 | Existing domain suite executed; no full semantic claim | Full W6 save/chart/export review incomplete; PARTIAL |
| Anti-collision | 14 | 0/14 | 0 | 0 | 0 | 0 | 0 | 0 | 14 | Existing domain suite executed; no full semantic claim | Field trajectories unavailable; PARTIAL |
| Hydraulics/nozzle/bit | 33 | 0/33 | 0 | 0 | 0 | 0 | 0 | 0 | 33 | Existing domain suite executed; no full semantic claim | Every adapter/UI default not independently reviewed; PARTIAL |
| Casing | 26 | 0/26 | 0 | 0 | 0 | 0 | 0 | 0 | 26 | Existing domain suite executed; no full semantic claim | All source calculations not independently recertified; PARTIAL |
| Cement | 17 | 0/17 | 0 | 0 | 0 | 0 | 0 | 0 | 17 | Existing domain suite executed; no full semantic claim | Field inputs/acceptance unavailable; PARTIAL |
| MSE | 7 | 2/7 | 2 | 0 | 0 | 0 | 0 | 0 | 5 | M30 regressions + existing domain modules; see item evidence | All UI numeric defaults not individually reviewed; PARTIAL |
| Mud volume | 20 | 0/20 | 0 | 0 | 0 | 0 | 0 | 0 | 20 | Existing domain suite executed; no full semantic claim | Field volume data not accepted; PARTIAL |
| Torque/drag | 36 | 0/36 | 0 | 0 | 0 | 0 | 0 | 0 | 36 | Existing domain suite executed; no full semantic claim | Independent physical validation unavailable; PARTIAL |
| Well control/kill sheet | 54 | 0/54 | 0 | 0 | 0 | 0 | 0 | 0 | 54 | Existing domain suite executed; no full semantic claim | Not safety-critical operational approval; PARTIAL |
| DrillPipe catalog/import | 9 | 0/9 | 0 | 0 | 0 | 0 | 0 | 0 | 9 | Existing domain suite executed; no full semantic claim | Every vendor alias/NFC/collision path not closed; PARTIAL |
| Schematic | 22 | 0/22 | 0 | 0 | 0 | 0 | 0 | 0 | 22 | Existing domain suite executed; no full semantic claim | Full persistence/report visual acceptance incomplete; PARTIAL |
| Excel raw/normalization | 7 | 0/7 | 0 | 0 | 0 | 0 | 0 | 0 | 7 | Existing domain suite executed; no full semantic claim | All date/number/identity normalization paths not audited; PARTIAL |
| DDR atomic persistence | 204 | 0/204 | 0 | 0 | 0 | 0 | 0 | 0 | 204 | Existing domain suite executed; no full semantic claim | Real PDF IR/review/persist unavailable; PARTIAL |
| Template learning/mapping | 69 | 0/69 | 0 | 0 | 0 | 0 | 0 | 0 | 69 | Existing domain suite executed; no full semantic claim | Concurrent editing/Windows replacement not accepted; PARTIAL |
| PDF/MinerU | 21 | 0/21 | 0 | 0 | 0 | 0 | 0 | 0 | 21 | Existing domain suite executed; no full semantic claim | Actual readable PDF pipeline ENVIRONMENT-BLOCKED; PARTIAL |
| JSON/copy independence | 0 | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Existing domain suite executed; no full semantic claim | Every reference/source mutation path not individually reviewed; PARTIAL |
| Export failure semantics | 51 | 0/51 | 0 | 0 | 0 | 0 | 0 | 0 | 51 | Existing domain suite executed; no full semantic claim | Every export format/partial-file path not closed; PARTIAL |
| Gate/accounting | 4 | 0/4 | 0 | 0 | 0 | 0 | 0 | 0 | 4 | Existing domain suite executed; no full semantic claim | Source gate is not exhaustive semantic certification; PARTIAL |
| Wheel/resources | 0 | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Existing domain suite executed; no full semantic claim | Windows DLL/plugins/installer runtime unexecuted; PARTIAL |
| Dependency reproducibility | 0 | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Existing domain suite executed; no full semantic claim | Build isolation tools not exact-lock reproducible; PARTIAL |
| CI/release workflow | 0 | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Existing domain suite executed; no full semantic claim | Fresh hosted run unavailable; GitHub authentication 401; PARTIAL |
| Security/user-data paths | 16 | 0/16 | 0 | 0 | 0 | 0 | 0 | 0 | 16 | Existing domain suite executed; no full semantic claim | Pen-test/log/backup/temp secret audit not exhaustive; PARTIAL |
| Legacy/duplicate modules | 91 | 0/91 | 0 | 0 | 0 | 0 | 0 | 0 | 91 | Existing domain suite executed; no full semantic claim | External callers/compatibility not exhaustively proven; PARTIAL |
| Documentation/certification | 0 | 0/0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Existing domain suite executed; no full semantic claim | No exhaustive certification asserted; PARTIAL |


## Reading this matrix

The totals refer only to the 2232-item baseline open queue, not every possible defect surface. Reviewed totals **41/2232**, with one reviewed G and **40 closed** within occurrence-level contracts. Aggregate A/B/C/D/E/F/G = **12/16/2/9/1/0/2192**. Remaining text inherited from M29 is a queue description, not a revalidated defect claim. It must be revisited, not used to assert a fixed defect still exists.

The JSON ledger contains concrete tests/callers/contracts for reviewed rows. Existing test modules for each of the 69 domains are enumerated in the original domain matrix; execution of those modules is not a substitute for a complete M30 semantic review. Zero selected inventory rows is not NOT-APPLICABLE or PASS.

### Evidence closure by layer

- **Source verification:** PASS for the recorded final source gate, compile, critical lint, declared lock and installed-wheel smoke.
- **Selected scenario regressions:** PASS within their described boundaries; see A–T in M30_SEMANTIC_AUDIT.md.
- **Exhaustive semantic review:** NOT-RUN to completion; 2191 items unreviewed, one additional reviewed item unresolved.
- **Per-field UI/HTML/PDF/Excel/JSON parity:** NOT-RUN to completion. Existing export tests and fixture-specific round trips are not a completed parity matrix.
- **All Plan/Actual/Forecast/Target combinations:** scalar and persisted eleven-pair Plan/Actual tests PASS; all other consumers/pairings NOT-RUN to closure.
- **All engineering engines:** registered-engine regressions ran; every input/persistence/snapshot/UI/export path NOT-RUN to closure.
- **All financial subdomains:** targeted currency/missing/derived overflow checks PASS; complete assumptions, payroll/taxes/insurance/CAPEX/revenue/payback/NPV/IRR tracing NOT-RUN to closure.
- **Native GUI/Windows installer:** EXTERNAL-BLOCKED/NOT-RUN. Offscreen with stubs is a limited substitute, not native acceptance.
- **Real MinerU PDF:** EXTERNAL-BLOCKED; actual opt-in attempt failed for missing/disabled MinerU, rather than being converted to a passing skip.

`PARTIAL` is a review-completeness label, not a test result. Test statuses use PASS, FAIL, NOT-RUN, EXTERNAL-BLOCKED, OPTIONAL-SKIPPED or NOT-APPLICABLE as applicable. No domain receives a blanket PASS here.

## Domain-specific source and regression references

References identify executed modules and future review surface, not proof of all assertions.

| Domain | Source modules | Existing regression modules |
|---|---|---|
| Git lineage/recovery | `core/database.py` | `tests/test_release_gate_integrity.py` |
| Canonical model registry | `core/database.py` | `tests/test_canonical_schema.py`, `tests/test_canonical_schema_expanded.py` |
| Wellbore ownership | `core/database.py` | `tests/test_wellbore_ownership_integrity.py` |
| Section ownership | `core/database.py` | `tests/test_m29_release_closure.py` |
| Report ownership | `core/database.py` | `tests/test_report_scoped_ownership_m26.py` |
| Parent reassignment | `core/database.py` | `tests/test_ownership_parent_edits.py` |
| Startup/migration | `core/database.py` | `tests/test_wellbore_schema_v3.py` |
| Scope attribution | `core/scope_attribution.py` | `tests/test_scope_attribution.py` |
| Company/project/well hierarchy | `core/hierarchy_operations.py`, `dialogs/hierarchy_dialogs.py` | `tests/test_hierarchy_updated_at.py` |
| Daily report lifecycle | `core/repositories/report_repository.py`, `tabs/w2_Daily_Report.py` | `tests/test_report_lifecycle.py` |
| Revision snapshots | `core/database.py`, `core/report_snapshot.py` | `tests/test_report_snapshot.py` |
| Next-day carry-forward | `core/hierarchy_operations.py`, `tabs/w2_Daily_Report.py` | `tests/test_m29_release_closure.py` |
| Credentials/bootstrap | `app.py`, `core/credential_policy.py`, `core/database.py` | `tests/test_credential_lifecycle.py` |
| Permissions/W8 | `core/permissions.py`, `tabs/w8_Safety_Widget.py` | `tests/test_p0_permissions.py` |
| Backup/restore | `core/database.py`, `main_window.py` | `tests/test_m28_finance_safety_plan.py` |
| Currency/NULL reducers | `core/cost_semantics.py` | `tests/test_cost_truth_boundary.py` |
| Daily cost/OPEX | `core/repositories/cost_repository.py`, `tabs/w16_Cost_Management.py` | `tests/test_cost_management_widget_smoke.py` |
| CAPEX/revenue | `core/cost_semantics.py`, `core/database.py` | `tests/test_m28_finance_safety_plan.py` |
| Payroll/insurance/tax | `core/cost_semantics.py`, `core/database.py` | `tests/test_cost_truth_boundary.py` |
| Fuel/maintenance/overhead | `core/cost_semantics.py`, `tabs/w7_logistics_Widget.py` | `tests/test_fuel_water_truth.py` |
| Standby/moving | `core/cost_semantics.py`, `core/operational_time.py` | `tests/test_operational_time_integrity.py` |
| Economic assumptions/IRR | `core/cost_semantics.py`, `tabs/w12_Analysis.py` | `tests/test_m28_finance_safety_plan.py` |
| W16 cost scope | `tabs/w16_Cost_Management.py` | `tests/test_cost_management_widget_smoke.py` |
| Plan scalar/11-pair matrix | `core/actual_vs_plan.py` | `tests/test_m29_release_closure.py` |
| Well plan revision/persistence | `dialogs/planning_dialog.py`, `tabs/w10_Planning_Widget.py` | `tests/test_planning_material_persistence.py` |
| Material identity/W10 | `core/database.py`, `tabs/w10_Planning_Widget.py` | `tests/test_planning_material_persistence.py` |
| NPT/W10 | `core/operational_time.py`, `tabs/w10_Planning_Widget.py` | `tests/test_m29_release_closure.py` |
| W10 code/status charts | `tabs/w10_Planning_Widget.py` | `tests/test_m29_planning_ui.py` |
| W10 drilling/mud summaries | `tabs/w10_Planning_Widget.py` | `tests/test_m29_planning_ui.py` |
| W10 milestones | `core/actual_vs_plan.py`, `tabs/w10_Planning_Widget.py` | `tests/test_w12_milestones_m25.py` |
| W12 shared KPI scope | `core/operations_intelligence.py`, `tabs/w12_Analysis.py` | `tests/test_kpi_parity.py` |
| W12 today/unique selection | `tabs/w12_Analysis.py` | `tests/test_w12_scope_leakage_m25.py` |
| W12 time-depth/calendar | `tabs/w12_Analysis.py` | `tests/test_m29_release_closure.py` |
| W12 ROP prediction | `tabs/w12_Analysis.py` | `tests/test_m29_release_closure.py` |
| W12 NPT forecast | `tabs/w12_Analysis.py` | `tests/test_w12_analytics_truth.py` |
| W12 cost analysis | `core/cost_semantics.py`, `tabs/w12_Analysis.py` | `tests/test_m28_finance_safety_plan.py` |
| W12 risk | `core/operations_intelligence.py`, `tabs/w12_Analysis.py` | `tests/test_w12_risk_assessment_m26.py` |
| W12 plan/quality/milestones | `core/actual_vs_plan.py`, `tabs/w12_Analysis.py` | `tests/test_w12_milestones_m25.py` |
| W11/export/report scope | `core/report_engine.py`, `tabs/w11_Export.py` | `tests/test_report_scope_metadata_m25.py` |
| Report history/selection | `core/selection_manager.py`, `dialogs/report_history_dialog.py` | `tests/test_report_history_ui.py` |
| Safety | `core/safety_semantics.py`, `tabs/w8_Safety_Widget.py` | `tests/test_m28_finance_safety_plan.py` |
| Trip sheet/W6 | `tabs/w6_Trajectory_Widget.py` | `tests/test_m29_planning_ui.py` |
| Logistics/personnel/transport | `core/database.py`, `tabs/w7_logistics_Widget.py` | `tests/test_w7_null_zero_semantics.py` |
| Inventory/bulk/fuel stock | `core/database.py`, `tabs/w9_Services_Widget.py` | `tests/test_inventory_zero_semantics.py` |
| Engineering facade/result | `core/engineering/core.py`, `core/engineering/registry.py`, `core/engineering/result.py` | `tests/test_engineering_data_semantics.py` |
| Trajectory/MCM | `core/engineering/engines/trajectory.py`, `tabs/w6_Trajectory_Widget.py` | `tests/test_trajectory_mcm_parity.py` |
| Anti-collision | `core/engineering/engines/anti_collision.py`, `tabs/w13_Engineering_Calculator.py` | `tests/test_anti_collision_engine.py` |
| Hydraulics/nozzle/bit | `core/engineering/engines/bit_performance.py`, `core/hydraulics_engine.py` | `tests/test_nozzle_optimization.py` |
| Casing | `core/engineering/casing_persistence.py`, `core/engineering/engines/casing.py` | `tests/test_casing_cross_process.py`, `tests/test_casing_history_viewmodel.py`, `tests/test_casing_persistence.py` |
| Cement | `core/engineering/cement_persistence.py`, `core/engineering/engines/cement.py` | `tests/test_cement_cross_process.py`, `tests/test_cement_history_viewmodel.py`, `tests/test_cement_persistence.py`, `tests/test_cement_save_widget_smoke.py` |
| MSE | `core/engineering/engines/mse.py`, `core/engineering/mse_persistence.py` | `tests/test_mse_cross_process.py`, `tests/test_mse_history_viewmodel.py`, `tests/test_mse_persistence.py`, `tests/test_mse_save_widget_smoke.py` |
| Mud volume | `core/engineering/engines/mud_volume.py`, `core/engineering/mud_volume_persistence.py` | `tests/test_mud_volume_cross_process.py`, `tests/test_mud_volume_history_viewmodel.py`, `tests/test_mud_volume_persistence.py`, `tests/test_mud_volume_save_widget_smoke.py` |
| Torque/drag | `core/engineering/engines/torque_drag.py`, `core/engineering/torque_drag_persistence.py` | `tests/test_torque_drag_history.py`, `tests/test_torque_drag_history_widget_smoke.py`, `tests/test_torque_drag_persistence.py`, `tests/test_torque_drag_save_widget_smoke.py` |
| Well control/kill sheet | `core/engineering/well_control_kill_sheet.py`, `core/engineering/well_control_kill_sheet_persistence.py` | `tests/test_well_control_icp_fcp_consolidation.py`, `tests/test_well_control_kill_sheet.py`, `tests/test_well_control_kill_sheet_cross_process.py`, `tests/test_well_control_kill_sheet_history_viewmodel.py`, `tests/test_well_control_kill_sheet_persistence.py`, `tests/test_well_control_kill_sheet_save_widget_smoke.py` |
| DrillPipe catalog/import | `core/engineering/drill_pipe_import.py`, `core/repositories/drill_pipe_reference_repository.py` | `tests/test_drill_pipe_catalog_view.py`, `tests/test_drill_pipe_catalog_widget_smoke.py`, `tests/test_drill_pipe_import.py`, `tests/test_drill_pipe_reference_repository.py`, `tests/test_drill_pipe_spec.py` |
| Schematic | `core/wellbore_schematic_engine.py` | `tests/test_schematic_no_fabrication.py` |
| Excel raw/normalization | `core/excel_normalizer.py`, `core/value_normalizer.py` | `tests/test_excel_intelligence.py`, `tests/test_excel_intelligence_regressions.py` |
| DDR atomic persistence | `core/canonical_schema.py`, `core/ddr_import_service.py` | `tests/test_ddr_save_atomicity.py` |
| Template learning/mapping | `core/mapping_store.py`, `dialogs/smart_template_dialog.py` | `tests/test_m29_release_closure.py` |
| PDF/MinerU | `core/document_import.py`, `core/mineru_engine.py` | `tests/test_mineru_engine.py` |
| JSON/copy independence | `core/mapping_store.py`, `core/report_snapshot.py` | `tests/test_m29_release_closure.py` |
| Export failure semantics | `core/ddr_pdf_export.py`, `core/professional_export.py`, `tabs/w10_Planning_Widget.py` | `tests/test_m29_release_closure.py` |
| Gate/accounting | `verify_release.py` | `tests/test_release_gate_integrity.py` |
| Wheel/resources | `packaging/DrillMaster.spec`, `packaging/package_smoke.py`, `pyproject.toml` | `tests/test_packaging_smoke.py` |
| Dependency reproducibility | `requirements-build.txt`, `requirements-lock.txt` | `tests/test_release.py`, `tests/test_release_gate_and_w13.py`, `tests/test_release_gate_integrity.py`, `tests/test_release_smoke.py` |
| CI/release workflow | `.github/workflows/ci.yml` | `tests/test_release_gate_integrity.py` |
| Security/user-data paths | `core/credential_policy.py`, `core/runtime_config.py` | `tests/test_credential_lifecycle.py` |
| Legacy/duplicate modules | `core/db_models.py`, `core/db_services.py` | `tests/test_single_source_guard.py` |
| Documentation/certification | `DEPLOYMENT.md`, `PRODUCTION_READINESS.md`, `README.md`, `TESTING.md` | `tests/test_release.py`, `tests/test_release_gate_and_w13.py`, `tests/test_release_gate_integrity.py`, `tests/test_release_smoke.py` |
