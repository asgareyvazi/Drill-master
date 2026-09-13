# Casing Strength — Second Persistent Engineering Calculation (Forensic Audit + Implementation)

**Date:** 2026-09-13
**Branch:** `arena/01a085e0-drill-master`
**Baseline commit:** `73fcdcc` (full suite 1093 passed / 4 skipped)
**Scope:** Select and implement DrillMaster's SECOND real persistent engineering
calculation without premature abstraction, after a cross-engine forensic audit.

---

## A. Mission and single verdict

The task was to (1) run a full cross-engine forensic audit, (2) decide the best
next concrete engineering calculation to persist, (3) decide whether Torque &
Drag (T&D, calculation #1) reveals a genuinely reusable persistence/verification
abstraction, and (4) reach **exactly one** verdict.

**VERDICT: `SECOND CALCULATION JUSTIFIED`.**
Calculation #2 = **Casing Strength** (`CasingEngine.evaluate`), persisted as
`casing_calculations` with whole-result verification.

**Abstraction sub-verdict: `ABSTRACTION JUSTIFIED (PARTIAL)`** — extract only the
engine-agnostic *verification core*; keep snapshot-building and reconstruction
concrete per engine. Two materially different real implementations (T&D, Casing)
now share an identical verification contract, satisfying the ≥2-implementation
gate for that narrow core and no more.

---

## B. Repository identity (independently verified)

`git` HEAD `73fcdcc` matched the remote tracking branch before any change; the
working tree carried only Mission-4 additions. No other branch was touched.

## C. Baseline revalidation

The T&D vertical slice and full suite were green at `73fcdcc` (1093 passed / 4
skipped, exit 0) before work began.

---

## D. Engine inventory (candidates considered)

Non-T&D engines under `core/engineering/engines/`: casing, cement, mse,
bit_performance, plus geometry/volume helpers. Each was audited for: inputs,
hidden inputs, outputs, determinism, snapshot complexity, reference
dependencies, and historical engineering meaning.

## E. Candidate ranking (repository evidence, not arbitrary scores)

| Rank | Candidate | Real UI? | Determinism | Result shape | Input class vs T&D | Reference risk | Historical value |
|------|-----------|----------|-------------|--------------|--------------------|----------------|------------------|
| **1** | **Casing strength** | **Yes** — W13 CSG/CMT → "💪 Casing Strength", `_csg_calc_strength` | Bit-identical across fresh processes | Rich, 37 numeric scalars, **no arrays** | **Different** (pressures/loads/design factors; no survey) | **None persisted** (see §H) | High (tubular design of record) |
| 2 | Cement | Yes | Deterministic | Volume/capacity, reference-light | Similar-ish | Low | Medium |
| 3 | MSE | Yes | Deterministic | Trivial (≈5 in / 4 out) | Similar | Low | Low |
| 4 | bit_performance | Partial | Deterministic | Report-coupled | — | Report state | Medium but coupled |

Casing wins: real production workflow, engineering design value, deterministic,
richly testable, and it exercises a **different input class** than T&D (no survey
geometry — instead pipe geometry + pressures/axial loads + design factors +
connection minimums).

## F. Casing engine contract

`CasingEngine.evaluate(od_in, id_in, wall_in, yield_psi, internal_pressure_psi,
external_pressure_psi, axial_tension_lbf, burst/collapse/tension_design_factor,
grade, weight_ppf, yield_at_temp_psi, connection_burst/collapse/tension)` →
`EngineeringResult`.

* `METHOD` = "API TR 5C3 pipe-body subset (Barlow + four-regime collapse + fyax +
  VME)", `SCOPE = PARTIAL` (pipe body, not connection/full-string design).
* `.values` = 43 keys, **all scalar** (37 numeric, 0 arrays / 0 nested dicts).
* Deterministic in-process, and **bit-identical across two separate fresh OS
  processes** (verified: burst 6865.5, collapse 4754.0, body-yield 1085789.0,
  governing_collapse 11721.2, vme 22600.3).
* No `random`/`now`/`time` usage in casing/cement/mse (`grep -c` = 0).

## G. Determinism & mutation audit

Repeated in-process calls are identical; unrelated intervening calls do not
perturb a snapshot's recomputation; input kwargs are not mutated. Verified in
`tests/test_casing_persistence.py::test_engine_deterministic_and_no_input_mutation`
and cross-process in `tests/test_casing_cross_process.py`.

## H. Reference-data forensics — the honesty constraint

The only casing "catalog" in the app is `AddCasingDialog.CASING_DB` — a
**hard-coded Python dict** in `dialogs/engineering_dialogs.py`, with no persisted
identity, provenance, or version. It is a UI convenience, not an authoritative
catalog.

**Consequence:** the persisted casing record stores **NO reference
fingerprint**. Claiming API-5CT catalog traceability would be misleading. The
frozen numeric snapshot alone fully reconstructs the run, so reconstruction can
never depend on mutable current reference state (mission §12/§13/§23/§25 are
satisfied by construction — there is no reference to disappear).

## I. Result-complexity boundary

The engineering claim boundary is the whole numeric result. Verification
compares the **entire** result deep-diff (not a summary projection), applying the
lesson from the T&D false-MATCH bug. Six headline scalars are additionally
promoted to queryable columns for listing/history, but they are not the
verification surface.

---

## J. Abstraction decision (do NOT copy T&D blindly)

Assessed which semantics are generic vs T&D-specific:

* **Generic (shared):** the discrete verification states, the `VerificationOutcome`
  value object, finite-float coercion, and the recursive whole-result
  `deep_numeric_diff` — the subtle 60-line comparison that was the site of the F1
  false-MATCH bug. Duplicating it would risk the two engines' verification
  drifting apart.
* **Engine-specific (kept concrete):** how inputs are frozen into a snapshot, how
  a snapshot is reconstructed into engine args, which engine runs, and the
  summary projection. T&D snapshots survey geometry + friction; casing snapshots
  pipe geometry + loads. These share no field vocabulary.

Therefore the abstraction is **partial**: a new `calculation_verification.py`
core, consumed by both engines; snapshot/reconstruct stay per engine. This meets
the ≥2-implementation gate for exactly the code that is provably shared, and
avoids a speculative framework.

## K. Files added / changed

**New (Qt-free domain + persistence):**
* `core/engineering/calculation_verification.py` — shared engine-agnostic core
  (`VERIFY_*`, `VerificationOutcome`, `clean_number`, `deep_numeric_diff`,
  `classify_verification`).
* `core/engineering/casing_persistence.py` — casing snapshot / reconstruction /
  summary (`SNAPSHOT_SCHEMA_VERSION=1`, `build_snapshot`,
  `snapshot_to_engine_args`, `recalculate_from_snapshot`, `result_summary`).
* `core/repositories/casing_repository.py` — `CasingCalculationRepository` +
  detached `SavedCasingCalculation` (save / get / all / count / verify).
* `dialogs/casing_history_dialog.py` — read-only history browser + Qt-free
  `build_history_rows` view-model.

**Changed:**
* `core/engineering/torque_drag_persistence.py` — refactored to delegate to the
  shared core; public API (`VERIFY_*`, `VerificationOutcome`,
  `_deep_numeric_diff`, `verify_saved_calculation`) preserved for backward compat.
* `core/database.py` — added `CasingCalculationRecord` ORM (`casing_calculations`).
* `tabs/w13_Engineering_Calculator.py` — Save + History buttons and handlers on
  the Casing Strength tab; caches the exact run inputs/result for verbatim save.

**Tests added:** `tests/test_casing_persistence.py` (18),
`tests/test_casing_cross_process.py` (2),
`tests/test_calculation_verification_core.py` (10),
`tests/test_casing_history_viewmodel.py` (2).

## L. Snapshot design

`build_snapshot(inputs, method)` freezes the **exact** engine kwargs
(finite-float coerced; optional loads preserved as `None`), plus `method` and
`schema_version`. It is JSON-serializable, order-independent, and self-contained.
A test pins `_ENGINE_PARAMS ∪ _ENGINE_TEXT_PARAMS == engine signature`, so no
engine input can ever be silently dropped from history.

## M. Reconstruction across a process boundary

`test_reconstruct_in_fresh_process` saves in one interpreter and reconstructs +
verifies in a **separate freshly-spawned Python process**, proving reproducibility
comes from the on-disk snapshot, not in-memory engine state. Result matches
bit-for-bit; status = MATCH.

## N. Mutation isolation

`SavedCasingCalculation` is a detached dataclass. Verifying/recalculating and
even tampering with the detached copy never mutate the persisted row
(`test_verify_and_recalculate_never_mutate_persisted_row` compares a full row
fingerprint including `updated_at`).

## O. Whole-result verification (F1 lesson applied)

`verify()` recomputes from the snapshot and deep-diffs the **entire** result:

* **MATCH** — every numeric leaf reproduces within 1e-6.
* **DIFFERENT** — any numeric field diverges (test drifts a *non-summary* field,
  `vme_psi`, and it is still caught — the exact class of bug F1 fixed).
* **NOT_REPRODUCIBLE** — snapshot cannot be reconstructed/run (engine failure).
* **UNREADABLE** — stored record has no result.

Method drift is reported honestly via `method_matches` (a numeric match under a
changed algorithm is not presented as exact reproduction).

## P. Corruption / edge states

Covered: empty result → UNREADABLE; broken snapshot (missing yield) →
NOT_REPRODUCIBLE with detail; method drift → MATCH but `method_matches=False`.

## Q. Algorithm identity

The record stores `method` and `snapshot_schema_version`. An algorithm change
becomes detectable rather than silently reproduced (mission §28). No fingerprint
is fabricated for the hard-coded preset table (§H).

## R. DB conventions (no Alembic)

Follows the repo's `_apply_safe_schema_upgrades` convention: the new `Base` table
is auto-created on fresh DBs via `create_all` and on **existing** DBs via the safe
upgrade path. `test_migration_provisions_table_on_existing_db` drops the table on
a populated DB and confirms the upgrade re-provisions all 16 columns while other
tables (incl. `torque_drag_calculations`) remain intact.

## S. Failure safety

`save_run` is a single `session_scope` unit of work;
`test_persistence_failure_leaves_no_partial_row` injects a commit-time error and
asserts zero rows persist.

## T. UI wiring (done last; core stays Qt-free)

Save + History buttons were added to the existing Casing Strength tab. The
handler persists the last successful run verbatim (inputs cached at calc time, so
later widget edits cannot alter a saved run) and the read-only dialog offers
observational Verify. No edit/delete of history (mission §32). No Search /
Retrieval / Evidence surface added (§33).

## U. Ground truth (engine-executed, never hard-coded)

`test_ground_truth_burst_barlow` independently derives Barlow burst
`0.875·2·Yp·t/OD` and asserts the engine matches — the ground truth is computed,
not copied from a prior run.

## V. Constants / dependencies

No new third-party dependency was introduced (mission §35): casing strength needs
none.

## W. Test results

* New casing/core tests: **32 passed**.
* Full suite after changes: **1125 passed / 4 skipped / exit 0** (was 1093/4).
  T&D's existing tests remain green through the shared-core refactor.

## X. Scope discipline / what was deliberately NOT done

* No generic "calculation framework" — only the provably-shared verification core
  was extracted.
* No reference fingerprint / catalog traceability claim for casing (would be
  dishonest given the hard-coded preset table).
* No edit/delete of history; no Search/Retrieval/Evidence expansion.
* Cement/MSE/bit_performance were ranked and rejected for now with reasons.

## Y. Conclusion

`SECOND CALCULATION JUSTIFIED` — Casing Strength is implemented as a real,
deterministic, reproducible, honestly-scoped persistent calculation with
whole-result verification, sharing exactly the verification core with T&D and
nothing more. The implementation is complete, tested cross-process and
cross-migration, and adds no regressions.
