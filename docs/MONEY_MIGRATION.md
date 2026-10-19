# Money representation: current state and migration design

Status: **design only. No persisted monetary value has been migrated.**
Changing the stored representation is an **owner-gated** decision (M43). This
document records what was verified, what was changed in code, and how a
migration would be executed and rolled back if the owner approves it.

## 1. Confirmed monetary columns

Verified by inventory of `core/database.py` (schema v6). Every other column
whose name suggests an amount (`*_cost` in hydraulics, volumes, weights,
rates) is a physical quantity, not money, and is out of scope.

| Column | Type | Currency source | Notes |
|---|---|---|---|
| `cost_records.planned_cost` | `Float` (SQLite REAL) | `cost_records.currency` | nullable; NULL = unknown |
| `cost_records.actual_cost` | `Float` | `cost_records.currency` | nullable; NULL = unknown |
| `cost_records.variance` | `Float` | `cost_records.currency` | derived on insert/update by the `_canonicalize_cost_record` listener as `planned - actual` |
| `projects.budget` | `Float`, default `0.0` | `projects.currency` | |
| `npt_reports.cost_impact` | `Float` | none recorded | currency is not stored for NPT cost impact |

Copies of these values also exist as JSON numbers in history: report revision
snapshots (`report_revisions.snapshot`, which include report-owned rows such as
`npt_reports`) and free-text audit details. These are historical evidence and
must never be rewritten by a migration (see section 6).

## 2. What changed in code (M43, no data change)

* `core/money.py` adds Decimal-safe helpers:
  * `to_decimal(value)` returns the exact decimal a float *displays* (via
    `repr()`, the shortest round-trip text: `0.1` becomes `Decimal("0.1")`).
    Accepted and rejected inputs are exactly those of the existing
    `optional_number` contract: `None`/`""` are unknown (`None`); booleans,
    non-numeric text, NaN and infinities raise `EngineeringError`.
  * `sum_money(values)` keeps the complete-total contract (empty or any
    unknown gives `None`) but sums exactly in decimal, sizing precision to the
    operands so it never rounds, and returns the nearest `float`. A total that
    would overflow a float is refused, never returned as infinity.
  * `to_minor_units(value, scale=, rounding=)` returns `(integer, exact)` for
    a future fixed-point column. The rounding rule is a **required**
    argument; `exact=False` reports any conversion that changed the amount.
* `cost_semantics.summarize_costs` (all cost totals in the Cost Management tab,
  the reports and the operations summary) now uses `sum_money`.

**Defect fixed (demonstrated before the change).** Float accumulation made
equal planned and actual totals differ in the last bits. Planned `[0.3]` versus
actual `[0.1, 0.2]` produced `total_actual = 0.30000000000000004` and a
variance of `-5.55e-17`, displayed as `USD -0.00` and coloured as over budget.
Planned `1000000.10 + 0.20` versus actual `1000000.00 + 0.30` produced
`-1.16e-10`. Both now give a variance of exactly `0.0` (`USD 0.00`).
The defect was demonstrated on Python 3.11. From Python 3.12 the built-in
`sum()` compensates float rounding (Neumaier), which removes some cases (ten
times `0.1` sums to `1.0`) but not these two. This was checked by reproducing
CPython's compensated algorithm, not on a 3.12 interpreter, so it applies to
the Python 3.12 Windows build as well. `sum_money` is exact on every
supported version.
Regression test: `tests/test_money.py::test_exactly_on_budget_totals_have_zero_variance_not_negative_residue`
(fails if the float sum is restored).

**Deliberately unchanged** (each would alter stored values or displayed
figures without an owner decision):

* Stored values and their REAL type, and the per-row `variance` listener
  (float subtraction already has the correct sign for unequal amounts).
* `complete_total`, which also totals physical quantities (bulk materials,
  requested quantities, NPT hours). Decimal summation is applied to money only.
* Display: `format_money` keeps Python float formatting, which rounds the exact
  binary value. `2.675` is stored as `2.67499999999999982236431605997495353221893310546875`
  and displays `2.67`. A decimal half-up rule would display `2.68`. Changing
  the displayed rounding rule is owner decision D3.
* Edit widgets keep two decimals (`w16_Cost_Management.py`).

## 3. Target representation (options)

| Option | Storage | Pros | Cons |
|---|---|---|---|
| **A. Integer minor units** (recommended) | `INTEGER` amount + currency code + scale | exact; native SQLite sum/compare; indexable; 64-bit range is about ±9.2e18 minor units | needs a scale per currency; every reader and writer changes |
| B. Decimal text | `TEXT` such as `"1234.50"` | exact; scale flexible per row | SQLite `SUM`/comparison on TEXT is wrong without casting; easy to misuse in raw SQL |
| C. Keep REAL, decimal at boundaries | unchanged | no migration; already done for totals | values like `0.1` remain inexact in storage; every new aggregation must remember `sum_money` |

Option C is the current state. Option A is recommended if the owner wants
exact storage; it is what `to_minor_units` prepares for.

## 4. Scale per currency

The scale must come from the currency, not be fixed at 2. ISO 4217 assigns,
for example, 2 minor digits to USD and EUR, 0 to JPY, and 3 to KWD, BHD and
OMR. The application stores free-text currency codes (`normalize_currency`
upper-cases them and maps "unknown" labels to `None`), so:

* rows with an unknown currency cannot be assigned a scale and must be
  reported, not guessed (owner decision D4);
* `npt_reports.cost_impact` has no currency column at all (owner decision D5);
* the supported currency list and its scales must be fixed by the owner (D2).

## 5. Rounding

Converting a REAL to minor units can change the amount when the stored value
has more decimals than the scale (for example a typed or imported `12.345` at
scale 2). Candidate rules, all available explicitly via `to_minor_units`:

* `ROUND_HALF_EVEN` (banker's rounding): unbiased over many rows.
* `ROUND_HALF_UP`: the common commercial convention.

They differ only on exact ties, e.g. `2.665`: half-up gives `267`, half-even
gives `266`; `-2.665` gives `-267` and `-266`. The conversion is applied to the
shortest decimal text of the float (`to_decimal`), so `2.675` is treated as the
`2.675` the user saw, not as its binary approximation. Every inexact row must
be listed in the dry-run report and approved; none may be rounded silently.

## 6. History, revisions and audit

* Report revision snapshots and audit records are immutable evidence and keep
  their original JSON numbers. They must not be rewritten.
* Readers of old snapshots must keep accepting JSON floats; new snapshots
  would serialise the new representation explicitly (for example
  `{"amount_minor": 1250, "scale": 2, "currency": "USD"}`) so old and new
  shapes are distinguishable.
* The migration itself must write one audit record per migrated table (actor,
  time, row counts, inexact-row count, rounding rule, source checksum).

## 7. Transition plan (if approved)

1. **Freeze inputs.** Owner decisions D1 to D6 are recorded.
2. **Backup.** Take a verified backup (integrity check and foreign-key check
   pass) and keep it until acceptance. Never run against the only copy.
3. **Dry run on a copy:** `python tools/money/money_audit.py --db <copy> --scale 2 --output audit.json`.
   The audit is read-only (`mode=ro`) and prints counts and currency codes
   only, never amounts or names. Review the null, invalid, non-finite,
   negative, inexact-at-scale, out-of-range and currency-unknown counts, and
   the stored-versus-canonical variance mismatches.
4. **Additive schema step** (next schema version): add `*_minor INTEGER` and a
   `money_scale INTEGER` beside the REAL columns; keep the REAL columns. This is
   additive and idempotent, like the v6 index step.
5. **Backfill** in one transaction per table with `to_minor_units` and the
   approved rule. Rows with unknown currency or non-finite or invalid values
   stay NULL in the new column and are listed.
6. **Dual read period.** Readers prefer `*_minor` when present and compare
   against the REAL value; writers write both.
7. **Validation** (section 8) must pass. Only then may the REAL columns be
   retired, in a later and separately approved release (destructive step,
   owner-gated).

## 8. Validation queries (read-only)

```sql
-- Row and null counts per column (compare before and after; must be equal).
SELECT COUNT(*), COUNT(planned_cost), COUNT(actual_cost), COUNT(variance) FROM cost_records;
SELECT COUNT(*), COUNT(budget) FROM projects;
SELECT COUNT(*), COUNT(cost_impact) FROM npt_reports;

-- Values stored with an unexpected storage class.
SELECT typeof(planned_cost), COUNT(*) FROM cost_records GROUP BY 1;

-- Totals per currency (before: REAL; after: minor units / 10^scale).
SELECT UPPER(TRIM(currency)), COUNT(*), SUM(planned_cost), SUM(actual_cost)
  FROM cost_records GROUP BY 1;

-- Backfill completeness: a known amount must have minor units.
SELECT COUNT(*) FROM cost_records WHERE planned_cost IS NOT NULL AND planned_cost_minor IS NULL;

-- Derived variance consistency after the backfill.
SELECT COUNT(*) FROM cost_records
 WHERE planned_cost_minor IS NOT NULL AND actual_cost_minor IS NOT NULL
   AND variance_minor IS NOT (planned_cost_minor - actual_cost_minor);

PRAGMA integrity_check;
PRAGMA foreign_key_check;
```

Per-currency totals must match within the documented rounding of inexact rows
only. The money audit tool reports the same facts without exposing amounts.

## 9. Rollback

* Steps 4 to 6 are additive: rollback means readers ignore `*_minor`; the REAL
  columns are untouched and remain authoritative until step 7.
* If the backfill transaction fails it rolls back as a whole; the schema
  version is not advanced (the same pattern as the tested v6 upgrade).
* Full rollback: restore the verified pre-migration backup (step 2).
* Step 7 (dropping REAL columns) is not reversible without the backup and
  must not be combined with steps 4 to 6.

## 10. Owner decisions (open)

| ID | Decision |
|---|---|
| D1 | Whether to migrate storage at all (option A or B) or keep option C |
| D2 | Supported currencies and their scales |
| D3 | Display rounding rule (current: float formatting of the binary value) |
| D4 | Treatment of amounts whose currency is unknown |
| D5 | Currency for `npt_reports.cost_impact` (not stored today) |
| D6 | Rounding rule for inexact stored values, and approval of the listed rows |
| D7 | When the legacy REAL columns may be dropped (destructive) |

## 11. Evidence

* `tests/test_money.py`: conversion, binary-float cases, signs, zero,
  extreme magnitudes, NaN and infinity rejection, halfway cases under both
  rules, range limits, the cost-summary regression, unchanged contract,
  display and JSON serialisation.
* `tests/test_money_audit.py`: the audit leaves the database file
  byte-identical, reports the planted facts, does not print amounts, vendors,
  well names or the path, refuses a missing file without creating it, and
  handles absent tables.
