# Engineering Reference Repository Matrix

> Updated: 2026-09-05 — verified against branch `arena/01a05747-drill-master`
> at HEAD `95fff1c` (engineering-refactor work in progress on top of it).
> Status legend:
> - **Integrated** — real code path in DrillMaster maps to a capability of the
>   repository (formulas/tests traceable to a DrillMaster module).
> - **Already implemented / equivalent** — DrillMaster has its own verified
>   implementation of the same capability (no code was copied; equivalence was
>   validated numerically where possible).
> - **Inspected but rejected** — reviewed; nothing integrable (duplicate,
>   unverified, or prototype-only).
> - **Not applicable** — domain outside DrillMaster's architecture.

| # | Repository | Area | Status | DrillMaster mapping / evidence |
|---|-----------|------|--------|-------------------------------|
| 1 | `jonnymaserati/welleng` | Trajectory, anti-collision, error models | Already implemented / equivalent (knowledge source) | `core/engineering/engines/trajectory.py` and `anti_collision.py` state "welleng … as knowledge source, not copy". MCM re-implemented deterministically in `core/engineering/core.py TrajectoryEngine`. `calculate_with_welleng()` adapter exists but is optional — never a silent backend. |
| 2 | `BillyFrcs/DrillingEngineeringOperations` | C# hydraulics pressure-loss modules | Inspected but rejected | DrillMaster `core/hydraulics_engine.py` (Bingham / Power-Law / Herschel-Bulkley) is more complete and already canonical; C# module adds nothing. |
| 3 | `Kukuruza24110/well-engine` | React calc prototype, unverified formulas | Inspected but rejected | Prototype with "never fabricate" verification gate but no verified formulas; DrillMaster canonical engines already implement the same verification principle (`EngineeringResult` contracts). |
| 4 | `dasvan/engineering-calculations` | Mud weighting/dilution/mix, AV, pit volume, deviation | Already implemented / equivalent | `core/engineering/engines/mud_volume.py` (`weight_up` L99, `dilution` L137, `mix` L167) and `HydraulicsEngine.calculate_annular_velocity` (`core/engineering/core.py`). |
| 5 | `manjramkar/Drilling-Engineering` | Trajectory/DLS, drill-string stress, IPR | Already implemented / equivalent (subset) | Trajectory DLS via `TrajectoryEngine`; axial mechanics subset in `torque_drag.py`. IPR/Klinkenberg/drawdown not applicable (production engineering out of scope). |
| 6 | `Otto-Destiny/3d_well_trajectory_visualization` | 3D trajectory visualization | Already implemented / equivalent (math) | Trajectory math implemented in `TrajectoryEngine`/`TrajectoryCalculator`; 3-D viewer rejected (no new top-level tab per architecture rule). |
| 7 | `juangjuang74-eng/drilling-engineer-toolkit` | d-exponent, cost/ft, corrosion | Integrated (formula basis; its 1000-lbf variant rejected) | `core/engineering/engines/bit_performance.py`: `d_exponent` L177 (standard 10⁶ lbf Jorden–Shirley form), `d_exponent_corrected` L233, `cost_per_foot` L280. Toolkit's 1000-klbf variant rejected (unit-inconsistent); its full-cycle cost/ft form used. Consumed by W12 Performance tab (`update_dexponent_data`, `_update_cost_comparison`). |
| 8 | `mengyangcup/drilling_engineering_design` | Casing/hydraulics design course content | Already implemented / equivalent | Casing design (`core/engineering/engines/casing.py`: burst/collapse/combined/triaxial/tensile) and hydraulics engine cover the same ground with API/IWCF references. |
| 9 | `johnryan417/python-for-drilling-engineers` | Bit-run analysis pattern | Integrated (analysis pattern only — no unique formula) | W12 Performance bit-run analysis (d-exponent trend + cost/ft comparison) follows the same bit-run dataframe analysis pattern; all numbers come from DrillMaster engines + stored DB data, none from that repo. |
| 10 | `Himageo2006/mud-engineer-pro` | Pump output (triplex/duplex), Eaton FG, LSRYP, MBT, excess lime, corrosion, slug | Integrated | Triplex `calc_pump_output` L1030 and duplex `calc_pump_output_duplex` L1041 in `core/hydraulics_engine.py`; `eaton_fracture_gradient` L573 in `well_control.py`; `mbt_bentonite_equiv` L191, `lsryp` L210, `excess_lime_obm` L232, `corrosion_rate` L160, `slug_dry_length` L250 in `core/engineering/extended.py MudEngineering`; consumed by W13 Mud Lab tab. |
| 11 | `f0nzie/volve-drilling` | WITSML/R exchange workflows | Not applicable | DrillMaster ingests Excel DDRs (`dialogs/excel_import_dialog.py`, OEOC golden regression); no WITSML/R stack. |
| 12 | `jntran08/DataAnalyticsforEngineering` | ML-based geosteering | Not applicable | No ML stack in the application; no integration path without new architecture. |
| 13 | `ejbo2001/3D-directional-drilling-engine` | Vectorized Minimum Curvature | Already implemented / equivalent — numerically validated | `TrajectoryEngine.calculate` matches the reference MCM bit-for-bit (0.0 difference on TVD/North/East/DLS for the 4-station audit survey; same RF=(2/α)tan(α/2) and DLS=α·30/ΔMD). |

## Rule

**“Used” is only claimed when a code path or a numerically validated
equivalence exists in DrillMaster at the verified HEAD.** No repository above
was force-integrated; anything marked “rejected” or “not applicable” was
inspected and intentionally excluded.
