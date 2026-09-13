# DrillPipe Reference Persistence — Readiness Audit & Architecture Decision

Date: 2026-09-13
Scope: Is DrillMaster architecturally ready for a **global engineering-reference
persistence layer**, and if so, what is the *smallest justified* production-grade
increment toward `DrillPipeSpec` reference selection → calculation?

Baseline before this work: HEAD `2b72ed7`; full suite **1009 passed / 4 skipped**;
E722=0; F821=0; ruff debt 5489.

---

## A. Question

The prior mission hardened `DrillPipeSpec` normalization (commit `2b72ed7`) but the
spec had **zero production consumers** and **no persistence**. This mission asks
whether persistence is *justified and possible without fabricating data*, and, if so,
to build only the smallest correct link of the chain
`SOURCE → PROVENANCE → NORMALIZATION → VALIDATION → IDENTITY → DUP/CONFLICT →
CANONICAL SPEC → PERSISTENCE → SELECTION → COMPONENT → CALCULATOR → RESULT`.

## B. Persistence stack (verified, repo is source of truth)

* ORM: SQLAlchemy `declarative_base()` (`core/database.py`). **No Alembic**; a custom
  versioned migration (`schema_version = 3`).
* `initialize()` → `_apply_safe_schema_upgrades()` creates **any missing
  `Base.metadata` table + its indexes inside one FK-off transaction**, then applies
  versioned `ADD COLUMN` lists. ⟹ **A new ORM model auto-creates its table on next
  `initialize()`** — no manual migration required, non-destructive to existing data.
  Verified empirically: `drill_pipe_specs` and its UNIQUE index appear after a real
  `initialize()` run.
* Transaction safety: `session_scope()` = commit / rollback / close unit of work.
* Repository pattern: `core/repositories/base.py::BaseRepository` (session-scoped CRUD).

## C. Scope matrix — is there a global reference scope? (independently verified)

Enumerated all 54 mapped tables by FK columns. Findings:

* Truly global (no scope FK): `companies`, `users`.
* **Global reusable reference precedent**: `procedure_templates`, `export_templates`
  — `id` PK, `name`, JSON payload, `is_default`, timestamps, `created_by` only.
* Everything else is project / well / report / section scoped **operational** data.
* `equipment_logs` is well+report+section scoped **operational inventory**, NOT a
  reference master. (Confirmed — the two must not be conflated.)

⟹ The earlier claim "no global scope exists" is **false**: a clean global
reference-table precedent (`*_templates`) exists to follow. What did *not* exist is a
global **engineering** reference table.

## D. Dataset re-search (§13)

Re-searched the whole repo (`*.xlsx/xls/csv/json/db/sqlite/parquet`). The only
tabular data file is `08-DDR OEOC-208 ... .xlsx` — an operational Daily Drilling
Report, **not** a pipe/casing/bit catalog. **No engineering reference dataset ships.**
Per the mission this means: **do not fabricate or seed any data.**

## E. Decision — **Outcome C (constrained)**

All persistence prerequisites are present and proven:

| Prerequisite | Status |
|---|---|
| Persistence tech + non-destructive migration | ✅ auto-creates new tables |
| Global reference-scope precedent | ✅ `procedure_templates`/`export_templates` |
| Repository + transaction pattern | ✅ `BaseRepository` + `session_scope` |
| Deterministic, stable identity | ✅ `DrillPipeSpec.identity_key` → `identity_fingerprint()` |
| Numeric / unique conventions | ✅ `Column(Float)`; `unique=True` natural keys |

Persistence is therefore **architecturally justified and independent of shipping
data**. The single seam that both a future vendor-import path *and* a future
reference selector must share is a **duplicate/conflict-aware repository** keyed on
domain identity. That is the smallest correct, non-speculative increment — so it is
what was built. **No UI, no seeded data, no new framework.**

STOP-conditions (§35) checked and NOT triggered: no fabrication (tests use synthetic
specs), no isolated parallel architecture (reuses ORM + BaseRepository + existing
migration + existing `classify_duplicate`), identity/revision resolved, provenance
carried through, no framework duplication.

## F. What was implemented

1. `DrillPipeSpec.identity_fingerprint()` — deterministic, storage-safe string of the
   domain `identity_key` (stable across float spelling `5.0`/`5.000`, and case/space).
2. `DrillPipeSpec.to_record_values()` / `from_record_values()` — a **storage bridge
   kept out of the ORM** so the domain stays persistence-agnostic. `payload_json`
   holds the full spec (provenance + issues + unmapped `extra`) for **lossless
   round-trip**.
3. `core/database.py::DrillPipeSpecRecord` — global-scoped reference table
   (`drill_pipe_specs`) modelled on the `procedure_templates` precedent: `id` PK,
   **UNIQUE `identity_fingerprint`**, denormalized canonical/queryable columns
   (canonical units: in, ppf, klbf), flattened provenance, `payload_json`, timestamps,
   `created_by`.
4. `core/repositories/drill_pipe_reference_repository.py::DrillPipeReferenceRepository`
   — controlled reads + a **duplicate/conflict-aware `upsert`** and `import_specs`
   summary, reusing the domain `classify_duplicate` verdict:

   | Situation | Outcome | Behaviour |
   |---|---|---|
   | No engineering identity, or identity-field normalization issue | `INVALID` | rejected + evidence |
   | Not present | `NEW` | insert |
   | Present, IDENTICAL | `UNCHANGED` | no write |
   | Present, DUPLICATE (incoming only *adds* missing descriptive fields) | `ENRICHED` | **non-destructive** gap-fill only |
   | Present, CONFLICTING | `CONFLICT` | **rejected; stored row untouched** |

   `import_specs` returns `rows_seen/inserted/unchanged/enriched/conflicting/invalid`
   plus per-row results, and is **row-isolated** (a bad row never aborts good rows,
   never leaves a half-written record).

## G. Traceable end-to-end proof (synthetic specs only)

`insert → identical(no-op) → enrich(add tensile, non-destructive) → conflict(rejected,
count unchanged) → invalid(rejected)`; then DB record → `from_record_values` →
`to_component(length)` → `TorqueDragEngine.calculate` → **165.23 klbf** buoyed hanging
weight (matches the established ground truth `BF = 1 − 10/65.5`). Round-trip preserved
OD/ID/weight, the enriched tensile, and provenance source.

## H. Units & numeric boundary

Canonical persisted units: OD/ID inches, weight ppf, tensile klbf — identical to the
in-memory `DrillPipeSpec` and to what `to_component` feeds the engine. The known
non-physical `ppf ↔ kg/m` `UnitManager` path is **not** touched; weight stays ppf on
the whole path.

## I. What was deliberately NOT done

* No seeded/fabricated catalog data (none exists to source).
* No Database Center / CRUD screen / browser UI, no reference-selector widget (§29).
* No `DrillPipeReferenceProvider` abstraction, no parallel provenance system (§12/§22).
* No change to `UnitManager`, engines, or `w13` (manual entry stays the primary path;
  a reference-select seam is now *available* but not wired into UI).

## J. Verification / gates

* New tests: `tests/test_drill_pipe_reference_repository.py` — 12 tests
  (persistence round-trip, UNIQUE key, identity stability, import dup/conflict/invalid
  taxonomy, row isolation, table auto-create via real `initialize()`, engine
  integration).
* Full regression: **1021 passed / 4 skipped** (baseline 1009/4 + 12 new; **0
  regressions**).
* E722=0, F821=0, ruff debt **5489** (unchanged), compileall clean, new/changed files
  ruff-clean.

## K. Files changed

* `core/engineering/drill_pipe.py` — identity fingerprint + storage bridge (domain-only).
* `core/database.py` — `DrillPipeSpecRecord` model.
* `core/repositories/drill_pipe_reference_repository.py` — new repository (new file).
* `tests/test_drill_pipe_reference_repository.py` — new tests (new file).
* `docs/audits/2026-09-13_DRILLPIPE_REFERENCE_PERSISTENCE_DECISION.md` — this document.

## L. Residual risk / follow-ups (not in scope now)

* First real consumer should be a vendor-file import adapter that produces
  `DrillPipeSpec`s and calls `import_specs` — then a reference selector in `w13`
  alongside (not replacing) manual entry.
* Identity vs. vendor **revision** (same identity, revision A/B) is intentionally left
  as a future decision — the current contract treats a contradicting revision as a
  `CONFLICT` (safe: never overwrites), which is the correct default until product
  rules for revisioning exist. No speculative revision table was added.

## M. Conclusion

DrillMaster **is** ready for a global engineering-reference persistence layer. The
minimal justified increment — a domain-identity-keyed, conflict-safe reference
repository plus its global table, proven end-to-end into the calculator — is now in
place, without fabricating data or building speculative UI.
