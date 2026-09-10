# DrillMaster — KPI Matrix (2026-09-09)

Inventory of every KPI/performance metric found in the codebase, with definition,
source, scope, formula, unit, null handling and drill-down. This is the input for
the Phase 4 canonicalization decision (handoff §18/§36: one canonical layer, no
duplicate formulas in tabs).

## 1. Current KPI computation sites (as found)

### 1.1 `core/operations_intelligence.py` — `OperationsIntelligenceService.analyze_well(well_id)`

| KPI | Formula | Source data | Scope | Unit | Null handling |
| --- | --- | --- | --- | --- | --- |
| avg_rop | `round(sum(rops)/len(rops), 2)` (line 79) | `DrillingParameters.avg_rop` per report | well | m/h (as stored) | empty list → `0.0` |
| npt_percent | `round(npt_hours/total_hours*100, 2)` (line 80) | `TimeLog24H.is_npt`/duration | well | % | zero total hours → `0.0` |
| NPT trend insight | threshold compare at 20 % (line 163) | derived npt_percent | well | – | – |

Note: ROP denominator is *report count*, i.e. average of daily averages — not
footage-weighted. Documented as-is; flagged for the canonical KPI decision.

### 1.2 `tabs/w12_Analysis.py` — `calculate_kpis(session)` (line 1211) and card updates

| KPI | Formula | Source | Scope | Unit |
| --- | --- | --- | --- | --- |
| avg_rop | SQL `func.avg(DrillingParameters.avg_rop)` (1223) | DrillingParameters | selected well | m/h |
| best_rop | SQL `func.max(DrillingParameters.avg_rop)` (1225) | same | well | m/h |
| npt_pct | `total_npt/total_hours*100` (1244) | TimeLog24H | well | % |
| efficiency | `100 - npt_pct` (1246) | derived | well | % |
| avg/best ROP (plot overlay) | `np.mean(rops)`/`max(rops)` (1654–1655) | plot series | visible range | m/h |
| ROP normalization for heatmap | `rop/max_rop` (1674) | plot series | visible range | ratio |
| report text stats | `np.mean/np.std` (1922–1923), NPT days (2060) | analysis series | well | mixed |

**Duplicate of 1.1's avg_rop and npt_percent with independently written code paths
(SQL vs Python, same semantics).** These two must converge on one implementation.

### 1.3 `tabs/home_tab.py`

Project progress (planned vs actual days per project, `load_project_progress`),
recent wells list, system status. No ROP/NPT/cost KPIs on Home today — consistent
with handoff §19 ("do not create a separate KPI tab"; evolve Home).

### 1.4 Other metric-producing code

* `core/performance.py` — performance analysis helpers (ROP analysis, NPT catalog
  via `core/npt_catalog.py`).
* `core/data_quality.py` — completeness/quality scores (data-quality warnings for
  Home per §19).
* `tabs/w16_Cost_Management.py` — cost aggregation by category/status
  (Actual vs Planned vs Variance per CostRecord) — cost KPI source.
* `core/api/rest_api.py` — exposes some of the above over HTTP; must consume the
  same canonical layer, not new formulas.

## 2. Canonical KPI target contract (Phase 4 design, to be implemented then verified)

```
Canonical data (DailyReport, TimeLog24H, DrillingParameters, CostRecord…)
        ↓
core KPI service (single implementation, pure functions + well/section scope)
        ↓
Home (executive cards) · Analysis (uses service) · Planning (plan-vs-actual)
· Export/Reports (labelled figures) · REST API
```

Required per-KPI record (handoff §18): definition, source, scope, formula, unit,
null handling (NULL stays NULL / empty stays 0 only when semantically a count),
drill-down path.

## 3. Status

**BLOCKED (as a completed area)** — a canonical KPI service does not exist yet;
today there are two independent ROP/NPT formula sites (1.1, 1.2) with equal
semantics but duplicated code, plus cost metrics in w16. No tab currently
*contradicts* another (same semantics, different code), but the duplication is the
defect the handoff describes. Phase 4 will extract `core/kpi_service.py` (name
subject to §38 repository search first) and point both consumers at it.
