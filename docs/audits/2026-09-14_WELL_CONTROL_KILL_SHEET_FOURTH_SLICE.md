# Well Control Kill Sheet — Calculation #4 (Composite) Deep Forensic Audit

**Date:** 2026-09-14
**Branch:** `arena/01a085e0-drill-master`
**Baseline verified at:** `bdb1ea2` (Well Control input-boundary hardening)
**Scope:** Qualify the Well Control kill sheet as a persistent historical
engineering calculation, and — since qualification passed — implement it as
DrillMaster's FOURTH persistent calculation (and its first *composite* one),
then reassess architecture after four calculations.

## A. Executive verdict — CERTIFIED

The kill sheet passed every persistence-qualification gate and has clear,
safety-critical user value. Calculation #4 is implemented as a concrete slice
(no generic framework), with whole-result verification, mandatory cross-process
reconstruction, corruption handling, historical immutability, and a read-only
history UI. Full suite **1186 passed / 4 skipped** (was 1160/4; +26 new),
zero regressions.

## B. Repository identity

* Branch `arena/01a085e0-drill-master`; remote `origin`
  (`github.com/asgareyvazi/Drill-master`).
* **Stale-ref trap recurred** (as it has repeatedly): local HEAD started at the
  branch-point `b05ea76` with all prior mission work appearing uncommitted.
  Recovery followed the proven safe procedure — `git fetch origin
  arena/01a085e0-drill-master` (by name) → `FETCH_HEAD = bdb1ea2`; confirmed
  `b05ea76` is an ancestor, **no unique local commits** (`bdb1ea2..HEAD` empty),
  tracked tree byte-identical to `bdb1ea2`, only untracked = pre-existing
  `.github/workflows/`; then `git reset FETCH_HEAD` (mixed). No work lost. Never
  hard-reset.

## C. Previous-report verification (independently checked)

| Claim | Evidence | Status |
|---|---|---|
| `well_control_kill_sheet.py` exists w/ canonical boundary | file present; read in full | ✅ |
| Old handler engineering relocated | `_wc_calc_kill` (L3976) has **zero** conversion constants (3.28084 / 7.48 / 0.052) and **zero** engine calls — only variable unpacking from `res` for ASCII render | ✅ |
| No duplicate conversion path in handler | grep across handler body: none | ✅ |
| 11 Qt-free kill-sheet tests | `--collect-only` = 11; all pass | ✅ |
| Full suite 1160/4 (post-hardening baseline) | re-ran three-calc + verification-core + WC baseline green | ✅ |
| commit `bdb1ea2` | `git rev-parse FETCH_HEAD` = `bdb1ea2` | ✅ |

Other conversion sites (`_wc_refresh_pipe_table`, `_wc_calc_eaton`,
`_wc_calc_hp`) are the pipe-table DISPLAY path and separate single-engine
handlers — not the kill-sheet calculation path.

## D. Baseline revalidation (three persisted calcs + verification core)

T&D / Casing / Cement persistence + cross-process + verification-core suites all
pass unchanged. No engine and no existing calculation was touched. Baseline is
known-good.

## E. Well Control architecture (actual)

* Engine `core/engineering/engines/well_control.py` — `WellControlEngine`,
  `METHOD = "IWCF / IADC well-control manuals; Bourgoyne et al."`, canonical-unit
  classmethods `kill_mw`, `maasp`, `kick_volume` (+ others), returning
  `EngineeringResult`.
* Composite `core/engineering/well_control_kill_sheet.py` —
  `WellControlKillSheetInputs` (frozen), `build_canonical_kill_sheet_inputs`
  (single unit-conversion owner), `compute_kill_sheet` → `KillSheetResult`.
* Handler `tabs/w13_Engineering_Calculator.py::_wc_calc_kill` — reads widgets →
  builds canonical inputs → computes → renders ASCII → caches
  `_wc_last_kill_inputs` / `_wc_last_kill_result`.

## F. Input boundary (canonical, single-owner)

All raw→canonical conversion happens exactly once in
`build_canonical_kill_sheet_inputs`:

| Raw input | Canonical field | Unit | Owner | Role | Persist? |
|---|---|---|---|---|---|
| tvd_m / md_m / shoe_tvd_m | tvd_ft / md_ft / shoe_tvd_ft (×3.28084) | ft | builder | kill_mw, maasp | yes |
| hole_size_in / casing_id_in | same | in | builder (no conv) | volumes | yes |
| mw_pcf | mw_ppg (÷7.48) | ppg | builder | kill_mw, fcp, maasp | yes |
| frac_gradient_psi_ft | same (÷0.052 only *inside* maasp call) | psi/ft | builder | maasp | yes |
| sidpp/sicp_psi | same | psi | builder | kill_mw, icp, kick | yes |
| pit_gain_bbl | same | bbl | builder | kick_volume | yes |
| scr1/scr2 psi+spm | same | psi/spm | builder | icp, fcp, schedule | yes |
| pump_output_bbl_stk | same | bbl/stk | builder | strokes | yes |
| pipe od/id (in), length_m | od_in/id_in, length_ft (×3.28084) | in/ft | builder | volumes | yes |
| method / well_type | same | — | builder | procedure/labels | yes |

## G. Unit-conversion audit

Three factors, one owner, each applied once (regression-proven in
`test_well_control_kill_sheet.py::test_unit_conversion_single_owner` and
`test_matches_original_handler_math`). No double/missing/UI-state-dependent
conversion. `frac_gradient` is intentionally NOT pre-converted at the boundary
because `maasp` consumes the psi/ft→ppg conversion internally — preserving the
original code path.

## H. Composite dependency graph (actual)

```
canonical inputs
  ├─ pipes ─────────────► string/annular volumes (AdvancedHydraulicsEngine caps)
  ├─ mw,sidpp,tvd ──────► WC.kill_mw ─► kill_mw_ppg ─► fcp = scr1·(kmw/mw)
  ├─ (scr1+sidpp) ──────► icp                          (derived, no engine)
  ├─ frac,mw,shoe ──────► WC.maasp ──► maasp
  ├─ volumes/pump ──────► strokes                      (derived, no engine)
  ├─ pit_gain,hole,od ──► WC.kick_volume ─► kick_height/type
  └─ icp,fcp,stk_to_bit ► choke schedule (linear, 10 intervals)  → KillSheetResult
```

Three sub-engine calls + derived arithmetic + schedule → **this is a genuine
composite (mission §7 answer = B)**. The composite owns the single historical
claim; sub-engine results are implementation details, never persisted separately
(mission §51).

## I. Result contract

`KillSheetResult.values` (the persisted correctness projection) includes every
CORRECTNESS field: kill weights, ICP/FCP/MAASP, all volumes, both nested
string/annular detail lists, strokes, kick height, and the full choke schedule.
Excluded as DIAGNOSTIC/PRESENTATION: `success`, `error`, `method`,
`engine_method`, `warnings`, `kick_note`, and the human-facing `kick_type` label.
This makes `deep_numeric_diff` compare exactly the numeric/structural answer.

## J. Determinism

Same-input, interleaved, fresh-process and serialization-round-trip determinism
all proven (`test_well_control_kill_sheet.py` + cross-process test). Ordering is
deterministic: pipe order is the operator's program (preserved, never sorted),
schedule rows are index-generated.

## K. Numerical regression

Independent-oracle regression (4 cases) reproduces the original handler
arithmetic exactly; reconstruction reproduces the WHOLE result
(`test_reconstruction_reproduces_whole_result`). Example run (case 1):
kill_mw 13.009 ppg, ICP 1300 psi, FCP 864.95 psi, MAASP 1143.91 psi, total well
vol 657.55 bbl, 7306 strokes, choke schedule 11 points.

## L. Snapshot readiness — READY

Explicit boundary ✅, all inputs captured ✅, canonical single-owner units ✅,
composite deterministic ✅, whole result complete ✅, reconstruct w/o UI/mutable
pipe list/catalog/globals ✅ (cross-process proven), hidden deps understood ✅,
reference semantics understood ✅.

## M. Persistence decision — IMPLEMENTED

User value is high: a kill sheet is the safety-critical, auditable well-control
artifact operators most want to preserve, inspect, and re-verify — it fits the
same Save/History workflow already shipped for T&D/Casing/Cement on the very same
W13 tab. Qualification gate fully satisfied → persist as Calculation #4.

## N. Persistence architecture (concrete)

* `core/engineering/well_control_kill_sheet_persistence.py` —
  `build_snapshot(inputs, method)` freezes `WellControlKillSheetInputs.as_dict()`
  under `canonical_inputs` (+ separate presentation-only `display`), records
  `method` (human-readable calc identifier, **not** a git/file hash — §11) and
  `schema_version`; `snapshot_to_inputs`, `recalculate_from_snapshot` (re-runs
  the SAME `compute_kill_sheet`), `result_summary`.
* `core/database.py::WellControlKillSheetCalculationRecord`
  (`well_control_kill_sheet_calculations`, 17 columns) — independent concrete
  ORM model; snapshot JSON + whole-result JSON + 7 promoted summary columns +
  timestamps; no reference fingerprint.
* `core/repositories/well_control_kill_sheet_repository.py` —
  `WellControlKillSheetRepository` (+ detached `SavedKillSheetCalculation`);
  single `session_scope` unit of work (no partial rows); each save is a distinct
  run (never deduplicated).
* `dialogs/well_control_kill_sheet_history_dialog.py` — read-only browse /
  inspect / verify; renders from the PERSISTED record only; owns no engineering
  or verification logic.
* W13 wiring — Save/History buttons on the Kill Sheet sub-tab;
  `_wc_kill_sheet_repo`, `_wc_save_calculation`, `_wc_open_history`.

## O. Historical reconstruction

Cross-process: Process A computes+saves to an on-disk SQLite DB and exits;
Process B (fresh interpreter) reloads, reconstructs `WellControlKillSheetInputs`
from the frozen snapshot, re-runs the whole composite, and verifies MATCH with
identical kill_mw, MAASP and schedule values. No live UI/catalog/global state
involved.

## P. Verification (four states, all exercised)

* MATCH — clean reload.
* DIFFERENT — scalar drift, nested detail-list drift, schedule-row drift, and
  schedule-length change all detected (whole-result, so no false MATCH).
* NOT_REPRODUCIBLE — snapshot forcing a sub-engine failure (mw_ppg=0 → kill_mw
  rejects) → composite cannot run.
* UNREADABLE — empty stored result; structurally invalid snapshot.

Reuses the shared engine-agnostic `calculation_verification.py` with **zero**
WC-specific branches: `KillSheetResult` exposes the `success`/`values`/`error`
duck-typed protocol the generic `classify_verification` already consumes.

## Q. Mutation isolation

`verify()` never mutates the stored record (proven). Two runs are independent;
run A still verifies MATCH after run B is saved. The W13 smoke test proves that
mutating current widgets + pipe program and recomputing does NOT alter the
already-persisted run and does not create a phantom row.

## R. Reference traceability

The kill-sheet pipe program is a MIXED reference: `AddPipeDialog.PIPE_DB`
built-in presets, the optional persisted DrillPipe catalog, or manual entry. But
the calculation consumes only each segment's numeric `od`/`id`/`length`/`type`,
which are frozen into the snapshot. Reconstruction needs no live catalog — proven
by the fresh-process test — so **no reference fingerprint is stored** (claiming
catalog traceability would be misleading). This is the correct, honest choice.

## S. Algorithm compatibility

Recorded: engine `METHOD` string + snapshot `schema_version`. Checked:
`method_matches` flag surfaced by verification (a numeric MATCH under a changed
method is explicitly flagged as NOT an exact-algorithm reproduction —
`test_method_change_flagged_even_if_numbers_match`). NOT enforced: no hard block
on method change; verification is observational.

## T. Composite calculation category — YES, distinct

The kill sheet IS a distinct semantic category from the three single-engine
calculations (three engine calls + derived arithmetic + schedule vs one engine
call = one result). **But per mission §50 this does NOT justify a
`CompositeCalculation` framework** — one real composite example is not enough. It
is implemented as a concrete composite; the category is documented for the next
composite to reconsider.

## U. Abstraction decision — VERIFICATION ONLY (unchanged after four)

| Concern | T&D | Casing | Cement | Kill Sheet | Shared? |
|---|---|---|---|---|---|
| Snapshot | engine kwargs | engine kwargs | engine kwargs | canonical composite inputs | ✗ different shapes |
| Reconstruction | 1 engine | 1 engine | 1 engine | whole composite | ✗ |
| Result | 1 EngineeringResult | 1 result | nested legs+layers | scalars+2 lists+schedule | ✗ |
| ORM record | concrete | concrete | concrete | concrete | ✗ |
| Repository | concrete | concrete | concrete | concrete | ✗ |
| History UI | concrete | concrete | concrete | concrete | ✗ |
| Reference | authoritative (DrillPipe) | preset | direct | mixed→no fingerprint | ✗ diverse |
| **Verification** | shared core | shared core | shared core | shared core (no WC branch) | ✅ |

Only `calculation_verification.py` is genuinely shared. The four snapshot/
result/reference shapes are materially different (reference diversity alone
argues against any generic reference layer). No generic calculation repository,
snapshot base, history-UI base, reference catalog, or composite framework is
earned. **Abstraction stays VERIFICATION-ONLY.**

## V. History UI

Read-only list (newest-first), details rendered from the persisted record only
(never live widgets), and a Verify button that delegates to the domain layer and
reports the four states with a method-change note. No edit/delete/overwrite.

## W. Database

* Fresh DB — `Base.metadata.create_all` creates the table; save/reload/verify
  works.
* Existing DB — `_apply_safe_schema_upgrades` auto-provisions
  `well_control_kill_sheet_calculations` via `CreateTable` (no Alembic), 17
  columns, while `cement_calculations` / `casing_calculations` /
  `torque_drag_calculations` remain present. Idempotent re-run keeps existing
  rows verifiable. All proven cross-process.

## X. Error / corruption handling

INPUT_INVALID vs ENGINE_FAILED classified at compute time; UNREADABLE vs
NOT_REPRODUCIBLE vs DIFFERENT classified at verify time; save is transactional
(no partial rows). Covered by tests.

## Y. Calculation #5 reconnaissance (ranked, not implemented)

1. **Hydraulics (ECD / pressure-loss / pump)** — heavily used on W13, likely a
   composite; needs its own boundary audit first.
2. **The clean single-engine WC sub-tabs** (kick tolerance, trip margin) —
   already canonical; cheap `EngineeringResult` persists if desired.
3. **Directional/survey (min-curvature)** — data-series result; different
   verification shape.

## Z. Reference inventory (living)

| Domain | Source | Authority | Historical strategy |
|---|---|---|---|
| DrillPipe | vendor xlsx + persisted catalog | authoritative | fingerprint where identity holds |
| Casing | dialog `CASING_DB` | preset | numeric snapshot |
| Cement | direct user inputs | manual | numeric snapshot |
| Well Control (kill sheet) | preset / catalog / manual pipe program | mixed | numeric snapshot, **no** fingerprint |

## AA. Search / Retrieval / Evidence

Unchanged. Calculations remain outside Search/Retrieval/EvidenceBundle/
CitationAuditor.

## AB. Dead / duplicate / abandoned

* `dialogs/calculator_dialog.py::DrillingCalculatorDialog` has its own KILL SHEET
  section and is instantiated from `main_window.py` (L2456). Classified **ACTIVE
  (separate legacy entry point)**, NOT a duplicate of the W13 kill sheet — out of
  scope; left untouched (§60/§63).
* No dead/duplicate kill-sheet compute path in the W13 stack. Nothing deleted.

## AC. Dependencies

None added.

## AD. Tests (exact)

New:
* `tests/test_well_control_kill_sheet_persistence.py` — 19 (snapshot/round-trip,
  CRUD, whole-result verification incl. nested-list & schedule drift, corruption,
  immutability, independence, method-change flag, summary columns).
* `tests/test_well_control_kill_sheet_cross_process.py` — 3 (fresh-process
  reconstruction MATCH, table auto-provision on existing DB, existing-records
  survival).
* `tests/test_well_control_kill_sheet_history_viewmodel.py` — 3 (Qt-free
  view-model projection).
* `tests/test_well_control_kill_sheet_save_widget_smoke.py` — 1 (subprocess UI:
  real handler save + reload MATCH + historical independence + history dialog).

Commands / outcomes:
* Focused: `test_well_control_kill_sheet*.py` + three-calc + verification-core →
  97 passed.
* `compileall` on all changed modules → OK.
* Full suite → **1186 passed, 4 skipped** (was 1160/4; +26 new; zero
  regressions).

## AE. Remaining debt (evidence-backed)

* The legacy `DrillingCalculatorDialog` kill sheet still contains inline
  engineering (separate entry point; not migrated — out of scope).
* `w13_Engineering_Calculator.py` (4790 lines) and `database.py` (9449 lines)
  exceed the 3000-line advisory (pre-existing warning in `test_release.py`; not a
  failure).
* The simplified annulus model (last casing ID for the whole string) is a
  documented, deliberately preserved modelling boundary — historical
  reproducibility, not a model redesign.

## AF. Git

Files changed: `core/database.py`, `core/engineering/well_control_kill_sheet.py`
(added `values` correctness projection), `tabs/w13_Engineering_Calculator.py`
(Save/History wiring) — modified; `well_control_kill_sheet_persistence.py`,
`well_control_kill_sheet_repository.py`,
`well_control_kill_sheet_history_dialog.py`, 4 test files, this audit — added.
`.github/workflows/` left untracked/untouched.

## AG. Final decision — PROCEED

Well Control Kill Sheet is a trustworthy, reproducible historical engineering
calculation and is now DrillMaster's fourth persistent calculation. The fourth
concrete implementation confirms the abstraction beyond the shared Verification
Core has NOT been earned — implementations stay concrete.
