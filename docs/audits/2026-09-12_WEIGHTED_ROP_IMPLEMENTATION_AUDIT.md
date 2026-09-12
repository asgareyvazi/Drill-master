# Canonical Footage & Weighted ROP Engine — Implementation Audit

**Date:** 2026-09-12
**Branch:** `arena/01a085e0-drill-master`
**Baseline HEAD before this work:** `515141c`
**Scope:** Smallest production-grade footage / weighted-ROP capability supported
by the verified data semantics (see companion audit
`2026-09-12_ENGINEERING_DATA_SEMANTICS_FORENSIC_AUDIT.md`). Repository is the
source of truth; every claim below was re-verified against code and tests.

---

## 1. Objective

Add a canonical, deterministic footage-weighted Rate-of-Penetration (ROP)
metric that is correct by construction — footage and hours summed from the SAME
valid paired observations — without creating a parallel KPI framework,
persisting derived rows, or overwriting the existing daily-average `avg_rop`.

## 2. Where it lives (host selection)

The metric was added to the **existing** canonical engine
`core.engineering.engines.bit_performance.BitPerformanceEngine`. That engine
already owns bit-run footage/hours/ROP (`from_run`, `from_daily_params`,
`rollup`) and returns the shared `EngineeringResult` contract. No new engine,
no `kpi_service.py`, no new KPI framework was introduced.

New members:

* `BitPerformanceEngine.VALID_PAIR_RULE` — human-readable statement of the gate.
* `BitPerformanceEngine.paired_observation(row)` — the single validity gate.
* `BitPerformanceEngine.weighted_rop(runs)` — the aggregate metric.

Well-scope exposure was added to the canonical consumer
`core.operations_intelligence.OperationsIntelligenceService.analyze_well`,
which already queries `DrillingParameters` by `well_id`.

## 3. Semantic contract — valid paired observation

A row forms a valid paired observation **iff ALL** of:

```
depth_in      is not None
depth_out     is not None
hours_on_bottom is not None
depth_out >= depth_in
hours_on_bottom > 0
```

When valid: `footage = depth_out - depth_in`, `hours = hours_on_bottom`.
When invalid: the row contributes **NEITHER footage NOR hours** — never a
partial contribution.

`paired_observation` accepts either a mapping (import/dict record) or an ORM row
(attribute access), reusing `optional_number` so malformed non-numeric tokens
are treated as invalid (excluded), never coerced to 0.

## 4. Weighted ROP definition

```
weighted_rop = Σ(valid-pair footage) / Σ(valid-pair hours)
```

* No valid pairs → value `None` (unknown), never `0`.
* Total valid hours ≤ 0 → value `None`.
* Result carries `values`: `weighted_rop`, `total_footage`, `total_hours`,
  `valid_pairs`, `excluded_rows`, `observations_considered`, plus `warnings`
  when rows were excluded or no pair existed. Units fixed at `m/hr`.

## 5. Wrong vs Correct aggregation (the core defect this prevents)

**WRONG — naive `SUM(footage)/SUM(hours)` across independently nullable
columns:**

```
Row 1: depth_in=1000, depth_out=1100, hours=5   → footage 100
Row 2: depth_in=NULL, depth_out=1200, hours=6   → footage dropped, hours kept
naive = (100) / (5 + 6) = 100 / 11 = 9.09 m/hr   ← WRONG
```

Row 2's 6 hours were counted although its footage was undefined — footage and
hours were mispaired.

**CORRECT — paired-filter BEFORE aggregation:**

```
Row 2 is not a valid pair → excluded WHOLE (0 footage AND 0 hours).
weighted = 100 / 5 = 20.0 m/hr                    ← CORRECT
```

This exact repro is locked in
`tests/test_weighted_rop.py::test_mandatory_pairing_repro`.

## 6. Pre-existing latent defect found & fixed

`BitPerformanceEngine.rollup` (previously **unused** in production — no callers,
no tests) summed footage and hours independently:

```python
footage += r.values.get("footage") or 0
hours   += r.values.get("hours_on_bottom") or 0
```

This is the same mispairing defect: a row with footage but null/zero hours would
add footage only; a row with hours but null footage would add hours only.
`rollup` was rewritten to aggregate through `paired_observation`, so it now
excludes incomplete rows whole. Its formula string was corrected accordingly.
Regression: `test_rollup_no_longer_mispairs`.

## 7. Explicit-zero footage handling

`depth_in == depth_out` with `hours > 0` is a **real recorded zero** (0 m
drilled while on bottom), so it forms a valid pair (footage 0, hours counted).
It is not silently dropped. Locked by
`test_explicit_zero_footage_is_a_real_pair`. The semantics audit confirmed the
data model does not treat in==out rows as sentinel-null.

## 8. Scope implemented

| Scope | Status | Notes |
|-------|--------|-------|
| DDR-level | IMPLEMENTED | `paired_observation` operates on one `DrillingParameters` row (one upserted row per DDR). |
| Well-level | IMPLEMENTED | `analyze_well` sums valid footage / valid hours across all DDR rows for a `well_id`. |
| Wellbore / Section | **NOT IMPLEMENTED (deliberate)** | FK exists but may be NULL on legacy rows (PARTIAL data sufficiency). Kept as an explicit gap rather than emitting an unreliable number. |

## 9. Well identity & isolation

Well scope filters `DrillingParameters` by canonical `well_id` (not rig / well
name / filename). A foreign well's absurd ROP must never leak into another
well's metric. Locked by `test_well_isolation_excludes_foreign_well`
(Well B at ~1,000,000 m/hr does not affect Well A's 20.0 m/hr).

## 10. Multiplicity integrity

The metric is computed only from `DrillingParameters` rows; it performs **no
join** to BHA / Bit / NPT / Cost / Mud. A 1:N child multiplicity therefore
cannot multiply footage or hours. `DrillingParameters` is one upserted row per
DDR (verified in the semantics audit), so a duplicate DDR import upserts rather
than double-inserting; no double counting. No N+1, no speculative indexes, no
unrelated child loads were added.

## 11. Existing `avg_rop` preserved

The daily-average `average_rop` KPI (mean of stored per-day `avg_rop`) is
**unchanged**. `weighted_rop` is an additive, distinctly named KPI. They can
legitimately differ and both are reported. Locked by
`test_weighted_rop_distinct_from_average_rop`. `weighted_rop` is a mean of
ratios' opposite: a mean of per-row rates for `[100 m/1 h, 100 m/100 h]` is
50.5 m/hr, while the footage-weighted value is 200/101 ≈ 1.98 m/hr
(`test_weighted_rop_differs_from_mean_of_rates`).

## 12. Units

Fixed: depths metres, hours hours → ROP `m/hr`. No unit conversion or
auto-detection was added (consistent with the trusted-metric convention for
depth/hours documented in the semantics audit).

## 13. No fabrication / no persistence

* Unknown → `None`, never `0`.
* No derived KPI rows are persisted; `weighted_rop` is computed on read.
* Warnings/metadata are surfaced only through the existing `EngineeringResult`
  and the existing `analyze_well` KPI dict — no new persistence surface.

## 14. UI exposure

Additive KPI keys (`weighted_rop`, `weighted_rop_footage`,
`weighted_rop_hours`, `weighted_rop_valid_pairs`) were added to the
`analyze_well` result. No report layout or widget was altered. **ENGINE
IMPLEMENTED + WELL-SCOPE KPI EXPOSED; dedicated UI widget/label = DEFERRED**
(would require design work beyond a trivial safe extension).

## 15. Files changed

Production:
* `core/engineering/engines/bit_performance.py` — added `VALID_PAIR_RULE`,
  `paired_observation`, `weighted_rop`; fixed `rollup` pairing defect.
* `core/operations_intelligence.py` — additive Well-scope `weighted_rop` KPIs.

Tests:
* `tests/test_weighted_rop.py` — 23 new tests (engine matrix + Well-scope
  integration).

Docs:
* `docs/audits/2026-09-12_WEIGHTED_ROP_IMPLEMENTATION_AUDIT.md` — this file.

## 16. Test matrix coverage (§22)

one valid pair · two valid pairs (sum-before-divide) · missing footage ·
missing hours · both missing · zero hours · negative footage · explicit zero
footage · no valid → None · empty → None · malformed token · ORM-attribute rows
· weighted ≠ mean of rates · mandatory pairing repro (20.0 not 9.09) · rollup
no-longer-mispairs · Well-scope sum · Well isolation (foreign well excluded) ·
Well no-valid → None · weighted distinct from average_rop.

## 17. Verification

* Targeted: `tests/test_weighted_rop.py` + `tests/test_engineering_data_semantics.py`
  — all pass.
* Full suite, ruff E722/F821, ruff debt total, and compileall — see the final
  certification block in the session response.

## 18. Certification summary

* WEIGHTED ROP ENGINE — PASS
* KPI SEMANTIC INTEGRITY (null/zero/pairing) — PASS
* NO-FABRICATION CONTRACT — PASS
* MULTIPLICITY INTEGRITY — PASS
* WELL IDENTITY INTEGRITY — PASS
* Wellbore/Section — intentionally NOT IMPLEMENTED (explicit PARTIAL gap)
