# Engineering Performance Completion Pass

**Date:** 2026-09-12
**Branch:** `arena/01a085e0-drill-master`
**Baseline HEAD before this pass:** `4302b62` (Weighted ROP engine, certified with documented risks)
**Repository is the source of truth** — every readiness/scope decision below was
verified against actual ORM models, join behaviour and executable tests, not
prior reports.

---

## 1. Objective

Close the Engineering Performance / KPI boundary as far as the *current
canonical data model genuinely supports it*, in one coherent vertical slice —
without speculative redesign, new frameworks, schema migrations, or fabricated
KPI values. Data readiness overrides roadmap ambition.

## 2. Repository state at start

* HEAD `4302b62`, clean tree (untracked `.github/workflows/` only).
* `4302b62` is an ancestor of / equal to HEAD; parent `515141c` exists.
* Python 3.11.2, SQLAlchemy 2.0.52. **No Alembic** — schema via
  `Base.metadata.create_all`. No migration is required or introduced by this
  pass.

## 3. Architecture reconstructed (from code)

```
Canonical import (ddr_import_service)
      ↓  ownership-integrity enforced at write (database.py _check_*_invariants)
Well ─< Wellbore(parent_wellbore_id) ─< Section
      ↓
DailyReport(well_id NOT NULL, wellbore_id NULLABLE, section_id NULLABLE)
      ↓ report_id
DrillingParameters(well_id, report_id)   TimeLog24H(report_id, duration, is_npt)
      ↓
core/engineering/engines/*  (canonical EngineeringResult contract)
      · BitPerformanceEngine.weighted_rop / paired_observation
      ↓
core/operations_intelligence.OperationsIntelligenceService
      · analyze_well  · analyze_wellbore (NEW)  · analyze_section (NEW)
      ↓
tabs/w12_Analysis, core/report_engine (EOWR), planning, export
```

Key schema facts proven:
* `DrillingParameters` has **no** `wellbore_id`/`section_id` column — scope is
  resolved through `report_id → DailyReport.wellbore_id / section_id`.
* Nullable wellbore/section FKs mean **"unknown"**, never fabricated
  (`_check_daily_report_invariants` returns early on NULL; cross-well ownership
  is rejected at write). This makes scoped aggregation safe.
* `TimeLog24H.report_id → DailyReport` lets time/NPT be scoped the same way.

## 4. Engineering capability matrix (evidence-based)

| Capability | Scope | Status before | Action taken | Status after | Evidence |
|---|---|---|---|---|---|
| Weighted ROP engine | — | PASS | none (reused) | PASS | `bit_performance.py` |
| Weighted ROP | Well | PASS (KPI dict) | none | PASS | `analyze_well` |
| Weighted ROP | Wellbore | NOT IMPLEMENTED | **implemented** | PASS | `analyze_wellbore` + tests |
| Weighted ROP | Section | NOT IMPLEMENTED | **implemented** | PASS | `analyze_section` + tests |
| avg_rop (daily-avg) | Well/Wellbore/Section | PASS | preserved + added per-scope | PASS | distinct key, untouched formula |
| Time / NPT / productive | Wellbore/Section | NOT IMPLEMENTED | **implemented** | PASS WITH LIMITATION | time-log rollup; None when no logs |
| Weighted ROP in EOWR report | Well | NOT IMPLEMENTED | **implemented** | PASS | `report_engine` KPI box + test |
| Weighted ROP in w12 UI card | Well | NOT IMPLEMENTED | deferred (layout risk) | NOT IMPLEMENTED | fixed 6-card index grid |
| Cost/day, footage/day | any | absent | not implemented | NOT READY | no reliable elapsed-time denominator |
| BHA/Bit run-duration KPIs | run | PARTIAL | not implemented | NOT READY | per-DDR JSON snapshots, no run identity |
| Advanced mud (ECD/dilution) | Well | absent | not implemented | NOT READY | required inputs absent |
| Directional (MD/TVD/DLS) | Well | existing engines | not touched | unchanged | trajectory engine already canonical |
| Cost schema | Well | Well-scoped | not touched | unchanged | no wellbore/section cost FK |

## 5. Weighted ROP completion

* **Engine:** unchanged; reused `BitPerformanceEngine.weighted_rop` /
  `paired_observation` (valid pair = depth_in, depth_out, hours all non-null AND
  depth_out ≥ depth_in AND hours > 0; invalid rows contribute neither footage
  nor hours; `None` when no valid pairs).
* **Well KPI:** unchanged (already exposed at `4302b62`).
* **Wellbore/Section KPI:** NEW `analyze_wellbore(wellbore_id)` /
  `analyze_section(section_id)` — see §6.
* **Report:** EOWR executive summary now shows a distinct
  **"Footage-Weighted ROP (m/hr)"** KPI box computed via the canonical engine
  (not recalculated in the report layer), rendering `—` when unknown.
* **null/zero:** `None → "—"` via existing `fmt_num(default=None)`; explicit
  zero footage stays a real 0.
* **Backward compatibility:** `avg_rop` DB column and the `average_rop`
  daily-average KPI are untouched; `weighted_rop` is always an additive, named
  metric. No consumer was switched from one to the other.

## 6. Wellbore & Section performance (NEW)

`OperationsIntelligenceService._analyze_scope(scope_field, scope_id)` powers both
`analyze_wellbore` and `analyze_section`:

* **Identity:** filters `DailyReport` by canonical integer FK
  (`wellbore_id` / `section_id`); drilling params and time logs are joined to
  those reports via `report_id`. No display-name matching.
* **Footage/ROP:** `BitPerformanceEngine.weighted_rop(params)` — one canonical
  formula, paired observations only. Also reports per-scope `average_rop` (mean
  of stored per-DDR `avg_rop`), kept distinct.
* **Time/NPT:** aggregated from `TimeLog24H` **independently** of drilling
  parameters, so BHA/Bit/cost multiplicity can never inflate hours (no cross
  join). `total_hours`/`npt_hours`/`productive_hours` are `None` when the scope
  has no time logs (no fabricated 0); `npt_percent` `None` when `total_hours` is
  falsy.
* **Unknown scope:** reports with NULL `wellbore_id`/`section_id` are not
  attributed to any scope; a non-existent id returns `{"reports": 0}`.

### Data readiness classification
* **Wellbore:** GREEN for footage/ROP and time/NPT **where reports carry a
  non-NULL `wellbore_id`**. Rows with NULL scope are legitimately excluded
  (unknown ≠ zero). This is a *coverage* limitation of legacy data, not a
  correctness defect → **PASS WITH DOCUMENTED LIMITATION**.
* **Section:** same as Wellbore, keyed on `section_id`.

## 7. Other engineering KPI improvements

* **Documentation truth fix:** the Weighted ROP audit claimed "23 new tests";
  the file actually contains **19** test functions. Corrected the count; the
  §16 matrix already lists exactly 19 behaviours. No fake tests added.

## 8. No-fabrication verification

* New `_analyze_scope` uses `duration or 0` only for per-row time-log summation
  (matching the existing `analyze_well` convention), guarded by
  `... if logs else None` so an empty scope yields `None`, not 0.
* Weighted ROP path uses no `or 0` / `or 1` / `setdefault(...,0)`.
* Report exposure uses `fmt_num(..., default=None)` → `—` for unknown.
* Rule upheld: missing → None/`—`; explicit zero → zero; no invalid denominator
  divides.

## 9. Multiplicity / identity verification (executed)

* Adding 2 BHA + 2 Bit children to a wellbore's report left weighted_rop
  (20.0) and total_hours (5.0) unchanged.
* Wellbore A1 excluded sibling sidetrack A2 (absurd ROP) and foreign Well B.
* Sections A1-1 / A1-2 partitioned correctly (40.0 vs 50.0).
* NULL-scope reports not attributed; foreign-scope excluded.

## 10. Test verification

Commands (headless Qt env):

```
.venv/bin/python -m pytest tests/test_wellbore_section_performance.py -q   # 12 passed
.venv/bin/python -m pytest tests/test_weighted_rop.py -q                   # 19 passed
.venv/bin/ruff check --select E722,F821 core dialogs tabs tests            # All checks passed (0)
ruff --statistics debt total                                               # 5489 (unchanged)
python -m compileall core tabs ui dialogs                                  # clean
.venv/bin/python -m pytest                                                 # 945 passed, 4 skipped
```

Baseline before pass: 933 passed / 4 skipped. After: **945 passed / 4 skipped**
(+12 new tests). E722=0, F821=0, debt 5489, compileall clean.

## 11. Changed files

Production:
* `core/operations_intelligence.py` — NEW `analyze_wellbore`, `analyze_section`,
  `_analyze_scope`.
* `core/report_engine.py` — EOWR footage-weighted ROP (collect + setdefault +
  KPI box).

Tests:
* `tests/test_wellbore_section_performance.py` — NEW, 12 tests.

Docs:
* `docs/audits/2026-09-12_WEIGHTED_ROP_IMPLEMENTATION_AUDIT.md` — count fix 23→19.
* `docs/audits/2026-09-12_ENGINEERING_PERFORMANCE_COMPLETION_PASS.md` — this file.

No unrelated production changes, debug code, temp files, secrets, or schema
migrations.

## 12. Remaining gaps (evidence-backed)

* **Legacy scope coverage:** wellbore/section KPIs only cover reports whose
  `wellbore_id`/`section_id` are populated; NULL-scope legacy rows are excluded
  (correct, but a coverage gap). Prerequisite to close: a data-side backfill of
  scope identity (out of scope here — would touch import/migration).
* **w12 Analysis UI card:** deferred; the perf-card grid is a fixed
  index-addressed 6-card layout, so adding a 7th card is a layout change beyond
  a trivial safe extension.
* **BHA/Bit run KPIs:** NOT READY — per-report JSON snapshots lack stable run
  identity.
* **footage/day, cost/day:** NOT READY — no reliable elapsed-time denominator.
* **Advanced mud / ECD:** NOT READY — inputs absent.

## 13. Certification

* Weighted ROP (Wellbore) — **PASS WITH DOCUMENTED LIMITATION** (legacy NULL
  scope coverage)
* Weighted ROP (Section) — **PASS WITH DOCUMENTED LIMITATION**
* Time/NPT (Wellbore/Section) — **PASS WITH DOCUMENTED LIMITATION**
* Weighted ROP EOWR exposure — **PASS**
* Documentation truth fix — **PASS**
* No-fabrication contract — **PASS**
* Multiplicity / identity integrity — **PASS**
* Backward compatibility (avg_rop, directional, plan/actual, cost) — **PASS**

**ENGINEERING PERFORMANCE = CERTIFIED WITH DOCUMENTED GAPS**

## 14. Recommended next phase (do NOT implement here)

A **scope-identity backfill / coverage** phase: analyse how many legacy
`DailyReport` rows have NULL `wellbore_id`/`section_id`, and design a
repository-native, no-fabrication resolver (deterministic only — e.g. single
-wellbore wells, or explicit section→wellbore mapping) to raise wellbore/section
KPI coverage without guessing. Pair it with a small `data_quality` metric that
reports scope-attribution coverage so the limitation is visible rather than
silent.
