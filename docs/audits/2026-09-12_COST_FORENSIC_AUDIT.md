# Cost Architecture — Forensic Audit & Canonical Ownership Certification

- **Date:** 2026-09-12
- **Branch:** `arena/01a085e0-drill-master`
- **Baseline commit:** `23821bc` (BHA/Bit ownership integrity — certified foundation)
- **Scope:** The Cost subsystem of DrillMaster — model, persistence boundary,
  import lineage, aggregation, UI, and physical SQLite schema — evaluated
  against the canonical Well → Wellbore → Section → DailyReport hierarchy.
- **Sources of truth:** repository code, executable behaviour, physical SQLite
  schema (`PRAGMA`), and the full test suite. Prior Arena reports, doc claims,
  and commit messages were **not** trusted; every finding below is reproduced
  from live behaviour.

---

## 1. Executive Summary

The Cost subsystem is a **single flat `cost_records` table owned only at the
well level** (`well_id`), holding a conflated planned/actual pair per row. It
faithfully preserves amounts, currency, and category without fabrication at the
model layer, and its aggregation paths are free of the join-multiplication class
of bug. Its analytical dimensions (rig, vendor, AFE) are stored as attributes,
never as identity.

One **HIGH-severity persistence defect** was found and fixed: cost rows that
carried their category only under the `cost_category` alias — the exact shape
emitted by the profile importer — were **silently dropped together with their
money** (`imported=0, failed=0, review=0`). The alias fallback was dead code
(it read the already-filtered column dict). Fixed minimally by resolving the
alias against the raw source row before column filtering; category-less rows
continue to route to review, never to fabrication or silent loss.

Two **architectural risks remain and are documented, not "fixed"**, because a
safe fix exceeds the minimal-change bar for this audit (they require a schema
version bump that would regress the certified foundation's version-assertion
tests, and a design decision about transaction identity): **(a)** cost has no
`report_id`, so it carries no transaction identity and is not idempotent across
re-import at the row level; **(b)** planned and actual are conflated in one row,
blurring the PLAN vs ACTUAL distinction. Both are mitigated in production by the
import-service source-fingerprint guard.

**Verdict: COST ARCHITECTURE = PASS WITH REMAINING RISKS.**
**REMOTE CI = BLOCKED / NOT OBSERVED.**

---

## 2. Method

- Located every Cost definition, API, import site, aggregation, UI touchpoint,
  and test (`grep`, direct reads).
- Inspected the physical schema on a fresh v3 database (`PRAGMA table_info`,
  `foreign_key_list`, `index_list`, `foreign_keys`).
- Ran targeted forensic probes against a live `DatabaseManager`: aliased-category
  import, re-import double-count, negative/credit amounts, default currency,
  zero-vs-NULL aggregation.
- Traced import lineage from both extraction paths (`table_record_mapper` and
  `profile_import_engine`) to `save_imported_multi_tab_data_atomic`.
- Applied one minimal fix on demonstrated defect; added regression tests; ran
  the full suite and debt/lint gates.

---

## 3. What "Cost" Represents Today

`CostRecord` (`core/database.py:1926`, duplicated verbatim in
`core/db_models.py:1606` which is **not** used to build the live schema) is a
**flat per-well cost line** with these columns:

| Column | Type | Note |
|---|---|---|
| `id` | INTEGER PK | |
| `well_id` | INTEGER, NOT NULL, FK→wells ON DELETE CASCADE | **sole ownership anchor** |
| `category` | VARCHAR(100), NOT NULL | required |
| `description` | TEXT | |
| `planned_cost` | FLOAT, default 0.0 | conflated with actual (see §12) |
| `actual_cost` | FLOAT, default 0.0 | conflated with planned |
| `variance` | FLOAT, default 0.0 | denormalised, never computed on write |
| `currency` | VARCHAR(10), default "USD" | assumed default (see §13) |
| `cost_date` | DATE | |
| `afe_number` | VARCHAR(50) | analytical attribute |
| `vendor` | VARCHAR(200) | analytical attribute |
| `invoice_number` | VARCHAR(100) | analytical attribute |
| `cost_type` | VARCHAR(50), default "OPEX" | |
| `status` | VARCHAR(50), default "Pending" | |
| `created_at`/`updated_at` | DATETIME | |
| `created_by` | INTEGER, FK→users | |

It is best characterised as an **aggregate/estimate line per well** (a manual
AFE/budget row), not a daily transaction, not an invoice, not a per-operation
material cost. There is no discriminator separating PLAN / ACTUAL / ESTIMATE /
ALLOCATED — a single row holds both a planned and an actual number.

## 4. Granularity vs Ownership

The only ownership level expressed is the well. This is defensible for a
budget/AFE aggregate but is **too coarse** for daily/operation/service/material
costs, which the hierarchy could attribute to a DailyReport (and thence Section
/ Wellbore). Crucially, the code does **not** invent a false ownership level:
because no `report_id`/`section_id`/`wellbore_id` column exists on cost, no cost
is mis-attributed to a report it does not belong to. The limitation is
under-attribution, not mis-attribution (see §11, Risk R-1).

## 5. Rig Is Never Identity — PASS

Rig appears nowhere in `CostRecord`. Rig day-rate handling lives entirely in the
`w16_Cost_Management` UI as an **operator-supplied analytical rate**
(`rig_rate + spread_rate`), never persisted as a cost identity or key. The
report engines only apply a rig/spread rate when the caller explicitly supplies
one (`rate_supplied = daily_rate is not None and spread_rate is not None`);
otherwise they report stored records and leave derived costs `None`
(`core/report_engine.py:1716-1745`). No fabricated rig-day rate. **PASS.**

## 6. Well Identity vs Free Text — PASS

`well_id` is an integer FK, resolved through the canonical well-resolution path
during import (`_resolve_import_well`). Cost never keys on a free-text well name.

## 7-9. Wellbore / Section / Report Ownership

Cost has **no** `wellbore_id`, `section_id`, or `report_id` column — neither in
the ORM nor in the physical schema (verified via `PRAGMA`). It is a pure
well-level entity. Consequently there is no persistence-boundary ownership
contract to enforce for cost (unlike BHA/Bit/Downhole, which are report-scoped);
`before_flush` ownership dispatch correctly does not include `CostRecord`. This
is coherent — but it is the root of Risk R-1 (no transaction identity / no
report continuity).

## 10. Operation Entity — SEARCHED, DOES NOT EXIST

There is **no** `Operation` model or `operations` table. The nearest names
(`OperationalProcedure`, `core/operations_intelligence.py`) are procedure
templates and analytics, not a drilling-operation entity. Therefore cost cannot
be attributed to an Operation because the entity does not exist. No cost code
assumes one. (KPI note: §38.)

## 11. Transaction Identity — RISK (R-1)

There is nothing that makes two cost rows "the same transaction": no
`report_id`, no natural key, no unique constraint. The import loop
(`save_imported_multi_tab_data_atomic`, section "10. Cost") simply **appends**
every extracted row. Every sibling report-scoped collection (Cement, Bit, BHA,
Downhole, Bulk, Fuel/Water) performs an idempotency check
(`existing = session.query(...).filter(report_id == report_id)...`) — **cost is
the only one that does not.**

**Reproduced double-count** (baseline `23821bc`, before considering the
production fingerprint guard):

```
First import  -> imported=1
Second import (identical DDR, same report) -> total cost rows = 2
get_cost_summary -> Fuel: planned 4000, actual 5000   (doubled from 2000/2500)
```

Row-level re-import doubles the money. In production this specific double-import
is blocked by the import service's source-fingerprint guard
(`find_import_audit(source_fingerprint)` → "Identical source already imported")
before the atomic save runs, so an operator re-importing the same file is
protected. But the *persistence layer itself* provides no idempotency, so any
path that bypasses the fingerprint guard (a slightly edited re-export, a
programmatic caller) will double-count. **Documented as Risk R-1, not fixed** —
the safe fix is a `report_id` column + `(report_id, category, description)`
dedup, which requires a schema v4 bump that regresses five certified-foundation
tests asserting `schema_version == 3` (`test_release_smoke.py`,
`test_wellbore_schema_v3.py`). That exceeds this audit's minimal-change mandate.

## 12. Line vs Aggregate & PLAN/ACTUAL Conflation — RISK (R-2)

`planned_cost` and `actual_cost` live on the **same row**. There is no
`kind`/`ledger` discriminator distinguishing a plan line from an actual line
from an estimate. Aggregations sum both columns independently
(`func.sum(planned_cost)`, `func.sum(actual_cost)`), which is arithmetically
consistent but architecturally blurs PLAN vs ACTUAL and makes a pure line-level
actual ledger (with its own provenance) impossible without carrying a phantom
planned=0.0 on every actual row. **Documented as Risk R-2.** No traceability
column (source cell/file) exists on cost rows, though import review captures
provenance for rejected rows.

## 13. Currency / Amount / Unit Semantics — MINOR RISK (R-3)

`currency` defaults to `"USD"` at the column level. A cost saved without a
currency is silently stamped `USD` (reproduced). This is a mild fabrication of
an unknown, contrary to the project's no-fabrication principle for other fields.
It is **not** fixed here because (a) it is a low-severity default rather than a
data-loss defect, (b) changing the default to NULL is a schema-semantics change
with UI implications (`w16` offers USD/EUR/GBP/IRR) that deserves its own
scoped change, and (c) no current reader crashes on NULL currency. **Documented
as Risk R-3.** Amounts are stored as FLOAT (acceptable for this app's scale; no
integer-minor-unit requirement is present).

## 14. Zero ≠ NULL — MOSTLY PASS, NOTED

Aggregation readers use the `float(x or 0)` idiom
(`get_cost_summary`, `CostReportEngine`, `get_actual_vs_plan`), which coerces a
genuine NULL to 0 **inside a SUM** — harmless for a sum (NULL and 0 contribute
identically to a total) and the outer "record exists?" guard preserves the
None-vs-empty distinction at the dataset level (`... if cost_records else None`).
The column-level `default=0.0` on `planned_cost`/`actual_cost` means a row
created without an amount stores 0.0, not NULL — a mild zero-vs-unknown blur at
write time, entangled with Risk R-2. No reader mis-reports an empty dataset as
zero cost. Acceptable; noted.

## 15. Negative / Credit / Adjustment Amounts — PASS (with dormant hazard)

The persistence layer **accepts negative amounts** (reproduced: a −500.0
adjustment round-trips intact). Good — credits/rebates/adjustments are real.
There is a `CostValidator.validate` (`core/validators.py:530`) that would
`add_error` on negative `actual_cost`, but it is **dead code**: it is imported
nowhere and wired into no path (verified). Because it is unused it does not
block credits today; it is a latent hazard if ever wired in. Left untouched
(modifying an unused validator is out of scope and risks unrelated churn); noted
as a follow-up.

## 16-18. Import Lineage / Atomicity / Idempotency

- **Lineage:** Production extraction is `table_record_mapper.extract_records`
  (invoked from `dialogs/smart_template_dialog._merge_table_records`), which
  emits canonical keys (`category`, `planned_cost`, `actual_cost`, `vendor`).
  The `profile_import_engine` path emits alias keys (`cost_category`,
  `daily_cost`, `cum_cost`) and is currently only instantiated by tests — but
  its output shape is what exposed defect **COST-01** and is a supported input
  contract to the atomic save. Both feed
  `save_imported_multi_tab_data_atomic`.
- **Atomicity:** Cost is persisted inside the single `session_scope()`
  transaction of the atomic import alongside all other tabs; a validation error
  in any report-scoped row triggers a full `session.rollback()` (verified in
  `ddr_import_service`), so cost is rolled back with the rest. **PASS.**
- **Idempotency:** Not at the row level (Risk R-1); protected at the file level
  by the fingerprint guard.

## 19. Multi-DDR Continuity — N/A / Risk R-1

Because cost is well-scoped with no report link, it neither duplicates across
reports (there is no per-report cost row to duplicate) nor tracks per-report
continuity. Continuity is simply not modelled. This is the flip side of R-1.

## 20. Sidetrack / Workover Isolation — PASS (by construction)

Cost attaches to `well_id`. A sidetrack is a Wellbore within the same Well
(v3 model), so all costs of a well — main bore and sidetracks — aggregate under
the well. Cost is not mis-attributed across wells. Finer isolation
(per-wellbore cost) is not possible today (R-1) but no incorrect isolation
occurs.

## 21. Category Semantics — PASS

`category` is required (NOT NULL). Import never fabricates a category: a row with
neither `category` nor `cost_category` is routed to review by the required-field
loop and is **not** persisted (reproduced). The `cost_category` alias is now
resolved correctly (COST-01 fix).

## 22. Inventory Double-Count — PASS

Material/inventory quantities live in `BulkMaterials`/`FuelWaterInventory`
(quantities, not money). Cost rows are independent money lines. There is no code
path that both books a bulk-material quantity **and** derives a cost row from
it, so no inventory→cost double count exists.

## 23. Service Linkage — PASS (independent)

`ServiceCompanyPOB` carries `npt_hours`/`duration_day` but no money. Cost is not
derived from service rows, so there is no service→cost double count and no
hidden linkage to break.

## 24. NPT Cost — PASS

NPT cost is computed only as an allocation of **stored actual cost** by the NPT
time fraction, and only when both a stored actual cost and recorded time exist
(`core/report_engine.py:1377-1384`): `npt_cost = total_npt/total_hours *
actual_cost`, else `None`. No implicit rig-day rate is fabricated. A separate
scalar subquery is used (no join to time logs), so there is no join
multiplication of the cost sum.

## 25-26. API Surface & generic_save Bypass — PASS

Public APIs: `save_cost_record` (upsert by id, column-filtered insert),
`get_cost_records` (well-scoped, raises on query failure rather than returning
empty), `get_cost_summary` (grouped sums). The import path builds `CostRecord`
directly but through the same `session_scope()` and the global `before_flush`
ownership listener — no path bypasses the transaction boundary. Cost has no
report-scoped ownership contract to bypass (§7-9), so its absence from
`_REPORT_SCOPED_WELL_MODELS` is correct.

## 27-28. Physical Schema & Migration — PASS (with R-1 note)

Fresh v3 physical schema (verified):

```
CREATE TABLE cost_records (
  id INTEGER NOT NULL, well_id INTEGER NOT NULL, category VARCHAR(100) NOT NULL,
  description TEXT, planned_cost FLOAT, actual_cost FLOAT, variance FLOAT,
  currency VARCHAR(10), cost_date DATE, afe_number VARCHAR(50), vendor VARCHAR(200),
  invoice_number VARCHAR(100), cost_type VARCHAR(50), status VARCHAR(50),
  created_at DATETIME, updated_at DATETIME, created_by INTEGER,
  PRIMARY KEY (id),
  FOREIGN KEY(well_id) REFERENCES wells (id) ON DELETE CASCADE,
  FOREIGN KEY(created_by) REFERENCES users (id))
```

- FKs enforced physically (`PRAGMA foreign_keys = 1`); `well_id` CASCADE is
  correct (deleting a well removes its costs).
- **No indexes at all** — not even on `well_id`, the sole query filter. Every
  read is a full-table scan. Low-severity performance risk at scale
  (Risk R-4); not a correctness defect.
- No cost-specific migration exists; the table is created by the generic
  "missing table" step. No `report_id` to migrate (R-1).

## 29. Aggregation Join-Multiplication — PASS (critical check)

Every cost aggregation was inspected for the "$10k becomes $20k via 1-to-many
join" hazard:

- `get_cost_summary` — `group_by(category)` over a **single-table** filter. No
  join. Safe.
- `CostReportEngine._collect_data` — iterates a single well-filtered
  `cost_records` list; NPT hours summed by a **separate** query. No join across
  cost. Safe.
- NPT/actual-cost engines — `func.sum(CostRecord.actual_cost)` in a **scalar
  subquery** filtered by `well_id`, never joined to time logs. Safe.
- `get_actual_vs_plan` — sums a single well-filtered list. Safe.

No aggregation multiplies a cost by a related-table cardinality. **PASS.**

## 30. UI Scope — EXPLICIT

`tabs/w16_Cost_Management.py` is a **rate-based calculator and AFE worksheet
only**. It does **not** read from or write to `CostRecord` (`save_data`
returns `True`; `refresh` recomputes UI totals). AFE rows, rig/spread rates and
currency are in-memory widgets, never persisted. Persisted cost exists solely
via import and the `save_cost_record` API. This scope is now documented so no
reader assumes the Cost tab reflects stored records.

## 31. Provenance

Import review rows capture source location for rejected/review cost rows
(`review_issue(... source=_source_for_row(c) ...)`), but a **persisted**
`CostRecord` carries no per-field source-cell provenance column. Provenance for
accepted rows is therefore not retained on the row (entangled with R-2). Noted.

## 32. Duplication-Path Map

| Path | Double-count? |
|---|---|
| Re-import identical file via UI | No — fingerprint guard blocks before save |
| Re-import edited re-export / programmatic atomic call | **Yes** — no row idempotency (R-1) |
| Inventory → cost | No — separate subsystems, no derivation |
| Service → cost | No — no money on service rows |
| NPT cost allocation | No — fraction of stored actual, scalar subquery |
| Aggregation joins | No — no 1-to-many join over cost |

---

## Defects

### COST-01 — Aliased cost category silently dropped with its money (HIGH) — FIXED

- **Severity:** HIGH (silent financial data loss, no error, no review entry).
- **Observed:** A cost row supplying its category only via the `cost_category`
  alias (the profile-importer shape) produced **no** `CostRecord` and **no**
  review row: `save_imported_multi_tab_data_atomic(...) -> imported=0, failed=0,
  review=0`, DB rows = 0. The row's `planned_cost`/`actual_cost` vanished.
- **Expected:** The alias resolves to `category` and the row persists with its
  amounts; only a row with genuinely no category goes to review.
- **Root cause:** The alias fallback executed **after** column filtering:
  ```python
  filtered = {k: v for k, v in c.items() if k in valid_keys and k != "id"}
  if not filtered.get("category") and filtered.get("cost_category"):  # dead:
      filtered["category"] = filtered["cost_category"]                # cost_category
                                                                      # already gone
  ```
  `cost_category` is not a `CostRecord` column, so it was stripped by `filtered`;
  the fallback could never fire. With no `category`, the bare `continue`
  discarded the row. Pre-validation checked the **raw** row (which had
  `cost_category`) and passed it, so nothing flagged the loss.
- **Evidence:** Live probe (above) on `23821bc`; `core/database.py` §"10. Cost".
- **Fix (minimal):** Resolve the alias against the **raw source row** before
  column filtering (`core/database.py`, cost import block). Category-less rows
  still `continue`, but they are already routed to review by the required-field
  loop, so no money is lost and no category is fabricated.
- **Regression tests:** `tests/test_integration.py::TestCostImportLineage`
  (3 tests): aliased category persists with amounts; category-less row → review,
  no persisted row; explicit category/amounts round-trip through
  `get_cost_summary`.
- **Verification:** New tests pass; aliased row now `imported=1`; full suite
  902 passed / 4 skipped; debt 5489 (neutral); E722/F821 = 0.

---

## Remaining Risks (documented, not changed — outside minimal-fix mandate)

| ID | Sev | Risk | Why not fixed now | Mitigation |
|---|---|---|---|---|
| R-1 | MED | No transaction identity / `report_id`; row-level re-import double-counts | Needs `report_id` + dedup + schema v4 bump → regresses 5 certified `schema_version==3` tests | Import-service fingerprint guard blocks identical-file re-import |
| R-2 | MED | PLAN/ACTUAL conflated in one row; no ledger discriminator; no per-row provenance | Design decision (ledger model) beyond a defect fix; broad blast radius | Sums are arithmetically correct |
| R-3 | LOW | `currency` defaults to `"USD"` (fabricates unknown) | Schema-semantics + UI change deserving its own scope | No reader crashes on NULL; single-currency ops unaffected |
| R-4 | LOW | No index on `cost_records.well_id`; full-scan reads | Performance, not correctness; index add is a separate scoped change | Small data volumes today |
| R-5 | LOW | Dead `CostValidator` would reject negative amounts if wired | Modifying unused code is out of scope | Not wired into any path; credits accepted today |

---

## §40. Gate Matrix (A–R)

| Gate | Dimension | Result |
|---|---|---|
| A | Cost meaning / kind identified (§3) | PASS |
| B | Correct granularity, no false ownership level (§4) | PASS |
| C | Rig never identity (§5) | PASS |
| D | Well identity is FK, not free text (§6) | PASS |
| E | Wellbore/Section/Report ownership coherent (§7-9) | PASS (well-scoped by design) |
| F | Operation entity searched (§10) | PASS (does not exist; nothing assumes it) |
| G | Transaction identity / idempotency (§11) | **RISK R-1** |
| H | Line vs aggregate; PLAN/ACTUAL distinction (§12) | **RISK R-2** |
| I | Currency/amount/unit semantics (§13) | RISK R-3 (minor) |
| J | Zero ≠ NULL (§14) | PASS (noted) |
| K | Negative/credit amounts allowed (§15) | PASS |
| L | Import lineage / atomicity (§16-18) | PASS |
| M | Multi-DDR continuity / sidetrack isolation (§19-20) | PASS (no mis-attribution) |
| N | Category semantics / no fabrication (§21) | PASS |
| O | Inventory / Service / NPT double-count (§22-24) | PASS |
| P | API & generic_save bypass (§25-26) | PASS |
| Q | Physical schema & migration (§27-28) | PASS (R-4 index note) |
| R | Aggregation join-multiplication (§29) | PASS |
| — | Silent cost drop (COST-01) | **FIXED** |
| — | UI scope explicit (§30) | PASS |

---

## §42. Final Verdict

**COST ARCHITECTURE = PASS WITH REMAINING RISKS.**

DrillMaster can record, preserve, attribute (at the well level), query, and
aggregate real drilling costs against the canonical hierarchy **without** using
rig or free-text names as identity, **without** fabricating unknown categories
or wells, and **without** aggregation join-multiplication. The one silent
data-loss defect (COST-01) is fixed with regression cover. The remaining risks
(R-1 transaction identity/idempotency, R-2 PLAN/ACTUAL conflation, R-3 default
currency, R-4 missing index, R-5 dead validator) are attribution-completeness
and semantics limitations, not correctness failures of the stored data, and are
mitigated in production. None blocks a future KPI/Performance layer, though R-1
and R-2 would need resolution before per-report/per-operation cost KPIs
(see §38).

**REMOTE CI = BLOCKED / NOT OBSERVED.** No CI run was observed or verified from
this environment; `.github/workflows/` is untracked and cannot be pushed without
the `workflows` permission. No claim of CI PASS is made (§41).

## §38. KPI Compatibility (check only — not implemented)

- Well-level cost aggregates (cost/well, cost/meter, category breakdown) are
  available today and KPI-ready.
- Per-report / per-section / per-operation cost KPIs are **blocked** by R-1
  (no `report_id`) and would require the transaction-identity work.
- No premature `CostRun` entity was invented (§37).

## §43. Change Verification

- `git status` / `git diff` reviewed before finalising (see commit).
- Files changed: `core/database.py` (COST-01 fix, alias resolved pre-filter),
  `tests/test_integration.py` (+3 regression tests), this report.
- Full suite: **902 passed / 4 skipped** (was 899/4; +3 new). E722=0, F821=0,
  ruff debt = 5489 (ceiling, neutral). Certified foundation (Wellbore v3,
  BHA/Bit) unchanged and green.
