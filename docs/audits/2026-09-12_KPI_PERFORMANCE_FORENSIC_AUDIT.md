# DrillMaster — KPI / Performance Architecture Forensic Audit & Canonical Intelligence Certification

- **Date:** 2026-09-12
- **Repository:** `asgareyvazi/Drill-master`
- **Branch:** `arena/01a085e0-drill-master`
- **Baseline commit:** `3b389ce` (Cost import alias fix — certified foundation)
- **Audit commit:** this change set (KPI-01 fix + regression tests + this report)
- **Sources of truth:** repository code, executable behaviour, physical SQLite
  schema, and the full test suite. Prior Arena reports and doc/commit claims
  were **not** trusted; every finding is reproduced from live behaviour.

---

## 1. Repository Identity (§2)

Confirmed at audit start (after session-reset recovery via `git fetch` +
`git reset --hard` to the remote, then rebuild of `.venv` and the headless-Qt
stub libraries):

- `git branch --show-current` → `arena/01a085e0-drill-master`
- `git rev-parse HEAD` → `3b389ce`
- `git log` shows the full certified chain present:
  `3b389ce` Cost import alias fix · `23821bc` BHA/Bit ownership ·
  `560c60d`/`c0e91b8`/`8a3d750` Wellbore v3.

## 2. Baseline (§3)

Established **before** any modification:

| Gate | Result |
|---|---|
| pytest | **902 passed, 4 skipped**, 14 warnings |
| failed / errored / xfailed | 0 / 0 / 0 |
| Ruff E722 | 0 |
| Ruff F821 | 0 |
| Ruff debt (core+dialogs+tabs+tests) | **5489** (= ceiling `.github/ruff-debt-ceiling.txt`) |
| `compileall` core/dialogs/tabs | clean (exit 0) |

Environment note: the sandbox reset wiped `.venv` and `/home/user/qt-libs`;
both were rebuilt from `requirements.txt` + `tools/qt_headless_env.sh`. Ruff
resolved to 0.16.7 (baseline was 0.16.6); debt is identical at 5489, so the
version drift is immaterial to the gate.

## 3. Existing KPI Inventory (§4)

The repository has a **real, centralised calculation layer** — it is not merely
UI cards. The KPI/performance surface:

| Component | Role |
|---|---|
| `core/operations_intelligence.py` — `OperationsIntelligenceService.analyze_well` | **Primary canonical KPI engine.** Well-scoped, evidence-backed KPIs + insights. |
| `core/actual_vs_plan.py` — `ActualVsPlanEngine.compare_metrics` | Deterministic plan-vs-actual variance layer (no fabrication, missing-metric warnings). |
| `core/database.py` — `get_actual_vs_plan` | Well-scoped data collector that feeds `ActualVsPlanEngine`. |
| `core/database.py` — `get_cost_summary`, `get_cost_records` | Cost aggregates (audited in the Cost phase). |
| `core/report_engine.py` — `CostReportEngine`, `NPTReportEngine`, EOWR/DDR engines | Report-time KPI computation (ROP, NPT%, cost/m). |
| `core/data_quality.py` — `DataQualityService.dashboard_kpis` | Wraps OI kpis + data-quality score. |
| `core/api/rest_api.py` — `get_intelligence` | REST passthrough to `analyze_well`. |
| `tabs/w12_Analysis.py` — `calculate_kpis`, `get_npt_data` | **UI-local** KPI computation for the Analysis tab cards. |
| `tabs/w10_Planning_Widget.py` | UI-local NPT/productive computation for Planning. |
| `tabs/w16_Cost_Management.py` | Rate-based cost calculator (audited in Cost phase; does not persist). |
| `tabs/home_tab.py` | Project/well **status counts only** — no drilling KPIs. |

Persisted analysis tables also exist: `NPTReport`, `TimeDepthData`,
`ROPAnalysis` (all with `well_id`/`section_id`/`report_id` FKs), plus
`ActivityCode`. They have save/get APIs but are **not** used by the live KPI
engines (OI/report_engine derive from `TimeLog24H`/`DrillingParameters`/
`DailyReport`). They are optional structured stores, not the KPI source of truth.

## 4. Performance Inventory (§4)

`core/performance.py` is **not** a KPI module — it is import/IO performance
(chunked Excel reads, `ProgressTracker`, `batch_save`). `core/engineering/`
(bit_performance, torque_drag, anti_collision, `OperationsIntelligenceEngine`)
holds deterministic engineering calculators consumed by OI for trend insights.

## 5-7. KPI Source-of-Truth / Formula / Scope Map

| KPI | Source entity → fields | Filter | Scope | Formula | Unit | Consumers |
|---|---|---|---|---|---|---|
| Current depth | DailyReport.depth_2400 | well_id | Well | `max(depth_2400)` | m | OI, w12, reports |
| Rig days | DailyReport (count) | well_id | Well | `len(reports)` | days | OI, w12 |
| Daily progress | DailyReport.depth_2400 | well_id | Well | `depth[-1]-depth[-2]` | m | OI |
| Average ROP | DrillingParameters.avg_rop | well_id | Well | `mean(daily avg_rop)` (**unweighted**) | m/hr | OI, w12, report_engine, get_actual_vs_plan |
| Best ROP | DrillingParameters.avg_rop | well_id | Well | `max(avg_rop)` | m/hr | w12 |
| NPT hours | TimeLog24H.duration where is_npt | via report→well | Well | `sum(duration)` | hr | OI, w12, report_engine |
| NPT % | TimeLog24H.duration | via report→well | Well | `npt_hours / total_hours × 100` | % | OI, w12, report_engine |
| Productive hours | TimeLog24H.duration | via report→well | Well | `total_hours − npt_hours` | hr | OI |
| Total cost | CostRecord.actual_cost | well_id | Well | `sum(actual_cost)` | currency | OI, reports |
| Cost / meter | CostRecord + depth | well_id | Well | `total_cost / current_depth` | currency/m | OI |
| Plan variance | WellPlan/PlannedActivity vs actuals | well_id | Well | `ActualVsPlanEngine` | mixed | OI, w12 |
| WOB/RPM/Torque trend | DrillingParameters min/max | well_id | Well | `midpoint(min,max)` | eng units | OI, w12 |

## 8. Drilling KPI Semantics — ROP (§8, §22)

**All four ROP consumers use the same formula: unweighted `mean(daily
avg_rop)`** (OI `sum(rops)/len(rops)`, w12 `func.avg(avg_rop)`, report_engine
`sum(rops)/len(rops)`, get_actual_vs_plan `sum/len`). This is **consistent
across consumers (no drift)** but is a *daily-average-of-averages*, not the
engineering-preferred footage-weighted `SUM(drilled depth)/SUM(drilling
hours)`. The two agree when daily drilling hours are equal and diverge when they
are not. Because the model stores a pre-computed daily `avg_rop` (not per-day
drilled-footage + drilling-hours as separate canonical fields), a correct
footage-weighted well ROP is **not currently derivable** without a schema/field
change. Per §22 and §34 this is **documented as a limitation (Risk R-2), not
changed** — the current definition is internally consistent and the mandate
forbids reformulating a KPI absent a concrete defect.

ROP granularity: only **daily** and **well** ROP exist. No interval/section/
instantaneous ROP is computed by the live engines (the `ROPAnalysis` table could
hold interval ROP but is unused by KPIs).

## 9. Time Semantics (§9)

Time is sourced from `TimeLog24H` (24-hour DDR breakdown) with a boolean
`is_npt` and a `main_code`/`sub_code`. The engines compute exactly two disjoint
buckets: **NPT** (`is_npt = True`) and **productive** (`total − npt`). There is
**no double-counting of overlapping categories**: `total_hours = SUM(duration)`
over all logs, `npt_hours = SUM(duration where is_npt)`, so
`productive = total − npt` is exact and cannot exceed 24h/day (verified with a
20h + 4h synthetic day → 44 productive of 48 total across two DDRs). Finer time
categories (connection/trip/ream/slide/circulate) are **not** separately
modelled as KPI buckets — they live only as free-text `main_code`/`sub_code`,
so category-level time KPIs are limited to NPT-vs-productive.

## 10. NPT Semantics (§10)

Two independent NPT representations exist:

1. **`TimeLog24H.is_npt`** — the source used by *every live time KPI* (OI, w12,
   report_engine). NPT% = `npt_hours / total_hours`. Denominator = total
   recorded time (not a fabricated 24h/day). No overlap double-count.
2. **`NPTReport`** — a richer persisted NPT event entity (start/end,
   duration_hours, category, code, cost_impact, `well_id`/`section_id`/
   `report_id` FKs, dedup by `(report_id, start_time, end_time)`). Used only by
   `w16_Cost_Management` for cost display, **not** by the time-KPI engines.

The two are **not summed together anywhere** (verified: no consumer joins or
adds `TimeLog24H.is_npt` and `NPTReport`), so there is no cross-source NPT
double-count. The split is a mild duplicate-truth risk (Risk R-3) but not a
correctness defect today.

## 11. Well / Wellbore / Section Behaviour (§11-13)

- **Well scope:** All live KPIs are **well-scoped** (`well_id` filter, or join
  `TimeLog24H → DailyReport.well_id`). A Well's KPIs legitimately combine all
  its wellbores (original + sidetracks) — the correct meaning of "Well ROP".
  Verified with a Well containing an original bore (DDR1) + a sidetrack (DDR2):
  well KPIs aggregate both, as intended.
- **Wellbore isolation:** There is **no wellbore-scoped KPI path**. `DailyReport`
  and `Section` carry `wellbore_id` (v3), so per-wellbore KPIs are *possible*,
  but no engine currently exposes them. This is a **capability gap, not a
  contamination defect** — nothing mis-attributes one bore's metrics to another
  because there is no per-bore claim.
- **Section isolation:** Same — no section-scoped KPI in the live engines.
  `NPTReport`/`ROPAnalysis`/`TimeDepthData` carry `section_id` for future use.
  Where sections are referenced, canonical `section_id` FKs exist (§13); no KPI
  groups by free-text `section_name`.
- **No KPI aggregates by `rig`, `rig_name`, or free-text well/section name**
  (verified by grep across the KPI surface).

## 12. BHA / Bit Compatibility (§14)

The current BHA/Bit snapshot-per-DDR architecture (no Run entity) is respected.
**No live KPI joins BHA/Bit tables into a time/depth aggregation**, so the
one-to-many snapshot rows cannot multiply any KPI. Verified directly: a report
with 2 BHA + 2 Bit snapshots yields `total_hours = 48` whether or not a BHA join
is (mistakenly) added — but the actual code never adds such a join, computing
hours purely from `TimeLog24H`. Bit-footage / bit-run KPIs are **not** computed
(would require run identity the snapshots deliberately lack); documented as a
limitation, no Run entity fabricated (§34 honoured).

## 13. Cost Compatibility (§15-16)

Cost KPIs are strictly well-level, matching the Cost architecture:
`total_cost = SUM(actual_cost)` per well, `cost_per_meter = total_cost /
current_depth`. **No KPI assumes wellbore/section/operation cost ownership**
(verified by grep — no `CostRecord` join to section/wellbore/report in any KPI).
Cost is never fabricated: when no cost records exist, `total_cost` and
`cost_per_meter` are `None`, and the NPT/Cost report engines return `None` for
`total_cost`/`npt_cost`/`cost_per_meter` (asserted by
`test_report_cost_paths_do_not_create_default_rig_rates`). **Cost Risk R-1 (no
row-level transaction identity) does NOT block any currently implemented KPI**
— every cost KPI is a well-level SUM that is correct regardless of row identity,
and the production fingerprint guard prevents file-level double import. Per §16,
R-1 stays deferred.

## 14. Plan vs Actual (§17)

Planning data exists (`WellPlan`, `PlannedActivity`) and is compared to actuals
through `ActualVsPlanEngine`, which compares **only metrics explicitly present on
both sides**, fabricates nothing, and emits warnings for missing metrics. Plan
and actual are distinct fields/entities (planned_* on activities/plan vs actual
from reports/logs/cost), so there is no silent same-field comparison. This is
sound; no expansion attempted (§17 honoured).

## 15. NULL / Zero Semantics (§18) — DEFECT KPI-01 (fixed)

See Defects. Summary: the canonical OI engine fabricated `npt_percent = 0.0` and
`average_rop = 0.0` when the source data was genuinely unknown — inconsistent
with its own cost handling (which correctly returns `None`). Fixed to return
`None`. Explicit zero (a real 0h NPT day) remains zero because it is a recorded
`duration`, not a missing value. The `get_actual_vs_plan`/`ActualVsPlanEngine`
path already handled unknowns correctly (returns `None`/omits metrics).

## 16. Division by Zero (§19)

All KPI divisions are guarded: OI (`if total_hours`, `if rops`,
`if current_depth > 0`), report_engine (`if total > 0`, `if total_hours > 0`,
`if max_depth > 0`), `ActualVsPlanEngine`/`compare` (`if planned else …`). No
KPI path can raise `ZeroDivisionError` or emit `NaN`/`Infinity` (verified with
empty-well and no-logs synthetic cases → clean `None`/`0`, no exceptions). The
w12 UI uses `total_hours or 1` as a denominator guard — safe against crashes,
but see Risk R-4 (it's a UI-local NULL→1 blur that the canonical engine avoids).

## 17. Unit Consistency (§20)

Units are **metric throughout the live KPIs** (m, m/hr, hr, %, currency, m/day).
The Cost report engine converts m→ft for `cost_per_foot` explicitly
(`/ 3.28084`). There is no silent metric/imperial mixing in the KPI engines. A
general unit-conversion framework is absent; documented as a limitation, not
added (§20 honoured).

## 18. Double-Counting Audit (§21) — PASS

Forensic synthetic test (one Well, original bore + sidetrack, a DDR with 2 BHA +
2 Bit snapshots + NPT/productive logs, plus a second DDR):

- `total_hours` computed from `TimeLog24H → DailyReport` = 48 (correct), and
  **does not change** when BHA is joined in the query — but the live code never
  joins BHA/Bit/NPT/Cost into time/depth aggregations.
- `npt_hours` = 4, `npt_percent` = 8.33%, `productive_hours` = 44 — exact.
- `average_rop` = 20 (mean of 10, 30) — no snapshot multiplication.
- No KPI query fans out across a one-to-many child table.

**No double-counting via joins, BHA/Bit snapshots, NPT rows, or Cost rows.**

## 19. Weighted vs Unweighted Averages (§22)

Covered in §8. ROP is unweighted mean-of-daily-averages, consistently. Documented
as Risk R-2; not changed (no defect, and footage-weighting needs canonical
per-day drilled-footage + drilling-hours fields that don't exist).

## 20. Duplicate Formula Audit (§23)

The same KPIs are implemented in **three places** — OI (canonical), w12
(UI-local `calculate_kpis`), and report_engine — plus w10 (Planning). Forensic
comparison of the formulas:

- **ROP:** identical unweighted mean across all — **no semantic drift**.
- **NPT%:** identical `npt/total×100` across all — **no drift**.
- **Difference:** only in NULL handling — the **canonical OI now returns None**
  for unknowns (post-fix), while **w12/w10/report_engine UI paths coerce to 0 /
  use `total_hours or 1`**. This is a mild consistency gap (Risk R-4), not a
  contradiction of formula: given present data they agree. Centralising w12/w10
  onto OI would be the ideal end-state but is a UI refactor beyond a defect fix
  (§23/§34 — "only centralize where evidence supports it"; the UI cards format
  with `:.1f` and would need None-tolerant rendering). Documented, not forced.

## 21. Calculation-Layer Architecture (§24, §35)

The intended architecture is present and correct:

```
Canonical Data (DailyReport, TimeLog24H, DrillingParameters, CostRecord, WellPlan)
        ↓
OperationsIntelligenceService.analyze_well  +  ActualVsPlanEngine   (calculation/semantic layer)
        ↓
REST API · DataQualityService.dashboard_kpis · Analysis tab (insights)
```

The layer computes deterministically from canonical facts and does **not**
persist a second copy of truth (the `NPTReport`/`ROPAnalysis`/`TimeDepthData`
tables are optional structured stores, not the KPI derivation path). A parallel
`kpi_service.py` was **not** created (§24 honoured) — the existing OI layer is
architecturally appropriate and was extended in place.

## 22. Home Audit (§26)

`tabs/home_tab.py` shows company/project/well counts, status breakdown, recent
wells, and project-completion progress bars — **no drilling KPI cards**. It reads
`db.get_hierarchy()` (canonical). No fabricated KPI. Not redesigned (§26).

## 23. Analysis Audit (§27)

`tabs/w12_Analysis.py` is the real KPI tab. It uses the canonical
`OperationsIntelligenceService` for the **insights** line, but computes its
**card values** via its own `calculate_kpis`/`get_npt_data` (UI-local, same
formulas). Values come from canonical entities (`DailyReport`,
`DrillingParameters`, `TimeLog24H`) via `well_id` — not free-text. Preserved as
is (§27); the UI-local duplication is Risk R-4.

## 24. Planning Audit (§28)

`tabs/w10_Planning_Widget.py` computes its own NPT/productive aggregates
(UI-local, canonical sources). It does not consume the canonical KPI layer.
Documented (Risk R-4); not redesigned (§28 — no concrete integration defect).

## 25. Export / Report Audit (§29)

`core/report_engine.py` (DDR/EOWR/Cost/NPT) computes ROP/NPT%/cost independently
but with the **same formulas** and the **same no-fabrication cost discipline**
(returns `None`, asserted by tests). No contradictory definitions. Semantic
drift limited to NULL handling (Risk R-4).

## 26. Provenance Audit (§30)

OI insights are **evidence-backed**: each carries `source_reports` (report IDs),
`date_range`, `metrics`, `confidence`, and `reason` — reproducible and traceable
to source DDRs. `ActualVsPlanEngine` results carry `formula`, `method`, `unit`,
`assumptions`, `scope`, and `warnings`. KPI *card* values (raw numbers) do not
individually carry provenance, but they are deterministically reproducible from
canonical facts. No fake citations are invented for calculated values (§30).

## 27. KPI Data Quality (§31)

`DataQualityService` provides per-report quality scoring; OI computes a
data-quality score (missing depths, 24h coverage deviation). Ownership integrity
(cross-well, section/wellbore) is enforced at the persistence boundary by the
certified Wellbore v3 / BHA-Bit `before_flush` listeners, so KPI inputs cannot
contain cross-well contamination. No massive new validation framework added
(§31).

## 28. Synthetic Forensic Dataset Results (§32)

A deterministic dataset (Well A → original bore + sidetrack; DDR1 with 2 BHA +
2 Bit + 20h productive + 4h NPT; DDR2 on sidetrack with 24h productive; drilling
params; explicit zero/NULL cases) confirmed:

| Check | Result |
|---|---|
| Well KPI aggregates all wellbores | PASS (depth 250, rig_days 2) |
| Hours not multiplied by BHA/Bit snapshots | PASS (48h with or without BHA join) |
| NPT% correct, no overlap | PASS (4/48 = 8.33%) |
| Productive = total − NPT | PASS (44h) |
| avg_rop unweighted mean | PASS (20 = mean(10,30)) |
| Cost None when absent (no fabrication) | PASS |
| Unknown ROP/NPT → None (post-fix) | PASS |
| Known ROP/NPT computed | PASS (15 m/hr, 25%) |
| Empty well → `{"reports": 0}`, no crash | PASS |

---

## Defects

### KPI-01 — Canonical KPI engine fabricated 0.0 for unknown ROP / NPT% (MEDIUM) — FIXED

- **Severity:** MEDIUM (canonical KPI layer asserts a false engineering fact
  from missing data; consumed by REST API + data-quality dashboard + Analysis
  tab insights).
- **Observed:** `OperationsIntelligenceService.analyze_well` returned
  `average_rop = 0.0`, `npt_percent = 0.0`, and `productive_hours = 0` for a well
  with daily reports but **no** `DrillingParameters` ROP and **no** `TimeLog24H`
  records. Reproduced: a "NoLogs" well reported `npt_percent = 0.0`,
  `average_rop = 0.0` — i.e. "0% NPT, 0 m/hr ROP" for a well whose ROP and NPT
  are genuinely unknown.
- **Expected:** Unknown metrics report `None` ("unknown"), never `0.0` — the
  same no-fabrication contract the **same method** already applied to
  `cost_per_meter`/`total_cost`.
- **Root cause:** `... if rops else 0.0` and `... if total_hours else 0.0`
  chose a fabricated zero as the empty-data sentinel instead of `None`
  (`core/operations_intelligence.py`, KPI block).
- **Evidence:** live probe (above); pre-fix values `0.0/0.0/0`.
- **Fix (minimal):** Return `None` for `avg_rop`, `npt_percent`, and
  `productive_hours` when their source data is absent
  (`core/operations_intelligence.py`). Guarded the two internal consumers of
  `npt_percent` (`analyze_npt_trend` call and the combined ROP/torque/NPT
  pattern) against `None` so no insight is fabricated and analysis never
  crashes. Explicit recorded zeros remain zero (they are real `duration`
  values, not missing).
- **Regression tests:**
  `tests/test_operations_intelligence_regressions.py`:
  `test_unknown_rop_and_npt_are_none_not_fabricated_zero` (unknown → None, no
  crash, cost stays None) and `test_known_rop_and_npt_are_computed`
  (15 m/hr, 25% NPT, 18h productive still computed).
- **Verification:** new tests pass; targeted OI + engineering-completion suites
  pass; full suite **904 passed / 4 skipped**; debt 5489 (neutral); E722/F821 =
  0; compile clean.

---

## Remaining Risks (documented, not changed — §34 minimal-fix mandate)

| ID | Sev | Risk | Why not changed | Impact |
|---|---|---|---|---|
| R-1 | — | Cost has no row-level transaction identity | Does **not** block any current KPI (all cost KPIs are well-level SUMs); Cost-phase deferral stands | None on KPI today |
| R-2 | MED | Well ROP is unweighted mean-of-daily-averages, not footage-weighted `SUM(depth)/SUM(hours)` | Consistent across consumers; no per-day drilled-footage + drilling-hours canonical fields exist to weight by; reformulating absent a defect is out of scope | Divergence only when daily drilling hours differ |
| R-3 | LOW | Two NPT representations (`TimeLog24H.is_npt` vs `NPTReport`) | Never summed together; time KPIs use one source only | Duplicate-truth hazard if a future KPI mixes them |
| R-4 | LOW–MED | KPI formulas duplicated in OI / w12 / w10 / report_engine; UI paths coerce unknown→0 while canonical OI now returns None | Centralising is a UI refactor beyond a defect fix; formulas already agree given data | UI cards may still show 0.0 for unknowns; canonical/API layer is correct |
| R-5 | LOW | No wellbore/section-scoped KPI path (only well-level) | Capability gap, not contamination; v3 FKs make it possible later | Per-bore/per-section KPIs unavailable |
| R-6 | LOW | No general unit-conversion framework | Live KPIs are metric-consistent; no defect | Imperial reporting limited |

---

## §40. Certification Gates (A–R)

| Gate | Area | Result | Evidence |
|---|---|---|---|
| A | Repository identity | PASS | HEAD `3b389ce`, branch + certified chain verified (§1) |
| B | Baseline regression | PASS | 902→904 passed, 0 failed; debt 5489 (§2) |
| C | KPI inventory completeness | PASS | Full inventory incl. persisted analysis tables (§3-4) |
| D | Formula correctness | PASS (with R-2) | ROP/NPT/cost formulas verified; ROP unweighted noted (§8, §18-19) |
| E | Scope correctness | PASS | All live KPIs well-scoped, canonical IDs only (§7, §11) |
| F | Well identity | PASS | `well_id` FK, no free-text keying (§11) |
| G | Wellbore isolation | PASS (capability gap R-5) | Well aggregates bores by design; no cross-bore contamination (§11-12) |
| H | Section isolation | PASS (capability gap R-5) | `section_id` FKs; no free-text section grouping (§13) |
| I | Time semantics | PASS | NPT/productive disjoint; no overlap double-count (§9) |
| J | NPT semantics | PASS | Single source per KPI; dedup on NPTReport; no cross-source sum (§10) |
| K | BHA/Bit compatibility | PASS | No snapshot join-multiplication; run KPIs documented as limitation (§12) |
| L | Cost compatibility | PASS | Well-level only; no fabricated ownership; R-1 non-blocking (§13) |
| M | Double-counting protection | PASS | Synthetic 1→many test; no join fan-out (§18, §28) |
| N | NULL/zero/unit semantics | PASS (post-fix) | KPI-01 fixed; explicit zero preserved; metric-consistent units (§15-17) |
| O | Cross-consumer consistency | PASS (with R-4) | Same formulas everywhere; only NULL handling differs (§20, §23) |
| P | Provenance / reproducibility | PASS | Evidence on insights; deterministic recompute; no fake citations (§26, §30) |
| Q | Full regression | PASS | 904 passed / 4 skipped; E722/F821 0; debt 5489; compile clean |
| R | Production-readiness | PASS WITH REMAINING RISKS | Sound calculation architecture; R-2..R-6 documented |

---

## §41. Final Certification

**KPI / PERFORMANCE ARCHITECTURE = PASS WITH REMAINING RISKS.**

DrillMaster **can** currently calculate trustworthy drilling KPIs from
canonical, evidenced data:

- **without cross-Well/Wellbore contamination** — all KPIs are well-scoped on
  canonical `well_id`; a Well correctly aggregates its wellbores; nothing keys on
  rig or free-text names;
- **without double counting** — no KPI joins one-to-many BHA/Bit/NPT/Cost tables
  into time/depth aggregations (verified with synthetic fan-out data);
- **without NULL-to-zero fabrication** — the one violation (KPI-01, the
  canonical engine emitting 0.0 for unknown ROP/NPT%) is fixed to return `None`,
  matching the existing cost discipline;
- **without inconsistent formulas** — ROP and NPT% share one formula across OI,
  w12, w10, and report_engine (drift limited to NULL handling, Risk R-4);
- **without unsupported Cost assumptions** — cost KPIs are strictly well-level
  and never fabricate rig rates;
- with **evidence/provenance** on insights and deterministic reproducibility.

The remaining risks are **completeness and semantics limitations** (unweighted
ROP R-2, dual NPT stores R-3, UI-local formula duplication R-4, no per-bore/
section KPI R-5, no unit framework R-6) — none is a correctness failure of the
certified calculation path, and none was fixed because none is a demonstrated
defect within this audit's minimal-change mandate.

**REMOTE CI = BLOCKED / NOT OBSERVED.** No remote CI run was observed or verified
from this environment; `.github/workflows/` cannot be pushed without the GitHub
App's `workflows` permission. Local test success is not remote CI (§38, §41).

## §42. Final Repository Verification

- `git status` / `git diff` reviewed before finalising.
- Files changed: `core/operations_intelligence.py` (KPI-01 fix: None for unknown
  ROP/NPT%/productive + two internal None-guards),
  `tests/test_operations_intelligence_regressions.py` (+2 regression tests),
  and this report.
- No unrelated modules modified; no tests deleted/weakened/xfailed; debt ceiling
  unchanged.
- Full suite **904 passed / 4 skipped**; E722=0; F821=0; ruff debt 5489;
  `compileall` clean. Certified foundation (Wellbore v3, BHA/Bit, Cost)
  unchanged and green.
