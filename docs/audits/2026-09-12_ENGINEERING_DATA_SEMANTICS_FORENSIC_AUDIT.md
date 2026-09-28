# DrillMaster — Engineering Data Semantics & Calculation-Readiness Forensic Audit

- **Date:** 2026-09-12
- **Repository:** `asgareyvazi/Drill-master`
- **Branch:** `arena/01a085e0-drill-master`
- **HEAD at audit start:** `472903f`
- **Sources of truth:** the SQLAlchemy models (`core/database.py`), the single
  canonical field registry (`core/canonical_schema.py`), the import service
  (`core/ddr_import_service.py`), the numeric normaliser
  (`core/value_normalizer.py`), the unit engine (`core/unit_manager.py`), the
  DDR entry form (`tabs/w3_drilling_report.py`), the calculation engines
  (`core/engineering/`), and live behaviour on freshly built SQLite databases.
  Prior reports, this prompt, variable names, and UI labels were **not** trusted
  as evidence.

This is a **data-semantics and calculation-readiness audit**. It does **not**
implement weighted ROP or any KPI. Its purpose is to prove whether the existing
source fields have a defensible engineering meaning good enough to support future
calculations.

Legend used throughout: **FACT** (stored source value), **DERIVED** (computed
from facts), **ASSUMPTION** (relied-upon but unverified), **CAPABILITY GAP**
(missing but not wrong), **CONFIRMED DEFECT** (reproduced wrong behaviour).

---

## 1. Repository Identity

| Check | Value |
|---|---|
| branch | `arena/01a085e0-drill-master` |
| HEAD | `472903ff9e8ab188f0368f4f99ddecc66e7aab2e` |
| tree | clean (only pre-existing untracked `.github/workflows/`) |

## 2. Baseline (before any change)

| Gate | Result |
|---|---|
| pytest | **910 passed, 4 skipped** |
| failed / errored / xfailed | 0 / 0 / 0 |
| Ruff E722 / F821 (core+dialogs+tabs+tests) | 0 / 0 |
| Ruff debt (core+dialogs+tabs+tests) | 5489 (= ceiling) |
| compileall core/tabs/ui/dialogs | clean |

## 3. Engineering Field Inventory & Semantics (§2, §3)

Traced pipeline: **source doc → extractor (MinerU/Excel) → canonical mapper
(`canonical_schema.py`) → `_save_drilling_params` → `save_drilling_parameters`
upsert → ORM → query/UI**.

| Field | Entity | Type | Unit (declared) | Meaning | Scope | NULL | Zero | Interval/Cumulative | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| `depth_2400` | DailyReport | Float | m (MD) | Hole MD at 24:00 (aliases: "bit depth","current depth","measured depth","td") | DDR | unknown | valid | daily snapshot | `canonical_schema.py:130` |
| `depth_0000/0600` | DailyReport | Float | m (MD) | Hole MD at 00:00 / 06:00 | DDR | unknown | valid | daily snapshot | `canonical_schema.py:128-129` |
| `depth_in` | DrillingParameters | Float | m (MD) | Bit-run interval start MD | DDR bit-run summary | unknown | valid | interval boundary | `canonical_schema.py:235`, `w3:689` |
| `depth_out` | DrillingParameters | Float | m (MD) | Bit-run interval end MD | DDR bit-run summary | unknown | valid | interval boundary | `canonical_schema.py:236`, `w3:690` |
| `bit_drilled` | DrillingParameters | Float | m | Footage = depth_out − depth_in (clamped ≥0) | DDR | unknown | valid | interval | `w3:680-682` |
| `cum_drilled` | DrillingParameters | Float | m | Cumulative footage | DDR | unknown | valid | cumulative | `canonical_schema.py:218` |
| `hours_on_bottom` | DrillingParameters | Float | hr | On-bottom drilling time (ROP denominator by construction) | DDR bit-run summary | unknown | valid | per-run | `w3:691`, `managers.calculate_rop` |
| `cum_hours` | DrillingParameters | Float | hr | Cumulative on-bottom hours | DDR | unknown | valid | cumulative | `canonical_schema.py:220` |
| `avg_rop` | DrillingParameters / DailyReport | Float | m/hr | (depth_out−depth_in)/hours_on_bottom | DDR | unknown | valid | DERIVED | `w3:687-693`, `canonical_schema.py:132,237` |
| `duration` | TimeLog24H | Float | hr | Activity duration (explicit) | time log row | unknown | valid | interval | schema |
| `is_npt` | TimeLog24H | Bool | — | NPT flag | time log row | — | — | fact | schema |
| `wob_min/max` | DrillingParameters | Float | klb | Weight-on-bit range | DDR | unknown | valid | range | `canonical_schema.py:227-228` |
| `rpm_min/max` | DrillingParameters | Float | (rpm) | Rotary speed range | DDR | unknown | valid | range | `canonical_schema.py:229-230` |
| `torque_min/max` | DrillingParameters | Float | kft-lbs | Torque range | DDR | unknown | valid | range | `canonical_schema.py:231-232` |
| `mw` | MudReport | Float | pcf (converted) | Mud weight (density-normalised to PCF) | mud report | unknown | valid | measurement | `mud_records.mud_density_pcf` |

## 4. Depth Field Forensic Audit (§4)

- **Physical meaning:** all depth fields are **MD in metres** (canonical
  `length`/`m`). `depth_2400` explicitly aliases "measured depth"/"bit
  depth"/"td". No field is declared as TVD at the DDR/DrillingParameters level;
  TVD lives only in `SurveyPoint.tvd`/`TrajectoryCalculation` (FACT/DERIVED from
  survey math).
- **Temporal meaning:** `depth_0000/0600/2400` are **daily snapshots** at fixed
  clock times. `depth_in`/`depth_out` are **interval boundaries** of a single
  bit run recorded on that DDR. `cum_drilled`/`cum_hours` are **cumulative**.
- **Scope:** depth snapshots belong to `DailyReport`; interval depths belong to
  `DrillingParameters` (one row per DDR — see §5). Section/Wellbore/Well carry no
  independent depth of their own; they are reached via `DailyReport` foreign keys.
- **Units:** declared metres in the canonical registry; **stored as-is** (no
  per-import length conversion — see §10/§12). ASSUMPTION: source templates are
  metric.

## 5. `depth_in` / `depth_out` Semantics (§5) — the 14 questions answered

1. **Source document:** the DDR "Bit run summary" / drilling-parameters section.
2. **Column mapping:** canonical aliases "depth in"/"depth out"
   (`canonical_schema.py:235-236`).
3. **Canonical field:** `drilling_params.depth_in` / `depth_out`.
4. **Multiple rows per DDR?** **No.** `save_drilling_parameters` **upserts by
   `report_id`** (`core/database.py:4750`): a second save for the same report
   updates the existing row. Confirmed by
   `test_drilling_parameters_are_one_upserted_row_per_report`.
5. **Interval boundaries?** Yes — `bit_drilled = depth_out − depth_in`
   (`w3:680-682`).
6. **Cumulative?** No; `cum_drilled`/`cum_hours` are the cumulative columns.
7. **MD?** Yes (length/m, MD).
8. **`depth_out < depth_in`?** **Rejected** at import validation ("Depth out must
   be >= depth in", `import_quality.py:732-735`). Confirmed by
   `test_import_validation_rejects_negative_footage`.
9. **NULL possible?** Yes — both are non-critical; `to_float` yields `None`.
10. **Zero valid?** Yes (e.g. spud at surface).
11. **Non-drilling rows?** The single per-DDR row is a bit-run summary; a DDR
    with no drilling simply has NULL depth_in/out.
12. **Same interval twice?** Not within a DDR (single row). Across DDRs the
    canonical daily convention is sequential intervals (prev depth_out ≈ next
    depth_in), verified in the §21 dataset.
13. **Overwritten on import?** Yes — upsert replaces prior values for the same
    report (intended re-import behaviour).
14. **Rounded?** `bit_drilled` rounded to 2 dp in the form; stored depths keep
    source precision.

## 6. `hours_on_bottom` Semantics (§6)

- **Meaning: on-bottom drilling time.** This is proven by construction, not by
  the name: the DDR form computes `avg_rop = calculate_rop(depth_in, depth_out,
  hours_on_bottom)` (`w3:687-693`), and `DrillingManager.calculate_rop` delegates
  to `BitPerformanceEngine.from_run` which computes `ROP = footage /
  hours_on_bottom`. So `hours_on_bottom` **is** the ROP denominator — on-bottom
  drilling hours.
- **Source/unit:** canonical alias "hours on bottom" / "bit hours on bottom",
  unit `hr` (`canonical_schema.py:219,238`).
- **Interval vs cumulative:** per-run (`cum_hours` is the cumulative sibling).
- **NULL / zero:** `None` when missing; `BitPerformanceEngine` returns ROP
  `None` when hours are 0 or missing (never divides).
- **What it does NOT include:** by the footage/ROP construction it represents
  drilling on bottom. There is **no schema field** separately recording rotary
  vs sliding vs reaming vs backreaming vs connection vs circulation time — those
  are only implicit in `TimeLog24H` activity codes. **CAPABILITY GAP:** a precise
  decomposition of on-bottom hours is not available.
- **Semantic drift note (not a defect):** `w12_Analysis.py:1798` labels
  `hours_on_bottom` as "rotating time" in a bit cost-per-foot screen. This is a
  loose UI label, not a data-model claim, and does not affect any stored value or
  canonical KPI. Documented for awareness.

## 7. Footage Calculation Readiness (§7)

`footage = depth_out − depth_in` is **valid per DDR** given: single upserted row
(no duplicate intervals), negative intervals rejected at import, NULL preserved.
Cases:

| Case | Inputs | Behaviour | Verdict |
|---|---|---|---|
| A | in=1000,out=1100 | footage 100 | ✅ |
| B | in=None,out=1100 | footage unknown (NULL) | ✅ must stay unknown |
| C | in=1000,out=None | footage unknown (NULL) | ✅ must stay unknown |
| D | in=1000,out=1000 | footage 0 (real zero) | ✅ preserved |
| E | in=1100,out=1000 | **import error** (rejected) | ✅ not silently zeroed |

## 8. Weighted-ROP Readiness (§8) — **PARTIAL**, with a mandatory design rule

`weighted_rop = Σ(depth_out − depth_in) / Σ(hours_on_bottom)` — readiness by
scope:

| Scope | Readiness | Reason |
|---|---|---|
| DDR | READY | single row; footage & hours co-located |
| Section | PARTIAL | `DailyReport.section_id` exists; must filter by id and pair NULLs |
| Wellbore | PARTIAL | `DailyReport.wellbore_id` (v3) exists but may be NULL on legacy rows |
| Well | READY | `well_id` join is reliable; §21 dataset confirms |

**Mandatory design rule (proven, `test_weighted_rop_must_pair_footage_and_hours_per_row`):**
a future implementation **must pair footage and hours per row** (both non-NULL).
A naive `SUM(depth_out−depth_in)/SUM(hours_on_bottom)` is **wrong**: SQL `SUM`
drops NULL footage from the numerator while still counting that row's hours in
the denominator. Reproduced: a well with row1 (100 m / 5 h) + row2 (NULL footage
/ 6 h) gives a naive **9.09 m/hr** vs the correct paired **20.0 m/hr**.

The denominator must be `hours_on_bottom` only — never elapsed hours, and never
mixing NPT/trip/connection/circulation time (those are `TimeLog24H`, a different
semantic).

## 9. Multiple-Row Semantics (§9)

- **DrillingParameters:** exactly one upserted row per DDR (§5.4). No per-DDR
  multi-interval drilling breakdown exists.
- **TimeLog24H / TimeLogMorning:** many rows per DDR (sequential activity
  intervals with explicit `duration` + `is_npt`). These are the granular time
  facts; they are **not** the footage source.
- Consequence: footage aggregation across DDRs is a clean sum of one interval per
  report; no de-duplication of repeated intervals is required within a DDR.

## 10. Import Pipeline Forensics (§10)

- Numeric parsing via `ValueNormalizer` handles comma decimals, unicode minus,
  fractions/mixed fractions, and a "K" thousands suffix; rejects NaN/Inf and
  out-of-range values; unknown unit suffixes are refused rather than stripped.
- Missing → `None` (NULL), never fabricated (`to_float`/`to_int`).
- `depth_out < depth_in` rejected (§7 Case E).
- Bit-run aliases (`bit_hours_on_bottom`→`hours_on_bottom`, etc.) are normalised,
  never dropped (`ddr_import_service.py:872-885`).
- **No silent loss reproduced** for depth/hours/ROP fields.

## 11. Field-Loss / Coercion Audit (§11)

`or 0` / `or 1` / `float(...)` patterns around engineering source fields:

| Location | Pattern | Classification |
|---|---|---|
| `ValueNormalizer.to_float/to_int` | `None` for missing | **SAFE** (no fabrication) |
| `w3:680-682` `bit_drilled` clamp `<0 → 0` | UI convenience field | **SAFE** (validator already rejects negative; stored footage recomputable) |
| `w12_Analysis.py:1336` `p.hours_on_bottom or 0` | per-row display in a screen | **POTENTIAL RISK** (a NULL hour shown as 0 in that cost-per-foot screen), but not a canonical KPI and not persisted |
| `managers.calculate_rop` returns `0.0` on engine failure | UI live calc | **SAFE-ish** (screening field; canonical layer uses None) |

No **CONFIRMED DEFECT**. The one POTENTIAL RISK is a non-canonical UI screen
already outside the certified KPI surface; per the defect-only rule it is
documented, not changed.

## 12. Unit Forensic Audit (§12)

- Canonical base units (`unit_manager.py`): length/depth = **m** (feet→0.3048),
  ROP = m/hr, pressure psi, density has full SG/PPG/PCF conversion, etc. A
  complete `UnitManager.convert` + `detect_unit` exists.
- **Applied conversions at import:** only **mud density → PCF**
  (`mud_records.mud_density_pcf`) and the AI-tools path. **Depth and hours are
  stored as-is** — no per-import length/time unit detection or conversion.
- **CAPABILITY GAP (not a defect):** if a source workbook supplied depth in feet,
  it would be stored unconverted (canonical templates are metric, so this is an
  input-contract assumption, not a reproduced fault). A `normalize_row` unit_map
  exists and preserves NULL (`test_p0_unit_preservation`) but is not wired into
  the DDR depth path. No unit framework was invented.

## 13. Time Field Semantics (§13)

- `TimeLog24H`: explicit `duration` (hr) per activity row + `is_npt` +
  `main_code`/`sub_code`/`main_phase`. Productive = Σduration where `not is_npt`;
  NPT = Σduration where `is_npt`.
- `TimeLogMorning`: parallel morning-tour representation.
- **Two representations exist** — Σ(activity durations) and (implicitly) a 24 h
  day. The canonical layer sums recorded `duration`; it does **not** assume 24 h
  and does **not** add the two representations together (verified in prior KPI
  audits). Authoritative source = Σ`TimeLog24H.duration`.

## 14. BHA / Bit Semantics (§14)

- `BHAReport.bha_data_json`, `BitReport.bit_records_json` are **report-scoped JSON
  snapshots** (FACT snapshots), plus `DrillingParameters` bit columns
  (`bit_size` in inches, `bit_type`, `manufacturer`, `bit_serial`, `iadc_code`,
  `bit_dull_condition`).
- Classification: bit size/type/serial/manufacturer/dull = **FACT (snapshot)**;
  per-run footage/hours/ROP/MSE = **DERIVED** (`BitPerformanceEngine`); **run
  identity across reports = UNKNOWN** (no run entity — deliberate). No
  longitudinal run entity was created.

## 15. Mud Semantics (§15)

- `MudReport` stores measured facts: `mw` (→PCF), `pv`, `yp`, `funnel_vis`,
  `gel_10s/10m`, `fl`, `cake_thickness`, `ph`, `temperature`,
  `solid/oil/water_percent`, `chloride`, `calcium`, `kcl`, `mbt`,
  `total_hardness`, plus `loss_downhole/surface`, `total_circulated`,
  `volume_hole`. All FACT (measurement), report-scoped, one row per DDR (upsert).
- **ECD:** no field. Future ECD would need MW + geometry + flow/annulus model →
  **NOT READY** (would fabricate). **Dilution/consumption:** no field → NOT READY.

## 16. Directional Semantics (§16)

- `SurveyPoint`: `md` (FACT, required), `inc`/`azi` (FACT, nullable — engine
  refuses incomplete stations), `tvd`/`north`/`east`/`vs`/`dls` (stored; may be
  IMPORTED or CALCULATED). `TrajectoryCalculator` (minimum curvature) recomputes
  `dls`/`build_rate`/`turn_rate` deterministically → **DERIVED and reproducible**.
- Classification: MD/inc/azi = **FACT**; TVD/DLS/build/turn = **DERIVED**
  (reproducible from stations); no engine rewrite needed.

## 17. Casing / Cement Semantics (§17)

- `CasingReport`: `casing_json`, `tally_json`, ratings (`burst/collapse_pressure`,
  `tensile_strength`, `makeup_torque`, `drift_diameter`, `running_speed`) — FACT.
- `CementReport`: `cement_volume`, `displacement_volume`, `slurry_density/yield`,
  `top_of_cement`, `bottom_of_cement`, `compressive_strength`, `fluid_loss`,
  `thickening_time` — FACT. `CementEngine` computes displacement/TOC/excess —
  DERIVED.
- **UNKNOWN / not collected:** cement returns, actual excess, bond quality.

## 18. Formation Semantics (§18)

- `FormationReport.formations_json` — report-scoped snapshot (tops/lithology only
  if authored). No normalised top/base columns and **no join key** binding a
  formation interval to a drilling interval or time log. **CAPABILITY GAP:**
  formation-specific ROP/NPT cannot be computed without fabricating the join.

## 19. Cost Semantics (§19)

- `CostRecord` is **Well-scoped** (no wellbore/section FK): `category`,
  `planned_cost`, `actual_cost`, `variance`, `currency`, `vendor`, `afe_number`,
  `cost_type` (OPEX/…), `status` (Pending/…), `cost_date`.
- `actual_cost` is a recorded amount (FACT); `planned_cost` a plan (FACT);
  `variance` derived. No rig-rate is invented. No currency conversion mechanism
  is wired for cost. Cost architecture left unchanged.

## 20. Provenance (§20)

- **At import:** review/lineage objects carry `source_cell`, `source_row`,
  `target_field`, `canonical_unit`, confidence, transform
  (`import_quality.py`, `ddr_import_service.py`). Professional export can emit
  `_provenance`.
- **After commit:** the `DrillingParameters`/`DailyReport` ORM rows have **no
  per-field source columns**; a stored depth/hours value cannot retroactively
  answer "which source cell produced me". **CAPABILITY GAP** (not a defect); no
  new provenance system was created.

## 21. Synthetic Validation (§21)

Dataset: Well A original wellbore (DDR1 1000→1100 @5 h; DDR2 1100→1250 @6 h) +
sidetrack (DDR3 800→900 @10 h); foreign Well B (0→1000 @1 h). Live results:

| Scope | Σfootage | Σhours | wROP | Correct? |
|---|---|---|---|---|
| Well A (both bores) | 350 | 21 | 16.67 | ✅ 250+100 / 11+10 |
| Well A original only | 250 | 11 | 22.73 | ✅ by `wellbore_id` |
| Well A sidetrack only | 100 | 10 | 10.00 | ✅ by `wellbore_id` |
| Well B | 1000 | 1 | 1000 | ✅ excluded from A |

Isolation by id holds; original/sidetrack are separable; no foreign-well
contamination. (No production weighted-ROP feature was added.)

## 22. Confirmed Defects (§21)

**None.** No wrong stored value or wrong canonical calculation was reproduced.

## 23. Capability Gaps (summary)

1. On-bottom-hours decomposition (rotary/sliding/reaming/connection) — no schema
   field.
2. Per-import depth/hours unit auto-detection/conversion — only mud density is
   converted; depth/hours trusted metric.
3. Persisted per-field provenance on committed engineering rows — provenance is
   import-time only.
4. Formation↔drilling-interval join key — absent.
5. Wellbore/section KPI roll-up API and footage-weighted-ROP surfacing (data
   ready; not exposed).
6. UI label drift: `hours_on_bottom` shown as "rotating time" in one w12 screen.

## 24. Future Calculation Readiness Matrix (§22)

| Calculation | Readiness |
|---|---|
| Footage-weighted ROP | **PARTIAL** (READY at DDR/Well; must pair NULLs; PARTIAL at Section/Wellbore) |
| Footage/day | **READY** (`bit_drilled` or Δdepth_2400 by id) |
| Wellbore KPI | **PARTIAL** (FK exists; may be NULL on legacy rows) |
| Section KPI | **PARTIAL** (FK exists; roll-up API absent) |
| Fine-grained time KPI | **PARTIAL** (only via activity-code text/taxonomy) |
| BHA Run KPI | **NOT READY** (no run identity) |
| Bit Run KPI | **NOT READY** across reports (per-DDR run only = READY) |
| ECD | **NOT READY** (no ECD/geometry model input) |
| Mud consumption | **NOT READY** (no consumption field) |
| Formation ROP | **NOT READY** (no join key) |
| Directional comparison | **READY** (survey facts + reproducible engine) |
| Construction KPI (casing/cement) | **PARTIAL** (ratings/volumes READY; returns/bond NOT READY) |

## 25. Final Architecture Conclusion (§24)

The core drilling source fields (`depth_in`, `depth_out`, `hours_on_bottom`,
`bit_drilled`, `depth_2400`, `duration`/`is_npt`, mud/survey/casing/cement facts)
have **defensible, internally-consistent engineering semantics**: metres MD, hr
on-bottom, m/hr ROP, one upserted bit-run row per DDR, negative footage rejected,
NULL preserved, isolation by id. Advanced calculations are **readiness-gated**,
not blocked — the principal design constraint for the most-requested one
(footage-weighted ROP) is the **per-row footage↔hours pairing rule** proven here.
No production change was warranted; four regression tests lock the newly
established semantics.

## 26. Final Certification

```
ENGINEERING DATA SEMANTICS = PASS WITH DOCUMENTED GAPS

WEIGHTED ROP READINESS       = PARTIAL   (READY at DDR/Well; pair NULLs; Section/Wellbore PARTIAL)
WELLBORE KPI READINESS       = PARTIAL
SECTION KPI READINESS        = PARTIAL
TIME KPI READINESS           = PARTIAL   (coarse productive/NPT READY; fine categories PARTIAL)
BHA/BIT RUN KPI READINESS    = NOT READY (no cross-report run identity)
MUD ADVANCED KPI READINESS   = NOT READY (no ECD / consumption fields)
DIRECTIONAL KPI READINESS    = READY
CONSTRUCTION KPI READINESS   = PARTIAL
UNIT SEMANTICS               = PASS WITH DOCUMENTED GAP (depth/hours trusted metric; only mud density converted)
PROVENANCE                   = IMPORT-TIME ONLY (capability gap; not persisted per field)
NO-FABRICATION CONTRACT      = PASS

REMOTE CI = NOT OBSERVED   (sandbox cannot observe remote workflow runs)
```

## 27. Final Repository Verification

- `git status` — only this audit doc + `tests/test_engineering_data_semantics.py`
  added; pre-existing untracked `.github/workflows/` unchanged.
- **No production code modified.**
- Final gates: **914 passed, 4 skipped**; E722=0; F821=0; debt=5489; compileall
  clean.
