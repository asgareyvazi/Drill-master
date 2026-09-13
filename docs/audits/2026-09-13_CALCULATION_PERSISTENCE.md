# Torque & Drag Calculation Persistence + Historical Reproducibility + Reference Traceability

Date: 2026-09-13
Branch: `arena/01a085e0-drill-master`
Baseline commit: `b153e39`

This slice makes one concrete engineering calculation — **Torque & Drag** —
persistent, historically reproducible, and traceable to the DrillPipe reference
identities it used, without corrupting the existing architecture.

---

## A. EXECUTIVE VERDICT

**CERTIFIED WITH DOCUMENTED DEBT.** T&D runs can now be saved as immutable
historical records that reconstruct and recalculate to the identical numerical
result across a real persistence boundary, and survive later mutation of the
master reference catalog. The engine, its formulas and the established ground
truth are unchanged. Debt: only T&D is covered (by design); other calculations
remain transient; algorithm-version reproducibility is recorded but not enforced.

## B. REPOSITORY IDENTITY

- Branch `arena/01a085e0-drill-master`; baseline HEAD `b153e39` (= remote tip).
- Parent chain: `b153e39`←`8042063`←`aa84a35`←`0e0af51`←`1557a08`←`2b72ed7`←`7a662c2`.
- No session reset this task; env intact (`.venv` py3.11.2, qt-libs). Tree clean
  except untracked `.github/workflows/`.

## C. PRE-IMPLEMENTATION CLAIM VERIFICATION

| Claim | Evidence | Status |
|---|---|---|
| "No persistent calculation-result model" for the engineering calculator | `grep __tablename__` → no T&D/engineering-result table; `W13.save_data()` → `return True` | **PARTIAL** — true for W13/T&D, but a persisted-calculation *convention* already exists: `trajectory_calculations` (`parameters_json`+`results_json`+summary cols) used by w6 |
| DrillPipe catalog feeds T&D | `_wt_run_td` builds string from `self.wt_pipes` (populated from Quick Select → catalog) → `TorqueDragEngine.calculate` | **VERIFIED** |
| Ground truth 5.000in/19.5ppf ≈ 165.23 klbf | engine-executed | **VERIFIED** |
| Component carried reference identity | component dict had no `reference_fingerprint` before this slice | **FALSIFIED** (gap fixed here) |

Because a persistence convention already existed, this slice **reuses** it
(mirrors `TrajectoryCalculation`) rather than inventing a second mechanism (§3).

## D. ACTUAL CALCULATION ARCHITECTURE (T&D)

```
W13 EngineeringCalculatorTab
  _wt_calculate → calculate_weight_card (weight card)
  _wt_run_td:
    self.wt_pipes (Quick Select ◆ / manual)  +  self.dd_surveys  +  scalar params
      → TorqueDragEngine.calculate(survey, bha, mud_density_ppg, friction_factor,
                                   wob_klbf, wellbore_id_in) → EngineeringResult
      → display label  (previously: transient, nothing persisted)
NEW:
      → cache self._wt_last_td_run (exact inputs + result)
      → [Save Calculation] → TorqueDragCalculationRepository.save_run
          → build_snapshot (Qt-free) → torque_drag_calculations row
          → get()/all() → SavedCalculation.recalculate() → engine (reproduce)
```

## E. PERSISTENCE GAP (proven)

No table, model, repository or save path persisted an engineering-calculator
result. `W13.save_data()` returned `True` unconditionally. The nearest analog,
`TrajectoryCalculation`, is well/report-scoped and serves only w6 trajectory —
it does not cover the standalone T&D tool. Gap confirmed; no abandoned/duplicate
T&D persistence found in git history (linear chain, §N).

## F. IMPLEMENTED DESIGN

- **ORM** `TorqueDragCalculationRecord` (`torque_drag_calculations`, new Base
  table): `well_id` (nullable — standalone tool), `label`, `method`,
  `snapshot_schema_version`, `input_snapshot_json`, `result_json`,
  `reference_fingerprints_json`, promoted summary columns
  (`hookload_pickup/slackoff/rotating_klbf`, `surface_torque_rotating_ft_lbf`,
  `total_buoyed_weight_klbf`), timestamps, `created_by`. Mirrors the
  `trajectory_calculations` convention; global-scoped like `drill_pipe_specs`.
- **Domain (Qt-free)** `core/engineering/torque_drag_persistence.py`:
  `build_snapshot`, `snapshot_to_engine_args`, `recalculate_from_snapshot`,
  `reference_fingerprints`, `result_summary`, `SNAPSHOT_SCHEMA_VERSION`.
  Preserves canonical units exactly (ppf never mass-converted; diameters in
  inches); rejects bool/NaN/inf; adds no new physics.
- **Repository** `core/repositories/torque_drag_repository.py`:
  `TorqueDragCalculationRepository.save_run/get/all/count` + detached
  `SavedCalculation` (with `.recalculate()`). One `session_scope` unit of work
  per save (§15).
- **UI** W13: "💾 Save Calculation" button saves the cached last successful T&D
  run (one dialog, no per-row prompts, no DB internals exposed).
- **Traceability** `AddPipeDialog` now records the selected catalog reference and
  stamps `reference_fingerprint` onto the component **only if the identity
  values still match at save** (honest — an edited component drops the tag).

## G. HISTORICAL SNAPSHOT

`input_snapshot_json` is a self-contained canonical dict:
`{schema_version, method, survey:[{md,inc,azi}], components:[{od,id,length,weight,
type,grade,connection,reference_fingerprint?}], parameters:{mud_density_ppg,
friction_factor,wob_klbf,wellbore_id_in}}`. Reconstruction
(`snapshot_to_engine_args`) builds engine arguments **only** from this frozen
snapshot — never from the live catalog — so it is deterministic, serializable,
order-independent and Qt/object-identity independent (§7).

## H. REFERENCE TRACEABILITY

Two distinct questions are answered separately (§8):
- *"Which reference identities did this run use?"* →
  `reference_fingerprints_json` (engineering `identity_fingerprint()` values,
  never DB primary keys).
- *"What exact inputs were used?"* → the full frozen snapshot (numeric fields
  needed to recompute are present regardless of the reference).

## I. REPRODUCIBILITY (evidence)

save → (detach `SavedCalculation`) → `get()` reloads from DB →
`recalculate()` re-runs the real engine → result equals the original. Verified
Qt-free (`test_save_reload_reconstruct_recalculate`) and via subprocess widget
smoke (`test_torque_drag_save_widget_smoke`).

## J. MUTATION ISOLATION (evidence)

`test_history_survives_catalog_enrichment`: after a Run is saved, the master
reference is legitimately **enriched** (import adds a tool-joint OD; repo reports
`enriched=1`). The historical run's snapshot (`id=4.276`, fingerprint) is
unchanged and still recalculates to the original result. A *conflicting*
re-import is rejected by the repo (CONFLICT), so it also cannot rewrite history.

## K. NUMERICAL GROUND TRUTH

```
OD 5.000 in, 19.5 ppf, MD 3048 m, MW 10 ppg, ff 0.3
1 manual              → 165.23 klbf
2 catalog-selected    → 165.23 klbf
3 persisted summary   → 165.23 klbf
4 reload+reconstruct+recalculate → 165.23 klbf   (ALL EQUAL)
```
The ground-truth number is produced by executing the real engine, never
hard-coded into the computation. Persistence changes no numerical result.

## L. MIGRATION VERIFICATION

The new table is a Base model; `DatabaseManager._apply_safe_schema_upgrades`
`CREATE TABLE`s any missing Base table inside the upgrade transaction.
- **Fresh DB:** real `initialize()` path creates `torque_drag_calculations`
  with all 16 columns (verified).
- **Existing DB:** a DB built with all tables then dropping the new one, run
  through `_apply_safe_schema_upgrades()`, gains the table (16 columns), other
  56 tables untouched (verified). No new column added to an existing table, so
  the `upgrades` list was not modified. No Alembic (project has none).

## M. TESTS

Commands (headless env, `.venv`):
- `pytest tests/test_torque_drag_persistence.py` → **12 passed** (domain
  serialization/reconstruction, ground truth, save/reload/recalculate, distinct
  runs, newest-first ordering, mutation isolation, invalid-snapshot,
  transaction-failure rollback, promoted columns).
- `pytest tests/test_torque_drag_save_widget_smoke.py` → **1 passed**
  (subprocess-isolated W13 save flow).
- `pytest tests/test_addpipe_reference_fingerprint_smoke.py` → **1 passed**
  (subprocess-isolated honest fingerprint stamping/dropping).
- Full suite `pytest -q` → **exit 0**, **1073 tests** (was 1059 at `b153e39`;
  +14), no Qt abort.
- `compileall` clean; `ruff --select E722,F821` → **0**; new modules pass ruff
  clean; debt 5496 → 5528 (+32, all F403/F405 from existing `import *`).

## N. FORENSICS (dead / duplicate / abandoned)

| Item | Classification | Evidence | Action |
|---|---|---|---|
| Prior T&D/engineering-calc persistence | **NONE** | no table/model/save; `save_data`→True | built the gap |
| `TrajectoryCalculation` + `save_trajectory_calculation` | **ACTIVE** (reused as convention) | used by w6/w12 | mirrored, not duplicated |
| `rop_analysis` table | ACTIVE, different domain | ROP analysis | untouched |
| Abandoned calc-save experiments in git history | **NONE** | linear commit chain | — |
| Duplicate snapshot/serialization | **NONE** | only new module builds T&D snapshots | — |

No deletions — nothing met the evidence bar (§20/§40).

## O. DEPENDENCY / ARCHITECTURE CHECK

- Dependencies added: **none**.
- Generic framework added: **no** (concrete T&D-only slice; §39).
- Source of truth changed: **no** (catalog remains authoritative; runs are a new,
  separate historical record).
- Search / Retrieval / Evidence chain: **untouched** (§17) — persisted
  calculations are a derived engineering claim, not added to that chain.
- Catalog UI: unchanged, still observational/read-only (§19).

## P. REMAINING DEBT

- **PRODUCTION DEBT:** only T&D is persisted; other engines (weight card,
  hydraulics, etc.) remain transient. No history-browsing UI yet (records are
  saved + reloadable + tested; a viewer is deferred).
- **PRODUCT DECISION:** algorithm-version reproducibility is *recorded*
  (`method` + `snapshot_schema_version`) but not *enforced* — a future engine
  numerical change would be detectable, not blocked. Enforcement/versioning
  policy is deferred pending a concrete need.
- **THEORETICAL:** Unicode NFC still absent in identity (harmless for ASCII).

## Q. GIT DECISION

Commit recorded below; files changed: `core/database.py` (new model),
`core/engineering/torque_drag_persistence.py` (new),
`core/repositories/torque_drag_repository.py` (new),
`dialogs/engineering_dialogs.py` (reference-fingerprint stamping),
`tabs/w13_Engineering_Calculator.py` (Save button + cache + repo),
three new test files, this document. CI: **LOCAL VERIFIED / CI UNVERIFIED**
(no test CI workflow configured on this branch).

## R. FINAL RELEASE DECISION

**PROCEED WITH DEBT.** A real historical T&D calculation is now reproducible and
reference-traceable across the persistence boundary, proven by save→reload→
recalculate and by mutation isolation, with the engine and ground truth intact
and no new dependency or generic framework.

---

# ADDENDUM (2026-09-13) — CALCULATION HISTORY + OBSERVATIONAL VERIFICATION

Second vertical slice on top of the persistence slice above. **No schema change,
no engine change, no new dependency.** Turns persisted T&D runs into an
inspectable, honestly-verifiable calculation history.

## Implemented
- **Verification domain (Qt-free)** in `core/engineering/torque_drag_persistence.py`:
  `verify_saved_calculation(snapshot, stored_result, current_method=…)` →
  `VerificationOutcome` with discrete `status` ∈ {`MATCH`, `DIFFERENT`,
  `NOT_REPRODUCIBLE`, `UNREADABLE`} (constants `VERIFY_*`), per-key
  `differences`, and `method_matches`. It re-runs the **real engine on the
  frozen snapshot only** and **never mutates** the stored result (§16). It
  compares at the engineering-result level (abs tol 1e-6 over rounded engine
  claims), not formatted strings (§15).
- **Algorithm-drift honesty (§17/§18):** `method_matches=False` is surfaced when
  the current engine `method` differs from the snapshot's, so a numeric `MATCH`
  under a changed algorithm is NOT presented as exact reproduction. This is the
  smallest concrete guardrail; enforcement/blocking remains bounded debt.
- **Repository** `SavedCalculation.verify(current_method)`, plus `component_count`
  / `survey_count` view helpers.
- **Read-only UI** `dialogs/torque_drag_history_dialog.py`
  (`TorqueDragHistoryDialog`): list (newest-first) → select → frozen details
  (identity / inputs / drill string with per-component catalog-vs-manual trace /
  reference fingerprints / stored result) → "Verify" (observational). Empty and
  load-failure states handled. No edit/delete; no DB PK shown as identity (§11).
  A Qt-free `build_history_rows()` projects the list model for unit testing.
- **W13 wiring:** "📜 Calculation History" button in the Weight tab →
  `_wt_open_history` (opens the dialog via the existing repo accessor).

## Input-completeness matrix (§7 — re-verified)
| Engine input | Runtime source | Persisted | Reconstructed | Verified |
|---|---|---|---|---|
| survey (md/inc/azi) | `self.dd_surveys` | ✅ snapshot.survey | ✅ | ✅ |
| bha components (od/id/length/weight/type/grade/connection) | `self.wt_pipes` | ✅ snapshot.components | ✅ | ✅ |
| mud_density_ppg | weight-card conversion | ✅ parameters | ✅ | ✅ |
| friction_factor | `wt_friction` | ✅ parameters | ✅ | ✅ |
| wob_klbf | `wt_wob` | ✅ parameters | ✅ | ✅ |
| wellbore_id_in | `wt_hole` | ✅ parameters | ✅ | ✅ |
| reference_fingerprint (per comp) | AddPipeDialog stamp | ✅ (traceability) | stripped before engine | ✅ |

All 6 `TorqueDragEngine.calculate` parameters round-trip; `reference_fingerprint`
is carried for traceability and stripped from engine args. No hidden UI state
affects the result.

## Verification evidence (real engine)
- `MATCH`: untouched run recomputes identically (`165.23`).
- `DIFFERENT`: divergent stored value reported per-key (stored vs recalculated).
- `NOT_REPRODUCIBLE`: empty snapshot → engine `MISSING_INPUT`, no crash.
- `UNREADABLE`: malformed snapshot → caught, reported, no crash.
- **Immutability:** stored result unchanged after repeated verification.
- **Current-vs-historical (§19):** Run A saved → catalog enriched → different
  Run B saved → reload+recalculate Run A equals Run A, never becomes Run B.

## Tests (exact)
- `pytest tests/test_torque_drag_history.py` → **10 passed** (verification states,
  method-drift honesty, immutability, current-vs-historical separation, list
  view-model, empty state, manual-no-fingerprint).
- `pytest tests/test_torque_drag_history_widget_smoke.py` → **1 passed**
  (subprocess-isolated: empty state, list, select, details, verify MATCH,
  no mutation).
- All T&D tests together → **25 passed**.
- Full suite `pytest` → **1080 passed, 4 skipped**, exit 0, no Qt abort.
- New modules ruff-clean; `compileall` clean; `E722/F821` = 0.

## Boundaries preserved
No schema/migration change (verification is pure domain). No engine change. No
dependency added. No generic framework. Search/Retrieval/Evidence untouched.
Catalog UI still read-only. UI owns no engineering logic (delegates to repo +
Qt-free domain).

## Remaining debt (unchanged + refined)
- Algorithm-version reproducibility is **detected and surfaced** (method drift
  flagged) but not **enforced/blocked** — bounded, documented debt.
- Still T&D-only; no cross-engine persistence (deferred until a second concrete
  case proves a real abstraction).
- History is read-only; no retention/lifecycle/delete (intentional — history is
  a record, not a mutable form).
