# DrillMaster — Wellbore / Schema v3 Forensic Acceptance Audit

Date: 2026-09-12
Branch: `arena/01a085e0-drill-master`
Audited commit: `8a3d750` (parent `b31ea83`)
Corrective commit produced by this audit: `c0e91b8`

---

## 1. Repository Evidence

```text
branch:          arena/01a085e0-drill-master
HEAD (at start): 8a3d750  "Introduce canonical Wellbore entity and migrate to schema v3"
HEAD (at end):   c0e91b8  "Enforce Wellbore ownership integrity and close physical-FK gap"
8a3d750 present: yes (git cat-file -t 8a3d750 => commit)
parent:          b31ea83  "Correct commit topology in CI operationalization audit"
working tree:    clean except untracked .github/workflows/ (the CI track, intentionally
                 not committed here because pushing workflow files is blocked by the
                 GitHub App `workflows` permission)
```

The checked-out repository genuinely contains the claimed Wellbore
implementation; the diff `8a3d750^..8a3d750` was inspected in full.

## 2. Baseline (commit 8a3d750, before any corrective change)

```text
pytest:   865 passed, 4 skipped, 0 failed, 0 error   (188s)
skipped:  DDR XLSX, DDR PDF, MinerU, Windows bundle   (all opt-in)
compile:  OK (compileall core dialogs tabs tests)
E722:     0
F821:     0
ruff debt (core dialogs tabs tests, summed statistics): 5489  (ceiling 5489)
python 3.11.2 · ruff 0.16.6 · pytest 9.1.1
```

## 3. Implementation Verified (what is actually present)

* `Wellbore` model: `id` (PK), `well_id` FK→wells (NOT NULL, CASCADE), `name`,
  `code`, `wellbore_type` (default "original"), `parent_wellbore_id` self-FK
  (SET NULL), `kickoff_md` (nullable), `status`, timestamps. Relationships to
  Well, parent/sidetracks, sections, daily_reports.
* `Section.wellbore_id` and `DailyReport.wellbore_id`: nullable FK→wellbores
  (SET NULL); existing `well_id`/`section_id` retained.
* Migration: `schema_version` 2→3; `wellbores` created via generic missing-table
  step; two `wellbore_id` columns added by a guarded `version in (None,1,2)`
  ALTER block; historical rows left NULL.
* Helpers: `save_wellbore`, `get_or_create_wellbore` (identity `(well_id, name)`),
  `get_wellbores_by_well`.
* Import: resolves a wellbore only when `wellbore_name`/`wellbore` is present.
* SelectionManager: full Well→Wellbore→Section→Report cascade with ownership
  guards; `select_full_context` extended with optional wellbore params.

## 4. Defects Found

The FK-only design of `8a3d750` guaranteed only that a referenced row exists,
never that it belongs to the same Well/Wellbore. Seven forensic probes each
created a contradictory state that was **silently accepted**.

### D1 — Cross-Well sidetrack lineage — HIGH
* File/fn: `core/database.py` Wellbore; `get_or_create_wellbore`
* Invariant: `child.well_id == parent.well_id`
* Repro: create sidetrack under Well A with `parent_wellbore_id` = a bore of Well B → accepted.
* Root cause: self-FK proves parent exists, not same-Well.
* Fix: `before_flush` check rejects cross-Well lineage; helper re-raises.
* Regression: `TestParentLineage::test_cross_well_parent_rejected_{orm,helper}`, `test_wellbore_cannot_be_its_own_parent`.

### D2 — Section Well/Wellbore ownership mismatch — HIGH
* File/fn: `core/database.py` Section
* Invariant: `section.wellbore.well_id == section.well_id`
* Repro: Section(well_id=A, wellbore_id=B1) → accepted.
* Fix: `before_flush` check; NULL still allowed.
* Regression: `TestSectionOwnership::*`.

### D3 — DailyReport well/section/wellbore contradiction — HIGH
* File/fn: `core/database.py` DailyReport
* Invariant: report.well_id agrees with its section's well and its wellbore's
  well, and (when both non-NULL) report.wellbore_id == section.wellbore_id.
* Repro: report well=A, section=A1, wellbore=B1 → accepted; report well=A,
  section belongs to B → accepted.
* Fix: `before_flush` check; NULL wellbore allowed (legacy/ambiguous).
* Regression: `TestDailyReportOwnership::*`.

### D4 — Arbitrary `wellbore_type` — MEDIUM
* Repro: `wellbore_type="banana"` persisted verbatim.
* Fix: `VALID_WELLBORE_TYPES={"original","sidetrack"}` enforced at flush.
* Regression: `TestWellboreType::test_invalid_type_rejected`.

### D5 — `original` bore carrying a parent — MEDIUM
* Repro: type="original" + parent_wellbore_id set → accepted (structurally contradictory).
* Fix: only a `sidetrack` may have a parent.
* Regression: `TestWellboreType::test_original_with_parent_rejected`.

### D6 — Wellbore identity mutation — MEDIUM
* File/fn: `save_wellbore`
* Repro: `save_wellbore({"id": A_bore, "well_id": B})` moved the bore to Well B,
  orphaning its sections/reports.
* Fix: `well_id` treated as immutable; attempts raise `OwnershipIntegrityError`.
* Regression: `TestIdentityImmutability::*`.

### D7 — Import shared a section across bores — HIGH (found via the new invariant)
* File/fn: `core/ddr_import_service.py` section resolution
* Invariant: a section belongs to exactly one wellbore.
* Repro: import "Original" DDR then a "ST #1" DDR reusing the same section name;
  section identity `(well, name)` reused the original bore's section, then the
  sidetrack report claimed a different bore → contradictory chain (now rejected
  by D3's invariant, previously silently wrong).
* Root cause: section identity ignored the wellbore dimension.
* Fix: section resolution is wellbore-scoped — same name under a different bore
  is a distinct section; an un-attributed section can be adopted once.
* Regression: `TestImportAttribution::test_same_section_name_across_bores_stays_distinct`.

### D8 — Physical-FK asymmetry on upgraded databases — MEDIUM/HIGH (Gate H)
* File/fn: migration `_apply_safe_schema_upgrades`
* Finding: fresh v3 DBs physically enforce the wellbore FK; v2→v3 upgraded DBs
  (ALTER ADD COLUMN cannot attach an inline FK) did **not** — an upgraded DB
  accepted a dangling `wellbore_id=999999` that a fresh DB rejects.
* Fix: `_install_wellbore_foreign_key` rebuilds `sections`/`daily_reports`
  during upgrade from their live CREATE SQL with the FK injected (ON DELETE SET
  NULL), preserving columns/indexes/triggers/rows; idempotent; validated by
  `PRAGMA foreign_key_check`.
* Regression: `test_upgraded_db_has_physical_wellbore_fk`,
  `test_upgraded_db_rejects_dangling_wellbore_id`, plus the idempotency test.

## 5. Cross-Well / Cross-Wellbore Integrity (each invalid scenario tested)

| Scenario | Before | After |
| --- | --- | --- |
| Sidetrack parent in another Well | accepted | rejected |
| Wellbore as its own parent | accepted | rejected |
| `original` bore with a parent | accepted | rejected |
| Section well_id≠wellbore.well_id | accepted | rejected |
| Report wellbore in another Well | accepted | rejected |
| Report section in another Well | accepted | rejected |
| Report wellbore ≠ its section's wellbore | accepted | rejected |
| Invalid `wellbore_type` | accepted | rejected |
| Move bore to another Well via save_wellbore | accepted | rejected |
| Section/Report with NULL wellbore (legacy) | allowed | **still allowed** (no fabrication) |
| Dangling wellbore_id on upgraded DB | accepted | rejected (physical FK) |

## 6. Migration Evidence

* Fresh DB: `initialize()` → version 3; `wellbores` present; both `wellbore_id`
  columns present; physical wellbore FK present on both tables.
* v2 → v3 (synthetic faithful v2 with seeded wells/sections/reports): upgrade
  succeeds; all rows preserved with unchanged IDs; new `wellbore_id` = NULL (no
  fabrication); physical wellbore FK installed; `foreign_key_check` empty.
* Idempotent re-init: version stays 3; exactly one wellbore FK per table (no
  duplication); no data mutation; no exceptions.
* Physical schema confirmed via `PRAGMA table_info` / `PRAGMA foreign_key_list`
  (not inferred from ORM declarations).

## 7. Import Evidence (source → Wellbore resolution)

`well_info["wellbore_name"]` (or `["wellbore"]`) is the ONLY trigger for
attribution; `wellbore_type` optionally marks a sidetrack. Verified:

* No wellbore named → 0 wellbores; section/report `wellbore_id` = NULL.
* `rig_name` present, no wellbore → still NULL (rig never implies a bore).
* Same source imported twice → 1 wellbore, idempotent report.
* Same well, two explicit bores → 2 wellbores under 1 well.
* Same bore name under two wells → 2 distinct wellbores (Well-scoped identity).
* Same section name across two bores → 2 distinct, correctly-attributed sections.

No assignment from rig, well name alone, section name alone, fuzzy similarity,
or a default "original" bore.

## 8. Selection Evidence

Cascade verified: Well→clears Wellbore+Section+Report; Wellbore→clears
Section+Report; Section→clears Report; Report→preserves parents. Ownership
guards reject a Wellbore from another Well, and a Section/Report whose
`wellbore_id` contradicts the selected wellbore. `select_full_context` remains
backward compatible (the one legacy caller in `main_window.py` passes only
well/section/report positionally). Covered by
`tests/test_selection_manager_context.py` (12 tests).

## 9. Test Quality (tests that genuinely persist and read back DB state)

* `tests/test_wellbore_ownership_integrity.py` (17) — commit + reload; asserts
  raises and post-rollback DB state.
* `tests/test_wellbore_schema_v3.py` (24) — real `initialize()`/migration, real
  import path, `sqlite3`-level `PRAGMA` assertions on physical schema.
* `tests/test_selection_manager_context.py` (12) — real singleton behaviour.
Object-only instantiation without commit is not relied upon for any persistence
claim.

## 10. Regression Results (final, after corrective commit c0e91b8)

```text
pytest:  885 passed, 4 skipped, 0 failed, 0 error   (189s)
compile: OK
E722:    0
F821:    0
ruff debt (core dialogs tabs tests): 5489  (ceiling 5489 — unchanged, neutral)
```

No tests deleted, no assertions weakened, no new xfail/skip introduced.

## 11. Production Changes Made During This Audit

* `core/import_diagnostics.py`: new `OwnershipIntegrityError`.
* `core/database.py`: `before_flush` ownership-integrity invariant + helpers;
  `VALID_WELLBORE_TYPES`; `save_wellbore` well_id immutability; helpers re-raise
  integrity errors; `_install_wellbore_foreign_key` and its call in the v2→v3
  upgrade block.
* `core/ddr_import_service.py`: wellbore-scoped section resolution.
* Tests: new `test_wellbore_ownership_integrity.py`; added import + physical-FK
  regression tests to `test_wellbore_schema_v3.py`.

## 12. Deferred Issues

* No DB-level `CHECK` constraint on `wellbore_type` (enforced at the persistence
  boundary instead, consistent with the project's migration architecture and
  applying uniformly to fresh and upgraded databases).
* No unique constraint on `(well_id, name)` for wellbores; `get_or_create` is the
  single creation path and is idempotent. A structural unique index is a
  possible future hardening, deferred to avoid a non-essential table rebuild.
* Wider tabs still operate at Well/Section granularity; no cross-Wellbore
  leakage was found because persistence-layer invariants now hold regardless of
  UI. Tab-level Wellbore surfacing is out of scope for this phase.

## 13. CI

```text
REMOTE CI: BLOCKED / NOT OBSERVED
```

The `.github/workflows/ci.yml` commit cannot be pushed without the GitHub App
`workflows` write permission. No GitHub Actions run exists for this work. All
results in this report are local and are not a substitute for remote CI.

## 14. Acceptance Matrix

| Gate | Result | Evidence |
| --- | --- | --- |
| A — Commit identity | PASS | §1 |
| B — Wellbore model | PASS | §3, D6 fix (identity immutable) |
| C — Parent lineage | PASS | D1 fixed + tests |
| D — Wellbore type | PASS | D4, D5 fixed + tests |
| E — Section ownership | PASS | D2 fixed + tests |
| F — DailyReport ownership | PASS | D3 fixed + tests |
| G — Migration non-destructive | PASS | §6 |
| H — Physical schema | PASS | D8 fixed; physical FK on fresh + upgraded |
| I — Import determinism | PASS | §7 |
| J — Repeatability | PASS | §7 |
| K — Sidetrack | PASS | §5, D1; lineage preserved, NULL vs 0 distinct |
| L — Selection | PASS | §8 |
| M — Legacy compatibility | PASS | §8; single caller unchanged |
| N — Previous integrity | PASS | schematic (16) + inventory (16) tests green |
| O — Tests | PASS | §10 |
| P — Static quality | PASS | E722=0, F821=0, debt 5489 ≤ ceiling |
| Q — Scope | PASS | §11; no KPI/BHA/tab redesign, no db rewrite |
| R — CI | BLOCKED | §13 |

## 15. Final Certification

```text
WELLBORE V3 = PASS
```

Rationale: every structural, ownership, migration, import, and selection
invariant is now enforced at the persistence boundary and verified by tests that
persist and read back real database state, on both fresh and upgraded databases.
Eight defects (three of them HIGH) discovered during the audit were fixed with
the smallest safe changes, no data loss, and no fabricated identity — unknown
ownership remains NULL by design. The only non-PASS item is remote CI, which is
externally BLOCKED and explicitly not claimed as passing.
