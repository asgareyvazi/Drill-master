# DrillMaster Engineering Capability Status

> **Capability scope reference:** labels below are bounded implementation claims, not production/operator acceptance. Current repository and release status: [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

The labels below are a conservative capability-scope reference, not a branch
identity or production-acceptance claim. Their original verification occurred
on `arena/01a0c945-drill-master` and its predecessor `arena/01a07094-drill-master`;
those names are historical. For a current calculation, the checked-out engine
and its returned `EngineeringResult.scope` are authoritative. Current release
and acceptance status is maintained in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

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

## M43 engineering review (2026-10-21)

**Defect fixed: casing VME capped-end stress.** `CasingEngine.triaxial_vme`
divided the end-cap term `pi*ri^2 - pe*ro^2` by the wall area `pi*(ro^2 - ri^2)`,
so the capped-end axial stress was understated by a factor of pi (x0.318). It is
now `(pi*ri^2 - pe*ro^2) / (ro^2 - ri^2)`, the end-cap force balance over the wall
area. Reproducible example: 9-5/8 in OD, 8.681 in ID, 80 ksi, 3,000 psi internal,
no external pressure or tension gives a capped-end stress of 13,082.6 psi (formerly
4,164 psi), hoop 29,165.3 psi, VME 27,855.9 psi, utilization 0.3482. The previous
ground-truth test copied the engine's expression; it now checks the force balance
and a thin-wall bound, and fails on the old code. `CasingEngine.METHOD` gained
`capped-end r2`, so saved casing calculations made before the fix verify as
`DIFFERENT` with `method_matches=False` instead of silently reproducing.
Limits: elastic Lamé stresses at the inner wall only; no temperature, wear,
bending, connection VME or ISO 10400 design envelope; a screening check, not
complete casing integrity.

**Non-finite inputs:** `tests/test_engineering_non_finite_contract.py` probes
42 public numeric engine entry points with NaN/inf (244 calls). 208 return a
failure flag and 18 raise. 18 are allowlisted with a reason: the legacy fishing
float wrappers, which only tests call, and `fyax`, whose only caller validates
its inputs.

**Not supported (no formula added in M43):**
- Stiff-string torque and drag: `TorqueDragEngine` is soft-string only.
- Pressure-area (closed-end) buoyancy: buoyancy is `BF = 1 - MW/65.5`; T&D
  results and W13 state this assumption.
- ISCWSA error models: anti-collision returns `iscwsa_compliant=False`. Optional
  `welleng` integration is a benchmark item, not a claim.

Adding any of these needs a cited source with its edition, a reproducible example
and stated limits.
