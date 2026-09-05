# DrillMaster Engineering Capability Status

Status verified against `arena/01a07094-drill-master` after the Engineering
Capability Completion work. `EngineeringResult.scope` is authoritative for
runtime calculations.

| Domain | Status | Canonical implementation | Methodology and limitations |
|---|---|---|---|
| Anti-collision | PARTIAL / SCREENING | `core/engineering/engines/anti_collision.py` | Linear common-MD interpolation, 3D centerline separation, continuous piecewise closest approach, optional wellbore-radius clearance, convergence indicators, threshold collision scan, and supplied-axis RSS uncertainty. No ISCWSA error model, covariance propagation, magnetic model, or survey-tool error model. |
| Torque & Drag | PARTIAL / SCREENING | `TorqueDragEngine` | Johancsik soft-string axial/torque screening with buoyancy, friction, pickup, slack-off, rotating torque, stretch, neutral point and buckling flags. No bending/contact stiffness, tortuosity reconstruction, or dynamics. |
| Casing | PARTIAL | `CasingEngine` | Pipe-body burst, four-regime collapse, axial tension, combined collapse, inner-wall VME and optional connection/load governing limits. Not a complete API TR 5C3/connection catalogue implementation. |
| Cement | COMPLETE worksheet / PARTIAL design | `CementEngine` | Hole/annular volume, excess, casing capacity, lead/tail legs, spacer, displacement, TOC, hydrostatic stack and slurry balance. Laboratory slurry design, thickening time, UCA, centralization and gas migration are unsupported. |
| Fishing / stuck pipe | PARTIAL / SCREENING | `FishingEngine` | Free point, string stretch, back-off depth with propagated modulus, jar range, adjusted weight and overshot fit. Pull limits and field-certified stuck-pipe prognosis require additional pipe/tool and operational inputs. |
| Well control | COMPLETE calculation kit | `WellControlEngine` | Kill MW, MAASP, fracture gradient, trip margin, kick tolerance/height/volume, influx type and formation pressure. Required fracture, influx and formation inputs are explicit; no silent gradients. |
| Trajectory / directional | COMPLETE MCM core | `TrajectoryEngine` | Minimum curvature TVD/North/East/VS/HD/DLS, build/turn, closure and project-ahead with validation and parity tests. Uncertainty is outside this engine. |
| Mud engineering | COMPLETE for implemented deterministic kit | `MudVolumeEngine`, `MudEngineering`, `HydraulicsEngine` | PV/YP, AV, ECD, annular velocity, balance, dilution, weight-up, mixing, MBT, LSRYP, excess lime, corrosion and slug calculations where inputs support them. No invented laboratory properties. |
| Bit / MSE / performance | COMPLETE for implemented kit | `BitPerformanceEngine`, `MSEEngine`, `AdvancedHydraulicsEngine` | ROP/run rollups, d-exponent, corrected d-exponent, MSE, cost/ft, bit hydraulics, TFA, HSI, jet velocity, impact force and pump output. Results depend on supplied field data. |
| Actual vs plan | PARTIAL / DATA-DEPENDENT | `core/actual_vs_plan.py`, database reporting | Explicit depth, hours, ROP, NPT and cost comparisons only when both plan and actual values exist. Missing metrics are reported, not estimated. |
| Cost / economics | PARTIAL | `BitPerformanceEngine.cost_per_foot`, cost records and W16 views | Deterministic bit cost/ft and stored planned/actual cost comparisons. No AFE forecasting, escalation, NPV or full economic model. |

## Integration rules

- UI and AI paths delegate to canonical engines or `CalculatorBridge`.
- Engine results use `EngineeringResult`; legacy dict/float facades remain only
  for backward compatibility.
- Anti-collision output explicitly sets `iscwsa_compliant=False`.
- Screening methods are not field-certified or standards-compliant claims.
- Optional external packages are never a silent calculation backend.

## Test evidence

Ground-truth and integration coverage is distributed across:

- `tests/test_anti_collision_engine.py`
- `tests/test_engineering_ground_truth.py`
- `tests/test_engineering_integrations.py`
- `tests/test_engineering_completion.py`
- `tests/test_single_source_guard.py`
- `tests/test_trajectory_mcm_parity.py`
- W13 delegation and headless acceptance tests

The release gate reports the live collection and execution population; test
counts are intentionally not hard-coded in this document.
