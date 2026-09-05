# DRILLMASTER — FULL ENGINEERING AUDIT REPORT

> **Date:** 2026-09-05 (re-audit at HEAD `5f92841` of
> `arena/01a05747-drill-master`)
> **Tests:** full suite **421 passed, 2 skipped, 0 failed** (fresh run);
> OEOC golden import regressions green (122 tests in the import batch).
> **Auditor:** Multi-role (Drilling Engineer + Software Architect + QA)

---

## A. Executive Summary

DrillMaster is a **production-oriented drilling operations management
desktop application**: real Excel DDR import (OEOC golden regression),
53+ ORM models, canonical single-source engineering engines, and a W13
engineering calculator that now **delegates** every calculation to the
canonical engines.

**Strengths (verified at this HEAD):**
- Canonical schema as SSOT for field aliases / quantity / unit / criticality.
- Deterministic engines (Bourgoyne, API RP, IWCF, Teale) with result
  contracts and no invented defaults.
- W13 `DrillingCalculationEngine` is a pure facade: 22 static delegates to
  canonical engines; legacy `12031` nozzle constant and duplicated
  `1029.4`-style capacity formulas removed from the tab and dialogs
  (guard-tested by `tests/test_single_source_guard.py`).
- Guard suite rejects stale constants and duplicated decorators in code.
- Torque & Drag, Anti-Collision, Fishing honestly labelled
  `PARTIAL / SCREENING` — nothing partial is claimed complete.

**Resolved since the 2026-08-24 baseline:** W13/UI delegation (was P0-2),
T&D soft-string engine, casing burst/collapse/combined/triaxial/tensile,
kick tolerance + MAASP + kill MW + formation pressure + kick volume,
cementing volumes/displacement, nozzle optimization canonical wiring (P0).

---

## B. Engineering Score (2026-09-05)

| Module | Status | Evidence at HEAD |
|--------|--------|------------------|
| Daily Report | ✅ Functional | Import + DB + UI verified end-to-end (OEOC workbook) |
| Time Log | ✅ Excellent validation | 24h/morning separation, NPT, dedup |
| BHA | ✅ Cumulative length/weight | `BHAEngine` in `core/engineering/core.py` |
| Drilling Parameters | ✅ Stored + analyzed | min/max WOB/RPM/torque/SPP/flow |
| Mud | ✅ Properties + ledger + mud-lab kit | `MudLedgerEngine`, `MudEngineering` (MBT, LSRYP, excess lime, OWR, slug, corrosion) |
| Hydraulics | ✅ Canonical engine | bit ΔP/TFA/HHP/HSI/jet velocity/impact, triplex/duplex pump output, AV, capacities, bottoms-up, lag, critical flow; capacities are SSOT (`D²/1029.4` lives once) |
| Survey/Trajectory | ✅ MCM correct | randomized MCM parity vs independent implementation (`tests/test_trajectory_mcm_parity.py`, worst |Δ|=3e-14) |
| Well Control | ✅ IWCF kit | kick tolerance, trip margin, MAASP, kill MW, kick volume, formation pressure, fracture gradient (incl. Eaton) |
| Casing | ✅ Design engine | burst/collapse/combined/triaxial/tensile (`engines/casing.py`) |
| Cementing | ✅ Volumes + displacement | `engines/cement.py`; capacity helpers delegate to `AdvancedHydraulicsEngine` |
| Torque & Drag | 🟡 PARTIAL / SCREENING | soft-string axial/soft model + buoyancy; never claimed COMPLETE |
| Anti-Collision | 🟡 PARTIAL / SCREENING | Euclidean clearance; ISCWSA error model explicitly unsupported without welleng |
| Fishing/stuck-pipe | 🟡 PARTIAL / SCREENING | free point, stretch, adjusted weight, jar range, overshot fit, back-off |
| NPT / Services / Logistics / HSE / Planning | ✅ Functional | models + analyses as implemented |
| Cost | 🟡 Basic storage | AFE/forecast not implemented |
| Bit performance (W12) | ✅ d-exp/dc/cost/ft/MSE | `engines/bit_performance.py`, `engines/mse.py`; DB-fed trends; torque klb.ft→ft·lbf at one boundary |
| Import/Export | ✅ Strong pipeline | OEOC golden + multi-company templates, additive-only DB upgrades |

---

## C. Status of previously-reported critical problems

| ID | Problem | Status (2026-09-05) |
|----|---------|---------------------|
| P0-1 | ROP model K constant unrealistic (was K=240) | **FIXED** — `core/engineering/extended.py` L743 now `k = 0.5 * strength_factor * (1 + porosity_pct/100)` (K≈0.5–1), calibrated range |
| P0-2 | Engineering calculator self-contained (4,784 lines, inline calcs) | **FIXED** — `DrillingCalculationEngine` is a delegation facade over canonical engines; guard tests enforce no duplicated constants in tabs/dialogs |
| P1-1 | No torque & drag implementation | **FIXED (partial)** — soft-string engine with explicit `PARTIAL / SCREENING` scope; optional welleng adapter never a silent backend |
| P1-2 | Casing design not implemented | **FIXED** — burst/collapse/combined/triaxial/tensile with design factors |
| P1-3 | No kick tolerance | **FIXED** — `kick_tolerance` with influx-gradient input (missing input → warning, no invented gradient) |
| P1-4 | MainWindow monolithic (2,958 lines) | **REMAINING** — refactor deferred; not a correctness blocker |

---

## D. Engineering-refactor changes (this work session)

| File | Change |
|------|--------|
| `tabs/w13_Engineering_Calculator.py` | Facade rewrite: 22 direct static delegates (hydraulics/trajectory/well-control/T&D/fishing/mud); `setattr` mud-facade deleted; 7 inline `3.281/1029.4` capacity clusters rewired to canonical per-ft statics; kill sheet kick type/height via `WellControlEngine.kick_volume`; no legacy constants remain |
| `core/hydraulics_engine.py` | `optimize_nozzles` uses canonical `calc_bit_pressure_drop`/`calc_tfa_from_pressure_drop` (10858 family); added canonical `calc_pipe_capacity_bbl_ft`, `calc_annular_capacity_bbl_ft`, `calc_pipe_displacement_bbl_ft` statics |
| `core/engineering/core.py` | `TrajectoryEngine.calculate_build_rate/calculate_turn_rate` real class statics used by `calculate()`; `WellControlEngine` compat statics |
| `core/engineering/engines/torque_drag.py` | buoyancy factor single-source; `calculate` delegates |
| `core/engineering/engines/well_control.py` | canonical kit incl. `formation_pressure`, `kick_volume` |
| `core/engineering/engines/cement.py` | capacity helpers + `job_volumes`/displacement delegate to `AdvancedHydraulicsEngine` |
| `core/engineering/engines/fishing.py` | NEW canonical fishing/stuck-pipe screening module |
| `core/engineering/engines/anti_collision.py` | honest `PARTIAL / SCREENING` `SCOPE`/`METHOD` metadata |
| `dialogs/calculator_dialog.py`, `dialogs/engineering_dialogs.py` | inline AV/capacity/volume formulas replaced by canonical engine calls |
| `ENGINEERING_REFERENCE_MATRIX.md` | NEW — 13-repository mapping table with evidence |

---

## E. Tests (fresh run, 2026-09-05)

```
Total:      421 collected
Passed:     421
Skipped:    2   (headless sandbox — PySide6 display-only tests)
Failed:     0
Errors:     0
New since last audit: +37 nozzle/guard/trajectory-parity + guard suite
OEOC import batch:    122 passed (golden DDR, multi-company, atomic import)
```

Guard coverage: stale constants (`12031`, `1086.31`, `10863.1`, `1932`)
absent everywhere; canonical constants (`10858`, `1714`, `1930`, `3.117`,
`1029.4`, …) present only in core engines / w15 reference tab / tests;
no stacked `@staticmethod` decorators anywhere in code.

---

## F. Honest limitations (2026-09-05)

**DrillMaster does NOT claim:**
- COMPLETE torque & drag — **PARTIAL / SCREENING soft-string only**
- Full ISCWSA anti-collision — Euclidean screening only; error-model path
  requires welleng and is explicitly optional
- Slurry thickening-time/cement job design
- Real-time drilling optimization, wellbore stability, pore pressure
  prediction, MPD/UBD — out of scope
- Casing wear / BHA vibration / shock modelling

**Known remaining code gaps:** MainWindow monolithic; cost AFE/forecast;
service performance analytics; NPT report synthesis from service rows;
time-log rows arriving as `timedelta` skipped by UI filter (7/10 24h rows
reach DB); 2 of 13 lookahead rows lack activity text (stored: 11).

---

## G. Remaining Roadmap

### P1
1. MainWindow decomposition (extract managers already exist in `core/`)
2. Wire T&D / anti-collision engines into a UI surface (engines ready,
   screening-grade)
3. Cost AFE/forecast from stored daily costs

### P2
1. Cement slurry design (thickening time, lead/tail)
2. NPT Pareto + service-performance dashboards
3. Real-time data integration (WITSML) — currently Excel-DDR based

### P3 (evaluation only — no commit yet)
1. welleng adapter benchmarking for full ISCWSA anti-collision
2. 3D trajectory visualization (architecture requires no new top-level tab)

---

## H. OEOC Real-Import Audit (preserved addendum, re-verified green)

Path verified end-to-end with the REAL workbook
`08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx` +
`templates/OEOC_DDR_v3.json` (no fabricated fixtures):
`Excel workbook → Template (anchored) → Canonical JSON → SQLite → UI tabs`.

Pipeline facts: canonical schema is the single registry; extraction scoring
(preferred cell > merge > exact label > alias > fuzzy) with honest certainty;
missing = key absent, "N.C" = None + provenance, never invented zeros;
generic flow with no per-company branching; additive-only DB schema upgrades
(`_apply_safe_schema_upgrades`, idempotent, data-preserving).

Real-workbook verification results (unchanged, still green at this HEAD):
report date 2024-10-22 assembled from parts; bit 17.5″ No. 2 rerun 1
KingDream IADC 135, nozzles 1×18/32″ + 2 Open, TFA 4.32; mud MW 71 PCF,
PV/YP/gel/pH/chlorides/solids/hardness/34 chemicals with units; fluid loss
N.C → NULL; pump liner verbatim; WOB/RPM/torque/SPP min–max; 24h vs morning
time-log separation; 6 service companies preserved; 13 lookahead activities
(11 stored); BOP stack 6 components with last-test provenance; LTA 468;
actual rig days 7.25; POB 130 breakdown; days_without_lti 468; missing drill
dates stay NULL.

**Remaining genuine import limitations (unchanged):** timedelta time cells
skipped by UI filter; 2 lookahead rows without activity text; no NPT report
synthesis from negative-duration service rows; UI verification is code-path
level in the headless sandbox (no libGL).
