# Scope Identity Integrity & Attribution Completion Pass

**Date:** 2026-09-12
**Branch:** `arena/01a085e0-drill-master`
**Baseline HEAD:** `4a55288`
**Source of truth:** the repository checkout, its ORM/schema behaviour, and
executed tests — not prior reports.

---

## 1. Objective

Complete the canonical **Well → Wellbore → Section** identity/attribution chain
so longitudinal engineering KPIs can use Wellbore/Section scope without guessing,
fabricating, or misattributing historical data — implementing only what the
repository can prove safe.

## 2. Repository state at start

* HEAD `4a55288`, clean tree (only untracked `.github/workflows/`).
* Baseline: **945 passed / 4 skipped**, E722=0, F821=0, ruff debt 5489,
  compileall clean.
* No Alembic; schema via `Base.metadata.create_all` + an in-code SQLite v3
  upgrade path.
* **No production DB corpus exists** in the repo — synthetic in-memory fixtures
  only. Attribution statistics are therefore behavioural (proven on fixtures),
  not measured against a production database. This is stated rather than
  fabricated.

## 3. Canonical identity model (reconstructed from code)

| Entity | Scope FKs | Nullability | Notes |
|---|---|---|---|
| `Well` | `id` | PK, immutable | canonical anchor |
| `Wellbore` | `well_id` NOT NULL, `parent_wellbore_id` | parent nullable | identity `(well_id, name)`; only a `sidetrack` may carry lineage |
| `Section` | `well_id` NOT NULL, `wellbore_id` | `wellbore_id` NULLABLE | NULL = unknown bore |
| `DailyReport` | `well_id` NOT NULL, `wellbore_id`, `section_id` | both scope FKs NULLABLE | legacy rows often have `section_id` set, `wellbore_id` NULL |
| `DrillingParameters` | `well_id`, `report_id` | — | **no** wellbore/section column; inherits scope via `report_id → DailyReport` |
| `TimeLog24H` | `report_id` | — | inherits scope via `report_id` |
| `BHAReport` / `BitReport` / `DownholeEquipment` | `well_id`, `report_id` | report_id nullable | report-scoped snapshots |

**Write-time invariants (already present, verified):** a `before_flush`
listener (`_enforce_ownership_integrity`) runs `_check_wellbore_invariants`,
`_check_section_invariants`, `_check_daily_report_invariants`, and
`_check_report_scoped_well_ownership` on every session — so no save path (ORM,
service, import) can commit cross-well ownership. **NULL scope is explicitly
allowed as "unknown" and never fabricated.**

**The documented gap:** `core/database.py` v3 upgrade note states existing rows
"keep wellbore_id = NULL ('unknown') until a deterministic attribution assigns
them." No such resolver existed. This pass adds it.

## 4. Scope-attribution classification (four states, never boolean)

`core/scope_attribution.py` → `ScopeAttributionService`:

* `RESOLVED`   — unique, provable owner found (and assigned in `resolve`).
* `AMBIGUOUS`  — ≥2 candidate owners, no canonical discriminator → left NULL.
* `UNRESOLVED` — 0 candidate owners → left NULL.
* `INVALID`    — existing scope contradicts the chain (detected read-only,
  never "repaired").
* `ALREADY`    — scope already present; preserved, never overwritten.

### Resolution rules (safe only)

**Wellbore** (report `wellbore_id` NULL):
1. `via_section` — the report's Section already owns a non-NULL wellbore (the
   strongest evidence; the section itself proves the bore).
2. `via_unique_wellbore` — the report's Well has exactly ONE wellbore.
Else `AMBIGUOUS` (≥2 bores) or `UNRESOLVED` (0 bores).

**Section** (report `section_id` NULL):
1. `via_unique_section_in_wellbore` — the known bore has exactly ONE section.
2. `via_unique_section_in_well` — the well has exactly ONE section.
Else `AMBIGUOUS` / `UNRESOLVED`.

**Explicitly NOT used as evidence:** rig name, display-name similarity, date
proximity, or "looks likely". These are called out in the module docstring.

### Safety properties (all tested)
* Writes through the ORM → the ownership invariants remain the ultimate net; a
  cross-well assignment raises rather than commits.
* Never overwrites existing non-NULL scope → **idempotent** (second `resolve`
  applies 0).
* `analyze()` is read-only; `resolve()` commits once; both group children per
  well (no N+1).

## 5. Coverage metrics

* `ScopeAttributionService.coverage(well_id=None)` → wellbore/section coverage
  percentages, counting ONLY genuinely-attributed reports (`ALREADY` +
  `RESOLVED`). NULL/ambiguous/unresolved are never counted as covered.
  Percentages are `None` when there are no reports (unknown, not 0/100).
* Integrated into the **existing** `DataQualityService.for_well` as two metrics
  ("Wellbore attribution", "Section attribution") — no second data-quality
  framework, no new tab. Failure is defensive (logged, non-fatal).

## 6. KPI impact (executed evidence)

Before resolution, a well whose reports have NULL scope returns
`analyze_wellbore(...) → {"reports": 0}` (correct: unknown, not fabricated).
After `resolve(well)` attributes 2 reports (4 FK assignments: 2×wellbore +
2×section), the same wellbore/section KPIs become populated:
`weighted_rop = 40.0`, `weighted_rop_valid_pairs = 2`, `total_hours = 10.0`
(see `test_kpi_coverage_improves_after_resolution`). Reports that remain
`AMBIGUOUS`/`UNRESOLVED` keep unknown KPI semantics
(`test_unresolved_reports_keep_unknown_kpis`).

## 7. Import / canonicalization audit

The DDR import path (`ddr_import_service.py`) already attributes wellbore ONLY
when the source names one, requires a section, and backfills a section's
`wellbore_id` only when previously NULL — never overwriting. The root cause of
NULL wellbore scope is **legitimate source ambiguity**, not an import defect, so
no import change was made (a change would risk fabricating identity). The new
resolver is the correct, deterministic post-hoc closure for the safe subset.

## 8. Boundary audits (no changes needed)

* BHA/Bit/Downhole snapshots: `(well_id, report_id)` coherence already enforced
  by `_check_report_scoped_well_ownership`.
* NPT/time (`TimeLog24H`) and DrillingParameters: report-scoped; KPI rollups
  aggregate time from time logs independently of drilling params (no
  multiplying join) — verified in the existing wellbore/section KPI tests.
* Cost: unchanged (Well-scoped; no wellbore/section FK — out of safe scope).

## 9. Files changed

Production:
* `core/scope_attribution.py` — NEW `ScopeAttributionService` (analyze /
  resolve / coverage; four-state classification).
* `core/data_quality.py` — `for_well` now emits Wellbore/Section attribution
  coverage metrics (additive; defensive).

Tests:
* `tests/test_scope_attribution.py` — NEW, 15 tests.

Docs:
* `docs/audits/2026-09-12_SCOPE_IDENTITY_ATTRIBUTION_PASS.md` — this file.

No schema migration, no new framework, no UI redesign, no unrelated changes.

## 10. Test evidence

```
.venv/bin/python -m pytest tests/test_scope_attribution.py -q          # 15 passed
.venv/bin/python -m pytest tests/test_wellbore_section_performance.py \
    tests/test_wellbore_ownership_integrity.py tests/test_wellbore_schema_v3.py \
    tests/test_operations.py tests/test_operations_intelligence_regressions.py \
    tests/test_weighted_rop.py -q                                       # all passed
.venv/bin/ruff check --select E722,F821 core dialogs tabs tests         # 0
ruff debt total                                                         # 5489 (unchanged)
python -m compileall core tabs ui dialogs                              # clean
git diff --check                                                        # clean
.venv/bin/python -m pytest                                             # 960 passed, 4 skipped
```

Baseline 945 → **960 passed** (+15). Test matrix covered: single-wellbore /
single-section resolution, via-section, multiple-wellbore & multiple-section
ambiguity, unresolved, foreign-wellbore/section rejection, existing-scope
preservation, idempotency, sidetrack sibling isolation, INVALID detection,
coverage-not-fabricated, KPI before/after improvement, unresolved-keeps-unknown,
empty-database safety.

## 11. Remaining gaps (evidence-backed)

* **No production corpus:** attribution statistics are proven on synthetic
  fixtures; real-data coverage cannot be measured in this repo.
* **AMBIGUOUS multi-wellbore wells:** deliberately left unresolved — closing
  them safely needs a canonical discriminator that the data model does not yet
  carry (e.g. a per-report wellbore identifier from the source document). A
  future import-side enhancement could capture it; guessing is refused here.
* **`resolve()` is not auto-invoked:** it is an explicit, auditable operation
  (service method), not wired into import or a migration, because the repo has
  no migration system and silent backfill would obscure the audit trail. The
  safe integration point (an admin/maintenance action or a call after bulk
  import) is documented for a later pass.
* **UI exposure:** coverage flows through `DataQualityService.for_well`
  (already surfaced by the Analysis data-quality path); no new card/tab added.

## 12. Certification

* Canonical identity model — correct (verified)
* Deterministic attribution — correct; four-state; provable-only
* Ambiguity preserved — PASS
* Invalid ownership rejected — PASS (write-time invariants + read-time INVALID)
* KPI isolation & before/after improvement — PASS
* No fabrication (NULL≠0, unknown preserved) — PASS
* Idempotency — PASS
* Tests pass, gates green, debt unchanged — PASS

**SCOPE IDENTITY = CERTIFIED WITH DOCUMENTED GAPS**

Gaps are limited to: absence of a production corpus, intentionally-unresolved
ambiguous multi-wellbore wells, and the deliberate choice to keep `resolve()` an
explicit auditable action rather than silent auto-backfill.

## 13. Recommended next phase (not implemented)

Capture a **canonical per-report wellbore/section discriminator at import time**
(from the source document's own wellbore identifier) so today's AMBIGUOUS
multi-wellbore reports become deterministically RESOLVED — plus a maintenance
action that runs `ScopeAttributionService.resolve()` after bulk import and
surfaces the coverage delta.
