# Well Control Dual-Path Forensics + ICP/FCP Canonical Consolidation

**Date:** 2026-09-14
**Branch:** `arena/01a085e0-drill-master`
**Baseline verified at:** `d4c0b99` (Kill Sheet = calculation #4)
**Scope:** Determine whether DrillMaster has multiple active Well Control kill
sheet calculation paths; if the same calculation is implemented more than once,
establish one authoritative implementation without deleting legitimate UI entry
points and without changing any formula.

## A. Executive verdict — CERTIFIED WITH DOCUMENTED DEBT

There are **two active Well Control kill-sheet UI entry points** but they are
**NOT the same calculation**: the W13 tab is the full composite kill sheet, and
`DrillingCalculatorDialog` is a lightweight quick-estimate *subset*. The genuine
duplication was the **ICP and FCP formulas**, which were re-implemented inline in
three places. Those are now consolidated to a single owner
(`WellControlEngine`); `kill_mw`/`maasp` were already single-owner. Both UI entry
points are preserved. No formula changed (numerical equivalence proven). Full
suite **1196 passed / 4 skipped** (was 1186/4; +10 new), zero regressions.

## B. Repository identity

Branch `arena/01a085e0-drill-master`; remote `origin`
(`github.com/asgareyvazi/Drill-master`). **Stale-ref trap recurred** (local HEAD
= branch-point `b05ea76`). Recovered safely: `git fetch origin
arena/01a085e0-drill-master` → `FETCH_HEAD = d4c0b99`; `b05ea76` confirmed
ancestor; no unique local commits; `git reset FETCH_HEAD` (mixed). Working tree
clean, only untracked = pre-existing `.github/workflows/`. No work lost.

## C. Previous-report verification

| Claim | Evidence | Status |
|---|---|---|
| 4 persistent calcs (T&D/Casing/Cement/Kill Sheet) | records + repos + tests present; baseline suite green | ✅ |
| Only `calculation_verification.py` shared | grep of imports; four concrete repos/records | ✅ |
| Canonical path W13→WellControlKillSheetInputs→compute_kill_sheet→KillSheetResult | read in full | ✅ |
| `DrillingCalculatorDialog` has an ACTIVE legacy Kill Sheet | `main_window.open_calculator` (L2456) opens it from the "🧮 Calculator" toolbar/menu action | ✅ |
| commit `bdb1ea2`/`d4c0b99` | `git rev-parse` confirms | ✅ |

## D. Four-calculation baseline

T&D / Casing / Cement / Kill Sheet persistence + cross-process + verification
suites all pass unchanged. No engine or existing calculation refactored for
cosmetics. Known-good baseline established before touching Well Control.

## E. Well Control entry-point inventory

| Entry point | File | Active | Calculation | Canonical core | Persistence |
|---|---|---|---|---|---|
| W13 Kill Sheet tab | `tabs/w13_Engineering_Calculator.py::_wc_calc_kill` | yes | full composite | `compute_kill_sheet` | yes (calc #4) |
| Drilling Calculator popup | `dialogs/calculator_dialog.py::_calc_kill_sheet` | yes | quick-estimate subset | engine calls only | no |
| `WellControlExtended.wait_weight_method` | `core/engineering/extended.py` | test-only (no prod caller) | ICP/FCP/kill_mw trio | now delegates | no |
| AI tool `calculate_kill_mw` | `core/ai_tools.py` | yes | single value | delegates to engine | no |
| W15 reference display | `tabs/w15_Reference_Tables.py` | yes | formula strings only | n/a (display) | no |

## F. Well Control semantic comparison (W13 composite vs legacy dialog)

| Concern | W13 canonical kill sheet | DrillingCalculatorDialog | Same? | Evidence |
|---|---|---|---|---|
| Inputs | TVD/MD/shoe, hole/casing, MW, frac, SIDPP/SICP, pit gain, SCR1/2+spm, pump output, **full pipe program** | TVD, MW, SIDPP, SICP, slow-pump-rate, shoe TVD, frac | **No** — legacy is a strict subset | widget reads |
| Unit conv | m→ft ×3.28084, pcf→ppg ÷7.48, psi/ft→ppg ÷0.052 (single owner) | identical factors, inline | conversions equal | code |
| Pipe / volumes | string+annular volumes, simplified annulus | **none** | No | code |
| Engine calls | kill_mw, maasp, kick_volume | kill_mw, maasp only | subset | code |
| ICP | `scr1+sidpp` | `spr+sidpp` | same formula | code |
| FCP | `scr1·kmw/mw` | `spr·kmw/mw` | same formula | code |
| Strokes | volumes/pump_output | **none** | No | code |
| Choke schedule | linear 10-interval | **none** | No | code |
| Kick geometry | kick_volume → type/height | **none** | No | code |
| Result | `KillSheetResult` (whole) | formatted ASCII only | No | code |
| Persistence | yes | no | No | code |
| Workflow | W13 engineering tab, saved history | toolbar quick popup, transient | different | main_window |

## G. Unit conversion

Both paths use the *same* factors (×3.28084, ÷7.48, ÷0.052), each applied once
before the engine call. No double/missing conversion. The legacy `frac/0.052` is
a psi/ft→ppg conversion feeding `WellControlEngine.maasp` (identical to the
composite).

## H. Input equivalence

For the shared subset (TVD, MW, SIDPP, slow-pump-rate, shoe TVD, frac gradient)
both paths canonicalize to identical engine arguments. The legacy path simply
omits the composite-only inputs (pipe program, pump output, pit gain, hole size).

## I. Result equivalence (numerical, full precision)

`test_well_control_icp_fcp_consolidation.py::test_composite_and_legacy_subset_agree_full_precision`
proves, across three representative cases, that composite and legacy agree
exactly on every shared correctness value:

| Case (TVD m) | kill_mw ppg | ICP psi | FCP psi | MAASP psi | Equal? |
|---|---|---|---|---|---|
| 3000 | 11.003661 | 1300.000 | 877.945433 | 1828.1472 | ✅ |
| 4200 | 16.117658 | 2020.000 | 1291.715131 | 1968.0654 | ✅ |
| 1500 | 13.204393 | 800.000 | 548.715896 | 292.6439 | ✅ |

(kill_mw exact to ~1e-12 due to a test-only ft→m→ft round-trip; ICP exact.)

## J. Legacy classification — **DISTINCT CALCULATION (subset) / MULTIPLE UI ENTRY POINTS for the shared formulas**

`DrillingCalculatorDialog._calc_kill_sheet` is NOT a duplicate composite kill
sheet — it is a genuinely reduced quick-estimate with a distinct user workflow
(transient toolbar popup, no pipe program, no volumes/strokes/schedule/kick, no
persistence). It legitimately remains. What WAS duplicated is the **ICP/FCP
arithmetic** shared by both — that is the real single-source violation, now
fixed.

## K. Consolidation decision — CONSOLIDATED (formulas), UI PRESERVED

`kill_mw` and `maasp` were already single-owner (both paths delegate to
`WellControlEngine`). ICP and FCP had three inline copies. Added canonical
owners and made every site delegate. No UI deleted.

## L. Actual code changes

* `core/engineering/engines/well_control.py` — new `calculate_icp` /
  `calculate_fcp` raw helpers (explicit validation, no silent defaults) and
  `initial_circulating_pressure` / `final_circulating_pressure`
  `EngineeringResult` wrappers (formula + method recorded). Single owner of ICP
  and FCP.
* `core/engineering/well_control_kill_sheet.py::compute_kill_sheet` — ICP/FCP now
  call `WC.calculate_icp` / `WC.calculate_fcp` (byte-identical values;
  regression tests unchanged and green).
* `dialogs/calculator_dialog.py::_calc_kill_sheet` — ICP/FCP now call the engine.
* `core/engineering/extended.py::wait_weight_method` — kill_mw/ICP/FCP now
  delegate to the engine (its rounded dict contract preserved).

## M. Numerical regression

All composite kill-sheet regression tests (independent-oracle, 4 cases) still
pass byte-for-byte; cross-process reconstruction still MATCHes; extended
wait_weight test still passes (ICP == 1300 for its case). No formula changed.

## N. Persistence ownership

Unchanged: only the W13 composite persists (calculation #4). The legacy quick
estimate does not persist. No duplicate save path, no duplicate table, no schema
change.

## O. History ownership

Unchanged: one record source (`well_control_kill_sheet_calculations`), read by
the W13 read-only history dialog. The legacy dialog has and creates no history.

## P. Verification core

`calculation_verification.py` unchanged and still engine-agnostic. The composite
reuses it via `KillSheetResult`'s `success`/`values`/`error` protocol — no
WC-specific branches added.

## Q. Historical integrity

Kill-sheet cross-process reconstruction test still green (fresh interpreter loads
snapshot, recomputes whole composite, MATCH). Verify remains observational (no
mutation). Consolidation did not touch snapshots or stored results.

## R. Abstraction decision — VERIFICATION ONLY (unchanged)

Four persistent calculations still have four materially different snapshot/
result/reference/ORM shapes; only the verification core is shared. This
consolidation is a *within-Well-Control* single-source fix (engine owns the
formulas), not a cross-calculation abstraction. No generic framework introduced.

## S. Composite architecture

Kill Sheet remains the only composite calculation. Per §29 this does NOT justify
a `CompositeCalculation`/`CompositeRepository`/`CompositeEngine` framework — one
example is insufficient. Kept concrete.

## T. Calculation #5 inventory (read-only)

| Candidate | Engine | Result | Determinism | Reference | W13 UI | Snapshot-ready |
|---|---|---|---|---|---|---|
| MSE (Teale 1965) | `MSEEngine.calculate` | single `EngineeringResult` | pure | none (direct inputs) | yes | high |
| Mud Volume | `MudVolumeEngine` (balance/weight_up/dilution/mix) | single result | pure | none | yes | high |
| Bit Performance | `BitPerformanceEngine` | roll-up | depends on DDR run data | daily-report data | yes (+w12) | medium (input source is report data, not a clean form) |
| Fishing | `FishingEngine` | SCREENING results | pure | legacy chart approximations | yes | medium (explicitly screening) |
| Anti-Collision | `AntiCollisionEngine` | trajectory series | pure | trajectory data | **no UI** | low (no entry point) |

## U. Calculation #5 decision — DEFER (recommend MSE next)

No Calc#5 implemented this mission (out of scope until dual-path resolved, per
§34). **Ranked recommendation for a future slice: (1) MSE** — mature Teale
engine, single clean `EngineeringResult`, deterministic, direct inputs (no
misleading reference provenance), clear W13 entry point, snapshot-ready;
**(2) Mud Volume**; **(3) Bit Performance** (needs an input-boundary audit
because its inputs come from daily-report data, not a clean form). Fishing is
explicitly SCREENING (weak historical value); Anti-Collision has no UI.

## V. Reference architecture (unchanged, diverse)

| Domain | Source | Authority | Historical strategy |
|---|---|---|---|
| DrillPipe | vendor xlsx + persisted catalog | authoritative | fingerprint where identity holds |
| Casing | dialog preset | preset | numeric snapshot |
| Cement | direct inputs | manual | numeric snapshot |
| Well Control (kill sheet) | preset/catalog/manual pipe program | mixed | numeric snapshot, no fingerprint |

Diversity remains evidence AGAINST a generic reference framework — none built.

## W. Dead / duplicate / abandoned

* ICP/FCP inline arithmetic — was DUPLICATE (3 sites) → now single-owner. No dead
  code left (only explanatory comments).
* `WellControlExtended.wait_weight_method` — test-only (no production caller);
  retained (delegates now), NOT deleted (still covered by
  `test_extended_engineering.py`; deletion would be unrelated scope).
* `DrillingCalculatorDialog` — ACTIVE separate entry point; retained.
* No other duplicate kill_mw/MAASP computational path (remaining grep hits are
  docstrings/procedure text/display strings/AI-tool delegations).

## X. Search / Retrieval / Evidence

Unchanged. Calculations remain outside Search/Retrieval/EvidenceBundle/
CitationAuditor.

## Y. Dependencies

None added.

## Z. Database

No schema change. No new table. No migration.

## AA. Tests (exact)

New:
* `tests/test_well_control_icp_fcp_consolidation.py` — 9 (engine ICP/FCP vs
  independent oracle; result-wrapper value/method; extended delegation; composite
  vs legacy subset full-precision parity; explicit validation).
* `tests/test_drilling_calculator_dialog_smoke.py` — 1 (subprocess: legacy dialog
  opens, renders engine-identical ICP/FCP, validation works).

Commands / outcomes:
* Focused WC + extended → green.
* `compileall` on all changed modules → OK.
* `single_source_guard` → green (delegation parity intact).
* Full suite → **1196 passed, 4 skipped** (was 1186/4; +10; zero regressions).

## AB. Remaining debt (evidence-backed)

* `DrillingCalculatorDialog` remains a separate quick-estimate that does not
  persist; if operators want its runs in history it should delegate to
  `compute_kill_sheet` with a reduced input form (deferred — distinct workflow,
  no current requirement).
* `WellControlExtended` is test-only surface; could be retired in a dedicated
  cleanup (out of scope).
* `w13_Engineering_Calculator.py` (4790 lines) / `database.py` (9449 lines)
  exceed the 3000-line advisory (pre-existing warning, not a failure).

## AC. Git

Changed: `core/engineering/engines/well_control.py`,
`core/engineering/well_control_kill_sheet.py`, `core/engineering/extended.py`,
`dialogs/calculator_dialog.py` (modified); two new test files; this audit.
`.github/workflows/` left untouched.

## AD. Final decision — PROCEED WITH DEBT

One authoritative implementation of every Well Control formula
(kill_mw/MAASP/ICP/FCP) now lives in `WellControlEngine`; both UI entry points
are preserved and delegate; no formula changed; documented non-critical debt
remains (legacy dialog non-persistent, test-only extended surface).
