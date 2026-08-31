# Engineering architecture (audit)

**Date:** 2026-08-31  
**Rule:** ONE ENGINE → ONE FORMULA → ONE RESULT  
UI and AI tools call engines. They must not re-implement the same formula. Missing inputs return `MISSING_INPUT`; they are not defaulted.

## Result contract

Every engine returns `EngineeringResult` (`core/engineering/result.py`):

`success`, `value`, `values`, `unit`, `formula`, `method`, `assumptions`, `warnings`, `validation_status`, `metadata`, `error`, `scope`.

`scope`: `COMPLETE` | `PARTIAL` | `SCREENING` | `NOT_IMPLEMENTED`.

`CalculationResult` in `core/engineering/core.py` is a backward-compatible alias.

## Call path

```
Tab / AI tool
    → CalculatorBridge  (core/engineering/bridge.py)
    → Engine            (core/engineering/engines/* or core.py Trajectory/Bit/Hydraulics)
    → EngineeringResult
```

`DrillingManager` (`core/managers.py`) is a thin façade for DDR tabs (TFA, ROP, HSI, AV). It contains no independent formulas.

## Status (honest)

| Capability | Engine | Formula | Scope | Status |
|---|---|---|---|---|
| Kick tolerance | `WellControlEngine` | IWCF: MAASP, remaining, H, Boyle, min(V_BHA, V_bottom) | COMPLETE (single-bubble, no T/z) | ✅ |
| Trip margin | `WellControlEngine` | MW − PP_EMW; psi = 0.052×TM×TVD | COMPLETE | ✅ |
| Kick volume | `WellControlEngine` | pit gain / annular capacity | COMPLETE | ✅ |
| Kill MW / MAASP | `WellControlEngine` | KMW = MW + SIDPP/(0.052×TVD); MAASP = (Frac−MW)×0.052×shoe | COMPLETE | ✅ |
| Trajectory MCM | `TrajectoryEngine` | Minimum Curvature, first station, VS, `project_ahead` | COMPLETE | ✅ |
| MSE | `MSEEngine` | Teale: WOB/Ab + (120π·RPM·T)/(Ab·ROP) | COMPLETE | ✅ |
| Mud volume | `MudVolumeEngine` | mass/volume balance, weight-up, dilution, mix | COMPLETE | ✅ |
| Bit / section from DDR | `BitPerformanceEngine` | footage, ROP, optional Teale MSE | COMPLETE | ✅ |
| Casing burst/collapse/tension | `CasingEngine` | Barlow 0.875 + four-regime + fyax + Pi correction + inner-wall VME; optional user connection ratings | PARTIAL (pipe-body; not full TR 5C3) | 🟠 |
| Cement volumes / hydrostatic | `CementEngine` | D²/1029.4 volumes, spacer/lead/tail, stacked 0.052 MW TVD, pump time | COMPLETE as worksheet; not lab design | ✅ worksheet / 🔴 lab |
| Torque & drag | `TorqueDragEngine` | Johancsik + Dawson-Paslay/Chen flags + stretch/twist/NP/side force | PARTIAL / SCREENING | 🟠 |
| welleng | adapters | **Benchmark only** — not the production backend | SCREENING | 🟠 |
| Full API TR 5C3 (triaxial, connections, temp) | — | not implemented | NOT_IMPLEMENTED | 🔴 |
| Cement job design (lab, UCA, gas migration) | — | not implemented | NOT_IMPLEMENTED | 🔴 |
| Production T&D (stiff-string, contact, dynamics) | — | not implemented | NOT_IMPLEMENTED | 🔴 |
| Anti-collision ISCWSA | `AntiCollisionEngine` | Euclidean screening only | PARTIAL | 🔴 do not expand this audit |

## Kick tolerance (IWCF)

Required: MW, shoe TVD, current TVD, frac MW **or** LOT, **influx gradient** (not defaulted to 0.1 psi/ft).  
Optional: formation EMW, DP/OH capacity, BHA capacity/length.

Ground truth (tests): LOT/frac 16 ppg, MW 14.5, shoe 6000 ft, TD 10000 ft, formation 15.0 ppg, gas 0.1 psi/ft, cap_BHA 0.0226, cap_DP 0.0459 → MAASP 468 psi, KI 0.5 ppg, remaining 208 psi, H ≈ 318 ft, V_BHA 7.2 bbl, V_bottom 9.34 bbl, **KT = 7.2 bbl**.

## Trajectory

- First station without `tie_on`: N = E = 0, TVD = MD × cos(inc). MD = 0 → TVD = 0.
- With `tie_on`: {tvd, north, east} applied to the first station.
- VS = N·cos(vs_azi) + E·sin(vs_azi) at **every** station, including `project_ahead`.
- DLS default unit: deg/30m.
- `tabs/w6_Trajectory_Widget.py` and calculator directional tab call `TrajectoryEngine`.

## Casing (PARTIAL — pipe-body combined loads)

Do **not** claim full API TR 5C3. Implemented: Barlow 0.875, four-regime collapse, pipe-body tensile, fyax biaxial reduction, Pc′ = Pc + Pi(1−2t/D), inner-wall Lamé VME. Connection ratings are used only if the user supplies them (never invented). Not implemented: published connection tables, temperature-yield tables, wear, full ISO 10400 envelopes.

9-5/8 in, t = 0.472 in, N80: burst ≈ 6866 psi (Barlow 0.875). fyax at z=0.5 → 0.6514 Yp.

## Cement (COMPLETE worksheet, not lab design)

Job-volume / stacked-hydrostatic worksheet: annulus + excess + shoe track + spacer, optional lead/tail sacks from **user yield**, H = Σ 0.052 MW TVD (layer TVD required). Not UCA, thickening time, centralization FEM, or gas-migration design.

## Torque & drag (SCREENING)

Johancsik soft-string. Label: **PARTIAL / SCREENING MODEL**. Not production-ready. Simple buoyancy BF = 1 − MW/65.5. Dawson-Paslay sinusoidal and Chen helical flags use **local** slackoff compression and inclination; they do not change hookload. Stretch Σ F L / AE, twist Σ T L / JG, side-force profile, slackoff neutral point. welleng / torque_drag packages are optional benchmarks, never a silent backend.

Vertical GT: 10 000 ft × 19.5 ppf, MW 10 ppg → BF ≈ 0.8473, buoyed ≈ 165.23 klbf.

## MSE

120π (≈ 376.99), not the 480 spreadsheet constant.

## Multi-company mapping

New company = JSON in `config/company_templates/`. No per-company Python. OEOC DDR labels map through `oeoc.json` into existing tabs. There is **no** checked-in binary OEOC workbook in this repo; mapping is validated against the template, not against a private DDR file.

## UI wiring

| Surface | Formula owner |
|---|---|
| w13 calculator KT / trip margin / casing / cement / MCM / mud mix | engines via `DrillingCalculationEngine` wrappers |
| w13 bit MSE / HSI | `MSEEngine` / `BitEngine` |
| w6 survey Calculate | `TrajectoryEngine` |
| w3 DDR TFA / ROP / HSI / AV | `DrillingManager` → engines |
| w3 mud volumes | `MudVolumeEngine` |
| AI tools | `CalculatorBridge` |

Remaining calculator sub-tools (surge/swab Bingham, nozzle optimisation, fishing, pump output) are **legacy UI helpers**, not claimed as the canonical engineering core. Do not treat them as a second engine.

## Tests

- `tests/test_p0_engineering_core.py` — existing contracts
- `tests/test_engineering_ground_truth.py` — numeric GT for KT, TM, MCM, burst, MSE, T&D, mapping, AI tools

Test count is not evidence of correctness. Ground-truth numbers are.

## Do not

- Start Anti-Collision / 3D / new cement-design / production T&D features until this audit stays clean.
- Call T&D or casing “production ready” or “full API TR 5C3”.
- Invent influx gradient, friction factor, hole size, or additive density.
