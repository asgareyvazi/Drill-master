# MSE Save-Gating Decoupling + Mud Volume Sixth Persistent Calculation

**Date:** 2026-09-19
**Branch:** `arena/01a085e0-drill-master`
**Baseline verified at:** `f225fbf` (MSE fifth persistent calculation)
**Scope:** Two tracks. (A) Determine whether the reported MSE Save gating behind
Bit Hydraulics/nozzles is a real engineering dependency or an accidental UI
coupling, and fix it only if accidental. (B) Qualify and, if justified, implement
Mud Volume as the sixth persistent engineering calculation. Then use six real
calculations to reassess whether any abstraction beyond the Verification Core is
now earned.

---

## A. Executive Verdict — **CERTIFIED WITH DOCUMENTED DEBT**

Track A: the MSE Save gating was an **ACCIDENTAL UI/workflow coupling**, not an
engineering dependency — MSE's engine consumes only WOB/RPM/torque/ROP/bit-size,
none of the nozzle/TFA/bit-hydraulics state, yet the MSE computation sat behind
`_bit_calculate`'s `if tfa <= 0: return "Add nozzles first"` gate. Fixed by
extracting a standalone `_mse_calculate` with its own "Calculate MSE" button; the
exact engine call is unchanged and the bit-hydraulics flow still triggers MSE.
Track B: Mud Volume **balance** passed forensic qualification and is implemented
as calculation #6 with the proven concrete pattern. The architecture decision
remains **VERIFICATION CORE ONLY**. Full suite **1242 passed / 4 skipped /
0 failed** (+23 over 1219).

---

## B. Repository Identity

* Branch `arena/01a085e0-drill-master`; remote `origin`
  (`github.com/asgareyvazi/Drill-master`).
* **No stale-ref trap this session:** HEAD = remote tip = `f225fbf` (0 ahead /
  0 behind). Working tree clean except pre-existing untracked `.github/` (left
  untouched).
* Parent of the new commit: `f225fbf`.

---

## C. Previous-Report Verification

| Claim | Evidence | Status |
|---|---|---|
| 5 persistent calcs (T&D/Casing/Cement/Kill Sheet/MSE) | records + repos + 99 baseline tests green | VERIFIED |
| Only `calculation_verification.py` shared | grep; five concrete persistence modules | VERIFIED |
| No generic calc/snapshot/history/repo/reference/composite framework | source inspection | VERIFIED |
| MSE mature Teale, 5-arg boundary, deterministic, direct inputs, no fingerprint | `mse.py` re-read | VERIFIED |
| **MSE Save reachable only after full Bit Hydraulics run (needs nozzles)** | `_bit_calculate` early-returns on `tfa<=0` before MSE block | VERIFIED (and now fixed) |
| Mud Volume candidate #6 (mature engine, direct inputs, deterministic, snapshot-ready) | `mud_volume.py` + empirical determinism/immutability check | VERIFIED |
| Commit `f225fbf` | `git rev-parse` = remote tip | VERIFIED |

---

## D. Five-Calculation Baseline

Focused persistence suites for T&D, Casing, Cement, Kill Sheet, MSE + the shared
verification core + MSE cross-process ran green (99 tests) before any change. No
prior engine or persistence module was modified.

---

## E. MSE Save-Gating Forensics

| MSE state | Bit Hydraulics required? | Nozzles required? | MSE numerically uses it? | Save allowed? | Justified? |
|---|---|---|---|---|---|
| Before fix | yes (implicit) | yes (`tfa>0`) | **no** | only after bit-hydraulics run | **NO** |
| After fix | no | no | no | after any successful MSE calc | yes |

**Evidence:** `tabs/w13_Engineering_Calculator.py::_bit_calculate` computes TFA
from `self.bit_nozzles`; if `tfa <= 0` it sets "Add nozzles first" and
`return`s — **before** the MSE block. MSE's inputs
(`wob_lbf/rpm/torque_ft_lbf/rop_ft_hr/bit_diameter_in`) are read from separate
widgets (`bit_wob/bit_rpm/bit_tq/bit_rop/bit_od`) and contain no
nozzle/TFA/bit-hydraulics value. The coupling was purely that MSE shared the
`_bit_calculate` code path after the nozzle gate.

---

## F. MSE Gating Decision — **ACCIDENTAL — FIXED**

Extracted a standalone `_mse_calculate` method (identical engine call, same
single WOB klbf→lbf conversion owner) and added a dedicated "🔄 Calculate MSE"
button. `_bit_calculate` now calls `self._mse_calculate()` in place of the inline
block, so:

* MSE computes and saves with **no nozzles / no bit hydraulics**.
* The full bit-hydraulics flow still computes and caches MSE unchanged.
* **No MSE formula changed; no bit-hydraulics change; no generic UI state
  manager; no W13 redesign.**

---

## G. MSE Regression

`tests/test_mse_save_widget_smoke.py` extended to prove all three:
(1) MSE computes + saves + verifies MATCH with `bit_nozzles = []` (decoupling);
(2) the bit-hydraulics flow (with nozzles) still renders and still caches+saves
MSE; (3) no-run save is a no-op. Plus the 18 Qt-free MSE persistence tests and
MSE cross-process still pass. Persisted MSE records unchanged.

---

## H. Cross-Calculation Coupling Inventory (§10/§45)

| Calculation | Save gated on | Type | Evidence | Action |
|---|---|---|---|---|
| MSE | (was) nozzles/TFA via `_bit_calculate` | **ACCIDENTAL** | engine ignores nozzles | **FIXED** |
| T&D | directional survey present | REQUIRED | engine needs survey → MISSING_INPUT otherwise | none |
| Casing | own `CasingEngine.evaluate` success | REQUIRED | gated only on its own inputs | none |
| Cement | own `CementEngine.job_volumes` success | REQUIRED | gated only on its own inputs | none |
| Kill Sheet | own composite success | REQUIRED | gated only on its own inputs | none |
| Mud Volume | own `MudVolumeEngine.balance` success | REQUIRED | gated only on its own inputs | none (new) |

MSE was the **only** accidental cross-calculation coupling. No global refactor.

---

## I. Mud Volume Architecture

* **Engine:** `core/engineering/engines/mud_volume.py` →
  `MudVolumeEngine.balance(cls, active_volume_bbl, additions_bbl=0, losses_bbl=0,
  transfers_in_bbl=0, transfers_out_bbl=0, returns_bbl=0, dilution_bbl=0,
  dumped_bbl=0)`. `METHOD = "Mass/volume balance; no hidden defaults"`.
  (The engine also has `weight_up`/`dilution`/`mix`; **balance** is the volume
  calculation and the persistence target.)
* **Formula:** `final = active + additions + transfers_in + returns + dilution −
  losses − transfers_out − dumped`; `net_change = final − active`.
* **Call graph:** W13 `_create_mud_tab` → new "⚖️ Volume Balance" sub-tab →
  `_mud_balance` reads 8 widgets → `MudVolumeEngine.balance(**inputs)` → displays
  + caches `_mud_bal_last_run`; Save/History via `_mud_bal_save_calculation` /
  `_mud_bal_open_history`. Pre-existing production caller:
  `tabs/w3_drilling_report.py::update_mud_volumes` (debug-logs only — proves real
  usage but no display/persistence there).
* **New files:** `core/engineering/mud_volume_persistence.py`,
  `core/repositories/mud_volume_repository.py`,
  `dialogs/mud_volume_history_dialog.py`, `MudVolumeCalculationRecord`.

---

## J. Mud Volume Input Contract

| Engine input | UI source | Canonical field | Unit | Transform | Default | Required | Persist |
|---|---|---|---|---|---|---|---|
| `active_volume_bbl` | `mud_bal_active` | same | bbl | none | — | yes | yes |
| `additions_bbl` | `mud_bal_add` | same | bbl | none | 0.0 | no | yes |
| `losses_bbl` | `mud_bal_loss` | same | bbl | none | 0.0 | no | yes |
| `transfers_in_bbl` | `mud_bal_tin` | same | bbl | none | 0.0 | no | yes |
| `transfers_out_bbl` | `mud_bal_tout` | same | bbl | none | 0.0 | no | yes |
| `returns_bbl` | `mud_bal_ret` | same | bbl | none | 0.0 | no | yes |
| `dilution_bbl` | `mud_bal_dil` | same | bbl | none | 0.0 | no | yes |
| `dumped_bbl` | `mud_bal_dump` | same | bbl | none | 0.0 | no | yes |

Every engine argument accounted for; no invented fields. Engine rejects negative
values and `None`/bool/NaN/inf via `require_number`.

---

## K. Mud Volume Unit Contract

**No conversion exists.** All eight inputs are in bbl and pass straight to the
engine; the result is in bbl. The snapshot stores bbl. There is nothing to double-
or mis-convert.

---

## L. Hidden Inputs

None. `balance` is a pure function of its eight arguments with no constants,
globals, environment reads, current-UI reads, mutable state, or reference
lookups. (Verified empirically: input mapping unchanged after the call.)

---

## M. Determinism

* Repeated same-process → identical (`test_determinism_repeated_and_serialized`).
* Interleaved with an unrelated `balance` call → identical.
* Serialization round trip (`snapshot→json→snapshot→engine`) → identical.
* Fresh process → `test_mud_volume_cross_process.py` reconstructs → MATCH.
* Input immutability → `test_engine_does_not_mutate_input_mapping`.

---

## N. Result Contract

Flat `values` dict: an echo of the eight inputs PLUS derived `final_volume_bbl`
and `net_change_bbl` — all CORRECTNESS-RELEVANT, none UI-only/diagnostic. The
whole dict is persisted in `result_json` and compared by `deep_numeric_diff`.
Promoted summary columns: `active_volume_bbl`, `final_volume_bbl`,
`net_change_bbl`. A tampered non-headline field is caught
(`test_verify_detects_tampered_secondary_field`).

---

## O. Snapshot

```
{"schema_version": 1,
 "method": "Mass/volume balance; no hidden defaults",
 "parameters": {8 bbl terms}}
```

Deterministic, JSON-serializable, UI-independent, engine-compatible.
`_ENGINE_PARAMS` asserted equal to the engine signature. An older partial
snapshot (only `active_volume_bbl`) reconstructs exactly because the seven
optionals default to `0.0`, matching the engine contract
(`test_old_partial_snapshot_defaults_optionals_to_zero`).

---

## P. Reference Semantics

| Concern | Value |
|---|---|
| Source | direct engineering volumes (bbl) |
| Authority | MANUAL (direct W13 user inputs) |
| Provenance | none (no catalog/preset) |
| Identity | numeric snapshot only |
| Fingerprint | **none** (would be misleading) |
| Historical strategy | frozen numeric snapshot fully reconstructs the run |

---

## Q. Persistence Decision — **IMPLEMENTED**

Real usage (production `balance` caller in w3; a first-class W13 worksheet added),
deterministic pure engine, clean input boundary, complete flat result, no
misleading reference → all qualification gates pass. Historical value: volume-
balance runs are worth reviewing/comparing across a well's life.

---

## R. Persistence Architecture

* **Model:** `MudVolumeCalculationRecord` (`mud_volume_calculations`, 13 cols) —
  concrete, not a shared base.
* **Repository:** `MudVolumeCalculationRepository` (`save_run`/`get`/`all`/`count`)
  + detached `SavedMudVolumeCalculation` (`recalculate`/`verify`).
* **Save semantics:** each `save_run` is a distinct immutable run — never
  deduplicated. Single `session_scope` unit of work.
* **Ownership:** one authoritative path — W13 → repository → DB; history reads
  the same records.

---

## S. Historical Reconstruction

Cross-process: save in interpreter A → reload+recompute in interpreter B → MATCH,
identical `final_volume_bbl`/`net_change_bbl`
(`test_mud_volume_cross_process.py::test_reconstruct_in_fresh_process`).

---

## T. Verification (all four states)

| State | Test |
|---|---|
| MATCH | `test_verify_match`, cross-process |
| DIFFERENT | `test_verify_detects_tampered_secondary_field` |
| NOT_REPRODUCIBLE | `test_verify_not_reproducible_on_missing_required_input` |
| UNREADABLE | `test_verify_unreadable_when_no_stored_result` |
| method drift | `test_verify_method_drift_flag` |

Reuses the shared engine-agnostic core unchanged — no Mud-Volume-specific branch.

---

## U. Mutation Isolation

`test_verify_does_not_mutate_stored_row` (byte-identical stored result after
repeated verify) and `test_saved_run_is_independent_of_later_inputs` (a different
current run does not alter the stored one).

---

## V. Corruption Handling

Missing required input → NOT_REPRODUCIBLE; empty stored result → UNREADABLE;
tampered numeric leaf → DIFFERENT; bool/NaN/inf inputs → cleaned to `None` in the
snapshot (`test_clean_number_rejects_bool_and_nonfinite`). No corrupted data ever
yields MATCH.

---

## W. History UI

`MudVolumeHistoryDialog` (read-only): deterministic newest-first list, empty
state, detail view (frozen 8 inputs + stored result + method + schema version),
observational Verify with colored states + method-drift note. No
edit/delete/overwrite. Qt-free `build_history_rows` unit-tested; full widget flow
via subprocess smoke.

---

## X. Database

* **Fresh DB:** `create_all` builds `mud_volume_calculations`; save/reload/verify
  work (in-memory fixture).
* **Existing DB:** `test_migration_provisions_table_on_existing_db` drops the
  table on a pre-existing DB, runs `_apply_safe_schema_upgrades`, confirms it is
  re-provisioned (13 cols) while `torque_drag_`, `casing_`, `cement_`,
  `well_control_kill_sheet_`, `mse_` tables all survive.
* No destructive migration; no Alembic.

---

## Y. Six-Calculation Architecture Matrix

| Concern | T&D | Casing | Cement | Kill Sheet | MSE | Mud Volume |
|---|---|---|---|---|---|---|
| Input boundary | components + survey | flat scalars | flat + multi-leg | composite (+pipe) | 5 params | 8 bbl terms |
| Snapshot | structured | flat | flat + nested | composite input | 5 params | 8 bbl terms |
| Persistence | concrete | concrete | concrete | concrete | concrete | concrete |
| Result | scalars + per-component | flat scalars | scalars + nested legs + layers | scalars + lists + schedule | flat scalars | flat scalars |
| Reconstruction | snapshot→engine | snapshot→engine | snapshot→engine | snapshot→composite | snapshot→engine | snapshot→engine |
| Verification | shared core | shared core | shared core (nested) | shared core (nested/lists) | shared core | shared core |
| History | concrete dialog | concrete dialog | concrete dialog | concrete dialog | concrete dialog | concrete dialog |
| Failure | MISSING/error | MISSING/error | MISSING/error | ENGINE_FAILED | MISSING/error | MISSING/error |
| Algorithm identity | method + schema_v | method + schema_v | method + schema_v | method + schema_v | method + schema_v | method + schema_v |
| Reference | AUTHORITATIVE + fingerprint | PRESET | MANUAL | MIXED | MANUAL | MANUAL |
| Identity | id handle | id handle | id handle | id handle | id handle | id handle |
| Provenance | catalog-linked | preset | direct | mixed | direct | direct |
| Save semantics | distinct run | distinct run | distinct run | distinct run | distinct run | distinct run |

**Only genuinely shared concern: engine-agnostic whole-result verification.**

---

## Z. Abstraction Decision — **VERIFICATION ONLY**

The strict gate (§36) still fails for any broader abstraction: six snapshot and
result shapes remain materially different (flat vs nested vs composite vs
lists+schedule), reference semantics span AUTHORITATIVE/PRESET/MANUAL/MIXED, and
a shared base would hide those differences rather than reduce complexity. The
repositories share only trivial CRUD names, not semantics. `calculation_
verification.py` is reused unchanged by all six. **Keep concrete.**

---

## AA. Composite Calculation Assessment

1. Is Kill Sheet genuinely a distinct composite category? **Yes** (multiple
   engine calls + derived arithmetic + choke schedule); the other five are each
   a single engine call.
2. Does it justify a framework? **No** — still only one composite example (§37).
   No `CompositeCalculation` abstraction.

---

## AB. Reference Architecture

| Domain | Source | Authority | Fingerprint | Historical strategy |
|---|---|---|---|---|
| DrillPipe | vendor xlsx + catalog | AUTHORITATIVE | yes (where identity holds) | fingerprint |
| Casing | dialog preset | PRESET | no | numeric snapshot |
| Cement | direct inputs | MANUAL | no | numeric snapshot |
| Well Control | preset/catalog/manual pipe program | MIXED | no | numeric snapshot |
| MSE | direct drilling params | MANUAL | no | numeric snapshot |
| Mud Volume | direct volumes | MANUAL | no | numeric snapshot |

Diversity still argues AGAINST a generic reference framework. **None built.**

---

## AC. Calculation #7 Reconnaissance (recon only — not implemented)

| Candidate | Engine | W13 UI | Determinism | Result | Reference risk | Snapshot readiness | Note |
|---|---|---|---|---|---|---|---|
| **Bit cost/ft** | `BitPerformanceEngine.cost_per_foot` | yes (+w12) | pure | scalars | none | high | clean input form; strongest #7 |
| Fishing | `FishingEngine` | yes | pure | SCREENING | legacy chart approx | medium | explicitly SCREENING → weak historical value |
| Hydraulics | `AdvancedHydraulicsEngine` | yes | pure | dict | none | medium | large surface, multiple sub-results |
| Trajectory | `TrajectoryEngine` | yes | pure | series | survey data | low-med | series, not a single claim |
| Anti-Collision | `AntiCollisionEngine` | **no UI** | pure | series | trajectory data | low | no entry point |

**Recommended #7: Bit cost/ft** (clean deterministic form, no reference risk).
Not implemented this iteration.

---

## AD. Dead / Duplicate / Abandoned

* **§44 Mud Volume:** grep for duplicate balance arithmetic outside the engine →
  **CLEAN**. All four `balance()` callers delegate to the engine (bridge, w13,
  w3, persistence). Hits are DB column names / display strings / an old
  audit-evidence file / an unrelated logistics counter.
* **§44 MSE regression:** single formula owner intact (no `120π`/`wob/area`
  outside `mse.py`).
* No dead/obsolete code introduced or found needing deletion.

---

## AE. Dependencies

**None added.** Existing stack only (SQLAlchemy, PySide6, stdlib).

---

## AF. Search / Retrieval / Evidence

Unchanged. No LLM/RAG/agent/vector/search work. Calculations remain outside any
AI layer.

---

## AG. Tests (exact)

New files:
* `tests/test_mud_volume_persistence.py` — 18 (signature↔snapshot; independent
  balance ground truth; snapshot round-trip; old-partial-snapshot defaults;
  bool/NaN rejection; CRUD; distinct runs; ordering; MATCH/DIFFERENT/
  NOT_REPRODUCIBLE/UNREADABLE; method drift; tampered-field guard; row
  immutability; reference independence; determinism; input immutability; summary
  keys).
* `tests/test_mud_volume_cross_process.py` — 2 (fresh-interpreter reconstruction;
  safe schema provisioning with 5 prior tables surviving).
* `tests/test_mud_volume_history_viewmodel.py` — 2.
* `tests/test_mud_volume_save_widget_smoke.py` — 1 (subprocess save flow).

Modified: `tests/test_mse_save_widget_smoke.py` — decoupling regression
(nozzle-free MSE save + bit-hydraulics still works).

Commands / outcomes:
* Focused Mud Volume suites → 23 passed.
* MSE decoupling smoke → passed.
* Baseline five-calc + verification core + MSE cross-process → 99 passed.
* `compileall` on all changed modules → OK.
* Full suite → **1242 passed / 4 skipped / 0 failed / 0 errors** (+23 over 1219).

---

## AH. Remaining Debt (evidence-backed)

* `w3_drilling_report.py::update_mud_volumes` computes a balance but only
  debug-logs it (no display/persistence). Left as-is (out of scope; not a
  correctness defect). The persistable balance now lives in W13.
* `database.py` (9553 lines) / `w13_Engineering_Calculator.py` (5045 lines)
  exceed the 3000-line advisory (pre-existing warning, not a failure).
* Algorithm drift is method+schema detectable, not source-hashed — bounded,
  documented debt consistent with the five prior calculations.

---

## AI. Git

New files: `core/engineering/mud_volume_persistence.py`,
`core/repositories/mud_volume_repository.py`,
`dialogs/mud_volume_history_dialog.py`, four `tests/test_mud_volume_*.py`, this
audit. Modified: `core/database.py` (+`MudVolumeCalculationRecord`),
`tabs/w13_Engineering_Calculator.py` (MSE decoupling + Mud Volume Balance
worksheet/handlers), `tests/test_mse_save_widget_smoke.py` (decoupling
regression). `.github/` untouched.

---

## AJ. Final Decision — **PROCEED WITH DEBT**

Track A: the accidental MSE Save coupling is removed (MSE now computes/saves
independently of nozzles; no formula or bit-hydraulics change). Track B: Mud
Volume is implemented as the sixth concrete historical calculation with full
snapshot / reconstruction / whole-result verification / cross-process
reproducibility / read-only history, no new dependency. Six real calculations
confirm **VERIFICATION ONLY** remains correct. Remaining debt is pre-existing and
non-blocking.
