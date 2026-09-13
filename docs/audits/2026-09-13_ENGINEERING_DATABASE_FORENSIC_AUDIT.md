# Engineering Database & Calculation Architecture — Forensic Audit + Foundation

**Date:** 2026-09-13
**Branch:** `arena/01a085e0-drill-master`
**Rule preserved:** ONE ENGINE → ONE FORMULA → ONE RESULT

Repository-first audit. Nothing here is trusted from prior reports, comments, or
this task's prompt unless the actual code proved it.

---

## A. Repository identity

| Item | Value |
|---|---|
| Path | `/home/user/Drill-master` |
| Branch | `arena/01a085e0-drill-master` |
| Starting SHA | `b210cad` |
| Final SHA | *(this commit)* |
| Remote | `origin` = `github.com/asgareyvazi/Drill-master`, in sync |
| Working tree | clean except untracked `.github/workflows/` (pre-existing) |

## B. Baseline / final test metrics

| Gate | Baseline (`b210cad`) | Final |
|---|---|---|
| pytest | 978 passed / 4 skipped | **999 passed / 4 skipped** |
| new tests | — | +21 (`tests/test_drill_pipe_spec.py`) |
| ruff E722 | 0 | 0 |
| ruff F821 | 0 | 0 |
| ruff total debt | 5489 | **5489** (no increase) |
| compileall | clean | clean |

---

## C. Engineering data inventory

Whole-repository search for engineering reference datasets (drill pipe, HWDP,
collars, stabilizers, jars, motors, RSS, MWD/LWD, reamers, bits, nozzles,
casing, liner, tubing, connections, mud, cement, pumps, formations, grades,
manufacturers) across `.xlsx/.xls/.csv/.json/.yaml/.sqlite/.db` and hard-coded
Python.

| Source | Domain | Format | Current owner | Consumers | Authoritative? | Risk |
|---|---|---|---|---|---|---|
| `DrillPipe.xlsx` (**absent from repo**) | Drill pipe reference | Excel (vendor sheet `Aa`) | `tabs/w13_Engineering_Calculator.py._load_drill_pipe_db` via `core/runtime_config.drill_pipe_reference_paths()` | **None** — rendered read-only in a `PandasTableModel`; no calculation reads it | No (optional vendor file, ships absent) | Schema-less passthrough; disconnected from calculations; user could load arbitrary columns |
| DDR import templates | Report field mapping (not engineering ref) | JSON | `templates/OEOC_DDR_*.json`, `config/company_templates/*.json` | import pipeline | Yes (for import mapping) | none for engineering |
| Physical constants | steel density 65.5 ppg, 120π, 10858, 3.117, Barlow 0.875, API 5C3 coeffs | hard-coded in engines | `core/engineering/engines/*`, `core/hydraulics_engine.py` | the engines themselves | Yes (documented, GT-tested) | none — these are formula constants, not catalog data |
| `CasingReport`, `BitReport`, `BHAReport`, `DownholeEquipment` | Operational equipment records | SQLAlchemy + JSON blobs | `core/database.py` | DDR tabs, KPI | Yes (operational) | JSON blobs, report-scoped, not normalized master specs |
| Test fixtures | DDR workbooks | Excel | `tests/fixtures/*.xlsx` | tests only | test-only | none |

**Headline finding:** the repository ships **no engineering reference/master
dataset at all**. The only thing called a "database" (drill pipe) is an
*optional, absent, schema-less, read-only Excel viewer* with **zero calculation
consumers**.

---

## D. Engineering calculation inventory

All engines return the canonical `EngineeringResult` (`core/engineering/result.py`)
and are reached through `core/engineering/bridge.CalculatorBridge`. They are
**pure calculators**: they take numeric inputs, not catalog lookups.

| Engine | Formula / model | Inputs | Outputs | Scope | Status | Tests |
|---|---|---|---|---|---|---|
| `TrajectoryEngine` (`core.py`) | Minimum Curvature | survey (md/inc/azi) | tvd/N/E/VS/DLS | COMPLETE | ✅ | GT + parity |
| `WellControlEngine` | IWCF kick tol / trip margin / kill MW / MAASP | MW, TVD, frac/LOT, influx grad | psi, ppg, bbl | COMPLETE (single-bubble) | ✅ | GT |
| `MSEEngine` | Teale | WOB, RPM, T, ROP, Ab | psi | COMPLETE | ✅ | GT |
| `MudVolumeEngine` | mass/volume balance | volumes, densities | bbl, sacks | COMPLETE | ✅ | GT |
| `BitPerformanceEngine` | footage/ROP/(Teale) | DDR bit data | ROP, MSE | COMPLETE | ✅ | yes |
| `CasingEngine` | Barlow 0.875 + 4-regime collapse + fyax + VME | OD, wall, **yield_psi** | psi, klbf | PARTIAL (pipe-body, not full TR 5C3) | 🟠 | GT |
| `CementEngine` | D²/1029.4 volumes, stacked hydrostatic | geometry, MW, yield | bbl, sacks, psi | COMPLETE worksheet / 🔴 lab | ✅ | GT |
| `TorqueDragEngine` | Johancsik soft-string + buckling flags | survey, **components {length,weight,od,id}**, MW, ff | klbf, ft·lbf | PARTIAL / SCREENING | 🟠 | GT |
| `AntiCollisionEngine` | Euclidean screening | two trajectories | clearance | PARTIAL | 🔴 (do not expand) | yes |
| `HydraulicsEngine` / `AdvancedHydraulicsEngine` | ΔP, TFA, jet velocity, nozzle opt | gpm, MW, TFA, geometry | psi, hhp | COMPLETE core | ✅ | yes |
| welleng / torque_drag adapters | external | — | — | SCREENING (benchmark only) | 🟠 | yes |

W13 sub-tools (surge/swab, fishing, pump output) are **legacy UI helpers**, not
a second engine — preserved as such.

---

## E. Database architecture findings

**What already exists**
- A clean canonical *calculation* architecture (engines + `EngineeringResult` +
  `CalculatorBridge`) with honest COMPLETE/PARTIAL/SCREENING/NOT_IMPLEMENTED
  scope labels.
- A canonical, no-fake-default **`UnitManager`** (`core/unit_manager.py`) with
  explicit canonical conventions (diameter → in, pressure → psi, weight → klbf,
  etc.).
- Operational equipment records (`CasingReport`, `BitReport`, `BHAReport`,
  `DownholeEquipment`) — report-scoped, JSON-blob-based.

**What is duplicated / conflicting**
- **No duplicate engineering master data was found** — because none exists.
  There is no `DrillPipeSpec2`, no parallel catalog. The only "database" is the
  disconnected drill-pipe Excel viewer.

**What is missing**
- Any canonical **Engineering Master Data** representation (a reference spec with
  explicit units, stable domain identity, and provenance).
- A safe boundary that turns an arbitrary vendor reference row into that
  canonical shape without fabricating unknowns.
- A proven handoff from reference specification → calculation engine.

**What should become canonical**
- Reference specifications (drill pipe first) as immutable, unit-explicit,
  provenance-carrying value objects — **separate** from operational runs.

**Units-integrity finding (§9):** `UnitManager` groups `ppf` (a *linear* weight,
lb/ft) under the scalar `weight` quantity with the same factor as `lb` and the
comment "keep numeric". It therefore does **not** convert `ppf`↔`kg/m`
physically. The canonical spec keeps nominal weight in **ppf** (matching the T&D
engine's `weight_ppf` contract) and never routes ppf through a unit conversion.
Diameters (mm↔in) do convert correctly and use `UnitManager`. This is documented
rather than "fixed", because ppf is intentionally the engine's native unit — a
`ppf`↔`kg/m` linear-density conversion is a separate, deferred decision.

---

## F. Drill Pipe vertical slice (the foundation implemented)

Evidence that the slice is justified, not speculative:
- W13's weight-card and hydraulics tabs already operate on pipe rows with
  columns **Type / OD (in) / ID (in) / Length (m) / Wt (ppf)** — but the user
  must **type** every value by hand.
- The `TorqueDragEngine` per-component contract is **exactly**
  `{length, weight (ppf), od (in), id (in)}`.
- So a canonical drill-pipe spec has a real, existing calculation consumer.

Because `DrillPipe.xlsx` is **absent** and its schema is vendor-defined, there is
no dataset to migrate — migrating a nonexistent file would fabricate data
(§15/§28). The correct minimal, production-grade foundation is therefore the
canonical **representation + safe normalizer + proven engine handoff**, with no
new DB table (nothing to persist yet), no UI change (it would be empty), and no
migration.

```
vendor row (arbitrary headers/units)
  → DrillPipeSpec.from_vendor_row()        # alias-mapped, unit-explicit, unknown-preserving
      · diameters → inches via UnitManager
      · weight → ppf (kept numeric)
      · unmapped columns → .extra (audit)
      · missing/blank/NaN → None (never 0)
  → DrillPipeSpec (identity = mfr+model+OD+weight+grade+connection; provenance)
  → .to_component(length_m)                 # {length, weight, od, id}
  → TorqueDragEngine.calculate(...)         # canonical engine, unchanged
  → EngineeringResult (total_buoyed_weight = 165.23 klbf)
```

**Test proof** (`tests/test_drill_pipe_spec.py`, 21 tests):
normalization (units, unknown-preservation, no-inference, extra-preservation);
identity (domain key not row index; OD+weight gate); duplicate classification
(IDENTICAL / DUPLICATE / CONFLICTING / AMBIGUOUS — never silent merge);
provenance; and the engine handoff reproducing the repository's own buoyed-weight
ground truth (165.23 klbf) plus a MISSING_INPUT safety case.

---

## G. BHA / Bit architecture findings (foundation only — no rewrite)

Current state: `BHAReport.bha_data_json` and `BitReport.bit_records_json` are
**report-scoped JSON blobs** keyed by `well_id` + `report_id`. They are
operational, not normalized, not longitudinal master data.

Correct next boundary (documented, **not** implemented here):
```
DrillPipeSpec / (future) BitSpec, StabilizerSpec …   [MASTER, unit+provenance]
        ↓  referenced by identity_key (not copied)
BHAComponent  (operational: which spec, serial, length run)
        ↓
BHARun        (Well + Wellbore + Run #)
        ↓
Hydraulics / T&D / KPI  via .to_component()
```
`DrillPipeSpec.to_component()` is deliberately the seam a future `BHAComponent`
will call. No BHA rewrite was performed — the slice needed none.

---

## H. UI findings

**Current W13 responsibilities:** input widgets (spinboxes) → engine wrappers →
formatted output. Every calculation input is manual. The "DP Database" tab is a
read-only Excel viewer disconnected from calculation.

**Future Database Center responsibilities (not built this phase):** search /
filter / view / add / edit / duplicate / import / export / provenance /
validation / revision over canonical specs — starting with drill pipe, once a
real source-of-truth dataset decision exists. Building the UI now would present
an empty table (no dataset ships), so it is deferred by evidence.

---

## I. Remaining gaps

- **FIXED / DELIVERED:** canonical `DrillPipeSpec` master-data foundation with
  explicit units, stable domain identity, provenance, safe vendor normalization,
  duplicate/conflict classification, and a GT-proven engine handoff.
- **DOCUMENTED:** no engineering reference dataset ships; drill-pipe Excel is a
  disconnected viewer; `ppf` linear-weight is not physically convertible in
  `UnitManager`; BHA/Bit are JSON blobs with a defined future normalization path.
- **DEFERRED (by evidence, not omission):** persistence table + CRUD UI (no
  dataset to store/show yet); BHA/Bit normalization (needs its own phase); other
  verticals (casing, bit, mud) — same "no shipped dataset" blocker.
- **BLOCKED:** true canonicalization of the vendor drill-pipe file — blocked on
  a source-of-truth decision and an actual dataset. Reported, not fabricated.

## J. Files changed

| File | Why | What | Architectural role |
|---|---|---|---|
| `core/engineering/drill_pipe.py` (new) | Establish canonical Engineering Master Data | `DrillPipeSpec` value object, `Provenance`, `from_vendor_row` normalizer, `to_component` engine handoff, `classify_duplicate` | The first canonical master-data representation + safe boundary to the engines |
| `tests/test_drill_pipe_spec.py` (new) | Prove the slice with numeric GT | 21 tests: normalization, identity, duplicates, provenance, engine handoff (165.23 klbf), MISSING_INPUT safety | Regression + ground-truth lock |
| `docs/audits/2026-09-13_ENGINEERING_DATABASE_FORENSIC_AUDIT.md` (new) | Record the audit | This report | Architecture documentation |

No existing engine, `core/database.py`, `UnitManager`, or W13 formula code was
modified. No migration. No UI redesign.

## K. Numerical evidence

- Vertical buoyed weight via `DrillPipeSpec → to_component → TorqueDragEngine`:
  10 000 ft × 19.5 ppf, MW 10 ppg → BF = 1 − 10/65.5 = 0.8473 →
  **165.23 klbf** (matches `test_engineering_ground_truth.test_vertical_buoyed_weight`).
- Diameter normalization: 127 mm → **5.000 in** (via `UnitManager`).
- Missing weight spec → engine returns non-success (`missing_input`/`error`),
  never a fabricated 0-weight result.

## L. Final recommendation (evidence-based)

The calculation core is healthy and honest; the real deficiency is the total
absence of canonical engineering master data and any safe reference→engine
boundary. This phase delivered that boundary for drill pipe without fabricating
data or destabilizing the app.

**Recommended next phase:** obtain/confirm a **real drill-pipe source-of-truth
dataset** (a committed, licensed reference table or an explicit company standard),
then (1) add a minimal persistence repository for `DrillPipeSpec` keyed by
`identity_key` with duplicate/conflict handling wired to `classify_duplicate`,
and (2) let W13's existing weight/hydraulics pipe tables *select a spec* to
populate a component instead of manual entry. Only after that is proven should
the Database Center UI and additional verticals (bit, casing, mud) follow. Do
**not** expand into new formulas, full API TR 5C3, production T&D, or a BHA
renderer until a shipped dataset justifies it.
