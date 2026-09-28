# MSE (Teale) — Fifth Persistent Calculation + Five-Calculation Architecture Review

**Date:** 2026-09-19
**Branch:** `arena/01a085e0-drill-master`
**Baseline verified at:** `92b36fa` (Well Control ICP/FCP consolidation)
**Scope:** Qualify and implement Mechanical Specific Energy (Teale 1965) as the
fifth persistent engineering calculation, following the proven
snapshot/reconstruction/whole-result-verification pattern; then use five real
calculations to reassess whether any shared abstraction beyond the Verification
Core is now justified.

---

## A. Executive Verdict — **CERTIFIED WITH DOCUMENTED DEBT**

MSE passed forensic qualification (real W13 production entry point, mature
deterministic Teale engine, clean five-argument input boundary, no misleading
reference dependency, snapshot-ready) and is now implemented as calculation #5:
canonical snapshot → ORM record → repository → cross-process reconstruction →
whole-result verification → read-only history UI. No engine formula changed. The
architecture decision remains **VERIFICATION CORE ONLY** — a fifth concrete
implementation did not create enough semantic overlap to justify a shared
persistence/snapshot/history/repository framework. Full suite **1219 passed /
4 skipped / 0 failed**, +23 over the 1196 baseline.

---

## B. Repository Identity

* Branch: `arena/01a085e0-drill-master`; remote `origin`
  (`github.com/asgareyvazi/Drill-master`).
* **Stale-ref trap recurred** (as in prior sessions): local HEAD started at the
  branch-point `b05ea76`; remote tip was `92b36fa` (33 ahead, 0 behind, no
  unique local commits). Recovered safely with `git fetch` → verified ancestry →
  `git reset FETCH_HEAD` (mixed). No work lost. Working tree clean except the
  pre-existing untracked `.github/` (left untouched).
* HEAD after recovery / before this slice: `92b36fa`.
* Parent of the new commit: `92b36fa`.

---

## C. Previous-Report Verification

| Claim | Evidence | Status |
|---|---|---|
| 4 persistent calcs (T&D/Casing/Cement/Kill Sheet) | records + repos + focused suites green | VERIFIED |
| Only `calculation_verification.py` shared | module read; no engine imports; 4 concrete persistence modules | VERIFIED |
| WC ICP/FCP canonical owners + 3 delegating sites | grep: `calculate_icp/fcp` defined once in `well_control.py`; delegated in `extended.py`, `well_control_kill_sheet.py`, `calculator_dialog.py` | VERIFIED |
| No WC formula changed / test-only extended | `wait_weight_method` delegates; still test-covered | VERIFIED |
| Suite 1196 passed / 4 skipped | rebaselined; this slice starts from it | VERIFIED |
| Commit `92b36fa` | `git rev-parse` confirms as remote tip | VERIFIED |
| MSE = mature Teale engine, W13 entry, single result, deterministic, snapshot-ready, no misleading ref | read `mse.py` + W13 `_bit_calculate`; confirmed | VERIFIED |
| MSE uses 120π not 480 | `TEALE_120_PI = 120π ≈ 376.99`; `480` only in an explanatory comment | VERIFIED |

---

## D. Four-Calculation Baseline

Focused persistence suites for T&D, Casing, Cement, Kill Sheet + the shared
verification core + engineering ground truths ran green (111 tests) before any
change. No prior engine or persistence module was modified by this slice.

---

## E. MSE Architecture (actual)

* **Engine:** `core/engineering/engines/mse.py` → `MSEEngine.calculate(cls, wob_lbf, rpm, torque_ft_lbf, rop_ft_hr, bit_diameter_in) -> EngineeringResult`. `METHOD = "Teale (1965) Mechanical Specific Energy"`, `SCOPE = "COMPLETE"`.
* **Formula:** `MSE = WOB/Ab + (120π · RPM · T)/(Ab · ROP)`, `Ab = π/4 · D²`.
* **Call graph:** W13 `tabs/w13_Engineering_Calculator.py::_bit_calculate` (Bit
  Hydraulics sub-tab) reads widgets → converts WOB klbf→lbf (once) → builds
  `mse_inputs` → `MSEEngine.calculate(**mse_inputs)` → displays `mse.value`;
  now also caches `self._mse_last_run` and offers Save/History. Also reachable
  via `CalculatorBridge.mse` (AI tool `calculate_mse`) — read-only, not persisted.
* **New files:** `core/engineering/mse_persistence.py`,
  `core/repositories/mse_repository.py`, `dialogs/mse_history_dialog.py`,
  `MSECalculationRecord` in `core/database.py`.

---

## F. MSE Input Contract

| Engine arg | Runtime source | W13 field | Snapshot field | Unit | Default | Required | Persist |
|---|---|---|---|---|---|---|---|
| `wob_lbf` | `self.bit_wob.value()*1000` | WOB | `wob_lbf` | lbf (UI shows klbf) | none | yes | yes |
| `rpm` | `self.bit_rpm.value()` | RPM | `rpm` | rev/min | none | yes | yes |
| `torque_ft_lbf` | `self.bit_tq.value()` | Torque | `torque_ft_lbf` | ft·lbf | none | yes | yes |
| `rop_ft_hr` | `self.bit_rop.value()` | ROP | `rop_ft_hr` | ft/hr | none | yes (>0) | yes |
| `bit_diameter_in` | `self.bit_od.value()` | Bit Size | `bit_diameter_in` | in | none | yes (>0) | yes |

Every engine argument is accounted for; no input is invented. `require_number`
rejects `None`/blank/bool/NaN/inf (no silent zero substitution).

---

## G. MSE Unit Conversion (single owner per quantity)

Only ONE conversion exists: **WOB klbf → lbf (×1000)**, owned by W13
`_bit_calculate` and applied ONCE before both the engine call and the snapshot
build. All other inputs pass through in canonical oilfield units (rpm, ft·lbf,
ft/hr, in) with no conversion. The snapshot therefore stores canonical engine
units, so reconstruction needs no conversion. No double/missing conversion; no
hidden conversion inside the engine.

---

## H. Hidden Inputs

| Hidden value | Location | Affects result? | Mutable? | Historical strategy |
|---|---|---|---|---|
| `TEALE_120_PI = 120π` | `mse.py` module constant | yes (rotary term) | no (algorithm constant) | ALGORITHM constant — stays in engine; drift detectable via `method` + `schema_version` |
| `π/4` bit-area factor | `mse.py` | yes | no | ALGORITHM constant — stays in engine |

No environment values, no current-UI reads, no mutable class state, no reference
lookups. The engine is a pure function of its five arguments.

---

## I. Determinism (tests + results)

* **Repeated (same process):** `test_determinism_repeated_and_serialized` — v1 == v2.
* **Interleaved:** an unrelated MSE call runs between the two; result unchanged.
* **Serialization round trip:** `snapshot → json → snapshot → engine` reproduces mse_psi.
* **Fresh process:** `test_mse_cross_process.py::test_reconstruct_in_fresh_process` — save in interpreter A, reload+recompute in interpreter B → MATCH, identical mse/axial/rotary.
* **Input immutability:** `test_engine_does_not_mutate_input_mapping` — the input mapping is unchanged after `calculate`.

---

## J. Result Contract (whole result persisted)

`MSEEngine.calculate` returns a flat `values` dict; classification:

| Field | Class |
|---|---|
| `mse_psi` | CORRECTNESS-RELEVANT (headline) |
| `axial_term_psi`, `rotary_term_psi` | CORRECTNESS-RELEVANT (decomposition) |
| `bit_area_in2` | CORRECTNESS-RELEVANT (derived) |
| `wob_lbf`, `rpm`, `torque_ft_lbf`, `rop_ft_hr`, `bit_diameter_in` | input echo (correctness-relevant, verified by deep diff) |

The entire `values` dict is persisted in `result_json` and compared whole by
`deep_numeric_diff`. Promoted summary columns: `mse_psi`, `axial_term_psi`,
`rotary_term_psi`, `bit_area_in2`. A false MATCH is impossible: a tampered
non-headline field (`rotary_term_psi`) is caught by verification
(`test_verify_detects_tampered_secondary_field`).

---

## K. Snapshot

```
{"schema_version": 1,
 "method": "Teale (1965) Mechanical Specific Energy",
 "parameters": {"wob_lbf", "rpm", "torque_ft_lbf", "rop_ft_hr", "bit_diameter_in"}}
```

Deterministic, JSON-serializable, UI-independent, engine-compatible. Frozen at
canonical engine units. `_ENGINE_PARAMS` is asserted to equal the engine
signature (`test_snapshot_params_match_engine_signature`) so a drifting input set
is caught.

---

## L. Reference Semantics

| Concern | Value |
|---|---|
| Source | direct drilling parameters (WOB/RPM/torque/ROP/bit diameter) |
| Authority | MANUAL (direct W13 user inputs) |
| Provenance | none (no catalog/preset) |
| Identity | numeric snapshot only |
| Fingerprint | **none** (claiming one would be misleading) |
| Historical strategy | frozen numeric snapshot fully reconstructs the run |

**Bit reference forensics (§25):** W13 `bit_od` is a plain `QDoubleSpinBox`, not
a Bit-catalog lookup. No Bit catalog exists or is created by this slice. MSE is
reproducible from frozen numeric bit diameter alone.

---

## M. Persistence Decision — **IMPLEMENTED**

Real user workflow (post-well drilling-performance review / offset comparison on
the W13 Bit Hydraulics worksheet), mature deterministic engine, clean input
boundary, complete result, no misleading reference → all qualification gates
pass. Persistence adds genuine historical value.

---

## N. Persistence Architecture

* **Model:** `MSECalculationRecord` (`mse_calculations`, 14 columns) — concrete,
  not a shared base.
* **Repository:** `MSECalculationRepository` (`save_run`/`get`/`all`/`count`) +
  detached `SavedMSECalculation` (`recalculate`/`verify`/`input_parameters`).
* **Snapshot/result:** as §K/§J. Summary columns promoted for querying.
* **Save semantics:** each `save_run` is a distinct immutable run — never
  deduplicated (`test_each_save_is_a_distinct_run`). Single `session_scope` unit
  of work; a failure leaves no partial row.
* **Ownership:** one authoritative path — W13 → repository → DB; history reads
  the same records. No engine-side or dialog-side save.

---

## O. Historical Reconstruction

`save_run` → detach → (fresh interpreter) `repo.get(id)` →
`recalculate_from_snapshot` runs the real `MSEEngine.calculate` →
`verify` → MATCH. Verified same-process and cross-process.

---

## P. Verification (all four states exercised)

| State | Test |
|---|---|
| MATCH | `test_verify_match`, cross-process |
| DIFFERENT | `test_verify_detects_tampered_secondary_field` |
| NOT_REPRODUCIBLE | `test_verify_not_reproducible_on_invalid_snapshot` (rop=0), `test_verify_unreadable_on_missing_snapshot_field` (missing WOB → engine `missing()`) |
| UNREADABLE | `test_verify_unreadable_when_no_stored_result` |
| method drift | `test_verify_method_drift_flag` (numbers match, `method_matches=False`) |

Reuses the shared engine-agnostic core unchanged — no MSE-specific branch added.

---

## Q. Historical Immutability

`test_verify_does_not_mutate_stored_row` — repeated verify/recalculate leaves the
stored `result_json` byte-identical. Verification is observational.

---

## R. Mutation / Reference Independence

`test_saved_run_is_independent_of_later_inputs` — after saving, a completely
different "current" run is computed; the stored run still recomputes to its
original value. No current-state coupling.

---

## S. History UI

`MSEHistoryDialog` (read-only): deterministic newest-first list, empty state,
detail view (frozen inputs + stored result + method + schema version), and an
observational Verify button with colored MATCH/DIFFERENT/NOT_REPRODUCIBLE/
UNREADABLE + method-drift note. No edit/delete/overwrite. The Qt-free
`build_history_rows` projection is unit-tested; the full widget flow is a
subprocess smoke test (§AC).

---

## T. Database

* **Fresh DB:** `Base.metadata.create_all` builds `mse_calculations`; save/reload/verify work (in-memory fixture, all persistence tests).
* **Existing DB:** `test_migration_provisions_table_on_existing_db` drops the
  table on a pre-existing DB, runs `_apply_safe_schema_upgrades`, and confirms
  `mse_calculations` is re-provisioned (14 cols) while `torque_drag_`,
  `casing_`, `cement_`, `well_control_kill_sheet_` tables all survive.
* No destructive migration; no Alembic; follows the existing safe-upgrade
  convention (new ORM tables auto-created from `Base.metadata.sorted_tables`).

---

## U. Five-Calculation Architecture Matrix

| Concern | T&D | Casing | Cement | Kill Sheet | MSE |
|---|---|---|---|---|---|
| Input boundary | components + survey | flat scalars | flat scalars + multi-leg program | composite canonical input (+pipe program) | 5 flat drilling params |
| Snapshot | structured (components/survey) | flat | flat + nested construction | composite canonical input | 5 flat params |
| Persistence | concrete record | concrete record | concrete record | concrete record | concrete record |
| Result | scalars + per-component | flat scalars | scalars + nested legs + layer list | scalars + string/annular lists + choke schedule | flat scalars (decomposed) |
| Reconstruction | snapshot→engine | snapshot→engine | snapshot→engine | snapshot→composite | snapshot→engine |
| Verification | shared core | shared core | shared core (nested) | shared core (nested/lists) | shared core |
| History | concrete dialog | concrete dialog | concrete dialog | concrete dialog | concrete dialog |
| Failure | MISSING/error | MISSING/error | MISSING/error | ENGINE_FAILED composite | MISSING/error (rop>0) |
| Algorithm identity | method + schema_v | method + schema_v | method + schema_v | method + schema_v | method + schema_v |
| Identity | id handle | id handle | id handle | id handle | id handle |
| Provenance | catalog-linked (DrillPipe) | preset | direct | mixed (preset/catalog/manual) | direct |
| Reference | AUTHORITATIVE catalog + fingerprint | PRESET, no fingerprint | MANUAL, no fingerprint | MIXED, no fingerprint | MANUAL, no fingerprint |
| Save semantics | distinct run | distinct run | distinct run | distinct run | distinct run |

**Only genuinely shared concern: engine-agnostic whole-result verification.**
Everything else (input boundary, snapshot shape, result shape, reference
semantics, history fields) differs materially.

---

## V. Abstraction Decision — **VERIFICATION ONLY**

Strict gate (§43) fails for a shared persistence abstraction: the five snapshot
and result shapes are materially different (flat vs nested vs composite vs
lists+schedule), reference semantics span AUTHORITATIVE/PRESET/MANUAL/MIXED, and
a shared base would hide those differences rather than reduce complexity. The
repositories share only trivial CRUD names, not semantics. **Keep concrete.**
The one proven shared contract — `calculation_verification.py` — is reused
unchanged by all five.

---

## W. Composite Calculation Assessment

1. Is Kill Sheet a genuinely distinct composite category? **Yes** — it runs
   multiple engine calls plus derived arithmetic and a choke schedule; T&D,
   Casing, Cement and MSE are each a single engine call.
2. Does that justify a composite framework? **No** — one composite example is
   insufficient (§72). No `CompositeCalculation` abstraction introduced.

---

## X. Reference Architecture Assessment

Reference diversity across five calculations (AUTHORITATIVE catalog with
fingerprint / PRESET / MANUAL / MIXED) still argues AGAINST a generic reference
framework. MSE adds another MANUAL-direct case. **No generic reference framework
justified.**

---

## Y. Calculation #6 Inventory (recon only — not implemented)

| Candidate | Engine | W13 UI | Determinism | Result | Reference risk | Snapshot readiness | Note |
|---|---|---|---|---|---|---|---|
| **Mud Volume** | `MudVolumeEngine` (balance/weight_up/dilution/mix) | yes (+w3) | pure | single result | none (direct) | **high** | strongest #6 candidate |
| Bit cost/ft | `BitPerformanceEngine.cost_per_foot` | yes (+w12) | pure | scalars | none | medium | inputs are a clean form; roll-up variants pull DDR data |
| Hydraulics | `AdvancedHydraulicsEngine` | yes | pure | dict | none | medium | large surface; multiple sub-results |
| Fishing | `FishingEngine` | yes | pure | SCREENING | legacy chart approximations | medium | explicitly SCREENING → weak historical value |
| Trajectory | `TrajectoryEngine` | yes | pure | series | survey data | low-med | series result, not a single claim |
| Anti-Collision | `AntiCollisionEngine` | **no UI** | pure | series | trajectory data | low | no entry point |

**Recommended #6: Mud Volume** (mature engine, clean direct inputs, deterministic
single result, no misleading reference, high snapshot readiness). Not implemented
this iteration.

---

## Z. Duplicate / Legacy Forensics

* **§50 MSE:** grep for duplicate Teale/`120π`/`480`/`wob/area` arithmetic
  outside `engines/mse.py` → **CLEAN** (no live duplicate). `480` appears only in
  an explanatory comment. Single formula owner.
* **§51 WC regression:** `calculate_icp`/`calculate_fcp` defined once in
  `well_control.py`; all three production sites (`extended.py`,
  `well_control_kill_sheet.py`, `calculator_dialog.py`) still delegate. No
  duplicate WC arithmetic re-introduced.

---

## AA. Search / Retrieval / Evidence / AI

Unchanged. No LLM/RAG/agent/vector/search work (§55). Calculations remain outside
any AI layer. The existing `calculate_mse` AI tool is read-only and untouched.

---

## AB. Dependencies

**None added** (§56). Uses only the existing stack (SQLAlchemy ORM, PySide6, stdlib).

---

## AC. Tests (exact)

New files:
* `tests/test_mse_persistence.py` — 18 (signature↔snapshot contract; independent
  Teale ground truth; snapshot round-trip; bool/NaN rejection; CRUD; distinct
  runs; deterministic ordering; MATCH/DIFFERENT/NOT_REPRODUCIBLE/UNREADABLE;
  method drift; tampered-field false-MATCH guard; row immutability; reference
  independence; determinism; input immutability; summary keys).
* `tests/test_mse_cross_process.py` — 2 (fresh-interpreter reconstruction → MATCH;
  safe schema provisioning on existing DB with 4 prior tables surviving).
* `tests/test_mse_history_viewmodel.py` — 2 (Qt-free row projection; empty/missing).
* `tests/test_mse_save_widget_smoke.py` — 1 (subprocess: W13 no-run no-op; drive
  `_bit_calculate` with nozzles; WOB klbf→lbf owned by UI; save; reload; verify MATCH).

Commands / outcomes:
* Focused MSE suites → 23 passed.
* Baseline four-calc + verification-core + ground truth → 111 passed.
* `compileall` on all changed modules → OK.
* Full suite → **1219 passed / 4 skipped / 0 failed / 0 errors** (+23 over 1196).

---

## AD. Database (schema changes + validation)

* Added table `mse_calculations` (14 cols: id, well_id, label, method,
  snapshot_schema_version, input_snapshot_json, result_json, mse_psi,
  axial_term_psi, rotary_term_psi, bit_area_in2, created_at, updated_at,
  created_by).
* No change to any existing table. Fresh-DB and existing-DB provisioning both
  validated (§T). No destructive migration.

---

## AE. Remaining Debt (evidence-backed)

* MSE persistence is offered on the Bit Hydraulics worksheet, which requires
  nozzles (TFA>0) to reach the calculation — MSE saving is only available after a
  full bit-hydraulics run. Acceptable (matches existing workflow), noted.
* `database.py` (9502 lines) / `w13_Engineering_Calculator.py` (4890 lines)
  exceed the 3000-line advisory (pre-existing warning, not a failure).
* Algorithm drift is detectable (method + schema_version) but not source-hash
  enforced — bounded, documented debt (§65), consistent with the four prior
  calculations. No source-hash system invented.

---

## AF. Git

New files: `core/engineering/mse_persistence.py`,
`core/repositories/mse_repository.py`, `dialogs/mse_history_dialog.py`,
`tests/test_mse_persistence.py`, `tests/test_mse_cross_process.py`,
`tests/test_mse_history_viewmodel.py`, `tests/test_mse_save_widget_smoke.py`,
this audit. Modified: `core/database.py` (+`MSECalculationRecord`),
`tabs/w13_Engineering_Calculator.py` (cache run + Save/History buttons +
handlers). `.github/` left untouched. Working tree otherwise clean.

---

## AG. Final Decision — **PROCEED WITH DEBT**

MSE is implemented as the fifth concrete historical engineering calculation with
full snapshot / reconstruction / whole-result verification / cross-process
reproducibility / read-only history, no formula change, and no new dependency.
The proven shared Verification Core is preserved and reused; five real
calculations confirm **VERIFICATION ONLY** remains the correct architecture. The
only remaining debt is pre-existing (large files, non-source-hash drift
detection) and non-blocking.
