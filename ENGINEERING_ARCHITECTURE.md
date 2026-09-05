# DrillMaster — Engineering Architecture Documentation

> **Version:** 2.0 — verified against branch `arena/01a05747-drill-master`
> at HEAD `5f92841` (2026-09-05), full test suite `421 passed, 2 skipped`.

---

## 1. Design Principles

1. **Single source of truth (SSOT):** one canonical engine per engineering
   domain. UI tabs, dialogs, and local calculators never re-implement an
   engineering formula — they delegate.
2. **Deterministic:** published formulas from industry references (Bourgoyne
   et al., API RP, IWCF, SPE).
3. **Explicit contracts:** engines return `EngineeringResult`
   (`value/unit/warnings/assumptions/errors/metadata`); inputs missing raise
   `MissingInputError` instead of defaulting to invented values.
4. **Traceable:** results carry method + assumptions.
5. **Honest scope:** engines that are screening-grade declare
   `SCOPE = "PARTIAL / SCREENING …"` (torque & drag, anti-collision, fishing);
   nothing partial is labelled complete.
6. **Optional externals only:** welleng/torque_drag adapters exist, are
   runtime-detected by `registry.py`, and are never a silent backend.

---

## 2. Integration Chain

```
UI Tab / Dialog
    │  (pure delegation statics — no formulas, no unit constants other
    │   than m↔ft / pcf↔ppg conversions at the boundary)
    ▼
core/engineering/bridge.py            # service layer between UI and engines
    ▼
Canonical Engines
    ├── core/hydraulics_engine.py     # AdvancedHydraulicsEngine (bit ΔP/TFA/
    │                                 #   HHP/HSI/jet velocity/impact,
    │                                 #   pump output, capacities, …)
    ├── core/engineering/core.py      # TrajectoryEngine, BitEngine,
    │                                 #   HydraulicsEngine, WellControlEngine
    │                                 #   (compat), BHA/…, facade
    ├── core/engineering/engines/     # specialized engines (see catalog)
    └── core/engineering/extended.py  # MudEngineering (mud-lab kit)
    ▼
EngineeringResult (value/unit/warnings/assumptions/errors/metadata)
    ▼
UI display · DB · export
```

**Rule:** a formula constant (e.g. `10858`, `1029.4`, `1714`, `1930`,
`3.117`) appears once — in a canonical engine. Tests in
`tests/test_single_source_guard.py` enforce this and reject the legacy
`12031`-family constants anywhere in code.

---

## 3. Engine Catalog

### Canonical engines (HEAD)

| Engine | File | Scope / Status | Consumed by |
|--------|------|----------------|-------------|
| `TrajectoryEngine` (MCM, build/turn rate, project-ahead) | `core/engineering/core.py` + `engines/trajectory.py` | COMPLETE — MCM parity-tested vs independent textbook implementation (`tests/test_trajectory_mcm_parity.py`) | W13 facade, surveys |
| `AdvancedHydraulicsEngine` | `core/hydraulics_engine.py` | COMPLETE | W13 facade, dialogs, W15 |
| `WellControlEngine` | `core/engineering/core.py` + `engines/well_control.py` | COMPLETE (IWCF kit: kick tolerance, MAASP, kill MW, formation pressure, fracture gradient, kick volume) | W13 kill sheet, dialogs |
| `MudVolumeEngine` / `MudEngineering` | `engines/mud_volume.py` + `core/engineering/extended.py` | COMPLETE (weight-up, dilution, mixing, OWR, MBT, LSRYP, …) | W13 Mud Lab + facade |
| `CasingEngine` | `engines/casing.py` | COMPLETE (burst/collapse/VME/triaxial/tensile) | engineering dialogs |
| `CementEngine` | `engines/cement.py` | COMPLETE (volumes, displacement — capacity helpers delegated to `AdvancedHydraulicsEngine`) | w13/cement UI paths |
| `TorqueDragEngine` | `engines/torque_drag.py` | **PARTIAL / SCREENING** — soft-string; `calculate_with_welleng()` optional | W13 facade |
| `AntiCollisionEngine` | `engines/anti_collision.py` | **PARTIAL / SCREENING** — Euclidean clearance; ISCWSA full error model explicitly unsupported without welleng | (not wired to a tab) |
| `FishingEngine` | `engines/fishing.py` | **PARTIAL / SCREENING** — free point, stretch, jar range, overshot fit, back-off | W13 facade |
| `MSEEngine` | `engines/mse.py` | COMPLETE (Teale) | analysis UI |
| `BitPerformanceEngine` | `engines/bit_performance.py` | COMPLETE (d-exponent, dc, cost/ft, rollup, run analysis; torque klb.ft→ft·lbf at engine boundary) | W12 Analysis |
| `OperationsIntelligenceEngine`, `MudLedgerEngine`, `BHAEngine` | `core/engineering/core.py` | COMPLETE | analysis tabs |

### W13 Engineering Calculator

`tabs/w13_Engineering_Calculator.py` `DrillingCalculationEngine` is a facade:
22 static methods delegate 1:1 to the canonical engines above (pump output,
TFA, bit HHP, jet velocity, impact force, nozzle optimization, free point,
stretch, adjusted weight, buoyancy factor, casing landing load, kick
tolerance, formation pressure, build/turn rate, overshot fit, jar range,
back-off, mud weight-up/dilution/mix, OWR). No `12031` legacy constant, no
`1029.4`/`10858` duplication remains in the tab (guard-tested).

---

## 4. Result Contract

`core/engineering/result.py`:

```python
@dataclass
class EngineeringResult:
    success: bool
    value: float | Dict | None
    unit: str
    values: Dict[str, Any]
    method: str
    assumptions: List[str]
    warnings: List[str]
    errors: List[str]       # legacy: error (str) alias
    scope: str = ""         # "PARTIAL / SCREENING …" when not complete
    metadata: Dict[str, Any]
```

Engines keep legacy tuple/dict return compatibility only through documented
wrapper methods whose bodies delegate — no mixed return types inside a single
engine method.

---

## 5. Unit & constant policy

- Canonical constants live in engines: `10858` (bit ΔP), `1714` (HHP),
  `1930` (impact), `3.117` (jet velocity), `1029.4` (capacity), `0.052`
  (pressure gradient), `7.48` (pcf↔ppg).
- Unit conversions (m↔ft `3.28084`, pcf↔ppg `7.48`, klb.ft→ft·lbf `×1000`)
  happen once at the UI/DB boundary — never inside formulas.
- Torque is stored in DB in klb.ft and converted to ft·lbf once in
  `BitPerformanceEngine.from_daily_params`.

---

## 6. Error hierarchy & registry

```
EngineeringError
├── MissingInputError(field)
└── UnsupportedCalculationError(reason)
```

`core/engineering/registry.py` detects optional packages (welleng,
torque_drag, gekko, camelot, pytesseract) without blocking startup.

---

## 7. Testing

Full suite at HEAD: **421 passed, 2 skipped** (2026-09-05 run). Engineering
coverage includes `tests/test_p0_engineering_core.py`,
`test_engineering_ground_truth.py`, `test_engineering_integrations.py`,
`test_extended_engineering.py`, `test_nozzle_optimization.py`,
`test_trajectory_mcm_parity.py`, `test_single_source_guard.py`, plus the
OEOC golden-import regressions (`test_real_oeoc_golden.py` and friends,
122 tests green).
