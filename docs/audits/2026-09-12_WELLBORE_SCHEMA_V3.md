# Wellbore / Schema v3 Foundation — Forensic Report

Date: 2026-09-12
Branch: `arena/01a085e0-drill-master`
Phase: Wellbore / Schema v3 Foundation (production architecture)

---

## 1. Scope & Mandate

Establish the correct, durable domain hierarchy

```
Company → Field/Project → Well → Wellbore → Section → DailyReport
                                     └→ (Ops / Eng / Cost / Inventory / BHA / Bit / NPT)
```

without breaking the existing application, import path, or stored data. The
governing rule of the product is that DrillMaster is **WELL-CENTRIC, not
RIG-CENTRIC**: a Rig is a resource/assignment attribute, never the identity of a
Well or a Wellbore.

The prior schema (v2) had **no Wellbore identity**. This phase introduces the
canonical `Wellbore` entity between `Well` and `Section`, migrates the database
non-destructively to schema v3, and extends the selection cascade — with no
big-bang refactor and no cosmetic UI restructuring.

## 2. Method

The repository is the sole source of truth; no document, comment, or prior
report was trusted without re-verification. Before writing any code the entire
`core/database.py` model layer (~55 models) and the `DatabaseManager` migration
engine were re-read end to end, and every schema-version pin was re-grepped
across `app.py`, `tests/`, and tooling.

## 3. Forensic Findings (pre-change state)

| Question | Evidence | Finding |
| --- | --- | --- |
| Is there an existing Wellbore identity? | `core/database.py` model scan | **No.** `WellboreSchematic` is a *drawing* table (well_id + report_id + JSON), not an identity. |
| Is Rig an identity key anywhere? | `Well.rig_name` is a plain column; `tests/test_well_centric_acceptance.py` | Rig is already an attribute; three wells share one rig and stay distinct. |
| How are Sections/Reports scoped? | `Section.well_id` NOT NULL; `DailyReport.well_id` NOT NULL, `section_id` nullable | Everything is well/section/report-scoped; no bore dimension. |
| What is the migration engine? | `DatabaseManager` custom engine, `schema_version = 2` | Bespoke, non-Alembic; supports create-missing-tables + ALTER upgrades + nullable-contract rebuild in one FK-off transaction. |
| Does import fuzzy-merge names? | `core/ddr_import_service.py`, `core/repositories/well_repository.py` | No fuzzy merge; ambiguous identity is rejected. `AZNS 12` vs `AZNS 12 ST #1` never auto-merge. |
| Does the selection manager have a bore level? | `core/selection_manager.py` | No — Well → Section → Report only. |

Conclusion: a canonical `Wellbore` entity is required, and none adequate exists.

## 4. Canonical Model Introduced

`Wellbore` (`core/database.py`):

* `id` — immutable integer PK (identity never changes with rig/name/source).
* `well_id` — FK NOT NULL → `wells.id` (`ondelete=CASCADE`).
* `name`, `code`, `status`.
* `wellbore_type` — `"original"` (default single bore) or `"sidetrack"`.
* `parent_wellbore_id` — nullable self-FK → `wellbores.id` (`ondelete=SET NULL`)
  for **sidetrack lineage**; NULL = root bore.
* `kickoff_md` — nullable float; unknown stays NULL, never defaulted to 0.
* `created_at` / `updated_at`.

Relationships: `Well.wellbores` (cascade delete-orphan), `Wellbore.parent` /
`Wellbore.sidetracks`, `Wellbore.sections`, `Wellbore.daily_reports`.

## 5. Rig ≠ Identity (guarantee preserved)

No Wellbore field references a rig. `get_or_create_wellbore(well_id, name)`
keys strictly on `(well_id, name)`. A test (`TestRigIsNotWellboreIdentity`)
changes `Well.rig_name` and re-resolves the same wellbore name, proving the
identity is stable and no fork occurs.

## 6. Sidetrack Handling (never auto-merge)

A sidetrack is a *distinct* `Wellbore` row under the *same* `Well`, linked to
its parent via `parent_wellbore_id`. It is never merged into the original bore
and never promoted to a new Well. `get_or_create_wellbore` treats a distinct
name (e.g. `"ST #1"`) as a distinct bore. Workover remains an event/phase, not a
new Well and not (by itself) a new Wellbore.

## 7. Section & DailyReport changes

Both gained a **nullable** `wellbore_id` FK → `wellbores.id`
(`ondelete=SET NULL`). Existing `Section.well_id` / `DailyReport.well_id` /
`DailyReport.section_id` are unchanged, preserving backward compatibility. The
column being nullable is the mechanism for "unknown": historical or ambiguous
rows keep `wellbore_id = NULL`.

## 8. Non-Destructive Migration (v2 → v3)

* `DatabaseManager.schema_version` bumped `2 → 3`.
* The `wellbores` table is created by the engine's existing
  "create missing tables" step inside the FK-off migration transaction.
* A new guarded block (`if version in (None, 1, 2)`) adds
  `sections.wellbore_id` and `daily_reports.wellbore_id` via `ALTER TABLE …
  ADD COLUMN … INTEGER` (nullable, no fabricated backfill).
* Atomicity, `PRAGMA foreign_key_check`, and the nullable-contract rebuild are
  all preserved; the version marker is rewritten to 3.

Verified end-to-end against a synthetic faithful v2 database: upgrade succeeds,
version advances to 3, the table + both columns appear, **all pre-existing rows
are preserved**, and legacy `wellbore_id` values remain NULL. Re-initialisation
is idempotent (`test_v2_upgrade_is_idempotent`).

## 9. Deterministic-Only Attribution (no fabrication)

`core/ddr_import_service.py` resolves a wellbore **only** when the source
explicitly provides `wellbore_name` (optionally `wellbore_type`). When it does
not, `wellbore_id` stays NULL on both the Section and the DailyReport — an
ambiguous DDR is never fabricated into a wellbore. Backfill onto an existing
Section only fills a NULL; it never overwrites an existing (possibly different)
attribution. This upholds *preserve uncertainty over inventing certainty*.

## 10. Selection Cascade (Well → Wellbore → Section → Report)

`core/selection_manager.py` gains a full wellbore level:

* `wellbore_changed` signal, `_wellbore_id` / `_wellbore_data`, `select_wellbore`,
  `current_wellbore_id` / `current_wellbore_data`, `has_wellbore`.
* Cascade: **Well** change clears Wellbore + Section + Report; **Wellbore**
  change clears Section + Report; **Section** clears Report; **Report** clears
  nothing.
* `_ownership_conflict` extended: a Section/Report tagged with a wellbore that
  contradicts the selected wellbore is rejected (defensive, only when both IDs
  are present).
* `select_full_context` accepts an optional `wellbore_id`/`wellbore_data`,
  keeping every existing `(well, section, report)` caller working unchanged.

## 11. Import Identity / No Unsafe Merge

Unchanged well-identity resolution (`WellRepository.resolve_identity`,
combo-identity, ambiguity → reject) is preserved; the new wellbore step sits
after well resolution and adds no fuzzy matching. `AZNS 12` and
`AZNS 12 ST #1` remain distinct wells, and their bores remain distinct.

## 12. None vs Zero, Schematic No-Fabrication

No zero-vs-missing semantics were altered. `kickoff_md` and both new
`wellbore_id` columns default to NULL, never 0. The schematic tab's
no-fabrication behaviour (`tabs/w3b_wellbore_schematic_tab.py`) is untouched.

## 13. Version Pins Updated in Lockstep

* `tests/test_release_smoke.py` — two `assert version == 2` → `== 3` (these
  assert the DB reports the *current* schema version after real init/upgrade; a
  genuine strengthening, not a weakening).
* `app.py` and the migration engine compare against `manager.schema_version`
  dynamically — no literal edits needed.
* `tests/test_credential_lifecycle.py:379` is a self-contained probe whose own
  `schema_version` matches its own mocked scalar; left unchanged intentionally.

## 14. Verification Results

* Full suite: **865 passed, 4 skipped, 0 failed/error** (baseline was 844
  passed / 4 skipped; +21 new tests).
* New tests: `tests/test_wellbore_schema_v3.py` (15) +
  `tests/test_selection_manager_context.py` wellbore cases (5) +
  passing version-bumped smoke tests.
* `ruff --select E722` → 0; `ruff --select F821` → 0.
* Lint-debt ratchet: `ruff check --statistics core dialogs tabs tests` = **5489**,
  ceiling **5489** → within budget (debt-neutral; new files are clean).
* `py_compile` of all changed modules → OK.

## 15. CI Status — BLOCKED / NOT OBSERVED

CI has **not** been observed to pass remotely. The `.github/workflows/ci.yml`
commit cannot be pushed without `workflows` write permission (push rejected on
three prior attempts), so no GitHub Actions run exists for this work. All
results above are **local**. Per the acceptance gates, no CI PASS is claimed
from local runs — the remote gate remains blocked pending the permission grant.

## Scope Discipline

No tab restructure, no new KPI/Home/Analysis/Planning redesign, no Alembic, no
big-bang rewrite of `database.py` / `main_window.py`. Changes are confined to:
`core/database.py` (model + migration + helpers), `core/selection_manager.py`
(cascade), `core/ddr_import_service.py` (deterministic attribution),
`tests/test_release_smoke.py` (version pins), and two new/extended test files.
