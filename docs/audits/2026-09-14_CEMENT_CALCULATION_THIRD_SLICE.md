# Calculation #3 (Cement Job Volumes) + Cross-Calculation Contract Audit

**Date:** 2026-09-14
**Branch:** `arena/01a085e0-drill-master`
**Baseline HEAD at start:** `b5f2e74` (remote session head; full suite 1125 passed / 4 skipped)
**Audit type:** Independent re-verification + third concrete vertical slice.

---

## A. Executive Verdict

**`CERTIFIED WITH DOCUMENTED DEBT`.** Calculation #3 = **Cement Job Volumes**
(`CementEngine.job_volumes`) is implemented as a real, deterministic,
historically-reproducible persistent calculation with whole-result verification,
mirroring the proven T&D/Casing principles as an INDEPENDENT concrete slice. The
shared abstraction remains **verification-only** — the third implementation
confirms (rather than assumes) that snapshot/reconstruction/repository/history
semantics are genuinely divergent and must stay concrete. The confirmed Casing
UI wording debt was also corrected.

## B. Repository Identity

| Property | Value |
|----------|-------|
| Branch | `arena/01a085e0-drill-master` |
| Local HEAD at start | `b05ea76` (stale local pointer — see recovery note) |
| Real remote head | `b5f2e74` (fetched by name; descendant of `b05ea76`) |
| Remote | `https://github.com/asgareyvazi/Drill-master.git` |
| Working tree after recovery | clean (only `.github/workflows/` untracked, `.venv` gitignored) |

**Git recovery note (mission §3):** as in the prior session, the local checkout
pointed at the branch-point with stale remote-tracking refs. Handled safely: no
hard reset; `git fetch origin arena/01a085e0-drill-master` revealed real head
`b5f2e74`; I verified the working tree was **byte-identical** to it (every
tracked path hashed equal) and that the only unique untracked file was the
pre-existing `.github/workflows/ci.yml`; then a non-destructive `git reset`
(mixed) moved the pointer to `b5f2e74` with no content loss.

## C. Previous Report Verification

| Claim | Evidence | Status |
|-------|----------|--------|
| Casing catalog NOT justified; `CASING_DB` is display-only preset | `_csg_select_from_db` copies only od/id/weight; engine computes ratings | ✅ TRUE |
| CasingEngine ignores stored burst/collapse | `CasingEngine.evaluate` derives all ratings from geometry+yield | ✅ TRUE |
| T&D + Casing persistent & reproducible | 67 targeted tests pass; cross-process reconstruct MATCH | ✅ TRUE |
| Shared engine-agnostic verification core exists | `calculation_verification.py` stdlib-only imports | ✅ TRUE |
| Broader abstraction rejected; no generic framework | No base calc classes; 3 concrete modules | ✅ TRUE |
| Search/Retrieval/Evidence untouched | no calc-persistence references there | ✅ TRUE |
| Calculation #3 deferred | was deferred; now implemented this slice | ✅ TRUE (now actioned) |
| Casing wording debt (`Select Casing from API 5CT Database`) | Found verbatim at w13:3103 | ✅ TRUE → fixed (§H) |
| Full suite 1125 passed / 4 skipped | Re-ran independently: 1125/4 | ✅ TRUE |

## D. Torque & Drag Revalidation

`test_torque_drag_persistence` + `test_torque_drag_history` pass. Snapshot =
survey stations + component specs (each carrying a `reference_fingerprint` for
catalog traceability); reconstruction strips fingerprint metadata before
re-running the engine; whole-result verification via shared core; history UI
present. Not modified in this slice.

## E. Casing Revalidation

`test_casing_persistence` (18) + cross-process (2) + history view-model (2) pass.
Snapshot = 19 flat scalar engine kwargs + `grade`; no reference fingerprint (by
honest design); whole-result verify; history UI present. Not modified except the
UI wording (§H).

## F. Shared Verification Contract

`core/engineering/calculation_verification.py` — imports only `math`,
`dataclasses`, `typing` (no engine/Qt/UI). Contract derived from code:

```
recalc.success is False                      → NOT_REPRODUCIBLE (engine could not run snapshot)
recalc.success and stored_result is empty    → UNREADABLE       (nothing to verify against)
recalc.success and deep_numeric_diff == []   → MATCH            (whole result reproduced)
recalc.success and deep_numeric_diff != []   → DIFFERENT        (any numeric leaf diverged)
snapshot_method != current_method            → method_matches=False (reported alongside, never collapsed)
```

`deep_numeric_diff` recurses through mappings, lists (element-wise with
path `key[i]`), booleans (exact), and numeric leaves (abs tol 1e-6), ignoring
textual metadata keys. The four states and `method_matches` are never collapsed.
**Cement stresses this core further than the prior two**: its result contains
nested `lead`/`tail` dicts and a `stacked_hydrostatic.layers` list-of-dicts, and
tests prove drift at `lead.slurry_bbl` and `stacked_hydrostatic.layers[0].psi`
is caught as DIFFERENT — a genuine whole-result claim, not a summary claim.

## G. Cross-Calculation Contract Comparison

| Concern | T&D | Casing | Cement | Shared? |
|---------|-----|--------|--------|---------|
| Input snapshot | survey array + component list | 19 flat scalars + grade | 31 flat scalars | **NO — concrete** |
| Reconstruction | rebuild survey+components, strip fp | flat kwargs | flat kwargs | NO — concrete |
| Result persistence | full `.values` (arrays) | full `.values` (flat) | full `.values` (nested dicts+list) | NO — concrete shapes |
| Result verification | `deep_numeric_diff` | `deep_numeric_diff` | `deep_numeric_diff` | **YES — shared core** |
| Verification states | VERIFY_* | VERIFY_* | VERIFY_* | **YES — shared** |
| Algorithm identity | method + schema_version | method + schema_version | method + schema_version | pattern shared, values concrete |
| Reference identity | fingerprint per component | none (honest) | none (honest) | **divergent by design** |
| Provenance | DrillPipe catalog seam | none | none | divergent |
| History dialog | concrete | concrete | concrete | pattern shared, code concrete |
| Failure/corruption states | 4 states | 4 states | 4 states | **YES — shared core** |
| Save semantics | one session_scope, no dedup | same | same | pattern shared |

Only verification (states + deep diff + outcome object) is genuinely shared and
already extracted. Everything else is provably divergent — three different input
classes and three different result shapes.

## H. Casing Wording Fix (§14)

Confirmed verbatim: `"📋 Select Casing from API 5CT Database"` (w13:3103) over a
hard-coded preset. Changed to `"📋 Select Casing Preset"` with a tooltip stating
the presets are convenience values, not an authoritative catalog, and the group
box to "select a preset or enter values". Also relabeled the copied burst/collapse
result hints from "(from API)" to "(preset ref)". No behavioral/data change; no
test depended on the old string; full suite still green.

## I. Calculation #3 Inventory

| Engine | File | UI path | Determinism | Input | Result | Ref coupling | Tests | Maturity |
|--------|------|---------|-------------|-------|--------|--------------|-------|----------|
| **Cement** | `engines/cement.py` | W13 `_csg_calc_cement` | 0 nondeterminism markers; verified | scalars (geometry+program) | scalars + nested legs + layer list | **none** (direct values) | ground-truth tests exist | COMPLETE scope |
| Well Control | `engines/well_control.py` | W13 `_wc_calc_kill` (+choke/hp/kt/trip) | clean | scalars + **mutable pipe list** built UI-side | scalars | none | some | multi-engine handler; snapshot risk |
| Mud Volume | `engines/mud_volume.py` | W13 `_mud_wu/_mud_dil/_mud_mix` | clean | scalars | scalars | none | some | many small handlers |
| MSE | `engines/mse.py` | W13 `_create_...`/MSE | clean | 5 scalars | ~9 scalars | none | some | trivial (low historical value) |
| Bit Performance | `engines/bit_performance.py` | W13 | clean | run/report rows | scalars | report state | yes | report-coupled |
| Anti-Collision | `engines/anti_collision.py` | not clearly wired in W13 | clean | survey pairs | complex | survey | some | SCREENING scope |
| Fishing | `engines/fishing.py` | W13 fishing handlers | clean | scalars | scalars | none | some | SCREENING scope |

## J. Candidate Ranking

| Candidate | Real engine | User value | Determinism | Snapshot difficulty | Result difficulty | Ref risk | Tests | Arch risk | Recommendation |
|-----------|-------------|-----------|-------------|--------------------|--------------------|----------|-------|-----------|----------------|
| **Cement** | ✅ single call | High (every casing job) | ✅ pure | Low (1 kwargs dict) | Medium (nested — good core test) | None | ground-truth | Low | **IMPLEMENT** |
| Well Control | ✅ but multi-engine | High (safety) | ✅ | **High** (UI-side pipe list + unit conversions before engine) | Medium | None | partial | Medium-High | Defer (snapshot-completeness risk) |
| Mud Volume | ✅ | Medium | ✅ | Low | Low | None | partial | Low | Viable later |
| MSE | ✅ | Low-Med | ✅ | Trivial | Low | None | yes | Low | Low value |

Cement wins on engineering value × maturity × a *single clean engine call* whose
inputs fully determine the result. Well Control was explicitly rejected for now:
its W13 handler mixes several engines and does significant unit-conversion /
mutable-pipe-list assembly *before* the engine, so an honest, complete snapshot
would require refactoring the handler first (mission §17/§19 — downgrade when
snapshot completeness is at risk).

## K. Calculation #3 Decision — `IMPLEMENT`

Cement satisfies every §18 gate: real production workflow, coherent numerical
engine (`SCOPE="COMPLETE"`), clear engineering inputs/outputs, high historical
value, deterministic, manageable snapshot/result, testable, no misleading
reference traceability (no catalog), and needs no generic framework.

## L. Input Contract

`CementEngine.job_volumes` signature has 30 keyword parameters; the snapshot
freezes **exactly** those 30 (verified by a test asserting
`set(_ENGINE_PARAMS) == signature`). All are runtime-sourced from W13 spinboxes
(or `None` when a spinbox is 0/omitted); none has a hidden dependency, catalog
lookup, global, or cache (engine audited: no `random`/`datetime`/`time`/file/env
access; uses only module constants `BBL_PER_CUFT`, `PSI_PER_PPG_FT` and pure
static `AdvancedHydraulicsEngine` capacity helpers). Units are canonical
(in/ft/ppg/bbl) and stored without conversion.

## M. Result Contract

`.values` (24 keys) classified:

* **Correctness-relevant (persisted & verified):** all volume scalars
  (`annular_*`, `slurry_*`, `shoe_track_volume_bbl`, `spacer_volume_bbl`,
  `displacement_volume_bbl`, `total_pump_bbl`, `casing_capacity_bbl`,
  `steel_displacement_bbl`, `hole_volume_bbl`), `sacks`, `mix_water_bbl`,
  `pump_time_min`, `hydrostatic_psi`, echoed inputs (`excess_pct`,
  `slurry_density_ppg`, `yield_ft3_sk`, `toc_md_ft`, `shoe_md_ft`), and the
  nested `lead`/`tail` leg dicts + `stacked_hydrostatic` layer list.
* **Diagnostic/UI:** none excluded from the numeric claim; textual `method`,
  `scope`, `warnings`, `assumptions` are ignored by `deep_numeric_diff`'s
  non-numeric-key policy (method drift handled separately via `method_matches`).

The **entire** result is persisted (`result_json`) and deep-compared — not the
summary. Six headline scalars are additionally promoted to queryable columns.

## N. Persistence

* ORM `CementCalculationRecord` (`cement_calculations`, 16 columns): id,
  well_id (nullable FK), label, method (NN), snapshot_schema_version (NN=1),
  input_snapshot_json (NN), result_json, 6 promoted Float summary cols,
  created_at/updated_at/created_by. Global-scoped; **no reference fingerprint**
  (honest — no catalog). Independent concrete model (not a shared base).
* `CementCalculationRepository` + detached `SavedCementCalculation`: save (one
  `session_scope` unit of work, no dedup), get, all (newest-first deterministic),
  count, verify, recalculate.
* `cement_persistence.py`: Qt-free `build_snapshot` / `snapshot_to_engine_args`
  / `recalculate_from_snapshot` / `result_summary` (SNAPSHOT_SCHEMA_VERSION=1).

## O. Historical Reproduction

`test_cement_cross_process.py::test_reconstruct_in_fresh_process` saves in one
interpreter and reconstructs+verifies in a **separate freshly-spawned Python
process** → status MATCH, slurry/pump/nested-lead values bit-identical. Proves
reproducibility comes from the on-disk snapshot, not in-memory state.

## P. Reference Traceability

Case **C (manual/direct engineering input)** per §23: cement inputs are direct
values with no catalog/preset behind them → snapshot only, no fingerprint.
Historical reconstruction depends on nothing but the frozen snapshot (no
mutation/disappearance tests needed — there is no reference to mutate).

## Q. Verification

`test_cement_persistence.py` covers MATCH, DIFFERENT (nested leg drift AND
list-of-dicts layer drift), NOT_REPRODUCIBLE (engine-precondition violation in a
tampered snapshot), UNREADABLE (empty stored result), method drift
(`method_matches=False`), row immutability across verify/recalculate/tamper, and
failure-safety (no partial row on commit error). Ground truth is engine-executed
(independent Barlow-style annulus hand-calc), never copied from the implementation.

## R. Abstraction Decision — `VERIFICATION ONLY`

The third concrete implementation is evidence, and that evidence says: keep it
concrete. Snapshots (survey/components vs flat scalars vs scalars-with-nested-
results), reconstruction, ORM shapes, and reference semantics are all divergent.
The §34 six-condition gate for new abstraction fails on "semantics genuinely
shared" and "reduces complexity". No `BaseCalculation`, generic repository,
snapshot DSL, or generic reference catalog introduced.

## S. History UI Decision — CONCRETE (per §35)

Three history dialogs share a *visual pattern* but differ in every engineering
field they display (T&D components+fingerprints; Casing ratings; Cement volumes+
legs). Extraction would hide those differences without reducing correctness risk.
Kept concrete; each exposes a Qt-free `build_history_rows` view-model that IS
unit-tested without a display.

## T. Search / Retrieval / Evidence

**Unchanged.** No calculation-persistence code references Search, Retrieval,
EvidenceBundle, or CitationAuditor (§40 boundary preserved).

## U. Dead / Duplicate / Abandoned Forensics

| Item | Finding | Classification |
|------|---------|----------------|
| `trajectory_calculations` table + `save_trajectory_calculation` (db:5801) | Pre-existing legacy dict-based store, unrelated to the snapshot-verification architecture | ACTIVE (legacy; left untouched) |
| Duplicate cement engine/persistence | none | CLEAN |
| Duplicate verification logic | single shared core; T&D re-exports for back-compat | ACTIVE |
| `CASING_DB` / `PIPE_DB` presets | live display presets | ACTIVE (preset) |
| `.github/workflows/ci.yml` | untracked, pre-existing | LEFT UNTOUCHED |

No deletions performed. Nothing removed on age alone.

## V. Dependencies

**None added.** Cement needs none; the local `.venv` (gitignored) was recreated
only to run tests.

## W. Tests

Commands (fresh `.venv`, `source tools/qt_headless_env.sh`,
`QT_QPA_PLATFORM=offscreen`):

* `pytest tests/test_cement_persistence.py tests/test_cement_cross_process.py
  tests/test_cement_history_viewmodel.py` → **23 passed**.
* `pytest tests/test_cement_save_widget_smoke.py` → **1 passed** (subprocess UI).
* `pytest` (full) → **1149 passed, 4 skipped** (exit 0); was 1125/4 → **+24**.
* `python -m compileall` on changed modules → OK.

## X. Remaining Debt

1. **Well Control** is the highest-value *next* calculation but its W13 handler
   assembles a mutable pipe list and does unit conversions before the engine;
   persisting it honestly needs a handler refactor first (deferred, evidence in §J).
2. Casing/pipe preset dicts remain display-layer; fine unless a real catalog is
   ever sourced (then converge).
3. `trajectory_calculations` legacy store is not part of the reproducible-snapshot
   architecture; not migrated (out of scope).

## Y. Git

Final commit adds Calculation #3 (engine unchanged): new
`cement_persistence.py`, `cement_repository.py`, `cement_history_dialog.py`,
`CementCalculationRecord` ORM, W13 wiring, 4 test files, this audit doc; plus the
Casing wording fix. `.github/` untouched; `.venv` gitignored. Exact hash in the
delivery message.

## Z. Final Decision

> **PROCEED WITH DEBT** — Calculation #3 (Cement Job Volumes) is implemented with
> historically trustworthy persistence and whole-result verification; the third
> concrete implementation empirically confirms the abstraction boundary stays at
> verification-only. Documented debt: Well Control needs a handler refactor
> before it can be persisted honestly.
