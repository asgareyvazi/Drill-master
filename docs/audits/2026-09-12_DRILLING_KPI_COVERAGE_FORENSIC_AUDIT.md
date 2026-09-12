# DrillMaster — Drilling Engineering KPI Coverage & Data-Sufficiency Forensic Audit

- **Date:** 2026-09-12
- **Repository:** `asgareyvazi/Drill-master`
- **Branch:** `arena/01a085e0-drill-master`
- **HEAD at audit start:** `9be4c42` (KPI consumer alignment — certified foundation)
- **Sources of truth:** repository code, the physical SQLAlchemy schema in
  `core/database.py`, the canonical engines under `core/engineering/`, and live
  behaviour exercised on a freshly built SQLite database. Prior Arena reports,
  commit messages, and this prompt were **not** trusted as evidence; every
  status below was derived from the actual repository.

This is a **coverage and data-sufficiency audit**. Its purpose is to state
exactly *what DrillMaster can truthfully compute today, what is partially
supported, and what the data model cannot support* — not to maximise the KPI
count.

---

## 1. Repository Identity (§0)

| Check | Value |
|---|---|
| `git branch --show-current` | `arena/01a085e0-drill-master` |
| `git rev-parse HEAD` | `9be4c42803fce0e1e00c82050df2afb38a1410b3` |
| Tree state | clean (only pre-existing untracked `.github/workflows/`) |
| Recent chain | `9be4c42` KPI consumers · `2eaacf4` KPI-01 · `3b389ce` Cost · `23821bc` BHA/Bit · Wellbore v3 |

HEAD equals the expected recent KPI commit; no re-derivation from an unexpected
state was required.

## 2. Baseline (§1) — captured before any change

| Gate | Result |
|---|---|
| pytest | **908 passed, 4 skipped** |
| failed / errored / xfailed | 0 / 0 / 0 |
| Ruff E722 (core+dialogs+tabs+tests) | 0 |
| Ruff F821 (core+dialogs+tabs+tests) | 0 |
| Ruff debt (core+dialogs+tabs+tests) | 5489 (= ceiling) |
| compileall core/tabs/ui/dialogs | clean (exit 0) |

## 3. Canonical KPI Architecture (§0, verified)

| Layer | Location | Role |
|---|---|---|
| Well-scoped intelligence | `core/operations_intelligence.py::OperationsIntelligenceService.analyze_well` | Deterministic well KPIs (depth, ROP, NPT%, productive hours, cost/m, mud/safety trends). No-fabrication: unknown → `None`. |
| Plan vs Actual | `core/actual_vs_plan.py::ActualVsPlanEngine` + `DatabaseManager.get_actual_vs_plan` | Compares only metrics present in both datasets; omits (never fabricates) missing ones. |
| Run/bit performance | `core/engineering/engines/bit_performance.py::BitPerformanceEngine` | Footage / hours / ROP / MSE from `DrillingParameters` (`depth_in/out`, `hours_on_bottom`). |
| Trajectory | `core/engineering/engines/trajectory.py` + `TrajectoryCalculation` | MD/TVD/inc/azi/DLS/build/turn via minimum curvature. |
| Casing / Cement | `core/engineering/engines/{casing,cement}.py` | Burst/collapse/triaxial/tensile; cement displacement/TOC/excess volumetrics. |
| UI/report consumers | `tabs/w12_Analysis.py`, `tabs/w10_Planning_Widget.py`, `core/report_engine.py` | Re-derive dashboard/report KPIs; now aligned to the same no-fabrication contract (`9be4c42`). |

The canonical intelligence layer remains the centre; **no KPI framework, KPI
table, KPI cache, registry, DSL, or `kpi_service.py` was created** (§18).

## 4. Data-Source Inventory (§3) — real entities & fields only

Confirmed from `core/database.py` (schema v3). KPI-relevant sources and their
actual columns:

- **DailyReport** — `depth_0000/0600/2400`, `rop_meter`, `wob/rpm/torque/pressure`,
  `mud_weight_in/out`, `rig_day`, `report_date`, `well_id/wellbore_id/section_id`.
- **TimeLog24H / TimeLogMorning** — `time_from`, `time_to`, `duration`,
  `main_phase`, `main_code`, `sub_code`, `is_npt`, `npt_category`, `contractor`.
- **DrillingParameters** — `avg_rop`, `depth_in`, `depth_out`, `bit_drilled`,
  `cum_drilled`, `hours_on_bottom`, `cum_hours`, `wob_min/max`, `rpm_min/max`,
  `torque_min/max`, `pump_*`, `hsi`, `annular_velocity`, `tfa`.
- **MudReport** — `mw`, `pv`, `yp`, `funnel_vis`, `gel_10s/10m`, `fl`,
  `cake_thickness`, `ph`, `temperature`, `solid/oil/water_percent`, `chloride`,
  `calcium`, `kcl`, `mbt`, `total_hardness`, `loss_downhole/surface`,
  `total_circulated`, `volume_hole`. **No ECD, no PV/YP-derived hydraulics
  output, no dilution/consumption column.**
- **CementReport** — `cement_volume`, `displacement_volume`, `slurry_density/yield`,
  `top_of_cement`, `bottom_of_cement`, `compressive_strength`, `fluid_loss`,
  `thickening_time`. **No cement-returns / actual-excess measurement column.**
- **CasingReport** — `casing_json`, `tally_json`, `burst/collapse_pressure`,
  `tensile_strength`, `makeup_torque`, `drift_diameter`, `running_speed`.
- **SurveyPoint** — `md`, `inc` (nullable), `azi` (nullable), `tvd`, `north`,
  `east`, `vs`, `dls`. **TrajectoryCalculation** — `total_md/tvd/hd`, targets.
- **BHAReport / BitReport / DownholeEquipment** — report-scoped JSON snapshots
  (`bha_data_json`, `bit_records_json`, `equipment_data_json`). **No run entity,
  no run start/end, no cumulative bit-run identity across reports.**
- **FormationReport** — `formations_json` (report-scoped snapshot).
- **CostRecord** — Well-scoped: `category`, `planned_cost`, `actual_cost`,
  `variance`, `currency`, `vendor`, `cost_type`. **No wellbore_id / section_id.**
- **WellPlan / PlannedActivity** — `planned_total_days`, `planned_final_depth`,
  `planned_duration_hours`, `planned_depth_from/to`, `progress_percent`.

## 5. Time Semantics (§5)

- Time is stored as discrete `TimeLog24H` (+ `TimeLogMorning`) rows with
  `time_from`, `time_to`, an explicit `duration`, an activity `main_code`/
  `sub_code`/`main_phase`, and a boolean `is_npt` (+ `npt_category`).
- **Duration is stored explicitly** — it is not inferred from timestamps, so a
  row with missing `duration` stays unknown (no fabrication).
- **Productive vs NPT** is a clean binary from `is_npt`. Productive = Σduration
  where `not is_npt`; NPT = Σduration where `is_npt`. Verified: with 24 h logged
  and 6 h NPT, `productive_hours=18`, `npt_percent=25.0`.
- **Finer categories (drilling / rotating / sliding / connection / trip /
  circulating)** are represented only *implicitly* through free-form activity
  codes (`main_code`/`sub_code`) plus the optional `ActivityCode` taxonomy
  (`is_productive`, `is_npt`). There is **no fixed schema field** guaranteeing a
  row is "rotating" vs "sliding" vs "connection". A dedicated `TripSheetEntry`
  table exists for trips (with `depth`, `cum_trip`, `duration`).
- **Unknown time never becomes zero** — confirmed both in the canonical layer
  and (post-`9be4c42`) in every consumer.

## 6. ROP Forensic Audit (§6) — no defect, precision limitation documented

- **Current well KPI ROP** (`analyze_well`, `w12.calculate_kpis`) = **unweighted
  mean of daily `DrillingParameters.avg_rop`**. This is an intentional,
  internally-consistent daily-average definition.
- **Footage AND drilling hours DO exist canonically**: `DrillingParameters`
  stores `depth_in`, `depth_out`, `bit_drilled`, and `hours_on_bottom`, and the
  import path (`core/ddr_import_service.py`, `core/import_quality.py`) populates
  them. A canonical footage/hours ROP already exists at the *run* level:
  `BitPerformanceEngine.from_run` computes `ROP = (depth_out − depth_in) /
  hours_on_bottom` and returns `None` when hours are missing.
- **Conclusion:** a footage-weighted well/section ROP
  (`Σfootage / Σdrilling_hours`) is **IMPLEMENTABLE** (data + engine exist) but is
  a *different* KPI, not a correction of the existing one. The unweighted daily
  average is not a defect; it is a documented modelling choice. **No footage was
  fabricated; no drilling hours were inferred from elapsed time.** Left
  unchanged per the defect-only constraint (§19, §20).

## 7. Drilling Performance KPI Coverage (§7)

| KPI | Status | Scope | Basis |
|---|---|---|---|
| Total elapsed time | CERTIFIED | Well/Report | Σ`TimeLog24H.duration` |
| Productive hours | CERTIFIED | Well | Σduration where `not is_npt` |
| NPT hours / NPT % | CERTIFIED | Well (Section via w10) | Σduration where `is_npt` / total |
| Drilling hours | PARTIALLY SUPPORTED | Run | `DrillingParameters.hours_on_bottom` (per-run, not a clean daily field) |
| Circulating / rotating / sliding / connection / trip hours | PARTIALLY SUPPORTED | Report | only via activity-code text / `ActivityCode` taxonomy / `TripSheetEntry`; no guaranteed schema classifier |
| Current / previous depth | CERTIFIED | Well | `DailyReport.depth_2400` |
| Footage drilled / daily footage | IMPLEMENTABLE | Well/Section | Δ`depth_2400` or `bit_drilled`/(`depth_out`−`depth_in`) |
| Section / well progress | IMPLEMENTABLE | Section/Well | depth deltas by `section_id` |
| Depth vs plan / days vs plan | CERTIFIED | Well | `ActualVsPlanEngine` + `WellPlan` |
| ROP (daily avg) | CERTIFIED | Well | unweighted mean `avg_rop` |
| ROP (footage-weighted) | IMPLEMENTABLE | Run/Section/Well | `BitPerformanceEngine` footage/hours |
| Drilling / productive utilization | IMPLEMENTABLE | Well | productive_hours / elapsed |
| MSE | CERTIFIED (engine) | Run | `MSEEngine` (needs WOB/RPM/torque/ROP/size) |
| Connection / trip efficiency | PARTIALLY SUPPORTED | Report | needs reliable connection/trip classification |

## 8. BHA / Bit Performance (§8)

`BHAReport`, `BitReport`, `DownholeEquipment` are **report-scoped JSON
snapshots** with no longitudinal run identity (no run start/end, no cross-report
run continuity). Respecting the certified architecture (no BHA-Run / Bit-Run
entity introduced):

| KPI | Status | Reason |
|---|---|---|
| Per-run bit footage / hours / ROP / MSE | CERTIFIED (engine) | `BitPerformanceEngine.from_run`/`from_daily_params` on a single record |
| Bit run duration across reports | UNSUPPORTED | no run-continuity identity between snapshots |
| BHA run duration / BHA performance | UNSUPPORTED | snapshots only; no run entity |
| Dull-grade analysis | PARTIALLY SUPPORTED | depends on dull fields being present in `bit_records_json`; not guaranteed |

Run-continuity KPIs are **not** promoted to defects — the snapshot model is a
deliberate certified decision. Documented as capability gaps.

## 9. Mud / Drilling Fluid KPIs (§9)

| KPI | Status | Reason |
|---|---|---|
| MW / PV / YP / funnel-vis / gels / FL / pH / chloride / MBT / solids / temperature trend | CERTIFIED / IMPLEMENTABLE | direct `MudReport` fields (trends already read by `analyze_well` for MW/PV) |
| Mud losses (downhole/surface) | IMPLEMENTABLE | `loss_downhole`, `loss_surface`, `total_circulated` |
| ECD | UNSUPPORTED | no ECD field; only a text mention in a procedure step. Estimating ECD would fabricate an engineering fact |
| Mud dilution / consumption rate | UNSUPPORTED | no consumption/dilution/built-volume column |

## 10. Cement / Casing Performance (§10)

| KPI | Status | Reason |
|---|---|---|
| Cement slurry/displacement volume, TOC, excess (calculated) | CERTIFIED (engine) | `CementEngine.displacement`/`toc_from_volume` |
| Recorded TOC / cement volume / compressive strength / fluid loss | IMPLEMENTABLE | `CementReport` fields |
| Cement returns / actual excess | UNSUPPORTED | no returns/actual-excess measurement column |
| Casing burst/collapse/triaxial/tensile ratings | CERTIFIED (engine) | `CasingEngine` |
| Casing install depth / running speed | IMPLEMENTABLE | `CasingReport.running_speed`, tally/section depth |
| Cement bond / quality | UNSUPPORTED | no bond-log/quality evidence field |

## 11. Directional / Survey Performance (§11)

| KPI | Status | Reason |
|---|---|---|
| MD / TVD / inc / azi | CERTIFIED | `SurveyPoint` (inc/azi nullable; engine refuses incomplete stations) |
| DLS / build rate / turn rate | CERTIFIED (engine) | `TrajectoryCalculator` (minimum curvature) |
| Trajectory vs plan | IMPLEMENTABLE | `TrajectoryCalculation` targets vs actual |
| Kickoff depth / sidetrack trajectory comparison | PARTIALLY SUPPORTED | wellbore identity exists (v3) but no dedicated KOP field; derivable from survey + wellbore lineage |

Incomplete survey stations remain `None` and are surfaced for review — no
interpolation of engineering facts.

## 12. Formation / Geology Performance (§12)

`FormationReport` is a report-scoped `formations_json` snapshot.

| KPI | Status | Reason |
|---|---|---|
| Formation tops / intervals / lithology | PARTIALLY SUPPORTED | present only if authored in `formations_json`; no normalized columns |
| Formation drilling time / formation ROP / formation NPT | UNSUPPORTED | no join key binding a time log or ROP interval to a formation top |

No geological interpretation is invented.

## 13. Cost Performance (§13) — Well-scoped, unchanged

| KPI | Status | Reason |
|---|---|---|
| Total well cost | CERTIFIED | Σ`CostRecord.actual_cost` |
| Cost / day | IMPLEMENTABLE | total / rig_days |
| Cost / meter (ft) | CERTIFIED | total / current_depth; `None` when depth 0/unknown |
| Planned vs actual cost | CERTIFIED | `planned_cost` vs `actual_cost` via `ActualVsPlanEngine` |
| Category / vendor cost | IMPLEMENTABLE | group by `category` / `vendor` |
| Cost trend | IMPLEMENTABLE | by `cost_date` |
| Cost / Wellbore, Cost / Section | UNSUPPORTED | `CostRecord` has no `wellbore_id`/`section_id` (certified Well-scope) |

Confirmed behaviour: missing cost → `None`; actual zero → `0`; missing depth →
cost/meter `None`. No rig-rate assumption; no currency conversion (no supported
mechanism).

## 14. Wellbore / Section KPI Capability (§14)

| Scope | Time | NPT | ROP | Depth | Cost | BHA/Bit | Mud | Casing/Cement |
|---|---|---|---|---|---|---|---|---|
| **Well** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (snapshot) | ✅ | ✅ |
| **Wellbore** | gap (data keyed via `DailyReport.wellbore_id`, no roll-up API) | gap | gap | gap | ✗ (no FK) | gap | gap | gap |
| **Section** | partial (w10 NPT accepts `section_id`) | partial | gap | gap | ✗ (no FK) | gap | gap | ✅ (cement/casing carry `section_id`) |

The schema **can** support wellbore/section time/NPT/ROP/depth roll-ups (the
foreign keys exist on `DailyReport`, `Section`, `Wellbore`), but no
canonical roll-up API exposes them today. This is a **capability gap, not a
defect** — no wrong wellbore/section number is displayed. Cost/wellbore and
cost/section are genuinely **unsupported** (no FK), consistent with the certified
Well-scoped Cost model.

## 15. Well Identity / Sidetrack Test (§15) — PASS

Synthetic dataset: one Well with an original wellbore + a sidetrack wellbore
(two sections each), plus a second unrelated Well in the same project.

Verified via `test_canonical_well_kpis_span_wellbores_without_cross_well_contamination`:

- Well-level aggregates **both** wellbores: `reports=2`, `current_depth=1500`,
  `npt_hours=12` (6+6), `npt_percent=50.0`, `average_rop=15.0` (mean 20,10).
- The other Well's records (`avg_rop=999`, 24 h NPT) are **excluded** — identity
  is by `well_id`, never by rig or free-text name.
- Wellbore ownership invariants (v3 `before_flush`) prevent cross-well sidetrack
  lineage.

## 16. One-to-Many Multiplicity Test (§16 / §21) — PASS

Synthetic dataset: `1 DailyReport × 2 BHA × 2 Bit × 3 NPT logs × 2 Cost`.

Verified via `test_canonical_kpis_do_not_multiply_across_one_to_many_children`:

- `reports=1`, `npt_hours=6.0`, `npt_percent=25.0`, `productive_hours=18.0`,
  `average_rop=25.0` (single param, **not ×4**), `total_cost=150000` (**not ×4**).
- Root reason: `analyze_well` reads each one-to-many child in its **own** query
  (`TimeLog24H` via a single join to `DailyReport`; `DrillingParameters`,
  `CostRecord` independently). No Cartesian join fans time/ROP/cost out.

## 17. KPI Data-Quality Rules (§17)

Every CERTIFIED KPI above satisfies: source completeness checked; `None` for
unknown; genuine `0` preserved; denominator guarded (`None` when zero/unknown,
never `1`); explicit unit; explicit scope (Well); aggregation by id.

## 18. Defects (§20)

**None found.** The canonical layer isolates wells/wellbores correctly, never
multiplies one-to-many children, and never fabricates unknowns; the consumers
were already aligned in `9be4c42`. Per the defect-only mandate, **no production
code was modified in this audit.**

## 19. Fixes

None required (see §18). The only change in this commit is **regression-test
hardening** — two new synthetic tests that lock the multiplicity (§16/§21) and
sidetrack-isolation (§14/§15) guarantees that previously had no explicit
coverage in `test_operations_intelligence_regressions.py`.

## 20. Unsupported KPIs (summary)

ECD; mud dilution/consumption; cement returns / actual excess; cement bond
quality; BHA-run / Bit-run duration across reports; formation-specific
time/ROP/NPT; Cost/Wellbore; Cost/Section.

## 21. Capability Gaps (summary)

Wellbore-level and Section-level KPI roll-up API for time/NPT/ROP/depth (data
model supports it; no canonical accessor yet); footage-weighted well/section ROP
(data + run engine exist; not surfaced as a well KPI); connection/trip/rotating/
sliding time breakdown (needs a guaranteed activity classifier).

## 22. Future Enhancements (non-defect, optional)

1. A `analyze_wellbore(wellbore_id)` / `analyze_section(section_id)` accessor
   reusing the existing per-child queries with an added id filter.
2. A footage-weighted ROP KPI (`Σbit_drilled / Σhours_on_bottom`) surfaced
   alongside the daily-average ROP.
3. Normalised time-category classification (drilling/rotating/sliding/…)
   if/when a canonical activity taxonomy is mandated.

## 23. Engineering KPI Coverage Matrix (§22)

| Domain | KPI | Status | Scope | Required Data | Available? | Reason |
|---|---|---|---|---|---|---|
| Time | Total / Productive / NPT hours, NPT% | CERTIFIED | Well | TimeLog24H.duration+is_npt | ✅ | direct |
| Time | Rotating/Sliding/Connection/Trip | PARTIALLY | Report | classified activity | ⚠️ | code-text only |
| Progress | Current depth | CERTIFIED | Well | depth_2400 | ✅ | direct |
| Progress | Footage/day, section progress | IMPLEMENTABLE | Well/Section | depth deltas / bit_drilled | ✅ | not surfaced |
| Drilling | ROP (daily avg) | CERTIFIED | Well | avg_rop | ✅ | unweighted mean |
| Drilling | ROP (footage-weighted) | IMPLEMENTABLE | Run/Section/Well | depth_in/out, hours_on_bottom | ✅ | engine exists |
| Drilling | MSE | CERTIFIED(engine) | Run | WOB/RPM/torque/ROP/size | ⚠️ | needs all inputs |
| Plan | Depth/Days/Cost variance | CERTIFIED | Well | WellPlan + actuals | ✅ | ActualVsPlanEngine |
| BHA/Bit | Per-run footage/ROP/MSE | CERTIFIED(engine) | Run | one bit record | ✅ | snapshot |
| BHA/Bit | Run duration across reports | UNSUPPORTED | Run | run identity | ✗ | snapshots only |
| Mud | MW/PV/YP/FL/pH/… trend | CERTIFIED | Well | MudReport fields | ✅ | direct |
| Mud | ECD | UNSUPPORTED | — | ECD field | ✗ | not collected |
| Mud | Dilution/consumption | UNSUPPORTED | — | consumption field | ✗ | not collected |
| Cement | Volume/TOC/excess (calc) | CERTIFIED(engine) | Job | volumes/geometry | ✅ | CementEngine |
| Cement | Returns / bond quality | UNSUPPORTED | — | returns/bond field | ✗ | not collected |
| Casing | Burst/collapse/tensile | CERTIFIED(engine) | String | OD/wall/yield | ✅ | CasingEngine |
| Directional | MD/TVD/inc/azi | CERTIFIED | Well | SurveyPoint | ✅ | direct |
| Directional | DLS/build/turn | CERTIFIED(engine) | Well | consecutive stations | ✅ | TrajectoryCalculator |
| Formation | Tops/lithology | PARTIALLY | Report | formations_json | ⚠️ | snapshot only |
| Formation | Formation ROP/NPT | UNSUPPORTED | — | time↔formation join | ✗ | no join key |
| Cost | Total / /day / /meter | CERTIFIED | Well | CostRecord + depth | ✅ | direct |
| Cost | Plan vs actual, category | CERTIFIED/IMPL | Well | planned/actual/category | ✅ | direct |
| Cost | /Wellbore, /Section | UNSUPPORTED | — | wellbore/section FK | ✗ | Well-scoped by design |

## 24. Final Certification (§24)

```
DRILLING ENGINEERING KPI COVERAGE = PASS WITH DOCUMENTED GAPS

KPI SEMANTIC INTEGRITY   = PASS   (unknown≠0≠default; denominators guarded)
KPI SCOPE INTEGRITY      = PASS   (well/wellbore isolation by id; no rig identity)
KPI MULTIPLICITY INTEGRITY = PASS (1×2×2×3×2 synthetic test: no fan-out)
NO-FABRICATION CONTRACT  = PASS   (no footage/hours/rate/ECD invented)

REMOTE CI = NOT OBSERVED   (sandbox cannot observe remote workflow runs)
```

The core engineering KPIs (time, NPT, depth/progress, ROP, plan-vs-actual, cost,
trajectory, casing/cement/mud fundamentals) are computable **truthfully** from
the canonical data that exists today, at Well scope, without contamination,
double-counting, or fabrication. The remaining items are honestly-classified
**capability gaps** (wellbore/section roll-up, footage-weighted ROP,
fine-grained time categories) and genuine **unsupported** KPIs (ECD, mud
consumption, cement returns/bond, cross-report BHA/Bit run duration,
formation-specific performance, cost below Well scope) — none of which are
treated as failures.

## 25. Final Repository Verification (§25)

- `git status` — only this audit doc + the regression-test additions changed;
  pre-existing untracked `.github/workflows/` unchanged.
- No production code modified; no speculative framework; no generated junk.
- New tests present in `tests/test_operations_intelligence_regressions.py`.
- Final gates: **910 passed, 4 skipped**; E722=0; F821=0; debt=5489; compileall
  clean.
