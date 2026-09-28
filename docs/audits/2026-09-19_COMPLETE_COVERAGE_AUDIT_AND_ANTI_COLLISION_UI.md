# Complete-Coverage Calculation Audit + Anti-Collision UI Functionalization

Date: 2026-09-19
Branch: `arena/01a085e0-drill-master`
Scope: Repository-wide inventory of every real engineering calculation, its UI
reachability, and closing the one remaining human-UI gap (Anti-Collision).

---

## A. Method

The repository is the sole source of truth. Every claim below was verified
directly against source, the call graph, tests, and a runtime smoke of the W13
`EngineeringCalculatorTab`. No engineering formula was written, changed, or
invented. No generic calculation framework was introduced. The only change is a
new **UI entry point that delegates to the already-canonical engine** via the
existing `CalculatorBridge`.

---

## B. Master Calculation Inventory (engines under `core/engineering/engines/` + `core/hydraulics_engine.py`)

| Engine | SCOPE (self-declared) | Key methods | UI reach (human) | Other reach | Classification |
|---|---|---|---|---|---|
| `AdvancedHydraulicsEngine` (`core/hydraulics_engine.py`) | (calc) | `calculate`, `calc_bit_hydraulics`, `optimize_nozzles`, `calc_surge_swab`, `calc_pump_output*`, TFA/HSI/impact | W13 Hydraulics + Bit Hydraulics + Nozzle/TFA tabs | — | **FUNCTIONAL** |
| `TorqueDragEngine` (`torque_drag.py`) | PARTIAL (Johancsik soft-string) | `calculate`, `calculate_weight_card`, `buoyancy_factor`, `casing_landing_load` | W13 Weight tab (persisted T&D) | — | **FUNCTIONAL+PERSISTED** |
| `CasingEngine` (`casing.py`) | PARTIAL (API TR 5C3 subset) | `burst`, `collapse`, `collapse_combined`, `triaxial_vme`, `tensile`, `evaluate` | W13 CSG/CMT → Casing Strength (persisted) | — | **FUNCTIONAL+PERSISTED** |
| `CementEngine` (`cement.py`) | COMPLETE | `displacement`, `toc_from_volume`, `hydrostatic_column`, `job_volumes` | W13 CSG/CMT → Cement Volume (persisted) | — | **FUNCTIONAL+PERSISTED** |
| `WellControlEngine` (`well_control.py`) | (IWCF/IADC) | `kill_mw`, `maasp`, `icp`, `fcp`, `kick_tolerance`, `trip_margin`, `formation_pressure`, `kick_volume`, `eaton_fracture_gradient`, `influx_type` | W13 Well Control tabs (Full Kill Sheet persisted); Quick Estimate dialog transient | AI-tools/bridge | **FUNCTIONAL+PERSISTED** (Kill Sheet) / **FUNCTIONAL-TRANSIENT** (Quick Estimate) |
| `MSEEngine` (`mse.py`) | COMPLETE (Teale 1965) | `calculate` | W13 Bit Hydraulics → MSE (persisted, decoupled from nozzles) | — | **FUNCTIONAL+PERSISTED** |
| `MudVolumeEngine` (`mud_volume.py`) | COMPLETE | `balance` (persisted), `weight_up`, `dilution`, `mix` (displayed) | W13 Mud → Volume Balance (persisted) + WDM tab | reports | **FUNCTIONAL+PERSISTED** |
| `BitPerformanceEngine` (`bit_performance.py`) | COMPLETE | `from_run`, `from_daily_params`, `weighted_rop`, `rollup`, `d_exponent(_corrected)`, `cost_per_foot` | W13 Bit econ (cost/ft) + Pore-Press (dc-exp); w12 Analysis (dc-exp, cost/ft) | `report_engine.py`, `operations_intelligence.py`, `managers.py` (roll-up KPIs) | **FUNCTIONAL** |
| `TrajectoryCalculator`/`TrajectoryEngine` (`trajectory.py`, `core.py`) | (min curvature) | `calculate` | W13 Directional → Multi-Survey | Anti-Collision recompute | **FUNCTIONAL** |
| `FishingEngine` (`fishing.py`) | PARTIAL/SCREENING | `free_point`, `string_stretch`, `adjusted_weight`, `backoff_depth`, `jar_operating_range`, `overshot_fit` | W13 Fishing + Stuck Pipe tabs | — | **FUNCTIONAL** |
| `AntiCollisionEngine` (`anti_collision.py`) | PARTIAL/SCREENING | `screen_clearance` (+ legacy `calculate_clearance`) | **NONE (before this change)** | AI-tools/bridge only | **NOT-READY-UI → now FUNCTIONAL-TRANSIENT** |

### Duplicate / legacy forensics
- No duplicate engineering implementations found. `DrillingCalculationEngine`
  in W13 is a pure delegation facade (documented, no formulas).
- `AntiCollisionEngine.calculate_clearance` / `calculate_with_welleng` are
  legacy dict-returning wrappers around the canonical `screen_clearance`;
  retained for existing AI/export callers (LEGACY-COMPAT, not a second impl).

---

## C. The single gap

Every mature engine had a human-facing UI entry point **except**
`AntiCollisionEngine`. Its only reach was `core/ai_tools.py` →
`CalculatorBridge.anti_collision` → `AntiCollisionEngine.screen_clearance`.
A drilling engineer using the W13 calculator could not run well-to-well
separation screening.

This qualifies for Wave-3 functionalization: the engine exists, is verified
(6 tests in `test_anti_collision_engine.py`), has a complete and honest input
contract (`REQUIRED_INPUTS`), and emits transparent, correctly-labelled
screening output.

---

## D. Change made (production-grade vertical slice)

Added an **"🚧 Anti-Collision"** sub-tab under W13 → Directional
(`tabs/w13_Engineering_Calculator.py`):

- **Reference well** = the existing Multi-Survey trajectory (`self.dd_surveys`),
  already computed with canonical minimum curvature. No duplicate survey model.
- **Offset well** = a second survey table on the tab, positions computed with
  the same canonical `TrajectoryEngine.calculate` (min curvature) — one
  authoritative trajectory implementation, reused.
- **Screening** delegates to `CalculatorBridge.anti_collision(...)` →
  `AntiCollisionEngine.screen_clearance(...)`. **No engineering logic in the
  UI** (asserted by the smoke test via `inspect.getsource`).
- **Result completeness (§27):** closest approach (distance + ref/offset MD),
  clearance (only when both wellbore radii supplied), separation factor (only
  when supplied σ present), full per-MD separation table with convergence trend,
  and the collision-scan verdict when a threshold is given.
- **Validation visibility (§29):** distinct states — `MISSING_INPUT` for
  reference (<2 pts) vs offset (<2 pts), and `ENGINE_FAILED: <error>` for engine
  rejection — never collapsed to a generic "failed".
- **Reference/scope honesty (§37):** a permanent banner plus surfaced engine
  warnings state SCREENING ONLY / no ISCWSA / no covariance / no tool-error
  model. No fabricated authority.

### Persistence decision (§4/§32) — deliberately NOT persisted
Anti-Collision is `PARTIAL/SCREENING`. Persisting a screening number as a
saved "calculation of record" would imply ISCWSA-grade authority it explicitly
does not have. It is therefore **FUNCTIONAL-BUT-TRANSIENT-BY-DESIGN**, matching
the Well Control *Quick Estimate* precedent. The persisted set remains **6**
(T&D, Casing, Cement, Kill Sheet, MSE, Mud Volume).

---

## E. No-change items (verified already correct)
- MSE decoupling from bit hydraulics still holds (Mission 10).
- Well Control dual-path (Full Kill Sheet persisted vs Quick Estimate transient)
  intact; ICP/FCP single-owner preserved.
- Bit Performance roll-up methods are genuinely functional through the reporting
  and operations-intelligence paths — not test-only; no new UI needed.
- No new dependency added; no viz framework; shared core remains
  `calculation_verification.py` only.

---

## F. Tests
- New: `tests/test_anti_collision_widget_smoke.py` — subprocess-isolated W13
  smoke driving the real handlers end-to-end (missing-input guards, min-curvature
  offset recompute, screening with radii + threshold, warning surfacing,
  bridge-delegation assertion).
- Existing `tests/test_anti_collision_engine.py` (6) unchanged and green.
- Full suite: green (see commit).

---

## G. Verdict
**CERTIFIED-WITH-DOCUMENTED-DEBT.** All mature engines are now reachable from
the human UI. Remaining declared debt is intentional and documented:
Anti-Collision is a screening tool (transient by design), and its engine remains
`PARTIAL/SCREENING` pending a full ISCWSA error model — which is an engineering
model expansion, out of scope for a UI-coverage pass and correctly not faked.
