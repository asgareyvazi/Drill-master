# DrillMaster — KPI Consumer Alignment & Scope-Capability Forensic Audit

- **Date:** 2026-09-12
- **Repository:** `asgareyvazi/Drill-master`
- **Branch:** `arena/01a085e0-drill-master`
- **Baseline commit:** `2eaacf4` (prior KPI audit — certified foundation)
- **Audit change set:** this commit (w12 / w10 / report_engine NULL-alignment
  fixes + 4 regression tests + this report)
- **Sources of truth:** repository code, executable behaviour, and the physical
  SQLite schema exercised through the full test suite. Prior Arena reports and
  commit/doc claims were **not** treated as evidence; every finding below was
  reproduced from live behaviour on a freshly built database.

This audit is a **follow-on** to `2026-09-12_KPI_PERFORMANCE_FORENSIC_AUDIT.md`.
That report certified the *canonical* KPI layer
(`core.operations_intelligence.OperationsIntelligenceService`) and fixed KPI-01.
The open question it flagged, and this audit answers, is:

> Do the **UI/report consumers** of KPIs (Analysis tab, Planning NPT tab, and
> the DDR/EOWR report engine) obey the same no-fabrication contract as the
> canonical layer, or do they silently turn *unknown* metrics into fabricated
> zeros / 100% — a false user-visible fact (audit dimensions §18, §19, §23,
> §29)? And can KPIs be scoped below the Well (wellbore/section) without
> cross-scope contamination (§12, §13)?

---

## 1. Repository Identity (§2)

- `git branch --show-current` → `arena/01a085e0-drill-master`
- `git rev-parse HEAD` (baseline) → `2eaacf4`
- Certified chain present in `git log`: `2eaacf4` KPI-01 · `3b389ce` Cost ·
  `23821bc` BHA/Bit · `560c60d`/`c0e91b8`/`8a3d750` Wellbore v3.

## 2. Baseline (§3) — captured before any modification

| Gate | Result |
|---|---|
| pytest | **904 passed, 4 skipped**, 14 warnings |
| failed / errored / xfailed | 0 / 0 / 0 |
| Ruff E722 (core+dialogs+tabs+tests) | 0 |
| Ruff F821 (core+dialogs+tabs+tests) | 0 |
| Ruff debt (core+dialogs+tabs+tests) | **5489** (= ceiling `.github/ruff-debt-ceiling.txt`) |
| `compileall` core/tabs/ui | clean (exit 0) |

---

## 3. Architecture Map (§5) — where KPIs are actually computed

| Layer | Location | Role |
|---|---|---|
| **Canonical intelligence** | `core/operations_intelligence.py::OperationsIntelligenceService.analyze_well` | Deterministic, evidence-bearing, well-scoped KPIs. Already no-fabrication (returns `None` for unknown ROP/NPT/productive hours). Certified in prior audit. |
| **Analysis UI consumer** | `tabs/w12_Analysis.py` — `calculate_kpis`, `get_npt_data`, `get_performance_data` + their render methods | Re-derives KPIs directly from SQL for the dashboard cards. **Did not** share the canonical no-fabrication contract (see KPI-02). |
| **Planning NPT UI consumer** | `tabs/w10_Planning_Widget.py::NPTReportTab.get_npt_data` + `display_npt_data` | Re-derives NPT% for the planning NPT tab. Same fabrication defect (see KPI-03). |
| **Report/export consumer** | `core/report_engine.py` — DDR `_build_html` Time Analysis; EOWR aggregate summary | Re-derives productive/NPT % and aggregate KPIs for exported reports. Same fabrication defect (see KPI-04). |

**Finding (§5, §23):** KPI computation is **decentralized** — the canonical
service and three consumers each re-derive the same metrics. The formulas are
*semantically* the same (unweighted mean ROP; `NPT% = NPT_hours / total_hours`).
The defect was not the duplication itself but that the consumers used a
different **missing-data policy** than the canonical layer. The remedy chosen is
**semantic alignment, not centralization** (see §7 decision) — the minimal
change that removes the false facts without a speculative new abstraction.

---

## 4. Defects

### KPI-02 — Analysis tab fabricates 0 ROP / 0% NPT / 100% efficiency for unknown data (P1 → false P0 fact)

- **ID:** KPI-02
- **Severity:** High (silent unknown→zero fabrication; contradicts canonical layer; user-visible false fact)
- **Observed:** For a Well that has a daily report but **no** `DrillingParameters`
  and **no** `TimeLog24H` rows, `tabs/w12_Analysis.py::calculate_kpis` returned
  `avg_rop=0`, `best_rop=0`, `npt_percentage=0.0`, `efficiency=100.0`, and
  `get_npt_data` returned `total_npt=0.0`, `npt_percentage=0.0`. The dashboard
  cards therefore displayed **"0.0 m/hr"**, **"0.0%"** NPT and **"100.0%"**
  efficiency — asserting the well drilled at zero rate with a perfect,
  fully-productive operation, when in truth *nothing is known*.
- **Expected:** Unknown metrics are unknown, not zero. The cards must show the
  repository's existing unknown marker `"—"` (`core.text_utils.fmt_num`
  convention already used elsewhere in w12/w10), matching the canonical
  `OperationsIntelligenceService`, which returns `average_rop=None`,
  `npt_percent=None` for the identical well.
- **Root cause:** Defensive `... or 0` / `... or 1` idioms:
  `avg_rop = session.query(...).scalar() or 0`;
  `total_hours = session.query(...).scalar() or 1` (a **fabricated denominator**);
  `npt_pct = total_npt / total_hours * 100`; `efficiency = 100 - npt_pct`. A
  `None` (no rows) collapsed into `0`/`1` before it could be distinguished from a
  genuine recorded zero.
- **Evidence:** Live synthetic probe on a fresh DB (one Well, one DailyReport, no
  params, no time logs). Consumer path yielded `0.0 / 0.0 / 100.0`; canonical
  `analyze_well(...)["kpis"]` yielded `average_rop=None`, `npt_percent=None`.
- **Fix (minimal, repo-native):** In `calculate_kpis`, `get_npt_data`,
  `get_performance_data`, drop the `or 0` / `or 1` fabrication; keep `None` when
  the source query returns no rows; compute NPT%/efficiency **only when
  `total_hours` is truthy**, otherwise `None`. Render every numeric card through
  `fmt_num(value, digits, default=None)` so `None → "—"` while a genuine `0.0`
  still prints `"0.0"`. No new module, table, or abstraction introduced.
- **Regression test:** `tests/test_real_user_acceptance_regressions.py::`
  `test_analysis_kpis_report_unknown_not_zero` (unknown → `None` → `"—"`, and
  consumer agrees with canonical `None`) and
  `test_analysis_kpis_real_zero_npt_stays_zero` (recorded 24 h with no NPT rows
  → real `0.0` / `0%` / `100%`, ROP `12.5`).
- **Verification:** Both new tests pass; full suite green (§6).

### KPI-03 — Planning NPT tab fabricates 0% NPT for unknown data (P1)

- **ID:** KPI-03
- **Severity:** Medium (same fabrication class, narrower surface: the Planning NPT tab)
- **Observed:** `tabs/w10_Planning_Widget.py::NPTReportTab.get_npt_data` used
  `total_hours = ...scalar() or 1` and rendered `npt_percent_card = "0.0"` and
  the empty-state cards as `"0.0"`, i.e. **0% NPT** for a well with no recorded
  time — the same false "perfectly productive" claim as KPI-02.
- **Expected:** `"—"` when NPT/total hours are unknown; a real `0.0` once time is
  recorded with no NPT rows.
- **Root cause:** identical `... or 1` denominator fabrication.
- **Evidence:** Synthetic probe — before any `TimeLog24H`, `total_npt=None`,
  `npt_percentage=None`; after adding a 24 h non-NPT log, `0.0` / `0.0`.
- **Fix:** `total_hours = ...scalar()`; compute `npt_pct` only when truthy, else
  `None` (and `total_npt=None`); empty-state and value cards render `"—"` via
  `fmt_num(..., default=None)`.
- **Regression test:** `test_planning_npt_unknown_not_zero_then_real_zero`.
- **Verification:** passes; full suite green.

### KPI-04 — Report engine claims 100% productive / 0% NPT for empty time logs (P1)

- **ID:** KPI-04
- **Severity:** Medium (exported DDR/EOWR reports — a durable, shareable false fact)
- **Observed:** In `core/report_engine.py`:
  1. DDR `_build_html` Time Analysis: `pt_pct = (pt/total*100) if total > 0 else 100`,
     `npt_pct = ... else 0`. A day with no time logs rendered
     **"Productive … (100%) / NPT … (0%) / Efficiency 100%"**.
  2. EOWR aggregate: `npt_pct = ... if total_hours > 0 else 0`, plus
     `s.setdefault("avg_rop"/"total_npt"/"npt_pct"/"final_depth", 0)` — unknowns
     defaulted to `0`.
- **Expected:** unknown percentages render `"—"` (and the visual time-bar draws
  empty) rather than a fabricated fully-productive day; unknown aggregate KPIs
  default to `None` (→ `"—"` via the already-present `fmt_num(..., default=None)`
  render sites).
- **Root cause:** `else 100` / `else 0` branches and `setdefault(..., 0)`.
- **Evidence:** DDR HTML for the baseline no-time-log report previously contained
  `(100%)` / `<b>100%</b>`; after the fix it contains neither and contains `"—"`.
- **Fix:** guard the single-report Time Analysis on `total > 0` (render `"—"` and
  zero-width bars otherwise); compute EOWR `total_npt`/`npt_pct` as `None` when no
  time logs exist; change the six aggregate `setdefault` fallbacks from `0`/`None`
  to `None` where the value is a metric (kept `total_reports=0`, a genuine count).
- **Regression test:** `test_eowr_and_ddr_time_analysis_no_false_full_productivity`
  (asserts DDR HTML has no `(100%)` / `<b>100%</b>`, does contain `"—"`; EOWR HTML
  has no literal `<td>None</td>` and does contain `"—"`).
- **Verification:** passes; the pre-existing
  `test_eowr_incomplete_survey_and_optional_plan_export` still passes (no `None`
  leakage into HTML).

---

## 5. Non-defects — deliberately **not** changed (constraints §34–§37)

- **Unweighted mean ROP (§8, §22):** `calculate_kpis` and the canonical layer
  average `DrillingParameters.avg_rop` unweighted. A footage/interval-weighted
  `SUM(depth)/SUM(time)` ROP would be more rigorous, **but** the schema stores no
  per-parameter footage or on-bottom-hours field to weight by. Introducing one is
  a schema change and a new KPI — out of scope. Left unweighted; documented as a
  precision limitation, not a false fact.
- **w12 cost "what-if" analyzer (`_analyze_cost`):** uses hard-coded rig/spread
  day-rates ($45k/$15k). This is a scenario calculator, **not** a canonical Cost
  KPI, and is outside the certified Cost surface (Cost/Well, Cost/Meter,
  Cost/Day). Only its consumption of the now-`None` NPT value was made
  None-safe; the day-rate model was left untouched (§15, §17).
- **No `kpi_service.py`, no persisted KPI tables (§7, §25):** see decision below.

### §7 decision — align semantics, do **not** centralize

Two viable options were weighed:

- **Option A (adopted):** leave the canonical service and the consumers as
  separate deterministic derivations, and make the consumers obey the **same
  missing-data contract** (`None` for unknown; `fmt_num(default=None)` for
  display). Minimal, defect-scoped, no new abstraction, no behavioural change for
  wells that already had data.
- **Option B (rejected):** route every consumer through
  `OperationsIntelligenceService` or a new `kpi_service.py`. Rejected because it
  is a large redesign of Home/Analysis/Planning/Export (explicitly forbidden by
  §34–§37), risks behavioural drift on the many wells that already render
  correctly, and the audit found only a *missing-data-policy* mismatch — not a
  *formula* mismatch — which Option A fully resolves.

Prefer-deterministic-calc-over-persisted-copies (§25) is upheld: nothing is
persisted; all KPIs remain computed on demand from canonical facts.

---

## 6. Scope-capability findings (§12, §13, §21)

- **Well isolation (§12):** Every KPI query in `w12`, `w10`, `report_engine`, and
  the canonical service filters on `well_id` (and `TimeLog24H` reaches the well
  via `join(DailyReport)` on `report_id`). No KPI is scoped by `rig`,
  `well_name`, or `section_name` text. A sidetrack/second Well cannot contaminate
  another Well's KPIs. **PASS.**
- **Double-counting / 1-to-many joins (§21):** NPT hours are summed from
  `TimeLog24H` joined once to `DailyReport`; ROP is aggregated from
  `DrillingParameters` directly. No KPI multiplies rows by joining two
  independent one-to-many children of the same parent. **PASS** — no
  join-multiplication defect reproduced.
- **Wellbore-/Section-level KPI (§13) — CAPABILITY GAP, not a defect:** KPIs are
  computed at **Well** granularity only. The Planning NPT tab accepts an optional
  `section_id`/`report_id` filter, but the Analysis dashboard and the canonical
  service do not expose per-wellbore or per-section KPI roll-ups. This is a
  *missing feature*, not a false fact — no incorrect wellbore/section number is
  displayed anywhere. Adding wellbore/section KPI scoping is a new feature
  (potentially a schema/UX change) and is **explicitly out of scope** for a
  defect-only audit. Documented here so the gap is on record (R-5).

---

## 7. Gate matrix (§40)

| Gate | Description | Result |
|---|---|---|
| A | Repo identity confirmed (branch/HEAD) | ✅ PASS |
| B | Baseline captured before changes (904/4) | ✅ PASS |
| C | KPI architecture mapped (canonical + 3 consumers) | ✅ PASS |
| D | ROP semantics reviewed (§8) | ✅ PASS (unweighted; limitation documented) |
| E | Time semantics reviewed (§9) | ✅ PASS |
| F | NPT semantics — unknown≠0, denominator not fabricated (§10) | ✅ FIXED (KPI-02/03/04) |
| G | Aggregation uses IDs not text (§11) | ✅ PASS |
| H | Well isolation / no cross-well contamination (§12) | ✅ PASS |
| I | Section/Wellbore KPI scope (§13) | ⚠️ CAPABILITY GAP (documented, not a defect) |
| J | BHA/Bit KPI unaffected by this change | ✅ PASS (out of scope; untouched) |
| K | Cost KPI ownership unaffected (§15) | ✅ PASS (day-rate what-if left as-is) |
| L | Plan vs Actual not conflated (§17) | ✅ PASS |
| M | unknown / NULL / 0 / NA distinction (§18) | ✅ FIXED |
| N | Division-by-zero → no misleading 0/100/Inf/NaN (§19) | ✅ FIXED |
| O | Unit consistency (§20) | ✅ PASS (no unit change) |
| P | Double-count / 1-to-many join (§21) | ✅ PASS (synthetic check) |
| Q | Consumer ↔ canonical semantic agreement (§23) | ✅ FIXED |
| R | Regression tests added; no test weakened; debt/ lint held | ✅ PASS |

## 8. Final verification (§42)

| Gate | Result |
|---|---|
| pytest | **908 passed, 4 skipped** (904 baseline + 4 new tests) |
| failed / errored / xfailed | 0 / 0 / 0 |
| Ruff E722 (core+dialogs+tabs+tests) | 0 |
| Ruff F821 (core+dialogs+tabs+tests) | 0 |
| Ruff debt (core+dialogs+tabs+tests) | **5489** (= ceiling, unchanged) |
| `compileall` core/tabs/ui | clean (exit 0) |
| Files changed | `core/report_engine.py`, `tabs/w10_Planning_Widget.py`, `tabs/w12_Analysis.py`, `tests/test_real_user_acceptance_regressions.py` |

No test was deleted, skipped, weakened, or `xfail`ed; the debt ceiling was not
raised; no lint was suppressed; no unrelated module was modified.

## 9. Verdict (§41)

> **PASS WITH REMAINING RISKS.**

The three consumer-side NULL→zero fabrication defects (KPI-02 Analysis, KPI-03
Planning NPT, KPI-04 report engine) are fixed with minimal, evidence-driven,
repo-native changes and locked by regression tests; the consumers now agree with
the certified canonical layer, distinguishing *unknown* (`"—"`) from a genuine
recorded *zero*. Well isolation and no-double-counting were verified. The
**remaining risk** is a documented *capability gap* — KPIs are computed at Well
granularity only; there is no per-wellbore/per-section KPI roll-up (Gate I / R-5).
This is a missing feature, not a false fact, and was intentionally left
unimplemented per the defect-only scope constraints.

### REMOTE CI status (§38)

**NOT OBSERVED / BLOCKED.** Remote CI status was not observed from this
environment (workflow pushes are permission-blocked in the sandbox). No claim of
a remote CI PASS is made. Local gates only are reported above.
